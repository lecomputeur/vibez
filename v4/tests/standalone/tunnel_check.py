#!/usr/bin/python3
"""Temporary authenticated HTTPS test with invented data only; no Mistral login."""
import hashlib,importlib.util,json,tempfile,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('webcheck',ROOT/'backend/web_connector.py');web=importlib.util.module_from_spec(spec);spec.loader.exec_module(web)
report={'live_mistral':False,'fixture_files_only':True,'tunnel_stopped':False}
with tempfile.TemporaryDirectory(prefix='vibez4-connector-https-') as tmp:
 folder=Path(tmp)/'Proefproject';folder.mkdir();(folder/'proef.txt').write_text('Dit is uitsluitend een verzonnen proefbestand.')
 c=web.Connector(lambda e:None,Path(tmp)/'private');key='cace260d-d95d-4859-b45b-f56f185f15da'
 try:
  c.select({'id':key,'name':'Verzonnen proefproject'});c.link(key,folder);c.enable(key,True);c.start_tunnel()
  deadline=time.monotonic()+50
  while c.tunnel_status=='starting' and time.monotonic()<deadline:time.sleep(.2)
  if c.tunnel_status!='running':raise RuntimeError('De tijdelijke HTTPS-verbinding kon niet worden gestart')
  endpoint=c.tunnel_url+'/mcp/'+key
  print('Tijdelijk proefadres: '+c.tunnel_url,flush=True)
  time.sleep(3)
  def request(msg,token=True,sid=None):
   headers={'Accept':'application/json, text/event-stream','Content-Type':'application/json'}
   if token:headers['Authorization']='Bearer '+c.projects[key]['token']
   if sid:headers['Mcp-Session-Id']=sid
   req=urllib.request.Request(endpoint,data=json.dumps(msg).encode(),headers=headers)
   for attempt in range(10):
    try:
     r=urllib.request.urlopen(req,timeout=12);break
    except urllib.error.HTTPError as e:
     r=e;break
    except urllib.error.URLError:
     if attempt==9:raise
     time.sleep(2)
   with r:
    raw=r.read();return r.code,r.headers,json.loads(raw) if raw else None
  init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'VibeZ-proef','version':'1'}}}
  code,h,d=request(init,False);assert code==401;report['unauthorized_rejected']=True
  code,h,d=request(init);assert code==200;sid=h['Mcp-Session-Id'];report['https_handshake']=True
  code,h,d=request({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'read_file','arguments':{'path':'proef.txt'}}},sid=sid)
  assert code==200 and not d['result']['isError'] and 'verzonnen proefbestand' in d['result']['content'][0]['text'];report['https_fixture_read']=True
  report['passed']=True
 finally:
  c.close();report['tunnel_stopped']=c.tunnel is None and c.server is None
  (ROOT/'artifacts'/('connector-https-'+web.VERSION+'.json')).write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report),flush=True)
