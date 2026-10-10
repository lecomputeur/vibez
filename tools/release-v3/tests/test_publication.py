import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault('VIBEZ_RELEASE_VERSION', json.loads((ROOT / 'desktop/package.json').read_text())['version'])
spec = importlib.util.spec_from_file_location('verify_assets', ROOT / 'tools/release-v3/verify-published-assets.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in verify.REQUIRED:
            (self.root / name).write_bytes(b'test artifact' * 100)
        (self.root / 'source-commit.txt').write_text(verify.SOURCE + '\n')
        entries = sorted(verify.REQUIRED | {'source-commit.txt'})
        self.manifest = ''.join(hashlib.sha256((self.root / name).read_bytes()).hexdigest() + '  ' + name + '\n' for name in entries)
        (self.root / 'SHA256SUMS').write_text(self.manifest)
    def check(self):
        with contextlib.redirect_stdout(io.StringIO()):
            verify.verify(self.root)
    def test_exact_complete_set_passes(self):
        self.check()
    def test_modified_installer_fails(self):
        (self.root / sorted(verify.REQUIRED)[0]).write_bytes(b'changed' * 200)
        with self.assertRaises(ValueError): self.check()
    def test_missing_platform_fails(self):
        (self.root / sorted(verify.REQUIRED)[0]).unlink()
        with self.assertRaises(ValueError): self.check()
    def test_wrong_source_fails(self):
        (self.root / 'source-commit.txt').write_text('0' * 40)
        with self.assertRaises(ValueError): self.check()
    def test_duplicate_manifest_fails(self):
        (self.root / 'SHA256SUMS').write_text(self.manifest + self.manifest.splitlines()[0] + '\n')
        with self.assertRaises(ValueError): self.check()
    def test_path_traversal_fails(self):
        (self.root / 'SHA256SUMS').write_text('0' * 64 + '  ../outside\n')
        with self.assertRaises(ValueError): self.check()
    def test_all_platform_pages_advertise_v3_not_v2(self):
        for name in ('index.html', 'linux.html', 'windows.html', 'macos.html'):
            text = (ROOT / 'docs' / name).read_text()
            self.assertIn('VibeZ 3', text)
            self.assertNotIn('/download/v2.', text)
            self.assertNotIn('Latest stable release: <strong>VibeZ 2', text)
    def test_readme_has_all_twelve_direct_downloads(self):
        text = (ROOT / 'README.md').read_text()
        for name in verify.REQUIRED: self.assertIn(name, text)

if __name__ == '__main__':
    unittest.main()
