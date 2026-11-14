"""In-memory Mistral API fixture, using documented request/response shapes.
Tool discovery connects to the actual local HTTP MCP server, not fake files.
"""
import copy,json,re,uuid,urllib.request
class Service:
 def __init__(self,error,web=None):self.error=error;self.web=web;self.connectors={};self.credentials={};self.calls=[];self.active=set();self.fail=None;self.hook=None;self.patch_upsert=False;self.expected_server=None;self.expected_token=None
 def api(self,key):return self
 def call(self,method,path,data=None):
  self.calls.append((method,path,copy.deepcopy(data)))
  if self.hook:self.hook(method,path,data)
  if self.fail:
   status=self.fail;self.fail=None;raise self.error('permission' if status==403 else 'network','Gecontroleerde fout',status)
  parts=path.split('?')[0].strip('/').split('/')
  def public(connector):
   value=copy.deepcopy(connector);value['active']=connector['id'] in self.active;value['is_authenticated']=connector['id'] in self.credentials;return value
  if parts==['connectors'] and method=='GET':
   from urllib.parse import parse_qs,urlsplit
   query=parse_qs(urlsplit(path).query);start=int(query.get('cursor',['0'])[0]);page_size=int(query.get('page_size',['100'])[0]);rows=sorted(self.connectors.values(),key=lambda c:c['id']);end=start+page_size
   return {'items':[public(c) for c in rows[start:end]],'pagination':{'page_size':page_size,'next_cursor':str(end) if end<len(rows) else None}}
  if parts==['connectors'] and method=='POST':
   if 'auth_methods' in data and any(field in data for field in ['headers','auth_data','oauth2_server_metadata','oauth2_server_metadata_url']):raise self.error('invalid_request','Value error, Use either auth_methods or top-level authentication fields, not both.',422)
   authorization=data.get('headers',{}).get('Authorization','')
   if not authorization.startswith('Bearer '):raise self.error('bootstrap_auth','MCP requires authentication during connector creation',400)
   if self.web is not None:self.discover(data['server'].rsplit('/',1)[1],authorization[7:])
   if any(v['name']==data['name'] for v in self.connectors.values()):raise self.error('conflict','Already exists',409)
   v={**data,'supported_auth_methods':[{'method_type':'none','headers':[{'name':'Authorization','is_required':True}]}],'id':str(uuid.uuid4()),'owner_type':'user','owner_id':'fixture-user','creator_id':'fixture-user','mistral':False};self.connectors[v['id']]=v
   return copy.deepcopy(v)
  connector=next((c for c in self.connectors.values() if parts[1] in (c['id'],c['name'])),None)
  if not connector:raise self.error('not_found','Not found',404)
  cid=connector['id']
  if len(parts)==2:
   if method=='GET':return public(connector)
   if method=='DELETE':
    del self.connectors[cid];self.active.discard(cid);self.credentials.pop(cid,None);return {}
   if method=='PATCH':
    if 'auth_methods' in data:
     requested=data['auth_methods'][0]
     previous=next((m for m in connector.get('supported_auth_methods',[]) if m.get('method_type')==requested['method_type']),{})
     method={**copy.deepcopy(previous),**copy.deepcopy(requested)}
     names=[h['name'].lower() for h in (method.get('headers') or [])]+[n.lower() for n in (method.get('global_headers') or {})]
     if len(names)!=len(set(names)):raise self.error('invalid_request',"Duplicate header name 'Authorization'; header names must be unique across 'headers' and 'global_headers'.",400)
     authorization=method.get('global_headers',{}).get('Authorization',{}).get('value','')
     if not authorization.startswith('Bearer '):raise self.error('bootstrap_auth','Updated server requires authenticated discovery',400)
     if self.web is not None:self.discover(data['server'].rsplit('/',1)[1],authorization[7:])
     connector['supported_auth_methods']=[method]
    connector.update(data);return copy.deepcopy(connector)
  if parts[2:]==['authentication_methods'] and method=='GET':
   methods=copy.deepcopy(connector['supported_auth_methods'])
   for m in methods:
    for h in m.get('global_headers',{}).values():h['value']='[REDACTED]'
   return methods
  if parts[2:]==['user','credentials'] and method in ('POST','PATCH'):
   if not re.fullmatch('[A-Za-z0-9-]+',data['name']):raise self.error('invalid_request','Invalid credential name',400)
   if data.get('credentials')!={'headers':{}}:raise self.error('sign_in','Invalid credentials provided',401)
   authorization=connector['supported_auth_methods'][0].get('global_headers',{}).get('Authorization',{}).get('value','')
   if (self.expected_server is not None and connector['server']!=self.expected_server) or (self.expected_token is not None and authorization!='Bearer '+self.expected_token):raise self.error('sign_in','Invalid credentials provided',401)
   exists=cid in self.credentials and self.credentials[cid]['name']==data['name']
   if method=='PATCH' and not exists and not self.patch_upsert:raise self.error('not_found','No credentials with name vibez-local found for consumer',404)
   if method=='POST' and exists:raise self.error('conflict','Credentials already exist',409)
   self.credentials[cid]=data;return {'message':'ok'}
  if parts[2:]==['user','activate'] and method=='POST':self.active.add(cid);return {'message':'ok'}
  if parts[2:]==['user','deactivate'] and method=='POST':self.active.discard(cid);return {'message':'ok'}
  if parts[2:]==['tools'] and method=='GET':
   if self.web is None:return [{'name':n} for n in ['read_file','write_file','create_document','list_directory','workspace_overview','change_status']]
   assert cid in self.active and cid in self.credentials
   return self.discover(connector['server'].rsplit('/',1)[1],connector['supported_auth_methods'][0]['global_headers']['Authorization']['value'][7:])
  if parts[2:]==['tools','workspace_overview','call'] and method=='POST':
   assert data=={'arguments':{}} and cid in self.active and cid in self.credentials
   if self.web is not None:
    result=self.discover(connector['server'].rsplit('/',1)[1],connector['supported_auth_methods'][0]['global_headers']['Authorization']['value'][7:],overview=True)
    return {'content':result['content'],'metadata':{'mcp_meta':{'isError':result.get('isError',False)}}}
   return {'content':[{'type':'text','text':json.dumps({'files':1,'directories':0,'bytes':12,'source':'Local MCP server · VibeZ workspace'})}],'metadata':{'mcp_meta':{'isError':False}}}
  raise AssertionError((method,path))

 def discover(self,project,token,overview=False):
  local='http://127.0.0.1:'+str(self.web.server.server_port)+'/mcp/'+project
  headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
  def rpc(method,params):
   req=urllib.request.Request(local,data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),headers=headers)
   with urllib.request.urlopen(req,timeout=4) as r:
    if r.headers.get('Mcp-Session-Id'):headers['Mcp-Session-Id']=r.headers['Mcp-Session-Id']
    return json.load(r)['result']
  rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{}})
  if overview:return rpc('tools/call',{'name':'workspace_overview','arguments':{}})
  return rpc('tools/list',{})['tools']
