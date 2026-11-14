#!/usr/bin/python3
"""The root-owned, Alpha-only Linux updater. Never upgrades other packages.

A signed manifest selects one immutable, hash-checked package. Installation is
deferred while any V4 Alpha process is running. Neither user project directories
nor the VibeZ 3 installation are used as update inputs.
"""
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request

FEED = 'https://github.com/lecomputeur/vibez/releases/download/v4-alpha-channel/alpha-linux.json'
FINGERPRINT = 'C641D84B6DAC2706B4EAE31DFB13C1E6EF8EE4E3'
STATE = Path('/var/lib/vibez4-alpha-updater')
KEYRING = Path('/usr/lib/vibez4-alpha-updater/alpha-updates.gpg')
MAX_PACKAGE = 512 * 1024 * 1024
# V4 Alpha, Beta, release candidate and final 4.x releases share this channel,
# so an Alpha installation moves on to the Beta without being reinstalled.
VERSION = re.compile(r'^4\.([0-9]+)\.([0-9]+)(?:-(alpha|beta|rc)\.([1-9][0-9]*))?$')
STAGES = {'alpha': 0, 'beta': 1, 'rc': 2, None: 3}
ALLOWED_HOSTS = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
ROOT_UID = 0
INIT = """install -d -m 0755 /var/lib/vibez4-alpha-updater
touch /var/lib/vibez4-alpha-updater/running.lock
chmod 0644 /var/lib/vibez4-alpha-updater/running.lock
if [ -d /run/systemd/system ]; then
  systemctl daemon-reload
  if [ ! -e /var/lib/vibez4-alpha-updater/initialized ]; then
    systemctl enable --now vibez4-alpha-update.timer
    touch /var/lib/vibez4-alpha-updater/initialized
  fi
fi"""
ENABLE = '#!/bin/sh\nset -e\n' + INIT + '\n'
REMOVE = """#!/bin/sh
set -e
if [ "$1" = remove ] && [ -d /run/systemd/system ]; then
  systemctl disable --now vibez4-alpha-update.timer || true
fi
"""
RPM_ENABLE = INIT
RPM_REMOVE = """if [ "$1" = 0 ] && [ -d /run/systemd/system ]; then
  systemctl disable --now vibez4-alpha-update.timer || true
fi"""
ARCH_INSTALL = 'post_install() {\n' + INIT + '\n}\npost_upgrade() {\n' + INIT + """
}
pre_remove() {
  if [ -d /run/systemd/system ]; then
    systemctl disable --now vibez4-alpha-update.timer || true
  fi
}
"""


def version(value):
    match = VERSION.fullmatch(value) if isinstance(value, str) else None
    if not match or any(len(x) > 6 for x in match.groups() if x):
        raise ValueError('Only a numbered V4 release is permitted')
    minor, patch, stage, number = match.groups()
    return (4, int(minor), int(patch), STAGES[stage], int(number or 0))


def rpm_form(release):
    """4.0.0-beta.1 is packaged as RPM 4.0.0-0.beta.1, a final 4.0.0 as 4.0.0-1."""
    base, _, pre = release.partition('-')
    return base + ('-0.' + pre if pre else '-1')


def arch_form(release):
    """4.0.0-beta.1 is packaged as Arch 4.0.0_beta.1-1, a final 4.0.0 as 4.0.0-1."""
    return release.replace('-', '_', 1) + '-1'


def allowed_url(value):
    url = urllib.parse.urlsplit(value)
    return (url.scheme == 'https' and url.hostname in ALLOWED_HOSTS and
            url.port in (None, 443) and not url.username and not url.password)


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        count = getattr(req, '_alpha_redirects', 0) + 1
        if count > 5 or not allowed_url(newurl):
            raise ValueError('Untrusted update redirect')
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        result._alpha_redirects = count
        return result


def download(url, target, limit):
    if not allowed_url(url):
        raise ValueError('Untrusted update address')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirect())
    request = urllib.request.Request(url, headers={'User-Agent': 'VibeZ-V4-Alpha-Updater'})
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    with opener.open(request, timeout=40) as response, os.fdopen(os.open(target, flags, 0o600), 'wb') as output:
        count = 0
        while block := response.read(65536):
            count += len(block)
            if count > limit:
                raise ValueError('Update exceeds its size limit')
            output.write(block)
        output.flush()
        os.fsync(output.fileno())


def manifest(data, kind):
    if not isinstance(data, dict) or data.get('schema') != 1 or data.get('channel') != 'v4-alpha':
        raise ValueError('Wrong update channel')
    release = data.get('version')
    version(release)
    asset = data.get('assets', {}).get('linux-x86_64-' + kind)
    if not isinstance(asset, dict):
        raise ValueError('No package for this installation')
    name = f'VibeZ-{release}-Linux-x64.{kind}'
    url = f'https://github.com/lecomputeur/vibez/releases/download/v{release}/{name}'
    if asset.get('name') != name or asset.get('url') != url:
        raise ValueError('Package identity does not match its release')
    if type(asset.get('size')) is not int or not 0 < asset['size'] <= MAX_PACKAGE:
        raise ValueError('Invalid package size')
    if not isinstance(asset.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', asset['sha256']):
        raise ValueError('Invalid package digest')
    return release, asset


def package_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        return False
    name = str(path)
    return (name == 'usr/bin/vibez4-alpha' or
            name.startswith('usr/lib/VibeZ V4 Alpha/') or
            name in {'usr/lib/vibez4-alpha-updater/update.py', 'usr/lib/vibez4-alpha-updater/alpha-updates.gpg'} or
            name in {'usr/lib/systemd/system/vibez4-alpha-update.service',
                     'usr/lib/systemd/system/vibez4-alpha-update.timer',
                     'usr/share/applications/nl.lecomputeur.vibez4.alpha.desktop',
                     'usr/share/metainfo/nl.lecomputeur.vibez4.alpha.metainfo.xml',
                     'usr/share/pixmaps/nl.lecomputeur.vibez4.alpha.png'} or
            re.fullmatch(r'usr/share/icons/hicolor/(?:128x128|256x256|512x512)/apps/(?:nl\.lecomputeur\.vibez4\.alpha|vibez4-alpha)\.png', name) is not None or
            name.startswith('usr/share/licenses/vibez4-alpha/') or
            name.startswith('usr/share/doc/vibe-z-v4-alpha/'))


def package_directory(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        return False
    name = str(path)
    return (name in {'.', 'usr', 'usr/bin', 'usr/lib', 'usr/lib/VibeZ V4 Alpha',
                     'usr/lib/vibez4-alpha-updater', 'usr/lib/systemd', 'usr/lib/systemd/system',
                     'usr/share', 'usr/share/applications', 'usr/share/metainfo', 'usr/share/pixmaps',
                     'usr/share/icons', 'usr/share/icons/hicolor', 'usr/share/licenses',
                     'usr/share/licenses/vibez4-alpha', 'usr/share/doc', 'usr/share/doc/vibe-z-v4-alpha'} or
            name.startswith('usr/lib/VibeZ V4 Alpha/') or
            name.startswith('usr/share/licenses/vibez4-alpha/') or
            name.startswith('usr/share/doc/vibe-z-v4-alpha/') or
            re.fullmatch(r'usr/share/icons/hicolor/(?:128x128|256x256|512x512)(?:/apps)?', name) is not None)


def safe_entry(entry, seen):
    name = str(PurePosixPath(entry.name))
    if (name in seen or entry.issym() or entry.islnk() or not (entry.isdir() or entry.isfile()) or
            entry.uid != 0 or entry.gid != 0 or entry.mode & 0o7022 or
            not (package_directory(name) if entry.isdir() else package_path(name))):
        raise ValueError('Update contains an unsafe or foreign payload entry')
    seen.add(name)
    return entry.size


def verify_manifest(feed, signature):
    verified = run(['gpgv', '--status-fd=1', '--keyring', str(KEYRING), str(signature), str(feed)])
    signers = [line.split()[2] for line in verified.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
    if signers != [FINGERPRINT]:
        raise ValueError('Wrong Alpha update signing key')
    return json.loads(feed.read_text())


def run(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=180)


def installed():
    if shutil.which('dpkg-query'):
        result = subprocess.run(['dpkg-query', '-W', '-f=${Version}', 'vibe-z-v4-alpha'], capture_output=True, text=True)
        if result.returncode == 0:
            version(result.stdout)
            return 'deb', result.stdout
    if shutil.which('rpm'):
        result = subprocess.run(['rpm', '-q', '--qf', '%{VERSION}-%{RELEASE}', 'vibez4-alpha'], capture_output=True, text=True)
        if result.returncode == 0:
            match = re.fullmatch(r'(4\.[0-9]+\.[0-9]+)-(?:0\.((?:alpha|beta|rc)\.[1-9][0-9]*)|1)', result.stdout)
            if not match:
                raise ValueError('Unexpected installed Alpha RPM version')
            value = match[1] + ('-' + match[2] if match[2] else '')
            version(value)
            return 'rpm', value
    if shutil.which('pacman'):
        result = subprocess.run(['pacman', '-Q', 'vibez4-alpha'], capture_output=True, text=True)
        if result.returncode == 0:
            match = re.fullmatch(r'vibez4-alpha (4\.[0-9]+\.[0-9]+)(?:_((?:alpha|beta|rc)\.[1-9][0-9]*))?-1\n?', result.stdout)
            if not match:
                raise ValueError('Unexpected installed Alpha Arch version')
            value = match[1] + ('-' + match[2] if match[2] else '')
            version(value)
            return 'pkg.tar.zst', value
    raise ValueError('No independent V4 Alpha package is installed')


def alpha_running():
    for item in Path('/proc').iterdir():
        if item.name.isdigit():
            try:
                name = os.readlink(item / 'exe').removesuffix(' (deleted)')
                if Path(name).name == 'vibez4-alpha':
                    return True
            except FileNotFoundError:
                pass
            except PermissionError:
                # A hidden process cannot establish that all Alpha apps closed.
                return True
    return False


def validate_deb(path, release):
    info = run(['dpkg-deb', '-f', str(path)])
    fields = dict(line.split(':', 1) for line in info.splitlines() if line and not line[0].isspace() and ':' in line)
    if (fields.get('Package', '').strip() != 'vibe-z-v4-alpha' or
            fields.get('Version', '').strip() != release or fields.get('Architecture', '').strip() != 'amd64' or
            {'Conflicts', 'Replaces', 'Breaks', 'Provides'} & fields.keys()):
        raise ValueError('Package may not replace another application')
    payload = subprocess.Popen(['dpkg-deb', '--fsys-tarfile', str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        total, seen = 0, set()
        with tarfile.open(fileobj=payload.stdout, mode='r|') as archive:
            for count, entry in enumerate(archive):
                if count > 5000:
                    raise ValueError('Too many payload entries')
                total += safe_entry(entry, seen)
                if total > 1024 * 1024 * 1024:
                    raise ValueError('Expanded package too large')
        if payload.wait(timeout=30) != 0:
            raise ValueError('Cannot inspect package payload')
    finally:
        if payload.poll() is None:
            payload.kill()
        payload.wait()
    controls = subprocess.Popen(['dpkg-deb', '--ctrl-tarfile', str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        with tarfile.open(fileobj=controls.stdout, mode='r|') as archive:
            seen = set()
            for count, entry in enumerate(archive):
                name = str(PurePosixPath(entry.name))
                if entry.isdir() and name == '.':
                    continue
                if count > 5 or name in seen or entry.uid != 0 or entry.gid != 0 or entry.mode & 0o7022 or not entry.isfile() or entry.size > 65536 or name not in {'control', 'md5sums', 'postinst', 'prerm'}:
                    raise ValueError('Unexpected installer hook')
                seen.add(name)
                if name in {'postinst', 'prerm'}:
                    wanted = ENABLE if name == 'postinst' else REMOVE
                    if archive.extractfile(entry).read().decode() != wanted:
                        raise ValueError('Unexpected installer hook')
            if not {'control', 'postinst', 'prerm'} <= seen:
                raise ValueError('Missing expected Alpha installer hooks')
        if controls.wait(timeout=30) != 0:
            raise ValueError('Cannot inspect package control archive')
    finally:
        if controls.poll() is None:
            controls.kill()
        controls.wait()


def validate_rpm(path, release):
    info = run(['rpm', '-qp', '--qf', '%{NAME}\n%{VERSION}-%{RELEASE}\n%{ARCH}', str(path)]).splitlines()
    canonical = rpm_form(release)
    if info != ['vibez4-alpha', canonical, 'x86_64']:
        raise ValueError('Wrong Alpha RPM identity')
    for flag in ['--conflicts', '--obsoletes']:
        if run(['rpm', '-qp', flag, str(path)]).strip():
            raise ValueError('RPM may not replace another application')
    listing = run(['rpm', '-qp', '--qf', '[%{FILENAMES}\t%{FILEMODES}\t%{FILELINKTOS}\t%{FILEUSERNAME}\t%{FILEGROUPNAME}\t%{FILECAPS}\n]', str(path)])
    seen = set()
    for line in listing.splitlines():
        name, mode, link, owner, group, caps = line.split('\t')
        relative = name.removeprefix('/')
        mode = int(mode)
        if (relative in seen or link or owner != 'root' or group != 'root' or caps not in {'', '(none)'} or mode & 0o7022 or
                not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)) or
                not (package_directory(relative) if stat.S_ISDIR(mode) else package_path(relative))):
            raise ValueError('RPM contains an unsafe or foreign payload entry')
        seen.add(relative)
    for tag, allowed in [('PREIN', ''), ('PREUN', RPM_REMOVE), ('POSTIN', ''), ('POSTUN', ''), ('PRETRANS', ''), ('POSTTRANS', RPM_ENABLE), ('VERIFYSCRIPT', '')]:
        body = run(['rpm', '-qp', '--qf', '%{' + tag + '}', str(path)]).strip()
        if body != (allowed.strip() if allowed else '(none)'):
            raise ValueError('Unexpected RPM installer hook')
        if allowed:
            interpreter = run(['rpm', '-qp', '--qf', '[%{' + tag + 'PROG}\n]', str(path)]).splitlines()
            if interpreter != ['/bin/sh']:
                raise ValueError('Unexpected RPM installer interpreter')
        flags = run(['rpm', '-qp', '--qf', '%{' + tag + 'FLAGS}', str(path)]).strip()
        if flags not in {'(none)', '0'}:
            raise ValueError('Unexpected RPM script expansion flags')
    for tag in ['TRIGGERSCRIPTS', 'FILETRIGGERSCRIPTS', 'TRANSFILETRIGGERSCRIPTS']:
        if run(['rpm', '-qp', '--qf', '[%{' + tag + '}]', str(path)]).strip():
            raise ValueError('Unexpected RPM trigger hook')


def validate_arch(path, release):
    process = subprocess.Popen(['zstd', '-dc', '--', str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        metadata, install, seen, total = None, None, set(), 0
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            for count, entry in enumerate(archive):
                name = str(PurePosixPath(entry.name))
                if count > 5000 or entry.mode & 0o7022 or entry.uid != 0 or entry.gid != 0:
                    raise ValueError('Unsafe Arch payload')
                if name in {'.PKGINFO', '.INSTALL', '.BUILDINFO', '.MTREE'}:
                    if name in seen or not entry.isfile() or entry.size > 131072:
                        raise ValueError('Unexpected Arch package metadata')
                    seen.add(name)
                    data = archive.extractfile(entry).read()
                    if name == '.PKGINFO':
                        metadata = data.decode()
                    elif name == '.INSTALL':
                        install = data.decode()
                else:
                    safe_entry(entry, seen)
                total += entry.size
                if total > 1024 * 1024 * 1024:
                    raise ValueError('Expanded package too large')
        if process.wait(timeout=30) != 0 or metadata is None or install != ARCH_INSTALL:
            raise ValueError('Wrong Arch installer hook or missing metadata')
        fields = {}
        for line in metadata.splitlines():
            if line and not line.startswith('#'):
                key, value = line.split(' = ', 1)
                fields.setdefault(key, []).append(value)
        if (fields.get('pkgname') != ['vibez4-alpha'] or fields.get('arch') != ['x86_64'] or
                fields.get('pkgver') != [arch_form(release)] or
                {'conflict', 'replaces', 'provides', 'backup'} & fields.keys()):
            raise ValueError('Wrong Arch identity or foreign package relationship')
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()


def status(value):
    target = STATE / 'status.json'
    temporary = STATE / 'status.tmp'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'w') as output:
        json.dump(value, output)
        output.write('\n')
    os.replace(temporary, target)


def main():
    if os.geteuid() != 0 or platform.machine() not in {'x86_64', 'amd64'}:
        raise RuntimeError('This updater is only for root-owned Linux x64 Alpha packages')
    STATE.mkdir(mode=0o755, exist_ok=True)
    for item in [STATE, KEYRING, Path(__file__)]:
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != ROOT_UID or info.st_mode & 0o022:
            raise RuntimeError('Updater files must be root-owned and not writable by other users')
    lock = os.open(STATE / 'lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock, 'w') as held:
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        kind, current = installed()
        try:
            with tempfile.TemporaryDirectory(prefix='check-', dir=STATE) as tmp:
                root = Path(tmp)
                feed, signature = root / 'alpha.json', root / 'alpha.json.asc'
                download(FEED, feed, 131072)
                download(FEED + '.asc', signature, 32768)
                release, asset = manifest(verify_manifest(feed, signature), kind)
                if version(release) <= version(current):
                    status({'status': 'current', 'current': current, 'channel': 'v4-alpha'})
                    return
                cache = STATE / 'packages'
                cache.mkdir(mode=0o700, exist_ok=True)
                info = cache.lstat()
                if stat.S_ISLNK(info.st_mode) or info.st_uid != ROOT_UID or info.st_mode & 0o077:
                    raise ValueError('Untrusted package cache')
                package = cache / asset['name']
                if not package.exists():
                    staged = root / asset['name']
                    download(asset['url'], staged, asset['size'])
                    os.replace(staged, package)
                info = package.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid != ROOT_UID or info.st_mode & 0o022:
                    raise ValueError('Untrusted cached package')
                if package.stat().st_size != asset['size'] or hashlib.sha256(package.read_bytes()).hexdigest() != asset['sha256']:
                    package.unlink()
                    raise ValueError('Package checksum does not match signed manifest')
                {'deb': validate_deb, 'rpm': validate_rpm, 'pkg.tar.zst': validate_arch}[kind](package, release)
                running_lock = os.open(STATE / 'running.lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o644)
                with os.fdopen(running_lock, 'w') as running:
                    try:
                        fcntl.flock(running, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        status({'status': 'waiting_for_close', 'current': current, 'available': release, 'channel': 'v4-alpha'})
                        return
                    if alpha_running():
                        status({'status': 'waiting_for_close', 'current': current, 'available': release, 'channel': 'v4-alpha'})
                        return
                    # Install exactly this verified Alpha package, never
                    # upgrade-all. The lock also prevents a new Alpha process
                    # opening old resources midway through installation.
                    command = {'deb': ['dpkg', '-i', str(package)], 'rpm': ['rpm', '-U', '--', str(package)],
                               'pkg.tar.zst': ['pacman', '-U', '--noconfirm', '--', str(package)]}[kind]
                    run(command)
                status({'status': 'updated', 'current': release, 'channel': 'v4-alpha'})
        except Exception as error:
            status({'status': 'error', 'current': current, 'channel': 'v4-alpha', 'error': str(error)[:500]})
            raise


if __name__ == '__main__':
    main()
