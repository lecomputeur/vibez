"""Connection diagnostics for the panel's Advanced tab: counts and names only, never secrets."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.error
import urllib.request

BASE = Path(__file__).resolve().parents[2]
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, BASE/'backend'/file)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
web = load('diag_web', 'web_connector.py'); auto = load('diag_auto', 'automatic_connector.py'); engine = load('diag_engine', 'standalone_engine.py')
A = 'cace260d-d95d-4859-b45b-f56f185f15da'
B = 'b0c1d2e3-f405-4617-8829-3a4b5c6d7e8f'


class TruncatedHostTests(unittest.TestCase):
    def test_tunnel_hosts_keep_only_a_prefix_and_the_provider_domain(self):
        self.assertEqual(web.truncated_host('quiet-river-apple-fixture.trycloudflare.com'), 'quie….trycloudflare.com')
        self.assertEqual(web.truncated_host('abc.example.org'), 'abc…')
        self.assertEqual(web.truncated_host('localhost'), 'loca…')
        self.assertIsNone(web.truncated_host('')); self.assertIsNone(web.truncated_host(None))


class EnvironmentTests(unittest.TestCase):
    def test_repository_labels_drop_credentials_and_show_github_as_owner_name(self):
        self.assertEqual(web.repository_label('https://github.com/lecomputeur/vibez.git'), 'lecomputeur/vibez')
        self.assertEqual(web.repository_label('git@github.com:lecomputeur/vibez.git'), 'lecomputeur/vibez')
        self.assertEqual(web.repository_label('https://user:ghp_secrettoken@github.com/lecomputeur/vibez'), 'lecomputeur/vibez')
        self.assertEqual(web.repository_label('ssh://git@gitlab.example.com:2222/team/app.git'), 'gitlab.example.com/team/app')
        self.assertIsNone(web.repository_label('/home/someone/repo')); self.assertIsNone(web.repository_label('')); self.assertIsNone(web.repository_label(None))

    def test_git_facts_read_branch_and_origin_from_dot_git_and_follow_worktree_pointers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root/'repo'; (repo/'.git'/'refs').mkdir(parents=True)
            (repo/'.git'/'HEAD').write_text('ref: refs/heads/feature/advanced\n')
            (repo/'.git'/'config').write_text('[core]\n\tbare = false\n[remote "upstream"]\n\turl = https://example.org/x/y.git\n[remote "origin"]\n\turl = https://user:ghp_token@github.com/lecomputeur/vibez.git\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n')
            facts = web.git_facts(str(repo))
            self.assertEqual(facts, {'branch': 'feature/advanced', 'remote': 'lecomputeur/vibez'}); self.assertNotIn('ghp_token', json.dumps(facts))
            (repo/'.git'/'HEAD').write_text('0123456789abcdef0123456789abcdef01234567\n')
            self.assertEqual(web.git_facts(str(repo))['branch'], '0123456789ab')
            worktree = root/'wt'; worktree.mkdir(); private = repo/'.git'/'worktrees'/'wt'; private.mkdir(parents=True)
            (worktree/'.git').write_text('gitdir: '+str(private)+'\n'); (private/'HEAD').write_text('ref: refs/heads/wt-branch\n'); (private/'commondir').write_text('../..\n')
            self.assertEqual(web.git_facts(str(worktree)), {'branch': 'wt-branch', 'remote': 'lecomputeur/vibez'})
            plain = root/'plain'; plain.mkdir()
            self.assertIsNone(web.git_facts(str(plain))); self.assertIsNone(web.git_facts(None)); self.assertIsNone(web.git_facts(str(root/'missing')))
            env = web.environment(str(repo))
            self.assertTrue(env['host']); self.assertLessEqual(len(env['host']), 64); self.assertEqual(env['git']['branch'], '0123456789ab')
            self.assertEqual(web.environment(None), {'host': env['host'], 'system': env['system'], 'git': None})

    def test_the_system_label_names_os_and_package_kind_only(self):
        with mock.patch.object(web._stdsys, 'platform', 'win32'): self.assertEqual(web.system_label(), 'Windows')
        with mock.patch.object(web._stdsys, 'platform', 'darwin'): self.assertEqual(web.system_label(), 'macOS')
        with mock.patch.object(web._stdsys, 'platform', 'linux'), mock.patch.object(web.Path, 'exists', return_value=False):
            with mock.patch.dict(os.environ, {'FLATPAK_ID': 'nl.lecomputeur.vibez4.alpha'}, clear=True): self.assertEqual(web.system_label(), 'Linux · Flatpak')
            with mock.patch.dict(os.environ, {'APPIMAGE': '/home/someone/VibeZ.AppImage'}, clear=True): self.assertEqual(web.system_label(), 'Linux · AppImage')
            with mock.patch.dict(os.environ, {}, clear=True): self.assertEqual(web.system_label(), 'Linux')


class ConnectorDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); self.events = []
        self.folder = self.root/'Alpha'; self.folder.mkdir(); (self.folder/'tekst.txt').write_text('Alleen A')
        self.c = web.Connector(self.events.append, self.root/'private', approval_wait=0)
        self.c.select({'id': A, 'name': 'CityTripXL'}); self.c.link(A, self.folder); self.c.enable(A, True)
        self.token = self.c.projects[A]['token']; self.url = 'http://127.0.0.1:'+str(self.c.server.server_port)+'/mcp/'+A; self.sid = None
    def tearDown(self): self.c.close(); self.tmp.cleanup()
    def request(self, msg, token=None, sid=True):
        h = {'Authorization': 'Bearer '+(self.token if token is None else token), 'Content-Type': 'application/json',
             'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-06-18'}
        if sid and self.sid: h['Mcp-Session-Id'] = self.sid
        req = urllib.request.Request(self.url, data=json.dumps(msg).encode(), headers=h, method='POST')
        try: r = urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as e: r = e
        with r:
            raw = r.read(); return r.code, r.headers, (json.loads(raw) if raw and r.headers.get('Content-Type') != 'text/event-stream' else raw)
    def rpc(self, method, params=None, **kw): return self.request({'jsonrpc': '2.0', 'id': 2, 'method': method, 'params': params or {}}, **kw)

    def test_diagnostics_summarize_requests_versions_and_errors_without_secrets(self):
        code, h, _ = self.request({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'Test', 'version': '1'}}})
        self.assertEqual(code, 200); self.sid = h['Mcp-Session-Id']
        self.assertEqual(self.rpc('tools/list')[0], 200)
        self.assertEqual(self.rpc('tools/call', {'name': 'read_file', 'arguments': {'path': 'ontbreekt.txt'}})[0], 200)
        real = self.sid; self.sid = 'unknown-session-fixture-value'
        self.assertEqual(self.rpc('tools/list')[0], 404); self.sid = real
        self.assertEqual(self.rpc('tools/list', token='private-fake-token')[0], 401)
        self.c.tunnel_url = 'https://quiet-river-apple-fixture.trycloudflare.com'; self.c.tunnel_status = 'running'
        d = self.c.diagnostics()
        self.assertEqual(d['type'], 'web_diagnostics'); self.assertEqual(d['project_id'], A); self.assertTrue(d['enabled'])
        self.assertEqual(d['tunnel_status'], 'running'); self.assertEqual(d['tunnel_host'], 'quie….trycloudflare.com')
        self.assertEqual(d['protocol_versions'], ['2025-06-18'])
        self.assertEqual(d['request_counts']['tools/list:200'], 1); self.assertEqual(d['request_counts']['tools/list:404'], 1)
        self.assertEqual(d['request_total'], sum(d['request_counts'].values())); self.assertGreaterEqual(d['request_total'], 4)
        self.assertEqual(d['rejections'], {'token': 1}); self.assertEqual(d['recent_rejections'][-1]['reason'], 'token')
        statuses = [row['http_status'] for row in d['recent_errors']]; self.assertIn(404, statuses)
        self.assertTrue(any(row.get('tool_error') is True and row.get('tool') == 'read_file' for row in d['recent_errors']))
        serialized = json.dumps(d)
        for secret in [self.token, 'private-fake-token', real, 'ontbreekt', str(self.folder), 'quiet-river-apple-fixture', self.url]:
            self.assertNotIn(secret, serialized)
        self.assertEqual(set(d['recent_errors'][0]) - {'time', 'verb', 'phase', 'method', 'http_status', 'tool', 'tool_error', 'session', 'rejection'}, set())
        rejected = [row for row in d['recent_errors'] if row.get('rejection')]
        self.assertEqual([(row['rejection'], row['http_status']) for row in rejected], [('token', 401)], 'a rejection is marked on its own traced request')

    def test_requests_without_a_json_rpc_method_are_counted_under_their_http_verb(self):
        stale = 'http://127.0.0.1:'+str(self.c.server.server_port)+'/mcp/'+B
        try: urllib.request.urlopen(urllib.request.Request(stale, method='GET'), timeout=3)
        except urllib.error.HTTPError as e: self.assertEqual(e.code, 404); e.close()
        d = self.c.diagnostics()
        self.assertEqual(d['request_counts'].get('GET:404'), 1); self.assertFalse(any(label.startswith('none:') for label in d['request_counts']))
        row = d['recent_errors'][-1]
        self.assertEqual((row['verb'], row['method'], row['rejection'], row['http_status']), ('GET', 'none', 'token', 404))

    def test_snapshot_carries_the_environment_of_the_linked_folder(self):
        (self.folder/'.git').mkdir(); (self.folder/'.git'/'HEAD').write_text('ref: refs/heads/main\n')
        snapshot = self.c.snapshot()
        self.assertEqual(snapshot['environment']['git'], {'branch': 'main', 'remote': None}); self.assertTrue(snapshot['environment']['host'])
        self.c.select(None); self.assertIsNone(self.c.snapshot()['environment']['git'])

    def test_diagnostics_without_a_project_or_tunnel_stay_empty_and_public(self):
        self.c.select(None); self.c.local_connector_records[A] = {'id': 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa', 'credentials': 'never-forward-this'}
        d = self.c.diagnostics()
        self.assertIsNone(d['project_id']); self.assertIsNone(d['local_connector_id']); self.assertIsNone(d['tunnel_host']); self.assertFalse(d['enabled'])
        self.assertEqual(d['protocol_versions'], []); self.assertEqual(d['request_total'], 0)
        self.c.select({'id': A, 'name': 'CityTripXL'}); d = self.c.diagnostics()
        self.assertEqual(d['local_connector_id'], 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'); self.assertNotIn('never-forward-this', json.dumps(d))

    def test_engine_action_emits_one_event_with_timing_from_the_last_setup(self):
        path = self.root/'private'/'connector-timing.json'
        path.write_text(json.dumps({'outcome': 'connected', 'method': 'work', 'steps': [['tunnel', 6.04], ['enroll:create', 17], ['bad step with spaces', 1], ['x', -1], 'junk', ['url', 'https://leak.example']], 'extra': 'ignored'}))
        automatic = SimpleNamespace(error_path=self.root/'private'/'connector-error.json', timing=lambda: auto.AutomaticConnector.timing(automatic))
        events = []; host = SimpleNamespace(web=self.c, automatic=automatic, external_output=events.append)
        engine.StandaloneEngine.dispatch(host, {'action': 'web_diagnostics'})
        self.assertEqual(len(events), 1); event = events[0]
        self.assertEqual(event['type'], 'web_diagnostics'); self.assertEqual(event['project_id'], A)
        self.assertEqual(event['timing'], {'outcome': 'connected', 'method': 'work', 'steps': [['tunnel', 6.0], ['enroll:create', 17.0]]})
        self.assertNotIn('leak.example', json.dumps(event)); self.assertNotIn('extra', event['timing'])

    def test_missing_oversized_or_invalid_timing_files_yield_nothing(self):
        path = self.root/'private'/'connector-timing.json'
        automatic = SimpleNamespace(error_path=self.root/'private'/'connector-error.json')
        self.assertIsNone(auto.AutomaticConnector.timing(automatic))
        path.write_text('not json'); self.assertIsNone(auto.AutomaticConnector.timing(automatic))
        path.write_text('[1,2]'); self.assertIsNone(auto.AutomaticConnector.timing(automatic))
        path.write_text(json.dumps({'outcome': 'weird', 'method': 'other', 'steps': 'none'}))
        self.assertEqual(auto.AutomaticConnector.timing(automatic), {'outcome': 'unknown', 'method': 'unknown', 'steps': []})
        path.write_bytes(b'{"steps":[' + b'["a",1],'*20000 + b'["b",2]]}'); self.assertIsNone(auto.AutomaticConnector.timing(automatic))


if __name__ == '__main__':
    unittest.main()
