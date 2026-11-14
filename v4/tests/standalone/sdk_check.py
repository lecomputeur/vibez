#!/usr/bin/python3
"""Official MCP client against a temporary fixture, locally and through HTTPS."""
import asyncio,importlib.metadata,importlib.util,json,logging,tempfile,time,threading,socket,urllib.request,urllib.parse
from datetime import timedelta
from pathlib import Path
import httpx
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('sdk_web',ROOT/'backend/web_connector.py');web=importlib.util.module_from_spec(spec);spec.loader.exec_module(web)
logging.disable(logging.CRITICAL)
spec=importlib.util.spec_from_file_location('sdk_automatic',ROOT/'backend/automatic_connector.py');automatic=importlib.util.module_from_spec(spec);spec.loader.exec_module(automatic)
report={'sdk':importlib.metadata.version('mcp'),'fixture_only':True,'live_mistral':False}
async def check(url,token,pinned=False):
 factory=create_mcp_http_client
 if pinned:
  host=urllib.parse.urlsplit(url).hostname;address=automatic.public_addresses(host)[0]
  class PublicTransport(httpx.AsyncHTTPTransport):
   async def handle_async_request(self,request):
    if request.url.host!=host:raise ValueError('Unexpected test destination')
    request.headers['Host']=host;request.extensions['sni_hostname']=host;request.url=request.url.copy_with(host=address)
    return await super().handle_async_request(request)
  factory=lambda **kwargs:httpx.AsyncClient(transport=PublicTransport(),trust_env=False,**kwargs)
 async with streamablehttp_client(url,httpx_client_factory=factory,headers={'Authorization':'Bearer '+token},timeout=10,sse_read_timeout=10) as (read,write,_):
  async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=10)) as session:
   initialized=await session.initialize();tools=await session.list_tools();result=await session.call_tool('read_file',{'path':'proef.txt'})
   assert not result.isError
   assert any('Verzonnen proeftekst' in getattr(part,'text','') for part in result.content)
   return {'initialized':True,'protocol':initialized.protocolVersion,'tools':[tool.name for tool in tools.tools],'fixture_read':True}
with tempfile.TemporaryDirectory(prefix='vibez-mcp-sdk-') as tmp:
 root=Path(tmp);folder=root/'fixture';folder.mkdir();(folder/'proef.txt').write_text('Verzonnen proeftekst.')
 c=web.Connector(lambda _:None,root/'private');key='cace260d-d95d-4859-b45b-f56f185f15da'
 try:
  c.select({'id':key,'name':'Fixture'});c.link(key,folder);c.enable(key,True);token=c.projects[key]['token']
  report['local']=asyncio.run(check('http://127.0.0.1:'+str(c.server.server_port)+'/mcp/'+key,token))
  c.start_tunnel();deadline=time.monotonic()+50
  while c.tunnel_status=='starting' and time.monotonic()<deadline:time.sleep(.2)
  assert c.tunnel_status=='running'
  started=time.monotonic();hostname=urllib.parse.urlsplit(c.tunnel_url).hostname;report['fixture_hostname']=hostname
  try:automatic.wait_ready(c.tunnel_url+'/mcp/'+key,token,lambda:None,threading.Event())
  except automatic.SetupError as error:
   report['readiness_error']={'code':error.code,'http_status':error.status}
   try:report['system_dns_addresses']=sorted({v[4][0] for v in socket.getaddrinfo(hostname,443)})
   except socket.gaierror as failure:report['system_dns_error']=failure.errno
   for label,base in [('google','https://dns.google/resolve'),('cloudflare','https://cloudflare-dns.com/dns-query')]:
    try:
     request=urllib.request.Request(base+'?'+urllib.parse.urlencode({'name':hostname,'type':'A'}),headers={'Accept':'application/dns-json'})
     with urllib.request.urlopen(request,timeout=8) as response:data=json.load(response)
     report[label+'_dns']={'status':data.get('Status'),'answers':[v.get('data') for v in data.get('Answer',[]) if v.get('type')==1]}
    except Exception as failure:report[label+'_dns_error']=type(failure).__name__
   raise
  finally:report['readiness_wait_seconds']=round(time.monotonic()-started,2)
  failures=[]
  for attempt in range(4):
   try:report['https']=asyncio.run(check(c.tunnel_url+'/mcp/'+key,token,pinned=True));break
   except Exception as exc:
    failures.append(type(exc).__name__)
    if attempt==3:raise
    time.sleep(2)
  report['https_initial_failures']=failures;report['passed']=True
 finally:
  c.close();report['tunnel_stopped']=c.tunnel is None and c.server is None
  (ROOT/'artifacts'/('sdk-readiness-check-'+web.VERSION+'.json')).write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report),flush=True)
