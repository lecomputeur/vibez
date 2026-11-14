#!/usr/bin/env python3
"""Prepare and verify local Alpha release files and update feeds. Never publishes.

Requires the complete requested package set, the existing Alpha Minisign private
key and explicit GPG signing home. Default: all 13 formats. --linux-only requires
all five Linux formats and explicitly leaves Windows/macOS out of the feeds.
Signatures are bound to the numbered Alpha version.
OpenSSL verifies Ed25519 signatures independently of the Tauri signing command.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile

BASE = Path(__file__).resolve().parents[1]
FINGERPRINT = 'C641D84B6DAC2706B4EAE31DFB13C1E6EF8EE4E3'
RELEASE_ROOT = 'https://github.com/lecomputeur/vibez/releases/download/'
APP_ID = 'nl.lecomputeur.vibez4.alpha'
MAX_PACKAGE = 512 * 1024 * 1024
NATIVE = {'linux-x86_64-appimage': 'Linux-x64.AppImage',
          'windows-x86_64-nsis': 'Windows-x64-Setup.exe',
          'windows-x86_64-msi': 'Windows-x64.msi',
          'darwin-x86_64-app': 'macOS-x64.app.tar.gz',
          'darwin-aarch64-app': 'macOS-arm64.app.tar.gz'}
SUFFIXES = ('Linux-x64.deb', 'Linux-x64.rpm', 'Linux-x64.flatpak', 'Linux-x64.pkg.tar.zst',
            'Linux-x64.AppImage', 'Windows-x64-Setup.exe', 'Windows-x64.msi',
            'macOS-x64.dmg', 'macOS-x64.zip', 'macOS-x64.app.tar.gz',
            'macOS-arm64.dmg', 'macOS-arm64.zip', 'macOS-arm64.app.tar.gz')


def require(value, message):
    if not value:
        raise ValueError(message)


def version(value):
    match = re.fullmatch(r'4\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-(alpha|beta)\.([1-9][0-9]*)', value)
    require(match and all(len(x) <= 6 for x in match.groups()), 'Only a canonical numbered V4 Alpha or Beta version is allowed')
    minor, patch, stage, number = match.groups()
    return (4, int(minor), int(patch), ('alpha', 'beta').index(stage), int(number))


def file_hash(path, algorithm='sha256'):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def captured(command, label, *, env=None, timeout=180):
    # Signer output can contain key material. It is never printed or written to
    # the release, including when the command fails.
    done = subprocess.run([str(x) for x in command], stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=timeout)
    require(done.returncode == 0, label + ' failed; command output was withheld')
    return done.stdout


def archive_names(names):
    require(0 < len(names) <= 100000, 'Invalid macOS archive member count')
    normalized = [str(PurePosixPath(name)) for name in names]
    require(all(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts for name in normalized),
            'macOS archive has an unsafe member name')
    roots = {PurePosixPath(name).parts[0] for name in normalized}
    require(len(roots) == 1 and next(iter(roots)).endswith('.app'), 'macOS archive must contain one top-level app')
    return next(iter(roots))


def mac_archive(path):
    if path.name.endswith('.zip'):
        with zipfile.ZipFile(path) as stream:
            members = stream.infolist()
            root = archive_names([member.filename for member in members])
            require(sum(member.file_size for member in members) <= 2 * 1024**3, 'macOS archive is too large')
            info = stream.read(root + '/Contents/Info.plist')
            binary = stream.read(root + '/Contents/MacOS/vibez4-alpha')
    else:
        with tarfile.open(path, 'r:gz') as stream:
            members = []
            for member in stream:
                members.append(member)
                require(len(members) <= 100000, 'macOS archive has too many members')
            root = archive_names([member.name for member in members])
            require(sum(member.size for member in members) <= 2 * 1024**3, 'macOS archive is too large')
            info = stream.extractfile(root + '/Contents/Info.plist').read()
            binary = stream.extractfile(root + '/Contents/MacOS/vibez4-alpha').read()
    metadata = plistlib.loads(info)
    require(metadata.get('CFBundleIdentifier') == APP_ID, 'macOS archive has the wrong application identity')
    require(binary[:4] in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'),
            'macOS archive has no Mach-O Alpha executable')
    return {'app_id': APP_ID, 'main_binary_sha256': hashlib.sha256(binary).hexdigest(),
            'info_plist_sha256': hashlib.sha256(info).hexdigest(),
            'bundle_short_version': metadata.get('CFBundleShortVersionString'),
            'bundle_version': metadata.get('CFBundleVersion')}


def format_check(path):
    with path.open('rb') as stream:
        head = stream.read(64)
        name = path.name
        if name.endswith('.deb'):
            require(head.startswith(b'!<arch>\n'), 'Invalid DEB header')
        elif name.endswith('.rpm'):
            require(head.startswith(bytes.fromhex('edabeedb')), 'Invalid RPM header')
        elif name.endswith('.flatpak'):
            require(head.startswith(b'flatpak\0'), 'Invalid Flatpak bundle header')
        elif name.endswith('.pkg.tar.zst'):
            require(head.startswith(bytes.fromhex('28b52ffd')), 'Invalid Arch/Zstandard header')
        elif name.endswith('.AppImage'):
            require(head.startswith(b'\x7fELF') and head[8:11] == b'AI\x02', 'Invalid type-2 AppImage header')
        elif name.endswith('.msi'):
            require(head.startswith(bytes.fromhex('d0cf11e0a1b11ae1')), 'Invalid MSI compound-file header')
        elif name.endswith('.exe'):
            require(head.startswith(b'MZ') and len(head) == 64, 'Invalid Windows installer header')
            offset = int.from_bytes(head[60:64], 'little')
            require(64 <= offset <= 1024**2, 'Invalid Windows PE header offset')
            stream.seek(offset)
            require(stream.read(4) == b'PE\0\0', 'Invalid Windows PE header')
        elif name.endswith('.dmg'):
            require(path.stat().st_size >= 512, 'Truncated macOS disk image')
            stream.seek(-512, os.SEEK_END)
            require(stream.read(4) == b'koly', 'Invalid UDIF disk-image footer')
        elif name.endswith(('.zip', '.app.tar.gz')):
            return mac_archive(path)
        else:
            raise ValueError('Unexpected release format')
    return {'header_checked': True}


def validate_inputs(artifacts, release, *, linux_only=False):
    version(release)
    require(artifacts.is_dir(), 'Final artifact folder is absent')
    suffixes = [suffix for suffix in SUFFIXES if not linux_only or suffix.startswith('Linux-')]
    expected = {f'VibeZ-{release}-{suffix}' for suffix in suffixes}
    found = {entry.name for entry in artifacts.iterdir()}
    require(expected <= found, 'Final package set is incomplete: ' + ', '.join(sorted(expected - found)))
    for name in found - expected:
        # Existing signatures/checksum files can accompany final packages. They
        # are independently rebuilt in the new output; no sidecar is copied.
        require(name == 'SHA256SUMS' or name == 'SHA256SUMS.asc' or name in {x + '.sig' for x in expected},
                'Foreign, stale or unrequested file in final artifact folder: ' + name)
    details = {}
    for name in sorted(expected):
        path = artifacts / name
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and not path.is_symlink() and 0 < info.st_size <= MAX_PACKAGE,
                'Final artifacts must be regular, nonempty files of at most 512 MiB')
        details[name] = format_check(path)
    for arch in (() if linux_only else ('x64', 'arm64')):
        prefix = f'VibeZ-{release}-macOS-{arch}'
        a, b = details[prefix + '.zip'], details[prefix + '.app.tar.gz']
        require(a == b, 'macOS ZIP and update archive do not contain the same app identity/main executable')
    return details


def openssl_verify(public_der, message, signature):
    with tempfile.TemporaryDirectory(prefix='vibez-public-signature-check-') as temporary:
        directory = Path(temporary)
        key, data, sig = [directory / name for name in ('public.der', 'message', 'signature')]
        key.write_bytes(public_der); data.write_bytes(message); sig.write_bytes(signature)
        captured(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey', key, '-keyform', 'DER',
                  '-rawin', '-in', data, '-sigfile', sig], 'Ed25519 signature verification')


def verify_minisign(path, signature, public_key, release):
    # Match minisign-verify 0.3's wire format and both Ed25519 verifications.
    # Tauri wraps the complete Minisign public-key/signature text in base64.
    key_lines = base64.b64decode(public_key.strip(), validate=True).decode('utf-8').splitlines()
    require(len(key_lines) == 2 and key_lines[0].startswith('untrusted comment: '), 'Malformed Alpha public key')
    key = base64.b64decode(key_lines[1], validate=True)
    require(len(key) == 42 and key[:2] in (b'Ed', b'ED'), 'Unsupported Alpha public key')
    lines = base64.b64decode(signature.strip(), validate=True).decode('utf-8').splitlines()
    require(len(lines) == 4 and lines[0].startswith('untrusted comment: ') and lines[2].startswith('trusted comment: '),
            'Malformed Alpha Minisign signature')
    signed = base64.b64decode(lines[1], validate=True)
    global_signature = base64.b64decode(lines[3], validate=True)
    require(len(signed) == 74 and len(global_signature) == 64 and signed[:2] in (b'Ed', b'ED'),
            'Unsupported Alpha Minisign signature')
    require(signed[2:10] == key[2:10], 'Alpha signature uses the wrong public key')
    # RFC 8410 SubjectPublicKeyInfo for a 32-byte Ed25519 public key.
    public_der = bytes.fromhex('302a300506032b6570032100') + key[10:]
    if signed[:2] == b'ED':
        with path.open('rb') as stream:
            message = hashlib.file_digest(stream, 'blake2b').digest()
    else:
        message = path.read_bytes()
    openssl_verify(public_der, message, signed[10:])
    trusted = lines[2][17:]
    openssl_verify(public_der, signed[10:] + trusted.encode('utf-8'), global_signature)
    versions = [field[8:] for field in trusted.split('\t') if field.startswith('version:')]
    require(versions == [release], 'Signature is not bound to the announced Alpha version')


def verify_gpg(feed, signature, public_keyring, fingerprint):
    with tempfile.TemporaryDirectory(prefix='vibez-public-gpg-check-') as temporary:
        verified = captured(['gpgv', '--homedir', temporary, '--status-fd=1', '--keyring', public_keyring,
                             signature, feed], 'OpenPGP manifest verification').decode('utf-8')
    signers = [line.split()[2] for line in verified.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
    require(signers == [fingerprint], 'Manifest was signed with the wrong Alpha OpenPGP key')


def gpg_sign(path, homedir, fingerprint):
    output = path.with_name(path.name + '.asc')
    captured(['gpg', '--homedir', homedir, '--batch', '--no-tty', '--pinentry-mode', 'loopback',
              '--passphrase', '', '--local-user', fingerprint + '!', '--armor', '--detach-sign',
              '--output', output, path], 'OpenPGP signing')
    return output


def prepare(artifacts, output, release, minisign_private, gpg_home, *,
            minisign_public=BASE / 'desktop/src-tauri/alpha-updater.pub',
            gpg_public=BASE / 'desktop/src-tauri/alpha-updates.gpg', fingerprint=FINGERPRINT,
            cli=BASE / 'desktop/node_modules/@tauri-apps/cli/tauri.js', password_file=None,
            previous_version=None, notes='V4 Alpha update.', fixture_only=False, linux_only=False):
    version(release)
    if previous_version is not None:
        require(version(release) > version(previous_version), 'Refusing a downgrade or repeated channel version')
    artifacts = artifacts.resolve(strict=True)
    output = output.absolute()
    require(not output.exists() and not output.is_symlink(), 'Output must be a new directory')
    require(output != artifacts and artifacts not in output.parents and output not in artifacts.parents,
            'Input and output folders must be separate')
    for private in (minisign_private, gpg_home):
        require(not private.is_symlink(), 'Signing paths must not be symlinks')
        private = private.resolve(strict=True)
        require(private != artifacts and artifacts not in private.parents and output not in private.parents,
                'Keep signing material outside artifact/output folders')
    require(minisign_private.is_file() and gpg_home.is_dir(), 'Explicit Alpha signing key/home is absent')
    if os.name == 'posix':
        require(minisign_private.stat().st_mode & 0o077 == 0 and gpg_home.stat().st_mode & 0o077 == 0,
                'Private signing material must be accessible only to its owner')
    require(re.fullmatch('[0-9A-F]{40}', fingerprint), 'Malformed Alpha OpenPGP fingerprint')
    require(cli.is_file() and minisign_public.is_file() and gpg_public.is_file(), 'Signer/public trust inputs are absent')
    details = validate_inputs(artifacts, release, linux_only=linux_only)
    native_targets = {key: suffix for key, suffix in NATIVE.items() if not linux_only or key.startswith('linux-')}
    output.parent.mkdir(parents=True, exist_ok=True)
    public_text = minisign_public.read_text(encoding='utf-8').strip()
    env = {key: value for key, value in os.environ.items() if not key.startswith('TAURI_SIGNING_')}
    env['TAURI_SIGNING_PRIVATE_KEY_PATH'] = str(minisign_private.resolve(strict=True))
    env['TAURI_SIGNING_PRIVATE_KEY_PASSWORD'] = password_file.read_text(encoding='utf-8').rstrip('\r\n') if password_file else ''
    records = {}
    with tempfile.TemporaryDirectory(prefix='alpha-feeds-stage-', dir=output.parent) as temporary:
        stage = Path(temporary); packages = stage / 'release'; channel = stage / 'channel'
        packages.mkdir(); channel.mkdir()
        for name in sorted(details):
            source, destination = artifacts / name, packages / name
            before = (source.stat().st_size, file_hash(source))
            shutil.copy2(source, destination)
            require(before == (destination.stat().st_size, file_hash(destination)) == (source.stat().st_size, file_hash(source)),
                    'Artifact changed while preparing its release copy')
            captured(['node', cli, 'signer', 'sign', '--app-version', release, destination], 'Alpha artifact signing', env=env)
            signature = destination.with_name(name + '.sig').read_text(encoding='utf-8').strip()
            verify_minisign(destination, signature, public_text, release)
            records[name] = {'name': name, 'size': before[0], 'sha256': before[1],
                'url': RELEASE_ROOT + 'v' + release + '/' + name,
                'signature': signature, 'format_validation': details[name]}
        manifest = {'version': release, 'notes': notes,
            'pub_date': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
            'platforms': {key: {'url': records[f'VibeZ-{release}-{suffix}']['url'],
                               'signature': records[f'VibeZ-{release}-{suffix}']['signature']}
                          for key, suffix in native_targets.items()}}
        linux = {'schema': 1, 'channel': 'v4-alpha', 'version': release,
            'assets': {'linux-x86_64-' + kind: {field: records[f'VibeZ-{release}-Linux-x64.{kind}'][field]
                       for field in ('name', 'url', 'size', 'sha256')} for kind in ('deb', 'rpm', 'pkg.tar.zst')}}
        for name, document in [('alpha.json', manifest), ('alpha-linux.json', linux)]:
            feed = channel / name
            feed.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
            verify_gpg(feed, gpg_sign(feed, gpg_home, fingerprint), gpg_public, fingerprint)
        sums = packages / 'SHA256SUMS'
        sums.write_text(''.join(file_hash(path) + '  ' + path.name + '\n' for path in sorted(packages.iterdir())), encoding='utf-8')
        verify_gpg(sums, gpg_sign(sums, gpg_home, fingerprint), gpg_public, fingerprint)
        # A final pass verifies exact copy integrity and the signatures that will
        # be published. Files are never signed in the original artifact folder.
        for name, record in records.items():
            require(file_hash(packages / name) == record['sha256'], 'Final signed artifact changed')
            require(file_hash(artifacts / name) == record['sha256'], 'Original final artifact changed')
            verify_minisign(packages / name, (packages / (name + '.sig')).read_text(encoding='utf-8'), public_text, release)
        proof = {'version': release, 'passed': True, 'published': False, 'fixture_only': fixture_only,
            'complete_format_count': len(records), 'msix_included': False,
            'scope': 'linux-only' if linux_only else 'all-requested-platforms',
            'all_requested_formats_present': True,
            'pending_platforms': ['windows-x64', 'macos-x64', 'macos-arm64'] if linux_only else [],
            'windows_macos_artifacts_included': not linux_only,
            'native_platforms': list(native_targets), 'linux_system_assets': list(linux['assets']),
            'flatpak_update_channel': 'independent signed OSTree origin; no native/system-feed target',
            'minisign_public_key_sha256': file_hash(minisign_public), 'gpg_fingerprint': fingerprint,
            'all_artifact_signatures_verified': True, 'all_signatures_bound_to_version': True,
            'all_gpg_signatures_verified': True, 'input_artifacts_modified': False,
            'existing_installations_or_stable_channel_modified': False,
            'artifacts': [{key: value for key, value in records[name].items() if key != 'signature'} for name in sorted(records)]}
        (stage / 'feed-proof.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
        # Rename the complete staging tree into place only after every check.
        # TemporaryDirectory sees no old directory on successful exit.
        stage.rename(output)
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True, help='Folder containing only the requested final packages and optional existing signature/checksum sidecars')
    parser.add_argument('--output', type=Path, required=True, help='New local release/channel directory; never replaces an existing directory')
    parser.add_argument('--version', '--current-version', dest='version', required=True)
    parser.add_argument('--previous-version')
    parser.add_argument('--minisign-private-key', type=Path, required=True)
    parser.add_argument('--minisign-password-file', type=Path)
    parser.add_argument('--gpg-homedir', type=Path, required=True)
    parser.add_argument('--notes-file', type=Path)
    parser.add_argument('--linux-only', action='store_true', help='Require all five Linux formats and generate only Linux update targets; default still requires all 13 formats')
    args = parser.parse_args()
    proof = prepare(args.artifacts, args.output, args.version, args.minisign_private_key, args.gpg_homedir,
        password_file=args.minisign_password_file, previous_version=args.previous_version,
        notes=args.notes_file.read_text(encoding='utf-8') if args.notes_file else 'V4 Alpha update.', linux_only=args.linux_only)
    print(json.dumps({key: proof[key] for key in ('version', 'passed', 'published', 'scope', 'pending_platforms', 'complete_format_count', 'msix_included')}, indent=2))
