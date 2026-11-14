import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('web',Path(__file__).parents[2]/'backend/web_connector.py')
web=importlib.util.module_from_spec(spec);spec.loader.exec_module(web)
A='cace260d-d95d-4859-b45b-f56f185f15da';B='229ee257-1234-4567-890a-123456789abc'

class ProjectIdentityTests(unittest.TestCase):
 def test_work_uuid_and_canonical_url_are_unchanged(self):
  self.assertEqual(web.project_info({'id':A,'name':'Work fixture'}),{'id':A,'name':'Work fixture','url':'https://chat.mistral.ai/work/projects/'+A})
 def test_code_namespace_has_separate_canonical_url_for_same_raw_uuid(self):
  code=web.project_info({'id':'code-'+A,'name':'Code fixture'})
  self.assertEqual(code,{'id':'code-'+A,'name':'Code fixture','url':'https://chat.mistral.ai/code/'+A})
  self.assertEqual(web.project_info({'id':'code-'+A})['name'],'Project '+A[:8])
 def test_project_namespaces_and_uuid_shape_are_strict(self):
  for key in ['work-'+A,'code-code-'+A,'code-'+A.upper(),'code-'+A+'/chat','code-'+A+'?x=1','code-'+A[:-1],'a'*36]:
   with self.assertRaises(ValueError):web.project_info({'id':key})

class ConnectorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.events=[]
  self.a=self.root/'Alpha';self.a.mkdir();(self.a/'tekst.txt').write_text('Alleen A')
  self.b=self.root/'Beta';self.b.mkdir();(self.b/'tekst.txt').write_text('Alleen B')
  self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
  self.c.select({'id':A,'name':'CityTripXL'});self.c.link(A,self.a);self.c.enable(A,True)
  self.token=self.c.projects[A]['token'];self.url='http://127.0.0.1:'+str(self.c.server.server_port)+'/mcp/'+A
  self.sid=None
 def tearDown(self):self.c.close();self.tmp.cleanup()
 def test_public_cached_connector_id_does_not_enable_access_or_expose_registry_credentials(self):
  self.c.enable(A,False);cached='aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'
  self.c.local_connector_records[A]={'id':cached,'credentials':'never-forward-this-fixture-secret'}
  snapshot=self.c.snapshot();self.assertEqual(snapshot['local_connector_id'],cached);self.assertFalse(snapshot['enabled']);self.assertIsInstance(snapshot['local_connector_id'],str);self.assertNotIn('never-forward-this-fixture-secret',json.dumps(snapshot))
  self.c.local_connector_records[A]={'id':B};self.assertEqual(self.c.snapshot()['local_connector_id'],B)
  self.c.local_connector_records.pop(A);self.assertIsNone(self.c.snapshot()['local_connector_id'])
 def request(self,msg=None,method='POST',token=None,path=None,headers=None,sid=True):
  h={'Authorization':'Bearer '+(self.token if token is None else token),'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-06-18'}
  if sid and self.sid:h['Mcp-Session-Id']=self.sid
  h.update(headers or {})
  req=urllib.request.Request(path or self.url,data=json.dumps(msg).encode() if msg else None,headers=h,method=method)
  try:r=urllib.request.urlopen(req,timeout=3)
  except urllib.error.HTTPError as e:r=e
  with r:
   raw=r.read()
   if r.headers.get('Content-Type')=='text/event-stream':return r.code,r.headers,raw.decode()
   return r.code,r.headers,json.loads(raw) if raw else None
 def init(self):
  code,h,d=self.request({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'Test','version':'1'}}})
  self.assertEqual(code,200);self.sid=h['Mcp-Session-Id'];return d
 def test_restart_listens_at_once_for_a_tunnel_helper_that_is_still_up(self):
  # Measured live: Mistral checks the connectors as soon as its page loads.
  # VibeZ listened only after Connect, the tunnel answered 502 and Mistral
  # refused the connector for about a minute. Projects stay paused.
  import os,socket,urllib.request,urllib.error
  self.c.close()
  with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
  (self.root/'private'/'tunnel.json').write_text(json.dumps({'pid':os.getpid(),'port':port,'url':'https://fixture-words.trycloudflare.com'}))
  self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
  self.assertEqual(self.c.server.server_port,port);self.assertEqual(self.c.enabled,set())
  def post(host,method,params=None):
   request=urllib.request.Request('http://127.0.0.1:%d/mcp/%s'%(port,A),data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params or {}}).encode(),
    headers={'Host':host,'Authorization':'Bearer '+self.token,'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
   try:
    with urllib.request.urlopen(request,timeout=5) as response:return response.status,json.loads(response.read())
   except urllib.error.HTTPError as error:return error.code,None
  status,body=post('fixture-words.trycloudflare.com','initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'t','version':'1'}})
  self.assertEqual(status,200);self.assertIn('paused',body['result']['instructions'])
  status,body=post('fixture-words.trycloudflare.com','tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}})
  self.assertNotIn('Alleen A',json.dumps(body))
  self.assertTrue(status!=200 or body['result'].get('isError'))
  self.assertEqual(post('other-words.trycloudflare.com','initialize')[0],403)

 def test_paused_http_response_has_english_message_and_stable_code(self):
  self.init();self.c.pause(A)
  code,_,response=self.request({'jsonrpc':'2.0','id':2,'method':'ping'})
  self.assertEqual(code,403)
  self.assertEqual(response,{'error':'The project connection is paused.','error_code':'project_paused'})
 def rpc(self,method,params=None,**kwargs):return self.request({'jsonrpc':'2.0','id':2,'method':method,'params':params or {}},**kwargs)
 def modern(self,method,params=None,headers=None,rid=2,name=None):
  params=dict(params or {});params['_meta']={'io.modelcontextprotocol/protocolVersion':'2026-07-28','io.modelcontextprotocol/clientInfo':{'name':'Test','version':'1'},'io.modelcontextprotocol/clientCapabilities':{}}
  h={'MCP-Protocol-Version':'2026-07-28','Mcp-Method':method}
  if name is not None:h['Mcp-Name']=name
  h.update(headers or {})
  msg={'jsonrpc':'2.0','method':method,'params':params}
  if rid is not None:msg['id']=rid
  return self.request(msg,headers=h,sid=False)
 def test_modern_stateless_requests_need_no_session_and_carry_result_type(self):
  code,h,d=self.modern('server/discover');self.assertEqual(code,200)
  self.assertEqual(d['result']['supportedVersions'],['2026-07-28']);self.assertEqual(d['result']['resultType'],'complete');self.assertNotIn('Mcp-Session-Id',h)
  self.assertEqual(d['result']['_meta']['io.modelcontextprotocol/serverInfo']['name'],'VibeZ-local-files');self.assertIn('linked folders',d['result']['instructions'])
  code,_,d=self.modern('tools/list');self.assertEqual(code,200);self.assertEqual(d['result']['cacheScope'],'private');self.assertGreater(d['result']['ttlMs'],0)
  self.assertTrue(any(t['name']=='read_file' for t in d['result']['tools']))
  code,_,d=self.modern('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}},name='read_file');self.assertEqual(code,200)
  self.assertEqual(json.loads(d['result']['content'][0]['text'])['content'],'Alleen A');self.assertEqual(d['result']['resultType'],'complete');self.assertFalse(d['result']['isError'])
  encoded='=?base64?'+base64.b64encode(b'read_file').decode()+'?='
  self.assertEqual(self.modern('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}},name=encoded)[0],200)
  self.assertEqual(self.modern('notifications/initialized',rid=None)[0],202)
  code,_,d=self.modern('ping');self.assertEqual((code,d['error']['code']),(404,-32601))
  # A stale session header from an older client is ignored in this era.
  self.assertEqual(self.modern('tools/list',headers={'Mcp-Session-Id':'left-over'})[0],200)
  # Legacy clients still get the handshake on the same endpoint.
  self.init();self.assertEqual(self.rpc('ping')[0],200)
  diagnostic=json.loads((self.root/'private/transport-status.json').read_text())
  rows=diagnostic['recent_requests']
  self.assertTrue(any(r.get('session')=='stateless' and r.get('era')=='modern' and r['method']=='server/discover' and r['protocol_header']=='2026-07-28' for r in rows))
  self.assertTrue(any(r.get('era')=='legacy' and r['method']=='initialize' for r in rows))
  self.assertNotIn('left-over',json.dumps(diagnostic))
 def test_handshake_only_mode_answers_the_new_era_like_an_older_server(self):
  self.c.modern=False
  code,_,d=self.modern('server/discover');self.assertEqual(code,400);self.assertNotIn('result',d or {})
  # The client then falls back to the handshake, which works as before.
  self.init();code,_,d=self.rpc('tools/list');self.assertEqual(code,200);self.assertTrue(any(t['name']=='read_file' for t in d['result']['tools']))
  (self.root/'private/legacy-era').write_text('');self.c.close()
  self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0);self.assertFalse(self.c.modern)
 def test_discovery_carries_the_full_instructions_and_the_trace_shows_the_kind_of_client(self):
  code,_,d=self.modern('server/discover');text=d['result']['instructions']
  self.assertIn('CityTripXL',text);self.assertIn('list_directory',text);self.assertGreater(len(text),200)
  self.sid=None;self.init()
  rows=json.loads((self.root/'private/transport-status.json').read_text())['recent_requests']
  row=next(r for r in rows if r['method']=='server/discover')
  self.assertEqual(row['client']['name'],'Test');self.assertIn('protocolVersion',row['client']['meta']);self.assertIn('Mcp-Method',row['client']['headers'])
  self.assertNotIn(self.token,json.dumps(rows))
 def test_modern_header_validation_follows_the_specification(self):
  code,_,d=self.modern('tools/list',headers={'Mcp-Method':'tools/call'});self.assertEqual((code,d['error']['code']),(400,-32020))
  code,_,d=self.modern('tools/list',headers={'MCP-Protocol-Version':'2025-06-18'});self.assertEqual((code,d['error']['code']),(400,-32020))
  code,_,d=self.modern('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}});self.assertEqual((code,d['error']['code']),(400,-32020),'Mcp-Name is required for tools/call')
  code,_,d=self.modern('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}},name='list_directory');self.assertEqual((code,d['error']['code']),(400,-32020))
  code,_,d=self.modern('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}},name='=?base64?not*base64?=');self.assertEqual((code,d['error']['code']),(400,-32020))
  # A newer modern version is named but not supported: the error lists what is, so the client can retry.
  params={'_meta':{'io.modelcontextprotocol/protocolVersion':'2099-01-01','io.modelcontextprotocol/clientCapabilities':{}}}
  code,_,d=self.request({'jsonrpc':'2.0','id':9,'method':'tools/list','params':params},headers={'MCP-Protocol-Version':'2099-01-01','Mcp-Method':'tools/list'},sid=False)
  self.assertEqual((code,d['error']['code'],d['error']['data']['supported'],d['error']['data']['requested']),(400,-32022,['2026-07-28'],'2099-01-01'))
  self.assertEqual((self.a/'tekst.txt').read_text(),'Alleen A')
 def tool(self,name,args={}):
  code,_,d=self.rpc('tools/call',{'name':name,'arguments':args});self.assertEqual(code,200)
  return d['result'],json.loads(d['result']['content'][0]['text']) if not d['result'].get('isError') else None
 def test_code_and_work_with_the_same_uuid_keep_separate_roots_tokens_and_sessions(self):
  self.init();work_sid=self.sid;work_url=self.url;work_token=self.token;code='code-'+A
  self.c.select({'id':code,'name':'Code fixture'});self.c.link(code,self.b);self.c.enable(code,True)
  self.assertEqual(self.rpc('ping')[0],403)
  code_url=work_url.rsplit('/',1)[0]+'/'+code
  self.assertEqual(self.rpc('initialize',path=code_url,sid=False)[0],401)
  self.token=self.c.projects[code]['token'];self.url=code_url
  self.assertNotEqual(self.token,work_token);self.assertEqual(self.rpc('ping')[0],404)
  self.init();self.assertEqual(self.tool('read_file',{'path':'tekst.txt'})[1]['content'],'Alleen B')
  proposal=self.tool('write_file',{'path':'tekst.txt','content':'Alleen Code aangepast'})[1]
  self.assertEqual((self.b/'tekst.txt').read_text(),'Alleen B');self.c.resolve(proposal['proposal_id'],True)
  self.assertTrue(self.tool('change_status',{'proposal_id':proposal['proposal_id']})[1]['written'])
  self.assertEqual((self.b/'tekst.txt').read_text(),'Alleen Code aangepast');self.assertEqual((self.a/'tekst.txt').read_text(),'Alleen A')
  self.assertEqual(self.c.projects[A]['token'],work_token);self.assertEqual(self.c.projects[A]['folder'],str(self.a))
  self.assertEqual(self.c.projects[A]['url'],'https://chat.mistral.ai/work/projects/'+A)
  self.assertEqual(self.c.projects[code]['url'],'https://chat.mistral.ai/code/'+A)
  code_token=self.token;self.c.select({'id':A,'name':'Work fixture'});self.c.enable(A,True)
  self.token=work_token;self.url=work_url;self.sid=work_sid
  self.assertEqual(self.rpc('ping')[0],404);self.init()
  self.assertEqual(self.tool('read_file',{'path':'tekst.txt'})[1]['content'],'Alleen A')
  self.assertEqual(self.rpc('initialize',token=code_token,sid=False)[0],401)
  self.assertEqual(self.rpc('ping',token=code_token,path=code_url,sid=False)[0],403)
 def test_code_binding_survives_restart_without_migrating_existing_work_binding(self):
  original=dict(self.c.projects[A]);code='code-'+A
  self.c.select({'id':code,'name':'Code fixture'});self.c.link(code,self.b)
  saved=dict(self.c.projects[code]);self.c.close()
  self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
  self.assertEqual(self.c.projects[A],original);self.assertEqual(self.c.projects[code],saved)
  self.assertEqual(self.c.enabled,set());self.assertIsNone(self.c.server);self.assertIsNone(self.c.active)

 def test_legacy_binding_needs_one_explicit_verified_approval_before_automatic_resume(self):
  original={k:v for k,v in self.c.projects[A].items() if k not in ('auto_approved','manually_paused')};self.c.close()
  self.c.file.write_text(json.dumps({'projects':{A:original}}))
  self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
  self.assertFalse(self.c.auto_approved(A));self.assertFalse(self.c.can_auto_connect(A));self.assertEqual(self.c.projects[A]['token'],original['token'])
  self.assertEqual(self.c.enabled,set());self.assertIsNone(self.c.server)
  self.c.select({'id':A,'name':'Fixture'});self.c.enable(A,True)
  self.assertTrue(self.c.approve_auto(A,(original['folder'],original['token'])));self.assertTrue(self.c.can_auto_connect(A))
  self.c.close();self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
  self.assertTrue(self.c.auto_approved(A));self.assertTrue(self.c.can_auto_connect(A));self.assertEqual(self.c.enabled,set());self.assertIsNone(self.c.server)
 def test_new_folder_never_receives_auto_approval_from_runtime_enable(self):
  self.assertFalse(self.c.auto_approved(A));self.assertFalse(self.c.can_auto_connect(A))
  self.c.enable(A,True,manual=True);self.assertFalse(self.c.auto_approved(A));self.assertFalse(self.c.can_auto_connect(A))
  self.assertFalse(self.c.approve_auto(A,(str(self.b),self.token)));self.assertFalse(self.c.auto_approved(A))
 def test_runtime_revoke_keeps_auto_approval_but_manual_pause_survives_restart(self):
  binding=(self.c.projects[A]['folder'],self.token);self.assertTrue(self.c.approve_auto(A,binding))
  with self.c.lock:self.c.revoke(A)
  self.assertTrue(self.c.can_auto_connect(A));self.c.enable(A,True);self.c.pause(A)
  self.assertTrue(self.c.auto_approved(A));self.assertFalse(self.c.can_auto_connect(A));self.assertNotIn(A,self.c.enabled)
  self.c.close();self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
  self.assertTrue(self.c.projects[A]['manually_paused']);self.assertTrue(self.c.auto_approved(A));self.assertFalse(self.c.can_auto_connect(A))
  self.c.select({'id':A,'name':'Fixture'});self.c.enable(A,True)
  self.assertTrue(self.c.projects[A]['manually_paused']);self.assertFalse(self.c.can_auto_connect(A))
  self.assertTrue(self.c.approve_auto(A,binding));self.assertFalse(self.c.projects[A]['manually_paused']);self.assertTrue(self.c.can_auto_connect(A))
 def test_advanced_manual_enable_clears_pause_without_granting_missing_approval(self):
  self.c.pause(A);self.assertFalse(self.c.can_auto_connect(A));self.c.enable(A,True,manual=True)
  self.assertFalse(self.c.projects[A]['manually_paused']);self.assertFalse(self.c.auto_approved(A));self.assertFalse(self.c.can_auto_connect(A))
  self.c.close();self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
  self.assertFalse(self.c.projects[A]['manually_paused']);self.assertFalse(self.c.auto_approved(A))
 def test_relink_and_rotation_invalidate_approval_for_the_old_binding(self):
  old=(self.c.projects[A]['folder'],self.token);self.c.approve_auto(A,old)
  self.c.link(A,self.b);self.assertFalse(self.c.auto_approved(A));self.assertFalse(self.c.can_auto_connect(A));self.assertFalse(self.c.projects[A]['manually_paused'])
  self.assertFalse(self.c.approve_auto(A,old));self.c.enable(A,True)
  current=(self.c.projects[A]['folder'],self.c.projects[A]['token']);self.assertTrue(self.c.approve_auto(A,current))
  self.c.rotate(A);self.assertTrue(self.c.projects[A]['manually_paused']);self.assertFalse(self.c.auto_approved(A));self.assertFalse(self.c.can_auto_connect(A))
  self.assertFalse(self.c.approve_auto(A,current));self.assertNotIn(A,self.c.enabled)
 def test_auto_approval_is_namespaced_and_snapshot_contains_only_boolean_policy(self):
  self.c.approve_auto(A,(self.c.projects[A]['folder'],self.token));proof=self.c.projects[A]['auto_approved'];code='code-'+A
  self.c.select({'id':code,'name':'Code fixture'});self.c.link(code,self.a)
  self.c.projects[code]['token']=self.token;self.c.projects[code]['auto_approved']=proof
  self.assertFalse(self.c.auto_approved(code));self.assertFalse(self.c.can_auto_connect(code));self.assertTrue(self.c.auto_approved(A))
  snapshot=self.c.snapshot();self.assertIs(snapshot['auto_approved'],False);self.assertIs(snapshot['manually_paused'],False)
  self.assertTrue(all(type(p['auto_approved']) is bool and type(p['manually_paused']) is bool for p in snapshot['projects']))
  self.assertNotIn(proof,json.dumps(snapshot))
 def test_manual_pause_all_marks_inactive_approved_projects_and_keeps_bindings(self):
  self.c.approve_auto(A,(self.c.projects[A]['folder'],self.token));self.c.select({'id':B,'name':'Other fixture'});self.c.link(B,self.b);self.c.enable(B,True)
  self.c.approve_auto(B,(self.c.projects[B]['folder'],self.c.projects[B]['token']));before={k:(v['folder'],v['token']) for k,v in self.c.projects.items()}
  self.c.pause_all();self.assertEqual(self.c.enabled,set());self.assertTrue(all(p['manually_paused'] for p in self.c.projects.values()))
  self.assertTrue(self.c.auto_approved(A));self.assertTrue(self.c.auto_approved(B));self.assertFalse(self.c.can_auto_connect(A));self.assertFalse(self.c.can_auto_connect(B))
  self.assertEqual(before,{k:(v['folder'],v['token']) for k,v in self.c.projects.items()})
 def test_malformed_policy_fields_fail_closed_and_do_not_change_bindings(self):
  original=dict(self.c.projects[A]);self.c.close()
  for proof,paused in [(True,False),('x'*64,False),('0'*64,'false'),('0'*64,0)]:
   record={**original,'auto_approved':proof,'manually_paused':paused};self.c.file.write_text(json.dumps({'projects':{A:record}}))
   self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
   self.assertFalse(self.c.auto_approved(A));self.assertFalse(self.c.can_auto_connect(A));self.assertEqual(self.c.projects[A]['token'],original['token'])
   if type(paused) is not bool:self.assertTrue(self.c.projects[A]['manually_paused'])
   self.c.close()
 def test_remote_mcp_cannot_change_auto_approval_or_pause_policy(self):
  self.init();self.assertFalse(self.c.auto_approved(A))
  for method in ['vibez/approve_auto','vibez/pause','vibez/pause_all']:
   self.assertEqual(self.rpc(method,{'allow':True})[2]['error']['code'],-32601)
  self.assertTrue(self.tool('approve_auto',{'binding':'invented'})[0]['isError']);self.assertFalse(self.c.auto_approved(A))
  self.assertFalse(self.c.projects[A]['manually_paused']);self.assertIn(A,self.c.enabled)
 def test_approval_save_failure_does_not_grant_auto_resume_in_memory(self):
  from unittest.mock import patch
  binding=(self.c.projects[A]['folder'],self.token)
  with patch.object(self.c,'save',side_effect=OSError('invented disk failure')):
   with self.assertRaises(OSError):self.c.approve_auto(A,binding)
  self.assertFalse(self.c.auto_approved(A));self.assertFalse(self.c.can_auto_connect(A))

 def test_manual_pause_still_revokes_runtime_access_when_policy_save_fails(self):
  from unittest.mock import patch
  self.init();workspace=self.c.sessions[self.sid]['workspace']
  with patch.object(self.c,'save',side_effect=OSError('invented disk failure')):
   with self.assertRaises(OSError):self.c.pause(A)
  self.assertNotIn(A,self.c.enabled);self.assertEqual(workspace.fd,-1);self.assertTrue(self.c.projects[A]['manually_paused'])

 def test_official_http_handshake_notifications_listing_delete(self):
  d=self.init();self.assertEqual(d['result']['protocolVersion'],'2025-06-18')
  code,_,_=self.request({'jsonrpc':'2.0','method':'notifications/initialized'});self.assertEqual(code,202)
  self.assertEqual({t['name'] for t in self.rpc('tools/list')[2]['result']['tools']},{'read_file','read_image','write_file','create_document','list_directory','workspace_overview','change_status'})
  with patch.object(web,'SSE_SECONDS',.3):code,h,body=self.request(method='GET')
  self.assertEqual((code,h['Content-Type'],body),(200,'text/event-stream',': vibez\n\n'))
  self.assertEqual(self.request(method='DELETE')[0],204)
  self.assertEqual(self.rpc('ping')[0],404)
 def test_event_stream_head_options_and_bearer_scheme(self):
  # Streamable HTTP GET: comments only, closes on its own, and frees its slot.
  with patch.object(web,'SSE_SECONDS',.2):
   code,h,body=self.open_request(None,self.url+'/'+self.token,method='GET')
  self.assertEqual((code,h['Content-Type'],body),(200,'text/event-stream',': vibez\n\n'))
  self.assertEqual(self.c.sse_streams,0)
  # A stream for a session closes as soon as that session is deleted.
  self.init();done=[]
  with patch.object(web,'SSE_SECONDS',5):
   t=threading.Thread(target=lambda:done.append(self.request(method='GET')));t.start()
   for _ in range(40):
    if self.c.sse_streams:break
    threading.Event().wait(.05)
   self.assertEqual(self.c.sse_streams,1)
   self.assertEqual(self.request(method='DELETE')[0],204);t.join(3)
  self.assertFalse(t.is_alive());self.assertEqual(done[0][0],200);self.assertEqual(self.c.sse_streams,0)
  # Full slots fall back to the specification's 405.
  self.c.sse_streams=web.SSE_LIMIT
  self.assertEqual(self.request(method='GET')[0],405)
  self.c.sse_streams=0
  code,h,body=self.request(method='HEAD');self.assertEqual((code,h['Content-Type'],body),(200,'text/event-stream',''))
  # OPTIONS names the methods only and needs no key, but keeps the host/origin rules.
  code,h,_=self.open_request(None,self.url,method='OPTIONS')
  self.assertEqual(code,204);self.assertEqual(h['Allow'],'GET, HEAD, POST, DELETE, OPTIONS')
  self.assertEqual(self.open_request(None,self.url,method='OPTIONS',headers={'Origin':'https://evil.test'})[0],403)
  # The Bearer scheme is case-insensitive (RFC 7235); the token itself is not.
  for scheme in ['bearer','BEARER','Bearer ']:
   self.assertEqual(self.rpc('initialize',headers={'Authorization':scheme+' '+self.token},sid=False)[0],200)
  self.assertEqual(self.rpc('initialize',headers={'Authorization':'Bearer '+self.token.swapcase()},sid=False)[0],401)
  self.assertEqual(self.rpc('initialize',headers={'Authorization':'Basic '+self.token},sid=False)[0],401)
 def test_stale_or_paused_plain_address_gets_no_bearer_challenge(self):
  # A probe without key for another, paused or unknown project is "not found",
  # so Mistral never classifies that older sibling connector as token-required.
  self.c.select({'id':B,'name':'Ander project'});self.c.link(B,self.b);self.c.enable(B,True)
  stale=self.url[:-36]+A
  for path in [stale,self.url[:-36]+'00000000-0000-4000-8000-000000000000']:
   code,h,_=self.open_request(None,path,method='GET');self.assertEqual(code,404);self.assertNotIn('WWW-Authenticate',h)
  # The active project still asks for its key, and a wrong key stays 401.
  code,h,_=self.open_request(None,self.url[:-36]+B,method='GET')
  self.assertEqual(code,401);self.assertEqual(h['WWW-Authenticate'],'Bearer realm="VibeZ-project"')
  self.assertEqual(self.rpc('initialize',path=stale,token='wrong')[0],401)
 def test_no_access_without_project_bearer_even_at_initialize(self):
  for token in ['', 'wrong', self.token[:-1]]:self.assertEqual(self.rpc('initialize',token=token)[0],401)
  self.assertEqual(self.c.sessions,{})
 def test_origin_host_protocol_and_content_negotiation(self):
  for headers,expected in [({'Origin':'https://evil.test'},403),({'Host':'evil.test'},403),({'Accept':'text/html'},406),({'Content-Type':'text/plain'},415),({'MCP-Protocol-Version':'nonsense'},400)]:
   self.assertEqual(self.rpc('initialize',headers=headers)[0],expected)
 def test_rejection_diagnostics_distinguish_pause_host_origin_without_secrets(self):
  self.rpc('initialize',headers={'Origin':'https://private-invalid.example/secret'})
  self.rpc('initialize',headers={'Host':'private-invalid.example'})
  self.rpc('initialize',token='private-fake-token')
  self.c.select(None);self.rpc('ping')
  diagnostic=json.loads((self.root/'private/transport-status.json').read_text())
  self.assertEqual(diagnostic['counts'],{'origin':1,'host':1,'token':1,'paused':1})
  self.assertFalse(diagnostic['recent_rejections'][-1]['active_project_known']);self.assertFalse(diagnostic['recent_rejections'][-1]['requested_enabled'])
  for secret in [self.token,'private-invalid','private-fake-token',A,str(self.a)]:self.assertNotIn(secret,json.dumps(diagnostic))
  self.assertEqual((self.root/'private/transport-status.json').stat().st_mode&0o777,0o600)
 def test_request_trace_shows_every_mcp_outcome_without_secrets(self):
  self.init();self.assertEqual(self.request({'jsonrpc':'2.0','method':'notifications/initialized'})[0],202)
  self.assertEqual(self.rpc('tools/list')[0],200)
  self.assertEqual(self.rpc('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}})[0],200)
  self.assertEqual(self.rpc('tools/call',{'name':'read_file','arguments':{'path':'ontbreekt.txt'}})[0],200)
  real=self.sid;self.sid='unknown-session-fixture-value'
  self.assertEqual(self.rpc('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}})[0],404)
  self.sid=real
  # A newer, well-formed protocol version header is accepted (Mistral sent 2026-07-28 before the negotiated version); an older unknown one is not.
  self.assertEqual(self.rpc('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}},headers={'MCP-Protocol-Version':'2099-01-01'})[0],200)
  self.assertEqual(self.rpc('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}},headers={'MCP-Protocol-Version':'2023-01-01'})[0],400)
  with patch.object(web,'SSE_SECONDS',.1):self.assertEqual(self.request(method='GET')[0],200)
  diagnostic=json.loads((self.root/'private/transport-status.json').read_text())
  rows=[(r['verb'],r['phase'],r['method'],r['http_status'],r.get('session'),r.get('tool'),r.get('tool_error')) for r in diagnostic['recent_requests']]
  self.assertEqual(rows,[('POST','rpc','initialize',200,'new',None,None),('POST','rpc','notifications/initialized',202,'known',None,None),
                         ('POST','rpc','tools/list',200,'known',None,None),('POST','rpc','tools/call',200,'known','read_file',False),
                         ('POST','rpc','tools/call',200,'known','read_file',True),('POST','session','tools/call',404,'unknown','read_file',None),
                         ('POST','rpc','tools/call',200,'known','read_file',False),
                         ('POST','headers','none',400,None,None,None),('GET','stream','none',200,None,None,None)])
  self.assertEqual(diagnostic['recent_requests'][-3]['protocol_header'],'2099-01-01')
  self.assertEqual(diagnostic['recent_requests'][-2]['protocol_header'],'2023-01-01')
  self.assertEqual(diagnostic['request_counts']['tools/call:200'],3)
  for secret in [self.token,real,'unknown-session-fixture-value','tekst.txt','ontbreekt','Alleen A',A,str(self.a)]:self.assertNotIn(secret,json.dumps(diagnostic))
 def test_paused_project_answers_the_handshake_but_never_opens_a_file(self):
  # Mistral checks every connector of the account in the background and shows
  # "Token verification failed" for each 403. A paused project therefore answers
  # the handshake and its fixed tool list, and refuses every tool call in words.
  self.init();self.c.pause(A);sessions=dict(self.c.sessions)
  code,h,d=self.rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'Test','version':'1'}},sid=False)
  self.assertEqual(code,200);self.assertNotIn('Mcp-Session-Id',h);self.assertIn('paused',d['result']['instructions'])
  self.assertNotIn(str(self.a),json.dumps(d));self.assertNotIn('Alleen A',json.dumps(d))
  self.assertEqual(self.request({'jsonrpc':'2.0','method':'notifications/initialized'},sid=False)[0],202)
  code,_,d=self.rpc('tools/list',sid=False);self.assertEqual(code,200);self.assertEqual(d['result']['tools'],web.TOOLS)
  for name,arguments in [('read_file',{'path':'tekst.txt'}),('workspace_overview',{}),('write_file',{'path':'nieuw.txt','content':'x'})]:
   code,_,d=self.rpc('tools/call',{'name':name,'arguments':arguments},sid=False);self.assertEqual(code,200)
   self.assertIs(d['result']['isError'],True);body=json.loads(d['result']['content'][0]['text'])
   self.assertEqual(body['error_code'],'project_paused');self.assertNotIn('Alleen A',json.dumps(d))
  self.assertFalse((self.a/'nieuw.txt').exists());self.assertEqual(self.c.sessions,sessions)
  for method in ['ping','resources/list','prompts/list']:self.assertEqual(self.rpc(method,sid=False)[0],403)
  code,_,d=self.modern('server/discover');self.assertEqual(code,200);self.assertEqual(d['result']['resultType'],'complete');self.assertIn('paused',d['result']['instructions'])
  code,_,d=self.modern('tools/list');self.assertEqual(code,200);self.assertEqual(d['result']['tools'],web.TOOLS)
  code,_,d=self.modern('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}},name='read_file');self.assertEqual(code,200);self.assertIs(d['result']['isError'],True)
  self.assertEqual(self.request(method='GET')[0],405)
  # Without the key nothing changes: unknown stays unknown.
  self.assertEqual(self.rpc('initialize',token='wrong-fixture-key',sid=False)[0],401)
 def test_paused_request_trace_names_the_attempted_method_only_with_a_valid_key(self):
  self.init();self.c.pause(A)
  self.assertEqual(self.rpc('ping')[0],403)
  code,_,reply=self.rpc('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}});self.assertEqual(code,200)
  self.assertEqual(self.rpc('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}},token='wrong-fixture-key')[0],401)
  rows=json.loads((self.root/'private/transport-status.json').read_text())['recent_requests']
  self.assertEqual([(r['phase'],r['http_status'],r['method'],r.get('tool'),r.get('session')) for r in rows[-3:]],
                   [('auth',403,'ping',None,None),('rpc',200,'tools/call','read_file','paused'),('auth',401,'none',None,None)])
  self.assertIs(reply['result']['isError'],True)
  self.assertNotIn('tekst.txt',json.dumps(rows))
 def open_request(self,msg,path,sid=None,method='POST',headers=None):
  h={'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
  if sid:h['Mcp-Session-Id']=sid
  h.update(headers or {})
  req=urllib.request.Request(path,data=json.dumps(msg).encode() if msg else None,headers=h,method=method)
  try:r=urllib.request.urlopen(req,timeout=3)
  except urllib.error.HTTPError as e:r=e
  with r:
   raw=r.read()
   if r.headers.get('Content-Type')=='text/event-stream':return r.code,r.headers,raw.decode() if raw else None
   return r.code,r.headers,json.loads(raw) if raw else None
 def test_secret_address_works_without_authorization_header_and_stays_scoped(self):
  secret=self.url+'/'+self.token
  init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'Work','version':'1'}}}
  code,h,d=self.open_request(init,secret);self.assertEqual(code,200);sid=h['Mcp-Session-Id']
  self.assertNotIn('WWW-Authenticate',h)
  code,_,d=self.open_request({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'read_file','arguments':{'path':'tekst.txt'}}},secret,sid)
  self.assertEqual(code,200);self.assertEqual(json.loads(d['result']['content'][0]['text'])['content'],'Alleen A')
  # Without the secret the plain address still demands the key (Code and older routes).
  self.assertEqual(self.open_request(init,self.url)[0],401)
  # A wrong or shortened secret is "not found", never an authentication challenge.
  for wrong in [self.url+'/'+'x'*len(self.token),self.url+'/'+self.token[:-1]]:
   code,h,_=self.open_request(init,wrong);self.assertEqual(code,404);self.assertNotIn('WWW-Authenticate',h)
  # Another project's secret never opens this project, and B's path never accepts A's secret.
  self.c.select({'id':B,'name':'Ander project'});self.c.link(B,self.b);self.c.enable(B,True)
  self.assertEqual(self.open_request(init,self.url[:-36]+B+'/'+self.token)[0],404)
  self.assertEqual(self.open_request(init,self.url[:-36]+B+'/'+self.c.projects[B]['token'])[0],200)
  # Pausing closes the secret address too.
  self.c.pause(B);code,h,_=self.open_request(init,self.url[:-36]+B+'/'+self.c.projects[B]['token']);self.assertEqual(code,200);self.assertNotIn('Mcp-Session-Id',h)
  diagnostic=(self.root/'private/transport-status.json').read_text()
  for value in [self.token,self.c.projects[B]['token']]:self.assertNotIn(value,diagnostic)
 def test_read_then_propose_then_local_approve_then_remote_status(self):
  self.init();_,r=self.tool('read_file',{'path':'tekst.txt'});self.assertEqual(r['content'],'Alleen A')
  _,p=self.tool('write_file',{'path':'tekst.txt','content':'Verbeterd A'});pid=p['proposal_id']
  self.assertEqual(p['status'],'pending');self.assertEqual((self.a/'tekst.txt').read_text(),'Alleen A')
  self.assertEqual(self.tool('change_status',{'proposal_id':pid})[1]['status'],'pending')
  self.c.resolve(pid,True);self.assertEqual((self.a/'tekst.txt').read_text(),'Verbeterd A')
  self.assertTrue(self.tool('change_status',{'proposal_id':pid})[1]['written'])
  with self.assertRaises(ValueError):self.c.resolve(pid,True)
 def test_remote_cannot_approve_or_choose_root(self):
  self.init()
  self.assertEqual(self.rpc('vibez/resolve',{'allow':True})[2]['error']['code'],-32601)
  self.assertTrue(self.tool('approve',{'allow':'true'})[0]['isError'])
  self.assertTrue(self.tool('read_file',{'path':'tekst.txt','project_id':B})[0]['isError'])
 def test_reject_and_concurrent_file_change(self):
  self.init();self.tool('read_file',{'path':'tekst.txt'})
  pid=self.tool('write_file',{'path':'tekst.txt','content':'Veranderd'})[1]['proposal_id']
  self.c.resolve(pid,False);self.assertEqual(self.tool('change_status',{'proposal_id':pid})[1]['status'],'rejected')
  pid=self.tool('write_file',{'path':'tekst.txt','content':'Nog anders'})[1]['proposal_id']
  (self.a/'tekst.txt').write_text('Handmatig gewijzigd')
  with self.assertRaises(ValueError):self.c.resolve(pid,True)
  self.assertEqual((self.a/'tekst.txt').read_text(),'Handmatig gewijzigd')
 def test_project_switch_revokes_old_sessions_and_pending_writes(self):
  self.init();self.tool('read_file',{'path':'tekst.txt'});pid=self.tool('write_file',{'path':'tekst.txt','content':'Niet opslaan'})[1]['proposal_id']
  self.c.select({'id':B,'name':'Ander project'});self.c.link(B,self.b);self.c.enable(B,True)
  self.assertEqual(self.rpc('ping')[0],403)
  with self.assertRaises(ValueError):self.c.resolve(pid,True)
  url=self.url[:-36]+B
  self.assertEqual(self.rpc('initialize',path=url)[0],401)
  self.token=self.c.projects[B]['token'];self.url=url
  self.assertEqual(self.rpc('ping')[0],404) # A session cannot become a B session.
  self.init();self.assertEqual(self.tool('read_file',{'path':'tekst.txt'})[1]['content'],'Alleen B')
 def test_relink_rotates_key_and_revokes_existing_approvals(self):
  self.init();self.tool('read_file',{'path':'tekst.txt'});pid=self.tool('write_file',{'path':'tekst.txt','content':'No'})[1]['proposal_id']
  self.c.link(A,self.b);self.assertNotEqual(self.token,self.c.projects[A]['token']);self.assertEqual(self.rpc('ping')[0],401)
  with self.assertRaises(ValueError):self.c.resolve(pid,True)
  self.assertEqual((self.b/'tekst.txt').read_text(),'Alleen B')
 def test_restart_preserves_binding_but_never_reopens_network_access(self):
  token=self.token;self.c.close();self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
  self.assertEqual(self.c.projects[A]['token'],token);self.assertEqual(self.c.enabled,set());self.assertIsNone(self.c.server);self.assertIsNone(self.c.active)
  self.assertEqual(self.c.file.stat().st_mode&0o777,0o600)
 def test_missing_session_bad_json_and_unsupported_method(self):
  self.assertEqual(self.rpc('tools/list')[0],400);self.init()
  self.assertEqual(self.rpc('delete_file',{'path':'tekst.txt'})[2]['error']['code'],-32601)
  self.assertEqual(self.request({'jsonrpc':'2.0','id':2,'method':{},'params':{}})[0],400)
 def test_file_boundaries_symlinks_hidden_parent_and_project_read_cache(self):
  (self.a/'link').symlink_to(self.b/'tekst.txt');(self.a/'.secret').write_text('Secret')
  self.init()
  for name in ['../Beta/tekst.txt','/etc/passwd','.secret','link']:
   self.assertTrue(self.tool('read_file',{'path':name})[0]['isError'])
  self.assertTrue(self.tool('write_file',{'path':'tekst.txt','content':'Changed'})[0]['isError'])
  self.tool('read_file',{'path':'tekst.txt'});old=self.sid;self.init()
  self.assertNotEqual(self.sid,old);self.assertFalse(self.tool('write_file',{'path':'tekst.txt','content':'Changed'})[0]['isError'])
 def test_fresh_read_survives_transport_delete_and_pending_approval_survives_write_delete(self):
  self.init();self.assertTrue(self.tool('write_file',{'path':'tekst.txt','content':'Changed'})[0]['isError'])
  self.tool('read_file',{'path':'tekst.txt'});read_sid=self.sid;workspace=self.c.sessions[read_sid]['workspace']
  self.assertEqual(self.request(method='DELETE')[0],204);self.assertGreaterEqual(workspace.fd,0)
  self.init();self.assertNotEqual(self.sid,read_sid);self.assertIs(self.c.sessions[self.sid]['workspace'],workspace)
  result,proposal=self.tool('write_file',{'path':'tekst.txt','content':'Across transport sessions'})
  self.assertFalse(result['isError']);self.assertEqual(proposal['status'],'pending');self.assertEqual((self.a/'tekst.txt').read_text(),'Alleen A')
  self.assertEqual(self.request(method='DELETE')[0],204);self.assertGreaterEqual(workspace.fd,0)
  self.c.resolve(proposal['proposal_id'],True);self.assertEqual((self.a/'tekst.txt').read_text(),'Across transport sessions')
  self.init();self.assertTrue(self.tool('change_status',{'proposal_id':proposal['proposal_id']})[1]['written'])
  self.c.enable(A,False);self.assertEqual(workspace.fd,-1);self.assertNotIn(A,self.c.workspaces)
 def test_external_file_change_invalidates_read_evidence_across_transport_sessions(self):
  self.init();self.tool('read_file',{'path':'tekst.txt'});self.request(method='DELETE')
  (self.a/'tekst.txt').write_text('Fresh external text');self.init()
  self.assertTrue(self.tool('write_file',{'path':'tekst.txt','content':'Stale replacement'})[0]['isError']);self.assertEqual(self.c.proposals,{})
  self.tool('read_file',{'path':'tekst.txt'});self.request(method='DELETE');self.init()
  proposal=self.tool('write_file',{'path':'tekst.txt','content':'Reviewed fresh replacement'})[1]
  self.assertEqual(proposal['status'],'pending');self.assertEqual((self.a/'tekst.txt').read_text(),'Fresh external text')
  (self.a/'tekst.txt').write_text('Changed after proposal')
  with self.assertRaises(ValueError):self.c.resolve(proposal['proposal_id'],True)
  self.assertEqual((self.a/'tekst.txt').read_text(),'Changed after proposal')
 def test_transport_expiry_does_not_close_project_workspace_or_pending_review(self):
  import time
  self.init();self.tool('read_file',{'path':'tekst.txt'});workspace=self.c.sessions[self.sid]['workspace']
  proposal=self.tool('write_file',{'path':'tekst.txt','content':'After transport expiry'})[1]
  self.c.sessions[self.sid]['used']=time.monotonic()-1801;self.init()
  self.assertGreaterEqual(workspace.fd,0);self.c.resolve(proposal['proposal_id'],True)
  self.assertEqual((self.a/'tekst.txt').read_text(),'After transport expiry')
 def test_pause_relink_rotate_and_restart_require_a_new_read(self):
  for transition in ['pause','relink','rotate','restart']:
   with self.subTest(transition=transition):
    self.init();self.tool('read_file',{'path':'tekst.txt'});workspace=self.c.sessions[self.sid]['workspace'];self.request(method='DELETE')
    if transition=='pause':self.c.enable(A,False)
    elif transition=='relink':self.c.link(A,self.b);self.token=self.c.projects[A]['token']
    elif transition=='rotate':self.c.rotate(A);self.token=self.c.projects[A]['token']
    else:
     self.c.close();self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0);self.c.select({'id':A,'name':'Fixture'})
    self.assertEqual(workspace.fd,-1);self.assertNotIn(A,self.c.workspaces)
    self.c.enable(A,True);self.url='http://127.0.0.1:'+str(self.c.server.server_port)+'/mcp/'+A
    self.init();self.assertTrue(self.tool('write_file',{'path':'tekst.txt','content':'Must read again'})[0]['isError'])
 def test_same_content_in_other_project_and_returned_project_cannot_reuse_read_evidence(self):
  (self.b/'tekst.txt').write_text('Alleen A');self.init();self.tool('read_file',{'path':'tekst.txt'});work_url=self.url;work_token=self.token
  code='code-'+A;self.c.select({'id':code,'name':'Code fixture'});self.c.link(code,self.b);self.c.enable(code,True)
  self.token=self.c.projects[code]['token'];self.url=work_url.rsplit('/',1)[0]+'/'+code;self.init()
  self.assertTrue(self.tool('write_file',{'path':'tekst.txt','content':'Other project must read'})[0]['isError'])
  self.tool('read_file',{'path':'tekst.txt'});self.request(method='DELETE');self.init()
  self.assertFalse(self.tool('write_file',{'path':'tekst.txt','content':'Code may propose after its own read'})[0]['isError'])
  self.c.select({'id':A,'name':'Work fixture'});self.c.enable(A,True);self.token=work_token;self.url=work_url;self.init()
  self.assertTrue(self.tool('write_file',{'path':'tekst.txt','content':'Returning Work must read again'})[0]['isError'])
  self.assertEqual((self.a/'tekst.txt').read_text(),'Alleen A');self.assertEqual((self.b/'tekst.txt').read_text(),'Alleen A')

 def test_no_private_paths_or_tokens_in_remote_handshake_or_errors(self):
  d=self.init();self.assertNotIn(str(self.root),json.dumps(d));self.assertNotIn(self.token,json.dumps(d))
  r,_=self.tool('read_file',{'path':'missing.txt'});self.assertNotIn(str(self.root),json.dumps(r))
 def test_approval_returns_actual_result_in_the_same_http_tool_call(self):
  import time
  self.init();self.tool('read_file',{'path':'tekst.txt'});self.c.approval_wait=3
  result=[]
  worker=threading.Thread(target=lambda:result.append(self.tool('write_file',{'path':'tekst.txt','content':'Samen in hetzelfde gesprek'})))
  worker.start();deadline=time.monotonic()+2
  while not self.c.proposals and time.monotonic()<deadline:time.sleep(.01)
  self.assertTrue(self.c.proposals);self.assertEqual((self.a/'tekst.txt').read_text(),'Alleen A')
  self.c.resolve(next(iter(self.c.proposals)),True);worker.join(3)
  self.assertFalse(worker.is_alive());self.assertTrue(result[0][1]['written']);self.assertEqual(result[0][1]['status'],'saved')
 def test_replaced_root_cannot_receive_old_approved_write(self):
  self.init();self.tool('read_file',{'path':'tekst.txt'});pid=self.tool('write_file',{'path':'tekst.txt','content':'No'})[1]['proposal_id']
  self.a.rename(self.root/'old');self.a.symlink_to(self.b,target_is_directory=True)
  with self.assertRaises(ValueError):self.c.resolve(pid,True)
  self.assertEqual((self.b/'tekst.txt').read_text(),'Alleen B')
 def test_tunnel_stop_revokes_all_access_and_pending(self):
  self.init();self.c.stop_tunnel();self.assertEqual(self.rpc('ping')[0],403)
 def test_proposal_expiry_is_enforced_before_approval(self):
  self.init();pid=self.tool('write_file',{'path':'new.txt','content':'No'})[1]['proposal_id'];self.c.proposals[pid]['created']-=601
  with self.assertRaises(ValueError):self.c.resolve(pid,True)
  self.assertFalse((self.a/'new.txt').exists())

 # Robustness found by tools/mcp-stress-test.py: a client always gets an answer.
 def test_modern_request_without_a_method_is_refused_not_dropped(self):
  meta={'io.modelcontextprotocol/protocolVersion':'2026-07-28'}
  for msg in [{'jsonrpc':'2.0','id':1,'params':{'_meta':meta}},{'jsonrpc':'2.0','id':1,'method':5,'params':{'_meta':meta}},{'jsonrpc':'1.0','id':1,'method':'tools/list','params':{'_meta':meta}},{'jsonrpc':'2.0','id':[1],'method':'tools/list','params':{'_meta':meta}}]:
   code,_,d=self.request(msg,headers={'MCP-Protocol-Version':'2026-07-28'},sid=False)
   self.assertEqual((code,d['error']['code']),(400,-32600))
 def test_deeply_nested_body_and_unknown_verbs_get_an_answer(self):
  import http.client
  port=self.c.server.server_port
  def raw(verb,body=None):
   k=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
   k.request(verb,'/mcp/'+A,body,{'Authorization':'Bearer '+self.token,'Content-Type':'application/json','Accept':'application/json'})
   r=k.getresponse();r.read();k.close();return r.status,r.getheader('Allow')
  self.assertEqual(raw('POST',b'{"a":'+b'['*100000+b']'*100000+b'}')[0],400)
  for verb in ('PUT','PATCH'):self.assertEqual(raw(verb,b'{}'),(405,web.ALLOWED_METHODS))
 def test_unexpected_fault_inside_a_tool_is_a_tool_error_in_english(self):
  self.init()
  with patch.object(type(self.c.sessions[self.sid]['workspace']),'read',side_effect=RuntimeError('/secret/path')):
   code,_,d=self.rpc('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}})
   self.assertEqual(code,200);self.assertTrue(d['result']['isError']);self.assertEqual(json.loads(d['result']['content'][0]['text'])['error_code'],'operation_failed');self.assertNotIn('secret',json.dumps(d))
   code,_,d=self.modern('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}},name='read_file')
   self.assertEqual(code,200);self.assertTrue(d['result']['isError'])
  code,_,d=self.rpc('tools/call',{'name':'no_such_tool','arguments':{}})
  self.assertEqual(json.loads(d['result']['content'][0]['text']),{'error_code':'unknown_tool','message':'The requested file tool is not available.'})
 def test_unexpected_fault_outside_a_tool_answers_500_without_detail(self):
  self.init()
  with patch.object(self.c,'rpc',side_effect=RuntimeError('/secret/path')):
   code,_,d=self.rpc('ping')
  self.assertEqual((code,d['error']['code']),(500,-32603));self.assertNotIn('secret',json.dumps(d))
  self.assertEqual(self.rpc('ping')[0],200)
 def test_oversized_body_is_answered_with_413(self):
  self.init();code,_,_=self.rpc('tools/call',{'name':'write_file','arguments':{'path':'big.txt','content':'x'*3_000_000}})
  self.assertEqual(code,413);self.assertEqual(self.rpc('ping')[0],200)
 def test_many_unclosed_sessions_drop_the_oldest_instead_of_locking_out(self):
  self.init();first=self.sid
  for _ in range(70):self.sid=None;self.init()
  self.assertLessEqual(len(self.c.sessions),64);self.assertNotIn(first,self.c.sessions);self.assertEqual(self.rpc('ping')[0],200)
 def test_too_many_requests_at_once_are_told_to_retry(self):
  import http.client
  self.init();taken=[self.c.server.slots.acquire(timeout=5) for _ in range(16)];self.assertTrue(all(taken))  # the thread of init may still hold one for a moment
  try:
   k=http.client.HTTPConnection('127.0.0.1',self.c.server.server_port,timeout=3);k.request('POST','/mcp/'+A,b'{}',{'Content-Type':'application/json'})
   r=k.getresponse();body=json.loads(r.read());k.close()
   self.assertEqual((r.status,r.getheader('Retry-After'),body['error_code']),(503,'1','busy'))
  finally:
   for ok in taken:
    if ok:self.c.server.slots.release()
  self.assertEqual(self.rpc('ping')[0],200)
 def test_new_file_in_folders_that_do_not_exist_yet(self):
  self.init();result,value=self.tool('write_file',{'path':'src/app/main.py','content':'print(1)\n'})
  self.assertFalse((self.a/'src').exists());self.c.resolve(value['proposal_id'],True)
  self.assertEqual((self.a/'src/app/main.py').read_text(),'print(1)\n')
  result,value=self.tool('create_document',{'path':'docs/new/report.odt','content':'Report'});self.c.resolve(value['proposal_id'],True)
  self.assertTrue((self.a/'docs/new/report.odt').is_file())
  result,value=self.tool('write_file',{'path':'never/made.txt','content':'x'});self.c.resolve(value['proposal_id'],False);self.assertFalse((self.a/'never').exists())
  (self.root/'elsewhere').mkdir();(self.a/'link').symlink_to(self.root/'elsewhere')
  self.assertTrue(self.tool('write_file',{'path':'link/sub/x.txt','content':'x'})[0]['isError']);self.assertEqual(list((self.root/'elsewhere').iterdir()),[])
  self.assertTrue(self.tool('write_file',{'path':'tekst.txt/sub/x.txt','content':'x'})[0]['isError'])
 def test_overview_and_listing_survive_an_unreadable_subfolder(self):
  import os
  locked=self.a/'locked';locked.mkdir();(locked/'x.txt').write_text('x');(self.a/'ok').mkdir();(self.a/'ok/y.txt').write_text('y');os.chmod(locked,0)
  try:
   self.init();result,value=self.tool('workspace_overview')
   if os.geteuid()!=0:self.assertFalse(result['isError']);self.assertEqual(value['files'],2);self.assertTrue(value['truncated'])
   self.assertIn('locked',[e['name'] for e in self.tool('list_directory',{'path':'.'})[1]['entries']])
  finally:os.chmod(locked,0o700)
 def test_saving_works_on_file_systems_without_noreplace_rename_or_sync(self):
  import errno,os,sys
  capfs=sys.modules['_vibez_capfs'];self.init()
  def nosync(fd):raise OSError(errno.EINVAL,'no sync')
  with patch.object(capfs,'_native_rename_noreplace',return_value=errno.EINVAL),patch.object(os,'fsync',nosync):
   _,value=self.tool('write_file',{'path':'nfs.txt','content':'one'});self.c.resolve(value['proposal_id'],True)
   self.assertEqual((self.a/'nfs.txt').read_text(),'one')
   self.tool('read_file',{'path':'nfs.txt'});_,value=self.tool('write_file',{'path':'nfs.txt','content':'two'});self.c.resolve(value['proposal_id'],True)
   self.assertEqual((self.a/'nfs.txt').read_text(),'two')
   _,value=self.tool('create_document',{'path':'nfs.odt','content':'doc'});self.c.resolve(value['proposal_id'],True);self.assertTrue((self.a/'nfs.odt').is_file())
   # The fallback still never replaces a file that appeared in the meantime.
   _,value=self.tool('write_file',{'path':'race.txt','content':'assistant'});(self.a/'race.txt').write_text('user')
   with self.assertRaises(ValueError):self.c.resolve(value['proposal_id'],True)
   self.assertEqual((self.a/'race.txt').read_text(),'user')
   fd=os.open(self.a,os.O_RDONLY)
   try:
    (self.a/'staged').write_text('new');(self.a/'taken').write_text('old')
    with self.assertRaises(FileExistsError):capfs.rename_noreplace(fd,'staged','taken')
    self.assertEqual((self.a/'taken').read_text(),'old');capfs.rename_noreplace(fd,'staged','free');self.assertEqual((self.a/'free').read_text(),'new')
    (self.a/'dir-staged').mkdir();(self.a/'dir-staged/in.txt').write_text('in');capfs.rename_noreplace(fd,'dir-staged','dir-free');self.assertEqual((self.a/'dir-free/in.txt').read_text(),'in')
   finally:os.close(fd)
  self.assertEqual([p.name for p in self.a.iterdir() if p.name.startswith('.')],[])
 def test_real_disk_error_while_writing_is_not_reported_as_saved(self):
  import errno,os
  self.init();_,value=self.tool('write_file',{'path':'io.txt','content':'x'})
  def broken(fd):raise OSError(errno.EIO,'io')
  with patch.object(os,'fsync',broken):
   with self.assertRaises(OSError):self.c.resolve(value['proposal_id'],True)
  self.assertFalse((self.a/'io.txt').exists());self.assertFalse(self.tool('change_status',{'proposal_id':value['proposal_id']})[1]['written'])
 def test_damaged_link_store_does_not_stop_the_start(self):
  self.c.close();store=self.root/'private'/'web-projects.json'
  for damage in (b'',b'{',b'null',b'[]',b'{"projects": 5}',b'{"projects": {"x": 1}}',b'\xff\xfe'):
   store.write_bytes(damage);c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
   try:self.assertTrue(c.store_damaged);self.assertEqual(c.projects,{});self.assertFalse(store.exists());self.assertEqual((self.root/'private'/'web-projects.damaged.json').read_bytes(),damage)
   finally:c.close()
  self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0);self.assertFalse(self.c.store_damaged)
  self.c.select({'id':A,'name':'Again'});self.c.link(A,self.a);self.c.enable(A,True);self.token=self.c.projects[A]['token'];self.url='http://127.0.0.1:'+str(self.c.server.server_port)+'/mcp/'+A;self.sid=None
  self.init();self.assertEqual(self.tool('read_file',{'path':'tekst.txt'})[1]['content'],'Alleen A')

 def test_one_name_the_system_refuses_never_hides_the_rest_of_the_folder(self):
  # Windows refuses names such as nul.txt; such a file must not break the listing or the overview.
  (self.a/'nul.txt').write_text('x');(self.a/'sub').mkdir();(self.a/'sub/aux.txt').write_text('y');(self.a/'sub/fine.txt').write_text('z')
  real=web.base.os.stat
  def picky(name,*args,**kwargs):
   if isinstance(name,str) and name.split('.')[0] in ('nul','aux'):raise ValueError('Device names are not allowed')
   return real(name,*args,**kwargs)
  self.init()
  with patch.object(web.base.os,'stat',picky):
   _,value=self.tool('list_directory',{'path':'.'});self.assertEqual([e['name'] for e in value['entries']],['sub','tekst.txt'])
   _,value=self.tool('list_directory',{'path':'sub'});self.assertEqual([e['name'] for e in value['entries']],['fine.txt'])
   result,value=self.tool('workspace_overview',{});self.assertFalse(result['isError']);self.assertEqual(value['files'],2)
 def test_reading_a_folder_as_a_file_leaves_nothing_open(self):
  import os
  (self.a/'sub').mkdir();os.mkfifo(self.a/'pipe');self.init();self.tool('read_file',{'path':'sub'})
  before=len(os.listdir('/proc/self/fd')) if os.path.isdir('/proc/self/fd') else None
  for _ in range(30):
   for name in ('read_file','read_image'):
    for path in ('sub','pipe','sub.odt'):
     result,_=self.tool(name,{'path':path});self.assertTrue(result['isError'])
  self.assertEqual(json.loads(self.tool('read_file',{'path':'sub'})[0]['content'][0]['text'])['error_code'],'unsupported_file')
  if before is not None:self.assertLessEqual(len(os.listdir('/proc/self/fd')),before+2)

 def test_handled_proposals_do_not_pile_up(self):
  self.init()
  with patch.object(web,'MAX_DONE_PROPOSALS',5):
   pids=[]
   for n in range(12):
    _,value=self.tool('write_file',{'path':'n%d.txt'%n,'content':'x'});pids.append(value['proposal_id']);self.c.resolve(value['proposal_id'],n%2==0)
   _,pending=self.tool('write_file',{'path':'last.txt','content':'x'})
   self.assertLessEqual(len(self.c.proposals),6);self.assertIn(pending['proposal_id'],self.c.proposals);self.assertIn(pids[-1],self.c.proposals)
  self.assertEqual((self.a/'n10.txt').read_text(),'x');self.assertFalse((self.a/'n11.txt').exists())

if __name__=='__main__':unittest.main()
