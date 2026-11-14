#!/usr/bin/env python3
"""Stage only the pinned tunnel executable for this package's platform."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request

BASE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = json.loads((BASE / 'packaging/cloudflared-sources.json').read_text())
    item = source['targets'][args.target]
    cache = BASE / '.cache/cloudflared'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / item['asset']
    if not archive.exists():
        request = urllib.request.Request(item['url'], headers={'User-Agent': 'VibeZ-build'})
        with urllib.request.urlopen(request, timeout=90) as response, archive.open('wb') as output:
            shutil.copyfileobj(response, output)
    data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() != item['archive_sha256']:
        raise ValueError('Tunnel download checksum mismatch')
    if item['asset'].endswith('.tgz'):
        with tarfile.open(fileobj=io.BytesIO(data)) as stream:
            files = [member for member in stream if member.isfile() and Path(member.name).name == 'cloudflared']
            if len(files) != 1:
                raise ValueError('Unexpected tunnel archive layout')
            data = stream.extractfile(files[0]).read()
    binary_sha = hashlib.sha256(data).hexdigest()
    if item.get('sha256') and binary_sha != item['sha256']:
        raise ValueError('Tunnel executable checksum mismatch')
    args.output.mkdir(parents=True, exist_ok=True)
    # Only known release executables may be removed, exclusively inside the
    # explicitly selected staging directory. Keep licenses and provenance.
    for known in source['targets'].values():
        candidate=args.output / known['file']
        if known['file'] != item['file'] and (candidate.exists() or candidate.is_symlink()):
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError('Unexpected tunnel staging entry')
            candidate.unlink()
    destination = args.output / item['file']
    if destination.exists() and destination.read_bytes() != data:
        raise ValueError('Refusing to replace a different tunnel executable')
    destination.write_bytes(data)
    destination.chmod(0o755)
    license_source=BASE / 'backend/vendor/LICENSE-cloudflared'
    license_target=args.output / 'LICENSE-cloudflared'
    if license_source.resolve() != license_target.resolve():
        shutil.copy2(license_source, license_target)
    metadata = {'version': source['version'], 'platforms': {args.target: {'file': item['file'], 'sha256': binary_sha}}}
    if args.target == 'linux-x64':
        metadata.update(url=item['url'], sha256=binary_sha)
    (args.output / 'source.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({'target': args.target, 'file': str(destination), 'sha256': binary_sha}))


if __name__ == '__main__':
    main()
