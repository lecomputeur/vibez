#!/usr/bin/env python3
"""Inspect the actual Store submission package without executing or installing it."""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

NS = {'p': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10'}


def verify(package: Path, version: str):
    if not re.fullmatch(r'3\.\d+\.\d+', version):
        raise ValueError('Invalid expected VibeZ 3 version')
    with ZipFile(package) as archive:
        if archive.namelist().count('AppxManifest.xml') != 1:
            raise ValueError('MSIX must contain one root AppxManifest.xml')
        document = ET.fromstring(archive.read('AppxManifest.xml'))
        identity = document.find('p:Identity', NS)
        expected = {
            'Name': 'LeComputeur.VibeZDesktop',
            'Publisher': 'CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95',
            'Version': version + '.0', 'ProcessorArchitecture': 'x64',
        }
        if identity is None or any(identity.get(k) != v for k, v in expected.items()):
            raise ValueError('Store MSIX identity, publisher, architecture or version mismatch')
        applications = document.findall('p:Applications/p:Application', NS)
        if len(applications) != 1 or any(applications[0].get(k) != v for k, v in {
            'Id': 'VibeZDesktop', 'Executable': 'vibez3.exe',
            'EntryPoint': 'Windows.FullTrustApplication',
        }.items()):
            raise ValueError('Store MSIX application entry point mismatch')
        if archive.namelist().count('vibez3.exe') != 1:
            raise ValueError('Store MSIX is missing its unique ordinary client executable')
        with archive.open('vibez3.exe') as executable:
            if executable.read(2) != b'MZ':
                raise ValueError('Store MSIX executable is not a PE image')
    print(f'MSIX_IDENTITY_OK: {version}.0; approved x64 Store identity and vibez3.exe; package creation is not Store submission')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    verify(args.package, args.version)
