#!/usr/bin/env python3
"""Verify the exact VibeZ 3.0.3 release asset set without executing installers."""
import hashlib
import os
from pathlib import Path
import re
import sys

VERSION = '3.0.3'
# Deterministic default for unit tests. Real publication supplies VIBEZ_RELEASE_SOURCE.
SOURCE = '1111111111111111111111111111111111111111'
SUFFIXES = (
    [f'Linux-x64.{ext}' for ext in ('AppImage', 'deb', 'rpm', 'pkg.tar.zst', 'flatpak')]
    + ['Windows-x64-Setup.exe', 'Windows-x64.msi', 'Windows-x64-Store.msix']
    + [f'macOS-{arch}.{ext}' for arch in ('x64', 'arm64') for ext in ('dmg', 'zip')]
)
REQUIRED = {f'VibeZ-{VERSION}-{suffix}' for suffix in SUFFIXES}

def verify(directory: Path, expected_source: str = SOURCE) -> None:
    if not re.fullmatch(r'[0-9a-f]{40}', expected_source):
        raise ValueError('Invalid expected source commit')
    expected = REQUIRED | {'source-commit.txt'}
    if (directory / 'source-commit.txt').read_text().strip() != expected_source:
        raise ValueError('Release source does not match the tested application')
    records = {}
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  ([^/\\]+)', line)
        if not match:
            raise ValueError('Invalid checksum-manifest entry')
        digest, name = match.groups()
        if name not in expected or name in records:
            raise ValueError(f'Unexpected or repeated checksum entry: {name}')
        records[name] = digest
    if set(records) != expected:
        raise ValueError('Checksum manifest does not cover the exact required file set')
    for name, expected_digest in sorted(records.items()):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing or unsafe release file: {name}')
        if name in REQUIRED and path.stat().st_size < 1024:
            raise ValueError(f'Release file is unexpectedly small: {name}')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected_digest:
            raise ValueError(f'Checksum mismatch: {name}')
        print(f'SHA256_OK: {name}')
    print('PUBLICATION_ASSETS_OK: all twelve installers/archives and source commit verified')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: verify-published-assets.py DIRECTORY')
    expected_source = os.environ.get('VIBEZ_RELEASE_SOURCE', SOURCE)
    try:
        verify(Path(sys.argv[1]), expected_source)
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
