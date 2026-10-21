#!/usr/bin/env python3
"""Verify the vendored package against the checksum-pinned upstream archive."""
import hashlib
import io
from pathlib import Path
import tarfile
import urllib.request

SHA256 = 'a819957a01b3119af85e638a38d242af76dbc87d130dca67bfd0441072e21ff0'
ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / 'desktop/src-tauri/vendor/wry'
ALLOWED_CHANGED = {'src/lib.rs', 'src/webkitgtk/mod.rs'}
ALLOWED_ADDED = {'.cargo-ok', 'README.patch'}

def verify():
    with urllib.request.urlopen('https://static.crates.io/crates/wry/wry-0.57.0.crate', timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('Upstream Wry archive checksum mismatch')
    upstream = set()
    changed = set()
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            relative = Path(member.name).relative_to('wry-0.57.0')
            if '..' in relative.parts:
                raise ValueError('Invalid upstream archive path')
            name = relative.as_posix()
            upstream.add(name)
            local = VENDOR / relative
            if not local.is_file():
                raise ValueError(f'Missing vendored upstream file: {name}')
            if local.read_bytes() != archive.extractfile(member).read():
                changed.add(name)
    actual = {p.relative_to(VENDOR).as_posix() for p in VENDOR.rglob('*') if p.is_file()}
    if changed != ALLOWED_CHANGED or actual - upstream != ALLOWED_ADDED:
        raise ValueError(f'Unexpected vendored modifications: changed={changed}, added={actual-upstream}')
    print('WRY_SUPPLY_CHAIN_OK: checksum-pinned 0.57.0 archive; exactly two documented hook changes; original licenses retained')

if __name__ == '__main__':
    verify()
