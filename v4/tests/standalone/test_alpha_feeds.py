"""Release-feed proof with inert package fixtures and disposable signing keys."""
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('alpha_feed_fixture_helper', BASE / 'tools/prepare-alpha-update-feeds.py')
feeds = importlib.util.module_from_spec(spec); spec.loader.exec_module(feeds)
VERSION = '4.0.0-alpha.987'


def run(command):
    done = subprocess.run([str(value) for value in command], stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if done.returncode:
        raise AssertionError('Disposable fixture command failed; output withheld')
    return done.stdout


def fixtures(directory):
    directory.mkdir()
    for suffix in feeds.SUFFIXES:
        path = directory / f'VibeZ-{VERSION}-{suffix}'
        if suffix.endswith('.deb'): path.write_bytes(b'!<arch>\n' + b'inert DEB fixture')
        elif suffix.endswith('.rpm'): path.write_bytes(bytes.fromhex('edabeedb') + b'inert RPM fixture')
        elif suffix.endswith('.flatpak'): path.write_bytes(b'flatpak\0inert OSTree fixture')
        elif suffix.endswith('.pkg.tar.zst'): path.write_bytes(bytes.fromhex('28b52ffd') + b'inert Arch fixture')
        elif suffix.endswith('.AppImage'): path.write_bytes(b'\x7fELF\x02\x01\x01\x00AI\x02' + b'inert ELF never executed')
        elif suffix.endswith('.msi'): path.write_bytes(bytes.fromhex('d0cf11e0a1b11ae1') + b'inert MSI fixture')
        elif suffix.endswith('.exe'):
            header = bytearray(64); header[:2] = b'MZ'; header[60:] = (64).to_bytes(4, 'little')
            path.write_bytes(header + b'PE\0\0inert NSIS fixture')
        elif suffix.endswith('.dmg'): path.write_bytes(b'koly' + bytes(508))
        else:
            metadata = plistlib.dumps({'CFBundleIdentifier': feeds.APP_ID, 'CFBundleShortVersionString': VERSION,
                                      'CFBundleVersion': '4.0.987'})
            files = {'VibeZ V4 Alpha.app/Contents/Info.plist': metadata,
                     'VibeZ V4 Alpha.app/Contents/MacOS/vibez4-alpha': b'\xcf\xfa\xed\xfeinert Mach-O never executed'}
            if suffix.endswith('.zip'):
                with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, contents in files.items(): archive.writestr(name, contents)
            else:
                with tarfile.open(path, 'w:gz') as archive:
                    for name, contents in files.items():
                        entry = tarfile.TarInfo(name); entry.size = len(contents)
                        archive.addfile(entry, io.BytesIO(contents))


@unittest.skipUnless(all(shutil.which(name) for name in ('node', 'gpg', 'gpgv', 'openssl')) and
                     (BASE / 'desktop/node_modules/@tauri-apps/cli/tauri.js').is_file(),
                     'Local release signing tools are required for disposable-key fixtures')
class AlphaFeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='vibez-feed-disposable-')
        cls.root = Path(cls.temporary.name)
        cls.artifacts = cls.root / 'artifacts'; fixtures(cls.artifacts)
        cls.keys = cls.root / 'private'; cls.keys.mkdir(mode=0o700)
        cls.minisign = cls.keys / 'throwaway.key'
        cli = BASE / 'desktop/node_modules/@tauri-apps/cli/tauri.js'
        environment = {key: value for key, value in os.environ.items() if not key.startswith('TAURI_SIGNING_')}
        generated = subprocess.run(['node', str(cli), 'signer', 'generate', '--ci', '--password', '',
                                    '--write-keys', str(cls.minisign)], env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if generated.returncode: raise AssertionError('Disposable Minisign generation failed; output withheld')
        cls.minisign.chmod(0o600)
        cls.public = cls.minisign.with_name('throwaway.key.pub')
        cls.gpg_home = cls.keys / 'gpg'; cls.gpg_home.mkdir(mode=0o700)
        run(['gpg', '--homedir', cls.gpg_home, '--batch', '--pinentry-mode', 'loopback', '--passphrase', '',
             '--quick-generate-key', 'Disposable Alpha feed fixture', 'ed25519', 'sign', '0'])
        listing = run(['gpg', '--homedir', cls.gpg_home, '--with-colons', '--list-keys']).decode()
        cls.fingerprint = next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))
        cls.gpg_public = cls.keys / 'public.gpg'
        cls.gpg_public.write_bytes(run(['gpg', '--homedir', cls.gpg_home, '--batch', '--export', cls.fingerprint]))
        cls.output = cls.root / 'prepared'
        cls.original_hashes = {p.name: feeds.file_hash(p) for p in cls.artifacts.iterdir()}
        cls.proof = feeds.prepare(cls.artifacts, cls.output, VERSION, cls.minisign, cls.gpg_home,
            minisign_public=cls.public, gpg_public=cls.gpg_public, fingerprint=cls.fingerprint,
            previous_version='4.0.0-alpha.986', fixture_only=True)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['gpgconf', '--homedir', str(cls.gpg_home), '--kill', 'gpg-agent'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.temporary.cleanup()

    def test_complete_final_set_is_signed_and_native_formats_have_distinct_targets(self):
        self.assertEqual(self.proof['complete_format_count'], 13)
        self.assertTrue(self.proof['all_artifact_signatures_verified'])
        self.assertTrue(self.proof['fixture_only'])
        self.assertFalse(self.proof['published'])
        native = json.loads((self.output / 'channel/alpha.json').read_text())
        self.assertEqual(set(native['platforms']), set(feeds.NATIVE))
        self.assertTrue(native['platforms']['windows-x86_64-msi']['url'].endswith('.msi'))
        self.assertTrue(native['platforms']['windows-x86_64-nsis']['url'].endswith('-Setup.exe'))
        self.assertNotIn('windows-x86_64', native['platforms'])
        self.assertEqual({p.name: feeds.file_hash(p) for p in self.artifacts.iterdir()}, self.original_hashes)

    def test_linux_manifest_matches_real_updater_contract_and_all_checksums(self):
        spec = importlib.util.spec_from_file_location('alpha_feed_linux_contract', BASE / 'packaging/alpha-updater/update.py')
        service = importlib.util.module_from_spec(spec); spec.loader.exec_module(service)
        linux = json.loads((self.output / 'channel/alpha-linux.json').read_text())
        for kind in ('deb', 'rpm', 'pkg.tar.zst'):
            release, asset = service.manifest(linux, kind)
            self.assertEqual(release, VERSION)
            self.assertEqual(asset['sha256'], self.original_hashes[asset['name']])
        self.assertFalse(any('flatpak' in name for name in linux['assets']))
        lines = (self.output / 'release/SHA256SUMS').read_text().splitlines()
        self.assertEqual(len(lines), 26)
        for line in lines:
            digest, name = line.split('  ', 1)
            self.assertEqual(digest, feeds.file_hash(self.output / 'release' / name))

    def test_payload_tampering_and_announced_version_replay_are_rejected(self):
        path = self.output / 'release' / f'VibeZ-{VERSION}-Linux-x64.AppImage'
        signature = path.with_name(path.name + '.sig').read_text()
        public = self.public.read_text()
        tampered = self.root / 'tampered.AppImage'; tampered.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaises(ValueError): feeds.verify_minisign(tampered, signature, public, VERSION)
        with self.assertRaises(ValueError): feeds.verify_minisign(path, signature, public, '4.0.0-alpha.988')
        lines = base64.b64decode(signature.strip()).decode().splitlines()
        lines[2] = lines[2].replace(VERSION, '4.0.0-alpha.988')
        forged = base64.b64encode(('\n'.join(lines) + '\n').encode()).decode()
        with self.assertRaises(ValueError): feeds.verify_minisign(path, forged, public, '4.0.0-alpha.988')

    def test_openpgp_tamper_and_wrong_key_fingerprint_are_rejected(self):
        feed = self.output / 'channel/alpha-linux.json'; signature = feed.with_name(feed.name + '.asc')
        tampered = self.root / 'tampered-linux.json'; tampered.write_bytes(feed.read_bytes() + b'changed')
        with self.assertRaises(ValueError): feeds.verify_gpg(tampered, signature, self.gpg_public, self.fingerprint)
        with self.assertRaises(ValueError): feeds.verify_gpg(feed, signature, self.gpg_public, '0' * 40)

    def test_missing_msix_stale_packages_and_wrong_archive_identity_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            target = Path(temporary) / 'incomplete'; fixtures(target)
            one = target / f'VibeZ-{VERSION}-Windows-x64.msi'; one.unlink()
            with self.assertRaises(ValueError): feeds.validate_inputs(target, VERSION)
            one.write_bytes((self.artifacts / one.name).read_bytes())
            foreign = target / f'VibeZ-{VERSION}-Windows-x64.msix'; foreign.write_bytes(b'not requested')
            with self.assertRaises(ValueError): feeds.validate_inputs(target, VERSION)
            foreign.unlink()
            stale = target / 'VibeZ-3.0.9-Linux-x64.deb'; stale.write_bytes(b'preserve stable')
            with self.assertRaises(ValueError): feeds.validate_inputs(target, VERSION)
            self.assertEqual(stale.read_bytes(), b'preserve stable')
            stale.unlink()
            mac = target / f'VibeZ-{VERSION}-macOS-x64.zip'
            with zipfile.ZipFile(mac, 'w') as archive:
                archive.writestr('Other.app/Contents/Info.plist', plistlib.dumps({'CFBundleIdentifier': 'other.app'}))
                archive.writestr('Other.app/Contents/MacOS/vibez4-alpha', b'\xcf\xfa\xed\xfe')
            with self.assertRaises(ValueError): feeds.validate_inputs(target, VERSION)

    def test_stable_versions_downgrades_and_existing_output_are_never_accepted(self):
        for value in ('3.0.9', '4.0.0', '4.0.0-test.62', '4.0.0-alpha.04', '4.0.0-alpha.1+other'):
            with self.subTest(value=value), self.assertRaises(ValueError): feeds.version(value)
        with self.assertRaises(ValueError):
            feeds.prepare(self.artifacts, self.root / 'downgrade', VERSION, self.minisign, self.gpg_home,
                          previous_version='4.0.0-alpha.988')
        with self.assertRaises(ValueError):
            feeds.prepare(self.artifacts, self.output, VERSION, self.minisign, self.gpg_home)
        self.assertFalse((self.root / 'downgrade').exists())

    def test_explicit_linux_only_signs_all_five_formats_and_leaves_other_platforms_pending(self):
        artifacts = self.root / 'linux-only-artifacts'; artifacts.mkdir()
        for path in self.artifacts.iterdir():
            if '-Linux-x64.' in path.name: shutil.copy2(path, artifacts / path.name)
        output = self.root / 'linux-only-prepared'
        proof = feeds.prepare(artifacts, output, VERSION, self.minisign, self.gpg_home,
            minisign_public=self.public, gpg_public=self.gpg_public, fingerprint=self.fingerprint,
            previous_version='4.0.0-alpha.986', fixture_only=True, linux_only=True)
        self.assertEqual(proof['scope'], 'linux-only')
        self.assertEqual(proof['complete_format_count'], 5)
        self.assertEqual(set(proof['pending_platforms']), {'windows-x64', 'macos-x64', 'macos-arm64'})
        self.assertFalse(proof['windows_macos_artifacts_included'])
        native = json.loads((output / 'channel/alpha.json').read_text())
        self.assertEqual(set(native['platforms']), {'linux-x86_64-appimage'})
        self.assertEqual(len(list((output / 'release').glob('*.sig'))), 5)
        self.assertTrue(proof['all_artifact_signatures_verified'])
        self.assertTrue(proof['all_gpg_signatures_verified'])
        # The full-set default still refuses this directory. An explicit Linux
        # release cannot accidentally imply that Windows/macOS are ready.
        with self.assertRaises(ValueError): feeds.validate_inputs(artifacts, VERSION)

    def test_linux_only_refuses_a_missing_requested_format_or_foreign_platform_file(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            artifacts = Path(temporary) / 'linux'; artifacts.mkdir()
            for path in self.artifacts.iterdir():
                if '-Linux-x64.' in path.name: shutil.copy2(path, artifacts / path.name)
            flatpak = artifacts / f'VibeZ-{VERSION}-Linux-x64.flatpak'; original = flatpak.read_bytes(); flatpak.unlink()
            with self.assertRaises(ValueError): feeds.validate_inputs(artifacts, VERSION, linux_only=True)
            flatpak.write_bytes(original)
            other = self.artifacts / f'VibeZ-{VERSION}-Windows-x64.msi'; shutil.copy2(other, artifacts / other.name)
            with self.assertRaises(ValueError): feeds.validate_inputs(artifacts, VERSION, linux_only=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
