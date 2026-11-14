#!/usr/bin/python3
"""Standalone VibeZ: local projects/history and one chat with optional MCP files."""
import collections
import copy
import importlib.util
import json
import os
import re
from pathlib import Path
import signal
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

# Load the bundled OS facade explicitly under isolated Python (-I).
import importlib.util as _cap_importlib
import sys as _cap_sys
from pathlib import Path as _CapPath
if '_vibez_capfs' not in _cap_sys.modules:
    _cap_spec = _cap_importlib.spec_from_file_location('_vibez_capfs', _CapPath(__file__).with_name('capfs.py'))
    _cap_module = _cap_importlib.module_from_spec(_cap_spec)
    _cap_sys.modules['_vibez_capfs'] = _cap_module
    try:
        _cap_spec.loader.exec_module(_cap_module)
    except BaseException:
        _cap_sys.modules.pop('_vibez_capfs', None)
        raise
os = _cap_sys.modules['_vibez_capfs']

_spec = importlib.util.spec_from_file_location('vibez_workspace', Path(__file__).with_name('workspace_engine.py'))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
VERSION = '4.0.0-beta.3'
SYNC_REASON = 'Automatic sync with the Mistral website is not available: no supported connection was found. Export a conversation to bring its context yourself.'


class Store:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
        path = directory / 'conversations.sqlite3'
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        path.chmod(0o600)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,folder TEXT);
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),title TEXT NOT NULL,context TEXT NOT NULL,events TEXT NOT NULL,updated REAL NOT NULL,folder TEXT);
            CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')
        if 'folder' not in {row['name'] for row in self.db.execute('PRAGMA table_info(conversations)')}:
            self.db.execute('ALTER TABLE conversations ADD COLUMN folder TEXT')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO projects VALUES(?,?,NULL)', ('default', 'Algemeen'))

    def project(self, project_id):
        with self.lock:
            row = self.db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
            if not row:
                raise ValueError('This project no longer exists')
            return dict(row)

    def new_project(self, name, *, project_id=None, folder=None):
        name = self.clean_name(name)
        with self.lock, self.db:
            project_id = project_id or uuid.uuid4().hex
            self.db.execute('INSERT INTO projects VALUES(?,?,?)', (project_id, name, folder))
        return project_id

    @staticmethod
    def clean_name(name):
        if not isinstance(name, str) or not name.strip() or len(name) > 100 or any(ord(c) < 32 for c in name):
            raise ValueError('Enter a name of 1 to 100 characters')
        return name.strip()

    def folder(self, project_id, path):
        with self.lock, self.db:
            self.db.execute('UPDATE projects SET folder=? WHERE id=?', (path, project_id))

    def rename(self, project_id, name):
        with self.lock, self.db:
            self.db.execute('UPDATE projects SET name=? WHERE id=?', (self.clean_name(name), project_id))

    def create_chat(self, project_id):
        project = self.project(project_id)
        chat_id = uuid.uuid4().hex
        with self.lock, self.db:
            self.db.execute('INSERT INTO conversations VALUES(?,?,?,?,?,?,?)', (chat_id, project_id, 'New conversation', json.dumps([{'role':'system','content':base.SYSTEM}]), '[]', time.time(),project['folder']))
        return chat_id

    def chat_folder(self, chat_id, path):
        with self.lock,self.db:
            self.db.execute('UPDATE conversations SET folder=? WHERE id=?',(path,chat_id))

    def chat(self, chat_id):
        with self.lock:
            row = self.db.execute('SELECT * FROM conversations WHERE id=?', (chat_id,)).fetchone()
            if not row:
                raise ValueError('This conversation no longer exists')
            value = dict(row)
        value['context'] = json.loads(value['context'])
        value['events'] = json.loads(value['events'])
        return value

    def save(self, chat_id, context, events):
        # UI history is inert on restore. Pending write approvals never survive
        # as executable actions; credentials/authentication are never stored.
        keep = {'user','assistant','tool','notice','error','approval','approval_done','approval_history'}
        saved = []
        for item in events:
            if item['type'] not in keep:
                continue
            item = copy.deepcopy(item)
            if item['type'] == 'approval':
                item['type'] = 'approval_history'
            saved.append(item)
        title = next((m['content'].strip().replace('\n',' ')[:70] for m in context if m.get('role') == 'user' and isinstance(m.get('content'), str)), 'New conversation')
        with self.lock, self.db:
            self.db.execute('UPDATE conversations SET title=?,context=?,events=?,updated=? WHERE id=?', (title,json.dumps(context,ensure_ascii=False),json.dumps(saved,ensure_ascii=False),time.time(),chat_id))

    def library(self):
        with self.lock:
            projects = [dict(r) for r in self.db.execute('SELECT * FROM projects ORDER BY name COLLATE NOCASE')]
            chats = [dict(r) for r in self.db.execute('SELECT id,project_id,title,updated FROM conversations ORDER BY updated DESC LIMIT 300')]
        return projects, chats

    def preference(self, key, value=None):
        with self.lock:
            if value is not None:
                with self.db:
                    self.db.execute('INSERT OR REPLACE INTO preferences VALUES(?,?)', (key,value))
                return value
            row = self.db.execute('SELECT value FROM preferences WHERE key=?', (key,)).fetchone()
            return row[0] if row else None

    def migrate(self, legacy):
        if self.preference('legacy_imported'):
            return
        if legacy and Path(legacy).is_file():
            try:
                content = Path(legacy).read_text()
                if len(content) > 1_000_000:
                    raise ValueError()
                folders = json.loads(content).get('folders', {})
                for key, folder in folders.items():
                    if not isinstance(key,str) or not isinstance(folder,str) or not os.is_absolute(folder):
                        continue
                    with self.lock:
                        exists = self.db.execute('SELECT 1 FROM projects WHERE id=?',(key,)).fetchone()
                    if not exists:
                        self.new_project(Path(folder).name or 'Imported project', project_id=key, folder=folder)
            except (OSError, ValueError, TypeError, AttributeError):
                # Legacy data remains untouched and can be retried manually.
                return
        self.preference('legacy_imported','yes')


class StandaloneEngine(base.Engine):
    def __init__(self, emit, directory, *, legacy=None, provider=None, auth=None, auto_api_factory=None):
        self.external_output = emit
        web_spec = importlib.util.spec_from_file_location('vibez_web_connector', Path(__file__).with_name('web_connector.py'))
        web_module = importlib.util.module_from_spec(web_spec); web_spec.loader.exec_module(web_module)
        self.web = web_module.Connector(emit, Path(directory) / 'web-connector')
        auto_spec=importlib.util.spec_from_file_location('vibez_automatic_connector',Path(__file__).with_name('automatic_connector.py'))
        auto_module=importlib.util.module_from_spec(auto_spec);auto_spec.loader.exec_module(auto_module)
        self.automatic=auto_module.AutomaticConnector(self,api_factory=auto_api_factory or auto_module.MistralAPI)
        self.store = Store(directory)
        self.store.migrate(legacy)
        self.chat_id = None
        self.transition = None
        self.restoring = False
        super().__init__(self.route_event, provider=provider or self.api_completion, auth=auth)
        # Mistral access of this installation (file mode 600 in the profile), so a
        # restart needs no new sign-in. Removed again when Mistral rejects it.
        self.access_file = Path(directory) / 'web-connector' / 'mistral-access.json'
        saved = self._load_access()
        if saved: self.key = saved
        chosen = self.store.preference('last_chat')
        if chosen:
            try:
                self.store.chat(chosen)
            except ValueError:
                chosen = None
        if not chosen:
            chosen = self.store.create_chat('default')
        self.activate(chosen)

    def _load_access(self):
        try:
            raw = self.access_file.read_bytes()
            if len(raw) > 8192: return ''
            key = json.loads(raw).get('api_key')
            return key if isinstance(key, str) and 1 <= len(key) <= 4096 and not any(c.isspace() for c in key) else ''
        except (OSError, ValueError, AttributeError):
            return ''

    def remember_key(self, key):
        with self.lock: self.key = key
        try:
            self.access_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = self.access_file.with_suffix('.tmp')
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as f: json.dump({'api_key': key, 'saved': time.time()}, f)
            os.replace(tmp, self.access_file)
        except OSError:
            pass

    def forget_key(self):
        with self.lock: self.key = ''
        try: self.access_file.unlink()
        except OSError: pass

    def emit(self, event):
        if event['type']=='approval_history':
            with self.lock:
                size=len(json.dumps(event))
                self.ui_events.append((event,size))
                self.ui_bytes+=size
                self.output(event)
        else:
            super().emit(event)

    def route_event(self, event):
        self.external_output(event)
        if self.chat_id and not self.restoring and event['type'] in ('user','done'):
            self.persist()
            self.library()

    def persist(self):
        if self.chat_id:
            self.store.save(self.chat_id, self.messages, [e for e,_ in self.ui_events])

    def library(self):
        projects, chats = self.store.library()
        self.external_output({'type':'library','projects':projects,'chats':chats,'active_chat':self.chat_id,'active_project':self.project['id'] if self.project else None})

    def state(self):
        self.emit({'type':'state','connected':bool(self.key),'workspace':self.workspace.root if self.workspace else None,
            'mcp':bool(self.mcp),'model':self.model,'busy':self.running,'api_calls':self.api_calls,
            'authenticating':self.login_cancel is not None,'project':self.project,'conversation_id':self.chat_id,
            'switching':self.transition is not None,'sync_available':False,'sync_message':SYNC_REASON})

    def attach(self, path):
        if self.mcp:
            self.mcp.close()
        self.mcp, self.workspace = None, None
        if path:
            try:
                root = os.canonical_root(path)
                self.mcp = base.MCPClient(root)
                self.workspace = collections.namedtuple('WorkspaceInfo','root')(root)
            except Exception:
                self.emit({'type':'notice','message':'The linked workspace folder is not available. Choose the folder again. The conversation is kept.'})
        self.emit({'type':'files','data':self.mcp.tool('list_directory',{'path':'.'}) if self.mcp else {'entries':[]}})

    def activate(self, chat_id):
        if self.running:
            raise ValueError('Stop the current answer first')
        if self.chat_id:
            self.persist()
        data = self.store.chat(chat_id)
        self.restoring = True
        try:
            self.pending.clear()
            self.messages = data['context']
            self.project = self.store.project(data['project_id'])
            self.chat_id = chat_id
            self.emit({'type':'reset'})
            for event in data['events']:
                # Populate base replay queue as well, without re-executing tools.
                self.emit(event)
            current_folder=self.project.get('folder')
            if data.get('folder') and data['folder']!=current_folder:
                self.attach(None)
                self.emit({'type':'notice','message':'This conversation belongs to an earlier workspace. File actions are off so old and new files do not mix. Start a new conversation for the current workspace.'})
            else:
                self.attach(current_folder)
                if current_folder and not data.get('folder'):
                    self.store.chat_folder(chat_id,current_folder)
            self.store.preference('last_chat',chat_id)
            self.state()
            self.library()
        finally:
            self.restoring = False

    def run_turn(self):
        super().run_turn()
        with self.lock:
            if self.transition is not None:
                change = self.transition
                self.transition = None
                self.dispatch(change)

    def api_completion(self, messages, tools):
        self.api_calls += 1
        payload = {'model':self.model,'messages':messages,'max_tokens':4096,'temperature':0.2,'stream':True}
        if tools:
            payload.update(tools=tools,tool_choice='auto',parallel_tool_calls=False)
        request = urllib.request.Request(base.API+'/chat/completions', data=json.dumps(payload).encode(),
            headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json','User-Agent':'VibeZ-4-Test/'+VERSION})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):
                return None
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect).open(request,timeout=60) as response:
                return self.read_stream(response)
        except urllib.error.HTTPError as exc:
            messages = {401:'Your Mistral sign-in has expired. Connect again.',402:'Your Mistral usage allowance or credit is used up.',403:'This model is not available for your account.',429:'The Mistral usage limit was reached. Try again later.'}
            raise RuntimeError(messages.get(exc.code,'Mistral does not accept this request (HTTP '+str(exc.code)+').')) from None
        except (urllib.error.URLError,TimeoutError,OSError):
            raise RuntimeError('The connection to Mistral was interrupted. Your conversation is saved locally.') from None

    def read_stream(self, response):
        text, calls, total = [], {}, 0
        for line in iter(lambda:response.readline(1_000_001),b''):
            if self.cancelled.is_set():
                break
            total += len(line)
            if len(line)>1_000_000 or total>4_000_000:
                raise ValueError('Antwoord van Mistral is te groot')
            if not line.startswith(b'data:'):
                continue
            raw = line[5:].strip()
            if raw==b'[DONE]':
                break
            data=json.loads(raw)
            choices=data.get('choices') or []
            if not choices:
                continue
            delta=choices[0].get('delta') or {}
            content=delta.get('content')
            if isinstance(content,str) and content:
                text.append(content)
                self.emit({'type':'assistant_delta','text':content})
            for fragment in delta.get('tool_calls') or []:
                index=fragment.get('index',0)
                if not isinstance(index,int) or not 0<=index<16:
                    raise ValueError('Too many tools in the answer')
                call=calls.setdefault(index,{'id':'','type':'function','function':{'name':'','arguments':''}})
                if fragment.get('id'):
                    call['id']=fragment['id']
                function=fragment.get('function') or {}
                for key in ('name','arguments'):
                    if isinstance(function.get(key),str):
                        call['function'][key]+=function[key]
        result={'role':'assistant','content':''.join(text)}
        if calls:
            result['tool_calls']=[calls[i] for i in sorted(calls)]
        return result

    def dispatch(self, command):
        if not isinstance(command,dict):
            raise ValueError('Invalid request')
        action=command.get('action')
        if action == 'web_context':
            previous=(self.web.active or {}).get('id')
            self.web.select(command.get('project'))
            current=(self.web.active or {}).get('id')
            self.automatic.context(auto_connect=previous!=current and self.web.auto_connect); return
        if action == 'web_hello':
            self.web.state(); self.automatic.state(); return
        if action == 'web_diagnostics':
            self.external_output({**self.web.diagnostics(), 'timing': self.automatic.timing()}); return
        if action == 'web_goal':
            key, request = command.get('project_id'), command.get('request_id')
            try:
                goal = self.web.set_goal(key, command.get('goal'))
                self.external_output({'type':'web_goal_result','project_id':key,'request_id':request,
                                      'goal':goal})
            except (ValueError, OSError) as error:
                self.external_output({'type':'web_goal_result','project_id':key,'request_id':request,
                                      'error':str(error) if isinstance(error,ValueError) else 'Saving failed.'})
            return
        if action in ('web_import', 'web_import_resolve', 'web_import_cancel'):
            key, binding = command.get('project_id'), command.get('binding')
            try:
                if action == 'web_import':
                    result = self.web.import_files(key, binding, command.get('paths'))
                else:
                    result = self.web.resolve_import(key, binding, command.get('plan_id'), command.get('choices'),
                                                     cancel=action == 'web_import_cancel')
                event_type = 'web_import_result' if result['status'] == 'done' else 'web_import_conflicts'
                self.external_output({'type':event_type, **result})
            except (ValueError, OSError) as error:
                copied = getattr(error, 'copied', [])
                message = str(error) if isinstance(error, ValueError) and str(error) else 'Copying failed. Choose the files again.'
                self.external_output({'type':'web_import_result', 'project_id':key, 'binding':binding,
                                      'error':message, 'names':copied, 'count':len(copied),
                                      'backups':getattr(error, 'backups', [])})
            self.web.state(); return
        if action == 'web_local_files':
            key=command.get('project_id');revision=command.get('workspace_binding');request=command.get('request_id')
            if not isinstance(request,str) or not re.fullmatch(r'[A-Za-z0-9-]{1,80}',request): raise ValueError('Invalid file request.')
            event={'type':'web_local_files_result','project_id':key,'workspace_binding':revision,'request_id':request}
            try: event.update(self.web.local_files(key,revision,command.get('operation'),command.get('path','.'),command.get('destination'),command.get('name')))
            except (ValueError,OSError) as error: event['error']='The file action could not be completed. Existing files are never overwritten.'
            self.external_output(event);self.web.state();return
        if action == 'web_create_folder':
            key=command.get('project_id');revision=command.get('workspace_binding');request=command.get('request_id')
            if not isinstance(request,str) or not 1 <= len(request) <= 80 or not request.isascii() or any(not (c.isalnum() or c=='-') for c in request):
                raise ValueError('Invalid request to create a folder')
            event={'type':'web_create_folder_result','project_id':key,'workspace_binding':revision,'request_id':request}
            try:
                result=self.web.create_folder(key, revision, command.get('name'))
                event.update(result)
            except (ValueError,OSError) as error:
                event['error']=str(error) if isinstance(error,ValueError) else 'The folder could not be created. Check that the workspace folder is available.'
            self.external_output(event);self.web.state();return
        if action == 'web_link':
            key=command.get('project_id');before=self.web.workspace_binding(key)
            self.web.link(key, command.get('path'), folder_id=command.get('folder_id'), revision=command.get('workspace_binding'))
            if before != self.web.workspace_binding(key): self.automatic.cancel(key)
            self.automatic.context(); return
        if action in ('web_add_folder', 'web_select_folder', 'web_remove_folder'):
            key=command.get('project_id');before=self.web.workspace_binding(key)
            if action=='web_add_folder': self.web.add_folder(key,command.get('path'),command.get('workspace_binding'))
            elif action=='web_select_folder': self.web.select_folder(key,command.get('folder_id'),command.get('workspace_binding'))
            else: self.web.remove_folder(key,command.get('folder_id'),command.get('workspace_binding'))
            if before!=self.web.workspace_binding(key): self.automatic.cancel(key)
            self.automatic.context();return
        if action == 'web_unlink':
            self.automatic.cancel(command.get('project_id'))
            self.web.unlink(command.get('project_id')); self.automatic.context(); return
        if action == 'web_auto_connect':
            self.web.set_auto_connect(command.get('enabled')); return
        if action == 'web_enable':
            key=command.get('project_id')
            if command.get('allow') is True:
                self.web.enable(key,True,manual=True)
            else:
                self.automatic.cancel(key)
                self.web.pause(key)
            self.automatic.context(); return
        if action == 'web_rotate':
            self.automatic.cancel(command.get('project_id'))
            self.web.rotate(command.get('project_id')); self.automatic.context(); return
        if action == 'web_approve':
            self.web.resolve(command.get('id'), command.get('allow') is True); return
        if action == 'web_start':
            self.web.start_tunnel(); return
        if action == 'web_stop':
            self.automatic.cancel(); self.web.pause_all(); self.web.stop_tunnel(); self.automatic.context(); return
        if action == 'web_connect':
            self.automatic.connect(command.get('project_id'),command.get('connector_reference'),method=command.get('method')); return
        if action == 'web_work_enroll_result':
            self.automatic.work_result(command); return
        if action == 'web_abort':
            self.automatic.cancel(command.get('project_id'))
            if command.get('project_id') in self.web.projects:self.web.pause(command['project_id'])
            self.automatic.context(); return
        if action == 'web_set_api_key':
            key=command.get('api_key')
            if not isinstance(key,str) or not 1<=len(key)<=4096 or any(c.isspace() for c in key):raise ValueError('Enter a valid Mistral Studio API key')
            if self.automatic.job and self.automatic.job['thread'].is_alive():raise ValueError('Wait until the previous connection has finished')
            self.remember_key(key)
            self.automatic.progress(command.get('project_id'),'idle','Mistral access is saved for this installation. Click Connect to Mistral.');return
        changes={'select_project','select_chat','new_chat'}
        if self.transition is not None and action not in changes|{'hello','cancel','cancel_login'}:
            raise ValueError('The conversation is switching; wait a moment')
        if action in changes and self.running:
            self.transition=dict(command)
            self.cancelled.set()
            self.state()
            return
        if action=='hello':
            super().dispatch(command)
            self.library()
        elif action=='new_project':
            if self.running:
                raise ValueError('Stop the current answer first')
            project_id=self.store.new_project(command.get('name',''))
            self.activate(self.store.create_chat(project_id))
        elif action=='rename_project':
            self.store.rename(self.project['id'],command.get('name',''))
            self.project=self.store.project(self.project['id'])
            self.state();self.library()
        elif action=='select_project':
            project_id=command.get('id')
            self.store.project(project_id)
            _,chats=self.store.library()
            chosen=next((c['id'] for c in chats if c['project_id']==project_id),None)
            self.activate(chosen or self.store.create_chat(project_id))
        elif action=='select_chat':
            self.activate(command.get('id'))
        elif action=='new_chat':
            self.activate(self.store.create_chat(self.project['id']))
        elif action=='workspace':
            if self.running:
                raise ValueError('Stop the current answer first')
            path=os.canonical_root(command['path'])
            previous=self.store.chat(self.chat_id).get('folder')
            self.store.folder(self.project['id'],path)
            self.project=self.store.project(self.project['id'])
            if previous and previous!=path:
                self.activate(self.store.create_chat(self.project['id']))
                self.emit({'type':'notice','message':'The workspace folder has changed. A new conversation keeps old file context from mixing in. The previous conversation is still in the history.'})
            else:
                self.store.chat_folder(self.chat_id,path)
                self.attach(path);self.state();self.library()
        elif action=='clear_workspace':
            if self.running:
                raise ValueError('Stop the current answer first')
            self.store.folder(self.project['id'],None)
            self.activate(self.store.create_chat(self.project['id']))
        elif action=='export':
            if self.running:
                raise ValueError('Wait until the answer is finished')
            self.persist()
            data=self.store.chat(self.chat_id)
            lines=['# '+data['title'],'','Project: '+self.project['name'],'']
            for event in data['events']:
                if event['type'] in ('user','assistant'):
                    lines.extend(['## '+('You' if event['type']=='user' else 'Mistral'),'',event['text'],''])
                elif event['type']=='tool' and event.get('status')!='running':
                    lines.extend(['Bestandsactie: '+str(event.get('name',''))+' — '+str(event.get('status','')),''])
            self.external_output({'type':'export','text':'\n'.join(lines),'filename':'VibeZ-chat.md'})
        else:
            super().dispatch(command)

    def close(self):
        self.automatic.close()
        self.web.close()
        with self.lock:
            if not self.running:
                self.persist()
        super().close()


def main():
    directory=sys.argv[sys.argv.index('--data-dir')+1]
    legacy=sys.argv[sys.argv.index('--legacy-projects')+1] if '--legacy-projects' in sys.argv else None
    output_lock=threading.Lock()
    def output(event):
        with output_lock:
            print(json.dumps(event,ensure_ascii=False),flush=True)
    engine=StandaloneEngine(output,directory,legacy=legacy)
    def shutdown(*_):
        engine.close()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,shutdown)
    try:
        while True:
            line=sys.stdin.readline(base.MAX_LINE+1)
            if not line:
                break
            try:
                if len(line)>base.MAX_LINE:
                    raise ValueError('Bericht is te groot')
                command=json.loads(line)
                if command.get('action')=='shutdown':
                    break
                engine.dispatch(command)
            except Exception as exc:
                output({'type':'error','message':engine.safe_error(exc)})
    finally:
        engine.close()

if __name__=='__main__':
    main()
