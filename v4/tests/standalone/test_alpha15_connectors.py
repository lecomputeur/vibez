"""Alpha15 connector lifecycle: isolated API, real local HTTP MCP where useful.

Never reads a personal profile, connects to Mistral, or removes a remote object.
"""
import copy,json,tempfile,threading,time,unittest,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from test_automatic_connector import auto,web,A,B,Service

class RegistryLifecycleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='vibez-alpha15-registry-');self.r=auto.Registry(self.tmp.name);self.api=Service(auto.SetupError)
  self.p={'id':A,'name':'Fixture project'};self.url='https://fixture.trycloudflare.com/mcp/'+A;self.token='fixture-mcp-secret'
  self.delays=patch.object(auto,'READINESS_DELAYS',(0,0,0));self.delays.start()
 def tearDown(self):self.delays.stop();self.tmp.cleanup()
 def configure(self,guard=lambda:None):return self.r.configure(self.p,self.url,self.token,self.api,guard)
 def add_clone(self,source,**changes):
  v=copy.deepcopy(self.api.connectors[source['id']]);v.update({'id':str(uuid.uuid4()),'name':'renamed_'+uuid.uuid4().hex,**changes});self.api.connectors[v['id']]=v;self.api.active.add(v['id']);return v
 def test_none_auth_metadata_false_does_not_block_a_verified_workspace_action(self):
  original=self.api.call
  def call(method,path,data=None):
   result=original(method,path,data)
   if method=='GET' and path.count('/')==2:result['is_authenticated']=False
   return result
  self.api.call=call;self.configure()
  self.assertEqual(sum(m=='POST' and p=='/connectors' for m,p,_ in self.api.calls),1)
  self.assertEqual(sum(p.endswith('/workspace_overview/call') for _,p,_ in self.api.calls),1)
  self.assertEqual(sum(p.endswith('/user/activate') for _,p,_ in self.api.calls),1)
 def test_explicit_inactive_provider_is_not_reported_connected(self):
  original=self.api.call
  def call(method,path,data=None):
   result=original(method,path,data)
   if method=='GET' and path.count('/')==2:result['active']=False
   return result
  self.api.call=call
  with self.assertRaises(auto.SetupError) as error:self.configure()
  self.assertEqual(error.exception.code,'connector_sync');self.assertFalse(any(p.endswith('/workspace_overview/call') for _,p,_ in self.api.calls))
 def test_real_api_shape_without_active_and_false_auth_still_executes(self):
  original=self.api.call
  def call(method,path,data=None):
   result=original(method,path,data)
   if method=='GET' and path.count('/')==2:result.pop('active',None);result['is_authenticated']=False
   return result
  self.api.call=call;self.configure()
  self.assertTrue(any(p.endswith('/workspace_overview/call') for _,p,_ in self.api.calls))
 def test_false_auth_metadata_cannot_hide_a_rejected_workspace_key(self):
  original=self.api.call
  def call(method,path,data=None):
   if path.endswith('/workspace_overview/call'):raise auto.SetupError('sign_in','Fixture connector rejected',401,stage='execute')
   result=original(method,path,data)
   if method=='GET' and path.count('/')==2:result['is_authenticated']=False
   return result
  self.api.call=call
  with self.assertRaises(auto.SetupError) as error:self.configure()
  self.assertEqual(error.exception.code,'connector_auth');self.assertEqual(error.exception.status,401)
 def test_false_auth_metadata_cannot_replace_actual_workspace_result(self):
  original=self.api.call
  def call(method,path,data=None):
   result=original(method,path,data)
   if method=='GET' and path.count('/')==2:result['is_authenticated']=False
   if path.endswith('/workspace_overview/call'):return {'content':[{'type':'text','text':'not a verified workspace'}]}
   return result
  self.api.call=call
  with self.assertRaises(auto.SetupError) as error:self.configure()
  self.assertEqual(error.exception.code,'execution')
 def test_missing_optional_consumer_fields_still_requires_actual_workspace_execution(self):
  original=self.api.call
  def call(method,path,data=None):
   result=original(method,path,data)
   if isinstance(result,dict):result.pop('active',None);result.pop('is_authenticated',None)
   return result
  self.api.call=call;self.configure();self.assertTrue(self.api.calls[-1][1].endswith('/workspace_overview/call'))
 def test_stale_tool_catalogue_and_transient_execution_retry_same_connector(self):
  original=self.api.call;stale=[True];failure=[True]
  def call(method,path,data=None):
   if '/tools?' in path and stale[0]:stale[0]=False;return []
   if path.endswith('/workspace_overview/call') and failure[0]:failure[0]=False;raise auto.SetupError('execution','Temporary gateway',502,stage='execute')
   return original(method,path,data)
  self.api.call=call;v=self.configure();self.assertEqual(len(self.api.connectors),1);self.assertIn(v['id'],self.api.active);self.assertFalse(stale[0] or failure[0])
 def test_confirmation_wait_is_cancelled_before_another_request(self):
  original=self.api.call
  def call(method,path,data=None):return [] if '/tools?' in path else original(method,path,data)
  self.api.call=call
  def cancel(_):raise auto.Cancelled()
  with self.assertRaises(auto.Cancelled):self.r.configure(self.p,self.url,self.token,self.api,lambda:None,wait=cancel)
  self.assertFalse(any(p.endswith('/workspace_overview/call') for _,p,_ in self.api.calls))
 def test_uncertain_create_response_recovers_remote_object_in_the_same_click(self):
  original=self.api.call;lost=[True]
  def call(method,path,data=None):
   result=original(method,path,data)
   if method=='POST' and path=='/connectors' and lost[0]:lost[0]=False;raise auto.SetupError('network','Response lost')
   return result
  self.api.call=call;v=self.configure();self.assertEqual(len(self.api.connectors),1);self.assertEqual(self.r.records[A]['id'],v['id'])
  self.assertEqual(sum(m=='POST' and p=='/connectors' for m,p,_ in self.api.calls),1)
 def test_renamed_legacy_connector_is_recovered_by_exact_marker_when_registry_record_is_lost(self):
  v=self.configure();self.api.connectors[v['id']]['name']='vibez_fixture_legacy';self.r.records.clear();self.r.save()
  recovered=self.configure();self.assertEqual(recovered['id'],v['id']);self.assertEqual(len(self.api.connectors),1)
 def test_other_scopes_and_same_scope_duplicates_are_paused_without_deleting_anything(self):
  a=self.configure();duplicate=self.add_clone(a);self.p={'id':B,'name':'Other fixture'};self.url='https://fixture.trycloudflare.com/mcp/'+B;b=self.configure();before=copy.deepcopy(self.r.records)
  result=self.r.deactivate_others(B,b['id'],self.api,lambda:None)
  self.assertEqual(result,{'inactive_owned_connectors':2,'connector_cleanup_pending':0});self.assertEqual(self.api.active,{b['id']});self.assertEqual(len(self.api.connectors),3);self.assertEqual(self.r.records,before)
  self.p={'id':A,'name':'Fixture project'};self.url='https://fixture.trycloudflare.com/mcp/'+A;again=self.configure()
  self.assertEqual(again['id'],a['id']);self.r.deactivate_others(A,a['id'],self.api,lambda:None);self.assertEqual(self.api.active,{a['id']});self.assertEqual(len(self.api.connectors),3)
 def test_unknown_other_installation_shared_or_wrong_owner_connectors_are_never_modified(self):
  a=self.configure();other_install=self.add_clone(a,description='[VibeZ:'+uuid.uuid4().hex+':'+B+']');shared=self.add_clone(a,visibility='shared_workspace');unknown=self.add_clone(a,description='Unrelated connector');wrong=self.add_clone(a,owner_id='other-owner')
  before=copy.deepcopy(self.api.connectors);start=len(self.api.calls);self.r.deactivate_others(A,a['id'],self.api,lambda:None)
  self.assertEqual(self.api.connectors,before)
  mutations=[p for m,p,_ in self.api.calls[start:] if m!='GET'];self.assertEqual(mutations,[])
  for v in [a,other_install,shared,unknown,wrong]:self.assertIn(v['id'],self.api.active)
 def test_pagination_recovers_owned_renamed_record_without_overwriting_foreign_names(self):
  a=self.configure();self.api.connectors[a['id']]['name']='renamed-owned';self.r.records.clear();self.r.save()
  for i in range(101):
   v=copy.deepcopy(self.api.connectors[a['id']]);v.update(id=f'{i:08x}-1111-4111-8111-aaaaaaaaaaaa',name='unrelated'+str(i),description='Unrelated');self.api.connectors[v['id']]=v
  self.api.calls.clear();self.assertEqual(self.configure()['id'],a['id']);self.assertTrue(any('&cursor=' in p for _,p,_ in self.api.calls));self.assertEqual(len(self.api.connectors),102)
 def test_invalid_pagination_never_falls_back_to_creating_a_duplicate(self):
  original=self.api.call
  def call(method,path,data=None):
   if path.startswith('/connectors?'):return {'items':[],'pagination':{'next_cursor':'same'}}
   return original(method,path,data)
  self.api.call=call
  with self.assertRaises(auto.SetupError) as error:self.configure()
  self.assertEqual(error.exception.code,'invalid_response');self.assertFalse(any(m=='POST' for m,_,_ in self.api.calls))
 def test_cleanup_requires_the_exact_saved_foreground_connector_before_any_network_request(self):
  a=self.configure();self.api.calls.clear()
  with self.assertRaises(auto.SetupError):self.r.deactivate_others(B,a['id'],self.api,lambda:None)
  self.assertEqual(self.api.calls,[])
 def test_foreign_cross_scope_marker_with_no_saved_record_is_not_a_cleanup_permission(self):
  a=self.configure();foreign=self.add_clone(a,description=self.r.marker(B),owner_id='different-owner',creator_id='different-creator');before=copy.deepcopy(self.api.connectors[foreign['id']]);start=len(self.api.calls)
  result=self.r.deactivate_others(A,a['id'],self.api,lambda:None)
  self.assertEqual(self.api.connectors[foreign['id']],before);self.assertIn(foreign['id'],self.api.active)
  self.assertEqual(result,{'inactive_owned_connectors':0,'connector_cleanup_pending':0})
  self.assertFalse(any(method!='GET' for method,_,_ in self.api.calls[start:]))
 def test_cross_scope_owner_and_creator_must_each_match_the_trusted_active_account(self):
  a=self.configure()
  for fields in [{'owner_id':'different-owner'},{'creator_id':'different-creator'},{'owner_id':None},{'creator_id':None}]:
   with self.subTest(fields=fields):
    foreign=self.add_clone(a,description=self.r.marker(B),**fields);start=len(self.api.calls)
    self.r.deactivate_others(A,a['id'],self.api,lambda:None);self.assertIn(foreign['id'],self.api.active)
    self.assertFalse(any(method!='GET' and foreign['id'] in path for method,path,_ in self.api.calls[start:]))
 def test_saved_foreign_scope_record_does_not_override_the_active_account_anchor(self):
  a=self.configure();foreign=self.add_clone(a,description=self.r.marker(B),owner_id='other-owner',creator_id='other-creator')
  self.r.records[B]={field:foreign[field] for field in ('id','name','owner_id','creator_id')};self.r.save();start=len(self.api.calls)
  result=self.r.deactivate_others(A,a['id'],self.api,lambda:None)
  self.assertIn(foreign['id'],self.api.active);self.assertEqual(result['inactive_owned_connectors'],0)
  self.assertFalse(any(method!='GET' for method,_,_ in self.api.calls[start:]))
  self.p={'id':B,'name':'Other'};self.url='https://fixture.trycloudflare.com/mcp/'+B;start=len(self.api.calls)
  with self.assertRaises(auto.SetupError) as error:self.configure()
  self.assertEqual(error.exception.code,'ownership');self.assertFalse(any(method!='GET' for method,_,_ in self.api.calls[start:]))
 def test_saved_stale_scope_identity_and_remote_replacement_are_never_mutated(self):
  a=self.configure();own=self.add_clone(a,description=self.r.marker(B));self.r.records[B]={field:own[field] for field in ('id','name','owner_id','creator_id')};self.r.save()
  self.api.connectors[own['id']]['creator_id']='replacement-creator';start=len(self.api.calls)
  result=self.r.deactivate_others(A,a['id'],self.api,lambda:None);self.assertEqual(result['inactive_owned_connectors'],0);self.assertIn(own['id'],self.api.active)
  self.assertFalse(any(method!='GET' for method,_,_ in self.api.calls[start:]))
 def test_renamed_foreign_list_match_is_not_recovered_into_an_unsaved_scope(self):
  a=self.configure();foreign=self.add_clone(a,description=self.r.marker(B),owner_id='foreign-owner',creator_id='foreign-creator');start=len(self.api.calls)
  self.assertIsNone(self.r.lookup(B,self.api,lambda:None));self.assertNotIn(B,self.r.records);self.assertIn(foreign['id'],self.api.active)
  self.assertTrue(all(method=='GET' for method,_,_ in self.api.calls[start:]))
 def test_direct_canonical_or_selected_foreign_scope_is_rejected_before_mutation(self):
  a=self.configure();foreign=self.add_clone(a,name=self.r.name(B),description=self.r.marker(B),owner_id='other-owner',creator_id='other-creator')
  for preferred in [None,foreign['name']]:
   with self.subTest(preferred=preferred):
    start=len(self.api.calls)
    with self.assertRaises(auto.SetupError) as error:self.r.lookup(B,self.api,lambda:None,preferred_reference=preferred)
    self.assertEqual(error.exception.code,'ownership');self.assertTrue(all(method=='GET' for method,_,_ in self.api.calls[start:]))
 def test_current_trusted_anchor_is_freshly_rechecked_before_any_cleanup(self):
  a=self.configure();duplicate=self.add_clone(a);self.api.connectors[a['id']]['owner_id']='changed-owner';start=len(self.api.calls)
  with self.assertRaises(auto.SetupError) as error:self.r.deactivate_others(A,a['id'],self.api,lambda:None)
  self.assertEqual(error.exception.code,'ownership');self.assertIn(duplicate['id'],self.api.active);self.assertTrue(all(method=='GET' for method,_,_ in self.api.calls[start:]))
 def test_account_anchor_survives_records_loss_and_restart_without_storing_credentials(self):
  a=self.configure();self.api.connectors[a['id']]['name']='provider-renamed';self.r.records.clear();self.r.save()
  restored=auto.Registry(self.tmp.name);self.assertEqual(restored.account_anchor['id'],a['id']);self.assertNotIn(self.token,restored.path.read_text())
  recovered=restored.lookup(A,self.api,lambda:None);self.assertEqual(recovered['id'],a['id'])
 def test_unanchored_list_matches_are_not_adopted_or_replaced_by_duplicates(self):
  a=self.configure();self.api.connectors[a['id']]['name']='renamed';self.r.records.clear();self.r.account_anchor=None;self.r.save();start=len(self.api.calls)
  with self.assertRaises(auto.SetupError) as error:self.r.lookup(A,self.api,lambda:None)
  self.assertEqual(error.exception.code,'ownership');self.assertTrue(all(method=='GET' for method,_,_ in self.api.calls[start:]))
 def test_older_registry_migrates_from_pinned_saved_owner_metadata(self):
  a=self.configure();data=json.loads(self.r.path.read_text());data.pop('account_anchor',None);self.r.path.write_text(json.dumps(data));restored=auto.Registry(self.tmp.name)
  self.assertEqual(restored.trusted_account(self.api,lambda:None),('fixture-user','fixture-user'))
  self.assertEqual(restored.account_anchor['id'],a['id'])
 def test_new_api_routes_preserve_the_fixed_origin_and_reject_query_injection_and_wrong_methods(self):
  import urllib.error
  requests=[]
  class Response:
   def __enter__(self):return self
   def __exit__(self,*_):pass
   def read(self,_):return b'{}'
  class Opener:
   def open(self,request,timeout):requests.append((request.full_url,request.method));return Response()
  with patch.object(auto.urllib.request,'build_opener',return_value=Opener()):
   api=auto.MistralAPI('fixture-secret');api.call('GET','/connectors?page_size=100&cursor=abc%2F123%3D');api.call('POST','/connectors/'+A+'/user/deactivate')
   # DELETE removes one connector by its exact id, nothing else.
   api.call('DELETE','/connectors/'+A)
   for method,path in [('GET','/connectors/'+A+'/user/deactivate'),('GET','/connectors/'+A+'/user/deactivate?refresh=true&pretty=true&page_size=100'),('DELETE','/connectors/vibez_name_ab12'),('DELETE','/connectors/'+A+'/user/credentials'),('DELETE','/connectors'),('DELETE','/connectors/'+A+'?x=1'),('GET','/connectors?page_size=100&cursor=x&server=evil'),('POST','/connectors?page_size=100')]:
    with self.subTest(method=method,path=path),self.assertRaises(auto.SetupError):api.call(method,path)
  self.assertEqual(requests,[('https://api.mistral.ai/v1/connectors?page_size=100&cursor=abc%2F123%3D','GET'),('https://api.mistral.ai/v1/connectors/'+A+'/user/deactivate','POST'),('https://api.mistral.ai/v1/connectors/'+A,'DELETE')])
 def test_cleanup_failure_is_reported_and_retry_can_clear_it(self):
  a=self.configure();duplicate=self.add_clone(a)
  def hook(method,path,data):
   if path.endswith('/user/deactivate'):raise auto.SetupError('network','Temporary outage',503)
  self.api.hook=hook;r=self.r.deactivate_others(A,a['id'],self.api,lambda:None);self.assertEqual(r['connector_cleanup_pending'],1);self.assertIn(a['id'],self.api.active)
  self.api.hook=None;r=self.r.deactivate_others(A,a['id'],self.api,lambda:None);self.assertEqual(r['connector_cleanup_pending'],0);self.assertEqual(self.api.active,{a['id']});self.assertIn(duplicate['id'],self.api.connectors)

class CompleteLifecycleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='vibez-alpha15-lifecycle-');self.root=Path(self.tmp.name);self.events=[]
  self.web=web.Connector(self.events.append,self.root/'private',approval_wait=0)
  for key in [A,B]:
   f=self.root/key;f.mkdir();(f/'marker.txt').write_text(key);self.web.select({'id':key,'name':'Fixture'});self.web.link(key,f)
  self.engine=SimpleNamespace(web=self.web,key='fixture-account-key',lock=threading.RLock(),external_output=self.events.append)
  self.service=Service(auto.SetupError,self.web);self.manager=auto.AutomaticConnector(self.engine,api_factory=self.service.api,probe=lambda url,token,guard,cancel:self.service.discover(url.rsplit('/',1)[1],token))
  self.web.start_tunnel=lambda:(setattr(self.web,'tunnel_url','https://fixture.trycloudflare.com'),setattr(self.web,'tunnel_status','running'))
 def tearDown(self):
  self.manager.close()
  if self.manager.job:self.manager.job['thread'].join(5)
  self.web.close();self.tmp.cleanup()
 def connect(self,key):
  self.web.select({'id':key,'name':'Fixture'});self.manager.context();self.manager.connect(key)
  deadline=time.monotonic()+8
  while time.monotonic()<deadline:
   with self.manager.lock:
    if self.manager.pending is None and self.manager.job and not self.manager.job['thread'].is_alive():break
   time.sleep(.01)
  self.assertEqual(self.manager.states[key]['status'],'connected')
 def test_cleanup_anchor_network_failure_keeps_the_execution_verified_foreground_folder_working(self):
  original=self.service.call;executed=[False]
  def call(method,path,data=None):
   if executed[0] and method=='GET' and path.count('/')==2:raise auto.SetupError('network','Temporary cleanup outage',503)
   result=original(method,path,data)
   if path.endswith('/workspace_overview/call'):executed[0]=True
   return result
  self.service.call=call;self.connect(A)
  self.assertEqual(self.web.enabled,{A});self.assertEqual(self.manager.states[A]['connector_cleanup_pending'],1)
 def test_only_foreground_owned_connector_stays_active_and_saved_projects_keep_their_identity(self):
  self.connect(A);first=self.manager.registry.records[A]['id'];token=self.web.projects[A]['token'];self.connect(B);second=self.manager.registry.records[B]['id']
  self.assertEqual(self.service.active,{second});self.assertEqual(self.web.enabled,{B});self.assertEqual(self.manager.states[B]['inactive_owned_connectors'],1)
  self.connect(A);self.assertEqual(self.service.active,{first});self.assertEqual(self.web.projects[A]['token'],token);self.assertEqual(len(self.service.connectors),2)
  self.assertEqual(self.manager.states[A]['connector_cleanup_pending'],0)
  for path in (self.root/'private').glob('*.json'):self.assertNotIn('fixture-account-key',path.read_text())

if __name__=='__main__':unittest.main()
