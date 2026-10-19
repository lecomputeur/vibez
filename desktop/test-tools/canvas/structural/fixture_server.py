"""Hermetic HTTPS origins through a private CONNECT proxy, never a forward proxy."""
import http.server
import json
from pathlib import Path
import ssl
import subprocess
import threading
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

HOSTS=('chat.mistral.ai','vibe.mistral.ai','canvas.mistralusercontent.com',
       'challenges.cloudflare.com','accounts.google.com','login.live.com','auth.mistral.ai',
       'frame-a.vibez.test','frame-b.vibez.test')

def case_of(path):
    value=parse_qs(urlsplit(path).query).get('case',[''])[0]
    return value if value and all(c.isalnum() or c=='-' for c in value) and len(value)<80 else None

def content(host,path):
    parsed=urlsplit(path);case=case_of(path)
    if not case:return 404,{},b'Unknown controlled fixture case'
    if parsed.path in ('/main-auth-start','/frame-auth-start'):
        target='main-auth-middle' if parsed.path=='/main-auth-start' else 'frame-auth-middle'
        return 302,{'Location':f'https://auth.mistral.ai/{target}?case={case}'},b''
    if parsed.path in ('/main-auth-middle','/frame-auth-middle'):
        target='main-auth-final' if parsed.path=='/main-auth-middle' else 'frame-auth-final'
        return 302,{'Location':f'https://frame-b.vibez.test/content?case={target}'},b''
    if parsed.path=='/return':
        mode='after-login-live' if case=='login-live-return' else 'after-main-auth'
        return 200,{'Content-Type':'text/html; charset=utf-8'},Path(__file__).with_name('fixture.html').read_text().replace('__RESUME__',json.dumps(mode)).encode()
    if parsed.path=='/redirect':
        return 302,{'Location':f'https://frame-b.vibez.test/content?case={case}'},b''
    if parsed.path=='/executed':return 204,{},b''
    script=f"""const tag={json.dumps(case)};const m={{kind:'structural-ready',case:tag,isTop:window===top}};
      if(window===top)fetch('https://frame-a.vibez.test/executed?case='+encodeURIComponent(tag)).catch(()=>{{}});
      (window.opener||top.opener||top).postMessage(m,'*');
      window.__structuralPopup={{case:tag,ready:true,openerPresent:!!window.opener}};"""
    if case=='nested-parent':
        script+="const f=document.createElement('iframe');f.src='https://frame-b.vibez.test/content?case=nested-child';document.body.append(f);"
    if case in ('oauth-direct','oauth-blank','login-live-popup','login-live-boundary-popup'):
        script+=f"setTimeout(()=>location.href='https://frame-b.vibez.test/redirect?case={case}-final',400);"
    if case=='popup-boundary-frame':
        script+="""let p=null;window.addEventListener('message',e=>{
          if(e.source===parent&&e.data?.kind==='boundary-open')p=window.open('https://login.live.com/content?case=login-live-boundary-popup','_blank');
          if(e.source===parent&&e.data?.kind==='boundary-status')parent.postMessage({kind:'boundary-popup-status',open:!!p&&!p.closed},'*');
          if(e.source===parent&&e.data?.kind==='boundary-close'&&p)p.close();
          if(e.source===p&&e.data?.kind==='structural-ready')parent.postMessage(e.data,'*');
        });"""
    if case=='top-during-iframe-login-popup':
        script+="window.__structuralState={controlledFixture:true,scenario:'auth-popup-boundary',currentCase:'unexpected-main-commit',finished:true};"
    if case=='login-live-main':
        script+="setTimeout(()=>location.href='https://chat.mistral.ai/return?case=login-live-return',350);"
    if case=='main-auth-final':
        script+="setTimeout(()=>location.href='https://chat.mistral.ai/return?case=main-auth-return',350);"
    if case=='pending-canvas':
        script+="setTimeout(()=>location.href='https://frame-b.vibez.test/content?case=pending-escape',500);"
    html=f'''<!doctype html><meta charset="utf-8"><style>body{{background:#dff5e8;color:#152a23;font:16px sans-serif}}</style>
      <body>Controlled HTTPS fixture: {case}<canvas width="200" height="80"></canvas>
      <script>const x=document.querySelector('canvas').getContext('2d');x.fillStyle='#2563eb';x.fillRect(5,5,80,60);{script}</script></body>'''
    return 200,{'Content-Type':'text/html; charset=utf-8'},html.encode()

class State:
    def __init__(self,path,certificate,key):
        self.path=Path(path);self.lock=threading.Lock()
        self.tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);self.tls.load_cert_chain(certificate,key)
    def record(self,event,**data):
        with self.lock:
            with self.path.open('a') as out:out.write(json.dumps({'event':event,**data})+'\n')

class Origin(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_GET(self):
        case=case_of(self.path);status,headers,body=content(self.server.host,self.path)
        self.server.state.record('https-request',host=self.server.host,case=case,
                                 pathKind=urlsplit(self.path).path,method='GET',status=status)
        self.send_response(status)
        for k,v in headers.items():self.send_header(k,v)
        self.send_header('Content-Length',str(len(body)));self.send_header('Connection','close');self.end_headers()
        if body:self.wfile.write(body)
        self.close_connection=True

class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_CONNECT(self):
        host,_,port=self.path.rpartition(':')
        allowed=host in HOSTS and port=='443'
        self.server.state.record('connect',host=host if host in HOSTS else 'unexpected-host',port=port,allowed=allowed)
        if not allowed:self.send_error(403);return
        self.send_response(200,'Connection established');self.end_headers();self.wfile.flush()
        try:
            secure=self.server.state.tls.wrap_socket(self.connection,server_side=True)
            Origin(secure,self.client_address,SimpleNamespace(host=host,state=self.server.state))
            secure.close()
        except (ssl.SSLError,ConnectionError,OSError) as exc:
            self.server.state.record('tls-connection-ended',host=host,errorType=type(exc).__name__)
        self.close_connection=True
    def do_GET(self):
        self.server.state.record('cleartext-proxy-request',case=case_of(self.path))
        self.send_error(403,'Controlled proxy does not forward cleartext requests')

def start(output):
    output=Path(output);cert=output/'fixture-certificate.pem';key=output/'fixture-key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                    '-subj','/CN=VibeZ isolated structural fixture',
                    '-addext','subjectAltName='+','.join('DNS:'+host for host in HOSTS),
                    '-keyout',str(key),'-out',str(cert)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    key.chmod(0o600)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Proxy);server.daemon_threads=True
    server.state=State(output/'server.jsonl',cert,key)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    return server,cert
