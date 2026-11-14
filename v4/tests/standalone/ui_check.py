#!/usr/bin/python3
import importlib.util,json,tempfile,time
from pathlib import Path
from screen_policy import safe_screen
import gi
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,GLib
BASE=Path(__file__).resolve().parents[2];VERSION=json.loads((BASE/'desktop/src-tauri/tauri.conf.json').read_text())['version'];OUT=BASE/'artifacts'/('standalone-ui-'+VERSION);OUT.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('ui_app',BASE/'backend/standalone_engine.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
temp=tempfile.TemporaryDirectory(prefix='vibez4-standalone-ui-');root=Path(temp.name);folder=root/'CityTripXL';folder.mkdir();(folder/'tekst.txt').write_text('Originele tekst.\n')
step=0;events=[];errors=[];checks=[];phase='start';ready=False;started=time.monotonic()
def call(name,args):return {'role':'assistant','content':'','tool_calls':[{'id':'c'+str(step),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
def provider(messages,tools):
 global step
 step+=1
 if step==1:return {'role':'assistant','content':'Hier is een gewoon chatantwoord.\n\n**Duidelijk** en veilig: <img src=x onerror=alert(1)>\n\n```python\nprint("Hallo")\n```'}
 if step==2:return call('read_file',{'path':'tekst.txt'})
 if step==3:return call('write_file',{'path':'tekst.txt','content':'Verbeterde tekst.\n'})
 return {'role':'assistant','content':'Ik heb het bestand na je goedkeuring bijgewerkt. Alles staat in hetzelfde gesprek.'}
manager=WebKit2.UserContentManager();manager.register_script_message_handler('native')
shim="""window.__nativeSeq=0;window.__nativePending=new Map();window.__TAURI__={core:{invoke:(name,args)=>new Promise((resolve,reject)=>{const id=++window.__nativeSeq;window.__nativePending.set(id,{resolve,reject});window.webkit.messageHandlers.native.postMessage(JSON.stringify({id,name,args}));})},event:{listen:async(name,fn)=>{window.__appListeners=window.__appListeners||[];window.__appListeners.push(fn);window.__appListener=e=>window.__appListeners.forEach(f=>f(e));}}};window.__nativeReply=(id,value,error)=>{const p=window.__nativePending.get(id);window.__nativePending.delete(id);if(p)(error?p.reject(error):p.resolve(value));};"""
manager.add_script(WebKit2.UserScript.new(shim,WebKit2.UserContentInjectedFrames.TOP_FRAME,WebKit2.UserScriptInjectionTime.START,None,None))
view=WebKit2.WebView(user_content_manager=manager);sx,sy,sw,sh=safe_screen();window=Gtk.Window(title='VibeZ 4 Test · Zelfstandige UI-controle');window.set_default_size(1280,860);window.set_focus_on_map(False);window.set_position(Gtk.WindowPosition.NONE);window.move(sx+40,sy+40);window.add(view)
def evaluate(script,callback=None):
 def done(widget,result,_):
  try:
   value=widget.evaluate_javascript_finish(result)
   if callback:callback(value.to_string())
  except Exception as exc:errors.append(str(exc))
 view.evaluate_javascript(script,-1,None,None,None,done,None)
def emit(event):
 events.append(event)
 GLib.idle_add(lambda:(evaluate('window.__appListener?.({payload:'+json.dumps(event)+'})'),False)[1])
e=module.StandaloneEngine(emit,root/'data',provider=provider);e.key='fixture-secret-not-in-ui';e.state()
def native(_,result):
 global ready
 req=json.loads(result.get_js_value().to_string());value=None;error=None
 try:
  name=req['name'];args=req.get('args') or {}
  if name=='app_command':e.dispatch(args['payload'])
  elif name=='web_command':e.dispatch(args['payload'])
  elif name=='app_info':
   ready=True;value={'version':VERSION,'screen':'Scherm 1','standalone':True}
  elif name=='app_choose_folder':value=str(folder)
  elif name=='app_copy':value=True
  elif name=='app_save_export':
   checks.append({'name':'Export contains ordinary chat and file answer','passed':'gewoon chatantwoord' in args['text'] and 'het bestand' in args['text']});value=True
  else:raise ValueError(name)
 except Exception as exc:error=str(exc);errors.append(error)
 evaluate('window.__nativeReply('+str(req['id'])+','+json.dumps(value)+','+json.dumps(error)+')')
manager.connect('script-message-received::native',native)
def screenshot(name):
 def done(widget,result,_):
  try:widget.get_snapshot_finish(result).write_to_png(str(OUT/name))
  except Exception as exc:errors.append(str(exc))
 view.get_snapshot(WebKit2.SnapshotRegion.VISIBLE,WebKit2.SnapshotOptions.NONE,None,done,None)
def check(name,passed):
 checks.append({'name':name,'passed':bool(passed)})
 if not passed:errors.append(name)
def finish():
 e.close();result={'passed':not errors,'checks':checks,'errors':errors,'live_mistral':False,'real_mcp':True,'safe_screen':[sx,sy,sw,sh],'seconds':round(time.monotonic()-started,2)};(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True);window.destroy();Gtk.main_quit();return False
def final_report(raw):
 d=json.loads(raw);check('One visible conversation contains chat and files',d['users']==2 and d['answers']==2);check('Model HTML is inert',not d['unsafe']);check('Code block with copy action is rendered',d['code']==1);check('Project name is readable',d['name']=='CityTripXL');check('Approved result visible',d['approved']);check('No credential in UI',not d['credential']);screenshot('conversation.png');evaluate("$('export').click()");GLib.timeout_add(600,finish)
def tick():
 global phase
 if errors or time.monotonic()-started>25:
  if not errors:errors.append('Timeout in '+phase)
  return finish()
 if phase=='start' and e.key and ready:
  evaluate("$('new-project').click();$('project-name-input').value='CityTripXL';$('project-form').requestSubmit();");phase='project'
 elif phase=='project' and e.project['name']=='CityTripXL':
  screenshot('welcome.png');evaluate("$('prompt').value='Een gewone chatvraag';$('composer').requestSubmit();");phase='chat'
 elif phase=='chat' and not e.running and step==1:
  evaluate("$('folder-button').click()");phase='folder'
 elif phase=='folder' and e.workspace:
  check('First folder keeps earlier chat context',any(m.get('content')=='Een gewone chatvraag' for m in e.messages));evaluate("$('prompt').value='Lees tekst.txt en verbeter de tekst';$('composer').requestSubmit();");phase='approval'
 elif phase=='approval' and e.pending:
  check('No write before approval',(folder/'tekst.txt').read_text()=='Originele tekst.\n');screenshot('approval.png');evaluate("document.querySelector('.approval-actions .primary').click()");phase='written'
 elif phase=='written' and not e.running and step==4:
  check('Write after UI approval',(folder/'tekst.txt').read_text()=='Verbeterde tekst.\n');evaluate("JSON.stringify({users:document.querySelectorAll('.message.user').length,answers:document.querySelectorAll('.message.assistant').length,unsafe:!!document.querySelector('#messages img'),code:document.querySelectorAll('.code-block').length,name:$('project-title').textContent,approved:document.querySelector('.approval-result')?.textContent.includes('Opgeslagen'),credential:document.body.innerText.includes('fixture-secret-not-in-ui')})",final_report);phase='finish'
 return True
view.load_uri((BASE/'standalone-ui/index.html').as_uri());window.connect('destroy',lambda *_:Gtk.main_quit());window.show_all();GLib.timeout_add(250,tick);Gtk.main();temp.cleanup();raise SystemExit(1 if errors else 0)
