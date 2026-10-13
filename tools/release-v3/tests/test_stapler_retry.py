import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SOURCE = (ROOT / 'tools/release-v3/sign-macos.sh').read_text()
HELPER = SOURCE[SOURCE.index('staple_and_validate() {'):SOURCE.index('# Preserve the runner')]
MOCK = r'''
arch=test
staple_calls=0
validate_calls=0
sleep() { :; }
xcrun() {
  printf '%s\n' "$2" >> "$CALL_LOG"
  if [ "$2" = validate ]; then
    validate_calls=$((validate_calls+1))
    if [ "$validate_calls" -le "$VALIDATE_FAIL_COUNT" ]; then
      printf '%s\n' "$VALIDATE_MESSAGE"
      return 68
    fi
    return "$VALIDATE_EXIT"
  fi
  staple_calls=$((staple_calls+1))
  if [ "$staple_calls" -le "$FAIL_COUNT" ]; then
    printf '%s\n' "$FAIL_MESSAGE"
    return "$FAIL_EXIT"
  fi
  return 0
}
'''

class StaplerRetryTests(unittest.TestCase):
    def run_helper(self, failures, code=68, message='The network connection was lost.', validation=0,
                   validation_failures=0, validation_message='The network connection was lost.'):
        with tempfile.TemporaryDirectory(prefix='vibez-stapler-test-') as directory:
            log = Path(directory) / 'calls.txt'
            env = {**os.environ, 'RUNNER_TEMP': directory, 'CALL_LOG': str(log),
                   'FAIL_COUNT': str(failures), 'FAIL_EXIT': str(code),
                   'FAIL_MESSAGE': message, 'VALIDATE_EXIT': str(validation),
                   'VALIDATE_FAIL_COUNT': str(validation_failures), 'VALIDATE_MESSAGE': validation_message}
            result = subprocess.run(['bash', '-ec', MOCK + HELPER + '\nstaple_and_validate "Synthetic Test.dmg"'],
                                    env=env, text=True, capture_output=True, timeout=5)
            return result.returncode, log.read_text().splitlines()

    def test_success_requires_validation(self):
        self.assertEqual(self.run_helper(0), (0, ['staple', 'validate']))

    def test_transient_network_loss_retries_then_validates(self):
        self.assertEqual(self.run_helper(2), (0, ['staple', 'staple', 'staple', 'validate']))

    def test_persistent_network_loss_stops_after_five_attempts(self):
        self.assertEqual(self.run_helper(6), (68, ['staple'] * 5))

    def test_other_ticket_errors_are_not_retried(self):
        self.assertEqual(self.run_helper(5, message='No valid ticket found'), (68, ['staple']))
        self.assertEqual(self.run_helper(5, code=73), (73, ['staple']))

    def test_failed_validation_is_not_retried_or_ignored(self):
        self.assertEqual(self.run_helper(0, validation=7), (7, ['staple', 'validate']))

    def test_validation_connection_loss_retries_until_validation_succeeds(self):
        self.assertEqual(self.run_helper(0, validation_failures=2), (0, ['staple', 'validate'] * 3))

    def test_persistent_validation_connection_loss_blocks_publication(self):
        self.assertEqual(self.run_helper(0, validation_failures=6), (68, ['staple', 'validate'] * 5))

    def test_missing_ticket_during_validation_is_not_retried(self):
        self.assertEqual(self.run_helper(0, validation_failures=6, validation_message='No valid ticket found'),
                         (68, ['staple', 'validate']))

if __name__ == '__main__':
    unittest.main()
