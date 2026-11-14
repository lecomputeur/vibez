"""Loose-conversation folder isolation, with temporary files and in-memory APIs."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from connector_service_fixture import Service

BASE = Path(__file__).resolve().parents[2]
def module(name, source):
    spec = importlib.util.spec_from_file_location(name, BASE/'backend'/source)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value
web = module('conversation_web', 'web_connector.py')
auto = module('conversation_auto', 'automatic_connector.py')
A = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'
B = 'bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb'
C = 'cccccccc-3333-4333-8333-cccccccccccc'
CHAT = 'chat-' + A


def draft(key=CHAT, name='Nieuw gesprek', url='https://chat.mistral.ai/work'):
    return {'id': key, 'kind': 'conversation', 'name': name, 'draft': True,
            'conversation_id': None, 'url': url}


def saved(key=CHAT, remote=B, name='Fixture conversation', url=None):
    return {'id': key, 'kind': 'conversation', 'name': name, 'draft': False,
            'conversation_id': remote, 'url': url or 'https://chat.mistral.ai/work/'+remote}


class ConversationSchemaTests(unittest.TestCase):
    def test_missing_conversation_names_use_english_without_changing_user_titles(self):
        fresh=draft();fresh.pop('name')
        self.assertEqual(web.project_info(fresh)['name'],'New conversation')
        existing=saved();existing.pop('name')
        self.assertEqual(web.project_info(existing)['name'],'Conversation '+A[:8])
        self.assertEqual(web.project_info(draft(name='Mijn eigen Nederlandse titel'))['name'],
                         'Mijn eigen Nederlandse titel')

    def test_existing_work_and_code_schema_stay_exactly_unchanged(self):
        self.assertEqual(web.project_info({'id': A, 'name': 'Work'}),
                         {'id': A, 'name': 'Work', 'url': 'https://chat.mistral.ai/work/projects/'+A})
        self.assertEqual(web.project_info({'id': 'code-'+A, 'name': 'Code'}),
                         {'id': 'code-'+A, 'name': 'Code', 'url': 'https://chat.mistral.ai/code/'+A})

    def test_conversation_schema_has_explicit_kind_and_canonical_saved_url(self):
        expected = saved()
        self.assertEqual(web.project_info(expected), expected)
        for route in ['/work/'+B, '/work/chat/'+B, '/work/chats/'+B, '/work/c/'+B]:
            value = saved(url='https://chat.mistral.ai'+route+'/?view=chat#end')
            self.assertEqual(web.project_info(value), expected)
        self.assertNotEqual(CHAT[5:], expected['conversation_id'])

    def test_draft_schema_only_accepts_new_work_composer_routes(self):
        for route in ['/work', '/work/', '/work/new', '/work/new/']:
            self.assertEqual(web.project_info(draft(url='https://chat.mistral.ai'+route)), draft())
        for route in ['/', '/new', '/code', '/work/projects/'+A, '/work/'+B]:
            with self.subTest(route=route), self.assertRaises(ValueError):
                web.project_info(draft(url='https://chat.mistral.ai'+route))

    def test_chat_prefix_cannot_bypass_conversation_kind_or_remote_identity(self):
        invalid = [dict(draft(), kind=None), dict(draft(), kind='project'), {'id': CHAT},
                   dict(draft(), draft=1), dict(draft(), draft=None), dict(draft(), draft=False),
                   dict(saved(), draft=True), dict(saved(), conversation_id='code-'+B),
                   dict(saved(), conversation_id=B.upper()), dict(saved(), conversation_id='wrong'),
                   dict(saved(), url='https://chat.mistral.ai/work/'+C),
                   dict(saved(), url='https://evil.invalid/work/'+B),
                   dict(saved(), url='http://chat.mistral.ai/work/'+B),
                   dict(saved(), url='https://user@chat.mistral.ai/work/'+B),
                   dict(saved(), url='https://chat.mistral.ai:444/work/'+B),
                   dict(saved(), id=A), dict(saved(), id='code-'+A),
                   dict(saved(), id='chat-code-'+A), dict(saved(), id='chat-'+A.upper())]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError): web.project_info(value)

    def test_context_ids_and_mcp_paths_expand_without_expanding_connector_resource_ids(self):
        for key in [A, 'code-'+A, CHAT]:
            self.assertEqual(web.context_key(key), key)
            self.assertIsNotNone(web.MCP_PATH.fullmatch('/mcp/'+key))
            self.assertIsNotNone(auto.PROJECT_ID.fullmatch(key))
            self.assertIsNotNone(auto.MCP_PATH.fullmatch('/mcp/'+key))
        self.assertIsNotNone(auto.UUID.fullmatch(A))
        self.assertIsNone(auto.UUID.fullmatch(CHAT))
        self.assertIsNone(auto.UUID.fullmatch('code-'+A))
        for key in ['chat-chat-'+A, 'chat-code-'+A, 'chat-'+A.upper(), 'chat-'+A+'/other']:
            with self.assertRaises(ValueError): web.context_key(key)


class ConversationBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='vibez-conversation-contexts-')
        self.root = Path(self.tmp.name); self.events = []
        self.web = web.Connector(self.events.append, self.root/'private', approval_wait=0)
        self.manager = None

    def tearDown(self):
        if self.manager: self.manager.close()
        self.web.close(); self.tmp.cleanup()

    def folder(self, name):
        root = self.root/name; root.mkdir(exist_ok=True)
        (root/'marker.txt').write_text(name)
        return root

    def linked(self, context=None, name='Conversation'):
        context = context or draft()
        self.web.select(context); self.web.link(context['id'], self.folder(name))
        return self.web.projects[context['id']]

    def approve(self, key=CHAT):
        p = self.web.projects[key]; self.web.enabled.add(key)
        self.assertTrue(self.web.approve_auto(key, (p['folder'], p['token'])))

    def test_deleted_project_chat_return_preserves_folder_files_and_approval_without_home_access(self):
        for manually_paused in [False, True]:
            with self.subTest(manually_paused=manually_paused):
                context = {'id': A, 'name': 'Fixture project'}
                self.linked(context, 'Project-folder')
                self.approve(A)
                if manually_paused: self.web.pause(A)
                before = copy.deepcopy(self.web.projects[A]); config = self.web.file.read_bytes()
                sentinel = Path(before['folder'])/'marker.txt'; contents = sentinel.read_bytes()
                self.web.select(None)
                self.assertIsNone(self.web.snapshot()['project'])
                self.assertIsNone(self.web.snapshot()['folder'])
                self.assertNotIn(A, self.web.enabled)
                self.web.select(context)
                self.assertEqual(self.web.projects[A], before)
                self.assertEqual(self.web.file.read_bytes(), config)
                self.assertEqual(sentinel.read_bytes(), contents)
                self.assertEqual(self.web.auto_approved(A), True)
                self.assertEqual(self.web.can_auto_connect(A), not manually_paused)
                self.assertEqual(set(self.web.projects), {A})

    def test_loose_conversation_folder_does_not_inherit_work_code_or_another_chat(self):
        original = {}
        for context, folder in [({'id': A, 'name': 'Same name'}, 'Work'),
                                ({'id': 'code-'+A, 'name': 'Same name'}, 'Code'),
                                (saved(name='Same name'), 'Conversation')]:
            original[context['id']] = copy.deepcopy(self.linked(context, folder))
        self.web.select(saved(key='chat-'+C, remote=C, name='Same name'))
        self.assertIsNone(self.web.snapshot()['folder'])
        self.assertFalse(self.web.snapshot()['auto_approved'])
        self.assertEqual(self.web.snapshot()['token'], '')
        self.assertEqual(self.web.projects, original)
        self.web.select(saved())
        self.assertEqual(self.web.snapshot()['folder'], original[CHAT]['folder'])

    def test_work_and_loose_chat_with_same_uuid_keep_mcp_sessions_and_approval_separate(self):
        self.linked({'id': A, 'name': 'Work'}, 'Work')
        self.approve(A)
        with self.web.lock:
            _, headers, _ = self.web.rpc(A, None, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}})
        work_sid = headers['Mcp-Session-Id']; work_ws = self.web.sessions[work_sid]['workspace']
        work_token = self.web.projects[A]['token']
        self.linked(saved(remote=A), 'Conversation')
        self.assertEqual(work_ws.fd, -1)
        self.assertNotEqual(self.web.projects[CHAT]['token'], work_token)
        self.assertFalse(self.web.auto_approved(CHAT)); self.assertTrue(self.web.auto_approved(A))
        self.web.enabled.add(CHAT)
        with self.web.lock:
            _, headers, _ = self.web.rpc(CHAT, None, {'jsonrpc': '2.0', 'id': 2, 'method': 'initialize', 'params': {}})
            chat_sid = headers['Mcp-Session-Id']
            message = {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'read_file', 'arguments': {'path': 'marker.txt'}}}
            self.assertEqual(self.web.rpc(CHAT, work_sid, message)[0], 404)
            self.assertEqual(self.web.rpc(A, chat_sid, message)[0], 404)
            code, _, result = self.web.rpc(CHAT, chat_sid, message)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(result['result']['content'][0]['text'])['content'], 'Conversation')

    def test_conversation_local_metadata_and_activity_keep_stable_id_across_promotion_restart(self):
        self.linked()
        self.web.set_goal(CHAT, 'Legacy local metadata')
        self.web.record(CHAT, 'read_file', 'marker.txt')
        self.web.select(saved())
        self.web.close(); self.web = web.Connector(self.events.append, self.root/'private', approval_wait=0)
        self.web.select(saved())
        self.assertEqual(self.web.snapshot()['project_goal'], 'Legacy local metadata')
        self.assertEqual(self.web.snapshot()['recent_activity'][0]['project_id'], CHAT)

    def test_snapshot_sequence_orders_parallel_context_events_without_persisting_or_changing_bindings(self):
        self.linked(saved())
        config = self.web.file.read_bytes(); bindings = copy.deepcopy(self.web.projects)
        first = self.web.snapshot()
        self.web.state(); second = self.events[-1]
        self.assertIs(type(first['snapshot_sequence']), int)
        self.assertGreater(first['snapshot_sequence'], 0)
        self.assertEqual(second['snapshot_sequence'], first['snapshot_sequence'] + 1)
        entered = threading.Event(); release = threading.Event(); delivered = []
        older_sequence = second['snapshot_sequence'] + 1
        original_emit = self.web.emit
        def emit(event):
            if event.get('snapshot_sequence') == older_sequence:
                entered.set(); release.wait(2)
            delivered.append(event)
        self.web.emit = emit
        worker = threading.Thread(target=self.web.state)
        try:
            worker.start(); self.assertTrue(entered.wait(1))
            self.web.select(saved(key='chat-'+C, remote=C))
            release.set(); worker.join(2)
            self.assertFalse(worker.is_alive())
        finally:
            release.set(); worker.join(2); self.web.emit = original_emit
        self.assertEqual(len(delivered), 2)
        self.assertGreater(delivered[0]['snapshot_sequence'], delivered[1]['snapshot_sequence'])
        self.assertEqual(delivered[0]['project']['id'], 'chat-'+C)
        self.assertEqual(delivered[1]['project']['id'], CHAT)
        latest = self.web.snapshot()
        self.assertGreater(latest['snapshot_sequence'], max(event['snapshot_sequence'] for event in delivered))
        self.assertEqual(self.web.projects, bindings)
        self.assertEqual(self.web.file.read_bytes(), config)
        self.assertNotIn('snapshot_sequence', json.loads(config))
        self.assertNotIn('snapshot_sequence', self.web.transport_snapshot())

    def test_first_message_promotion_preserves_binding_permissions_sessions_and_endpoint(self):
        self.linked(); self.approve()
        self.web.set_goal(CHAT, 'Existing local metadata remains scoped')
        self.web.record(CHAT, 'read_file', 'marker.txt')
        with self.web.lock:
            _, headers, _ = self.web.rpc(CHAT, None, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}})
        sid = headers['Mcp-Session-Id']; workspace = self.web.sessions[sid]['workspace']
        before = copy.deepcopy(self.web.projects[CHAT]); binding = self.web.snapshot()['import_binding']
        self.web.tunnel_url = 'https://fixture.trycloudflare.com'
        endpoint = self.web.snapshot()['url']
        self.web.select(saved(name='First message title'))
        after = self.web.projects[CHAT]
        for field in ['id', 'folder', 'token', 'auto_approved', 'manually_paused']:
            self.assertEqual(after[field], before[field])
        self.assertEqual(after['conversation_id'], B); self.assertFalse(after['draft'])
        self.assertEqual(after['url'], 'https://chat.mistral.ai/work/'+B)
        self.assertEqual(self.web.snapshot()['url'], endpoint)
        self.assertEqual(self.web.snapshot()['import_binding'], binding)
        self.assertIs(self.web.sessions[sid]['workspace'], workspace)
        self.assertNotEqual(workspace.fd, -1)
        self.assertIn(CHAT, self.web.enabled); self.assertTrue(self.web.auto_approved(CHAT))
        self.assertEqual(self.web.snapshot()['project_goal'], 'Existing local metadata remains scoped')
        self.assertEqual(self.web.snapshot()['recent_activity'][-1]['project_id'], CHAT)

    def test_promotion_does_not_clear_an_explicit_pause(self):
        self.linked(); self.approve(); self.web.pause(CHAT)
        before = copy.deepcopy(self.web.projects[CHAT])
        self.web.select(saved())
        self.assertTrue(self.web.projects[CHAT]['manually_paused'])
        self.assertEqual(self.web.projects[CHAT]['token'], before['token'])
        self.assertEqual(self.web.projects[CHAT]['auto_approved'], before['auto_approved'])
        self.assertNotIn(CHAT, self.web.enabled); self.assertFalse(self.web.can_auto_connect(CHAT))

    def test_saved_alias_survives_restart_and_snapshot_only_exposes_safe_identity_metadata(self):
        self.linked(); self.approve(); self.web.select(saved())
        original = copy.deepcopy(self.web.projects[CHAT])
        self.web.close(); self.web = web.Connector(self.events.append, self.root/'private', approval_wait=0)
        self.assertEqual(self.web.projects[CHAT], original)
        row = next(p for p in self.web.snapshot()['projects'] if p['id'] == CHAT)
        self.assertEqual(row['kind'], 'conversation'); self.assertEqual(row['conversation_id'], B)
        self.assertFalse(row['draft']); self.assertNotIn('token', row)
        self.web.select(saved())
        self.assertEqual(self.web.snapshot()['folder'], original['folder'])
        self.assertTrue(self.web.auto_approved(CHAT)); self.assertFalse(self.web.enabled)

    def test_saved_remote_identity_is_immutable_and_cannot_claim_an_existing_alias(self):
        self.linked(saved())
        original = copy.deepcopy(self.web.projects[CHAT]); before = self.web.file.read_bytes()
        for context in [saved(remote=C), draft(), saved(key='chat-'+C, remote=B)]:
            with self.subTest(context=context), self.assertRaises(ValueError): self.web.select(context)
            self.assertEqual(self.web.projects[CHAT], original)
            self.assertEqual(self.web.file.read_bytes(), before)

    def test_only_the_current_live_draft_can_promote_and_abandoned_drafts_never_reactivate(self):
        p = self.linked(); folder = Path(p['folder'])
        self.web.select(None)
        for context in [draft(), saved()]:
            with self.assertRaises(ValueError): self.web.select(context)
        self.web.select(draft(key='chat-'+C))
        self.assertIsNone(self.web.snapshot()['folder'])
        self.assertFalse(self.web.enabled)
        self.assertEqual((folder/'marker.txt').read_text(), 'Conversation')
        self.web.close(); self.web = web.Connector(self.events.append, self.root/'private', approval_wait=0)
        with self.assertRaises(ValueError): self.web.select(draft())
        self.assertIsNone(self.web.active)

    def test_promotion_save_failure_rolls_back_identity_without_losing_approval_or_session(self):
        self.linked(); self.approve()
        original = copy.deepcopy(self.web.projects[CHAT]); active = copy.deepcopy(self.web.active)
        before = self.web.file.read_bytes()
        with patch.object(self.web, 'save', side_effect=OSError('Controlled identity save failure')):
            with self.assertRaises(OSError): self.web.select(saved())
        self.assertEqual(self.web.projects[CHAT], original)
        self.assertEqual(self.web.active, active)
        self.assertEqual(self.web.file.read_bytes(), before)
        self.assertIn(CHAT, self.web.enabled)

    def test_duplicate_saved_aliases_in_storage_fail_closed(self):
        self.linked(saved()); payload = json.loads(self.web.file.read_text())
        duplicate = dict(payload['projects'][CHAT], id='chat-'+C)
        payload['projects'][duplicate['id']] = duplicate
        self.web.file.write_text(json.dumps(payload))
        # Fail closed without stopping the start: nothing stays linked, the old file is kept aside.
        restarted = web.Connector(self.events.append, self.root/'private')
        self.assertTrue(restarted.store_damaged); self.assertEqual(restarted.projects, {})
        self.assertTrue((self.root/'private'/'web-projects.damaged.json').exists())
        self.assertEqual((self.root/'Conversation'/'marker.txt').read_text(), 'Conversation')

    def test_draft_orphans_are_bounded_without_deleting_folders_or_work_code_bindings(self):
        original = {}
        for context, folder in [({'id': A, 'name': 'Work'}, 'Work'), ({'id': 'code-'+A, 'name': 'Code'}, 'Code')]:
            original[context['id']] = copy.deepcopy(self.linked(context, folder))
        with patch.object(web, 'MAX_DRAFT_BINDINGS', 2):
            for uuid, folder in [(A, 'Draft-A'), (B, 'Draft-B'), (C, 'Draft-C')]: self.linked(draft(key='chat-'+uuid), folder)
        self.assertEqual(len([p for p in self.web.projects.values() if p.get('draft')]), 2)
        self.assertNotIn(CHAT, self.web.projects)
        for key, record in original.items(): self.assertEqual(self.web.projects[key], record)
        for folder in ['Draft-A', 'Draft-B', 'Draft-C']:
            self.assertEqual((self.root/folder/'marker.txt').read_text(), folder)

    def test_automatic_connector_reuses_the_same_connector_when_draft_becomes_saved(self):
        self.linked()
        service = Service(auto.SetupError)
        engine = SimpleNamespace(web=self.web, key='fixture-in-memory-access', external_output=self.events.append,
                                 lock=threading.RLock(), auth=SimpleNamespace(authenticate=lambda *_: self.fail('Unexpected account sign-in')))
        self.manager = auto.AutomaticConnector(engine, api_factory=lambda _: service, probe=lambda *_: None)
        self.web.start_server = lambda: None
        def tunnel():
            self.web.tunnel_status = 'running'; self.web.tunnel_url = 'https://fixture.trycloudflare.com'; self.web.state()
        self.web.start_tunnel = tunnel
        self.manager.connect(CHAT)
        deadline = time.monotonic()+4
        while time.monotonic() < deadline:
            if self.manager.states.get(CHAT, {}).get('status') in ('connected', 'error'): break
            time.sleep(.01)
        self.assertEqual(self.manager.states[CHAT]['status'], 'connected')
        calls = len(service.calls); connector_id = self.manager.registry.records[CHAT]['id']
        self.assertTrue(auto.UUID.fullmatch(connector_id))
        remote = service.connectors[connector_id]
        self.assertTrue(remote['description'].startswith('Local files for Mistral conversation Nieuw gesprek. '))
        self.assertTrue(remote['system_prompt'].startswith('Use only this connector for conversation Nieuw gesprek. '))
        self.assertNotIn('Mistral project', remote['description'])
        self.web.select(saved()); self.manager.context()
        self.assertEqual(self.manager.states[CHAT]['status'], 'connected')
        self.assertEqual(len(service.calls), calls)
        self.assertEqual(self.manager.registry.records[CHAT]['id'], connector_id)
        self.assertEqual(len(service.connectors), 1)


if __name__ == '__main__': unittest.main()
