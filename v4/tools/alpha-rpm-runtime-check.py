#!/usr/bin/python3
"""Check the installed Alpha backend using temporary data and local HTTP only."""
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import sqlite3
import ssl
import subprocess
import sys
import tempfile

RESOURCES=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/usr/lib/VibeZ V4 Alpha/backend')


def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,RESOURCES/filename)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def main():
    web=load('alpha_rpm_runtime_web','web_connector.py')
    imports=load('alpha_rpm_runtime_import','project_import.py')
    engine=load('alpha_rpm_runtime_engine','standalone_engine.py')
    assert web.VERSION=='4.0.0-alpha.3' and engine.VERSION==web.VERSION
    cloudflared=RESOURCES/'vendor/cloudflared-linux-amd64'
    assert hashlib.sha256(cloudflared.read_bytes()).hexdigest()==web.TUNNEL_HASH
    helper_version=subprocess.check_output([str(cloudflared),'--version'],text=True,timeout=10).strip()
    contexts=[{'id':'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa','name':'Temporary project'},
              {'id':'chat-bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb','kind':'conversation','draft':True,
               'conversation_id':None,'name':'New conversation','url':'https://chat.mistral.ai/work'}]
    cases=[]
    with tempfile.TemporaryDirectory(prefix='vibez-alpha-rpm-runtime-') as tmp:
        root=Path(tmp);connector=web.Connector(lambda event:None,root/'settings',approval_wait=0)
        try:
            store=engine.Store(root/'history');assert store.project('default')['id']=='default'
            for index,context in enumerate(contexts):
                folder=root/f'workspace-{index}';folder.mkdir()
                marker=folder/'marker.txt';marker.write_text('Original temporary text.\n')
                connector.select(context);connector.link(context['id'],str(folder))
                state=connector.snapshot();assert state['folder']==str(folder) and len(state['folders'])==1
                revision=state['workspace_binding'];connector.create_folder(context['id'],revision,'Nested')
                assert (folder/'Nested').is_dir()
                source=root/f'import-{index}.txt';source.write_text('A temporary import.\n')
                original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
                copied=imports.copy_files(connector,context['id'],imports.binding(connector),[str(source)])
                assert copied['count']==1 and (folder/source.name).read_bytes()==source.read_bytes()
                assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
                connector.enable(context['id'],True)
                token=connector.projects[context['id']]['token']
                def request(method,params=None,sid=None):
                    connection=http.client.HTTPConnection('127.0.0.1',connector.server.server_port,timeout=10)
                    headers={'Authorization':'Bearer '+token,'Accept':'application/json','Content-Type':'application/json'}
                    if sid:headers['Mcp-Session-Id']=sid
                    message={'jsonrpc':'2.0','id':1,'method':method,'params':params or {}}
                    connection.request('POST','/mcp/'+context['id'],json.dumps(message),headers)
                    response=connection.getresponse();body=response.read();new_sid=response.getheader('Mcp-Session-Id')
                    status=response.status;connection.close();assert status==200,(method,status)
                    return json.loads(body),new_sid
                initialized,sid=request('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'rpm-runtime-test','version':'1'}})
                assert initialized['result']['serverInfo']['version']==web.VERSION and sid
                result,_=request('tools/call',{'name':'read_file','arguments':{'path':'marker.txt'}},sid)
                read=json.loads(result['result']['content'][0]['text']);assert read['content']==marker.read_text()
                result,_=request('tools/call',{'name':'write_file','arguments':{'path':'marker.txt','content':'Approved temporary text.\n'}},sid)
                proposal=json.loads(result['result']['content'][0]['text'])
                assert marker.read_text()=='Original temporary text.\n'
                connector.resolve(proposal['proposal_id'],True)
                assert marker.read_text()=='Approved temporary text.\n'
                result,_=request('tools/call',{'name':'change_status','arguments':{'proposal_id':proposal['proposal_id']}},sid)
                assert json.loads(result['result']['content'][0]['text'])['written'] is True
                cases.append({'context':'project' if index==0 else 'new_conversation','one_root':True,
                              'new_subfolder':True,'import_copy_preserves_source':True,
                              'local_mcp_initialize_and_read':True,'write_waits_for_approval':True,
                              'approved_write_and_status_confirmed':True})
            connector.select(contexts[0]);assert connector.snapshot()['folder']==str(root/'workspace-0')
        finally:connector.close()
    print(json.dumps({'passed':True,'resource_path':str(RESOURCES),'python':sys.version.split()[0],'openssl':ssl.OPENSSL_VERSION,
                      'sqlite':sqlite3.sqlite_version,'cloudflared_version':helper_version,
                      'contexts':cases,'temporary_data_removed':True,'network':'localhost only',
                      'real_account_used':False,'host_files_or_windows_used':False},indent=2))


if __name__=='__main__':main()
