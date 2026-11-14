"""The tunnel helper outlives the app and is reused after a restart.

A fake helper stands in for cloudflared: it writes the two log lines the real
one writes (the public address, then "Registered tunnel connection") to the
requested --logfile and then waits like a daemon would.
"""
import importlib.util
import json
import os
import signal
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('web_tunnel_test', Path(__file__).parents[2] / 'backend/web_connector.py')
web = importlib.util.module_from_spec(spec); spec.loader.exec_module(web)
A = 'cace260d-d95d-4859-b45b-f56f185f15da'

FAKE = """#!/usr/bin/python3
import sys, time
args = sys.argv
log = args[args.index('--logfile') + 1]
with open(log, 'a') as out:
    out.write('{"level":"info","message":"|  https://reused-fixture.trycloudflare.com  |"}\\n')
    out.write('{"level":"info","message":"Registered tunnel connection"}\\n')
time.sleep(300)
"""


@unittest.skipUnless(sys.platform.startswith('linux'), 'process adoption is checked through /proc here')
class TunnelReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vibez-tunnel-reuse-')
        base = Path(self.temp.name)
        self.helper = base / 'cloudflared-linux-amd64'
        self.helper.write_text(FAKE); self.helper.chmod(self.helper.stat().st_mode | stat.S_IXUSR)
        self.directory = base / 'web-connector'
        self.events = []
        self.patches = [patch.object(web.os, 'tunnel_helper', lambda *_: self.helper),
                        patch.object(web.os, 'runtime_env', lambda: {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})]
        for p in self.patches: p.start()
        self.pids = []

    def tearDown(self):
        for p in self.patches: p.stop()
        for pid in self.pids:
            try: os.kill(pid, signal.SIGKILL)
            except OSError: pass
        self.temp.cleanup()

    def connector(self):
        c = web.Connector(self.events.append, self.directory)
        c.enabled.add(A)
        return c

    def wait(self, predicate, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate(): return True
            time.sleep(0.1)
        return False

    def test_helper_is_detached_recorded_and_adopted_after_a_restart(self):
        first = self.connector()
        first.start_tunnel()
        self.assertTrue(self.wait(lambda: first.tunnel_status == 'running' and (self.directory / 'tunnel.json').exists()), 'the fake helper announces its address')
        pid = first.tunnel.pid; self.pids.append(pid); port = first.server.server_port
        self.assertEqual(first.tunnel_url, 'https://reused-fixture.trycloudflare.com')
        record = json.loads((self.directory / 'tunnel.json').read_text())
        self.assertEqual((record['pid'], record['port'], record['url']), (pid, port, first.tunnel_url))
        self.assertEqual(stat.S_IMODE((self.directory / 'tunnel.json').stat().st_mode), 0o600)
        self.assertNotEqual(os.getsid(pid), os.getsid(os.getpid()), 'the helper runs in its own session')
        # The app exits: the helper keeps running and the record stays.
        first.close()
        self.assertTrue(web.helper_alive(pid))
        self.assertTrue((self.directory / 'tunnel.json').exists())
        # Next start: same port, same address, no second helper.
        second = self.connector()
        second.start_tunnel()
        self.assertEqual(second.server.server_port, port)
        self.assertEqual(second.tunnel_status, 'running')
        self.assertEqual(second.tunnel_url, 'https://reused-fixture.trycloudflare.com')
        self.assertIsNone(second.tunnel); self.assertEqual(second.tunnel_pid, pid)
        # Stopping on purpose ends the helper and forgets the address.
        second.stop_tunnel()
        def gone():
            try: return os.waitpid(pid, os.WNOHANG)[0] == pid  # our child: reap it
            except ChildProcessError: return not web.helper_alive(pid)
        self.assertTrue(self.wait(gone, 10), 'the helper ends when the tunnel is stopped on purpose')
        self.assertFalse((self.directory / 'tunnel.json').exists())
        self.assertEqual(second.tunnel_status, 'stopped')
        second.close()

    def test_a_dead_or_foreign_record_starts_a_fresh_helper(self):
        self.directory.mkdir(parents=True)
        (self.directory / 'tunnel.json').write_text(json.dumps({'pid': 1, 'port': 1, 'url': 'https://stale.trycloudflare.com'}))
        c = self.connector()
        c.start_tunnel()
        self.assertTrue(self.wait(lambda: c.tunnel_status == 'running' and (self.directory / 'tunnel.json').exists()))
        self.pids.append(c.tunnel.pid)
        self.assertEqual(c.tunnel_url, 'https://reused-fixture.trycloudflare.com')
        self.assertNotEqual(json.loads((self.directory / 'tunnel.json').read_text())['pid'], 1)
        c.stop_tunnel(); c.close()

    def test_helper_identity_checks_are_strict(self):
        self.assertFalse(web.helper_matches(1, 1, self.helper))
        self.assertFalse(web.helper_matches(os.getpid(), 1, self.helper))
        bad = self.directory / 'tunnel.json'; self.directory.mkdir(parents=True)
        for raw in ['[]', '{"pid":"1","port":1,"url":"https://x.trycloudflare.com"}', '{"pid":1,"port":1,"url":"https://evil.example/"}', 'x' * 5000]:
            bad.write_text(raw)
            self.assertIsNone(web.Connector(self.events.append, self.directory)._tunnel_record_load())


if __name__ == '__main__':
    unittest.main(verbosity=2)
