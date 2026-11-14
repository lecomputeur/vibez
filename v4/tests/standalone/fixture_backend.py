#!/usr/bin/python3
"""Only used by the separately compiled native test binary and temporary profile."""
import importlib.util,json,signal,sys,threading
from pathlib import Path
source=Path(sys.argv[sys.argv.index('--engine-source')+1]);directory=sys.argv[sys.argv.index('--data-dir')+1]
spec=importlib.util.spec_from_file_location('native_app_fixture',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
lock=threading.Lock()
def output(event):
 with lock:print(json.dumps(event),flush=True)
def call(name,args):return {'role':'assistant','content':'','tool_calls':[{'id':'fixture-'+name,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
def provider(messages,tools):
 last=messages[-1]
 if last['role']=='tool':
  if last.get('name')=='read_file':return call('write_file',{'path':'tekst.txt','content':'Verbeterde tekst van VibeZ.\n'})
  return {'role':'assistant','content':'Het bestand is na jouw goedkeuring bijgewerkt.'}
 if 'Lees' in last.get('content',''):return call('read_file',{'path':'tekst.txt'})
 if 'Herinner' in last.get('content',''):
  assert any(m.get('name')=='read_file' for m in messages)
  assert any(m.get('content')=='Een gewone chatvraag' for m in messages)
  return {'role':'assistant','content':'Ik herinner de gewone chat én de bestandsactie in hetzelfde gesprek.'}
 return {'role':'assistant','content':'Dit is het antwoord op je gewone chatvraag.'}
e=module.StandaloneEngine(output,directory,provider=provider)
service_spec=importlib.util.spec_from_file_location('native_connector_service',Path(__file__).with_name('connector_service_fixture.py'));service_module=importlib.util.module_from_spec(service_spec);service_spec.loader.exec_module(service_module);Service=service_module.Service
service=Service(e.automatic.registry.configure.__globals__['SetupError'],web=e.web)
e.automatic.api_factory=service.api
e.automatic.probe=lambda server,token,guard,cancel:(guard(),service.discover(server.rsplit("/",1)[1],token),guard())
def fixture_tunnel():
 e.web.tunnel_status='running';e.web.tunnel_url='https://fixture.trycloudflare.com';e.web.state()
e.web.start_tunnel=fixture_tunnel
e.key='fixture-account-secret-never-shown';e.available_models=['mistral-small-latest'];e.state()
def stop(*_):e.close();raise SystemExit()
signal.signal(signal.SIGTERM,stop)
try:
 for line in sys.stdin:
  try:
   value=json.loads(line)
   if value.get('action')=='shutdown':break
   if value.get('action')=='fixture_web_make':
    def peer():
     import urllib.request
     key=e.web.active['id'];url='http://127.0.0.1:'+str(e.web.server.server_port)+'/mcp/'+key;sid=None
     def call(method,params):
      nonlocal sid
      headers={'Authorization':'Bearer '+e.web.projects[key]['token'],'Accept':'application/json, text/event-stream','Content-Type':'application/json'}
      if sid:headers['Mcp-Session-Id']=sid
      req=urllib.request.Request(url,data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),headers=headers)
      with urllib.request.urlopen(req,timeout=25) as r:
       sid=r.headers.get('Mcp-Session-Id',sid);return json.load(r)['result']
     call('initialize',{'protocolVersion':'2025-06-18','capabilities':{}})
     call('tools/call',{'name':'read_file','arguments':{'path':'tekst.txt'}})
     result=call('tools/call',{'name':'write_file','arguments':{'path':'tekst.txt','content':'Verbeterde tekst van VibeZ.\n'}})
     output({'type':'fixture_saved','written':json.loads(result['content'][0]['text'])['written']})
    threading.Thread(target=peer,daemon=True).start()
   else:e.dispatch(value)
  except Exception as exc:output({'type':'error','message':e.safe_error(exc)})
finally:e.close()
