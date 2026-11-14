#!/usr/bin/python3
"""Exercise the real signed updater against inert, private AppImage fixtures.

The Tauri mock runtime creates no windows. Tests make no network request and do
not read the production private key, launch an AppImage, or change an installed app.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

BASE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=BASE / 'artifacts/alpha-native-update-client')
    parser.add_argument('--target-dir', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'passed': False, 'fixture_only': True, 'mock_runtime': True,
              'host_displays_used': False, 'host_installation_modified': False,
              'network_requests': False, 'production_private_key_used': False,
              'fixture_appimages_executed': False}
    command = ['cargo', 'test', '--manifest-path', str(BASE / 'desktop/src-tauri/Cargo.toml'),
               '--offline', '--locked', '--release', 'alpha_updates::client_tests', '--', '--test-threads=1']
    env = dict(os.environ)
    for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'APPIMAGE', 'FLATPAK_ID',
                'TAURI_SIGNING_PRIVATE_KEY', 'TAURI_SIGNING_PRIVATE_KEY_PATH',
                'TAURI_SIGNING_PRIVATE_KEY_PASSWORD']:
        env.pop(key, None)
    if args.target_dir:
        env['CARGO_TARGET_DIR'] = str(args.target_dir.resolve())
    with tempfile.TemporaryDirectory(prefix='vibez-alpha-client-environment-') as isolated:
        root = Path(isolated)
        for setting, folder in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                                ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state')]:
            target = root / folder
            target.mkdir(mode=0o700)
            env[setting] = str(target)
        try:
            result = subprocess.run(command, cwd=BASE, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, timeout=600)
            (output / 'cargo-tests.log').write_text(result.stdout)
            cases = re.findall(r'^test alpha_updates::client_tests::([a-z_]+) \.\.\. ok$',
                               result.stdout, re.MULTILINE)
            report['checks'] = {name: True for name in cases}
            report['test_count'] = len(cases)
            report['exit_code'] = result.returncode
            report['passed'] = result.returncode == 0 and len(cases) == 6
            if not report['passed']:
                report['error'] = 'The native updater test suite did not complete all six cases.'
        except Exception as error:
            report['error'] = str(error)
    report['sources_sha256'] = {name: hashlib.sha256((BASE / name).read_bytes()).hexdigest()
                               for name in ['desktop/src-tauri/src/alpha_update_client_tests.rs',
                                            'desktop/src-tauri/src/alpha_updates.rs',
                                            'desktop/src-tauri/tauri.conf.json',
                                            'desktop/src-tauri/Cargo.lock']}
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
