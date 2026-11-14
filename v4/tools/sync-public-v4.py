#!/usr/bin/env python3
"""Keep this release working tree and the public v4/ folder in step.

The V4 source is public in lecomputeur/vibez under v4/; contributions arrive
there as pull requests. Releases are still built from this working tree, which
has no Git of its own. This tool compares three versions of every file:

  base    v4/ at the public commit of the last sync (recorded locally)
  public  v4/ on the public main branch now
  local   this working tree

  status   what would be pulled, what is only local, and any conflicts
  check    like status, but exits 1 when public changes are not pulled yet
           or a conflict exists (release-alpha.py bump runs this)
  pull     copy public changes into this tree; refuses everything when one
           file changed on both sides
  push     put local changes on a new branch of the public clone and commit
           them; --pr also pushes the branch and opens a pull request

The public clone lives in _claude-build/v4-public and the last synced commit
in _claude-build/public-sync.json; neither is part of the source. Nothing is
pushed or merged without `push --pr`, and merging stays a manual step.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
BUILD = BASE / '_claude-build'
CLONE = BUILD / 'v4-public'
STATE = BUILD / 'public-sync.json'
REPO = 'lecomputeur/vibez'
PREFIX = 'v4/'
AUTHOR = ['-c', 'user.name=lecomputeur', '-c', 'user.email=121440176+lecomputeur@users.noreply.github.com']
# Files the public folder carries besides the build and maintainer lists.
EXTRAS = ['.gitattributes', '.gitignore', 'README.md', 'management/README.md', 'management/release.json',
          'management/source-files.json', 'management/maintainer-files.json',
          'management/manage.py', 'management/test_manage.py']


class SyncError(Exception):
    pass


def git(*args, cwd=None, data=False):
    result = subprocess.run(['git', *args], cwd=cwd or CLONE, capture_output=True)
    if result.returncode:
        raise SyncError('git %s failed: %s' % (args[0], result.stderr.decode(errors='replace').strip()[:300]))
    return result.stdout if data else result.stdout.decode().strip()


def blob_id(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def local_paths():
    names = set(EXTRAS)
    names.update(json.loads((BASE / 'management/source-files.json').read_text())['files'])
    for entry in json.loads((BASE / 'management/maintainer-files.json').read_text())['files']:
        names.add(entry if isinstance(entry, str) else entry['path'])
    return names


def tree(commit):
    """{path inside v4/: blob id} of the public folder at a commit."""
    listing = git('ls-tree', '-r', '-z', commit, '--', PREFIX, data=True).decode()
    result = {}
    for line in filter(None, listing.split('\0')):
        meta, path = line.split('\t', 1)
        result[path[len(PREFIX):]] = meta.split()[2]
    return result


def local_tree(names):
    result = {}
    for name in names:
        path = BASE / name
        if path.is_file():
            result[name] = blob_id(path.read_bytes())
    return result


def safe_name(name):
    parts = Path(name).parts
    if not parts or Path(name).is_absolute() or '..' in parts or parts[0] in ('_claude-build', 'artifacts', '.git'):
        raise SyncError('Refusing an unexpected path: %r' % name)
    return name


def prepare_clone():
    if not (CLONE / '.git').is_dir():
        BUILD.mkdir(exist_ok=True)
        subprocess.run(['gh', 'repo', 'clone', REPO, str(CLONE), '--', '--quiet'], check=True)
    git('fetch', '--quiet', 'origin', 'main')
    return git('rev-parse', 'origin/main')


def load_base():
    try:
        return json.loads(STATE.read_text())['commit']
    except (OSError, ValueError, KeyError):
        raise SyncError('No sync baseline yet. Run: python3 tools/sync-public-v4.py status --baseline <public commit>')


def save_base(commit):
    STATE.write_text(json.dumps({'repository': REPO, 'path': PREFIX, 'commit': commit}, indent=2) + '\n')


def compare(base_commit, public_commit):
    base, public = tree(base_commit), tree(public_commit)
    names = set(base) | set(public) | local_paths()
    local = local_tree(names)
    plan = {'pull': [], 'local': [], 'conflict': [], 'same': 0}
    for name in sorted(names):
        b, r, l = base.get(name), public.get(name), local.get(name)
        if r == l:
            plan['same'] += 1
        elif r == b:
            plan['local'].append(name)
        elif l == b:
            plan['pull'].append(name)
        else:
            plan['conflict'].append(name)
    return plan


def report(plan, base_commit, public_commit):
    print('* base %s, public main %s, %d files equal' % (base_commit[:7], public_commit[:7], plan['same']))
    for key, title in (('pull', 'changed on public main (pull)'), ('local', 'changed only here (push)'),
                       ('conflict', 'CONFLICT: changed on both sides')):
        if plan[key]:
            print('* %s: %d' % (title, len(plan[key])))
            for name in plan[key][:40]:
                print('    ' + name)


def pull(plan, public_commit):
    if plan['conflict']:
        raise SyncError('Nothing copied: %d file(s) changed both here and on public main. '
                        'Bring the local change into a pull request first, or resolve by hand.' % len(plan['conflict']))
    public = tree(public_commit)
    for name in plan['pull']:
        target = BASE / safe_name(name)
        if name in public:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git('show', '%s:%s%s' % (public_commit, PREFIX, name), data=True))
        elif target.is_file():
            target.unlink()
    save_base(public_commit)
    print('* pulled %d file(s); baseline is now %s' % (len(plan['pull']), public_commit[:7]))


def push(plan, public_commit, branch, message, open_pr):
    if plan['conflict']:
        raise SyncError('Not pushing: %d file(s) also changed on public main; pull first.' % len(plan['conflict']))
    if not plan['local']:
        print('* no local changes to push')
        return
    if git('status', '--porcelain'):
        raise SyncError('The public clone has uncommitted changes: %s' % CLONE)
    git('checkout', '--quiet', '-B', branch, public_commit)
    for name in plan['local']:
        source, target = BASE / safe_name(name), CLONE / PREFIX / name
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            git('add', '-f', '--', PREFIX + name)
        elif target.is_file():
            git('rm', '--quiet', '--', PREFIX + name)
    git(*AUTHOR, 'commit', '--quiet', '-m', message)
    print('* committed %d file(s) on %s in %s' % (len(plan['local']), branch, CLONE))
    if open_pr:
        git('push', '--quiet', '-u', 'origin', branch)
        subprocess.run(['gh', 'pr', 'create', '--repo', REPO, '--base', 'main', '--head', branch,
                        '--title', message.splitlines()[0], '--body', 'Changes from the V4 release working tree.'],
                       cwd=CLONE, check=True)
    else:
        print('* not pushed; rerun with --pr to push the branch and open a pull request')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('step', choices=['status', 'check', 'pull', 'push'])
    parser.add_argument('--baseline', help='record this public commit as the last sync (first use only)')
    parser.add_argument('--branch', default='v4/sync', help='push: branch name in the public clone')
    parser.add_argument('--message', default='Update the V4 source from the release working tree')
    parser.add_argument('--pr', action='store_true', help='push: push the branch and open a pull request')
    args = parser.parse_args(argv)
    try:
        public_commit = prepare_clone()
        if args.baseline:
            save_base(git('rev-parse', '%s^{commit}' % args.baseline))
        base_commit = load_base()
        plan = compare(base_commit, public_commit)
        report(plan, base_commit, public_commit)
        if args.step == 'check' and (plan['pull'] or plan['conflict']):
            print('STOP: public main has V4 changes that are not in this tree; run tools/sync-public-v4.py pull')
            return 1
        if args.step == 'pull':
            pull(plan, public_commit)
        elif args.step == 'push':
            push(plan, public_commit, args.branch, args.message, args.pr)
    except (SyncError, subprocess.CalledProcessError) as error:
        print('STOP: %s' % error)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
