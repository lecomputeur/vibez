#!/usr/bin/env python3
"""Make a Linux AppDir use its matching bundled GIO TLS provider."""
import argparse
import hashlib
import json
from pathlib import Path

MARKER = '# VibeZ AppImage: select the bundled GIO TLS module directory.'
ORIGINAL = 'AppRun.original'
WRAPPER = '''#!/bin/sh
set -eu
# VibeZ AppImage: select the bundled GIO TLS module directory.
APPDIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
export APPDIR
export GIO_MODULE_DIR="$APPDIR/usr/lib/gio/modules"
exec "$APPDIR/AppRun.original" "$@"
'''


def prepare(appdir):
    root = Path(appdir).resolve(strict=True)
    launcher = root / 'AppRun'
    original = root / ORIGINAL
    modules = root / 'usr/lib/gio/modules'
    provider = modules / 'libgiognutls.so'
    cache = modules / 'giomodule.cache'
    if not provider.is_file() or provider.read_bytes()[:4] != b'\x7fELF':
        raise ValueError('A bundled GnuTLS GIO provider is required')
    if not cache.is_file() or not any(line.startswith('libgiognutls.so:') and 'gio-tls-backend' in line for line in cache.read_text().splitlines()):
        raise ValueError('The bundled GIO cache must register its TLS provider')
    if launcher.is_symlink() or not launcher.is_file():
        raise ValueError('Expected a regular AppRun launcher')
    content = launcher.read_bytes()
    if content == WRAPPER.encode():
        if not original.is_file() or original.is_symlink() or original.read_bytes()[:4] != b'\x7fELF':
            raise ValueError('The original AppRun ELF is missing or invalid')
        changed = False
    else:
        if content[:4] != b'\x7fELF' or original.exists() or original.is_symlink():
            raise ValueError('Refusing to overwrite an unknown AppRun layout')
        launcher.rename(original)
        try:
            launcher.write_text(WRAPPER)
            launcher.chmod(0o755)
        except BaseException:
            launcher.unlink(missing_ok=True)
            original.rename(launcher)
            raise
        changed = True
    return {'passed': True, 'changed': changed,
            'original_launcher_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
            'wrapper_sha256': hashlib.sha256(launcher.read_bytes()).hexdigest(),
            'bundled_TLS_provider_sha256': hashlib.sha256(provider.read_bytes()).hexdigest(),
            'GIO_module_path': '$APPDIR/usr/lib/gio/modules',
            'certificate_validation_or_WebKit_sandbox_disabled': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--appdir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.appdir)))


if __name__ == '__main__':
    main()
