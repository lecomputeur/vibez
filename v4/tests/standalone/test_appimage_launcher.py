"""Check the actual launcher in paths with spaces, plus packaging safety."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('alpha_appimage_launcher', BASE/'tools/prepare-alpha-appimage-launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux ELF AppImage launcher')
class AppImageLauncherTests(unittest.TestCase):
    def make_app(self, root):
        app = root/'VibeZ Alpha é with spaces.AppDir'
        modules = app/'usr/lib/gio/modules'
        modules.mkdir(parents=True)
        shutil.copy2(shutil.which('env'), app/'AppRun')
        (modules/'libgiognutls.so').write_bytes(b'\x7fELFfixture')
        (modules/'giomodule.cache').write_text('libgiognutls.so: gio-tls-backend\n')
        return app

    def test_executed_launcher_overrides_foreign_module_path_preserves_arguments_and_host_env(self):
        with tempfile.TemporaryDirectory() as temp:
            app = self.make_app(Path(temp))
            old_hash = hashlib.sha256((app/'AppRun').read_bytes()).hexdigest()
            parent = dict(os.environ)
            env = dict(parent, GIO_MODULE_DIR='/nonexistent/foreign-provider', APPDIR='/wrong/app')
            result = launcher.prepare(app)
            child = subprocess.check_output([str(app/'AppRun'), 'VIBEZ_ARGUMENT=some words é'], env=env, text=True)
            values = dict(line.split('=',1) for line in child.splitlines() if '=' in line)
            self.assertEqual(values['GIO_MODULE_DIR'], str(app/'usr/lib/gio/modules'))
            self.assertEqual(values['APPDIR'], str(app))
            self.assertEqual(values['VIBEZ_ARGUMENT'], 'some words é')
            self.assertEqual(result['original_launcher_sha256'], old_hash)
            self.assertEqual(dict(os.environ), parent)
            self.assertNotIn('GIO_USE_TLS', values)
            self.assertNotIn('WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS', values)

    def test_prepare_twice_keeps_original_binary_and_wrapper_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            app = self.make_app(Path(temp))
            first = launcher.prepare(app)
            second = launcher.prepare(app)
            self.assertTrue(first['changed'])
            self.assertFalse(second['changed'])
            self.assertEqual(first['original_launcher_sha256'], second['original_launcher_sha256'])
            self.assertEqual(first['wrapper_sha256'], second['wrapper_sha256'])

    def test_missing_tls_provider_rejects_package_without_changing_launcher(self):
        with tempfile.TemporaryDirectory() as temp:
            app = self.make_app(Path(temp))
            original = (app/'AppRun').read_bytes()
            (app/'usr/lib/gio/modules/libgiognutls.so').unlink()
            with self.assertRaises(ValueError):
                launcher.prepare(app)
            self.assertEqual((app/'AppRun').read_bytes(), original)
            self.assertFalse((app/'AppRun.original').exists())

    def test_unknown_existing_backup_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            app = self.make_app(Path(temp))
            (app/'AppRun.original').write_bytes(b'do not replace')
            with self.assertRaises(ValueError):
                launcher.prepare(app)
            self.assertEqual((app/'AppRun.original').read_bytes(), b'do not replace')


if __name__ == '__main__':
    unittest.main()
