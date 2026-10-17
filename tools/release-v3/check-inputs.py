#!/usr/bin/env python3
"""Check production identity, version coherence and native packaging inputs.

This checks source inputs only. It does not certify builds or create release proof.
"""
import argparse
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def check(version):
    if not re.fullmatch(r'3\.\d+\.\d+', version):
        raise ValueError('Expected a stable VibeZ 3 version')
    desktop = ROOT / 'desktop'
    package = json.loads((desktop / 'package.json').read_text())
    lock = json.loads((desktop / 'package-lock.json').read_text())
    config = json.loads((desktop / 'src-tauri/tauri.conf.json').read_text())
    cargo = tomllib.loads((desktop / 'src-tauri/Cargo.toml').read_text())
    cargo_lock = tomllib.loads((desktop / 'src-tauri/Cargo.lock').read_text())
    versions = {
        'package.json': package['version'],
        'package-lock.json': lock['version'],
        'package-lock.json root': lock['packages']['']['version'],
        'tauri.conf.json': config['version'],
        'Cargo.toml': cargo['package']['version'],
        'Cargo.lock': next(p for p in cargo_lock['package'] if p['name'] == 'vibez3')['version'],
    }
    for name, actual in versions.items():
        if actual != version:
            raise ValueError(f'{name}: expected {version}, found {actual}')
    if package['name'] != 'vibez3' or cargo['package']['name'] != 'vibez3':
        raise ValueError('Production package name changed')
    for name, expected in {
        'productName': 'VibeZ 3', 'identifier': 'nl.lecomputeur.vibez3',
        'mainBinaryName': 'vibez3',
    }.items():
        if config[name] != expected:
            raise ValueError(f'Production {name} changed')
    if config['bundle']['targets'] != 'all':
        raise ValueError('Production native bundle targets must remain enabled')
    linux = config['bundle']['linux']
    for field, expected in {
        'preInstallScript': 'linux/preinst.sh',
        'postInstallScript': 'linux/postinst.sh',
        'postRemoveScript': 'linux/postrm.sh',
    }.items():
        if linux['deb'].get(field) != expected or not (desktop / 'src-tauri' / expected).is_file():
            raise ValueError(f'DEB installer hook missing: {field}')
    if linux['rpm'].get('preInstallScript') != 'linux/preinst.sh':
        raise ValueError('RPM installer shutdown hook missing')
    launcher = (desktop / 'src-tauri/linux/nl.lecomputeur.vibez3.desktop').read_text().splitlines()
    for line in ['Exec=vibez3', 'StartupWMClass=nl.lecomputeur.vibez3']:
        if line not in launcher:
            raise ValueError(f'Production launcher mismatch: {line}')
    print(f'PRODUCTION_INPUTS_OK: {version}; identity, versions and native packaging inputs agree (builds not yet certified)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    try:
        check(args.version)
    except (ValueError, KeyError, StopIteration, OSError) as error:
        raise SystemExit(str(error)) from error
