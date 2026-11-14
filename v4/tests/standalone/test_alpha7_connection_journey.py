"""Real local MCP journeys; Mistral registration is an explicit API fixture.

No user profile, real account, public tunnel, or existing user file is used.
The separate live diagnostic checks the real official Mistral round trip.
"""
import json
from pathlib import Path
import tempfile
import time
import unittest

from test_auto_project_flow import app, Service, NoUnexpectedAuth
from code_multiproject_check import Client

RAW = 'a7777777-1111-4111-8111-aaaaaaaaaaaa'
WORK = RAW
CODE = 'code-' + RAW
CHAT = 'chat-' + RAW


class CompleteConnectionJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vibez-alpha7-journey-')
        self.root = Path(self.temp.name)
        self.profile = self.root/'profile'
        self.events = []
        self.auth = NoUnexpectedAuth()
        self.service = None
        self.contexts = {
            WORK: {'id': WORK, 'name': 'Work fixture'},
            CODE: {'id': CODE, 'name': 'Code fixture'},
            CHAT: {'id': CHAT, 'name': 'Conversation fixture', 'kind': 'conversation',
                   'conversation_id': None, 'draft': True},
        }
        self.folders = {}
        for key, label in [(WORK, 'Work'), (CODE, 'Code'), (CHAT, 'Conversation')]:
            folder = self.root/label
            folder.mkdir()
            (folder/'marker.txt').write_text(label+' original\n')
            (folder/'untouched.txt').write_text(label+' unchanged\n')
            self.folders[key] = folder
        self.make_engine()

    def make_engine(self):
        self.e = app.StandaloneEngine(self.events.append, self.profile, auth=self.auth,
                                     auto_api_factory=lambda _: self.service)
        self.e.web.approval_wait = 0
        # These journeys follow the option to connect automatically; manual is the default.
        self.e.web.set_auto_connect(True)
        if self.service is None:
            error = self.e.automatic.registry.lookup.__globals__['SetupError']
            self.service = Service(error, self.e.web)
        else:
            self.service.web = self.e.web
        # This fixture replaces the Internet transport only. Discovery,
        # workspace execution and every tested file tool use actual local HTTP.
        def tunnel():
            self.e.web.tunnel_url = 'https://alpha7-fixture.trycloudflare.com'
            self.e.web.tunnel_status = 'running'
            self.e.web.state()
        self.e.web.start_tunnel = tunnel
        def probe(server, token, guard, cancel):
            guard()
            self.service.discover(server.rsplit('/', 1)[1], token)
            guard()
        self.e.automatic.probe = probe
        self.e.key = 'invented-test-account-key'

    def tearDown(self):
        self.idle()
        self.e.close()
        self.temp.cleanup()

    def idle(self):
        end = time.monotonic()+8
        while time.monotonic() < end:
            with self.e.automatic.lock:
                job = self.e.automatic.job
                if self.e.automatic.pending is None and (job is None or not job['thread'].is_alive()):
                    return
            time.sleep(.01)
        self.fail('Connector did not become idle')

    def select(self, key):
        self.e.dispatch({'action': 'web_context', 'project': self.contexts[key] if key else None})

    def connect(self, key, *, link=False):
        self.select(key)
        if link:
            self.e.dispatch({'action': 'web_link', 'project_id': key, 'path': str(self.folders[key])})
        self.e.dispatch({'action': 'web_connect', 'project_id': key})
        self.idle()
        self.assertEqual(self.e.automatic.states[key]['status'], 'connected')
        self.assertEqual(self.e.web.enabled, {key})

    def test_missing_workspace_is_explained_before_sign_in_network_or_public_transport(self):
        self.select(WORK)
        self.e.dispatch({'action': 'web_link', 'project_id': WORK, 'path': str(self.folders[WORK])})
        self.folders[WORK].rename(self.root/'moved-workspace')
        self.e.key = ''
        self.e.dispatch({'action': 'web_connect', 'project_id': WORK})
        self.idle()
        failure = self.e.automatic.states[WORK]
        self.assertEqual(failure['status'], 'error')
        self.assertEqual(failure['error_code'], 'workspace_unavailable')
        diagnostic = json.loads(self.e.automatic.error_path.read_text())
        self.assertEqual(diagnostic['stage'], 'workspace')
        self.assertEqual(self.auth.calls, 0)
        self.assertEqual(self.service.calls, [])
        self.assertIsNone(self.e.web.server)
        self.assertFalse(self.e.web.enabled)
        self.assertFalse(self.e.web.auto_approved(WORK))

    def test_workspace_disappearing_after_account_lookup_has_same_actionable_failure(self):
        self.connect(WORK, link=True)
        self.select(None)
        self.select(WORK)
        self.idle()
        def moved(method, path, data):
            if method == 'GET' and path.count('/') == 2:
                self.service.hook = None
                self.folders[WORK].rename(self.root/'moved-during-lookup')
        self.service.hook = moved
        self.e.dispatch({'action': 'web_connect', 'project_id': WORK})
        self.idle()
        self.assertEqual(self.e.automatic.states[WORK]['error_code'], 'workspace_unavailable')
        self.assertFalse(self.e.web.enabled)
        self.assertTrue(self.e.web.auto_approved(WORK))

    def test_local_transport_start_error_is_not_misreported_as_missing_folder(self):
        self.select(WORK)
        self.e.dispatch({'action': 'web_link', 'project_id': WORK, 'path': str(self.folders[WORK])})
        def unavailable_socket():
            raise PermissionError('Invented fixture socket permission failure')
        self.e.web.start_server = unavailable_socket
        self.e.dispatch({'action': 'web_connect', 'project_id': WORK})
        self.idle()
        self.assertEqual(self.e.automatic.states[WORK]['status'], 'error')
        self.assertNotEqual(self.e.automatic.states[WORK]['error_code'], 'workspace_unavailable')
        self.assertFalse(self.e.web.enabled)

    def test_work_code_conversation_read_propose_approve_save_switch_pause_and_restart(self):
        clients = {}
        for key in [WORK, CODE, CHAT]:
            with self.subTest(context=key.split('-')[0]):
                self.connect(key, link=True)
                for old_key, client in clients.items():
                    self.assertEqual(client.request('ping')[0], 403)
                client = Client(self.e.web, key).initialize()
                original = (self.folders[key]/'marker.txt').read_text()
                self.assertEqual(client.tool('read_file', {'path': 'marker.txt'})['content'], original)
                changed = original.replace('original', 'approved')
                # Mistral may open a new session per tool; read evidence must
                # survive that legitimate session boundary for the same scope.
                client = Client(self.e.web, key).initialize()
                proposal = client.tool('write_file', {'path': 'marker.txt', 'content': changed})
                self.assertFalse(proposal['written'])
                self.assertEqual((self.folders[key]/'marker.txt').read_text(), original)
                self.e.dispatch({'action': 'web_approve', 'id': proposal['proposal_id'], 'allow': True})
                self.assertTrue(client.tool('change_status', {'proposal_id': proposal['proposal_id']})['written'])
                self.assertEqual(Client(self.e.web, key).initialize().tool('read_file', {'path': 'marker.txt'})['content'], changed)
                self.assertEqual((self.folders[key]/'untouched.txt').read_text(), original.replace('original', 'unchanged'))
                clients[key] = client

        # The real website promotes a new composer to a saved conversation.
        # An abandoned empty composer deliberately cannot be reopened later.
        self.contexts[CHAT].update(draft=False, conversation_id=RAW)
        self.select(CHAT)

        identity = {key: (value['folder'], value['token']) for key, value in self.e.web.projects.items()}
        connector_ids = {key: value['id'] for key, value in self.e.automatic.registry.records.items()}
        self.select(WORK)
        self.idle()
        self.e.dispatch({'action': 'web_enable', 'project_id': WORK, 'allow': False})
        self.assertTrue(self.e.web.projects[WORK]['manually_paused'])
        self.idle()
        self.e.close()
        self.make_engine()
        self.e.key = ''
        self.select(CODE)
        self.idle()
        self.assertEqual(self.e.automatic.states[CODE]['pause_reason'], 'sign_in')
        self.assertFalse(self.e.web.enabled)
        self.assertEqual(self.auth.calls, 0)

        # Account permission is supplied explicitly in this fixture, not read
        # from browser cookies or any persisted credentials.
        self.e.key = 'invented-new-session-account-key'
        self.select(WORK)
        self.idle()
        self.assertEqual(self.e.automatic.states[WORK]['pause_reason'], 'manual')
        self.assertFalse(self.e.web.enabled)
        for key in [CODE, CHAT]:
            self.select(key)
            self.idle()
            self.assertEqual(self.e.automatic.states[key]['status'], 'connected')
            self.assertEqual(self.e.web.enabled, {key})
            content = Client(self.e.web, key).initialize().tool('read_file', {'path': 'marker.txt'})['content']
            self.assertIn('approved', content)
        self.assertEqual(identity, {key: (value['folder'], value['token']) for key, value in self.e.web.projects.items()})
        self.assertEqual(connector_ids, {key: value['id'] for key, value in self.e.automatic.registry.records.items()})
        self.assertEqual(len(self.service.connectors), 3)
        self.assertEqual(self.auth.calls, 0)

    def test_tunnel_failure_retry_reuses_the_owned_connector_and_exact_folder(self):
        self.connect(WORK, link=True)
        connector_id = self.e.automatic.registry.records[WORK]['id']
        before = dict(self.e.web.projects[WORK])
        self.e.web.stop_tunnel()
        self.e.automatic.context()
        self.assertNotIn(WORK, self.e.web.enabled)
        self.assertNotEqual(self.e.automatic.states[WORK]['status'], 'connected')
        self.connect(WORK)
        self.assertEqual(len(self.service.connectors), 1)
        self.assertEqual(self.e.automatic.registry.records[WORK]['id'], connector_id)
        self.assertEqual(self.e.web.projects[WORK], before)
        self.assertEqual(Client(self.e.web, WORK).initialize().tool('read_file', {'path': 'marker.txt'})['content'], 'Work original\n')


if __name__ == '__main__':
    unittest.main()
