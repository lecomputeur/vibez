"""Offline WebKit diagnostic only, run if actual application paste regression fails."""
import gi,time,json
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2

def pause(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.02)
window=Gtk.Window();window.set_default_size(420,200)
view=WebKit2.WebView();window.add(view);window.show_all()
view.connect('permission-request',lambda _,req: print('STANDALONE_PERMISSION:',type(req).__name__,flush=True) or False)
def js(script):
    result=[]
    def done(v,res,_):
        try:result.append(v.run_javascript_finish(res).get_js_value().to_string())
        except Exception as e:result.append(str(e))
    view.run_javascript(script,None,done,None)
    end=time.monotonic()+3
    while not result and time.monotonic()<end:pause(.03)
    return result
for enable in [False,True]:
    view.get_settings().set_property('javascript-can-access-clipboard',enable)
    view.load_html('<textarea id="editor" style="width:380px;height:100px"></textarea><script>window.result=null;editor.addEventListener("paste",e=>{e.preventDefault();window.result={trusted:e.isTrusted,types:[...e.clipboardData.types],items:[...e.clipboardData.items].map(i=>({kind:i.kind,type:i.type})),files:[...e.clipboardData.files].map(f=>({size:f.size,type:f.type})),uri:e.clipboardData.getData("text/uri-list")};});</script>','https://paste-test.invalid/')
    pause(.7);view.grab_focus();js('editor.focus();true');pause(.2)
    view.execute_editing_command('Paste');pause(.5)
    print('STANDALONE_PASTE:',enable,js('JSON.stringify(window.result)'),flush=True)
window.destroy()
