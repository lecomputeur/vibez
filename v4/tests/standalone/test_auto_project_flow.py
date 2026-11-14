"""Exercise the real engine's project/pause commands using isolated HTTP fixtures."""
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest

from connector_service_fixture import Service

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('auto_project_app', BASE/'backend/standalone_engine.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
A = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'
B = 'code-' + A


class NoUnexpectedAuth:
    def __init__(self): self.calls = 0
    def authenticate(self, *_):
        self.calls += 1
        raise AssertionError('A context or status update must never initiate sign-in')


class ProjectAutoFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vibez28-project-flow-')
        self.root = Path(self.temp.name)
        self.directory = self.root/'profile'
        self.events = []
        self.auth = NoUnexpectedAuth()
        self.service = None
        self.make_engine()
        # Connecting is manual by default; these journeys cover the opt-in automatic mode.
        self.assertFalse(self.e.web.snapshot()['auto_connect'])
        self.e.dispatch({'action': 'web_auto_connect', 'enabled': True})
        self.assertTrue(self.e.web.snapshot()['auto_connect'])
        self.e.key = 'invented-in-memory-test-access'
        self.folders = {}
        for key, name in [(A, 'Alpha'), (B, 'Beta')]:
            folder = self.root/name
            folder.mkdir()
            (folder/'marker.txt').write_text(name)
            self.folders[key] = folder

    def make_engine(self):
        self.e = app.StandaloneEngine(self.events.append, self.directory, auth=self.auth,
                                      auto_api_factory=lambda _: self.service)
        if self.service is None:
            error = self.e.automatic.registry.lookup.__globals__['SetupError']
            self.service = Service(error, self.e.web)
        else:
            self.service.web = self.e.web
        self.e.automatic.probe = lambda *_: None
        def tunnel():
            self.e.web.tunnel_url = 'https://fixture.trycloudflare.com'
            self.e.web.tunnel_status = 'running'
            self.e.web.state()
        self.e.web.start_tunnel = tunnel

    def tearDown(self):
        self.e.close()
        self.temp.cleanup()

    def select(self, key, name=None):
        project = None if key is None else {'id': key, 'name': name or ('Beta' if key == B else 'Alpha')}
        self.e.dispatch({'action': 'web_context', 'project': project})

    def wait_connected(self, key):
        end = time.monotonic()+6
        while time.monotonic() < end:
            if (self.e.automatic.states.get(key, {}).get('status') == 'connected'
                    and key in self.e.web.enabled):
                return
            if self.e.automatic.states.get(key, {}).get('status') == 'error':
                self.fail(str(self.e.automatic.states[key]))
            time.sleep(.01)
        self.fail('Project connection did not complete')

    def confirm(self, key):
        self.select(key)
        self.e.dispatch({'action': 'web_link', 'project_id': key, 'path': str(self.folders[key])})
        self.e.dispatch({'action': 'web_connect', 'project_id': key})
        self.wait_connected(key)

    def test_automatic_switch_manual_pause_and_explicit_resume_through_engine(self):
        self.confirm(A)
        self.confirm(B)
        self.assertTrue(self.e.web.can_auto_connect(A))
        self.assertTrue(self.e.web.can_auto_connect(B))
        self.select(A)
        self.wait_connected(A)
        self.assertNotIn(B, self.e.web.enabled)
        self.e.dispatch({'action': 'web_enable', 'project_id': A, 'allow': False})
        self.assertTrue(self.e.web.snapshot()['manually_paused'])
        self.select(B)
        self.wait_connected(B)
        self.service.calls.clear()
        self.select(A)
        time.sleep(.15)
        self.assertNotIn(A, self.e.web.enabled)
        self.assertEqual(self.service.calls, [])
        self.assertEqual(self.e.automatic.states[A].get('pause_reason'), 'manual')
        self.e.dispatch({'action': 'web_connect', 'project_id': A})
        self.wait_connected(A)
        self.assertFalse(self.e.web.snapshot()['manually_paused'])
        self.select(B)
        self.wait_connected(B)
        self.select(A)
        self.wait_connected(A)
        self.assertEqual(len(self.service.connectors), 2)
        self.assertEqual(self.auth.calls, 0)

    def test_manual_is_the_default_and_the_choice_survives_a_restart(self):
        self.e.dispatch({'action': 'web_auto_connect', 'enabled': False})
        self.assertFalse((self.directory/'web-connector'/'auto-connect').exists())
        self.confirm(A)
        self.confirm(B)
        self.service.calls.clear()
        self.select(A)
        time.sleep(.15)
        self.assertNotIn(A, self.e.web.enabled)
        self.assertEqual(self.service.calls, [])
        self.assertNotIn(self.e.automatic.states.get(A, {}).get('status'), ('starting', 'connected'))
        self.e.dispatch({'action': 'web_connect', 'project_id': A})
        self.wait_connected(A)
        with self.assertRaises(ValueError):
            self.e.web.set_auto_connect('yes')
        self.e.dispatch({'action': 'web_auto_connect', 'enabled': True})
        self.e.close()
        self.make_engine()
        self.assertTrue(self.e.web.snapshot()['auto_connect'])
        self.e.dispatch({'action': 'web_auto_connect', 'enabled': False})
        self.e.close()
        self.make_engine()
        self.assertFalse(self.e.web.snapshot()['auto_connect'])

    def test_replay_name_changes_and_unconfirmed_folders_do_not_connect(self):
        self.confirm(A)
        self.service.calls.clear()
        self.e.dispatch({'action': 'web_hello'})
        self.select(A, 'Renamed Alpha')
        self.e.dispatch({'action': 'web_hello'})
        time.sleep(.1)
        self.assertEqual(self.service.calls, [])
        self.select(B)
        self.e.dispatch({'action': 'web_link', 'project_id': B, 'path': str(self.folders[B])})
        self.select(A)
        self.wait_connected(A)
        self.service.calls.clear()
        self.select(B)
        time.sleep(.1)
        self.assertFalse(self.e.web.auto_approved(B))
        self.assertNotIn(B, self.e.web.enabled)
        self.assertEqual(self.service.calls, [])
        self.assertEqual(self.auth.calls, 0)

    def test_pause_survives_restart_and_approved_map_waits_for_account_access(self):
        self.confirm(A)
        self.confirm(B)
        self.select(A)
        self.wait_connected(A)
        self.e.dispatch({'action': 'web_enable', 'project_id': A, 'allow': False})
        self.e.close()
        self.make_engine()
        self.assertFalse(self.e.key)
        self.service.calls.clear()
        self.select(A)
        self.select(B)
        time.sleep(.1)
        self.assertFalse(self.e.web.enabled)
        self.assertTrue(self.e.web.auto_approved(B))
        self.assertEqual(self.e.automatic.states[B].get('pause_reason'), 'sign_in')
        self.assertEqual(self.service.calls, [])
        self.assertEqual(self.auth.calls, 0)
        self.e.key = 'invented-in-memory-test-access'
        self.select(A)
        time.sleep(.1)
        self.assertTrue(self.e.web.snapshot()['manually_paused'])
        self.assertNotIn(A, self.e.web.enabled)
        self.select(B)
        self.wait_connected(B)

    def test_stop_and_cancel_are_persistent_manual_holds(self):
        self.confirm(A)
        self.confirm(B)
        self.e.dispatch({'action': 'web_stop'})
        self.assertFalse(self.e.web.can_auto_connect(A))
        self.assertFalse(self.e.web.can_auto_connect(B))
        self.assertTrue(all(p['manually_paused'] for p in self.e.web.projects.values()))
        self.select(A)
        self.e.dispatch({'action': 'web_connect', 'project_id': A})
        self.wait_connected(A)
        self.e.dispatch({'action': 'web_abort', 'project_id': A})
        self.select(B)
        self.select(A)
        time.sleep(.1)
        self.assertNotIn(A, self.e.web.enabled)
        self.assertTrue(self.e.web.snapshot()['manually_paused'])


if __name__ == '__main__': unittest.main()
