import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

spec=importlib.util.spec_from_file_location('standalone',Path(__file__).parents[2]/'backend/standalone_engine.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class LocalAppTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='vibez4-test-store-');self.root=Path(self.temp.name);self.data=self.root/'data';self.events=[]
  self.e=app.StandaloneEngine(self.events.append,self.data,provider=lambda m,t:{'role':'assistant','content':'Gewoon chatantwoord.'})
  self.e.key='fixture-secret-must-not-be-stored';self.e.available_models=['mistral-small-latest']
 def tearDown(self):
  self.e.close();self.temp.cleanup()
 def turn(self,text):
  worker=self.e.start_turn(text);worker.start();worker.join(8);self.assertFalse(worker.is_alive());self.assertFalse(self.e.running)
 def workspace(self,name='project',text='Originele tekst'):
  folder=self.root/name;folder.mkdir(exist_ok=True);(folder/'tekst.txt').write_text(text);self.e.dispatch({'action':'workspace','path':str(folder)});return folder
 def test_normal_chat_and_first_folder_keep_one_conversation(self):
  chat=self.e.chat_id;self.turn('Mijn gewone vraag');self.workspace()
  self.assertEqual(self.e.chat_id,chat);self.assertTrue(any(m.get('content')=='Mijn gewone vraag' for m in self.e.messages));self.assertTrue(self.e.tools())
 def test_real_mcp_read_approve_write_and_followup_survive_restart(self):
  folder=self.workspace();step=0
  def call(name,args):return {'role':'assistant','content':'','tool_calls':[{'id':str(step),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
  def provider(messages,tools):
   nonlocal step
   step+=1
   if step==1:return call('read_file',{'path':'tekst.txt'})
   if step==2:return call('write_file',{'path':'tekst.txt','content':'Verbeterde tekst'})
   return {'role':'assistant','content':'Ik heb de tekst verbeterd.'}
  def output(event):
   self.events.append(event)
   if event['type']=='approval':self.e.dispatch({'action':'approve','id':event['id'],'allow':True})
  self.e.external_output=output;self.e.provider=provider;self.turn('Verbeter mijn tekst')
  chat=self.e.chat_id;self.assertEqual((folder/'tekst.txt').read_text(),'Verbeterde tekst');self.e.close()
  events=[];self.e=app.StandaloneEngine(events.append,self.data)
  self.assertEqual(self.e.chat_id,chat);self.assertFalse(self.e.key);self.assertEqual(self.e.workspace.root,str(folder));self.assertTrue(any(m.get('name')=='read_file' for m in self.e.messages))
  self.assertTrue(any(e['type']=='approval_history' for e in events));self.assertFalse(any(e['type']=='approval' for e in events));self.assertEqual(self.e.pending,{})
  with self.assertRaises(ValueError):self.e.mcp.tool('write_file',{'path':'tekst.txt','content':'Moet eerst opnieuw lezen'})
  self.e.key='fixture-secret-must-not-be-stored'
  def followup(messages,tools):
   self.assertTrue(any(m.get('name')=='read_file' for m in messages));return {'role':'assistant','content':'Ik herinner me de bestandsactie.'}
  self.e.provider=followup;self.turn('Wat heb je gewijzigd?')
  self.assertNotIn(b'fixture-secret-must-not-be-stored',(self.data/'conversations.sqlite3').read_bytes())
 def test_project_roots_and_histories_are_separate(self):
  self.e.dispatch({'action':'new_project','name':'Alpha'});a=self.e.project['id'];chat_a=self.e.chat_id;fa=self.workspace('a','Alleen A');self.turn('Vraag A')
  self.e.dispatch({'action':'new_project','name':'Beta'});b=self.e.project['id'];fb=self.workspace('b','Alleen B');self.turn('Vraag B')
  self.e.dispatch({'action':'select_project','id':a});self.assertEqual(self.e.chat_id,chat_a);self.assertEqual(self.e.workspace.root,str(fa));self.assertEqual(self.e.mcp.tool('read_file',{'path':'tekst.txt'})['content'],'Alleen A');self.assertFalse(any(m.get('content')=='Vraag B' for m in self.e.messages))
  self.e.dispatch({'action':'select_project','id':b});self.assertEqual(self.e.workspace.root,str(fb));self.assertFalse(any(m.get('content')=='Vraag A' for m in self.e.messages))
 def test_changing_root_preserves_old_chat_in_history(self):
  fa=self.workspace('a');self.turn('Vraag over A');old=self.e.chat_id;self.workspace('b');self.assertNotEqual(self.e.chat_id,old);self.assertEqual(len(self.e.messages),1);self.assertTrue(any(m.get('content')=='Vraag over A' for m in self.e.store.chat(old)['context']))
 def test_reopening_history_cannot_use_old_context_against_new_project_root(self):
  self.workspace('a');self.turn('Vraag over de oude bestanden');old=self.e.chat_id;self.workspace('b');self.e.dispatch({'action':'select_chat','id':old});self.assertIsNone(self.e.workspace);self.assertEqual(self.e.tools(),[])
 def test_unlink_also_revokes_file_tools_when_old_history_is_opened(self):
  self.workspace();self.turn('Bestandsvraag');old=self.e.chat_id;self.e.dispatch({'action':'clear_workspace'});self.e.dispatch({'action':'select_chat','id':old});self.assertIsNone(self.e.workspace);self.assertEqual(self.e.tools(),[])
 def test_unlink_revokes_mcp_and_starts_clean_chat(self):
  self.workspace();self.turn('Bestandsvraag');old=self.e.chat_id;self.e.dispatch({'action':'clear_workspace'});self.assertIsNone(self.e.mcp);self.assertIsNone(self.e.workspace);self.assertNotEqual(old,self.e.chat_id);self.assertEqual(self.e.tools(),[])
 def test_export_is_local_and_does_not_claim_web_sync(self):
  self.turn('Bewaar mijn gewone vraag');self.e.dispatch({'action':'export'});export=next(e for e in self.events if e['type']=='export');self.assertIn('Bewaar mijn gewone vraag',export['text']);self.assertIn('Gewoon chatantwoord',export['text']);self.e.state();self.assertFalse(self.events[-1]['sync_available'])
 def test_streaming_text_and_split_tool_call_arguments(self):
  chunks=[{'choices':[{'delta':{'content':'Hallo '}}]},{'choices':[{'delta':{'content':'wereld'}}]},{'choices':[{'delta':{'tool_calls':[{'index':0,'id':'c1','function':{'name':'read_file','arguments':'{"path":'}}]}}]},{'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'arguments':'"tekst.txt"}'}}]}}]}]
  stream=io.BytesIO(b''.join(b'data: '+json.dumps(c).encode()+b'\n\n' for c in chunks)+b'data: [DONE]\n\n');self.e.cancelled.clear();reply=self.e.read_stream(stream);self.assertEqual(reply['content'],'Hallo wereld');self.assertEqual(json.loads(reply['tool_calls'][0]['function']['arguments']),{'path':'tekst.txt'});self.assertEqual(''.join(e['text'] for e in self.events if e['type']=='assistant_delta'),'Hallo wereld')
 def test_latest_project_transition_cancels_old_model_reply(self):
  self.e.dispatch({'action':'new_project','name':'A'});a=self.e.project['id'];self.e.dispatch({'action':'new_project','name':'B'});b=self.e.project['id'];self.e.dispatch({'action':'select_project','id':a});entered=threading.Event();release=threading.Event()
  def provider(*args):entered.set();release.wait(5);return {'role':'assistant','content':'Oude A-inhoud'}
  self.e.provider=provider;worker=self.e.start_turn('Vraag A');worker.start();self.assertTrue(entered.wait(3));self.e.dispatch({'action':'select_project','id':b})
  with self.assertRaises(ValueError):self.e.dispatch({'action':'chat','text':'Te vroeg'})
  release.set();worker.join(5);self.assertEqual(self.e.project['id'],b);self.assertFalse(any(m.get('content')=='Oude A-inhoud' for m in self.e.messages))
 def test_legacy_folder_associations_import_once_without_modification(self):
  self.e.close();legacy=self.root/'project-folders.json';legacy.write_text(json.dumps({'folders':{'old-id':str(self.root/'CityTripXL')}}));before=legacy.read_bytes();other=self.root/'migrated';self.e=app.StandaloneEngine(self.events.append,other,legacy=legacy);projects,_=self.e.store.library();self.assertTrue(any(p['id']=='old-id' and p['name']=='CityTripXL' for p in projects));self.assertEqual(legacy.read_bytes(),before);self.e.close();self.e=app.StandaloneEngine(self.events.append,other,legacy=legacy);self.assertEqual(sum(p['id']=='old-id' for p in self.e.store.library()[0]),1)
 def test_database_and_directory_are_private(self):
  self.assertEqual(self.data.stat().st_mode&0o777,0o700);self.assertEqual((self.data/'conversations.sqlite3').stat().st_mode&0o777,0o600)
 def test_project_goal_command_confirms_actual_local_save_and_rejects_stale_project(self):
  a='aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa';b='bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb'
  self.e.web.select({'id':a,'name':'Fixture'})
  self.e.dispatch({'action':'web_goal','project_id':a,'goal':'  Plan een korte reis  ','request_id':'fixture-save'})
  result=[event for event in self.events if event['type']=='web_goal_result'][-1]
  self.assertEqual(result,{'type':'web_goal_result','project_id':a,'request_id':'fixture-save','goal':'Plan een korte reis'})
  self.assertEqual(self.e.web.snapshot()['project_goal'],'Plan een korte reis');self.assertEqual(self.e.web.projects,{})
  self.e.web.select({'id':b,'name':'Fixture'})
  self.e.dispatch({'action':'web_goal','project_id':a,'goal':'Verkeerd project','request_id':'stale-save'})
  result=[event for event in self.events if event['type']=='web_goal_result'][-1]
  self.assertIn('error',result);self.assertEqual(result['request_id'],'stale-save');self.assertNotIn('goal',result)
  self.assertEqual(self.e.web.snapshot()['project_goal'],'');self.e.web.select({'id':a,'name':'Fixture'});self.assertEqual(self.e.web.snapshot()['project_goal'],'Plan een korte reis')

if __name__=='__main__':unittest.main()
