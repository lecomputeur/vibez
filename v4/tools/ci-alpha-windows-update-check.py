#!/usr/bin/env python3
"""Genuine signed MSI and NSIS Alpha A->B updates on disposable native Windows.

Installs the actual previous Alpha, stages the actual signed next package, then
lets that unmodified production app perform its own next-start update. No real
Mistral login is used. Stable 3.0.9 is actually installed beside both transitions.
"""
import argparse
import ctypes
from ctypes import wintypes
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

BASE = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


install = module('alpha_install_check', BASE / 'tools/ci-alpha-windows-install-check.py')
shared = module('alpha_real_update', BASE / 'tools/test-alpha-real-native-update.py')
require = shared.require


def owned_processes(root):
    """Query image paths, never terminate a process outside our fixture install."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', wintypes.LONG), ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    require(snapshot != ctypes.c_void_p(-1).value, 'Cannot inspect owned update processes')
    found = []
    try:
        entry = Entry(); entry.dwSize = ctypes.sizeof(Entry)
        success = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while success:
            process = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
            if process:
                try:
                    size = wintypes.DWORD(32768); buffer = ctypes.create_unicode_buffer(size.value)
                    if kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                        path = Path(buffer.value)
                        if path.is_relative_to(root): found.append((entry.th32ProcessID, path))
                finally: kernel.CloseHandle(process)
            success = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally: kernel.CloseHandle(snapshot)
    return found


def stop_owned(root):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    for pid, path in owned_processes(root):
        handle = kernel.OpenProcess(1, False, pid)
        if handle:
            try: kernel.TerminateProcess(handle, 0)
            finally: kernel.CloseHandle(handle)
    deadline = time.monotonic() + 10
    while owned_processes(root) and time.monotonic() < deadline: time.sleep(.1)
    require(not owned_processes(root), 'Owned test processes did not close')


def check(args):
    runner = install.native_ci_only()
    shared.native_ci_only('windows-msi')
    install.no_existing_vibez()
    env = dict(os.environ); manager = install.Installer()
    stable = manager.properties(args.stable_msi)
    before_msi = manager.properties(args.from_msi); after_msi = manager.properties(args.to_msi)
    expected = json.loads(args.feed.read_text(encoding='utf-8'))['version']
    require(stable['ProductVersion'] == '3.0.9', 'Wrong stable test installer')
    require(before_msi['UpgradeCode'] == after_msi['UpgradeCode'], 'Alpha update changed its upgrade identity')
    require(before_msi['UpgradeCode'] != stable['UpgradeCode'], 'Alpha update shares stable upgrade identity')
    require(before_msi['ProductCode'] != after_msi['ProductCode'], 'Next MSI needs a new product identity')
    for product in (stable['ProductCode'], before_msi['ProductCode'], after_msi['ProductCode']):
        require(manager.state(product) < 0, 'Refusing to change an existing installer product')
    report = {'passed': False, 'from_version': args.from_version, 'to_version': expected,
              'actual_previous_production_app': True, 'actual_signed_target_packages': True,
              'network_download_route_tested': False, 'real_mistral_sign_in_tested': False,
              'dummy_profile_markers_only': True, 'github_hosted_disposable_runner': True,
              'existing_user_profile_used': False, 'msix_built_or_installed': False,
              'input_sha256': {path.name: shared.digest(path) for path in
                  (args.stable_msi, args.from_msi, args.from_nsis, args.to_msi, args.to_nsis, args.feed)}, 'transitions': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    logs = args.output.parent / 'windows-update-private-logs'; logs.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='vibez-genuine-update-', dir=runner) as temporary:
        root = Path(temporary).resolve(); stable_dir = root / 'Stable309'
        stable_snapshot = None
        def stable_unchanged():
            require(install.snapshot(stable_dir) == stable_snapshot, 'Alpha update changed stable 3.0.9 files')
            require(manager.state(stable['ProductCode']) == 5, 'Alpha update unregistered stable 3.0.9')
            require(manager.registered_version(stable['ProductCode']) == '3.0.9', 'Alpha update changed stable version')
        try:
            manager.install(args.stable_msi, stable_dir, logs / 'stable-install.log')
            stable_snapshot = install.snapshot(stable_dir)
            for kind in ('msi', 'nsis'):
                fixture = root / kind; fixture.mkdir(); destination = fixture / 'AlphaInstall'
                profile_created = False
                try:
                    if kind == 'msi': manager.install(args.from_msi, destination, logs / 'alpha6-msi-install.log')
                    else: install.run(subprocess.list2cmdline([str(args.from_nsis), '/S']) + ' /D=' + str(destination))
                    executable = destination / 'vibez4-alpha.exe'
                    shared.version(executable, args.from_version, env); stable_unchanged()
                    cache, markers = shared.seed_profile('windows-' + kind, env, fixture)
                    profile_created = True
                    backends=list(destination.rglob('capfs.py'))
                    runtimes=[path for path in destination.rglob('python.exe') if path.parent.name=='python-runtime']
                    require(len(backends)==1 and len(runtimes)==1,'Previous installed backend/runtime absent or ambiguous')
                    before_bindings=shared.check_bundled_bindings(backends[0].parent,runtimes[0],
                        'windows-'+kind,env,fixture,'before')
                    shared.markers_unchanged(markers)
                    staged, version = shared.stage(cache, args.feed, getattr(args, 'to_' + kind), 'windows-' + kind)
                    log = (logs / (kind + '-actual-updater.log')).open('wb')
                    try:
                        original = subprocess.Popen([str(executable)], env=env, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, creationflags=0x00000200)
                        deadline = time.monotonic() + 150; updated = False
                        while time.monotonic() < deadline:
                            try:
                                current = subprocess.check_output([str(executable), '--version'], env=env,
                                    text=True, encoding='utf-8', timeout=5, creationflags=0x08000000)
                                if version in current and not (staged / 'release.json').exists() and any(
                                        path.name.lower() == 'vibez4-alpha.exe' for _, path in owned_processes(destination)):
                                    updated = True; break
                            except (OSError, subprocess.SubprocessError): pass
                            time.sleep(.3)
                        require(updated, 'Production ' + kind + ' updater did not install and start the next Alpha')
                        time.sleep(5)
                        shared.markers_unchanged(markers); stable_unchanged()
                        backends=list(destination.rglob('capfs.py'))
                        runtimes=[path for path in destination.rglob('python.exe') if path.parent.name=='python-runtime']
                        require(len(backends)==1 and len(runtimes)==1,'Updated installed backend/runtime absent or ambiguous')
                        after_bindings=shared.check_bundled_bindings(backends[0].parent,runtimes[0],
                            'windows-'+kind,env,fixture,'after')
                        shared.markers_unchanged(markers)
                        require(not (staged / 'package').exists(), 'Updated app did not clean its cached package')
                        install.installed_alpha_check(destination, version, args.output.parent / ('updated-' + kind + '-backend.json'))
                        stable_unchanged()
                        report['transitions'].append({'format': kind, 'passed': True,
                            'production_previous_app_applied_signed_target': True,
                            'automatic_next_start_apply': True, 'new_version_started': True,
                            'settings_bytes_preserved': True, 'webview_dummy_profile_marker_preserved': True,
                            'project_and_conversation_bindings_preserved': True,
                            'work_code_and_chat_bindings_loaded_by_actual_previous_backend':before_bindings,
                            'work_code_and_chat_bindings_loaded_by_actual_updated_backend':after_bindings,
                            'manually_paused_bindings_preserved': True, 'linked_workspace_files_unchanged': True,
                            'actual_installed_stable_309_unchanged': True,
                            'staging_cleaned_after_install': True})
                    finally: log.close()
                finally:
                    stop_owned(destination)
                    for product in (after_msi['ProductCode'], before_msi['ProductCode']):
                        if manager.state(product) >= 0: manager.remove(product, logs / (kind + '-cleanup-' + product.strip('{}') + '.log'))
                    uninstaller = destination / 'uninstall.exe'
                    if uninstaller.exists(): install.run(subprocess.list2cmdline([str(uninstaller), '/S']) + ' _?=' + str(destination))
                    # These ID directories were absent on entry and created only by seed_profile.
                    if profile_created:
                        for path in set(shared.profile_paths('windows-' + kind, env)):
                            if path.exists(): shutil.rmtree(path)
                stable_unchanged()
            report['stable_file_count'] = len(stable_snapshot)
            report['passed'] = True
        finally:
            if manager.state(stable['ProductCode']) >= 0: manager.remove(stable['ProductCode'], logs / 'stable-cleanup.log')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('stable-msi', 'from-msi', 'from-nsis', 'to-msi', 'to-nsis', 'feed', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--from-version', required=True)
    args = parser.parse_args()
    for name in ('stable_msi', 'from_msi', 'from_nsis', 'to_msi', 'to_nsis', 'feed'):
        setattr(args, name, getattr(args, name).resolve(strict=True))
    try:
        proof = check(args)
    except Exception as error:
        proof = {'passed': False, 'error': str(error), 'real_mistral_sign_in_tested': False,
                 'github_hosted_disposable_runner': True, 'network_download_route_tested': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(proof, indent=2))
    raise SystemExit(0 if proof['passed'] else 1)
