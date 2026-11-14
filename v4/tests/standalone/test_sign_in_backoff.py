import importlib.util
from pathlib import Path
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('sign_in_backoff_test', ROOT / 'backend' / 'workspace_engine.py')
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)


class FakeCancel:
    def __init__(self):
        self.waits = []
    def is_set(self):
        return False
    def wait(self, seconds):
        self.waits.append(seconds)
        return False


class SignInBackoffTests(unittest.TestCase):
    def test_repeated_rate_limits_back_off_instead_of_polling_every_second(self):
        answers = [workspace.SignInRateLimit(1)] * 7 + [{'status': 'pending'}]
        def request(url, payload=None):
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        auth = workspace.BrowserSignIn(request=request, poll_interval=3)
        shown = []
        auth.retry_status = shown.append
        cancel = FakeCancel()
        with mock.patch.object(workspace.time, 'monotonic', return_value=0):
            result = auth.request_waiting(cancel, 10_000, 'https://console.mistral.ai/poll')
        self.assertEqual(result, {'status': 'pending'})
        self.assertEqual(cancel.waits, [3, 6, 12, 24, 48, 60, 60])
        self.assertEqual(shown, cancel.waits)

    def test_backoff_never_waits_past_the_sign_in_deadline(self):
        def request(url, payload=None):
            raise workspace.SignInRateLimit(30)
        auth = workspace.BrowserSignIn(request=request, poll_interval=3)
        cancel = FakeCancel()
        clock = iter([0, 0, 100])
        with mock.patch.object(workspace.time, 'monotonic', side_effect=lambda: next(clock)):
            with self.assertRaises(workspace.SignInError):
                auth.request_waiting(cancel, 100, 'https://console.mistral.ai/poll')
        self.assertEqual(cancel.waits, [30])

    def test_cancel_during_backoff_stops_sign_in(self):
        def request(url, payload=None):
            raise workspace.SignInRateLimit(1)
        auth = workspace.BrowserSignIn(request=request, poll_interval=3)
        cancel = threading.Event()
        cancel.wait = lambda seconds: True
        with self.assertRaises(workspace.SignInCancelled):
            auth.request_waiting(cancel, float('inf'), 'https://console.mistral.ai/poll')


if __name__ == '__main__':
    unittest.main()
