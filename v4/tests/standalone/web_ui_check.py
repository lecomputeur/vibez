#!/usr/bin/python3
"""Inspect the real local connector UI on screen 1, without publishing a folder."""
import json, tempfile, time
from pathlib import Path
from screen_policy import safe_screen
import gi
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,GLib
BASE=Path(__file__).resolve().parents[2];OUT=BASE/'artifacts/connector-ui-test7';OUT.mkdir(exist_ok=True)
errors=[];start=time.monotonic();phase=0
manager=WebKit2.UserContentManager()
shim="""window.__TAURI__={core:{invoke:async(name,args)=>{if(name==='app_info')return {version:'4.0.0-test.7',screen:'Scherm 1'};return null;}},event:{listen:async()=>{}}};"""
manager.add_script(WebKit2.UserScript.new(shim,WebKit2.UserContentInjectedFrames.TOP_FRAME,WebKit2.UserScriptInjectionTime.START,None,None))
view=WebKit2.WebView(user_content_manager=manager);x,y,w,h=safe_screen();window=Gtk.Window(title='VibeZ 4 Test · Projectkoppeling controleren');window.set_default_size(1280,860);window.set_focus_on_map(False);window.set_position(Gtk.WindowPosition.NONE);window.move(x+40,y+40);window.add(view)
def evaluate(script,callback=None):
 def done(v,r,_):
  try:
   val=v.evaluate_javascript_finish(r)
   if callback:callback(val.to_string())
  except Exception as e:errors.append(str(e))
 view.evaluate_javascript(script,-1,None,None,None,done,None)
def snapshot():
 def done(v,r,_):
  try:v.get_snapshot_finish(r).write_to_png(str(OUT/'project-connector.png'))
  except Exception as e:errors.append(str(e))
 view.get_snapshot(WebKit2.SnapshotRegion.VISIBLE,WebKit2.SnapshotOptions.NONE,None,done,None)
def finish():
 (OUT/'result.json').write_text(json.dumps({'passed':not errors,'errors':errors,'safe_screen':[x,y,w,h],'fixture_ui':True,'live_mistral':False},indent=2)+'\n');window.destroy();Gtk.main_quit();return False
def check(raw):
 d=json.loads(raw)
 for k,v in d.items():
  if not v:errors.append(k)
 snapshot();GLib.timeout_add(500,finish)
def loaded(v,e):
 if e!=WebKit2.LoadEvent.FINISHED:return
 data={'project':{'id':'cace260d-d95d-4859-b45b-f56f185f15da','name':'CityTripXL'},'folder':'/voorbeelden/CityTripXL','enabled':True,'url':'https://voorbeeld.trycloudflare.com/mcp/project','token':'alleen-een-verzonnen-proefsleutel','tunnel_status':'running','pending':[{'id':'fixture','project_name':'CityTripXL','path':'README.md','before':'Beschrijving van CityTripXL.','after':'CityTripXL helpt je een stedentrip te plannen.'}],'activity':[{'project':'CityTripXL','action':'read_file','path':'README.md'}]}
 evaluate("webMode(true).then(()=>renderWeb("+json.dumps(data)+"));true")
 GLib.timeout_add(900,lambda:(evaluate("JSON.stringify({name:$('web-project-name').textContent==='CityTripXL',setup:!$('web-setup').hidden,tokenHidden:$('web-token').type==='password',proposal:document.querySelectorAll('#web-proposals .approval').length===1,noUnsafeHTML:!document.querySelector('#web-proposals img'),panelWidth:$('web-panel').getBoundingClientRect().width===390})",check),False)[1])
view.connect('load-changed',loaded);view.load_uri((BASE/'standalone-ui/index.html').as_uri());window.show_all();GLib.timeout_add_seconds(15,lambda:(errors.append('UI timeout'),finish())[1]);Gtk.main();print(json.dumps({'passed':not errors,'errors':errors}));raise SystemExit(bool(errors))
