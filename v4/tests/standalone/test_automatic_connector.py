import importlib.util,json,threading,time,tempfile,unittest,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from connector_service_fixture import Service
ROOT=Path(__file__).parents[2]
spec=importlib.util.spec_from_file_location('automatic_test',ROOT/'backend/automatic_connector.py');auto=importlib.util.module_from_spec(spec);spec.loader.exec_module(auto)
spec=importlib.util.spec_from_file_location('web_auto_test',ROOT/'backend/web_connector.py');web=importlib.util.module_from_spec(spec);spec.loader.exec_module(web)
A='cace260d-d95d-4859-b45b-f56f185f15da';B='229ee257-1234-4567-890a-123456789abc'
class RegistryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.r=auto.Registry(self.tmp.name);self.api=Service(auto.SetupError);self.project={'id':A,'name':'CityTripXL'};self.uri='https://fixture.trycloudflare.com/mcp/'+A;self.token='fixture-local-access-secret'
 def tearDown(self):self.tmp.cleanup()
 def configure(self,guard=lambda:None):return self.r.configure(self.project,self.uri,self.token,self.api,guard)
 def test_complete_private_registration_authentication_activation_and_tools(self):
  v=self.configure();c=self.api.connectors[v['id']];self.assertEqual(c['visibility'],'private');self.assertEqual(c['owner_type'],'user');self.assertIn(v['id'],self.api.active)
  cred=self.api.credentials[v['id']];self.assertTrue(cred['is_default']);self.assertEqual(cred['credentials'],{'headers':{}});self.assertNotIn(self.token,self.r.path.read_text())
 def test_connector_reference_uses_readable_title_and_distinct_resource_ids(self):
  first=self.configure();again=self.configure()
  self.assertEqual(first['id'],again['id']);self.assertEqual(first['title'],again['title'])
  self.assertEqual(first['title'],self.api.connectors[first['id']]['title'])
  other=self.r.configure({'id':B,'name':self.project['name']},'https://fixture.trycloudflare.com/mcp/'+B,self.token,self.api,lambda:None)
  self.assertEqual(first['title'],other['title']);self.assertNotEqual(first['id'],other['id'])
  self.assertIn(self.project['name'],first['title']);self.assertNotIn(self.token,first['title'])
 def test_cached_older_tools_without_document_creation_cannot_be_reported_ready(self):
  original=self.api.call
  def call(method,path,data=None):
   result=original(method,path,data)
   if method=='GET' and '/tools?' in path:return [tool for tool in result if tool.get('name')!='create_document']
   return result
  self.api.call=call
  with self.assertRaises(auto.SetupError) as rejected:self.configure()
  self.assertEqual(rejected.exception.code,'tools')
  self.assertFalse(any(path.endswith('/workspace_overview/call') for _,path,_ in self.api.calls))
 def test_repeated_setup_updates_address_without_duplicate_connectors(self):
  first=self.configure();self.uri='https://new-address.trycloudflare.com/mcp/'+A;second=self.configure();self.assertEqual(first['id'],second['id']);self.assertEqual(len(self.api.connectors),1);self.assertEqual(self.api.connectors[first['id']]['server'],self.uri)
 def test_creation_supplies_bootstrap_authentication_before_any_credential_upsert(self):
  self.configure();post=next(d for m,p,d in self.api.calls if m=='POST' and p=='/connectors')
  self.assertEqual(post['headers'],{'Authorization':'Bearer '+self.token});self.assertNotIn('auth_methods',post)
  credential=next(d for m,p,d in self.api.calls if p.endswith('/user/credentials'))
  self.assertEqual(credential['name'],'vibez-local')
 def test_migration_clears_old_header_declaration_while_setting_the_fixed_secret(self):
  value=self.configure();method=self.api.connectors[value['id']]['supported_auth_methods'][0]
  self.assertEqual(method['headers'],[]);self.assertEqual(set(method['global_headers']),{'Authorization'})
  update=next(data for verb,path,data in self.api.calls if verb=='PATCH' and path=='/connectors/'+value['id'])
  self.assertEqual(update['auth_methods'][0]['headers'],[])
 def test_live_duplicate_header_failure_is_reproduced_without_mutating_the_connector(self):
  value=self.configure();connector=self.api.connectors[value['id']]
  for header_name in ['Authorization','authorization']:
   connector['supported_auth_methods']=[{'method_type':'none','headers':[{'name':header_name,'is_required':True}]}]
   previous=json.loads(json.dumps(connector))
   with self.assertRaises(auto.SetupError) as rejected:
    self.api.call('PATCH','/connectors/'+value['id'],{'protocol':'mcp','server':self.uri,'auth_methods':[{'method_type':'none','global_headers':{'Authorization':{'value':'Bearer '+self.token,'is_secret':True}}}]})
   self.assertEqual(rejected.exception.status,400);self.assertIn('Duplicate header name',str(rejected.exception));self.assertEqual(connector,previous)
 def test_reported_live_error_rejects_the_old_combined_authentication_request(self):
  body={'protocol':'mcp','name':self.r.name(A),'description':self.r.marker(A),'server':self.uri,'visibility':'private','auth_methods':[{'method_type':'bearer'}],'headers':{'Authorization':'Bearer '+self.token}}
  with self.assertRaises(auto.SetupError) as rejected:self.api.call('POST','/connectors',body)
  self.assertEqual(rejected.exception.status,422);self.assertIn('not both',str(rejected.exception));self.assertEqual(self.api.connectors,{})
 def test_missing_named_credentials_are_created_then_updated_on_next_connection(self):
  value=self.configure();calls=[method for method,path,_ in self.api.calls if path.endswith('/user/credentials')]
  self.assertEqual(calls,['PATCH','POST']);self.api.calls.clear();self.configure()
  self.assertEqual([method for method,path,_ in self.api.calls if path.endswith('/user/credentials')],['PATCH'])
  self.assertEqual(self.api.credentials[value['id']]['name'],'vibez-local')
 def test_old_bearer_payload_is_rejected_by_header_connector(self):
  value=self.configure()
  with self.assertRaises(auto.SetupError) as rejected:self.api.call('PATCH','/connectors/'+value['id']+'/user/credentials',{'name':'vibez-local','credentials':{'bearer_token':self.token}})
  self.assertEqual(rejected.exception.status,401)
 def test_rejected_connector_secret_is_not_reported_as_expired_account(self):
  self.configure()
  def hook(method,path,data):
   if path.endswith('/user/credentials'):raise auto.SetupError('sign_in','Invalid credentials provided',401)
  self.api.hook=hook
  with self.assertRaises(auto.SetupError) as rejected:self.configure()
  self.assertEqual(rejected.exception.code,'connector_auth');self.assertEqual(rejected.exception.stage,'credentials')
  self.assertIn('do not need to sign in again',str(rejected.exception))
 def test_expired_account_during_secret_setup_is_confirmed_by_read_only_lookup(self):
  self.configure();failed=False
  def hook(method,path,data):
   nonlocal failed
   if path.endswith('/user/credentials'):failed=True;raise auto.SetupError('sign_in','Invalid credentials provided',401)
   if failed and method=='GET':raise auto.SetupError('sign_in','Expired account',401)
  self.api.hook=hook
  with self.assertRaises(auto.SetupError) as rejected:self.configure()
  self.assertEqual(rejected.exception.code,'sign_in');self.assertEqual(rejected.exception.stage,'lookup')
 def test_credentials_keep_working_with_api_versions_that_support_patch_upsert(self):
  self.api.patch_upsert=True;self.configure()
  self.assertEqual([method for method,path,_ in self.api.calls if path.endswith('/user/credentials')],['PATCH'])
 def test_credential_creation_race_recovers_with_update_without_duplicate_connector(self):
  original=self.api.call;raced=False
  def call(method,path,data=None):
   nonlocal raced
   if method=='POST' and path.endswith('/user/credentials') and not raced:
    raced=True;original(method,path,data);raise auto.SetupError('conflict','Created concurrently',409)
   return original(method,path,data)
  self.api.call=call;self.configure();self.assertTrue(raced);self.assertEqual(len(self.api.connectors),1);self.assertEqual(len(self.api.credentials),1)
 def test_current_server_and_secret_are_stored_before_credential_validation(self):
  value=self.configure();self.api.calls.clear()
  self.token='rotated-fixture-secret';self.uri='https://new-address.trycloudflare.com/mcp/'+A
  self.api.expected_server=self.uri;self.api.expected_token=self.token
  self.configure();paths=[(m,p) for m,p,_ in self.api.calls]
  self.assertLess(paths.index(('PATCH','/connectors/'+value['id'])),next(i for i,(_,p) in enumerate(paths) if p.endswith('/user/credentials')))
  c=self.api.connectors[value['id']]
  self.assertEqual(c['supported_auth_methods'][0]['global_headers']['Authorization'],{'value':'Bearer '+self.token,'is_secret':True})
 def test_stale_endpoint_and_secret_reproduce_credential_401_before_refresh(self):
  value=self.configure();self.api.expected_server='https://new-address.trycloudflare.com/mcp/'+A
  self.api.expected_token='rotated-fixture-secret'
  with self.assertRaises(auto.SetupError) as rejected:self.api.call('PATCH','/connectors/'+value['id']+'/user/credentials',self.api.credentials[value['id']])
  self.assertEqual(rejected.exception.status,401)
 def test_token_rotation_updates_only_the_verified_private_project_connector(self):
  value=self.configure();self.token='replacement-local-token';self.configure()
  self.assertEqual(self.api.connectors[value['id']]['supported_auth_methods'][0]['global_headers']['Authorization']['value'],'Bearer '+self.token)
  self.assertEqual(self.api.credentials[value['id']]['credentials'],{'headers':{}})
  self.assertFalse(any('/organization/' in p or '/share' in p or '/workspace/' in p for _,p,_ in self.api.calls))
 def test_credentials_are_not_written_unless_remote_authentication_schema_is_confirmed(self):
  original=self.api.call
  def call(method,path,data=None):
   if path.endswith('/authentication_methods'):return [{'method_type':'oauth2'}]
   return original(method,path,data)
  self.api.call=call
  with self.assertRaises(auto.SetupError) as rejected:self.configure()
  self.assertEqual(rejected.exception.code,'connector_auth_schema');self.assertEqual(self.api.credentials,{})
 def test_readback_with_a_remaining_header_declaration_is_not_accepted(self):
  original=self.api.call
  def call(method,path,data=None):
   result=original(method,path,data)
   if path.endswith('/authentication_methods'):result[0]['headers']=[{'name':'Authorization','is_required':True}]
   return result
  self.api.call=call
  with self.assertRaises(auto.SetupError) as rejected:self.configure()
  self.assertEqual(rejected.exception.code,'connector_auth_schema');self.assertEqual(self.api.credentials,{})
 def test_success_requires_executing_workspace_action_through_the_same_connector(self):
  value=self.configure();method,path,body=self.api.calls[-1]
  self.assertEqual((method,path,body),('POST','/connectors/'+value['id']+'/tools/workspace_overview/call',{'arguments':{}}))
 def test_discovery_alone_or_metadata_tool_error_never_counts_as_connected(self):
  original=self.api.call
  for result in [{'content':[]},{'content':[{'type':'text','text':'not a workspace'}]},{'content':[{'type':'text','text':json.dumps({'files':1,'directories':0,'bytes':1,'source':'Local MCP server · VibeZ workspace'})}],'metadata':{'mcp_meta':{'isError':True}}}]:
   def call(method,path,data=None):return result if path.endswith('/workspace_overview/call') else original(method,path,data)
   self.api.call=call
   with self.assertRaises(auto.SetupError) as rejected:self.configure()
   self.assertEqual(rejected.exception.code,'execution');self.assertEqual(rejected.exception.stage,'execute')
 def test_preferred_existing_reference_requires_same_installation_project_and_owner(self):
  first=self.configure();old=dict(self.api.connectors[first['id']]);old.update(id=str(uuid.uuid4()),name='vibez_citytripxl_old');self.api.connectors[old['id']]=old
  chosen=self.r.lookup(A,self.api,lambda:None,preferred_reference=old['name']);self.assertEqual(chosen['id'],old['id'])
  self.r.remember(A,chosen);again=self.configure();self.assertEqual(again['id'],old['id']);self.assertEqual(len(self.api.connectors),2)
  old['description']='An unrelated connector'
  with self.assertRaises(auto.SetupError):self.r.lookup(A,self.api,lambda:None,preferred_reference=old['name'])
 def test_stale_uuid_with_display_label_falls_back_to_owned_canonical_connector(self):
  first=self.configure();owned=dict(self.r.records[A]);stale={**owned,'id':str(uuid.uuid4()),'name':'Provider display label'}
  self.r.records[A]=stale;self.r.save();self.api.calls.clear()
  recovered=self.configure()
  self.assertEqual(recovered['id'],first['id']);self.assertEqual(len(self.api.connectors),1)
  self.assertFalse(any('Provider display label' in path for _,path,_ in self.api.calls))
  self.assertIn(('GET','/connectors/'+self.r.name(A)),[(method,path) for method,path,_ in self.api.calls])
  self.r.records[A]=stale;self.r.save();self.api.connectors[first['id']]['owner_id']='other-fixture-owner';self.api.calls.clear()
  with self.assertRaises(auto.SetupError) as rejected:self.configure()
  self.assertEqual(rejected.exception.code,'ownership');self.assertTrue(all(method=='GET' for method,_,_ in self.api.calls))
 def test_code_and_work_same_uuid_use_distinct_private_connectors_and_preserve_work_record(self):
  work=self.configure();work_record=dict(self.r.records[A]);code='code-'+A
  self.project={'id':code,'name':'Code fixture'};self.uri='https://fixture.trycloudflare.com/mcp/'+code
  coded=self.configure();self.assertNotEqual(work['id'],coded['id']);self.assertEqual(self.r.records[A],work_record)
  self.assertNotEqual(self.r.marker(A),self.r.marker(code));self.assertNotEqual(self.r.name(A),self.r.name(code));self.assertTrue(auto.NAME.fullmatch(self.r.name(code)))
  restored=auto.Registry(self.tmp.name);self.assertEqual(restored.records[A],work_record);self.assertEqual(restored.records[code]['id'],coded['id'])
  before=len(self.api.calls)
  with self.assertRaises(auto.SetupError):self.r.lookup(code,self.api,lambda:None,preferred_reference=work['name'])
  self.assertTrue(all(method=='GET' for method,_,_ in self.api.calls[before:]))
 def test_code_registry_rejects_work_or_other_code_endpoint_before_any_request(self):
  self.project={'id':'code-'+A,'name':'Code fixture'}
  for path in [A,'code-'+B,'code-code-'+A,'code-'+A.upper()]:
   self.uri='https://fixture.trycloudflare.com/mcp/'+path
   with self.assertRaises(auto.SetupError):self.configure()
  self.assertEqual(self.api.calls,[])
 def test_code_project_key_does_not_relax_remote_connector_uuid_validation(self):
  self.project={'id':'code-'+A,'name':'Code fixture'};self.uri='https://fixture.trycloudflare.com/mcp/code-'+A
  remote=self.configure();self.r.records['code-'+A]['id']='code-'+remote['id'];self.r.save()
  with self.assertRaises(ValueError):auto.Registry(self.tmp.name)

 def test_previous_capitalized_connector_names_are_recovered_without_duplicates(self):
  v=self.configure();self.api.connectors[v['id']]['name']=self.r.legacy_name(A);self.r.records.clear();self.r.save()
  again=self.configure();self.assertEqual(again['id'],v['id']);self.assertEqual(len(self.api.connectors),1)
 def test_provider_assigned_name_keeps_the_same_private_connector_identity(self):
  original=self.api.call
  def call(method,path,data=None):
   response=original(method,path,data)
   if isinstance(response,dict) and response.get('protocol')=='mcp':response['name']='Mistral assigned label'
   return response
  self.api.call=call
  first=self.configure();second=self.configure()
  self.assertEqual(first['id'],second['id']);self.assertEqual(first['name'],'Mistral assigned label');self.assertEqual(len(self.api.connectors),1)
  self.r.records.clear();self.r.save();recovered=self.configure();self.assertEqual(first['id'],recovered['id']);self.assertEqual(len(self.api.connectors),1)
 def test_provider_assigned_name_does_not_bypass_the_project_marker(self):
  value=self.configure();self.api.connectors[value['id']]['name']='Different display label';self.api.connectors[value['id']]['description']='Other project'
  with self.assertRaises(auto.SetupError):self.configure()
 def test_ownership_mismatch_is_not_patched(self):
  v=self.configure();self.api.connectors[v['id']]['description']='Something else';before=len(self.api.calls)
  with self.assertRaises(auto.SetupError):self.configure()
  self.assertTrue(all(m=='GET' for m,_,_ in self.api.calls[before:]))
 def test_ownership_diagnostics_include_only_safe_checks_and_scope_types(self):
  v=self.configure();remote=self.api.connectors[v['id']];remote['owner_type']='workspace'
  with self.assertRaises(auto.SetupError) as rejected:self.configure()
  data=rejected.exception.ownership_check;self.assertEqual(data['owner_type'],'workspace');self.assertFalse(data['checks']['user_owner']);self.assertTrue(data['checks']['private'])
  for secret in [self.token,v['id'],self.project['id']]:self.assertNotIn(secret,json.dumps(data))
 def test_other_owner_is_not_modified(self):
  v=self.configure();self.api.connectors[v['id']]['owner_id']='someone-else';before=len(self.api.calls)
  with self.assertRaises(auto.SetupError):self.configure()
  self.assertTrue(all(m=='GET' for m,_,_ in self.api.calls[before:]))
 def test_shared_connector_is_not_modified(self):
  v=self.configure();self.api.connectors[v['id']]['visibility']='shared_workspace'
  with self.assertRaises(auto.SetupError):self.configure()
 def test_uncertain_create_is_recovered_by_deterministic_name(self):
  v=self.configure();self.r.records.clear();self.r.save();second=self.configure();self.assertEqual(v['id'],second['id']);self.assertEqual(len(self.api.connectors),1)
 def test_failure_after_creation_can_resume(self):
  def hook(m,p,d):
   if p.endswith('/user/credentials'):raise auto.SetupError('network','Interrupted')
  self.api.hook=hook
  with self.assertRaises(auto.SetupError):self.configure()
  self.assertIn(A,self.r.records);self.api.hook=None;self.configure();self.assertEqual(len(self.api.connectors),1)
 def test_expired_remote_id_is_recovered_without_modifying_other_entries(self):
  v=self.configure();self.api.connectors.clear();new=self.configure();self.assertNotEqual(v['id'],new['id']);self.assertEqual(len(self.api.connectors),1)
 def test_permission_error_is_not_retried_as_new_creation(self):
  self.api.fail=403
  with self.assertRaises(auto.SetupError):self.configure()
  self.assertFalse(any(m!='GET' for m,_,_ in self.api.calls))
 def test_context_cancellation_stops_before_mutation(self):
  calls=0
  def guard():
   nonlocal calls
   calls+=1
   if calls>=2:raise auto.Cancelled()
  with self.assertRaises(auto.Cancelled):self.configure(guard)
  self.assertFalse(any(m!='GET' for m,_,_ in self.api.calls))
 def test_no_success_without_the_actual_file_tool_set(self):
  original=self.api.call
  def call(m,p,d=None):return [{'name':'read_file'}] if '/tools?' in p else original(m,p,d)
  self.api.call=call
  with self.assertRaises(auto.SetupError):self.configure()
 def test_project_endpoints_and_registrations_are_separate(self):
  a=self.configure();self.project={'id':B,'name':'Ander project'};self.uri='https://fixture.trycloudflare.com/mcp/'+B;b=self.configure();self.assertNotEqual(a['id'],b['id']);self.assertEqual(len(self.r.records),2)
 def test_invalid_or_other_project_addresses_are_rejected(self):
  for uri in ['http://fixture.trycloudflare.com/mcp/'+A,'https://evil.test/mcp/'+A,'https://fixture.trycloudflare.com/mcp/'+B,'https://key:secret@fixture.trycloudflare.com/mcp/'+A]:
   self.uri=uri
   with self.assertRaises(auto.SetupError):self.configure()
  self.assertEqual(self.api.calls,[])
 def test_private_registry_survives_restart_without_tokens(self):
  v=self.configure();r=auto.Registry(self.tmp.name);self.assertEqual(r.records[A]['id'],v['id']);self.assertEqual(r.installation,self.r.installation);self.assertEqual(r.path.stat().st_mode&0o777,0o600);self.assertNotIn(self.token,r.path.read_text())

 def work_record(self, slug, description, server):
  cid=str(uuid.uuid4())
  self.api.connectors[cid]={'id':cid,'name':slug+'_a1b2','title':slug,'description':description,'protocol':'mcp',
                            'server':server,'visibility':'private','owner_type':'user',
                            'owner_id':'fixture-user','creator_id':'fixture-user'}
  self.api.credentials[cid]={'credentials':{'headers':{'Authorization':'Bearer '+self.token}}}
  self.api.active.add(cid)
  return cid

 def test_work_enrollment_replaces_local_identity_only_after_proof_and_resumes_without_touching_credentials(self):
  predecessor=self.configure()['id'];revision='0'*64
  def enroll(slug,description,server,token):
   self.assertEqual(token,self.token)
   self.assertIn(self.r.work_marker(A,revision),description)
   self.assertEqual(self.r.records[A]['id'],predecessor)
   cid=self.work_record(slug,description,server)
   return self.api.connectors[cid]['name']
  self.api.calls.clear()
  result=self.r.configure_work(self.project,revision,self.uri,self.token,self.api,lambda:None,enroll)
  self.assertTrue(all(method=='GET' and '/tools' not in path for method,path,_ in self.api.calls))
  self.assertEqual(self.r.records[A]['id'],predecessor)
  self.r.remember(A,result,work_binding=revision)
  self.assertEqual(self.r.records[A]['id'],result['id'])
  self.assertIn(predecessor,self.api.connectors)
  self.assertNotEqual(predecessor,result['id'])
  self.assertNotIn(self.token,self.r.path.read_text())
  self.assertFalse(any(path.endswith(('/credentials','/activate','/deactivate')) for _,path,_ in self.api.calls))
  r=auto.Registry(self.tmp.name)
  self.assertEqual(r.records[A]['work_binding'],revision)
  self.api.calls.clear()
  new_url='https://another-fixture.trycloudflare.com/mcp/'+A
  remote=r.find_work(A,revision,self.api,lambda:None)
  resumed=r.configure_work(self.project,revision,new_url,self.token,self.api,lambda:None,
                           lambda *args:self.fail('Existing Work connector must be reused'),remote=remote)
  self.assertEqual(resumed['id'],result['id'])
  self.assertEqual([c for c in self.api.calls if c[0]=='PATCH'],
                   [('PATCH','/connectors/'+result['id'],{'protocol':'mcp','server':new_url})])
  self.assertFalse(any(path.endswith(('/credentials','/activate','/deactivate')) for _,path,_ in self.api.calls))

 def test_older_key_based_work_connector_is_never_reused_for_the_secret_address(self):
  rev='5'*64
  old_slug='vibezwork'+auto.hashlib.sha256(f'{self.r.installation}:{A}:{rev}'.encode()).hexdigest()[:16]
  old_marker=f'[VibeZ-work:{self.r.installation}:{A}:{old_slug}]'
  old=self.work_record(old_slug,self.r.marker(A)+' '+old_marker,self.uri)
  self.r.records[A]={'id':old,'work_binding':rev}
  self.assertNotEqual(self.r.work_slug(A,rev),old_slug)
  self.assertIsNone(self.r.find_work(A,rev,self.api,lambda:None))
  secret=self.uri+'/'+'S'*54
  self.assertTrue(self.r.work_endpoint(A,secret));self.assertTrue(self.r.work_endpoint(A,self.uri))
  for bad in [self.uri+'/short',secret+'/x',secret+'?a=1','https://fixture.trycloudflare.com/mcp/'+B+'/'+'S'*54]:
   self.assertFalse(self.r.work_endpoint(A,bad))
 def test_work_setup_removes_only_older_vibez_connectors_of_the_same_project(self):
  legacy_a=self.configure()['id']
  legacy_b=self.r.configure({'id':B,'name':'Ander project'},'https://fixture.trycloudflare.com/mcp/'+B,self.token,self.api,lambda:None)['id']
  old_rev,new_rev='3'*64,'4'*64
  old_work=self.work_record(self.r.work_slug(A,old_rev),self.r.marker(A)+' '+self.r.work_marker(A,old_rev),self.uri)
  new_work=self.work_record(self.r.work_slug(A,new_rev),self.r.marker(A)+' '+self.r.work_marker(A,new_rev),self.uri)
  foreign=str(uuid.uuid4());self.api.connectors[foreign]={**self.api.connectors[old_work],'id':foreign,'description':'Someone else [VibeZ:'+'f'*32+':'+A+']'};self.api.active.add(foreign)
  result=self.r.deactivate_project_siblings(A,new_work,self.api,lambda:None)
  self.assertEqual(result,{'inactive_project_connectors':2,'project_cleanup_pending':0})
  # A connector the caller just verified is not read again; a foreign or
  # mismatching "active" value is ignored and read as before.
  before=len(self.api.calls);result=self.r.deactivate_project_siblings(A,new_work,self.api,lambda:None,active=self.api.connectors[new_work])
  self.assertEqual(result,{'inactive_project_connectors':0,'project_cleanup_pending':0})
  self.assertNotIn(('GET','/connectors/'+new_work,None),self.api.calls[before:])
  before=len(self.api.calls);self.r.deactivate_project_siblings(A,new_work,self.api,lambda:None,active={'id':foreign})
  self.assertIn(('GET','/connectors/'+new_work,None),self.api.calls[before:])
  self.assertIn(new_work,self.api.active);self.assertIn(legacy_b,self.api.active);self.assertIn(foreign,self.api.active)
  self.assertNotIn(legacy_a,self.api.active);self.assertNotIn(old_work,self.api.active)
  # This installation's older connectors of this project are removed; another
  # project's and someone else's connectors are never touched.
  self.assertNotIn(old_work,self.api.connectors);self.assertNotIn(legacy_a,self.api.connectors)
  self.assertIn(new_work,self.api.connectors);self.assertIn(legacy_b,self.api.connectors);self.assertIn(foreign,self.api.connectors)
  self.assertEqual(sorted(path for method,path,_ in self.api.calls if method=='DELETE'),sorted(['/connectors/'+old_work,'/connectors/'+legacy_a]))

 def test_refused_removal_falls_back_to_pausing(self):
  old_rev,new_rev='3'*64,'4'*64
  old_work=self.work_record(self.r.work_slug(A,old_rev),self.r.marker(A)+' '+self.r.work_marker(A,old_rev),self.uri)
  new_work=self.work_record(self.r.work_slug(A,new_rev),self.r.marker(A)+' '+self.r.work_marker(A,new_rev),self.uri)
  original=self.api.call
  def refuse(method,path,data=None):
   if method=='DELETE':raise auto.SetupError('mistral_error','refused',405)
   return original(method,path,data)
  self.api.call=refuse
  result=self.r.deactivate_project_siblings(A,new_work,self.api,lambda:None)
  self.assertEqual(result,{'inactive_project_connectors':1,'project_cleanup_pending':0})
  self.assertIn(old_work,self.api.connectors);self.assertNotIn(old_work,self.api.active)
 def test_work_lost_receipt_is_recovered_by_exact_marker_and_duplicates_are_rejected(self):
  revision='1'*64;slug=self.r.work_slug(A,revision)
  desc=self.r.marker(A)+' '+self.r.work_marker(A,revision)
  cid=self.work_record(slug,desc,self.uri)
  remote=self.r.find_work(A,revision,self.api,lambda:None)
  self.assertEqual(remote['id'],cid)
  self.work_record(slug,desc,self.uri)
  with self.assertRaisesRegex(auto.SetupError,'more than one'):
   self.r.find_work(A,revision,self.api,lambda:None)
  self.assertEqual(self.r.records,{})
  self.assertTrue(all(method=='GET' for method,_,_ in self.api.calls))

 def test_work_receipt_for_the_wrong_folder_never_replaces_the_old_connector(self):
  predecessor=self.configure()['id'];revision='2'*64
  def wrong_scope(slug,description,server,token):
   return self.work_record(slug,description,'https://fixture.trycloudflare.com/mcp/'+B)
  self.api.calls.clear()
  with self.assertRaises(auto.SetupError) as exc:
   self.r.configure_work(self.project,revision,self.uri,self.token,self.api,lambda:None,wrong_scope)
  self.assertEqual(exc.exception.code,'ownership')
  self.assertEqual(self.r.records[A]['id'],predecessor)
  self.assertTrue(all(method=='GET' for method,_,_ in self.api.calls))


class AutomaticTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);folder=self.root/'folder';folder.mkdir();(folder/'text.txt').write_text('Fixture file')
  self.events=[];self.web=web.Connector(self.events.append,self.root/'private',approval_wait=0);self.web.select({'id':A,'name':'CityTripXL'});self.web.link(A,folder)
  self.auth_calls=0
  def authenticate(cancel,announce):self.auth_calls+=1;announce('https://console.mistral.ai/authorize?fixture=1');return 'fixture-api-account-secret'
  self.engine=SimpleNamespace(web=self.web,key='',lock=threading.RLock(),external_output=self.events.append,auth=SimpleNamespace(authenticate=authenticate))
  self.service=Service(auto.SetupError,self.web);self.manager=auto.AutomaticConnector(self.engine,api_factory=self.service.api,probe=lambda server,token,guard,cancel:(guard(),self.service.discover(server.split('/mcp/',1)[1].split('/')[0],token),guard()))
  def tunnel():self.web.tunnel_url='https://fixture.trycloudflare.com';self.web.tunnel_status='running';self.web.state()
  self.web.start_tunnel=tunnel
 def tearDown(self):
  self.manager.close()
  if self.manager.job:self.manager.job['thread'].join(3)
  self.web.close();self.tmp.cleanup()
 def connect(self):self.manager.connect(A);self.manager.job['thread'].join(6);self.assertFalse(self.manager.job['thread'].is_alive())
 def test_transient_public_readiness_timeout_is_retried_without_another_click(self):
  original=self.manager.probe;calls=[]
  def probe(server,token,guard,cancel):
   calls.append(1)
   if len(calls)==1:raise auto.SetupError('readiness','Temporary fixture edge delay',stage='readiness')
   return original(server,token,guard,cancel)
  self.manager.probe=probe;self.manager._wait=lambda job,delay:self.manager.guard(job)
  self.connect();self.assertEqual(len(calls),2);self.assertEqual(self.manager.states[A]['status'],'connected');self.assertIn(A,self.web.enabled)
 def test_public_readiness_retry_is_bounded_and_never_registers_an_unreachable_server(self):
  calls=[]
  def probe(*args):calls.append(1);raise auto.SetupError('readiness','Fixture unavailable',stage='readiness')
  self.manager.probe=probe;self.manager._wait=lambda job,delay:self.manager.guard(job)
  self.connect();self.assertEqual(len(calls),auto.READY_ATTEMPTS);self.assertEqual(self.manager.states[A]['error_code'],'readiness');self.assertNotIn(A,self.web.enabled);self.assertEqual(self.service.connectors,{})
 def test_silent_public_address_is_replaced_by_a_new_tunnel_address(self):
  starts=[];urls=[]
  def tunnel():
   starts.append(1);self.web.tunnel_url='https://fixture-%d.trycloudflare.com'%len(starts);self.web.tunnel_status='running';self.web.state()
  self.web.start_tunnel=tunnel;original=self.manager.probe
  def probe(server,token,guard,cancel):
   urls.append(server.split('/mcp/')[0])
   if len(urls)==1:raise auto.SetupError('readiness','Fixture silent address',stage='readiness')
   return original(server,token,guard,cancel)
  self.manager.probe=probe;self.manager._wait=lambda job,delay:self.manager.guard(job)
  self.connect();self.assertEqual(urls,['https://fixture-1.trycloudflare.com','https://fixture-2.trycloudflare.com']);self.assertEqual(len(starts),2)
  self.assertEqual(self.manager.states[A]['status'],'connected');self.assertIn(A,self.web.enabled)
 def failing_tunnel(self,failures,reason='cloudflare'):
  starts=[];phases=[]
  def tunnel():
   starts.append(1)
   if len(starts)<=failures:
    # Like the real helper: a failed start revokes the project.
    with self.web.lock:self.web.revoke(A)
    self.web.tunnel_status='failed'
   else:self.web.tunnel_url='https://fixture.trycloudflare.com';self.web.tunnel_status='running'
   self.web.state()
  self.web.start_tunnel=tunnel;self.web.tunnel_failure_reason=lambda:reason
  progress=self.manager.progress
  def record(key,status,message,**extra):phases.append((extra.get('phase'),extra.get('attempt')));return progress(key,status,message,**extra)
  self.manager.progress=record;self.manager._wait=lambda job,delay:self.manager.guard(job)
  return starts,phases
 def test_a_tunnel_that_fails_to_start_is_tried_again_without_another_click(self):
  # Measured on 12 Nov 2026: Cloudflare's quick-tunnel service gave no address
  # for about twenty minutes and one failed start ended the link.
  starts,phases=self.failing_tunnel(2)
  self.connect();self.assertEqual(len(starts),3);self.assertEqual(self.manager.states[A]['status'],'connected');self.assertIn(A,self.web.enabled)
  self.assertIn(('tunnel_retry',2),phases);self.assertIn(('tunnel_retry',3),phases);self.assertIn(('tunnel',None),phases)
 def test_tunnel_retries_are_bounded_and_name_the_side_that_failed(self):
  self.assertEqual(auto.TUNNEL_ATTEMPTS,3);self.assertLessEqual(sum(auto.TUNNEL_RETRY_PAUSES),30)
  for reason,code in (('cloudflare','tunnel_cloudflare'),('network','tunnel_network'),('unknown','tunnel')):
   with self.subTest(reason=reason):
    starts,_=self.failing_tunnel(99,reason)
    self.connect();self.assertEqual(len(starts),auto.TUNNEL_ATTEMPTS);self.assertEqual(self.manager.states[A]['status'],'error')
    self.assertEqual(self.manager.states[A]['error_code'],code);self.assertNotIn(A,self.web.enabled);self.assertEqual(self.service.connectors,{})
 def test_a_stopped_tunnel_is_not_retried(self):
  starts=[]
  def tunnel():starts.append(1);self.web.tunnel_status='stopped';self.web.state()
  self.web.start_tunnel=tunnel;self.manager._wait=lambda job,delay:self.manager.guard(job)
  self.connect();self.assertEqual(len(starts),1);self.assertEqual(self.manager.states[A]['error_code'],'tunnel')
 def test_the_helper_log_tells_a_cloudflare_outage_from_no_internet(self):
  log=self.web.directory/'tunnel.log'
  cases=((b'{"level":"error","message":"failed to request quick Tunnel: Post \\"https://api.trycloudflare.com/tunnel\\": context deadline exceeded"}\n','cloudflare'),
         (b'ERR failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": dial tcp: lookup api.trycloudflare.com: no such host\n','network'),
         (b'ERR dial tcp 198.51.100.1:443: connect: network is unreachable\n','network'),
         (b'','cloudflare'),(b'ERR the helper binary reported something else\n','unknown'))
  for raw,expected in cases:
   with self.subTest(expected=expected,raw=raw[:40]):
    log.write_bytes(raw);self.assertEqual(self.web.tunnel_failure_reason(),expected)
  log.unlink();self.assertEqual(self.web.tunnel_failure_reason(),'unknown')
 def test_public_readiness_check_is_short_by_default(self):
  self.assertLessEqual(auto.READY_SECONDS,15);self.assertGreaterEqual(auto.READY_ATTEMPTS,2)
 def test_public_authentication_failure_is_not_retried(self):
  calls=[]
  def probe(*args):calls.append(1);raise auto.SetupError('readiness_auth','Fixture unauthorized',401,stage='readiness')
  self.manager.probe=probe
  self.connect();self.assertEqual(len(calls),1);self.assertEqual(self.manager.states[A]['error_code'],'readiness_auth');self.assertEqual(self.service.connectors,{})
 def test_manual_pause_cancels_the_pending_public_readiness_retry(self):
  calls=[]
  def probe(*args):calls.append(1);raise auto.SetupError('readiness','Fixture edge delay',stage='readiness')
  def wait(job,delay):self.web.pause(A);self.manager.cancel(A);self.manager.guard(job)
  self.manager.probe=probe;self.manager._wait=wait
  self.connect();self.assertEqual(len(calls),1);self.assertTrue(self.web.projects[A]['manually_paused']);self.assertEqual(self.manager.states[A]['status'],'paused');self.assertNotIn(A,self.web.enabled);self.assertEqual(self.service.connectors,{})
 def test_one_click_authorizes_registers_activates_and_discovers_real_http_mcp(self):
  self.connect();self.assertEqual(self.manager.states[A]['status'],'connected');self.assertEqual(self.auth_calls,1);self.assertEqual(len(self.service.connectors),1);self.assertIn(A,self.web.enabled)
  for p in (self.root/'private').glob('*.json'):self.assertNotIn('fixture-api-account-secret',p.read_text())
  self.assertNotIn('fixture-api-account-secret',json.dumps(self.events))
 def test_sign_in_failure_keeps_safe_reason_and_stage_without_credentials(self):
  def fail(cancel,announce):raise web.base.SignInError('The connection to Mistral dropped. Try again.')
  self.engine.auth=SimpleNamespace(authenticate=fail);self.connect()
  diagnostic=json.loads(self.manager.error_path.read_text());self.assertEqual(diagnostic['stage'],'authorize');self.assertEqual(diagnostic['exception_type'],'SignInError');self.assertIn('dropped',diagnostic['auth_message'])
  self.assertEqual(self.manager.states[A]['error_code'],'sign_in')
 def test_unknown_failure_records_stack_locations_but_never_exception_values(self):
  def fail(cancel,announce):raise ValueError('private-error-secret-value')
  self.engine.auth=SimpleNamespace(authenticate=fail);self.connect()
  raw=self.manager.error_path.read_text();diagnostic=json.loads(raw);self.assertEqual(diagnostic['exception_type'],'ValueError');self.assertTrue(diagnostic['trace']);self.assertNotIn('private-error-secret-value',raw)
 def test_second_click_reuses_login_and_existing_connector(self):
  self.connect();self.connect();self.assertEqual(self.auth_calls,1);self.assertEqual(len(self.service.connectors),1)
 def test_rejected_file_credentials_keep_valid_account_login_and_pause_folder(self):
  self.connect();key=self.engine.key
  def hook(method,path,data):
   if path.endswith('/user/credentials'):raise auto.SetupError('sign_in','Invalid credentials provided',401)
  self.service.hook=hook;self.connect()
  self.assertEqual(self.manager.states[A]['error_code'],'connector_auth');self.assertEqual(self.engine.key,key)
  self.assertNotIn(A,self.web.enabled);self.assertEqual(self.auth_calls,1)
  diagnostic=json.loads(self.manager.error_path.read_text());check=diagnostic['connection_check']
  self.assertTrue(check['current_server_is_current']);self.assertEqual(check['current_auth_methods'],[{'method_type':'none','authorization_is_global':True,'header_count':0}])
  for secret in [key,self.web.projects[A]['token']]:self.assertNotIn(secret,self.manager.error_path.read_text())
 def test_actual_workspace_failure_pauses_access_instead_of_reporting_connected(self):
  def hook(method,path,data):
   if path.endswith('/workspace_overview/call'):raise auto.SetupError('mistral_error','Bad gateway',502)
  self.service.hook=hook;self.connect()
  self.assertEqual(self.manager.states[A]['status'],'error');self.assertNotIn(A,self.web.enabled)
  diagnostic=json.loads(self.manager.error_path.read_text());self.assertEqual(diagnostic['stage'],'execute');self.assertEqual(diagnostic['http_status'],502)
  self.assertNotIn(self.web.projects[A]['token'],self.manager.error_path.read_text())
 def test_update_stage_rejection_also_keeps_confirmed_account_login(self):
  self.connect();key=self.engine.key
  def hook(method,path,data):
   if method=='PATCH' and '/user/' not in path:raise auto.SetupError('sign_in','Invalid credentials provided',401)
  self.service.hook=hook;self.connect()
  self.assertEqual(self.manager.states[A]['error_code'],'connector_auth');self.assertEqual(self.engine.key,key)
  self.assertEqual(json.loads(self.manager.error_path.read_text())['stage'],'update');self.assertNotIn(A,self.web.enabled)
 def test_confirmed_expired_account_clears_only_the_account_access(self):
  self.connect()
  def hook(method,path,data):raise auto.SetupError('sign_in','Expired account',401)
  self.service.hook=hook;self.connect();self.assertEqual(self.engine.key,'');self.assertNotIn(A,self.web.enabled)
 def test_explicit_legacy_recovery_repairs_existing_connector_without_creating_another(self):
  self.connect();first=self.manager.registry.records[A]['id'];old=dict(self.service.connectors[first]);old.update(id=str(uuid.uuid4()),name='vibez_citytripxl_old');self.service.connectors[old['id']]=old
  self.manager.connect(A,old['name']);self.manager.job['thread'].join(6)
  self.assertEqual(self.manager.states[A]['status'],'connected');self.assertEqual(self.manager.registry.records[A]['id'],old['id']);self.assertEqual(len(self.service.connectors),2)
 def test_missing_preferred_reference_never_creates_a_new_connector(self):
  self.manager.connect(A,'vibez_nonexistent_old');self.manager.job['thread'].join(6)
  self.assertEqual(self.manager.states[A]['error_code'],'not_found');self.assertEqual(self.service.connectors,{})
 def test_invalid_reference_is_rejected_before_any_setup(self):
  for ref in ['https://evil.test','../other','x?redirect=bad']:
   with self.assertRaises(ValueError):self.manager.connect(A,ref)
  self.assertEqual(self.service.calls,[])
 def test_context_switch_during_setup_cancels_before_creating(self):
  def hook(m,p,d):self.web.select({'id':B,'name':'Other'});self.manager.context()
  self.service.hook=hook;self.connect();self.assertEqual(self.manager.states[A]['status'],'cancelled');self.assertEqual(self.service.connectors,{});self.assertNotIn(A,self.web.enabled)
 def test_permission_failure_pauses_the_folder_and_reports_the_limit(self):
  self.service.fail=403;self.connect();self.assertEqual(self.manager.states[A]['error_code'],'permission');self.assertNotIn(A,self.web.enabled)
 def test_http_failure_records_only_step_status_and_safe_field_names(self):
  def hook(method,path,data):
   if method=='POST' and path=='/connectors':raise auto.SetupError('invalid_request','Afgewezen',400)
  self.service.hook=hook;self.connect();report=json.loads(self.manager.error_path.read_text())
  self.assertEqual(report,{'stage':'create','http_status':400,'error_code':'invalid_request','fields':[],'transport_check':self.web.transport_snapshot()})
  self.assertEqual(self.manager.error_path.stat().st_mode&0o777,0o600)
  self.assertNotIn('fixture-api-account-secret',self.manager.error_path.read_text());self.assertNotIn(A,self.manager.error_path.read_text())
 def test_temporary_provider_reachability_failure_is_retried_once(self):
  failed=False
  def hook(method,path,data):
   nonlocal failed
   if method=='POST' and path=='/connectors' and not failed:
    failed=True;raise auto.SetupError('server_unreachable','Temporary server connection failure',400)
  self.service.hook=hook;self.connect();self.assertEqual(self.manager.states[A]['status'],'connected');self.assertEqual(len(self.service.connectors),1)
 def test_uncertain_creation_retry_recovers_existing_connector(self):
  original=self.service.call;failed=False
  def call(method,path,data=None):
   nonlocal failed
   value=original(method,path,data)
   if method=='POST' and path=='/connectors' and not failed:
    failed=True;raise auto.SetupError('server_unreachable','Unknown outcome',400)
   return value
  self.service.call=call;self.connect();self.assertEqual(self.manager.states[A]['status'],'connected');self.assertEqual(len(self.service.connectors),1)
 def test_duplicate_click_during_authentication_does_not_start_second_job(self):
  entered=threading.Event();release=threading.Event()
  def auth(cancel,announce):entered.set();release.wait(3);return 'fixture-api-account-secret'
  self.engine.auth=SimpleNamespace(authenticate=auth);self.manager.connect(A);self.assertTrue(entered.wait(2));first=self.manager.job['thread'];self.manager.connect(A);self.assertIs(self.manager.job['thread'],first);release.set();first.join(6);self.assertFalse(first.is_alive());self.assertEqual(len(self.service.connectors),1)
 def test_relink_during_setup_revokes_the_old_scope(self):
  replacement=self.root/'replacement';replacement.mkdir()
  def hook(m,p,d):self.web.link(A,replacement)
  self.service.hook=hook;self.connect();self.assertEqual(self.manager.states[A]['status'],'cancelled');self.assertEqual(self.service.connectors,{})

 def test_native_work_failure_reports_only_sanitized_step_names(self):
  self.engine.key='fixture-api-account-secret'
  ready=threading.Event()
  def capture(event):
   self.events.append(event)
   if event['type']=='web_work_enroll':ready.set()
  self.engine.external_output=capture
  self.manager.connect(A,method='work')
  self.assertTrue(ready.wait(4))
  request=next(e for e in self.events if e['type']=='web_work_enroll')
  self.manager.work_result({'job_id':request['job_id'],'project_id':A,'error':'work_setup_failed',
                            'diagnostic':{'stage':'reselect','state':'timeout','reason':'Secret Page Text','token':'fixture-api-account-secret','site_language':'en'}})
  self.manager.job['thread'].join(8);self.assertFalse(self.manager.job['thread'].is_alive())
  self.assertEqual(self.manager.states[A]['error_code'],'work_setup_failed')
  report=json.loads(self.manager.error_path.read_text())
  self.assertEqual(report['work_step'],{'event':'enroll','stage':'reselect','state':'timeout','site_language':'en'})
  # The panel learns which part failed through a fixed name only.
  self.assertEqual(self.manager.states[A]['work_failure'],'setup')
  self.assertEqual(self.manager.states[A]['message'],'VibeZ could not finish the setup in Mistral Work. Try again.')
  self.assertNotIn('fixture-api-account-secret',self.manager.error_path.read_text());self.assertNotIn('Secret Page Text',self.manager.error_path.read_text())

 def test_work_failure_names_only_fixed_kinds(self):
  work_failure=auto.work_failure
  self.assertEqual(work_failure({'event':'enroll','stage':'open-menu','state':'timeout'}),'setup')
  for stage in ['authorize','confirm','reselect','selected']:self.assertEqual(work_failure({'event':'attach','stage':stage}),'verify')
  for step in [{'event':'attach','stage':'open-menu'},{'event':'attach','stage':'choose'},{},None,'enroll']:self.assertIsNone(work_failure(step))

 def test_native_step_timing_is_recorded_with_the_connector_steps(self):
  # The native wizard and conversation steps report their own step timing
  # (fixed names, seconds since the request): it lands in connector-timing.json
  # as enroll:<step> and attach:<step> marks, so slow steps can be found.
  self.engine.key='fixture-api-account-secret'
  binding=self.web.workspace_binding(A);r=self.manager.registry;slug=r.work_slug(A,binding)
  owner={'visibility':'private','owner_type':'user','owner_id':'fixture-user','creator_id':'fixture-user','mistral':False,'protocol':'mcp','title':slug,
         'description':r.marker(A)+' '+r.work_marker(A,binding)}
  def capture(event):
   self.events.append(event)
   if event['type'] in ('web_work_enroll','web_work_attach'):
    reply={'job_id':event['job_id'],'project_id':A}
    if event['type']=='web_work_enroll':
     new=str(uuid.uuid4());self.service.connectors[new]={'id':new,'name':slug+'_cd34','server':event['endpoint'],**owner}
     self.service.active.add(new);reply['connector_name']=slug+'_cd34'
     reply['timing']=[['view',0.2],['page',1.4],['submit',6.0],['detail',9.1],['Bad Name',1],['page',-3],['page','x'],[1,2],['page',True],['t'*33,1]]
    else:
     reply['connector_id']=event['connector_id'];reply['timing']=[['open-menu',0.5],['selected',4.2]]
    threading.Thread(target=self.manager.work_result,args=(reply,),daemon=True).start()
  self.engine.external_output=capture
  self.manager.connect(A,method='work');self.manager.job['thread'].join(8)
  self.assertEqual(self.manager.states[A]['status'],'connected')
  timing=json.loads(self.manager.error_path.with_name('connector-timing.json').read_text())
  names=[step for step,_ in timing['steps']]
  self.assertEqual([n for n in names if n.startswith('enroll:')],['enroll:view','enroll:page','enroll:submit','enroll:detail'])
  self.assertEqual([n for n in names if n.startswith('attach:')],['attach:open-menu','attach:selected'])
  self.assertLess(names.index('enroll:detail'),names.index('enrolled'));self.assertLess(names.index('enrolled'),names.index('created'))
  self.assertLess(names.index('attach:selected'),names.index('attached'))
  by=dict(timing['steps']);self.assertLessEqual(by['enroll:view'],by['enroll:detail']);self.assertAlmostEqual(by['enroll:detail']-by['enroll:view'],8.9,delta=0.3)
  self.assertTrue(all(isinstance(v,(int,float)) for v in by.values()))

 def work_fixture(self,events_seen):
  self.engine.key='fixture-api-account-secret'
  binding=self.web.workspace_binding(A);r=self.manager.registry;slug=r.work_slug(A,binding)
  owner={'visibility':'private','owner_type':'user','owner_id':'fixture-user','creator_id':'fixture-user','mistral':False,'protocol':'mcp','title':slug,
         'description':r.marker(A)+' '+r.work_marker(A,binding)}
  def add(endpoint):
   new=str(uuid.uuid4());self.service.connectors[new]={'id':new,'name':slug+'_cd34','server':endpoint,**owner};self.service.active.add(new);return slug+'_cd34'
  def capture(event):
   self.events.append(event)
   if event['type'] in ('web_work_enroll','web_work_attach','web_work_refresh'):
    events_seen.append(event['type']);reply={'job_id':event['job_id'],'project_id':A}
    if event['type']=='web_work_enroll':reply['connector_name']=add(event['endpoint'])
    elif event['type']=='web_work_refresh':reply['connector_name']=event['connector_name']
    else:reply['connector_id']=event['connector_id']
    threading.Thread(target=self.manager.work_result,args=(reply,),daemon=True).start()
  self.engine.external_output=capture
  return binding,add
 def test_link_after_an_interrupted_request_waits_instead_of_failing(self):
  # Someone presses Connect, clicks away while Mistral Work is busy, comes back
  # and presses again. The second press waits for the open request and then
  # links; it never answers with an error that asks to press once more.
  seen=[];binding,_=self.work_fixture(seen)
  with patch.object(auto,'WORK_SETTLE_POLL_SECONDS',.1):
   self.manager.work_uncertain_until[(A,binding)]=time.monotonic()+.5;started=time.monotonic()
   self.manager.connect(A,method='work');self.manager.job['thread'].join(8)
  self.assertEqual(self.manager.states[A]['status'],'connected');self.assertGreaterEqual(time.monotonic()-started,.45)
  self.assertEqual(seen.count('web_work_enroll'),1)
  self.assertNotIn((A,binding),self.manager.work_uncertain_until)
 def test_link_after_an_interrupted_request_adopts_its_late_connector(self):
  # The interrupted request did create its connector, a little later. The
  # second press finds it during the wait and makes no second connector.
  seen=[];binding,add=self.work_fixture(seen)
  original=self.manager._wait;waits=[]
  def wait(job,delay):
   waits.append(delay)
   if len(waits)==1:add('https://fixture.trycloudflare.com/mcp/'+A+'/'+self.web.projects[A]['token'])
   return original(job,delay)
  self.manager._wait=wait
  with patch.object(auto,'WORK_SETTLE_POLL_SECONDS',.1):
   self.manager.work_uncertain_until[(A,binding)]=time.monotonic()+20
   self.manager.connect(A,method='work');self.manager.job['thread'].join(8)
  self.assertNotIn('web_work_enroll',seen);self.assertEqual(len(self.service.connectors),1)
  self.assertEqual(self.manager.states[A]['status'],'connected')
 def test_cancel_ends_the_wait_for_an_interrupted_request(self):
  seen=[];binding,_=self.work_fixture(seen)
  self.manager.work_uncertain_until[(A,binding)]=time.monotonic()+20
  self.manager.connect(A,method='work');thread=self.manager.job['thread']
  deadline=time.monotonic()+4
  while time.monotonic()<deadline and 'confirm the previous request' not in self.manager.states.get(A,{}).get('message',''):time.sleep(.02)
  self.assertIn('confirm the previous request',self.manager.states[A]['message'])
  self.manager.cancel(A);thread.join(4);self.assertFalse(thread.is_alive());self.assertEqual(seen,[])

 def test_connector_with_an_old_tunnel_address_is_replaced_by_a_new_one(self):
  # After a restart the tunnel address changes. Mistral does not reliably let
  # the account connect a re-addressed connector, so VibeZ removes it and
  # creates a new one, which works like a first link.
  self.engine.key='fixture-api-account-secret'
  binding=self.web.workspace_binding(A);token=self.web.projects[A]['token'];r=self.manager.registry
  slug=r.work_slug(A,binding);old=str(uuid.uuid4())
  owner={'visibility':'private','owner_type':'user','owner_id':'fixture-user','creator_id':'fixture-user','mistral':False,'protocol':'mcp','title':slug,
         'description':r.marker(A)+' '+r.work_marker(A,binding)}
  self.service.connectors[old]={'id':old,'name':slug+'_ab12','server':'https://old-address.trycloudflare.com/mcp/'+A+'/'+token,**owner}
  self.service.active.add(old)
  r.records[A]={'id':old,'name':slug+'_ab12','owner_id':'fixture-user','creator_id':'fixture-user','work_binding':binding,'work_auth':'open'}
  seen=[]
  def capture(event):
   self.events.append(event)
   if event['type'] in ('web_work_refresh','web_work_attach','web_work_enroll'):
    seen.append(event['type'])
    reply={'job_id':event['job_id'],'project_id':A}
    if event['type']=='web_work_enroll':
     # The old connector is already gone when the new one is created.
     self.assertNotIn(old,self.service.connectors)
     new=str(uuid.uuid4());self.service.connectors[new]={'id':new,'name':slug+'_cd34','server':event['endpoint'],**owner}
     self.service.active.add(new);reply['connector_name']=slug+'_cd34'
    elif event['type']=='web_work_attach':reply['connector_id']=event['connector_id']
    else:reply['connector_name']=event['connector_name']
    threading.Thread(target=self.manager.work_result,args=(reply,),daemon=True).start()
  self.engine.external_output=capture
  self.manager.connect(A,method='work');self.manager.job['thread'].join(8)
  self.assertEqual(self.manager.states[A]['status'],'connected')
  self.assertEqual(seen,['web_work_enroll','web_work_attach'])
  self.assertNotIn(old,self.service.connectors)
  self.assertNotIn(('PATCH','/connectors/'+old,{'protocol':'mcp','server':self.service.connectors[self.manager.states[A]['connector_id']]['server']}),self.service.calls)
  self.assertEqual(self.manager.registry.records[A]['name'],slug+'_cd34')

 def test_existing_connector_that_mistral_cannot_verify_is_replaced_once(self):
  # Mistral shows its own connection error when an existing connector is
  # connected in the conversation. VibeZ removes it, creates a new one and
  # chooses that; a second failure is reported, never a third attempt.
  for second_fails in (False,True):
   self.setUp() if second_fails else None
   self.engine.key='fixture-api-account-secret'
   binding=self.web.workspace_binding(A);token=self.web.projects[A]['token'];r=self.manager.registry
   slug=r.work_slug(A,binding);old=str(uuid.uuid4())
   owner={'visibility':'private','owner_type':'user','owner_id':'fixture-user','creator_id':'fixture-user','mistral':False,'protocol':'mcp','title':slug,
          'description':r.marker(A)+' '+r.work_marker(A,binding)}
   self.service.connectors[old]={'id':old,'name':slug+'_ab12','server':'https://fixture.trycloudflare.com/mcp/'+A+'/'+token,**owner}
   self.service.active.add(old)
   r.records[A]={'id':old,'name':slug+'_ab12','owner_id':'fixture-user','creator_id':'fixture-user','work_binding':binding,'work_auth':'open'}
   seen=[]
   def capture(event):
    self.events.append(event)
    if event['type'] in ('web_work_refresh','web_work_attach','web_work_enroll'):
     seen.append(event['type'])
     reply={'job_id':event['job_id'],'project_id':A}
     if event['type']=='web_work_refresh':reply['connector_name']=event['connector_name']
     elif event['type']=='web_work_enroll':
      self.assertNotIn(old,self.service.connectors)
      new=str(uuid.uuid4());self.service.connectors[new]={'id':new,'name':slug+'_cd34','server':event['endpoint'],**owner}
      self.service.active.add(new);reply['connector_name']=slug+'_cd34'
     elif event['connector_id']==old or second_fails:
      reply['error']='work_setup_failed';reply['diagnostic']={'stage':'authorize','state':'timeout','reason':'no-password-dialog-open'}
     else:reply['connector_id']=event['connector_id']
     threading.Thread(target=self.manager.work_result,args=(reply,),daemon=True).start()
   self.engine.external_output=capture
   self.manager.connect(A,method='work');self.manager.job['thread'].join(8)
   self.assertEqual(seen,['web_work_refresh','web_work_attach','web_work_enroll','web_work_attach'])
   self.assertNotIn(old,self.service.connectors)
   if second_fails:
    self.assertEqual(self.manager.states[A]['error_code'],'work_setup_failed')
   else:
    self.assertEqual(self.manager.states[A]['status'],'connected')
    self.assertEqual(self.manager.registry.records[A]['name'],slug+'_cd34')

 def test_existing_connector_whose_reconnect_mistral_refuses_is_replaced_without_choosing_it_first(self):
  # Measured live after downtime: Mistral's reconnect form stays open after
  # Save. Choosing that connector then fails three times, so it is replaced at
  # once. Mistral's new-connector form can hang the same way after it made the
  # connector: the engine then finds the new connector itself.
  for form_hangs in (False,True):
   self.setUp() if form_hangs else None
   self.engine.key='fixture-api-account-secret'
   binding=self.web.workspace_binding(A);token=self.web.projects[A]['token'];r=self.manager.registry
   slug=r.work_slug(A,binding);old=str(uuid.uuid4())
   owner={'visibility':'private','owner_type':'user','owner_id':'fixture-user','creator_id':'fixture-user','mistral':False,'protocol':'mcp','title':slug,
          'description':r.marker(A)+' '+r.work_marker(A,binding)}
   self.service.connectors[old]={'id':old,'name':slug+'_ab12','server':'https://fixture.trycloudflare.com/mcp/'+A+'/'+token,**owner}
   self.service.active.add(old)
   r.records[A]={'id':old,'name':slug+'_ab12','owner_id':'fixture-user','creator_id':'fixture-user','work_binding':binding,'work_auth':'open'}
   seen=[]
   def capture(event):
    self.events.append(event)
    if event['type'] in ('web_work_refresh','web_work_attach','web_work_enroll'):
     seen.append(event['type'])
     reply={'job_id':event['job_id'],'project_id':A}
     if event['type']=='web_work_refresh':
      reply['error']='work_setup_failed';reply['diagnostic']={'stage':'refresh','state':'reconnect-failed','reason':'save-stuck'}
     elif event['type']=='web_work_enroll':
      self.assertNotIn(old,self.service.connectors)
      new=str(uuid.uuid4());self.service.connectors[new]={'id':new,'name':slug+'_cd34','server':event['endpoint'],**owner}
      self.service.active.add(new)
      if form_hangs:reply['error']='work_setup_failed';reply['diagnostic']={'stage':'detail','state':'timeout','reason':'form-stuck'}
      else:reply['connector_name']=slug+'_cd34'
     else:
      self.assertNotEqual(event['connector_id'],old);reply['connector_id']=event['connector_id']
     threading.Thread(target=self.manager.work_result,args=(reply,),daemon=True).start()
   self.engine.external_output=capture
   self.manager.connect(A,method='work');self.manager.job['thread'].join(8)
   self.assertEqual(seen,['web_work_refresh','web_work_enroll','web_work_attach'])
   self.assertNotIn(old,self.service.connectors)
   self.assertEqual(self.manager.states[A]['status'],'connected')
   self.assertEqual(self.manager.registry.records[A]['name'],slug+'_cd34')

 def test_failure_after_registration_keeps_the_project_reachable_but_a_cancel_revokes(self):
  # Mistral already holds this attempt's connector when the conversation step
  # fails: revoking the project would make Mistral's own checks fail until
  # the next attempt. A cancel by the user still revokes.
  for cancel in (False,True):
   self.setUp() if cancel else None
   self.engine.key='fixture-api-account-secret'
   binding=self.web.workspace_binding(A);token=self.web.projects[A]['token'];r=self.manager.registry
   slug=r.work_slug(A,binding);cid=str(uuid.uuid4())
   self.service.connectors[cid]={'id':cid,'name':slug+'_ab12','title':slug,'description':r.marker(A)+' '+r.work_marker(A,binding),
    'protocol':'mcp','server':'https://fixture.trycloudflare.com/mcp/'+A+'/'+token,'visibility':'private','owner_type':'user',
    'owner_id':'fixture-user','creator_id':'fixture-user','mistral':False}
   self.service.active.add(cid)
   r.records[A]={'id':cid,'name':slug+'_ab12','owner_id':'fixture-user','creator_id':'fixture-user','work_binding':binding,'work_auth':'open'}
   def capture(event):
    self.events.append(event)
    if event['type'] in ('web_work_refresh','web_work_attach'):
     reply={'job_id':event['job_id'],'project_id':A}
     if event['type']=='web_work_refresh':reply['connector_name']=event['connector_name']
     elif cancel:self.manager.cancel(A);return
     else:reply['error']='work_setup_failed';reply['diagnostic']={'stage':'open-menu','state':'blocked-draft','reason':'other-folder-reference'}
     threading.Thread(target=self.manager.work_result,args=(reply,),daemon=True).start()
   self.engine.external_output=capture
   self.manager.connect(A,method='work');self.manager.job['thread'].join(8)
   if cancel:
    self.assertEqual(self.manager.states[A]['status'],'cancelled');self.assertNotIn(A,self.web.enabled)
   else:
    self.assertEqual(self.manager.states[A]['error_code'],'work_setup_failed')
    self.assertIn(A,self.web.enabled,'the registered connector stays reachable for Mistral and a retry')

 def test_reused_work_connector_that_lost_its_activation_is_activated_again(self):
  self.engine.key='fixture-api-account-secret'
  binding=self.web.workspace_binding(A);token=self.web.projects[A]['token'];r=self.manager.registry
  slug=r.work_slug(A,binding);cid=str(uuid.uuid4())
  self.service.connectors[cid]={'id':cid,'name':slug+'_ab12','title':slug,'description':r.marker(A)+' '+r.work_marker(A,binding),
   'protocol':'mcp','server':'https://fixture.trycloudflare.com/mcp/'+A+'/'+token,'visibility':'private','owner_type':'user',
   'owner_id':'fixture-user','creator_id':'fixture-user','mistral':False}
  r.records[A]={'id':cid,'name':slug+'_ab12','owner_id':'fixture-user','creator_id':'fixture-user','work_binding':binding,'work_auth':'open'}
  def capture(event):
   self.events.append(event)
   if event['type'] in ('web_work_refresh','web_work_attach'):
    reply={'job_id':event['job_id'],'project_id':A}
    if event['type']=='web_work_refresh':reply['connector_name']=event['connector_name']
    else:
     # The chat can only use it once the account has it active again.
     self.assertIn(cid,self.service.active);reply['connector_id']=event['connector_id']
    threading.Thread(target=self.manager.work_result,args=(reply,),daemon=True).start()
  self.engine.external_output=capture
  self.manager.connect(A,method='work');self.manager.job['thread'].join(8)
  self.assertEqual(self.manager.states[A]['status'],'connected')
  self.assertIn(('POST','/connectors/'+cid+'/user/activate',None),self.service.calls)

 def test_reused_open_work_connector_is_reconnected_before_selection(self):
  self.engine.key='fixture-api-account-secret'
  binding=self.web.workspace_binding(A);token=self.web.projects[A]['token'];r=self.manager.registry
  slug=r.work_slug(A,binding);cid=str(uuid.uuid4())
  self.service.connectors[cid]={'id':cid,'name':slug+'_ab12','title':slug,'description':r.marker(A)+' '+r.work_marker(A,binding),
   'protocol':'mcp','server':'https://fixture.trycloudflare.com/mcp/'+A+'/'+token,'visibility':'private','owner_type':'user',
   'owner_id':'fixture-user','creator_id':'fixture-user','mistral':False}
  self.service.active.add(cid)
  r.records[A]={'id':cid,'name':slug+'_ab12','owner_id':'fixture-user','creator_id':'fixture-user','work_binding':binding,'work_auth':'open'}
  seen=[]
  def capture(event):
   self.events.append(event)
   if event['type'] in ('web_work_refresh','web_work_attach','web_work_enroll'):
    seen.append(event['type'])
    reply={'job_id':event['job_id'],'project_id':A}
    if event['type']=='web_work_refresh':reply['connector_name']=event['connector_name']
    elif event['type']=='web_work_attach':reply['connector_id']=event['connector_id']
    else:reply['error']='work_setup_failed'
    threading.Thread(target=self.manager.work_result,args=(reply,),daemon=True).start()
  self.engine.external_output=capture
  self.manager.connect(A,method='work');self.manager.job['thread'].join(8)
  self.assertEqual(seen,['web_work_refresh','web_work_attach'])
  self.assertEqual(self.manager.states[A]['status'],'connected')
  # Already active: no extra activation call.
  self.assertNotIn(('POST','/connectors/'+cid+'/user/activate',None),self.service.calls)
  refresh=next(e for e in self.events if e['type']=='web_work_refresh')
  self.assertEqual(refresh['connector_name'],slug+'_ab12');self.assertNotIn('token',refresh)

 def test_work_receipt_after_project_switch_cannot_pin_the_work_connector(self):
  self.engine.key='fixture-api-account-secret'
  ready=threading.Event()
  def capture(event):
   self.events.append(event)
   if event['type']=='web_work_enroll':ready.set()
  self.engine.external_output=capture
  self.manager.connect(A,method='work')
  self.assertTrue(ready.wait(4))
  request=next(e for e in self.events if e['type']=='web_work_enroll')
  self.assertEqual(request['project_id'],A)
  self.assertEqual(request['binding'],self.web.workspace_binding(A))
  self.web.select({'id':B,'name':'Other'})
  self.manager.context()
  self.manager.work_result({'job_id':request['job_id'],'project_id':A,'connector_id':str(uuid.uuid4())})
  self.manager.job['thread'].join(3)
  self.assertEqual(self.manager.states[A]['status'],'cancelled')
  self.assertNotIn(A,self.manager.registry.records)
  self.assertNotIn(A,self.web.enabled)
  self.assertTrue(any(e['type']=='web_work_enroll_cancel' for e in self.events))


class ReadinessTests(unittest.TestCase):
 def test_readiness_retries_dns_checks_tools_and_releases_its_session(self):
  import io,urllib.error
  calls=[];attempts=0
  class Response(io.BytesIO):
   def __init__(self,value):super().__init__(json.dumps(value).encode());self.headers={'Mcp-Session-Id':'fixture-session'}
  class Opener:
   def open(self,request,timeout):
    nonlocal attempts
    calls.append(request.get_method())
    if request.get_method()=='DELETE':return Response({})
    method=json.loads(request.data)['method']
    if method=='initialize':
     attempts+=1
     if attempts<3:raise urllib.error.URLError('temporary DNS failure')
     return Response({'result':{'serverInfo':{'name':'VibeZ-local-files'},'protocolVersion':'2025-06-18'}})
    if json.loads(request.data)['method']=='server/discover':return Response({'result':{'resultType':'complete','supportedVersions':['2026-07-28']}})
    return Response({'result':{'tools':[{'name':name} for name in auto.REQUIRED]}})
  auto.wait_ready('https://fixture.trycloudflare.com/mcp/'+A,'fixture-token',lambda:None,threading.Event(),opener=Opener(),timeout=1,interval=.001)
  self.assertEqual(attempts,3);self.assertEqual(calls[-1],'DELETE')
 def test_readiness_accepts_a_server_that_answers_the_handshake_only(self):
  import io
  class Response(io.BytesIO):
   def __init__(self,value):super().__init__(json.dumps(value).encode());self.headers={'Mcp-Session-Id':'fixture-session'}
  class Opener:
   def open(self,request,timeout):
    if request.get_method()=='DELETE':return Response({})
    method=json.loads(request.data)['method']
    if method=='initialize':return Response({'result':{'serverInfo':{'name':'VibeZ-local-files'},'protocolVersion':'2025-06-18'}})
    if method=='server/discover':raise auto.urllib.error.HTTPError(request.full_url,400,'Bad Request',{},io.BytesIO(b'{}'))
    return Response({'result':{'tools':[{'name':name} for name in auto.REQUIRED]}})
  auto.wait_ready('https://fixture.trycloudflare.com/mcp/'+A,'fixture-token',lambda:None,threading.Event(),opener=Opener(),timeout=1,interval=.001)
 def test_code_readiness_uses_exact_namespaced_path_and_cleans_up_session(self):
  import io
  url='https://fixture.trycloudflare.com/mcp/code-'+A;calls=[]
  class Response(io.BytesIO):
   def __init__(self,value):super().__init__(json.dumps(value).encode());self.headers={'Mcp-Session-Id':'fixture-code-session'}
  class Opener:
   def open(self,request,timeout):
    calls.append((request.get_method(),request.full_url))
    if request.get_method()=='DELETE':return Response({})
    if json.loads(request.data)['method']=='initialize':return Response({'result':{'serverInfo':{'name':'VibeZ-local-files'},'protocolVersion':'2025-06-18'}})
    if json.loads(request.data)['method']=='server/discover':return Response({'result':{'resultType':'complete','supportedVersions':['2026-07-28']}})
    return Response({'result':{'tools':[{'name':name} for name in auto.REQUIRED]}})
  auto.wait_ready(url,'fixture-token',lambda:None,threading.Event(),opener=Opener(),timeout=1)
  self.assertEqual(calls[-1],('DELETE',url));self.assertTrue(all(target==url for _,target in calls))
 def test_readiness_rejects_malformed_code_and_work_ids_without_sending_key(self):
  class Opener:
   def open(self,*args,**kwargs):raise AssertionError('must not send fixture key')
  for key in ['code-code-'+A,'code-'+A[:-1],'code-'+A.upper(),'a'*36,'work-'+A]:
   with self.assertRaises(auto.SetupError):auto.wait_ready('https://fixture.trycloudflare.com/mcp/'+key,'fixture-token',lambda:None,threading.Event(),opener=Opener())

 def test_readiness_rejects_other_origins_before_sending_authentication(self):
  class Opener:
   def open(self,*args,**kwargs):raise AssertionError('must not send')
  with self.assertRaises(auto.SetupError):auto.wait_ready('https://example.org/mcp/'+A,'fixture-token',lambda:None,threading.Event(),opener=Opener())
 def test_public_dns_rejects_private_addresses(self):
  import io
  class Response(io.BytesIO):
   def __init__(self):super().__init__(json.dumps({'Status':0,'Answer':[{'name':'fixture.trycloudflare.com.','type':1,'data':'127.0.0.1'}]}).encode())
  class Opener:
   def open(self,*args,**kwargs):return Response()
  with patch.object(auto.urllib.request,'build_opener',return_value=Opener()):
   with self.assertRaises(OSError):auto.public_addresses('fixture.trycloudflare.com')
 def test_public_dns_never_accepts_other_domains(self):
  with self.assertRaises(ValueError):auto.public_addresses('example.org')
 def test_cancelled_readiness_never_sends_any_request(self):
  cancel=threading.Event();cancel.set()
  with self.assertRaises(auto.Cancelled):auto.wait_ready('https://fixture.trycloudflare.com/mcp/'+A,'fixture-token',lambda:None,cancel)

class TransportTests(unittest.TestCase):
 def test_non_connector_routes_and_custom_origins_are_never_accepted(self):
  api=auto.MistralAPI('fixture-api-account-secret')
  for path in ['https://evil.test','/chat/completions','/connectors/../models','/connectors/x?redirect=https://evil.test']:
   with self.assertRaises(auto.SetupError):api.call('POST',path,{})
 def test_400_schema_errors_show_only_allowlisted_fields_and_step(self):
  import io,urllib.error
  body={'detail':[{'loc':['body','auth_methods'],'type':'extra_forbidden','msg':'fixture-api-account-secret','input':{'secret':'fixture-local-secret'}},{'loc':['body','fixture-api-account-secret'],'type':'missing'}]}
  error=urllib.error.HTTPError('https://api.mistral.ai/v1/connectors',400,'Bad Request',{},io.BytesIO(json.dumps(body).encode()))
  parsed=auto.parse_error(error,'POST','/connectors')
  self.assertEqual(parsed.stage,'create');self.assertEqual(parsed.fields,[{'field':'auth_methods','type':'extra_forbidden'}]);self.assertIn('creating',str(parsed))
  self.assertNotIn('fixture-api',str(parsed));self.assertNotIn('fixture-local',str(parsed))
 def test_failed_workspace_execution_is_not_misreported_as_missing_api_permissions(self):
  import io,urllib.error
  for status in [403,502]:
   error=urllib.error.HTTPError('https://api.mistral.ai/v1/connectors/x/tools/workspace_overview/call',status,'failure',{},io.BytesIO(b'{"message":"connection refused"}'))
   parsed=auto.parse_error(error,'POST','/connectors/x/tools/workspace_overview/call');self.assertEqual(parsed.code,'execution');self.assertEqual(parsed.stage,'execute')
 def test_400_explicit_key_restriction_uses_permission_guidance(self):
  import io,urllib.error
  error=urllib.error.HTTPError('https://api.mistral.ai/v1/connectors',400,'Bad Request',{},io.BytesIO(b'{"detail":"Unsupported API key type: Vibe"}'))
  parsed=auto.parse_error(error,'POST','/connectors');self.assertEqual(parsed.code,'permission');self.assertIn('Studio',str(parsed))
 def test_oversized_or_unstructured_400_responses_never_become_error_text(self):
  import io,urllib.error
  for body in [b'fixture-api-account-secret',b'{"detail":"'+b'x'*70000+b'"}']:
   error=urllib.error.HTTPError('https://api.mistral.ai/v1/connectors',400,'Bad Request',{},io.BytesIO(body));parsed=auto.parse_error(error,'POST','/connectors')
   self.assertEqual(parsed.fields,[]);self.assertNotIn('fixture-api',str(parsed));self.assertLess(len(str(parsed)),180)
 def test_alternate_error_envelope_reports_message_without_short_or_encoded_credentials(self):
  body={'error':{'message':'Invalid field auth_methods. key tinykey; Authorization: Bearer local-token; see https://example.org/private'},'input':{'password':'do-not-report'}}
  summary=auto.provider_summary(body,['tinykey','local-token'])
  self.assertIn('Invalid field auth_methods',summary)
  for secret in ['tinykey','local-token','do-not-report','example.org']:self.assertNotIn(secret,summary)
 def test_nested_connector_global_headers_are_redacted_in_provider_errors(self):
  body={'auth_methods':[{'method_type':'none','global_headers':{'Authorization':{'value':'Bearer short-key','is_secret':True}}}]}
  secrets=auto.request_secrets('account-key',body);self.assertIn('short-key',secrets)
  self.assertNotIn('short-key',auto.provider_summary({'message':'Rejected Bearer short-key'},secrets))
 def test_request_secrets_include_both_account_and_nested_mcp_authentication(self):
  values=auto.request_secrets('account-key',{'headers':{'Authorization':'Bearer local-token'},'credentials':{'bearer_token':'replacement-token'}})
  for secret in ['account-key','local-token','replacement-token']:self.assertIn(secret,values)
 def test_nested_validation_messages_never_copy_reflected_inputs(self):
  body={'detail':[{'loc':['body','headers'],'msg':'Extra inputs are not permitted','type':'extra_forbidden','input':{'Authorization':'secret'}}]}
  summary=auto.provider_summary(body);self.assertEqual(summary,'Extra inputs are not permitted');self.assertNotIn('secret',summary)
 def test_a_dropped_connection_is_retried_for_reads_but_never_repeats_a_change(self):
  import io,socket,urllib.error
  class Reply(io.BytesIO):
   def __enter__(self):return self
   def __exit__(self,*a):return False
  def opener(failures):
   calls=[]
   class Opener:
    def open(self,req,timeout):
     calls.append(req.get_method())
     if len(calls)<=len(failures):raise failures[len(calls)-1]
     return Reply(b'{"ok":true}')
   return Opener(),calls
  def run(method,failures):
   fake,calls=opener(failures)
   with patch.object(auto.urllib.request,'build_opener',return_value=fake),patch.object(auto.MistralAPI,'pause',staticmethod(lambda delay:None)):
    try:return auto.MistralAPI('fixture-api-account-secret').call(method,'/connectors/test',{} if method!='GET' else None),calls
    except auto.SetupError as error:return error,calls
  reset=urllib.error.URLError(ConnectionResetError());gateway=lambda:urllib.error.HTTPError('https://api.mistral.ai/v1/connectors/test',503,'x',{},None)
  result,calls=run('GET',[reset,TimeoutError()]);self.assertEqual((result,len(calls)),({'ok':True},3))
  result,calls=run('GET',[gateway(),gateway()]);self.assertEqual((result,len(calls)),({'ok':True},3))
  result,calls=run('GET',[reset,reset,reset]);self.assertEqual((result.code,len(calls)),('network',3))
  result,calls=run('GET',[auto.http.client.IncompleteRead(b'')]);self.assertEqual((result,len(calls)),({'ok':True},2))
  # A change that may have reached Mistral is never sent twice.
  result,calls=run('POST',[reset]);self.assertEqual((result.code,len(calls)),('network',1))
  result,calls=run('POST',[gateway()]);self.assertEqual(len(calls),1)
  # No address or no connection: it certainly never arrived.
  result,calls=run('POST',[urllib.error.URLError(socket.gaierror()),urllib.error.URLError(ConnectionRefusedError())]);self.assertEqual((result,len(calls)),({'ok':True},3))
 def test_redirects_and_provider_secret_bodies_do_not_reach_the_ui(self):
  import urllib.error
  class Opener:
   def open(self,req,timeout):
    assert req.full_url=='https://api.mistral.ai/v1/connectors/test'
    raise urllib.error.HTTPError(req.full_url,403,'fixture-api-account-secret',{},None)
  with patch.object(auto.urllib.request,'build_opener',return_value=Opener()):
   with self.assertRaises(auto.SetupError) as error:auto.MistralAPI('fixture-api-account-secret').call('GET','/connectors/test')
  self.assertNotIn('fixture-api-account-secret',str(error.exception))

if __name__=='__main__':unittest.main()
