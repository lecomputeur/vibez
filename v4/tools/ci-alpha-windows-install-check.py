#!/usr/bin/env python3
"""Silent MSI/NSIS side-by-side proof on disposable GitHub-hosted Windows only.

Requires the real V3.0.9 MSI and the newly built Alpha MSI/NSIS. Never run on
the user's desktop. All application files use fresh RUNNER_TEMP folders; the
only installed product codes removed are verified absent before this test.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parents[1]
ALPHA_UPGRADE_CODE = '{9C2E12C9-8EE2-4C1C-9D4E-02AD0BD79DA7}'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def native_ci_only():
    require(os.name == 'nt', 'Installer proof requires native Windows')
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted',
            'Refusing installation outside a disposable GitHub-hosted runner')
    require(os.environ.get('RUNNER_OS') == 'Windows', 'Runner OS is not Windows')
    require(not hasattr(ctypes.WinDLL('ntdll'), 'wine_get_version'), 'Installer proof requires native Windows, not Wine')
    root = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    require(root.is_dir(), 'Runner temporary folder is absent')
    return root


class Installer:
    def __init__(self):
        self.dll = ctypes.WinDLL('msi')
        u, up = wintypes.UINT, ctypes.POINTER(wintypes.UINT)
        self.dll.MsiOpenDatabaseW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, up]
        self.dll.MsiDatabaseOpenViewW.argtypes = [u, wintypes.LPCWSTR, up]
        self.dll.MsiViewExecute.argtypes = [u, u]
        self.dll.MsiViewFetch.argtypes = [u, up]
        self.dll.MsiRecordGetStringW.argtypes = [u, u, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.dll.MsiCloseHandle.argtypes = [u]
        self.dll.MsiQueryProductStateW.argtypes = [wintypes.LPCWSTR]
        self.dll.MsiQueryProductStateW.restype = ctypes.c_int
        self.dll.MsiGetProductInfoW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPWSTR,
                                              ctypes.POINTER(wintypes.DWORD)]
        self.msiexec = Path(os.environ['SystemRoot']) / 'System32' / 'msiexec.exe'

    @staticmethod
    def ok(code):
        if code != 0:
            raise OSError(code, 'Windows Installer metadata API failed')

    def text(self, record, index):
        size = wintypes.DWORD(4096)
        buffer = ctypes.create_unicode_buffer(size.value)
        self.ok(self.dll.MsiRecordGetStringW(record, index, buffer, ctypes.byref(size)))
        return buffer.value

    def properties(self, path):
        database, view, row = wintypes.UINT(), wintypes.UINT(), wintypes.UINT()
        self.ok(self.dll.MsiOpenDatabaseW(str(path), None, ctypes.byref(database)))
        try:
            self.ok(self.dll.MsiDatabaseOpenViewW(database, 'SELECT `Property`, `Value` FROM `Property`', ctypes.byref(view)))
            self.ok(self.dll.MsiViewExecute(view, 0))
            found = {}
            while True:
                code = self.dll.MsiViewFetch(view, ctypes.byref(row))
                if code == 259:  # ERROR_NO_MORE_ITEMS
                    break
                self.ok(code)
                try:
                    found[self.text(row, 1)] = self.text(row, 2)
                finally:
                    self.dll.MsiCloseHandle(row)
            return found
        finally:
            if view.value: self.dll.MsiCloseHandle(view)
            self.dll.MsiCloseHandle(database)

    def state(self, code):
        return self.dll.MsiQueryProductStateW(code)

    def registered_version(self, code):
        size = wintypes.DWORD(256); buffer = ctypes.create_unicode_buffer(256)
        self.ok(self.dll.MsiGetProductInfoW(code, 'VersionString', buffer, ctypes.byref(size)))
        return buffer.value

    def install(self, artifact, destination, log):
        # INSTALLDIR is the public install-root property in Tauri's WiX template.
        run([self.msiexec, '/i', artifact, '/qn', '/norestart', '/L*v', log,
             'INSTALLDIR=' + str(destination)])

    def remove(self, product, log):
        run([self.msiexec, '/x', product, '/qn', '/norestart', '/L*v', log])


def run(command):
    # NSIS /D and uninstaller _?= consume the rest of the command line and must
    # be last, unquoted even when the directory contains spaces (NSIS manual).
    process = subprocess.run(command if isinstance(command, str) else [str(x) for x in command],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=0x08000000, timeout=600)
    require(process.returncode in (0, 3010), 'Silent installer failed with exit code ' + str(process.returncode))


def no_existing_vibez():
    import winreg
    keyname = r'Software\Microsoft\Windows\CurrentVersion\Uninstall'
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                key = winreg.OpenKey(hive, keyname, 0, winreg.KEY_READ | view)
            except FileNotFoundError:
                continue
            with key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    with winreg.OpenKey(key, winreg.EnumKey(key, index)) as entry:
                        try:
                            name = winreg.QueryValueEx(entry, 'DisplayName')[0]
                        except FileNotFoundError:
                            continue
                        require(not re.sub(r'\s+', '', str(name)).lower().startswith('vibez'),
                                'Runner already contains a VibeZ installation; refusing to change it')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(folder):
    require(folder.is_dir(), 'Installer ignored its disposable install folder')
    files = {}
    for path in folder.rglob('*'):
        require(not path.is_symlink(), 'Unexpected link in installed fixture')
        if path.is_file():
            files[path.relative_to(folder).as_posix()] = digest(path)
    require(files and any(name.lower().endswith('.exe') for name in files), 'Installed fixture has no executable')
    return files


def installed_alpha_check(folder, version, output):
    executables = list(folder.rglob('vibez4-alpha.exe'))
    require(len(executables) == 1, 'Installed Alpha executable is absent or ambiguous')
    reported = subprocess.check_output([str(executables[0]), '--version'], text=True, encoding='utf-8', timeout=30)
    require(version in reported and 'VibeZ V4 ' in reported, 'Installed Alpha reports the wrong identity')
    backends = list(folder.rglob('capfs.py'))
    runtimes = [path for path in folder.rglob('python.exe') if path.parent.name == 'python-runtime']
    require(len(backends) == 1 and len(runtimes) == 1, 'Installed backend/runtime resources are absent or ambiguous')
    subprocess.run([str(runtimes[0]), '-I', '-B', '-X', 'utf8', str(BASE / 'tools/ci-alpha-backend-check.py'),
        '--target', 'windows-x64', '--backend-dir', str(backends[0].parent), '--output', str(output)],
        check=True, stdin=subprocess.DEVNULL, creationflags=0x08000000, timeout=120)
    require(json.loads(output.read_text(encoding='utf-8'))['native_ntfs_junction_checked'] is True,
            'Installed Alpha did not pass native NTFS boundary proof')


def check(stable_msi, alpha_msi, alpha_nsis, version, output):
    runner_temp = native_ci_only()
    no_existing_vibez()
    installer = Installer()
    stable = installer.properties(stable_msi)
    alpha = installer.properties(alpha_msi)
    match = re.fullmatch(r'4\.0\.0-(alpha|beta)\.([1-9][0-9]*)', version)
    require(match is not None, 'Expected a V4.0.0 Alpha or Beta version')
    # Alpha N installs as MSI 4.0.N, Beta N as 4.0.(100+N), so every Beta upgrades every Alpha.
    sequence = int(match[2]) + (100 if match[1] == 'beta' else 0); require(sequence <= 65535, 'Sequence exceeds MSI version limit')
    require(stable['ProductVersion'] == '3.0.9', 'Stable fixture is not VibeZ 3.0.9')
    require('vibez' in re.sub(r'\s+', '', stable['ProductName']).lower(), 'Stable fixture is not VibeZ')
    require(alpha['ProductName'] == 'VibeZ V4 Alpha', 'Alpha MSI has the wrong product identity')
    require(alpha['ProductVersion'] == f'4.0.{sequence}', 'MSI ProductVersion must be 4.0.N for Alpha N and 4.0.(100+N) for Beta N')
    require(alpha['UpgradeCode'].upper() == ALPHA_UPGRADE_CODE, 'Unexpected Alpha MSI upgrade identity')
    require(stable['UpgradeCode'].upper() != alpha['UpgradeCode'].upper(), 'Alpha MSI would share the stable upgrade identity')
    require(stable['ProductCode'].upper() != alpha['ProductCode'].upper(), 'Alpha MSI would share the stable product identity')
    for product in (stable['ProductCode'], alpha['ProductCode']):
        require(installer.state(product) < 0, 'Fixture product is already registered; refusing changes')
    output.parent.mkdir(parents=True, exist_ok=True)
    logs = output.parent / 'windows-installer-private-logs'; logs.mkdir(exist_ok=True)
    report = {'version': version, 'msi_product_version': alpha['ProductVersion'], 'fixture_only': True,
              'github_hosted_disposable_runner': True, 'existing_user_profile_used': False,
              'msix_built_or_installed': False,
              'artifact_sha256': {path.name: digest(path) for path in (stable_msi, alpha_msi, alpha_nsis)}}
    with tempfile.TemporaryDirectory(prefix='vibez-side-by-side-', dir=runner_temp) as temporary:
        fixture = Path(temporary)
        stable_dir, msi_dir, nsis_dir = [fixture / name for name in ('Stable309', 'AlphaMsi', 'AlphaNsis')]
        stable_snapshot = None
        def stable_unchanged():
            require(snapshot(stable_dir) == stable_snapshot, 'Alpha changed stable V3.0.9 files')
            require(installer.state(stable['ProductCode']) == 5, 'Alpha unregistered stable V3.0.9')
            require(installer.registered_version(stable['ProductCode']) == '3.0.9', 'Stable product version changed')
        try:
            installer.install(stable_msi, stable_dir, logs / 'stable-install.log')
            require(installer.state(stable['ProductCode']) == 5, 'Stable fixture did not register')
            stable_snapshot = snapshot(stable_dir)
            installer.install(alpha_msi, msi_dir, logs / 'alpha-msi-install.log')
            require(installer.state(alpha['ProductCode']) == 5, 'Alpha MSI did not register')
            stable_unchanged()
            installed_alpha_check(msi_dir, version, output.parent / 'installed-msi-backend.json')
            stable_unchanged()
            report['alpha_msi_installed_with_309_unchanged_and_backend_functional'] = True
            installer.remove(alpha['ProductCode'], logs / 'alpha-msi-uninstall.log')
            require(installer.state(alpha['ProductCode']) < 0, 'Alpha MSI remained registered after uninstall')
            stable_unchanged()
            report['alpha_msi_uninstalled_with_309_unchanged'] = True
            require(not any(c in str(nsis_dir) for c in '\r\n"'), 'Invalid disposable NSIS destination')
            run(subprocess.list2cmdline([str(alpha_nsis), '/S']) + ' /D=' + str(nsis_dir))
            stable_unchanged()
            installed_alpha_check(nsis_dir, version, output.parent / 'installed-nsis-backend.json')
            stable_unchanged()
            report['alpha_nsis_installed_with_309_unchanged_and_backend_functional'] = True
            uninstallers = [p for p in nsis_dir.rglob('*.exe') if p.name.lower() == 'uninstall.exe']
            require(len(uninstallers) == 1, 'NSIS uninstaller is absent or ambiguous')
            run(subprocess.list2cmdline([str(uninstallers[0]), '/S']) + ' _?=' + str(nsis_dir))
            stable_unchanged()
            require(not (nsis_dir / 'vibez4-alpha.exe').exists(), 'NSIS uninstaller left the Alpha executable')
            report['alpha_nsis_uninstalled_with_309_unchanged'] = True
            report['stable_baseline_file_count'] = len(stable_snapshot)
            report['stable_baseline_tree_sha256'] = hashlib.sha256(json.dumps(stable_snapshot, sort_keys=True).encode()).hexdigest()
        finally:
            # These exact package identities were verified absent at entry.
            # Hosted runners are disposable if an installer itself cannot clean up.
            if installer.state(alpha['ProductCode']) >= 0:
                installer.remove(alpha['ProductCode'], logs / 'cleanup-alpha-msi.log')
            if installer.state(stable['ProductCode']) >= 0:
                installer.remove(stable['ProductCode'], logs / 'cleanup-stable.log')
    report['passed'] = True
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stable-msi', type=Path, required=True)
    parser.add_argument('--alpha-msi', type=Path, required=True)
    parser.add_argument('--alpha-nsis', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = check(args.stable_msi.resolve(strict=True), args.alpha_msi.resolve(strict=True),
                   args.alpha_nsis.resolve(strict=True), args.version, args.output)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
