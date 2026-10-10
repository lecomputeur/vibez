#!/usr/bin/env python3
"""Exercise process shutdown and deferred AppImage launches with harmless fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = None


def start_token(pid):
    return Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()[19]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vibez-install tests-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.children = []
        self.addCleanup(self.stop_children)

    def stop_children(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)

    def spawn(self, *args, **kwargs):
        child = subprocess.Popen(*args, **kwargs)
        self.children.append(child)
        return child

    def test_package_upgrade_closes_only_the_installed_executable(self):
        paths = [self.root / folder / 'vibez3' for folder in ('installed', 'unrelated')]
        for path in paths:
            path.parent.mkdir()
            shutil.copy2('/usr/bin/sleep', path)
        running = [self.spawn([str(path), '60']) for path in paths]
        hook = (ROOT / 'src-tauri/linux/preinst.sh').read_text().replace('/usr/bin/vibez3', str(paths[0]))
        result = subprocess.run(['/bin/sh', '-s', 'upgrade'], input=hook, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(running[0].wait(timeout=3), -15)
        self.assertIsNone(running[1].poll(), 'An unrelated process with the same name must stay running')

    def test_aborted_package_action_does_not_close_the_app(self):
        installed = self.root / 'vibez3'
        shutil.copy2('/usr/bin/sleep', installed)
        child = self.spawn([str(installed), '60'])
        hook = (ROOT / 'src-tauri/linux/preinst.sh').read_text().replace('/usr/bin/vibez3', str(installed))
        result = subprocess.run(['/bin/sh', '-s', 'abort-upgrade'], input=hook, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(child.poll())

    def helper(self, parent, package, digest=None, replacement=None):
        payload = package.read_bytes()
        return self.spawn([str(BINARY), '--launch-appimage-after-exit', str(parent.pid), start_token(parent.pid),
                           str(package), str(len(payload)), digest or hashlib.sha256(payload).hexdigest(),
                           json.dumps(replacement)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env={**os.environ, 'APPIMAGE': '/old/appimage', 'APPDIR': '/old/appdir'})

    def fixture(self):
        marker = self.root / 'started'
        package = self.root / 'VibeZ-3.0.5-Linux-x64.AppImage'
        # Arguments and paths include spaces; no shell interpolation may be used.
        package.write_text('#!/bin/sh\n[ -z "${APPIMAGE:-}" ] && [ -z "${APPDIR:-}" ] || exit 7\n'
                           f'touch "{marker}"\n')
        package.chmod(0o700)
        parent = self.spawn(['/usr/bin/sleep', '60'])
        return parent, package, marker

    def finish(self, parent, helper, marker, succeeds):
        self.assertFalse(marker.exists(), 'The new version must wait for the old instance to exit')
        parent.terminate()
        parent.wait(timeout=3)
        _, error = helper.communicate(timeout=5)
        self.assertEqual(helper.returncode == 0, succeeds, error.decode())
        if succeeds:
            deadline = time.monotonic() + 3
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(marker.exists())
        else:
            self.assertFalse(marker.exists())

    def test_appimage_launch_waits_for_exit_and_clears_the_old_runtime_environment(self):
        parent, package, marker = self.fixture()
        helper = self.helper(parent, package)
        time.sleep(.2)
        self.finish(parent, helper, marker, True)

    def test_changed_download_is_not_executed_after_waiting(self):
        parent, package, marker = self.fixture()
        helper = self.helper(parent, package)
        time.sleep(.2)
        package.write_text(package.read_text().replace('touch', 'false'))
        self.finish(parent, helper, marker, False)

    def replacement(self, parent, package):
        original = self.root / 'Installed AppImage'
        original.write_bytes(b'old application')
        original.chmod(0o755)
        meta = original.stat()
        staged = original.with_name(f'.vibez-update-{parent.pid}.AppImage')
        shutil.copy2(package, staged)
        staged.chmod(meta.st_mode & 0o777)
        return dict(path=str(original), staged=str(staged), device=meta.st_dev, inode=meta.st_ino)

    def test_appimage_replaces_the_original_path_after_exit(self):
        parent, package, marker = self.fixture()
        replacement = self.replacement(parent, package)
        helper = self.helper(parent, package, replacement=replacement)
        time.sleep(.2)
        self.assertEqual(Path(replacement['path']).read_bytes(), b'old application')
        self.finish(parent, helper, marker, True)
        self.assertEqual(Path(replacement['path']).read_bytes(), package.read_bytes())
        self.assertEqual(Path(replacement['path']).stat().st_mode & 0o777, 0o755)
        self.assertFalse(Path(replacement['staged']).exists())

    def test_a_changed_installed_appimage_is_preserved(self):
        parent, package, marker = self.fixture()
        replacement = self.replacement(parent, package)
        helper = self.helper(parent, package, replacement=replacement)
        time.sleep(.2)
        original = Path(replacement['path'])
        different = original.with_name('different version')
        different.write_bytes(b'changed by another installer')
        different.replace(original)
        self.finish(parent, helper, marker, False)
        self.assertEqual(original.read_bytes(), b'changed by another installer')
        self.assertFalse(Path(replacement['staged']).exists())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('binary', type=Path)
    args = parser.parse_args()
    BINARY = args.binary.resolve()
    if sys.platform != 'linux':
        raise SystemExit('These process/package fixtures require Linux')
    unittest.main(argv=[sys.argv[0]])
