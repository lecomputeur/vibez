"""MCP text is rendered outside the local UI and must have an English fallback."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('remote_language_web', BASE/'backend/web_connector.py')
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)
workspace = web.base
A = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'


class RemoteLanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vibez-remote-language-')
        self.root = Path(self.temp.name)
        self.folder = self.root/'test-workspace'
        self.folder.mkdir()
        self.original = 'Nederlandse bestandsinhoud blijft ongewijzigd.\n'
        (self.folder/'bestand.txt').write_text(self.original)
        (self.folder/'zonderextensie').write_text('user data')
        (self.folder/'binary.dat').write_bytes(b'\x00\xff')
        self.c = web.Connector(lambda event: None, self.root/'profile', approval_wait=0)
        self.c.select({'id': A, 'name': 'Mijn eigen projectnaam'})
        self.c.link(A, self.folder)
        # Exercise the transport serializer directly; no socket or external
        # account is needed, and authentication is covered in the HTTP suite.
        self.c.enabled.add(A)
        _, headers, initialized = self.request('initialize', {'protocolVersion': '2025-06-18'})
        self.sid = headers['Mcp-Session-Id']
        self.initialized = initialized

    def tearDown(self):
        self.c.close()
        self.temp.cleanup()

    def request(self, method, params=None):
        with self.c.lock:
            return self.c.rpc(A, getattr(self, 'sid', None), {
                'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})

    def tool(self, name, args=None):
        status, _, reply = self.request('tools/call', {'name': name, 'arguments': args or {}})
        self.assertEqual(status, 200)
        result = reply['result']
        return result, json.loads(result['content'][0]['text'])

    def test_known_failures_have_actionable_english_codes_without_reflection(self):
        cases = [
            ('read_file', {'path': '../outside.txt'}, 'scope_denied'),
            ('read_file', {'path': 'missing.txt'}, 'file_unavailable'),
            ('read_file', {'path': 'binary.dat'}, 'unsupported_text'),
            ('write_file', {'path': 'bestand.txt', 'content': 'new'}, 'read_required'),
            ('read_file', {'path': 'bestand.txt', 'unexpected': 'ignored'}, 'invalid_arguments'),
            ('not_a_tool', {}, 'unknown_tool'),
            ('change_status', {'proposal_id': 'missing'}, 'proposal_expired'),
        ]
        for tool, args, code in cases:
            with self.subTest(tool=tool, code=code):
                result, data = self.tool(tool, args)
                self.assertTrue(result['isError'])
                self.assertEqual(data['error_code'], code)
                self.assertTrue(data['message'].isascii())
                self.assertNotIn(str(self.root), json.dumps(result))
        self.assertEqual((self.folder/'bestand.txt').read_text(), self.original)

    def test_unknown_internal_exception_never_leaks_dutch_secrets_or_paths(self):
        text = 'Niet toegankelijk /home/someone/prive bearer-secret-test'
        with patch.object(self.c, 'tool', side_effect=ValueError(text)):
            result, data = self.tool('read_file', {'path': 'bestand.txt'})
        self.assertTrue(result['isError'])
        self.assertEqual(data['error_code'], 'invalid_request')
        self.assertNotIn(text, json.dumps(result))
        self.assertNotIn('bearer-secret-test', json.dumps(result))
        self.assertEqual(workspace.remote_error(UnicodeError('Nederlandse decodefout'))['error_code'], 'unsupported_text')

    def test_remote_metadata_is_english_but_user_names_and_file_text_are_untouched(self):
        self.assertEqual(self.initialized['result']['serverInfo']['name'], 'VibeZ-local-files')
        self.assertIn('Mijn eigen projectnaam', self.initialized['result']['instructions'])
        _, overview = self.tool('workspace_overview')
        self.assertEqual(overview['source'], 'Local MCP server · VibeZ workspace')
        self.assertIn('(no extension)', overview['extensions'])
        _, read = self.tool('read_file', {'path': 'bestand.txt'})
        self.assertEqual(read['content'], self.original)
        self.assertEqual(read['path'], 'bestand.txt')

    def test_pending_and_saved_results_are_english_without_preapproved_writes(self):
        self.tool('read_file', {'path': 'bestand.txt'})
        _, proposal = self.tool('write_file', {'path': 'bestand.txt', 'content': 'Nederlands voorstel.\n'})
        self.assertEqual(proposal['status'], 'pending')
        self.assertFalse(proposal['written'])
        self.assertTrue(proposal['message'].startswith('Not saved.'))
        self.assertEqual((self.folder/'bestand.txt').read_text(), self.original)
        self.c.resolve(proposal['proposal_id'], True)
        _, status = self.tool('change_status', {'proposal_id': proposal['proposal_id']})
        self.assertTrue(status['written'])
        self.assertEqual((self.folder/'bestand.txt').read_text(), 'Nederlands voorstel.\n')

    def test_same_call_save_message_is_english_after_explicit_local_approval(self):
        self.tool('read_file', {'path': 'bestand.txt'})
        def approve_locally(*args, **kwargs):
            proposal_id = next(pid for pid, p in self.c.proposals.items() if p['status'] == 'pending')
            self.c.resolve(proposal_id, True)
            return True
        with patch.object(self.c.changed, 'wait_for', side_effect=approve_locally):
            _, saved = self.tool('write_file', {'path': 'bestand.txt', 'content': 'Goed gekeurde tekst'})
        self.assertTrue(saved['written'])
        self.assertIn('Saved in the linked folder', saved['message']);self.assertIn('after local approval.',saved['message']);self.assertEqual(saved['destination'],'linked_local_folder');self.assertEqual(saved['path'],'bestand.txt')
        self.assertEqual((self.folder/'bestand.txt').read_text(), 'Goed gekeurde tekst')

    def test_stdio_protocol_errors_and_generated_diff_labels_are_english(self):
        commands = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
                'name': 'read_file', 'arguments': {'path': '../outside'}}},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'not_a_method'},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {
                'name': 'write_file', 'arguments': {'path': 'new.txt', 'content': 'Gebruikerstekst'}}},
        ]
        done = subprocess.run([sys.executable, '-I', '-B', str(BASE/'backend/workspace_engine.py'), '--mcp', str(self.folder)],
                              input=''.join(json.dumps(c)+'\n' for c in commands), text=True, capture_output=True, timeout=10)
        self.assertEqual(done.returncode, 0, done.stderr)
        replies = [json.loads(line) for line in done.stdout.splitlines()]
        self.assertEqual(json.loads(replies[1]['result']['content'][0]['text'])['error_code'], 'scope_denied')
        self.assertEqual(replies[2]['error']['data']['error_code'], 'unknown_method')
        self.assertTrue(replies[2]['error']['message'].startswith('The requested'))
        proposal = json.loads(replies[3]['result']['content'][0]['text'])
        self.assertIn('new.txt (current)', proposal['diff'])
        self.assertIn('new.txt (proposed)', proposal['diff'])
        self.assertEqual(proposal['after'], 'Gebruikerstekst')
        self.assertFalse((self.folder/'new.txt').exists())

    def test_stdio_user_rejection_keeps_files_and_has_english_reason(self):
        commands = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
                'name': 'write_file', 'arguments': {'path': 'rejected.txt', 'content': 'Mijn voorstel'}}},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'vibez/resolve', 'params': {
                'proposal_id': 'fixture-proposal-id', 'allow': False}},
        ]
        output = io.StringIO()
        with patch.object(workspace.sys, 'stdin', io.StringIO(''.join(json.dumps(c)+'\n' for c in commands))), \
                patch.object(workspace.sys, 'stdout', output), \
                patch.object(workspace.uuid, 'uuid4', return_value=SimpleNamespace(hex='fixture-proposal-id')):
            workspace.serve_mcp(str(self.folder))
        rejected = json.loads(output.getvalue().splitlines()[-1])['result']
        self.assertFalse(rejected['written'])
        self.assertEqual(rejected['reason_code'], 'user_rejected')
        self.assertEqual(rejected['reason'], 'The user rejected or stopped this change.')
        self.assertFalse((self.folder/'rejected.txt').exists())


if __name__ == '__main__':
    unittest.main()
