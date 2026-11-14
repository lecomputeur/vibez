#!/usr/bin/env python3
"""Local V4 release preparation. Never builds, installs, uploads or publishes."""
from __future__ import annotations
import argparse
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib

VERSION_RE = re.compile(r"4\.0\.0-(alpha|beta)\.([1-9][0-9]*)\Z")
STAGES = {"alpha": 0, "beta": 1}
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 100 * 1024 * 1024
VERSION_FILES = (
    'desktop/package.json', 'desktop/package-lock.json',
    'desktop/src-tauri/Cargo.toml', 'desktop/src-tauri/Cargo.lock',
    'desktop/src-tauri/tauri.conf.json', 'backend/workspace_engine.py',
    'backend/standalone_engine.py', 'backend/web_connector.py',
)
EXPECTED_FORMATS = {
    'linux-x64': ['AppImage', 'deb', 'rpm', 'pkg.tar.zst', 'flatpak'],
    'windows-x64': ['Setup.exe', 'msi'],
    'macos-x64': ['dmg', 'app.tar.gz'],
    'macos-arm64': ['dmg', 'app.tar.gz'],
}
GATES = ['frozen_source', 'native_tests', 'package_tests', 'signatures',
         'macos_notarization', 'all_required_packages', 'maintainer_approval']

class ReleaseError(ValueError):
    pass

def require(ok, message):
    if not ok:
        raise ReleaseError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

def alpha_number(value):
    """Release order key: every Alpha comes before every Beta."""
    require(isinstance(value, str), 'Version must be text')
    m = VERSION_RE.fullmatch(value)
    require(m is not None, 'Only numbered 4.0.0-alpha.N and 4.0.0-beta.N releases are supported')
    return (STAGES[m.group(1)], int(m.group(2)))

def next_versions(value):
    """The releases that may follow: the next number, and Beta 1 after an Alpha."""
    stage, number = VERSION_RE.fullmatch(value).groups()
    allowed = {'4.0.0-%s.%d' % (stage, int(number)+1)}
    if stage == 'alpha': allowed.add('4.0.0-beta.1')
    return allowed

def safe_relative(value):
    require(isinstance(value, str) and value and '\\' not in value, 'Invalid source path')
    p = PurePosixPath(value)
    require(not p.is_absolute() and str(p) == value and all(x not in ('', '.', '..') for x in p.parts),
            'Source paths must be normalized and relative')
    protected = {'.git', 'artifacts', 'node_modules', 'target', '.ssh', '.aws', '.gnupg', '__pycache__'}
    require(not any(x in protected or x.lower().startswith('.env') for x in p.parts), 'Protected source path: '+value)
    require(p.suffix.lower() not in ('.pem', '.p12', '.pfx', '.key'), 'Private key paths are not source')
    require(not any(x in p.name.lower() for x in ('secret', 'credential', 'password', 'passphrase')), 'Secret-like filename is not source')
    return p

def safe_file(root, rel):
    pure = safe_relative(rel)
    at = root
    for component in pure.parts:
        at = at / component
        require(not at.is_symlink(), 'Symlink in source path: '+rel)
    require(at.is_file() and at.stat().st_size <= MAX_FILE, 'Missing or oversized source: '+rel)
    data = at.read_bytes()
    require(b'-----BEGIN PRIVATE KEY-----' not in data and b'-----BEGIN OPENSSH PRIVATE KEY-----' not in data
            and not re.search(rb'-----BEGIN (?:RSA |EC |DSA |PGP |OPENSSH )?PRIVATE KEY(?: BLOCK)?-----', data), 'Private key material is not source')
    return data

def load_json(root, rel):
    return json.loads(safe_file(root, rel).decode('utf-8'))

def package_names(spec):
    version = spec['version']
    names = {}
    for target, formats in EXPECTED_FORMATS.items():
        platform = 'Linux' if target == 'linux-x64' else ('Windows' if target == 'windows-x64' else 'macOS')
        architecture = 'arm64' if target.endswith('arm64') else 'x64'
        names[target] = ['VibeZ-'+version+'-'+platform+'-'+architecture+('-Setup.exe' if ext == 'Setup.exe' else '.'+ext) for ext in formats]
    return names

def validate_release(spec):
    require(spec.get('schema_version') == 1, 'Unsupported release schema')
    current = alpha_number(spec.get('version'))
    published = alpha_number(spec.get('published_version'))
    require(published <= current, 'Published version cannot be ahead of local source')
    require(spec.get('installed_version') is None or alpha_number(spec['installed_version']) <= current,
            'Installed version cannot be ahead of local source')
    require(spec.get('stage') in ('development', 'local-tested', 'release-candidate', 'published'), 'Unknown release stage')
    require(spec.get('stage') != 'published' or spec['published_version'] == spec['version'], 'Published stage and version differ')
    require(spec.get('channel') == 'v4-alpha' and spec.get('stable_version') == '3.0.9', 'Stable and Alpha channels must remain separate')
    require(spec.get('formats') == EXPECTED_FORMATS, 'Required package formats differ; MSIX is excluded')
    require(spec.get('gates') == GATES, 'Release gates were changed')
    require(spec.get('required_targets') == list(EXPECTED_FORMATS), 'Required build targets differ')
    require(spec.get('source_revision') == 'HEAD', 'Source revision must resolve from the clean local Git HEAD')
    require(isinstance(spec.get('changes'), list) and all(isinstance(x, str) and 0 < len(x) <= 1000 for x in spec['changes']), 'Invalid release change list')
    require(isinstance(spec.get('related_issues'), list) and all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in spec['related_issues']), 'Invalid related issue list')
    require(spec.get('source_private') is True and spec.get('replace_published_assets') is False,
            'Private source and published-package policy changed')
    return spec

def source_paths(root):
    spec = load_json(root, 'management/source-files.json')
    require(spec.get('schema_version') == 1, 'Unsupported source allowlist schema')
    names = spec.get('files')
    require(isinstance(names, list) and 0 < len(names) <= 2000 and names == sorted(set(names)), 'Source allowlist must be sorted and unique')
    for name in names:
        safe_relative(name)
    require(set(VERSION_FILES) <= set(names), 'Version files missing from source allowlist')
    return names

def read_versions(root):
    package = load_json(root, VERSION_FILES[0]); lock = load_json(root, VERSION_FILES[1])
    cargo = tomllib.loads(safe_file(root, VERSION_FILES[2]).decode('utf-8'))
    cargo_lock = tomllib.loads(safe_file(root, VERSION_FILES[3]).decode('utf-8'))
    app = load_json(root, VERSION_FILES[4])
    require(package.get('name') == 'vibez4-alpha' and cargo['package']['name'] == 'vibez4-alpha', 'Unexpected app package identity')
    require(lock.get('name') == 'vibez4-alpha' and lock['packages']['']['name'] == 'vibez4-alpha', 'Unexpected npm lock identity')
    require(app.get('identifier') == 'nl.lecomputeur.vibez4.alpha' and app.get('mainBinaryName') == 'vibez4-alpha', 'V4 must retain its separate application identity')
    own_lock = [x for x in cargo_lock['package'] if x['name'] == 'vibez4-alpha']
    require(len(own_lock) == 1, 'Cargo lock must contain exactly one V4 package')
    values = {VERSION_FILES[0]: [package['version']], VERSION_FILES[1]: [lock['version'], lock['packages']['']['version']],
              VERSION_FILES[2]: [cargo['package']['version']], VERSION_FILES[3]: [own_lock[0]['version']], VERSION_FILES[4]: [app['version']]}
    for name in VERSION_FILES[5:]:
        parsed = ast.parse(safe_file(root, name).decode('utf-8'))
        values[name] = [ast.literal_eval(x.value) for x in parsed.body if isinstance(x, ast.Assign)
                        and any(isinstance(y, ast.Name) and y.id == 'VERSION' for y in x.targets)]
        require(len(values[name]) == 1, 'Expected one service VERSION in '+name)
    return values

def check(root):
    spec = validate_release(load_json(root, 'management/release.json'))
    paths = source_paths(root)
    versions = read_versions(root)
    require(all(value == spec['version'] for values in versions.values() for value in values), 'Source version differs from management/release.json')
    total = 0
    for name in paths:
        total += len(safe_file(root, name))
    require(total <= MAX_TOTAL, 'Source allowlist exceeds private snapshot limit')
    return {'passed': True, 'version': spec['version'], 'installed_version': spec['installed_version'],
            'published_version': spec['published_version'], 'stable_version': spec['stable_version'],
            'stage': spec['stage'], 'version_fields_checked': sum(map(len, versions.values())),
            'source_files_checked': len(paths), 'source_bytes': total, 'formats': spec['formats'],
            'package_names': package_names(spec), 'required_targets': spec['required_targets'],
            'build_or_publication_performed': False}

def git(root, *args):
    r = subprocess.run(['git', '-C', str(root), *args], capture_output=True)
    require(r.returncode == 0, 'Git check failed: '+r.stderr.decode('utf-8', 'replace').strip())
    return r.stdout

def checked_git(root):
    require(git(root, 'rev-parse', '--show-toplevel').decode().strip() == str(root), 'Run from the private source repository root')
    commit = git(root, 'rev-parse', 'HEAD').decode().strip()
    require(re.fullmatch('[0-9a-f]{40,64}', commit) is not None, 'Unexpected Git commit')
    require(not git(root, 'status', '--porcelain', '--untracked-files=no'), 'Commit tracked changes before preparing a release')
    tracked = set(git(root, 'ls-files', '-z').decode('utf-8').rstrip('\0').split('\0'))
    require(set(source_paths(root)) <= tracked, 'Approved source files are not all tracked by Git')
    require({'management/release.json', 'management/source-files.json'} <= tracked, 'Commit release metadata before preparing a release')
    return commit

def new_output(path, root):
    path = Path(os.path.abspath(path))
    for parent in [path, *path.parents]:
        require(not parent.is_symlink(), 'Output contains a symlink')
    require(path != root and root not in path.parents, 'Prepare output outside the source tree')
    require(not path.exists(), 'Output already exists; previous plans and snapshots are never overwritten')
    require(path.parent.is_dir(), 'Output parent must already exist')
    return path

def atomic_directory(output, producer):
    # Exclusive directory creation prevents replacing even an empty prior output.
    # The plan/snapshot manifest is written last and marks successful completion.
    output.mkdir(mode=0o700)
    try:
        producer(output)
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise

def json_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        # A hard link publishes the complete JSON atomically without clobbering.
        os.link(temporary, path)
    finally:
        os.unlink(temporary)

def draft_release_notes(spec):
    """Prepare reviewable text only; required packages are not availability claims."""
    validate_release(spec)
    version = spec['version']
    lines = ['# DRAFT — VibeZ V4 Alpha '+version.rsplit('.', 1)[-1], '',
             '**NOT PUBLISHED — release preparation only.**', '',
             'Version: `'+version+'`.', '',
             'This draft does not announce downloads or claim native platform tests have passed. '
             'Publish only after the required build, test, signing and approval gates are verified.', '',
             '## Changes prepared for this version', '']
    if spec['changes']:
        lines.extend('- '+change for change in spec['changes'])
    else:
        lines.append('No changes have been described yet. Complete the release description before publication.')
    lines.extend(['', '## Related reports', ''])
    if spec['related_issues']:
        lines.extend('- [Issue #'+str(issue)+'](https://github.com/lecomputeur/vibez/issues/'+str(issue)+')'
                     for issue in spec['related_issues'])
    else:
        lines.append('No issue links have been recorded for this draft.')
    lines.extend(['', '## Required package matrix — not download availability', '',
                  '| Target | Expected files |', '|---|---|'])
    for target, names in package_names(spec).items():
        lines.append('| '+target+' | '+' · '.join('`'+name+'`' for name in names)+' |')
    lines.extend(['', 'V4 Alpha installs separately from stable VibeZ '+spec['stable_version']+
                  ' and uses its own application identity and profile. VibeZ '+spec['stable_version']+
                  ' is not replaced by this Alpha.', '',
                  'MSIX is excluded from this V4 Alpha package matrix. The V4 Alpha update channel remains separate from the stable channel.', ''])
    return '\n'.join(lines)

def text_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(value);stream.flush();os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)

def replace_own_version(text, filename, current, next_version):
    if filename.endswith('.json'):
        value = json.loads(text)
        require(value['version'] == current, 'Changed version during plan')
        value['version'] = next_version
        if filename == 'desktop/package-lock.json':
            require(value['packages']['']['version'] == current, 'Changed npm root during plan')
            value['packages']['']['version'] = next_version
        return json.dumps(value, ensure_ascii=True, indent=2)+'\n'
    if filename == 'desktop/src-tauri/Cargo.toml':
        pattern = r'(?ms)(\A\[package\]\n.*?^version\s*=\s*")'+re.escape(current)+r'("\s*$)'
    elif filename == 'desktop/src-tauri/Cargo.lock':
        pattern = r'(?m)(^name = "vibez4-alpha"\nversion = ")'+re.escape(current)+r'("$)'
    else:
        pattern = r'(?m)(^VERSION\s*=\s*[\'\"])'+re.escape(current)+r'([\'\"]\s*$)'
    result, count = re.subn(pattern, lambda m: m[1]+next_version+m[2], text)
    require(count == 1, 'Expected one version field in '+filename)
    return result

def plan(root, next_version, output):
    checked = check(root); spec = load_json(root, 'management/release.json')
    alpha_number(spec['version']); proposed = alpha_number(next_version)
    require(next_version in next_versions(spec['version']) and proposed > alpha_number(spec['published_version']), 'Next release must be the next Alpha or Beta number, never a published version')
    commit = checked_git(root)
    output = new_output(output, root)
    changed = {}
    for name in VERSION_FILES:
        text = safe_file(root, name).decode('utf-8')
        changed[name] = replace_own_version(text, name, spec['version'], next_version).encode('utf-8')
    proposed_spec = dict(spec, version=next_version, stage='development', changes=[], related_issues=[])
    records = [{'path': name, 'before_sha256': digest(safe_file(root, name)), 'after_sha256': digest(data)} for name, data in sorted(changed.items())]
    result = {'version': next_version, 'base_version': checked['version'], 'source_commit': commit,
              'source_private': True, 'applied': False, 'built': False, 'published': False,
              'changed_files': records, 'required_gates': GATES, 'formats': EXPECTED_FORMATS,
              'required_targets': list(EXPECTED_FORMATS), 'package_names': package_names(proposed_spec),
              'instructions': 'Review these files, then copy them into the private source checkout and commit. Build only from a new frozen snapshot. Do not upload this directory to the public repository.'}
    def producer(temp):
        for name, data in changed.items():
            p=temp/'files'/name;p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(data);p.chmod(0o600)
        json_write(temp/'files/management/release.json', proposed_spec)
        json_write(temp/'plan.json', result)
    atomic_directory(output, producer)
    return result

def snapshot(root, output):
    checked = check(root); commit = checked_git(root)
    output = new_output(output, root)
    entries=[];content={}
    for name in source_paths(root):
        data=git(root, 'show', commit+':'+name)
        require(data == safe_file(root, name), 'Working source differs from its Git commit: '+name)
        content[name]=data;entries.append({'path':name,'sha256':digest(data),'size':len(data)})
    result={'version':checked['version'],'source_commit':commit,'source_private':True,
            'files':entries,'source_manifest_sha256':digest(canonical(entries)),
            'built':False,'published':False,'required_gates':GATES,'formats':EXPECTED_FORMATS,
            'required_targets':list(EXPECTED_FORMATS),'package_names':package_names(load_json(root,'management/release.json')),
            'release':load_json(root,'management/release.json')}
    def producer(temp):
        archive=temp/'private-source.tar.gz'
        with archive.open('xb') as raw:
            with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as compressed:
                with tarfile.open(fileobj=compressed,mode='w') as stream:
                    for name,data in content.items():
                        info=tarfile.TarInfo(name);info.size=len(data);info.mtime=0
                        info.mode=0o755 if os.access(root/name,os.X_OK) else 0o644
                        stream.addfile(info,io.BytesIO(data))
        archive.chmod(0o600)
        result['archive_sha256']=digest(archive.read_bytes())
        text_write(temp/'RELEASE-NOTES.md',draft_release_notes(result['release']))
        json_write(temp/'snapshot.json',result)
    atomic_directory(output,producer)
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('check');sub.add_parser('status')
    future=sub.add_parser('plan');future.add_argument('--next-version',required=True);future.add_argument('--output',type=Path,required=True)
    freeze=sub.add_parser('snapshot');freeze.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        root=args.root.resolve(strict=True)
        if args.command in ('check','status'):result=check(root)
        elif args.command=='plan':result=plan(root,args.next_version,args.output)
        else:result=snapshot(root,args.output)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ReleaseError,OSError,ValueError,KeyError,TypeError,SyntaxError) as error:
        parser.exit(1,'Release preparation stopped: '+str(error)+'\n')

if __name__=='__main__':
    raise SystemExit(main())
