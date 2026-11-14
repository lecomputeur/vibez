#!/usr/bin/python3
"""Live self-test of the Mistral Work connection, driven from this computer.

Runs the locally built VibeZ V4 Alpha binary (feature `native-smoke`) with
`--live-work-self-test`, uses the signed-in Mistral session of the app's own
profile and one fixed test project, and exercises the Work route end to end:

1. link a test folder from a clean state  -> created, attached, Mistral calls tools/list
   then send one real message             -> the sent message reads exactly as typed, the
                                              vibezwork label is invisible, the reference is kept
2. leave a draft with the connector chip, restart the app, link again
                                           -> registered with the same connector when the
                                              tunnel helper survived, else replaced + created;
                                              attached, no blocked-draft
3. navigate away and back                  -> registered, attached within seconds
4. repeat 1-3 in the current app language, Polish and English
5. exactly one vibezwork connector remains for the test project
6. with --code-project-id: link a folder to a Code project, check that the
   "VibeZ · <project>" title chip is hidden in the composer and in a sent
   message, then remove the test connectors again

Only step names, seconds, counts and booleans are recorded. Addresses, keys,
tokens, cookies and page text never enter the report or the log.

With `--engine-source` this file runs as the backend engine wrapper inside the
app instead: it loads the real standalone engine and adds one diagnostic
command (`self_test_connectors`) that counts or removes this installation's own
test connectors for the test project only. Nothing else is changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

BASE = Path(__file__).resolve().parents[1]
APP_ID = 'nl.lecomputeur.vibez4.alpha'
# The test projects belong to the maintainer's own Mistral account, so they are
# not in the source: put them in tools/live-work-self-test.local.json (never
# tracked) as {"project_id", "project_name", "code_project_id",
# "code_project_name"}, or pass them on the command line.
try:
    LOCAL = json.loads((BASE / 'tools/live-work-self-test.local.json').read_text())
except (OSError, ValueError):
    LOCAL = {}
DEFAULT_PROJECT = str(LOCAL.get('project_id') or '')
DEFAULT_NAME = str(LOCAL.get('project_name') or '')
DRAFT_TEXT = 'VibeZ live self-test draft'
SENT_PREFIX = 'VibeZ live self-test message'
SENT_REQUEST = ' Please answer with the single word OK and do not use any tools.'
WORK_LABEL = r'vibezwork[0-9a-f]{16}'
UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
RETURN_SECONDS = 30  # "a few seconds" budget for the leave-and-return scenario


# --------------------------------------------------------------------------
# Engine wrapper (runs inside the app, under python3 -I)
# --------------------------------------------------------------------------
def engine_wrapper():
    import importlib.util
    source = Path(sys.argv[sys.argv.index('--engine-source') + 1])
    spec = importlib.util.spec_from_file_location('vibez_standalone_engine', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    Base = module.StandaloneEngine

    class SelfTestEngine(Base):
        def dispatch(self, command):
            if isinstance(command, dict) and command.get('action') == 'self_test_connectors':
                self.external_output(self.self_test_connectors(command))
                return
            return super().dispatch(command)

        def self_test_connectors(self, command):
            key = command.get('project_id')
            remove = command.get('remove') is True
            request = command.get('request_id')
            event = {'type': 'self_test_connectors', 'project_id': key, 'remove': remove,
                     'request_id': request if isinstance(request, str) and re.fullmatch(r'[A-Za-z0-9-]{1,40}', request) else None}
            registry = self.automatic.registry
            if not isinstance(key, str) or not re.fullmatch(r'(?:chat-|code-)?[0-9a-f-]{36}', key):
                event['error'] = 'invalid_project'
                return event
            with self.lock:
                api_key = self.key
            if not api_key:
                event['error'] = 'no_key'
                return event
            if self.automatic._active_job() is not None:
                event['error'] = 'busy'
                return event
            api = self.automatic.api_factory(api_key)
            guard = lambda: None
            work_prefix = '[VibeZ-work:' + registry.installation + ':' + key + ':'
            legacy_marker = registry.marker(key)
            try:
                rows = [row for row in registry.list_connectors(api, guard)
                        if isinstance(row.get('description'), str) and isinstance(row.get('id'), str)
                        and (work_prefix in row['description'] or legacy_marker in row['description'])]
                work = [row for row in rows if str(row.get('name', '')).startswith('vibezwork')]
                event.update(count=len(rows), work=len(work), legacy=len(rows) - len(work))
                if remove:
                    outcomes = {}
                    for row in rows:
                        try:
                            outcome = registry.remove_connector(key, row['id'], api, guard)
                        except Exception as exc:  # names only, never messages
                            outcome = 'error:' + str(getattr(exc, 'code', None) or type(exc).__name__)
                        outcomes[outcome] = outcomes.get(outcome, 0) + 1
                    event['removed'] = outcomes
            except Exception as exc:
                event['error'] = str(getattr(exc, 'code', None) or type(exc).__name__)
            return event

    module.StandaloneEngine = SelfTestEngine
    module.main()


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
class SelfTestError(Exception):
    pass


def now_ms():
    return int(time.time() * 1000)


def write_json(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    os.replace(tmp, path)


AGENT_INSTALL = r"""(()=>{if(window.__vibezLiveWork)return 'present';const s=window.__vibezLiveWork={connector:null,auto:null,auth:null,selftest:null,results:{},errors:[],ready:false};
window.__TAURI__.event.listen('app-engine',e=>{const d=e.payload||{};if(d.type==='web_connector'){s.connector={project:d.project?{id:d.project.id,name:d.project.name}:null,folder:d.folder||null,enabled:!!d.enabled,tunnel_status:d.tunnel_status||null,workspace_binding:d.workspace_binding||null,target_folder_id:d.target_folder_id||null,folders:(d.folders||[]).length,auto_approved:!!d.auto_approved,manually_paused:!!d.manually_paused,at:Date.now()};}
else if(d.type==='web_auto'){if(d.status==='starting')s.auto_start={project_id:d.project_id||null,automatic:d.automatic===true,at:Date.now()};s.auto={project_id:d.project_id||null,status:d.status,error_code:d.error_code||null,work_failure:d.work_failure||null,pause_reason:d.pause_reason||null,connector_id:d.connector_id||null,method:d.method||null,retry_after:d.retry_after||null,automatic:d.automatic===true,at:Date.now()};}
else if(d.type==='auth'){s.auth={status:d.status,at:Date.now()};}
else if(d.type==='self_test_connectors'){s.selftest=d;}
else if(d.type==='error'){s.errors.push(String(d.code||'error').slice(0,60));}}).then(()=>{s.ready=true;});
s.call=(key,name,args)=>{s.results[key]={pending:true};window.__TAURI__.core.invoke(name,args).then(v=>{s.results[key]={ok:true,value:v===undefined?null:v};}).catch(e=>{s.results[key]={ok:false,error:String(e).slice(0,300)};});};
return 'installed';})()"""
AGENT_SNAPSHOT = r"""JSON.stringify((()=>{const s=window.__vibezLiveWork;if(!s)return {missing:true};let language=null;try{language=window.vibezLanguage?.state?.()||null;}catch(e){}return {ready:s.ready,connector:s.connector,auto:s.auto,auto_start:s.auto_start||null,auth:s.auth,selftest:s.selftest,errors:s.errors.slice(-5),language};})())"""
MISTRAL_CHIPS = r"""JSON.stringify((()=>{const eds=[...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(e=>e.getClientRects().length);if(eds.length!==1)return {editors:eds.length};const doc=eds[0].pmViewDesc?.node;if(!doc||typeof doc.descendants!=='function')return {editors:1,no_doc:true};const chips=[];doc.descendants(n=>{if(n.isText||!n.isInline||!n.isAtom)return;if(n.type.name==='slash'&&n.attrs?.subType==='connection'&&/^vibezwork[a-f0-9]{16}$/.test(n.attrs.selectedLabel||''))chips.push({id:n.attrs.selectedValue||null});});return {editors:1,chips,text:String(doc.textContent||'').trim().slice(0,80),path:location.pathname.split('/').slice(0,3).join('/')};})())"""
PROJECT_SCRIPT = (BASE / 'desktop/src-tauri/src/workspace_project.js').read_text()
# Type a message into the only visible composer and press its send button
# (pointerdown + click, as a person would); nothing else on the page is touched.
MISTRAL_SEND = r"""JSON.stringify((()=>{const eds=[...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(e=>e.getClientRects().length);if(eds.length!==1)return {ok:false,editors:eds.length};const ed=eds[0];ed.focus();const sel=window.getSelection();const range=document.createRange();range.selectNodeContents(ed);range.collapse(false);sel.removeAllRanges();sel.addRange(range);const ok=document.execCommand('insertText',false,__TEXT__);return {ok};})())"""
# The editor's own text, read after ProseMirror has processed the input.
MISTRAL_COMPOSER_TEXT = r"""JSON.stringify({text:String([...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(e=>e.getClientRects().length)[0]?.pmViewDesc?.node?.textContent||'').trim().slice(0,120)})"""
# Mistral answers a refused send with HTTP 200 and an error inside the reply,
# and shows nothing on the page. Record such refusals, so a failed send names
# its reason (for example TOO_MANY_REQUESTS / user_concurrent_limit).
MISTRAL_WATCH_REFUSALS = r"""(()=>{if(window.__vibezSelfTestRefusals)return 'watching';const log=window.__vibezSelfTestRefusals=[];const original=window.fetch;window.fetch=async function(...a){const response=await original.apply(this,a);try{const url=new URL(String(a[0]?.url||a[0]),location.href);const method=a[1]?.method||a[0]?.method||'GET';if(method!=='GET'&&/\/api\/(code-)?trpc\//.test(url.pathname)&&!/track|event\./.test(url.pathname))response.clone().text().then(t=>{const code=/"code":"([A-Z_]{3,40})"/.exec(t),kind=/"kind":"([a-z_]{3,40})"/.exec(t);if(!response.ok||code)log.push({path:url.pathname.split('/').pop().slice(0,60),status:response.status,code:code?code[1]:null,kind:kind?kind[1]:null});}).catch(()=>{});}catch(e){}return response;};return 'watching';})()"""
MISTRAL_REFUSALS = r"""JSON.stringify(window.__vibezSelfTestRefusals||[])"""
# A failed earlier run can leave its own unsent test message in the composer;
# only such a leftover (it starts with the test prefix) is ever cleared.
MISTRAL_CLEAR_TEST_DRAFT = r"""JSON.stringify((()=>{const eds=[...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(e=>e.getClientRects().length);if(eds.length!==1)return {cleared:false,editors:eds.length};const ed=eds[0];const text=String(ed.pmViewDesc?.node?.textContent||'').trim();if(!text)return {cleared:false,empty:true};if(!text.startsWith(__PREFIX__))return {cleared:false,foreign:true};ed.focus();const sel=getSelection();const range=document.createRange();range.selectNodeContents(ed);sel.removeAllRanges();sel.addRange(range);document.execCommand('delete');return {cleared:true,length:text.length};})())"""
# A Code session keeps running after its answer and counts toward Mistral's
# limit of concurrent sessions; the test stops the one session it started
# (the session the page is on right after its own send).
MISTRAL_PRESS = "const o={bubbles:true,cancelable:true,pointerId:1,pointerType:'mouse',button:0};const press=b=>{b.dispatchEvent(new PointerEvent('pointerdown',o));b.dispatchEvent(new MouseEvent('mousedown',o));b.dispatchEvent(new PointerEvent('pointerup',o));b.dispatchEvent(new MouseEvent('mouseup',o));b.click();};"
MISTRAL_STOP_WORDS = "['Stoppen','Stop','Zatrzymaj','Arrêter','Stopp','Detener','Parar','Interrompi']"
MISTRAL_SESSION_MENU = r"""(()=>{""" + MISTRAL_PRESS + r"""const path=location.pathname;if(!/^\/code\/[0-9a-f-]{36}\/[0-9a-f-]{36}$/.test(path))return 'no-session';const a=[...document.querySelectorAll('a[data-jump-target]')].find(a=>a.dataset.jumpTarget===path);if(!a)return 'not-listed';const b=a.parentElement?.querySelector('button');if(!b)return 'no-menu';press(b);return 'opened';})()"""
MISTRAL_SESSION_STOP = r"""(()=>{""" + MISTRAL_PRESS + r"""const words=""" + MISTRAL_STOP_WORDS + r""";const it=[...document.querySelectorAll('[role="menu"] [role="menuitem"]')].find(e=>words.includes((e.innerText||'').trim()));if(!it){document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));return 'no-stop-entry';}press(it);return 'chosen';})()"""
MISTRAL_SESSION_STOP_CONFIRM = r"""(()=>{""" + MISTRAL_PRESS + r"""const words=""" + MISTRAL_STOP_WORDS + r""";const d=[...document.querySelectorAll('[role="dialog"],[role="alertdialog"]')].filter(d=>d.getClientRects().length);if(d.length!==1)return 'no-dialog';const b=[...d[0].querySelectorAll('button')].filter(b=>words.includes((b.innerText||'').trim()));if(b.length!==1)return 'no-button';press(b[0]);return 'stopped';})()"""
# The one visible, enabled submit button nearest to the composer (Mistral's
# "Send" button sits a few levels above the editor, outside its form).
MISTRAL_CLICK_SEND = r"""(()=>{const eds=[...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(e=>e.getClientRects().length);if(eds.length!==1)return 'no-editor';let anc=eds[0];for(let i=0;i<8&&anc.parentElement;i++){anc=anc.parentElement;const bs=[...anc.querySelectorAll('button[type=submit]')].filter(b=>b.getClientRects().length&&!b.disabled&&b.getAttribute('aria-disabled')!=='true');if(bs.length===1){const b=bs[0];b.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,cancelable:true,pointerId:1,pointerType:'mouse',button:0}));b.click();return 'clicked';}if(bs.length>1)return 'ambiguous';}return 'no-button';})()"""
MISTRAL_PRESS_ENTER = r"""(()=>{const eds=[...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(e=>e.getClientRects().length);if(eds.length!==1)return 'no-editor';eds[0].focus();eds[0].dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true}));return 'enter';})()"""
# What a person sees of the sent message: only counts, booleans and a path.
# Real input (the app's "input" self-test command) needs a point on the page.
# Each helper names the element under that point, so a covered control is reported, not clicked blindly.
MISTRAL_EDITOR_POINT = r"""JSON.stringify((()=>{const eds=[...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(e=>e.getClientRects().length);if(eds.length!==1)return {ok:false,editors:eds.length};const r=eds[0].getBoundingClientRect();const x=Math.round(r.left+Math.min(r.width-12,Math.max(12,r.width*0.6)));const y=Math.round(r.bottom-Math.min(14,r.height/2));const hit=document.elementFromPoint(x,y);return {ok:!!hit&&(eds[0].contains(hit)||hit.contains(eds[0])),x,y,hit:hit?hit.tagName:null};})())"""
MISTRAL_SEND_POINT = r"""JSON.stringify((()=>{const eds=[...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(e=>e.getClientRects().length);if(eds.length!==1)return {ok:false,reason:'no-editor'};let anc=eds[0];for(let i=0;i<8&&anc.parentElement;i++){anc=anc.parentElement;const bs=[...anc.querySelectorAll('button[type=submit]')].filter(b=>b.getClientRects().length&&!b.disabled&&b.getAttribute('aria-disabled')!=='true');if(bs.length===1){const r=bs[0].getBoundingClientRect();const x=Math.round(r.left+r.width/2);const y=Math.round(r.top+r.height/2);const hit=document.elementFromPoint(x,y);return {ok:!!hit&&(bs[0].contains(hit)||hit.contains(bs[0])),x,y,hit:hit?hit.tagName:null};}if(bs.length>1)return {ok:false,reason:'ambiguous'};}return {ok:false,reason:'no-button'};})())"""
MISTRAL_TRUST_WATCH = r"""(()=>{if(window.__vibezSelfTestTrust)return 'watching';const t=window.__vibezSelfTestTrust={keys:0,trusted_keys:0,clicks:0,trusted_clicks:0};window.addEventListener('keydown',e=>{t.keys++;if(e.isTrusted)t.trusted_keys++;},true);window.addEventListener('click',e=>{t.clicks++;if(e.isTrusted)t.trusted_clicks++;},true);return 'installed';})()"""
MISTRAL_TRUST = r"""JSON.stringify(window.__vibezSelfTestTrust||{})"""
MISTRAL_SENT = r"""JSON.stringify((()=>{const marker=__MARK__;const full=__FULL__;const re=new RegExp(__LABEL__);const all=[...document.querySelectorAll('body *')].filter(e=>!e.closest('[contenteditable="true"]')&&(e.textContent||'').includes(marker));const leaves=all.filter(e=>![...e.children].some(c=>(c.textContent||'').includes(marker)));const msg=leaves[0]||null;const eds=[...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(e=>e.getClientRects().length);const q=window.__vibezWorkLabelQuiet||null;const body=document.body.innerText||'';const strip=s=>s.replace(/\s+/g,' ').trim();return {found:!!msg,candidates:leaves.length,path:location.pathname.split('/').slice(0,2).join('/'),message_text_exact:msg?strip(msg.innerText)===strip(full):null,message_leading_space:msg?/^[\s\u00a0]/.test(msg.innerText):null,message_hidden_chips:msg?msg.querySelectorAll('[data-vibez-quiet-label],[aria-hidden="true"][contenteditable="false"]').length:null,message_label_visible:msg?re.test(msg.innerText):null,label_visible_on_page:re.test(body),label_in_dom:re.test(document.body.textContent||''),quiet_hidden:q?q.hidden:null,titles:q?(q.titles?q.titles.size:0):null,composer_text:eds.length===1?String(eds[0].pmViewDesc?.node?.textContent||'').trim().slice(0,40):null,composer_hidden_atoms:eds.length===1?[...eds[0].querySelectorAll('[contenteditable=false]')].filter(n=>getComputedStyle(n).display==='none').length:null,composer_visible_atoms:eds.length===1?[...eds[0].querySelectorAll('[contenteditable=false]')].filter(n=>getComputedStyle(n).display!=='none').length:null};})())"""
MISTRAL_DRAFT = r"""JSON.stringify((()=>{const eds=[...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(e=>e.getClientRects().length);if(eds.length!==1)return {ok:false,editors:eds.length};const ed=eds[0];ed.focus();const sel=window.getSelection();const range=document.createRange();range.selectNodeContents(ed);range.collapse(false);sel.removeAllRanges();sel.addRange(range);const ok=document.execCommand('insertText',false,__TEXT__);return {ok,text:String(ed.pmViewDesc?.node?.textContent||'').trim().slice(0,80)};})())"""


class App:
    """One app process with the file-based command channel."""

    def __init__(self, binary, directory, log, environment):
        self.binary = binary
        self.directory = directory
        self.log = log
        self.environment = environment
        self.process = None
        self.serial = 0
        self.engine_pid = None
        self.ready = None

    def start(self, timeout=60):
        for name in ('command.json', 'result.json'):
            try:
                (self.directory / name).unlink()
            except FileNotFoundError:
                pass
        self.started_ms = now_ms()
        self.started_at = time.time()
        self.process = subprocess.Popen([str(self.binary), '--live-work-self-test'], env=self.environment,
                                        stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
                                        start_new_session=True, cwd=str(self.directory))
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise SelfTestError('The app stopped during startup (exit %s)' % self.process.returncode)
            result = self._read_result()
            if result and result.get('id') == 0 and result.get('result', {}).get('ready'):
                self.ready = result['result']
                self.engine_pid = self.ready.get('engine_pid')
                return self.ready
            time.sleep(0.25)
        raise SelfTestError('The app did not announce the self-test channel in time')

    def _read_result(self):
        try:
            return json.loads((self.directory / 'result.json').read_text())
        except (OSError, ValueError):
            return None

    def command(self, action, timeout=20, **fields):
        self.serial += 1
        request = {'id': self.serial, 'action': action, **fields}
        tmp = self.directory / 'command.json.tmp'
        tmp.write_text(json.dumps(request))
        os.replace(tmp, self.directory / 'command.json')
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None and action != 'quit':
                raise SelfTestError('The app stopped unexpectedly (exit %s)' % self.process.returncode)
            result = self._read_result()
            if result and result.get('id') == self.serial:
                if not result.get('ok'):
                    raise SelfTestError('%s failed: %s' % (action, result.get('result', {}).get('error', 'unknown')))
                return result.get('result')
            time.sleep(0.15)
        raise SelfTestError('No answer to %s within %ss' % (action, timeout))

    def input(self, kind, **fields):
        """Real keys and clicks on the Mistral page (trusted events, as a person produces them)."""
        return self.command('input', surface='mistral', kind=kind, **fields)

    def eval(self, surface, script, timeout=20):
        return self.command('eval', timeout=timeout, surface=surface, script=script)

    def invoke(self, name, args, timeout=30):
        key = uuid.uuid4().hex[:12]
        self.eval('main', 'window.__vibezLiveWork.call(%s,%s,%s);"sent"' % (json.dumps(key), json.dumps(name), json.dumps(args)))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.eval('main', 'JSON.stringify(window.__vibezLiveWork.results[%s]||{missing:true})' % json.dumps(key))
            result = json.loads(raw)
            if result.get('pending'):
                time.sleep(0.3)
                continue
            if result.get('missing'):
                raise SelfTestError('invoke %s lost its result' % name)
            if not result.get('ok'):
                raise SelfTestError('%s failed: %s' % (name, result.get('error')))
            return result.get('value')
        raise SelfTestError('invoke %s timed out' % name)

    def snapshot(self):
        return json.loads(self.eval('main', AGENT_SNAPSHOT))

    def install_agent(self, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.eval('main', AGENT_INSTALL)
                snap = self.snapshot()
                if snap.get('ready'):
                    return
            except SelfTestError as error:
                if 'outside screen 1' in str(error):
                    raise
            time.sleep(0.5)
        raise SelfTestError('The self-test agent did not become ready in the main window')

    def quit(self, timeout=30):
        if self.process is None:
            return
        try:
            if self.process.poll() is None:
                self.command('quit', timeout=10)
        except SelfTestError:
            pass
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._kill(self.process.pid)
            self.process.wait(timeout=10)
        # The engine (and its tunnel helper) live in their own process group.
        if self.engine_pid:
            for _ in range(40):
                if not pid_alive(self.engine_pid):
                    break
                time.sleep(0.25)
            if pid_alive(self.engine_pid):
                self._kill(self.engine_pid)
        self.process = None

    @staticmethod
    def _kill(pid):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
            except ProcessLookupError:
                return
            except PermissionError:
                return
            time.sleep(1.5)
            if not pid_alive(pid):
                return


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        with open('/proc/%d/stat' % pid) as handle:
            return handle.read().split(')')[-1].split()[0] != 'Z'
    except OSError:
        return False


class Diagnostics:
    """Reads the engine's own diagnostic files: step names, seconds and counts only."""

    def __init__(self, directory):
        self.directory = directory

    def _mtime(self, name):
        try:
            return (self.directory / name).stat().st_mtime
        except FileNotFoundError:
            return 0.0

    def timing_mtime(self):
        return self._mtime('connector-timing.json')

    def wait_timing(self, after, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.timing_mtime() > after:
                try:
                    data = json.loads((self.directory / 'connector-timing.json').read_text())
                    return {'outcome': data.get('outcome'), 'method': data.get('method'),
                            'steps': [[str(step[0]) if not isinstance(step[0], dict) else 'other', float(step[1])] for step in data.get('steps', [])[:80]]}
                except (OSError, ValueError, IndexError, TypeError):
                    pass
            time.sleep(0.3)
        return None

    def error_report(self, since):
        if self._mtime('connector-error.json') < since:
            return None
        try:
            data = json.loads((self.directory / 'connector-error.json').read_text())
        except (OSError, ValueError):
            return {'unreadable': True}
        report = {key: data.get(key) for key in ('stage', 'error_code', 'http_status') if key in data}
        step = data.get('work_step')
        if isinstance(step, dict):
            report['work_step'] = {key: value for key, value in step.items() if key in ('event', 'stage', 'state', 'reason', 'reloaded', 'site_language')}
        return report

    def transport_since(self, since):
        try:
            data = json.loads((self.directory / 'transport-status.json').read_text())
        except (OSError, ValueError):
            return []
        rows = []
        for row in data.get('recent_requests', []):
            if not isinstance(row, dict) or row.get('time', 0) < int(since) - 1:
                continue
            rows.append({key: row.get(key) for key in ('verb', 'method', 'http_status', 'tool', 'session') if key in row})
        return rows

    def transport_counts(self, since):
        """Requests since a moment, counted by method, answer and kind of project. No names."""
        try:
            data = json.loads((self.directory / 'transport-status.json').read_text())
        except (OSError, ValueError):
            return {}
        counts = {}
        for row in data.get('recent_requests', []):
            if not isinstance(row, dict) or row.get('time', 0) < int(since):
                continue
            label = '%s %s %s for %s%s' % (row.get('verb'), row.get('method'), row.get('http_status'), row.get('target'),
                                           '' if row.get('target_enabled') is None else (' on' if row.get('target_enabled') else ' paused'))
            counts[label] = counts.get(label, 0) + 1
        return counts


class Run:
    def __init__(self, args, output, diagnostics):
        self.args = args
        self.output = output
        self.diagnostics = diagnostics
        self.project = args.project_id
        self.project_url = 'https://chat.mistral.ai/work/projects/' + self.project
        self.chat_url = None
        self.chat_navigated_ms = 0
        # Folder each project was linked to before the test touched it: restored at the end.
        self.original_folders = {}
        # Page scripts act on trusted events only; real input exercises them.
        self.real_input = sys.platform.startswith('linux') and not args.synthetic_input
        self.report = {'passed': False, 'live_mistral': True, 'offline_engine': False, 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                       'binary': str(args.binary), 'binary_sha256': hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(),
                       'project_id': self.project, 'app_starts': 0, 'runs': [], 'final_connectors': None, 'errors': [], 'notes': []}
        self.save()

    def save(self):
        write_json(self.output / 'report.json', self.report)

    def note(self, text):
        self.report['notes'].append(text)
        self.save()

    # ---- waiting helpers -------------------------------------------------
    def wait(self, app, predicate, timeout, what):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = app.snapshot()
            if predicate(last):
                return last
            time.sleep(0.5)
        raise SelfTestError('Timeout while waiting for %s' % what)

    def goto_project(self, app, timeout=60):
        app.invoke('web_surface', {'show': True, 'route': self.project_url})
        snap = self.wait(app, lambda s: (s.get('connector') or {}).get('project', {}) and s['connector']['project'].get('id') == self.project, timeout, 'the test project page')
        if not self.args.project_name:
            return snap
        # The id is known from the address at once; the visible name follows
        # when Mistral has rendered the page, and may still be the previous
        # page's title for a moment. Wait for it instead of judging the first snapshot.
        named = lambda s: ((s.get('connector') or {}).get('project') or {}).get('id') == self.project and s['connector']['project'].get('name') == self.args.project_name
        try:
            return self.wait(app, named, 20, 'the test project name')
        except SelfTestError:
            seen = ((app.snapshot().get('connector') or {}).get('project') or {}).get('name')
            raise SelfTestError('The open project is not the test project (name differs: %r)' % (seen,))

    def goto_code_project(self, app, timeout=60):
        key = 'code-' + self.args.code_project_id
        app.invoke('web_surface', {'show': True, 'route': 'https://chat.mistral.ai/code/' + self.args.code_project_id})
        expected = self.args.code_project_name
        seen = []

        def open_and_named(s):
            project = (s.get('connector') or {}).get('project') or {}
            if project.get('id') != key:
                return False
            if not seen or seen[-1] != project.get('name'):
                seen.append(project.get('name'))
            # The page shows the project id first and its name a moment later.
            return not expected or project.get('name') == expected
        try:
            snap = self.wait(app, open_and_named, timeout, 'the Code test project page')
        except SelfTestError as error:
            if seen:
                raise SelfTestError('The open Code project is not the Code test project (names seen %r, expected %r)' % (seen, expected))
            raise error
        time.sleep(2)
        return snap

    def open_work(self, app, project, timeout=60):
        app.invoke('web_surface', {'show': True, 'route': 'https://chat.mistral.ai/work/projects/' + project})
        try:
            return self.wait(app, lambda s: ((s.get('connector') or {}).get('project') or {}).get('id') == project, timeout, 'the project page')
        except SelfTestError:
            seen = (app.snapshot().get('connector') or {}).get('project') or {}
            try:
                path = app.eval('mistral', 'location.pathname+" | "+document.title.slice(0,60)+" | "+(document.querySelector("h1")?.innerText||"").slice(0,60)')
            except SelfTestError as error:
                path = 'eval failed: %s' % error
            raise SelfTestError('Timeout while waiting for the project page (wanted %s, panel has %s, page %s)' % (project[:8], str(seen.get('id'))[:8], path))

    def scenario_switch(self, app, projects, rounds, dwell):
        """Two linked projects, connected by hand in turn. Counts how often Mistral rejects the kept connector."""
        scenario = {'name': 'switch_projects', 'passed': False, 'visits': [], 'checks': {}}
        self.report['switch'] = scenario
        for round_number in range(rounds):
            for index, project in enumerate(projects):
                since = time.time()
                snap = self.open_work(app, project)
                time.sleep(3)
                # Collect Mistral's own toasts for this visit (texts cut to 60 characters).
                # Kept in sessionStorage so a page reload during the connect does not lose them.
                # Also notes every Mistral request that fails (status, method, path without ids).
                collector = r"""(()=>{const K='__vibezNotes';const add=x=>{try{const l=JSON.parse(sessionStorage.getItem(K)||'[]');
l.push([Math.round(Date.now()/100)/10,x]);sessionStorage.setItem(K,JSON.stringify(l.slice(-80)))}catch(e){}};
if(RESET)sessionStorage.setItem(K,'[]');
clearInterval(window.__vibezToastTimer);window.__vibezToastTimer=setInterval(()=>{
for(const t of document.querySelectorAll('[data-sonner-toast],[role=status],[role=alert]')){const x=(t.innerText||'').trim().slice(0,60);
if(x&&!t.__vibezSeen){t.__vibezSeen=1;add('toast '+x)}}},200);
if(!window.__vibezFetch){window.__vibezFetch=window.fetch;window.fetch=async function(input,init){
const u=new URL((input&&input.url)||input,location.href);const m=((init&&init.method)||(input&&input.method)||'GET');
const path=u.host+u.pathname.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g,'*').replace(/[A-Za-z0-9_-]{20,}/g,'*').slice(0,90);
try{const r=await window.__vibezFetch.apply(this,arguments);if(r.status>=400)add('http '+r.status+' '+m+' '+path);
else if(/connector|mcp|tool/i.test(path))add('ok '+r.status+' '+m+' '+path);return r}
catch(e){add('neterr '+m+' '+path);throw e}}}
return 'ok'})()"""
                app.eval('mistral', collector.replace('RESET', 'true').replace('\n', ''))
                self.collector = collector.replace('RESET', 'false').replace('\n', '')
                linked = (snap.get('connector') or {}).get('folder') or ''
                if not os.path.isdir(linked):
                    # A fresh test project: give it its own folder inside this run's output.
                    self.link_folder(app, snap.get('connector') or {}, project, (self.args.workspace_a, self.args.workspace_b)[index])
                    time.sleep(2)
                record = self.connect(app, manual=True, label='switch %d.%d' % (round_number + 1, index + 1), timeout=self.args.connect_timeout, project=project)
                names = self.step_names(record)
                visit = {'round': round_number + 1, 'project': index + 1, 'status': record['status'], 'duration_s': record['duration_s'],
                         'kept_connector': 'registered' in names and not ({'created', 'recreated', 'attach-failed'} & set(names)),
                         'rejected': 'attach-failed' in names, 'steps': record.get('steps'), 'error_report': record.get('error_report'),
                         'work_failure': record.get('work_failure'), 'requests_during_connect': self.diagnostics.transport_counts(since)}
                scenario['visits'].append(visit)
                self.save()
                print('switch', visit['round'], visit['project'], visit['status'], visit['duration_s'], 'rejected' if visit['rejected'] else 'kept' if visit['kept_connector'] else 'new', flush=True)
                idle = time.time()
                time.sleep(dwell)
                visit['requests_while_open'] = self.diagnostics.transport_counts(idle)
                try:
                    raw = app.eval('mistral', 'sessionStorage.getItem("__vibezNotes")')
                    visit['toasts'] = json.loads(raw) if isinstance(raw, str) else raw
                except Exception: visit['toasts'] = None
                print('  toasts', visit['toasts'], flush=True)
                self.save()
        visits = scenario['visits']
        later = visits[len(projects):]
        scenario['checks'] = {'all_connected': all(v['status'] == 'connected' for v in visits),
                              'no_rejection': not any(v['rejected'] for v in visits),
                              'returns_within_30s': all((v['duration_s'] or 999) <= 30 for v in later)}
        scenario['rejections'] = sum(1 for v in visits if v['rejected'])
        scenario['slowest_return_s'] = max([v['duration_s'] or 0 for v in later] or [0])
        scenario['passed'] = all(scenario['checks'].values())
        return scenario

    def leave_project(self, app, timeout=30):
        app.invoke('web_navigate', {'destination': 'home'})
        self.wait(app, lambda s: not ((s.get('connector') or {}).get('project')), timeout, 'leaving the project page')

    def connect(self, app, *, manual, label, timeout, project=None, adopt=False, since=None):
        """Run one connection attempt and collect its step names and outcome."""
        project = project or self.project
        start = time.time()
        start_ms = now_ms() - 1000
        before = self.diagnostics.timing_mtime()
        record = {'label': label, 'manual': manual, 'status': None, 'duration_s': None, 'steps': [], 'statuses': [], 'consent_clicks': 0}
        if manual:
            # With saved Mistral access VibeZ relinks by itself right after a start.
            # The restart scenario observes that attempt instead of interrupting it.
            auto = app.snapshot().get('auto') or {}
            running = adopt and auto.get('project_id') == project and auto.get('at', 0) >= app.started_ms and \
                auto.get('status') in ('starting', 'authorizing', 'connecting', 'registering', 'connected')
            if running:
                record['manual'] = False; record['adopted_automatic'] = True
                start_ms = app.started_ms; before = app.started_at - 1
            else:
                app.invoke('web_command', {'payload': {'action': 'web_connect', 'project_id': project}})
        if since and not manual:
            # The attempt began before this call (the page was opened earlier).
            start_ms, before = since
        deadline = time.time() + timeout
        final = None
        while time.time() < deadline:
            if getattr(self, 'collector', None):
                try: app.eval('mistral', self.collector)
                except Exception: pass
            snap = app.snapshot()
            auto = snap.get('auto') or {}
            connector = snap.get('connector') or {}
            if auto.get('project_id') == project and auto.get('at', 0) >= start_ms:
                status = auto.get('status')
                if status and (not record['statuses'] or record['statuses'][-1] != status):
                    record['statuses'].append(status)
                started = snap.get('auto_start') or {}
                if started.get('project_id') == project and started.get('at', 0) >= start_ms:
                    record['automatic'] = started.get('automatic') is True
                if status == 'authorizing':
                    consent = app.command('consent')
                    record['consent_clicks'] += consent.get('clicked', 0)
                    if consent.get('needs_sign_in'):
                        record['status'] = 'needs_user_sign_in'
                        final = auto
                        break
                if status == 'connected' and connector.get('enabled') and connector.get('tunnel_status') == 'running':
                    final = auto
                    record['status'] = 'connected'
                    break
                if status in ('error', 'cancelled'):
                    final = auto
                    record['status'] = status
                    record['error_code'] = auto.get('error_code')
                    record['work_failure'] = auto.get('work_failure')
                    break
                if status == 'paused' and auto.get('pause_reason') == 'sign_in' and not manual:
                    final = auto
                    record['status'] = 'paused_sign_in'
                    break
            time.sleep(0.5)
        record['duration_s'] = round(time.time() - start, 1)
        if record['status'] is None:
            record['status'] = 'timeout'
        record['connector_id'] = (final or {}).get('connector_id')
        timing = self.diagnostics.wait_timing(before, timeout=20 if record['status'] != 'timeout' else 3)
        if timing:
            record['steps'] = timing['steps']
            record['outcome'] = timing['outcome']
            record['method'] = timing['method']
        error = self.diagnostics.error_report(start)
        if error:
            record['error_report'] = error
        return record

    @staticmethod
    def step_names(record):
        return [step[0] for step in record.get('steps', [])]

    def transport_check(self, since, record):
        rows = self.diagnostics.transport_since(since)
        names = self.step_names(record)
        probes = names.count('reachable') + names.count('unreachable')
        tools_list = sum(1 for row in rows if row.get('method') == 'tools/list' and row.get('http_status') == 200)
        overview = sum(1 for row in rows if row.get('method') == 'tools/call' and row.get('tool') == 'workspace_overview')
        return {'tools_list_calls': tools_list, 'readiness_probes': probes, 'mistral_tools_list_calls': max(0, tools_list - probes),
                'workspace_overview_calls': overview, 'methods': sorted({str(row.get('method')) for row in rows}),
                'mistral_called_tools': tools_list > probes or overview > 0}

    def chips(self, app):
        try:
            return json.loads(app.eval('mistral', MISTRAL_CHIPS))
        except (SelfTestError, ValueError) as error:
            return {'error': str(error)[:120]}

    def chip_summary(self, chips, connector_id, previous_connector=None):
        items = chips.get('chips') or []
        return {'editors': chips.get('editors'), 'vibez_chips': len(items),
                'current_connector_chips': sum(1 for item in items if connector_id and item.get('id') == connector_id),
                'previous_connector_chips': sum(1 for item in items if previous_connector and item.get('id') == previous_connector),
                'stale_connector_chips': sum(1 for item in items if not connector_id or item.get('id') != connector_id),
                'draft_text_present': DRAFT_TEXT in (chips.get('text') or ''), 'path': chips.get('path')}

    def project_chat(self, app):
        """An existing chat of the test project, where Mistral keeps drafts; None without one."""
        try:
            raw = app.eval('mistral', PROJECT_SCRIPT, timeout=20)
            links = json.loads(raw).get('chats') or []
        except (SelfTestError, ValueError, AttributeError):
            return None
        for link in links[:64]:
            if isinstance(link, str) and re.fullmatch(r'https://chat\.mistral\.ai/work/(?:(?:chat|chats|c)/)?[0-9a-f-]{36}', link):
                return link
        return None

    def goto_chat(self, app, timeout=45):
        """Open the project's chat page while the project scope stays the test project."""
        if not self.chat_url:
            return False
        self.chat_navigated_ms = now_ms() - 1000
        app.invoke('web_surface', {'show': True, 'route': self.chat_url})
        try:
            self.wait(app, lambda s: (s.get('connector') or {}).get('project', {}) and s['connector']['project'].get('id') == self.project
                      and (s['connector'].get('at') or 0) >= self.chat_navigated_ms, timeout, 'the project chat page')
        except SelfTestError:
            self.note('The project chat page was not recognised as the test project; the project page is used instead')
            self.chat_url = None
            self.goto_project(app)
            return False
        time.sleep(2)
        return True

    def set_language(self, app, code):
        app.invoke('language_set', {'language': code})
        self.wait(app, lambda s: (s.get('language') or {}).get('language') == code and not (s.get('language') or {}).get('pending'), 60, 'language %s' % code)
        # The Mistral page reloads in the new site language; wait for the project again.
        time.sleep(3)
        self.wait(app, lambda s: (s.get('connector') or {}).get('project', {}) and s['connector']['project'].get('id') == self.project, 60, 'the project after the language change')
        time.sleep(2)

    def engine_connectors(self, app, *, remove, timeout=90, project=None):
        # Opening a project page starts an automatic link; the wrapper answers
        # "busy" while that job runs, so wait for it instead of failing the scenario.
        deadline = time.time() + timeout
        while True:
            request = uuid.uuid4().hex[:12]
            app.command('engine', payload={'action': 'self_test_connectors', 'project_id': project or self.project, 'remove': remove, 'request_id': request})
            snap = self.wait(app, lambda s: (s.get('selftest') or {}).get('request_id') == request, timeout, 'the connector count')
            result = snap['selftest']
            if result.get('error') != 'busy' or time.time() > deadline:
                return {key: result.get(key) for key in ('count', 'work', 'legacy', 'removed', 'error') if key in result}
            time.sleep(3)

    # ---- scenarios -------------------------------------------------------
    def scenario_clean_link(self, app, language, *, first):
        """Scenario 1: link from a clean state -> created, attached, Mistral calls tools/list."""
        scenario = {'name': 'clean_link', 'language': language, 'passed': False, 'checks': {}}
        since = time.time()
        snap = self.goto_project(app)
        connector = snap['connector']
        if first or not connector.get('folder'):
            # No API key yet in this process: a fresh folder binding is the clean state.
            # Alternate between two test folders so a re-run also starts clean.
            current = connector.get('folder') or ''
            folder = self.args.workspace_a if os.path.realpath(current) != os.path.realpath(self.args.workspace_a) else self.args.workspace_b
            self.link_folder(app, connector, self.project, folder)
            scenario['clean_state'] = 'new_folder_binding'
        else:
            cleanup = self.engine_connectors(app, remove=True)
            scenario['clean_state'] = 'removed_own_connectors'
            scenario['cleanup'] = cleanup
            if cleanup.get('error'):
                raise SelfTestError('Could not clean the test project connectors: %s' % cleanup['error'])
            time.sleep(2)
        record = self.connect(app, manual=True, label='clean_link', timeout=self.args.connect_timeout)
        scenario['connection'] = record
        names = self.step_names(record)
        time.sleep(4)
        scenario['transport'] = self.transport_check(since, record)
        chips = self.chips(app)
        scenario['composer'] = self.chip_summary(chips, record.get('connector_id'))
        checks = scenario['checks']
        checks['connected'] = record['status'] == 'connected'
        checks['created'] = 'created' in names
        checks['attached'] = 'attached' in names
        checks['no_reuse'] = not ({'registered', 'replaced'} & set(names))
        checks['mistral_called_tools'] = scenario['transport']['mistral_called_tools']
        checks['chip_in_composer'] = scenario['composer'].get('current_connector_chips', 0) >= 1
        scenario['passed'] = all(checks.values())
        return scenario

    def link_folder(self, app, connector, project, folder):
        """Bind a test folder to a project (same payload the panel sends)."""
        if project not in self.original_folders:
            self.original_folders[project] = connector.get('folder') or ''
        app.command('choose_folder', path=str(folder))
        payload = {'action': 'web_link', 'project_id': project, 'path': str(folder)}
        if connector.get('workspace_binding'):
            payload['workspace_binding'] = connector['workspace_binding']
            if connector.get('target_folder_id'):
                payload['folder_id'] = connector['target_folder_id']
        app.invoke('web_command', {'payload': payload})
        self.wait(app, lambda s: os.path.realpath((s.get('connector') or {}).get('folder') or '') == os.path.realpath(str(folder)), 30, 'the linked test folder')

    def restore_folders(self, app):
        """Link each touched project back to the folder it had before the run, so the
        person's own VibeZ does not open on a test workspace afterwards."""
        restored = {}
        inside = lambda folder: os.path.realpath(folder).startswith(os.path.realpath(str(self.output)) + os.sep)
        for project, folder in self.original_folders.items():
            try:
                if folder and os.path.isdir(folder) and inside(folder):
                    # The wrapper only lets the test choose folders inside its own
                    # output directory, so only this run's workspaces can be relinked.
                    app.command('choose_folder', path=folder)
                    app.invoke('web_command', {'payload': {'action': 'web_link', 'project_id': project, 'path': folder}})
                    restored[project] = folder
                elif not folder:
                    app.invoke('web_command', {'payload': {'action': 'web_unlink', 'project_id': project}})
                    restored[project] = None
                else:
                    restored[project] = 'left (was %s, outside this run)' % folder
            except SelfTestError as error:
                restored[project] = 'failed: %s' % error
        self.report['restored_folders'] = restored
        self.save()
        return restored

    def sent_state(self, app, marker, label_pattern):
        try:
            return json.loads(app.eval('mistral', MISTRAL_SENT.replace('__MARK__', json.dumps(marker)).replace('__FULL__', json.dumps(marker + SENT_REQUEST)).replace('__LABEL__', json.dumps(label_pattern))))
        except (SelfTestError, ValueError) as error:
            return {'found': False, 'error': str(error)[:120]}

    def real_click(self, app, point_script):
        point = json.loads(app.eval('mistral', point_script))
        if point.get('ok'):
            app.input('click', x=point['x'], y=point['y'])
        return point

    def trust(self, app):
        try:
            return json.loads(app.eval('mistral', MISTRAL_TRUST))
        except (SelfTestError, ValueError):
            return {}

    def type_message(self, app, text):
        """Put one message in the composer: with real keys after a real click in it, or by script."""
        try:
            if self.real_input:
                app.eval('mistral', MISTRAL_TRUST_WATCH)
                # Right after a send Mistral redraws the page; a person waits for
                # the message box to be back before typing the next message.
                waited = time.time()
                point = self.real_click(app, MISTRAL_EDITOR_POINT)
                while not point.get('ok') and time.time() - waited < 20:
                    time.sleep(1)
                    point = self.real_click(app, MISTRAL_EDITOR_POINT)
                typed = {'ok': bool(point.get('ok')), 'input': 'real', 'point': point, 'editor_after_s': round(time.time() - waited, 1)}
                if typed['ok']:
                    time.sleep(0.6)
                    typed['keys'] = app.input('text', text=text).get('sent')
            else:
                typed = json.loads(app.eval('mistral', MISTRAL_SEND.replace('__TEXT__', json.dumps(text))))
                typed['input'] = 'synthetic'
            time.sleep(2)  # ProseMirror reads the insertion back a moment later
            typed['text'] = json.loads(app.eval('mistral', MISTRAL_COMPOSER_TEXT)).get('text')
        except (SelfTestError, ValueError) as error:
            typed = {'ok': False, 'error': str(error)[:120]}
        return typed

    def press_send(self, app, via):
        if not self.real_input:
            return app.eval('mistral', MISTRAL_CLICK_SEND if via == 'click' else MISTRAL_PRESS_ENTER)
        # Linking can reload the page after the draft was typed (the draft is put
        # back); the watch from typing is then gone, so watch the send itself too.
        try:
            app.eval('mistral', MISTRAL_TRUST_WATCH)
        except SelfTestError:
            pass
        if via == 'click':
            point = self.real_click(app, MISTRAL_SEND_POINT)
            return 'clicked' if point.get('ok') else 'no-button: %s' % (point.get('reason') or point.get('hit'))
        app.input('key', key='Enter')
        return 'enter'

    def await_sent(self, app, marker, label_pattern, result, start, timeout=45, retry_enter=True):
        """Wait until the message shows on the page; the result is what a person sees."""
        state = None
        deadline = time.time() + timeout
        pressed_enter = False
        while time.time() < deadline:
            time.sleep(1.5)
            state = self.sent_state(app, marker, label_pattern)
            if state.get('found') and not (state.get('composer_text') or '').startswith(marker):
                result['appeared_after_s'] = round(time.time() - start, 1)
                # The page script hides the chip and its separator a moment after the
                # message renders; give it a few seconds before judging the gap.
                # A Code project moves to the session page meanwhile: the message is
                # gone for a moment and then rendered again.
                settle = time.time() + 10
                seen = state
                while (state.get('message_leading_space') or not state.get('found')) and time.time() < settle:
                    time.sleep(1)
                    state = self.sent_state(app, marker, label_pattern)
                    if state.get('found'):
                        seen = state
                if not state.get('found'):
                    state = seen
                result['settled_after_s'] = round(time.time() - start, 1)
                break
            if retry_enter and not pressed_enter and time.time() - start > 8:
                pressed_enter = True
                result['sent_via'] = '%s, then %s' % (result['sent_via'], self.press_send(app, 'enter'))
        if result['appeared_after_s'] is None:
            try:
                refused = json.loads(app.eval('mistral', MISTRAL_REFUSALS))
            except (SelfTestError, ValueError):
                refused = []
            if refused:
                result['refused_by_mistral'] = refused[:5]
        if self.real_input:
            result['trusted_events'] = self.trust(app)
        return state

    def send_message(self, app, marker, label_pattern, timeout=45, via='click', typed=None):
        """Type one short message beside the connector chip, send it, and read back what a person sees.
        With `typed` the message is already in the composer (written before the link was ready)."""
        result = {'typed': False, 'sent_via': None, 'appeared_after_s': None}
        if typed is None:
            typed = self.type_message(app, marker + SENT_REQUEST)
        else:
            try:
                typed = dict(typed, text=json.loads(app.eval('mistral', MISTRAL_COMPOSER_TEXT)).get('text'))
            except (SelfTestError, ValueError) as error:
                typed = {'ok': False, 'error': str(error)[:120]}
        result['typed'] = bool(typed.get('ok')) and marker in (typed.get('text') or '')
        result['input'] = typed.get('input')
        if not result['typed']:
            result['typing'] = typed
            return result, None
        start = time.time()
        try:
            app.eval('mistral', MISTRAL_WATCH_REFUSALS)
        except SelfTestError:
            pass
        result['sent_via'] = self.press_send(app, via)
        state = self.await_sent(app, marker, label_pattern, result, start, timeout)
        return result, state

    def stop_code_session(self, app):
        """Stop the Code session this run started; a running one counts toward Mistral's concurrent limit."""
        try:
            opened = app.eval('mistral', MISTRAL_SESSION_MENU)
            if opened != 'opened':
                return opened
            time.sleep(1.5)
            chosen = app.eval('mistral', MISTRAL_SESSION_STOP)
            if chosen != 'chosen':
                return chosen
            time.sleep(1.5)
            confirmed = app.eval('mistral', MISTRAL_SESSION_STOP_CONFIRM)
            time.sleep(3)
            return confirmed
        except SelfTestError as error:
            return 'failed: %s' % str(error)[:120]

    def scenario_send_message(self, app, language, connector_id):
        """Scenario 1b: a real message beside the hidden Work chip reads exactly as typed."""
        scenario = {'name': 'send_message', 'language': language, 'passed': False, 'checks': {}}
        marker = '%s %s' % (SENT_PREFIX, uuid.uuid4().hex[:8])
        before = self.sent_state(app, marker, WORK_LABEL)
        scenario['composer_before'] = {k: before.get(k) for k in ('composer_hidden_atoms', 'composer_visible_atoms', 'label_visible_on_page', 'quiet_hidden')}
        sending, state = self.send_message(app, marker, WORK_LABEL)
        scenario['sending'] = sending
        scenario['sent'] = state
        # Mistral's answer and its tool lines arrive a little later; look again.
        time.sleep(20)
        later = self.sent_state(app, marker, WORK_LABEL)
        scenario['later'] = {k: later.get(k) for k in ('label_visible_on_page', 'label_in_dom', 'quiet_hidden', 'composer_hidden_atoms', 'composer_visible_atoms', 'path')}
        chat = app.eval('mistral', 'location.href')
        if isinstance(chat, str) and re.fullmatch(r'https://chat\.mistral\.ai/work/[0-9a-f-]{36}', chat):
            self.chat_url = chat
        checks = scenario['checks']
        checks['typed_beside_chip'] = sending.get('typed') is True and (before.get('composer_hidden_atoms') or 0) >= 1
        checks['sent'] = bool(state and state.get('found'))
        checks['message_text_exact'] = bool(state and state.get('message_text_exact'))
        checks['no_leading_space'] = bool(state) and state.get('message_leading_space') is False
        checks['label_hidden_in_message'] = bool(state) and state.get('message_label_visible') is False
        checks['label_hidden_on_page'] = bool(state) and state.get('label_visible_on_page') is False and later.get('label_visible_on_page') is False
        checks['reference_kept'] = bool(state) and ((state.get('message_hidden_chips') or 0) >= 1 or state.get('label_in_dom') is True)
        checks['composer_cleared'] = bool(state) and not (state.get('composer_text') or '').startswith(SENT_PREFIX)
        scenario['passed'] = all(checks.values())
        return scenario

    def scenario_code_project(self, app, draft_first=False):
        """Scenario 6: a Code project's "VibeZ · <project>" title chip is hidden in the composer and in a sent message.
        With draft_first the message is written before the link is ready, as a person in a hurry does;
        it must still leave with the project reference."""
        scenario = {'name': 'code_draft_before_link' if draft_first else 'code_title_chip', 'passed': False, 'checks': {}}
        key = 'code-' + self.args.code_project_id
        if draft_first:
            self.leave_project(app)
            time.sleep(2)
        snap = self.goto_code_project(app)
        connector = snap['connector']
        title = 'VibeZ · ' + (connector['project'].get('name') or '')
        title_pattern = re.escape(title)
        cleanup = self.engine_connectors(app, remove=True, project=key)
        scenario['cleanup_before'] = cleanup
        if cleanup.get('error') == 'no_key':
            scenario['note'] = 'No API key before the first link in this process; connectors are removed after the scenario instead'
        elif cleanup.get('error'):
            raise SelfTestError('Could not clean the Code test project connectors: %s' % cleanup['error'])
        current = connector.get('folder') or ''
        if not current or os.path.realpath(current) != os.path.realpath(str(self.args.workspace_c)):
            self.link_folder(app, connector, key, self.args.workspace_c)
        marker = '%s %s' % (SENT_PREFIX, uuid.uuid4().hex[:8])

        def clear_leftover():
            try:
                leftover = json.loads(app.eval('mistral', MISTRAL_CLEAR_TEST_DRAFT.replace('__PREFIX__', json.dumps(SENT_PREFIX))))
            except (SelfTestError, ValueError) as error:
                leftover = {'cleared': False, 'error': str(error)[:120]}
            if leftover.get('cleared'):
                scenario['leftover_test_draft_cleared'] = leftover
                time.sleep(6)  # the page script puts the reference back in the emptied composer
        typed = None
        if draft_first:
            clear_leftover()
            typed = self.type_message(app, marker + SENT_REQUEST)
            scenario['draft'] = {k: typed.get(k) for k in ('ok', 'input', 'text', 'error')}
        record = self.connect(app, manual=True, label='code_link', timeout=self.args.connect_timeout, project=key)
        scenario['connection'] = record
        time.sleep(4)
        if not draft_first:
            clear_leftover()
        before = self.sent_state(app, marker, title_pattern)
        scenario['composer_before'] = {k: before.get(k) for k in ('composer_text', 'composer_hidden_atoms', 'composer_visible_atoms', 'label_visible_on_page', 'label_in_dom', 'titles', 'quiet_hidden')}
        sending, state = self.send_message(app, marker, title_pattern, via='enter' if draft_first else 'click', typed=typed)
        scenario['sending'] = sending
        scenario['sent'] = state
        time.sleep(20)
        later = self.sent_state(app, marker, title_pattern)
        scenario['later'] = {k: later.get(k) for k in ('label_visible_on_page', 'label_in_dom', 'quiet_hidden', 'titles', 'path', 'message_leading_space', 'message_text_exact')}
        scenario['session_stop'] = self.stop_code_session(app) if (state and state.get('found')) or later.get('found') else 'nothing sent'
        scenario['cleanup_after'] = self.engine_connectors(app, remove=True, project=key)
        checks = scenario['checks']
        checks['connected'] = record['status'] == 'connected'
        checks['title_known_to_page'] = (before.get('titles') or 0) >= 1
        if draft_first:
            checks['draft_survived_link'] = (before.get('composer_text') or '').startswith(SENT_PREFIX)
        else:
            checks['composer_chip_hidden'] = (before.get('composer_hidden_atoms') or 0) >= 1
        checks['title_hidden_before_send'] = before.get('label_visible_on_page') is False
        checks['sent'] = bool(state and state.get('found'))
        checks['message_text_exact'] = bool(state and state.get('message_text_exact'))
        checks['no_leading_space'] = bool(state) and state.get('message_leading_space') is False
        checks['title_hidden_in_message'] = bool(state) and state.get('message_label_visible') is False
        if self.real_input:
            checks['real_input_trusted'] = (sending.get('trusted_events') or {}).get('trusted_keys', 0) >= 1
        checks['title_hidden_on_page'] = bool(state) and state.get('label_visible_on_page') is False and later.get('label_visible_on_page') is False
        checks['reference_kept'] = bool(state) and ((state.get('message_hidden_chips') or 0) >= 1 or state.get('label_in_dom') is True)
        checks['test_session_stopped'] = scenario['session_stop'] == 'stopped'
        checks['test_connectors_removed'] = not scenario['cleanup_after'].get('error') and (scenario['cleanup_after'].get('removed') or {}).get('removed', 0) >= 1
        scenario['passed'] = all(checks.values())
        return scenario

    # ---- a person's order of actions -------------------------------------
    def message_checks(self, sending, state):
        checks = {'typed': sending.get('typed') is True, 'sent': bool(state and state.get('found'))}
        checks['message_text_exact'] = bool(state and state.get('message_text_exact'))
        checks['no_leading_space'] = bool(state) and state.get('message_leading_space') is False
        checks['label_hidden_in_message'] = bool(state) and state.get('message_label_visible') is False
        checks['reference_kept'] = bool(state) and ((state.get('message_hidden_chips') or 0) >= 1 or state.get('label_in_dom') is True)
        checks['composer_cleared'] = bool(state) and not (state.get('composer_text') or '').startswith(SENT_PREFIX)
        if self.real_input:
            checks['real_input_trusted'] = (sending.get('trusted_events') or {}).get('trusted_keys', 0) >= 1
        return checks

    def open_project_unlinked(self, app):
        """The state of a first link: the project page is open, this installation's test
        connectors are gone and the project has a folder VibeZ was never allowed to link
        by itself. (Removing the connectors alone leaves the earlier approval, and VibeZ
        would link again on its own before a person could act.)"""
        self.leave_project(app)
        snap = self.goto_project(app)
        time.sleep(3)
        cleanup = self.engine_connectors(app, remove=True)
        if cleanup.get('error'):
            raise SelfTestError('Could not clean the test project connectors: %s' % cleanup['error'])
        connector = snap['connector']
        current = connector.get('folder') or ''
        folder = self.args.workspace_a if os.path.realpath(current) != os.path.realpath(self.args.workspace_a) else self.args.workspace_b
        self.link_folder(app, connector, self.project, folder)
        time.sleep(3)
        return cleanup

    def link_after_open(self, app, since, label, timeout=None):
        """The link a person waits for after opening the page: VibeZ's own attempt when it started, else the button."""
        deadline = time.time() + 15
        automatic = False
        while time.time() < deadline and not automatic:
            auto = app.snapshot().get('auto') or {}
            fresh = auto.get('project_id') == self.project and auto.get('at', 0) >= since[0]
            automatic = fresh and auto.get('status') in ('starting', 'authorizing', 'connecting', 'registering', 'connected')
            if fresh and auto.get('status') in ('paused', 'cancelled', 'error'):
                break  # VibeZ asks for the button: a person presses it
            if not automatic:
                time.sleep(0.5)
        return self.connect(app, manual=not automatic, label=label, timeout=timeout or self.args.connect_timeout, since=since)

    def scenario_draft_before_link(self, app):
        """H1: the message is typed first, then the person presses Connect and sends with Enter."""
        scenario = {'name': 'draft_before_link', 'passed': False, 'checks': {}}
        started = time.time()
        scenario['cleanup'] = self.open_project_unlinked(app)
        marker = '%s %s' % (SENT_PREFIX, uuid.uuid4().hex[:8])
        typed = self.type_message(app, marker + SENT_REQUEST)
        scenario['draft'] = {k: typed.get(k) for k in ('ok', 'input', 'text', 'error', 'point')}
        record = self.connect(app, manual=True, label='draft_before_link', timeout=self.args.connect_timeout)
        scenario['connection'] = record
        time.sleep(4)
        scenario['transport'] = self.transport_check(started, record)
        scenario['composer'] = self.chip_summary(self.chips(app), record.get('connector_id'))
        before = self.sent_state(app, marker, WORK_LABEL)
        sending, state = self.send_message(app, marker, WORK_LABEL, via='enter', typed=typed)
        scenario['sending'] = sending
        scenario['sent'] = state
        chat = app.eval('mistral', 'location.href')
        if isinstance(chat, str) and re.fullmatch(r'https://chat\.mistral\.ai/work/[0-9a-f-]{36}', chat):
            self.chat_url = chat
        checks = scenario['checks']
        checks['connected'] = record['status'] == 'connected'
        checks['no_blocked_draft'] = ((record.get('error_report') or {}).get('work_step') or {}).get('state') != 'blocked-draft' and record.get('work_failure') is None
        checks['draft_survived_link'] = (before.get('composer_text') or '').startswith(SENT_PREFIX)
        checks['chip_beside_draft'] = scenario['composer'].get('current_connector_chips', 0) >= 1
        checks.update(self.message_checks(sending, state))
        scenario['passed'] = all(checks.values())
        return scenario

    def scenario_send_with_selection(self, app):
        """H2: part of the message is selected when Send is clicked; nothing may replace the selection."""
        scenario = {'name': 'send_with_selection', 'passed': False, 'checks': {}}
        marker = '%s %s' % (SENT_PREFIX, uuid.uuid4().hex[:8])
        typed = self.type_message(app, marker + SENT_REQUEST)
        if self.real_input and typed.get('ok'):
            for _ in range(6):
                app.input('key', key='Left', mods=['shift'])
            time.sleep(0.5)
            scenario['selected'] = app.eval('mistral', 'String(window.getSelection()).length')
        sending, state = self.send_message(app, marker, WORK_LABEL, via='click', typed=typed)
        scenario['sending'] = sending
        scenario['sent'] = state
        checks = scenario['checks']
        if self.real_input:
            checks['selection_made'] = scenario.get('selected') in (6, '6')
        checks.update(self.message_checks(sending, state))
        scenario['passed'] = all(checks.values())
        return scenario

    def scenario_rapid_sends(self, app):
        """H3: a second message is typed and sent right behind the first one."""
        scenario = {'name': 'rapid_sends', 'passed': False, 'checks': {}}
        first = '%s %s' % (SENT_PREFIX, uuid.uuid4().hex[:8])
        second = '%s %s' % (SENT_PREFIX, uuid.uuid4().hex[:8])
        typed = self.type_message(app, first + SENT_REQUEST)
        one = {'typed': bool(typed.get('ok')) and first in (typed.get('text') or ''), 'sent_via': None, 'appeared_after_s': None}
        start = time.time()
        one['sent_via'] = self.press_send(app, 'enter')
        time.sleep(1.5)
        typed = self.type_message(app, second + SENT_REQUEST)
        two = {'typed': bool(typed.get('ok')) and second in (typed.get('text') or ''), 'sent_via': None, 'appeared_after_s': None, 'typing': typed}
        start_two = time.time()
        two['sent_via'] = self.press_send(app, 'enter')
        state_one = self.await_sent(app, first, WORK_LABEL, one, start, timeout=45, retry_enter=False)
        # Mistral holds a message back while it still answers the previous one;
        # a person presses Enter again, and so does the wait below.
        state_two = self.await_sent(app, second, WORK_LABEL, two, start_two, timeout=120)
        scenario['first'] = {'sending': one, 'sent': state_one}
        scenario['second'] = {'sending': two, 'sent': state_two}
        checks = scenario['checks']
        for name, sending, state in (('first', one, state_one), ('second', two, state_two)):
            for key, value in self.message_checks(sending, state).items():
                checks['%s_%s' % (name, key)] = value
        scenario['passed'] = all(checks.values())
        return scenario

    def scenario_leave_during_link(self, app):
        """H4: the person presses Connect, clicks away while the link is being made and comes back; the link must then be made and work."""
        scenario = {'name': 'leave_during_link', 'passed': False, 'checks': {}}
        scenario['cleanup'] = self.open_project_unlinked(app)
        app.invoke('web_command', {'payload': {'action': 'web_connect', 'project_id': self.project}})
        scenario['started_by'] = 'button'
        time.sleep(5)
        scenario['status_when_leaving'] = (app.snapshot().get('auto') or {}).get('status')
        self.leave_project(app)
        time.sleep(6)
        scenario['status_while_away'] = (app.snapshot().get('auto') or {}).get('status')
        back = (now_ms() - 500, self.diagnostics.timing_mtime())
        self.goto_project(app)
        record = self.link_after_open(app, back, 'leave_during_link')
        scenario['connection'] = record
        time.sleep(4)
        scenario['composer'] = self.chip_summary(self.chips(app), record.get('connector_id'))
        scenario['connectors'] = self.engine_connectors(app, remove=False)
        marker = '%s %s' % (SENT_PREFIX, uuid.uuid4().hex[:8])
        sending, state = self.send_message(app, marker, WORK_LABEL)
        scenario['sending'] = sending
        scenario['sent'] = state
        checks = scenario['checks']
        checks['connected'] = record['status'] == 'connected'
        checks['chip_in_composer'] = scenario['composer'].get('current_connector_chips', 0) >= 1
        checks['no_stale_chip'] = scenario['composer'].get('stale_connector_chips') == 0
        checks['one_connector'] = scenario['connectors'].get('work') == 1 and scenario['connectors'].get('count') == 1
        checks.update(self.message_checks(sending, state))
        scenario['passed'] = all(checks.values())
        return scenario

    def human_order(self, app):
        """The Work scenarios in a person's order of actions; one failure does not hide the next."""
        results = []
        for scenario in (self.scenario_draft_before_link, self.scenario_send_with_selection, self.scenario_rapid_sends, self.scenario_leave_during_link):
            try:
                result = scenario(app)
            except SelfTestError as error:
                result = {'name': scenario.__name__.replace('scenario_', ''), 'passed': False, 'error': str(error)[:300]}
            results.append(result)
            self.report['human_order'] = results
            self.save()
        return results

    def leave_draft(self, app, language):
        """Leave a draft (text next to the connector chip Work inserted) for the restart scenario."""
        if self.chat_url is None:
            self.chat_url = self.project_chat(app)
        on_chat = self.goto_chat(app)
        if on_chat:
            # The chat's own composer: the chip is inserted there once the
            # connector is chosen for this conversation as well.
            time.sleep(2)
        try:
            result = json.loads(app.eval('mistral', MISTRAL_DRAFT.replace('__TEXT__', json.dumps(DRAFT_TEXT))))
        except (SelfTestError, ValueError) as error:
            result = {'ok': False, 'error': str(error)[:120]}
        time.sleep(2)
        chips = self.chips(app)
        return {'inserted': bool(result.get('ok')), 'draft_text_present': DRAFT_TEXT in (chips.get('text') or ''), 'vibez_chips': len(chips.get('chips') or []), 'on_project_chat': on_chat, 'path': chips.get('path')}

    def scenario_restart(self, app, language, previous_connector):
        """Scenario 2 (after the app restarted): the connector is kept when the tunnel
        helper survived the restart (registered, same connector), or replaced when
        the address changed (replaced, created, new connector); attached either way."""
        scenario = {'name': 'restart_relink', 'language': language, 'passed': False, 'checks': {}}
        self.goto_project(app)
        time.sleep(3)
        scenario['on_project_chat'] = self.goto_chat(app)
        before = self.chips(app)
        scenario['composer_before'] = self.chip_summary(before, previous_connector)
        scenario['composer_before']['old_chip_restored'] = scenario['composer_before'].get('vibez_chips', 0) >= 1
        record = self.connect(app, manual=True, label='restart_relink', timeout=self.args.connect_timeout, adopt=True)
        scenario['connection'] = record
        names = self.step_names(record)
        time.sleep(3)
        after = self.chips(app)
        scenario['composer_after'] = self.chip_summary(after, record.get('connector_id'), previous_connector)
        checks = scenario['checks']
        reused = 'registered' in names and 'replaced' not in names
        scenario['tunnel_reused'] = reused
        checks['connected'] = record['status'] == 'connected'
        checks['relinked'] = reused or ({'replaced', 'created'} <= set(names))
        checks['attached'] = 'attached' in names
        checks['connector_consistent'] = bool(record.get('connector_id')) and (
            record.get('connector_id') == previous_connector if reused else record.get('connector_id') != previous_connector)
        step = (record.get('error_report') or {}).get('work_step') or {}
        checks['no_blocked_draft'] = step.get('state') != 'blocked-draft' and record.get('work_failure') is None
        checks['one_current_chip'] = scenario['composer_after'].get('current_connector_chips') == 1
        checks['no_stale_chip'] = scenario['composer_after'].get('stale_connector_chips') == 0
        if not scenario['composer_before']['old_chip_restored']:
            scenario['note'] = 'Mistral did not restore a VibeZ connector chip after the restart; the stale-chip removal was not exercised in this run.'
        elif reused:
            scenario['note'] = 'The tunnel helper survived the restart: the restored chip is the current connector, no replacement was needed.'
        scenario['passed'] = all(checks.values())
        return scenario

    def scenario_leave_return(self, app, language, current_connector):
        """Scenario 3: navigate away and back, press Connect -> registered, attached within seconds, no new connector.

        Since Alpha 30 connecting is manual by default: returning to a project
        leaves it paused until Connect is pressed, so the scenario presses it."""
        scenario = {'name': 'leave_return', 'language': language, 'passed': False, 'checks': {}}
        self.leave_project(app)
        time.sleep(2)
        app.invoke('web_surface', {'show': True, 'route': self.project_url})
        record = self.connect(app, manual=True, label='leave_return', timeout=max(60, RETURN_SECONDS * 4))
        scenario['connection'] = record
        names = self.step_names(record)
        checks = scenario['checks']
        checks['connected'] = record['status'] == 'connected'
        checks['registered'] = 'registered' in names
        checks['attached'] = 'attached' in names
        checks['no_new_connector'] = not ({'created', 'replaced'} & set(names))
        checks['same_connector'] = record.get('connector_id') == current_connector
        checks['within_seconds'] = (record.get('duration_s') or 9999) <= RETURN_SECONDS
        scenario['passed'] = all(checks.values())
        return scenario


def preflight(args, environment):
    binary = Path(args.binary).resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise SelfTestError('Binary not found or not executable: %s' % binary)
    version = subprocess.run([str(binary), '--version'], capture_output=True, text=True, timeout=20).stdout.strip()
    if 'standalone app' not in version:
        raise SelfTestError('Unexpected binary: %s' % version[:80])
    if not environment.get('DISPLAY'):
        raise SelfTestError('DISPLAY is not set; the live self-test needs the desktop session')
    running = subprocess.run(['pgrep', '-x', 'vibez4-alpha'], capture_output=True, text=True).stdout.split()
    if running:
        raise SelfTestError('VibeZ V4 Alpha is already running (pid %s). Close it first.' % ', '.join(running))
    engines = subprocess.run(['pgrep', '-f', 'standalone_engine.py'], capture_output=True, text=True).stdout.split()
    if engines:
        raise SelfTestError('A VibeZ engine is still running (pid %s). Stop it first.' % ', '.join(engines))
    return version


def main():
    if '--engine-source' in sys.argv:
        engine_wrapper()
        return
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--binary', type=Path, default=BASE / 'desktop/src-tauri/target-live/release/vibez4-alpha',
                        help='vibez4-alpha built with --features native-smoke')
    parser.add_argument('--output', type=Path, default=BASE / 'artifacts/live-work-self-test')
    parser.add_argument('--project-id', default=DEFAULT_PROJECT)
    parser.add_argument('--project-name', default=DEFAULT_NAME, help='expected visible project name; empty to skip the check')
    parser.add_argument('--languages', default='current,pl,en', help='comma separated; "current" is the app language at start')
    parser.add_argument('--data-dir', type=Path, default=Path.home() / '.local/share' / APP_ID / 'standalone/web-connector')
    parser.add_argument('--config-dir', type=Path, default=Path.home() / '.config' / APP_ID)
    parser.add_argument('--connect-timeout', type=int, default=420)
    parser.add_argument('--code-project-id', default=str(LOCAL.get('code_project_id') or ''), help='UUID of a Code test project for the title-chip scenario; empty skips it')
    parser.add_argument('--code-project-name', default=str(LOCAL.get('code_project_name') or ''), help='expected visible name of that Code project; empty to skip the check')
    parser.add_argument('--synthetic-input', action='store_true', help='type and send by page script instead of real keys and clicks')
    parser.add_argument('--only-human', action='store_true', help='run only the human-order scenarios (a quick pass while working on them)')
    parser.add_argument('--skip-human', action='store_true', help='skip the scenarios that follow a person\'s order of actions')
    parser.add_argument('--switch-with', default='', help='UUID of a second linked Work test project: run only the switch scenario between the two')
    parser.add_argument('--switch-rounds', type=int, default=3)
    parser.add_argument('--switch-dwell', type=int, default=45, help='seconds to stay on each project before switching')
    parser.add_argument('--skip-send', action='store_true', help='do not send real messages (skips the sent-message checks)')
    args = parser.parse_args()
    if not UUID_RE.fullmatch(args.project_id):
        parser.error('--project-id must be a Work project UUID (or set project_id in tools/live-work-self-test.local.json)')
    if args.code_project_id and not UUID_RE.fullmatch(args.code_project_id):
        parser.error('--code-project-id must be a Code project UUID')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    artifacts = (BASE / 'artifacts').resolve()
    if output == artifacts or artifacts not in output.parents:
        parser.error('--output must be a folder inside %s' % artifacts)
    args.workspace_a = output / 'workspace-a'
    args.workspace_b = output / 'workspace-b'
    args.workspace_c = output / 'workspace-c'
    for folder in (args.workspace_a, args.workspace_b, args.workspace_c):
        folder.mkdir(exist_ok=True)
        (folder / 'README.txt').write_text('VibeZ live Work self-test workspace. Files here are test data only.\n')
    environment = dict(os.environ)
    environment['VIBEZ4_LIVE_WORK_DIR'] = str(output)
    environment.pop('VIBEZ4_CODE_PROBE_DIR', None)
    environment.pop('VIBEZ4_LIVE_TEST_OUTPUT', None)
    diagnostics = Diagnostics(args.data_dir)
    language_file = args.config_dir / 'language.json'
    original_language_text = language_file.read_text() if language_file.exists() else None

    try:
        version = preflight(args, environment)
    except SelfTestError as error:
        write_json(output / 'report.json', {'passed': False, 'errors': [str(error)]})
        print('FAILED:', error)
        return 2

    run = Run(args, output, diagnostics)
    run.report['version'] = version
    try:
        mcp = subprocess.run([sys.executable, str(BASE / 'tools/check-mcp-versions.py'), '--offline', '--json'], capture_output=True, text=True, timeout=30)
        run.report['mcp_versions'] = json.loads(mcp.stdout) if mcp.stdout.strip() else {'error': 'no report'}
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        run.report['mcp_versions'] = {'error': str(error)[:120]}
    app = None
    passed = False
    def restore_after_failure():
        # A failed scenario must not leave the person's project on a test folder.
        try:
            if app is not None and app.process is not None and app.process.poll() is None:
                run.restore_folders(app)
        except Exception as error:
            run.report['errors'].append('restore_folders: %s' % str(error)[:200])

    try:
        with (output / 'app.log').open('a') as log:
            def start_app():
                nonlocal app
                app = App(Path(args.binary).resolve(), output, log, environment)
                ready = app.start()
                run.report['app_starts'] += 1
                if not ready.get('on_screen_1'):
                    raise SelfTestError('The main window is not on the configured screen 1')
                app.install_agent()
                app.invoke('web_command', {'payload': {'action': 'web_hello'}})
                time.sleep(1)
                return ready

            def stop_app():
                nonlocal app
                if app:
                    app.quit()
                    app = None
                time.sleep(3)

            ready = start_app()
            run.report['window'] = {'on_screen_1': ready.get('on_screen_1'), 'visible': ready.get('visible')}
            current_language = (app.snapshot().get('language') or {}).get('language') or 'system'
            run.report['original_language'] = current_language
            languages = []
            for code in [part.strip() for part in args.languages.split(',') if part.strip()]:
                code = current_language if code == 'current' else code
                if code not in languages:
                    languages.append(code)
            run.report['languages'] = languages

            if args.switch_with:
                scenario = run.scenario_switch(app, [args.project_id, args.switch_with], args.switch_rounds, args.switch_dwell)
                passed = scenario['passed']
                if not passed:
                    run.report['errors'].append('Scenario switch_projects failed: %s' % ', '.join(k for k, v in scenario['checks'].items() if not v))
                raise StopIteration
            # Process plan: each language run needs one restart between scenario 1 and 2.
            # P1: L1-s1 | restart | P2: L1-s2, L1-s3, L2-s1 | restart | P3: L2-s2, L2-s3, L3-s1 | restart | P4: L3-s2, L3-s3, final count
            previous = None  # (language, connector id after scenario 1)
            for index, language in enumerate([] if args.only_human else languages):
                record = {'language': language, 'scenarios': []}
                run.report['runs'].append(record)
                if language != current_language:
                    run.set_language(app, language)
                    current_language = language
                scenario = run.scenario_clean_link(app, language, first=(index == 0))
                record['scenarios'].append(scenario)
                run.save()
                if not scenario['passed']:
                    raise SelfTestError('Scenario clean_link (%s) failed' % language)
                connector_after_link = scenario['connection'].get('connector_id')
                if not args.skip_send:
                    scenario = run.scenario_send_message(app, language, connector_after_link)
                    record['scenarios'].append(scenario)
                    run.save()
                    if not scenario['passed']:
                        raise SelfTestError('Scenario send_message (%s) failed' % language)
                record['draft'] = run.leave_draft(app, language)
                run.save()
                stop_app()
                start_app()
                scenario = run.scenario_restart(app, language, connector_after_link)
                record['scenarios'].append(scenario)
                run.save()
                if not scenario['passed']:
                    raise SelfTestError('Scenario restart_relink (%s) failed' % language)
                current_connector = scenario['connection'].get('connector_id')
                scenario = run.scenario_leave_return(app, language, current_connector)
                record['scenarios'].append(scenario)
                run.save()
                if not scenario['passed']:
                    raise SelfTestError('Scenario leave_return (%s) failed' % language)
                previous = (language, current_connector)
            human_failed = []
            if not args.skip_human and not args.skip_send:
                human_failed = [item['name'] for item in run.human_order(app) if not item['passed']]
            final = run.engine_connectors(app, remove=False)
            run.report['final_connectors'] = final
            run.report['final_connectors']['exactly_one_work_connector'] = final.get('work') == 1 and final.get('count') == 1
            if run.report['original_language'] != current_language:
                run.set_language(app, run.report['original_language'])
                current_language = run.report['original_language']
            passed = run.report['final_connectors']['exactly_one_work_connector']
            if not passed:
                run.report['errors'].append('More or fewer than one VibeZ connector remains for the test project')
            if human_failed:
                passed = False
                run.report['errors'].append('Human-order scenarios failed: %s' % ', '.join(human_failed))
            if args.code_project_id:
                scenario = run.scenario_code_project(app)
                run.report['code_project'] = scenario
                run.save()
                if not scenario['passed']:
                    passed = False
                    run.report['errors'].append('Scenario code_title_chip failed')
                if not args.skip_human and not args.skip_send:
                    scenario = run.scenario_code_project(app, draft_first=True)
                    run.report['code_draft_before_link'] = scenario
                    run.save()
                    if not scenario['passed']:
                        passed = False
                        run.report['errors'].append('Scenario code_draft_before_link failed')
            run.restore_folders(app)
    except StopIteration:
        pass
    except SelfTestError as error:
        run.report['errors'].append(str(error))
        restore_after_failure()
    except Exception as error:  # report, never crash silently
        run.report['errors'].append('%s: %s' % (type(error).__name__, str(error)[:300]))
        restore_after_failure()
    finally:
        try:
            if app:
                app.quit()
        except Exception as error:
            run.report['errors'].append('quit: %s' % type(error).__name__)
        if original_language_text is not None:
            try:
                if language_file.read_text() != original_language_text:
                    language_file.write_text(original_language_text)
                    run.note('App language restored from the saved setting')
            except OSError:
                run.report['errors'].append('Could not restore language.json')
        for name in ('command.json', 'command.json.tmp'):
            try:
                (output / name).unlink()
            except FileNotFoundError:
                pass
        run.report['passed'] = passed and not run.report['errors']
        run.report['finished'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
        run.save()
    summary = {'passed': run.report['passed'], 'app_starts': run.report['app_starts'], 'runs': [
        {'language': item['language'], 'scenarios': [(s['name'], s['passed'], (s.get('connection') or {}).get('duration_s')) for s in item['scenarios']]}
        for item in run.report['runs']], 'final_connectors': run.report['final_connectors'],
        'code_project': (lambda s: s and {'passed': s['passed'], 'checks': s['checks']})(run.report.get('code_project')),
        'human_order': [(s['name'], s['passed'], [k for k, v in (s.get('checks') or {}).items() if not v] or s.get('error')) for s in run.report.get('human_order', [])],
        'code_draft_before_link': (lambda s: s and {'passed': s['passed'], 'checks': s['checks']})(run.report.get('code_draft_before_link')), 'errors': run.report['errors']}
    print(json.dumps(summary, indent=1))
    print('Report:', output / 'report.json')
    return 0 if run.report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
