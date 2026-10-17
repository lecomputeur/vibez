import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('verify_msix', ROOT / 'tools/release-v3/verify-msix.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class MsixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name) / 'candidate.msix'

    def write(self, version='3.0.7.0', identity='LeComputeur.VibeZDesktop', architecture='x64', executable=True):
        manifest = f'''<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">
<Identity Name="{identity}" Publisher="CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95" Version="{version}" ProcessorArchitecture="{architecture}"/>
<Applications><Application Id="VibeZDesktop" Executable="vibez3.exe" EntryPoint="Windows.FullTrustApplication"/></Applications></Package>'''
        with ZipFile(self.package, 'w') as archive:
            archive.writestr('AppxManifest.xml', manifest)
            if executable:
                archive.writestr('vibez3.exe', b'MZ' + b'fixture' * 200)

    def check(self):
        with contextlib.redirect_stdout(io.StringIO()):
            verifier.verify(self.package, '3.0.7')

    def test_approved_identity_and_four_part_version_pass(self):
        self.write()
        self.check()

    def test_old_manifest_version_rejected_even_with_new_package_filename(self):
        self.write(version='3.0.6.0')
        with self.assertRaises(ValueError):
            self.check()

    def test_unapproved_product_identity_rejected(self):
        self.write(identity='VibeZ.ResizeTest')
        with self.assertRaises(ValueError):
            self.check()

    def test_wrong_architecture_rejected(self):
        self.write(architecture='arm64')
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_executable_rejected(self):
        self.write(executable=False)
        with self.assertRaises(ValueError):
            self.check()
