"""Automatic resume exercises the real local MCP transport and verified API fixture.
No Mistral account or public tunnel is used; barriers expose cancellation races.
"""
import tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from test_automatic_connector import auto,web,A,B,Service

class AutoResumeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.events=[];self.releases=[]
  self.web=web.Connector(self.events.append,self.root/'private',approval_wait=0)
  for key,name in [(A,'Project A'),(B,'Project B')]:
   folder=self.root/name;folder.mkdir();(folder/'text.txt').write_text('Local fixture')
   self.web.select({'id':key,'name':name});self.web.link(key,folder)
  self.web.select({'id':A,'name':'Project A'});self.auth_calls=0
  def authenticate(cancel,announce):self.auth_calls+=1;announce('https://console.mistral.ai/authorize?fixture=1');return 'fixture-account-secret'
  self.engine=SimpleNamespace(web=self.web,key='fixture-existing-account-key',lock=threading.RLock(),external_output=self.events.append,auth=SimpleNamespace(authenticate=authenticate))
  self.service=Service(auto.SetupError,self.web)
  self.real_probe=lambda server,token,guard,cancel:(guard(),self.service.discover(server.rsplit('/',1)[1],token),guard())
  self.manager=auto.AutomaticConnector(self.engine,api_factory=self.service.api,probe=self.real_probe)
  def tunnel():self.web.tunnel_url='https://fixture.trycloudflare.com';self.web.tunnel_status='running';self.web.state()
  self.web.start_tunnel=tunnel
 def tearDown(self):
  for release in self.releases:release.set()
  self.manager.close()
  if self.manager.job:self.manager.job['thread'].join(4)
  self.web.close();self.tmp.cleanup()
 def wait(self,predicate,seconds=6):
  until=time.monotonic()+seconds
  while time.monotonic()<until:
   if predicate():return
   time.sleep(.01)
  self.fail('Scheduler did not reach the expected state')
 def idle(self):
  def check():
   with self.manager.lock:return self.manager.pending is None and (self.manager.job is None or not self.manager.job['thread'].is_alive())
  self.wait(check)
 def switch(self,key,automatic=False):
  self.web.select({'id':key,'name':self.web.projects[key]['name']} if key else None);self.manager.context(auto_connect=automatic)
 def manual(self,key):
  if (self.web.active or {}).get('id')!=key:self.switch(key)
  self.manager.connect(key);self.idle();self.assertEqual(self.manager.states[key]['status'],'connected')
 def approved_pair(self):self.manual(A);self.manual(B)
 def blocking_probe(self):
  entered=threading.Event();release=threading.Event();self.releases.append(release);first=True
  def probe(server,token,guard,cancel):
   nonlocal first
   if first:first=False;entered.set();release.wait(4)
   self.real_probe(server,token,guard,cancel)
  self.manager.probe=probe;return entered,release
 def test_legacy_folder_requires_manual_success_before_any_automatic_access(self):
  self.assertFalse(self.web.auto_approved(A));self.manager.context(auto_connect=True);self.idle()
  self.assertEqual(self.service.calls,[]);self.assertEqual(self.auth_calls,0);self.assertNotIn(A,self.web.enabled)
  self.assertEqual(self.manager.states[A]['pause_reason'],'approval')
  self.manual(A);self.assertTrue(self.web.auto_approved(A));self.assertTrue(self.web.can_auto_connect(A))
 def test_previously_verified_projects_resume_without_duplicate_connectors_or_login(self):
  self.approved_pair();self.switch(None);before=len(self.service.calls)
  self.switch(A,True);self.idle();self.assertTrue(self.manager.states[A]['automatic']);self.assertIn(A,self.web.enabled);self.assertNotIn(B,self.web.enabled)
  self.switch(B,True);self.idle();self.assertIn(B,self.web.enabled);self.assertNotIn(A,self.web.enabled)
  self.assertGreater(len(self.service.calls),before);self.assertEqual(len(self.service.connectors),2);self.assertEqual(self.auth_calls,0)
 def test_new_chats_within_one_project_preserve_the_live_session_and_never_reconnect(self):
  import json,urllib.request
  self.manual(A);project=dict(self.web.active);token=self.web.projects[A]['token'];server=self.web.server;calls=len(self.service.calls)
  sessions=dict(self.web.sessions);self.assertTrue(sessions)
  sid=next(iter(sessions));workspace=sessions[sid]['workspace'];binding=dict(self.manager.connected_bindings)
  for _ in range(5):
   self.web.select(project);self.manager.context(auto_connect=False);self.idle()
   self.assertIs(self.web.server,server);self.assertEqual(self.web.enabled,{A});self.assertEqual(self.web.projects[A]['token'],token)
   self.assertEqual(self.manager.states[A]['status'],'connected');self.assertEqual(self.manager.connected_bindings,binding)
   self.assertIs(self.web.sessions[sid]['workspace'],workspace);self.assertEqual(len(self.service.calls),calls)
   req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mcp/'+A,
    data=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'workspace_overview','arguments':{}}}).encode(),
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json, text/event-stream','Mcp-Session-Id':sid})
   with urllib.request.urlopen(req,timeout=4) as response:
    result=json.load(response);self.assertEqual(response.status,200);self.assertFalse(result['result'].get('isError',False))
  self.assertEqual(len(self.service.connectors),1);self.assertEqual(self.auth_calls,0)
 def test_new_chat_updates_never_resume_an_intentionally_paused_project(self):
  self.manual(A);self.manager.cancel(A);self.web.pause(A);self.manager.context();calls=len(self.service.calls)
  for _ in range(5):self.web.select({'id':A,'name':'Project A'});self.manager.context(auto_connect=False)
  self.idle();self.assertEqual(self.manager.states[A]['pause_reason'],'manual');self.assertNotIn(A,self.web.enabled);self.assertEqual(len(self.service.calls),calls)
 def test_name_updates_and_status_refreshes_never_start_automatic_requests(self):
  self.manual(A);self.switch(None);self.switch(A);before=len(self.service.calls)
  for _ in range(4):
   self.web.select({'id':A,'name':'Renamed project A'});self.manager.context();self.manager.state();self.web.state()
  self.idle();self.assertEqual(len(self.service.calls),before);self.assertNotIn(A,self.web.enabled)
 def test_automatic_resume_without_key_is_paused_without_authorization_popup(self):
  self.manual(A);self.switch(None);self.engine.key='';before=len(self.service.calls)
  self.switch(A,True);self.idle();self.assertEqual(self.manager.states[A]['status'],'paused');self.assertEqual(self.manager.states[A]['pause_reason'],'sign_in')
  self.assertEqual(self.auth_calls,0);self.assertEqual(len(self.service.calls),before);self.assertNotIn(A,self.web.enabled)
  self.manager.context();self.manager.state();self.assertFalse(any(e.get('type')=='auth' and e.get('status')=='waiting' for e in self.events))
  self.manual(A);self.assertEqual(self.auth_calls,1)
 def test_explicit_pause_survives_project_switch_and_only_successful_manual_connect_clears_it(self):
  self.approved_pair();self.switch(A);self.manager.cancel(A);self.web.pause(A);self.manager.context();before=len(self.service.calls)
  self.switch(B);self.switch(A,True);self.idle();self.assertEqual(len(self.service.calls),before)
  self.assertTrue(self.web.projects[A]['manually_paused']);self.assertFalse(self.web.can_auto_connect(A));self.assertEqual(self.manager.states[A]['pause_reason'],'manual')
  self.manual(A);self.assertFalse(self.web.projects[A]['manually_paused']);self.assertTrue(self.web.can_auto_connect(A))
 def test_failed_manual_resume_does_not_remove_explicit_pause_or_grant_new_approval(self):
  self.manual(A);self.web.pause(A);self.manager.context()
  def fail(method,path,data):
   if path.endswith('/workspace_overview/call'):raise auto.SetupError('mistral_error','Fixture failure',502)
  self.service.hook=fail;self.manager.connect(A);self.idle()
  self.assertTrue(self.web.projects[A]['manually_paused']);self.assertFalse(self.web.can_auto_connect(A));self.assertNotIn(A,self.web.enabled)
  self.service.hook=None;self.switch(B);self.assertFalse(self.web.auto_approved(B));self.service.hook=fail;self.manager.connect(B);self.idle();self.assertFalse(self.web.auto_approved(B))
 def test_explicit_pause_after_error_replaces_the_old_failure_status(self):
  self.manual(A)
  def fail(method,path,data):
   if path.endswith('/workspace_overview/call'):raise auto.SetupError('mistral_error','Fixture failure',502)
  self.service.hook=fail;self.manager.connect(A);self.idle();self.assertEqual(self.manager.states[A]['status'],'error')
  self.manager.cancel(A);self.web.pause(A);self.manager.context()
  self.assertEqual(self.manager.states[A]['status'],'paused');self.assertEqual(self.manager.states[A]['pause_reason'],'manual')
 def test_name_update_during_explicit_resume_keeps_busy_state_and_manual_hold_until_success(self):
  self.manual(A);self.web.pause(A);self.manager.context();entered,release=self.blocking_probe();self.manager.connect(A);self.assertTrue(entered.wait(2))
  self.web.select({'id':A,'name':'Renamed while resuming'});self.manager.context()
  self.assertEqual(self.manager.states[A]['status'],'connecting');self.assertTrue(self.web.projects[A]['manually_paused'])
  release.set();self.idle();self.assertEqual(self.manager.states[A]['status'],'connected');self.assertFalse(self.web.projects[A]['manually_paused'])
 def test_pausing_inflight_automatic_setup_remains_manual_paused_after_old_job_finishes(self):
  self.manual(A);self.switch(None);entered,release=self.blocking_probe();self.switch(A,True);self.assertTrue(entered.wait(2))
  self.manager.cancel(A);self.web.pause(A);self.manager.context();release.set();self.idle()
  self.assertEqual(self.manager.states[A]['status'],'paused');self.assertEqual(self.manager.states[A]['pause_reason'],'manual');self.assertNotIn(A,self.web.enabled)
 def test_rapid_a_b_a_keeps_latest_request_waits_for_old_cleanup_and_never_overlaps(self):
  self.approved_pair();entered,release=self.blocking_probe();starts=[];running=0;maximum=0;lock=threading.Lock();original=self.manager.run
  def run(job):
   nonlocal running,maximum
   with lock:starts.append(job['key']);running+=1;maximum=max(maximum,running)
   try:original(job)
   finally:
    with lock:running-=1
  self.manager.run=run;self.switch(A,True);self.assertTrue(entered.wait(2));old=self.manager.job
  self.switch(B,True);self.switch(A,True);self.assertTrue(old['cancel'].is_set());release.set();self.idle()
  self.assertEqual(starts,[A,A]);self.assertEqual(maximum,1);self.assertEqual(self.manager.states[A]['status'],'connected');self.assertIn(A,self.web.enabled);self.assertNotIn(B,self.web.enabled);self.assertEqual(len(self.service.connectors),2)
 def test_queued_automatic_project_is_immediately_cancellable_and_cancel_keeps_manual_hold(self):
  self.approved_pair();entered,release=self.blocking_probe();self.switch(A,True);self.assertTrue(entered.wait(2));self.switch(B,True)
  with self.manager.lock:
   self.assertEqual(self.manager.pending['key'],B);self.assertTrue(self.manager.pending['automatic'])
  self.assertEqual(self.manager.states[B]['status'],'starting');self.assertTrue(self.manager.states[B]['automatic'])
  before=len(self.service.calls);self.manager.cancel(B);self.assertEqual(self.manager.states[B]['status'],'cancelled');self.web.pause(B);self.manager.context()
  with self.manager.lock:self.assertIsNone(self.manager.pending)
  self.assertEqual(self.manager.states[B]['status'],'paused');self.assertEqual(self.manager.states[B]['pause_reason'],'manual')
  release.set();self.idle();self.manager.context(auto_connect=True);self.idle()
  self.assertNotIn(B,self.web.enabled);self.assertFalse(self.web.can_auto_connect(B));self.assertEqual(len(self.service.calls),before)
 def test_manual_request_takes_priority_over_queued_automatic_resume(self):
  self.approved_pair();entered,release=self.blocking_probe();self.switch(A,True);self.assertTrue(entered.wait(2))
  self.switch(B,True);self.manager.connect(B);self.manager.context(auto_connect=True)
  with self.manager.lock:self.assertFalse(self.manager.pending['automatic'])
  release.set();self.idle();self.assertEqual(self.manager.states[B]['status'],'connected');self.assertFalse(self.manager.states[B]['automatic']);self.assertIn(B,self.web.enabled)
 def test_queued_manual_resume_keeps_busy_state_while_its_persisted_hold_is_still_set(self):
  self.approved_pair();self.web.pause(B);self.manager.context();entered,release=self.blocking_probe();self.switch(A,True);self.assertTrue(entered.wait(2))
  self.switch(B,True);self.manager.connect(B);self.manager.context()
  self.assertEqual(self.manager.states[B]['status'],'starting');self.assertTrue(self.web.projects[B]['manually_paused'])
  release.set();self.idle();self.assertEqual(self.manager.states[B]['status'],'connected');self.assertFalse(self.web.projects[B]['manually_paused'])
 def test_rotation_during_automatic_request_invalidates_approval_and_old_cleanup_cannot_revoke_new_binding(self):
  self.manual(A);self.switch(None);entered,release=self.blocking_probe();self.switch(A,True);self.assertTrue(entered.wait(2));old=self.manager.job
  self.manager.cancel(A);self.web.rotate(A);self.manager.context();self.web.enable(A,True)
  release.set();self.idle();self.assertTrue(old['cancel'].is_set());self.assertFalse(self.web.auto_approved(A));self.assertIn(A,self.web.enabled)
  self.web.enable(A,False);before=len(self.service.calls);self.manager.context(auto_connect=True);self.idle();self.assertEqual(len(self.service.calls),before)
 def test_relink_competing_with_transport_enable_cannot_enable_the_replacement_binding(self):
  self.manual(A);self.switch(None)
  entered=threading.Event();release=threading.Event();mutating=threading.Event();mutated=threading.Event();errors=[];self.releases.append(release)
  original=self.web.enable;first=True
  def enable(key,allow,**kwargs):
   nonlocal first
   if first and allow:first=False;entered.set();release.wait(3)
   return original(key,allow,**kwargs)
  self.web.enable=enable;replacement=self.root/'concurrent-replacement';replacement.mkdir()
  def relink():
   try:
    entered.wait(3);mutating.set();self.manager.cancel(A);self.web.link(A,replacement);self.manager.context();mutated.set()
   except BaseException as error:errors.append(error)
  competitor=threading.Thread(target=relink);competitor.start();self.switch(A,True)
  self.assertTrue(entered.wait(2));self.assertTrue(mutating.wait(2));mutated.wait(.15);release.set();competitor.join(4);self.idle()
  self.assertFalse(competitor.is_alive());self.assertEqual(errors,[]);self.assertFalse(self.web.auto_approved(A));self.assertNotIn(A,self.web.enabled)
 def test_relink_during_manual_setup_never_approves_or_enables_the_replacement_root(self):
  entered,release=self.blocking_probe();self.manager.connect(A);self.assertTrue(entered.wait(2));self.manager.cancel(A)
  new=self.root/'replacement';new.mkdir();self.web.link(A,new);self.manager.context();release.set();self.idle()
  self.assertFalse(self.web.auto_approved(A));self.assertNotIn(A,self.web.enabled);self.assertEqual(self.service.connectors,{})
 def test_cancellation_clears_pending_resume_and_repeated_context_does_not_retry(self):
  self.approved_pair();entered,release=self.blocking_probe();self.switch(A,True);self.assertTrue(entered.wait(2));self.switch(B,True)
  self.manager.cancel();self.manager.context();release.set();self.idle()
  with self.manager.lock:self.assertIsNone(self.manager.pending)
  before=len(self.service.calls);self.manager.context(auto_connect=True);self.idle();self.assertEqual(len(self.service.calls),before);self.assertNotIn(B,self.web.enabled)
 def test_automatic_error_is_not_retried_by_name_or_repeated_context_updates(self):
  self.manual(A);self.switch(None)
  def fail(method,path,data):
   if path.endswith('/workspace_overview/call'):raise auto.SetupError('mistral_error','Fixture failure',502)
  self.service.hook=fail;self.switch(A,True);self.idle();self.assertEqual(self.manager.states[A]['status'],'error');before=len(self.service.calls)
  for _ in range(4):self.manager.context();self.manager.context(auto_connect=True)
  self.idle();self.assertEqual(len(self.service.calls),before);self.assertNotIn(A,self.web.enabled)
  self.service.hook=None;self.switch(None);self.switch(A,True);self.idle();self.assertIn(A,self.web.enabled)
 def test_close_stops_coordinator_and_drops_queued_project(self):
  self.approved_pair();entered,release=self.blocking_probe();self.switch(A,True);self.assertTrue(entered.wait(2));self.switch(B,True);self.manager.close()
  self.assertFalse(self.manager.coordinator.is_alive());self.assertIsNone(self.manager.pending);release.set();self.idle();self.assertNotIn(B,self.web.enabled)

if __name__=='__main__':unittest.main()
