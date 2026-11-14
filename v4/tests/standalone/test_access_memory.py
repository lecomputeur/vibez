"""Mistral access survives a restart of the engine and is forgotten when rejected."""
import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('access_memory_app', BASE / 'backend/standalone_engine.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class AccessMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vibez-access-memory-')
        self.directory = Path(self.temp.name)
        self.events = []

    def tearDown(self):
        self.temp.cleanup()

    def engine(self):
        return app.StandaloneEngine(self.events.append, self.directory, provider=lambda *_: {'role': 'assistant', 'content': ''})

    def test_access_is_kept_for_this_installation_and_loaded_after_a_restart(self):
        first = self.engine()
        self.assertEqual(first.key, '')
        first.dispatch({'action': 'web_set_api_key', 'api_key': 'fixture-key-never-shown'})
        self.assertEqual(first.key, 'fixture-key-never-shown')
        path = self.directory / 'web-connector' / 'mistral-access.json'
        self.assertTrue(path.exists())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(json.loads(path.read_text())['api_key'], 'fixture-key-never-shown')
        first.close()
        second = self.engine()
        self.assertEqual(second.key, 'fixture-key-never-shown', 'no new sign-in after a restart')
        second.forget_key()
        self.assertEqual(second.key, '')
        self.assertFalse(path.exists())
        second.close()
        third = self.engine()
        self.assertEqual(third.key, '')
        third.close()

    def test_a_damaged_or_odd_file_is_ignored(self):
        path = self.directory / 'web-connector' / 'mistral-access.json'
        path.parent.mkdir(parents=True)
        for raw in ['not json', '[]', '{"api_key": 12}', '{"api_key": "with space"}', '{"api_key": ""}', 'x' * 9000]:
            path.write_text(raw)
            e = self.engine()
            self.assertEqual(e.key, '', raw[:20])
            e.close()

    def test_the_saved_key_never_reaches_the_app_events(self):
        e = self.engine()
        e.dispatch({'action': 'web_set_api_key', 'api_key': 'fixture-key-never-shown'})
        e.close()
        self.assertNotIn('fixture-key-never-shown', json.dumps(self.events))


if __name__ == '__main__':
    unittest.main(verbosity=2)
