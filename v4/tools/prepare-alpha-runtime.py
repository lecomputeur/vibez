#!/usr/bin/env python3
"""Fetch a pinned relocatable Python runtime; never use a tester's Python."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile

BASE = Path(__file__).resolve().parents[1]


def fetch(spec, path):
    if not path.exists():
        request = urllib.request.Request(spec['url'], headers={'User-Agent': 'VibeZ-build'})
        with urllib.request.urlopen(request, timeout=90) as response, path.open('wb') as out:
            shutil.copyfileobj(response, out)
    if hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
        raise ValueError('Runtime checksum mismatch')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = json.loads((BASE / 'packaging/runtime-sources.json').read_text())
    spec = sources['targets'][args.target]
    cache = BASE / '.cache/alpha-runtimes'
    cache.mkdir(parents=True, exist_ok=True)
    archive = fetch(spec, cache / spec['name'])
    if args.output.exists():
        raise ValueError('Runtime output must be new; existing runtimes are preserved')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent, prefix='runtime-extract-') as temp:
        with tarfile.open(archive) as stream:
            stream.extractall(temp, filter='data')
        root = Path(temp) / 'python'
        if not root.is_dir():
            raise ValueError('Unexpected runtime archive layout')
        shutil.move(str(root), args.output)
    cert = sources['certificates']
    wheel = fetch(cert, cache / cert['filename'])
    dest = args.output / 'certificates'
    dest.mkdir(exist_ok=True)
    with zipfile.ZipFile(wheel) as stream:
        (dest / 'cacert.pem').write_bytes(stream.read('certifi/cacert.pem'))
        licenses = [n for n in stream.namelist() if n.endswith('/LICENSE') or n.endswith('/LICENSE.txt')]
        if licenses:
            (dest / 'LICENSE-certifi').write_bytes(stream.read(licenses[0]))
    (args.output / 'vibez-runtime-source.json').write_text(json.dumps({
        'target': args.target, 'runtime': spec, 'certificates': cert,
        'python_version': sources['python_version'],
    }, indent=2) + '\n')
    print(json.dumps({'target': args.target, 'output': str(args.output), 'sha256': spec['sha256']}))


if __name__ == '__main__':
    main()
