"""Local, user-initiated file copies into an exact web-project binding.

This module is never exposed as an MCP tool. Native code supplies the source
paths only after an OS drop or file choice; the renderer cannot choose paths.
"""
import hashlib
import json
import os
from pathlib import PurePath
import secrets
import stat
import ctypes
import errno
import threading
import time
import unicodedata

# Load the bundled OS facade explicitly under isolated Python (-I).
import importlib.util as _cap_importlib
import sys as _cap_sys
from pathlib import Path as _CapPath
if '_vibez_capfs' not in _cap_sys.modules:
    _cap_spec = _cap_importlib.spec_from_file_location('_vibez_capfs', _CapPath(__file__).with_name('capfs.py'))
    _cap_module = _cap_importlib.module_from_spec(_cap_spec)
    _cap_sys.modules['_vibez_capfs'] = _cap_module
    try:
        _cap_spec.loader.exec_module(_cap_module)
    except BaseException:
        _cap_sys.modules.pop('_vibez_capfs', None)
        raise
os = _cap_sys.modules['_vibez_capfs']

MAX_FILES = 50
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_TOTAL_BYTES = 500 * 1024 * 1024
CHUNK = 1024 * 1024
MAX_TREE_ENTRIES = 10000
MAX_TREE_DEPTH = 32
PLAN_SECONDS = 300


class ImportFailure(ValueError):
    """A safe message plus names of any earlier completed copies in the batch."""
    def __init__(self, message, names):
        super().__init__(message)
        self.copied = list(names)
        self.count = len(self.copied)


def binding(connector, key=None):
    """An opaque, non-authorizing revision; relinking invalidates native grants."""
    with connector.lock:
        key = key or (connector.active or {}).get('id')
        project = connector.projects.get(key)
        if not project:
            return ''
        folder = connector.import_folder(key) if hasattr(connector, 'import_folder') else project['folder']
        raw = json.dumps([key, folder, project['token']],
                         ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        return hashlib.sha256(raw).hexdigest()


def _directory(path):
    """Open each absolute component using retained no-follow handles."""
    return os.open_directory(path)



def create_directory(folder, name, *, expected_fd=None):
    """Create one visible child using a directory handle, never a path join."""
    if (not isinstance(name, str) or not name or name != name.strip() or name.startswith('.') or
            '/' in name or '\\' in name or len(name.encode('utf-8', errors='surrogatepass')) > 255 or
            any(unicodedata.category(c).startswith('C') or c in '\u2028\u2029' for c in name)):
        raise ValueError('Choose a visible subfolder name without slashes or special characters')
    root = _directory(folder)
    try:
        current = os.stat(folder, follow_symlinks=False)
        anchored = os.fstat(root)
        if (current.st_dev, current.st_ino) != (anchored.st_dev, anchored.st_ino):
            raise ValueError('The workspace folder changed in the meantime; choose the subfolder again')
        if expected_fd is not None:
            previous = os.fstat(expected_fd)
            if (previous.st_dev, previous.st_ino) != (anchored.st_dev, anchored.st_ino):
                raise ValueError('The workspace folder was replaced in the meantime; link the folder again')
        try:
            os.mkdir(name, mode=0o755, dir_fd=root)
        except FileExistsError:
            raise ValueError('A file or folder with this name already exists') from None
        os.fsync(root)
        return {'name': name, 'created': True}
    finally:
        os.close(root)


def _source(path):
    parent, name = os.split_absolute(path)
    parent_fd = _directory(parent)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent_fd)
    finally:
        os.close(parent_fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise ValueError('Drag only regular files, not folders or links')
    if info.st_size > MAX_FILE_BYTES:
        os.close(fd)
        raise ValueError('A file may be at most 100 MB')
    return fd, name, info


def _current(connector, key, expected):
    if (connector.active or {}).get('id') != key or not expected or binding(connector, key) != expected:
        raise ValueError('The project folder has changed. Drag the files to the right project again.')
    return connector.import_folder(key) if hasattr(connector, 'import_folder') else connector.projects[key]['folder']


def _candidate(name, number, max_bytes=255):
    if number == 1:
        return name
    suffix = PurePath(name).suffix
    stem = name[:-len(suffix)] if suffix else name
    extra = f' ({number})'
    while stem and len((stem + extra + suffix).encode('utf-8')) > max_bytes:
        stem = stem[:-1]
    while suffix and len((stem + extra + suffix).encode('utf-8')) > max_bytes:
        suffix = suffix[:-1]
    return stem + extra + suffix


def listing(connector, key=None):
    """Bounded, read-only top-level file names for the local project panel."""
    with connector.lock:
        key = key or (connector.active or {}).get('id')
        project = connector.projects.get(key)
        if not project:
            return []
        try:
            fd = _directory(connector.import_folder(key) if hasattr(connector, 'import_folder') else project['folder'])
            try:
                values = []
                with os.scandir(fd) as entries:
                    for entry in entries:
                        if len(values) >= 100:
                            break
                        if entry.name.startswith(('.vibez-import-', '.vibez-backup-')):
                            continue
                        info = entry.stat(follow_symlinks=False)
                        if stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode):
                            values.append({'name': entry.name, **({'kind': 'directory'} if stat.S_ISDIR(info.st_mode) else {})})
                return sorted(values, key=lambda item: item['name'].casefold())
            finally:
                os.close(fd)
        except (OSError, ValueError):
            return []


def copy_files(connector, key, expected_binding, sources):
    """Copy binary files without moving sources, following links or overwriting.

    The project lock holds the chosen destination binding for the whole batch.
    Each completed file becomes visible through an atomic no-clobber rename.
    This also works on selected document-portal directories without hard links.
    """
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_FILES:
        raise ValueError('Choose at most 50 files at a time')
    opened = []
    root_fd = None
    temporary = None
    copied = []
    try:
        with connector.lock:
            folder = _current(connector, key, expected_binding)
            root_fd = _directory(folder)
            root_info = os.fstat(root_fd)
            for path in sources:
                opened.append(_source(path))
            if sum(info.st_size for _, _, info in opened) > MAX_TOTAL_BYTES:
                raise ValueError('Choose at most 500 MB of files at a time')
            for source_fd, name, source_info in opened:
                _current(connector, key, expected_binding)
                temporary_name = '.vibez-import-' + secrets.token_hex(16)
                target_fd = os.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                    stat.S_IMODE(source_info.st_mode) & 0o777 or 0o600,
                                    dir_fd=root_fd)
                temporary = temporary_name
                size = 0
                try:
                    while True:
                        content = os.read(source_fd, CHUNK)
                        if not content:
                            break
                        size += len(content)
                        if size > MAX_FILE_BYTES or size > source_info.st_size:
                            raise ValueError('The source file changed while copying')
                        remaining = memoryview(content)
                        while remaining:
                            written = os.write(target_fd, remaining)
                            remaining = remaining[written:]
                    if size != source_info.st_size:
                        raise ValueError('The source file changed while copying')
                    after = os.fstat(source_fd)
                    if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (source_info.st_size, source_info.st_mtime_ns, source_info.st_ctime_ns):
                        raise ValueError('The source file changed while copying')
                    os.fsync(target_fd)
                finally:
                    os.close(target_fd)
                current_root = _directory(folder)
                try:
                    info = os.fstat(current_root)
                    if (info.st_dev, info.st_ino) != (root_info.st_dev, root_info.st_ino):
                        raise ValueError('The project folder changed while copying')
                finally:
                    os.close(current_root)
                for number in range(1, 10001):
                    final_name = _candidate(name, number, os.fpathconf(root_fd, 'PC_NAME_MAX'))
                    try:
                        _rename_at(root_fd, temporary, final_name, 1)
                        break
                    except FileExistsError:
                        continue
                else:
                    raise ValueError('Too many files with this name already exist')
                temporary = None
                copied.append(final_name)
                connector.record(key, 'import_file', final_name)
            os.fsync(root_fd)
            return {'project_id': key, 'binding': expected_binding, 'names': copied, 'count': len(copied)}
    except (OSError, ValueError) as exc:
        message = ('Copying failed. Check that the folder and files are available.'
                   if isinstance(exc, OSError) else str(exc))
        raise ImportFailure(message, copied) from exc
    finally:
        if temporary is not None and root_fd is not None:
            os.unlink(temporary, dir_fd=root_fd)
        if root_fd is not None:
            os.close(root_fd)
        for fd, _, _ in opened:
            os.close(fd)


class _Changed(ValueError):
    def __init__(self, message='The source or destination changed while copying. Choose again.'):
        super().__init__(message)


def _kind(info):
    if stat.S_ISREG(info.st_mode): return 'file'
    if stat.S_ISDIR(info.st_mode): return 'directory'
    if stat.S_ISLNK(info.st_mode): return 'symlink'
    return 'other'


def _meta(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _scan_at(parent, name, *, source=False):
    """A no-follow tree fingerprint. No file text is retained in an import plan."""
    tree = {'kind': '', 'entries': {}, 'hashes': {}, 'bytes': 0, 'safe': True}
    def visit(parent_fd, child, relative, depth):
        if depth > MAX_TREE_DEPTH or len(tree['entries']) >= MAX_TREE_ENTRIES:
            raise ValueError('The folder contains too many files or folder levels')
        info = os.stat(child, dir_fd=parent_fd, follow_symlinks=False)
        kind = _kind(info)
        if not relative: tree['kind'] = kind
        tree['entries'][relative] = _meta(info)
        if kind not in ('file', 'directory'):
            tree['safe'] = False
            if source: raise ValueError('Copy only regular files and folders, not symbolic links or devices')
            return
        if kind == 'file':
            tree['bytes'] += info.st_size
            if info.st_size > MAX_FILE_BYTES:
                raise ValueError('A file may be at most 100 MB')
            if tree['bytes'] > MAX_TOTAL_BYTES:
                raise ValueError('Choose at most 500 MB of files at a time')
            fd = os.open(child, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
            try:
                if _meta(os.fstat(fd)) != _meta(info): raise _Changed()
                digest, size = hashlib.sha256(), 0
                while True:
                    chunk = os.read(fd, CHUNK)
                    if not chunk: break
                    size += len(chunk)
                    if size > info.st_size: raise _Changed()
                    digest.update(chunk)
                if size != info.st_size or _meta(os.fstat(fd)) != _meta(info): raise _Changed()
                tree['hashes'][relative] = digest.hexdigest()
            finally: os.close(fd)
            return
        fd = os.open(child, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            if _meta(os.fstat(fd)) != _meta(info): raise _Changed()
            with os.scandir(fd) as scan:
                children = sorted(entry.name for entry in scan)
            for entry in children:
                if any(ord(c) < 32 for c in entry): raise ValueError('Invalid file name')
                visit(fd, entry, relative + '/' + entry if relative else entry, depth + 1)
            if _meta(os.fstat(fd)) != _meta(info): raise _Changed()
        finally:
            os.close(fd)
    visit(parent, name, '', 0)
    return tree


def _source_tree(path):
    parent, name = os.split_absolute(path)
    fd = _directory(parent)
    try: return name, _scan_at(fd, name, source=True)
    finally: os.close(fd)


def _target_tree(root, name):
    try:
        info = os.stat(name, dir_fd=root, follow_symlinks=False)
    except FileNotFoundError:
        return None
    try: return _scan_at(root, name)
    except (OSError, ValueError):
        # A very large/special destination is still a conflict, but cannot be replaced.
        return {'kind': _kind(info), 'entries': {'': _meta(info)}, 'hashes': {}, 'bytes': 0,
                'safe': False, 'opaque': True}


def _same_tree(first, second, *, renamed=False):
    if first is None or second is None: return first is second
    if first['kind'] != second['kind'] or first.get('opaque') != second.get('opaque'): return False
    if first.get('hashes') != second.get('hashes'): return False
    if first['entries'].keys() != second['entries'].keys(): return False
    for name, info in first['entries'].items():
        other = second['entries'][name]
        # A rename updates the root ctime, but never an entry's content/mtime/inode.
        if info != other and not (renamed and name == '' and info[:-1] == other[:-1]):
            return False
    return True


def _rename_at(root, source, target, flag):
    """Linux atomic no-replace/exchange; never fall back to a clobbering rename."""
    if os.name == 'nt':
        if flag != 1:
            raise ValueError('Safe replace is not available on Windows yet. Choose Keep both or Skip.')
        return os.rename_noreplace(root, source, target)
    if flag == 1:
        # Shared no-replace publishing, including file systems without the native flag.
        return os.rename_noreplace(root, source, target)
    libc = ctypes.CDLL(None, use_errno=True)
    import sys
    darwin = sys.platform == 'darwin'
    rename = getattr(libc, 'renameatx_np' if darwin else 'renameat2', None)
    if rename is None: raise ValueError('Safe replace is not available on this system. Choose Keep both.')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    native_flag = ({1: 4, 2: 2}.get(flag) if darwin else flag)
    if native_flag is None:
        raise ValueError('Invalid safe replace operation')
    if rename(root, os.fsencode(source), root, os.fsencode(target), native_flag) != 0:
        code = ctypes.get_errno()
        if code in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            raise ValueError('Safe replace is not available on this system. Choose Keep both.')
        raise OSError(code, os.strerror(code))


def _remove_tree_at(parent, name):
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if stat.S_ISDIR(info.st_mode):
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            if os.fstat(fd).st_ino != info.st_ino: raise _Changed()
            os.fchmod(fd, stat.S_IMODE(info.st_mode) | 0o700)
            with os.scandir(fd) as entries: children = [entry.name for entry in entries]
            for child in children: _remove_tree_at(fd, child)
        finally: os.close(fd)
        os.rmdir(name, dir_fd=parent)
    else:
        os.unlink(name, dir_fd=parent)


def _stage_tree(path, tree, root):
    """Copy an entire verified tree into one hidden same-filesystem staging entry."""
    parent, name = os.split_absolute(path)
    source_parent = _directory(parent)
    temporary = '.vibez-import-' + secrets.token_hex(16)
    created = False
    def copy(src_parent, src_name, dst_parent, dst_name, relative):
        nonlocal created
        info = os.stat(src_name, dir_fd=src_parent, follow_symlinks=False)
        expected = tree['entries'].get(relative)
        if _meta(info) != expected: raise _Changed()
        if stat.S_ISDIR(info.st_mode):
            src = os.open(src_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=src_parent)
            dst = None
            try:
                if _meta(os.fstat(src)) != expected: raise _Changed()
                os.mkdir(dst_name, 0o700, dir_fd=dst_parent)
                if not relative: created = True
                dst = os.open(dst_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dst_parent)
                with os.scandir(src) as entries: children = sorted(entry.name for entry in entries)
                for child in children:
                    rel = relative + '/' + child if relative else child
                    copy(src, child, dst, child, rel)
                if _meta(os.fstat(src)) != expected: raise _Changed()
                os.fchmod(dst, stat.S_IMODE(info.st_mode) & 0o777 or 0o700)
                os.fsync(dst)
            finally:
                os.close(src)
                if dst is not None: os.close(dst)
        elif stat.S_ISREG(info.st_mode):
            src = os.open(src_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=src_parent)
            dst = None
            try:
                if _meta(os.fstat(src)) != expected: raise _Changed()
                dst = os.open(dst_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                              stat.S_IMODE(info.st_mode) & 0o777 or 0o600, dir_fd=dst_parent)
                if not relative: created = True
                copied, digest = 0, hashlib.sha256()
                while True:
                    chunk = os.read(src, CHUNK)
                    if not chunk: break
                    copied += len(chunk)
                    if copied > info.st_size: raise _Changed()
                    digest.update(chunk)
                    remaining = memoryview(chunk)
                    while remaining:
                        written = os.write(dst, remaining)
                        remaining = remaining[written:]
                if copied != info.st_size or _meta(os.fstat(src)) != expected or digest.hexdigest() != tree['hashes'][relative]: raise _Changed()
                os.fsync(dst)
            finally:
                os.close(src)
                if dst is not None: os.close(dst)
        else:
            raise _Changed()
    try:
        copy(source_parent, name, root, temporary, '')
        if not _same_tree(tree, _scan_at(source_parent, name, source=True)): raise _Changed()
        return temporary
    except BaseException:
        if created:
            try: _remove_tree_at(root, temporary)
            except FileNotFoundError: pass
        raise
    finally:
        os.close(source_parent)


class Manager:
    """Single-use, binding-owned plans. Public results contain basenames only."""
    def __init__(self, connector):
        self.connector = connector
        self.plans = {}
        self.lock = threading.RLock()

    def _prune(self):
        now = time.monotonic()
        for key in list(self.plans):
            if now - self.plans[key]['created'] > PLAN_SECONDS: del self.plans[key]
        while len(self.plans) > 8: del self.plans[next(iter(self.plans))]

    def _plan(self, key, revision, paths):
        if not isinstance(paths, list) or not 1 <= len(paths) <= MAX_FILES:
            raise ValueError('Choose at most 50 files or folders at once')
        folder = _current(self.connector, key, revision)
        root = _directory(folder)
        try:
            root_info = os.fstat(root)
            items, total, entries, virtual = [], 0, 0, {}
            for path in paths:
                name, source = _source_tree(path)
                total += source['bytes']; entries += len(source['entries'])
                if total > MAX_TOTAL_BYTES or entries > MAX_TREE_ENTRIES:
                    raise ValueError('Choose at most 500 MB and 10000 files at a time')
                if source['kind'] == 'directory':
                    # Prevent recursively copying a folder into itself or its descendants.
                    source_path = PurePath(path)
                    if PurePath(folder).is_relative_to(source_path) or any(
                        info[:2] == (root_info.st_dev, root_info.st_ino) for info in source['entries'].values()):
                        raise ValueError('A folder cannot be copied into itself or one of its subfolders')
                target = _target_tree(root, name)
                prior = virtual.get(name)
                same_source = bool(target and any(info[:2] == source['entries'][''][:2] for info in target['entries'].values()))
                can_replace = bool(os.atomic_exchange_available() and target and target['safe'] and not same_source and not prior)
                item = {'id': secrets.token_hex(12), 'path': path, 'name': name, 'source': source,
                        'target': target, 'virtual': bool(prior), 'can_replace': can_replace}
                items.append(item); virtual.setdefault(name, source['kind'])
            # Replacing one destination must never erase another selected source.
            # Check the entire batch, including sources encountered after a conflict.
            source_roots = {item['source']['entries'][''][:2] for item in items}
            for item in items:
                if item['target'] and any(info[:2] in source_roots for info in item['target']['entries'].values()):
                    item['can_replace'] = False
            plan = {'id': secrets.token_urlsafe(24), 'project_id': key, 'binding': revision,
                    'folder': folder, 'root': (root_info.st_dev, root_info.st_ino), 'items': items,
                    'created': time.monotonic()}
            return plan
        finally: os.close(root)

    def _review(self, plan, *, changed=False, copied=None, skipped=0):
        plan['carried_names'] = list(copied or [])
        plan['carried_skipped'] = skipped
        self._prune()
        while len(self.plans) >= 8: del self.plans[next(iter(self.plans))]
        self.plans[plan['id']] = plan
        virtual = {}
        rows = []
        for item in plan['items']:
            if item['target'] is not None or item['virtual']:
                rows.append({'id': item['id'], 'name': item['name'], 'source_kind': item['source']['kind'],
                             'target_kind': item['target']['kind'] if item['target'] else virtual[item['name']],
                             'can_replace': item['can_replace']})
            virtual.setdefault(item['name'], item['source']['kind'])
        return {'status': 'changed' if changed else 'conflicts', 'project_id': plan['project_id'],
                'binding': plan['binding'], 'plan_id': plan['id'], 'items': rows,
                'confirm_required': changed, 'names': copied or [], 'count': len(copied or []), 'skipped': skipped}

    def prepare(self, key, revision, paths):
        with self.lock, self.connector.lock:
            try:
                plan = self._plan(key, revision, paths)
                if any(item['target'] is not None or item['virtual'] for item in plan['items']): return self._review(plan)
                return self._execute(plan, {})
            except ImportFailure: raise
            except (OSError, ValueError) as exc:
                message = ('Copying failed. Check that the folder and files are available.'
                           if isinstance(exc, OSError) else str(exc) or 'The source files have changed. Choose them again.')
                raise ImportFailure(message, []) from exc

    def cancel(self, plan_id):
        with self.lock, self.connector.lock:
            names = []
            try:
                self._prune()
                plan = self.plans.pop(plan_id, None)
                if plan is None: raise ValueError('This copy selection has expired. Choose the files again.')
                names = list(plan.get('carried_names', []))
                _current(self.connector, plan['project_id'], plan['binding'])
                return {'status': 'done', 'project_id': plan['project_id'], 'binding': plan['binding'],
                        'names': names, 'count': len(names),
                        'skipped': plan.get('carried_skipped', 0) + len(plan['items']), 'cancelled': True}
            except OSError as exc:
                raise ImportFailure('Copying failed. Choose the files again.', names) from exc

    def resolve(self, plan_id, choices):
        with self.lock, self.connector.lock:
            names = []
            try:
                self._prune()
                plan = self.plans.get(plan_id)
                if plan is None: raise ValueError('This copy selection has expired. Choose the files again.')
                names = list(plan.get('carried_names', []))
                expected = {item['id']: item for item in plan['items'] if item['target'] is not None or item['virtual']}
                if not isinstance(choices, dict) or set(choices) != set(expected):
                    raise ValueError('Choose what to do with each existing file')
                for item_id, action in choices.items():
                    if action not in ('skip', 'replace', 'keep_both') or (action == 'replace' and not expected[item_id]['can_replace']):
                        raise ValueError('This copy selection is not allowed')
                del self.plans[plan_id]
                return self._execute(plan, choices)
            except OSError as exc:
                raise ImportFailure('Copying failed. Choose the files again.', names) from exc

    def _execute(self, plan, choices):
        copied, skipped, staged = list(plan.get('carried_names', [])), plan.get('carried_skipped', 0), []
        completed = set()
        root = None
        try:
            folder = _current(self.connector, plan['project_id'], plan['binding'])
            root = _directory(folder)
            info = os.fstat(root)
            if (info.st_dev, info.st_ino) != plan['root']: raise ValueError('The project folder has changed. Choose the files again.')
            changed = False
            for item in plan['items']:
                _, source = _source_tree(item['path'])
                target = _target_tree(root, item['name'])
                changed |= not _same_tree(source, item['source']) or not _same_tree(target, item['target'])
            if changed:
                return self._review(self._plan(plan['project_id'], plan['binding'], [item['path'] for item in plan['items']]),
                                    changed=True, copied=copied, skipped=skipped)
            reserved = set()
            for item in plan['items']:
                action = choices.get(item['id'], 'copy')
                if action == 'skip': skipped += 1; completed.add(item['id']); continue
                name = item['name']
                if action == 'keep_both':
                    for number in range(1, 10001):
                        candidate = _candidate(name, number, os.fpathconf(root, 'PC_NAME_MAX')) if item['source']['kind'] == 'file' else _folder_candidate(name, number, os.fpathconf(root, 'PC_NAME_MAX'))
                        if candidate not in reserved and _target_tree(root, candidate) is None:
                            name = candidate; break
                    else: raise ValueError('Too many files with this name already exist')
                if name in reserved: raise ValueError('Choose Keep both for files with the same name')
                reserved.add(name)
                temp = _stage_tree(item['path'], item['source'], root)
                staged.append({'item': item, 'action': action, 'name': name, 'temp': temp,
                               'staged_tree': _scan_at(root, temp), 'backup': False})
            # Nothing becomes visible before every source and destination is rechecked.
            for entry in staged:
                item = entry['item']
                _, source = _source_tree(item['path'])
                expected_target = item['target'] if entry['action'] == 'replace' else None
                if not _same_tree(source, item['source']) or not _same_tree(_target_tree(root, entry['name']), expected_target): raise _Changed()
            for entry in staged:
                _current(self.connector, plan['project_id'], plan['binding'])
                current_root = _directory(folder)
                try:
                    info = os.fstat(current_root)
                    if (info.st_dev, info.st_ino) != plan['root']: raise ValueError('The project folder has changed. Choose the files again.')
                finally: os.close(current_root)
                item = entry['item']
                if entry['action'] == 'replace':
                    if not _same_tree(_target_tree(root, entry['name']), item['target']): raise _Changed()
                    _rename_at(root, entry['temp'], entry['name'], 2)
                    entry['backup'] = True
                    displaced = _target_tree(root, entry['temp'])
                    if not _same_tree(displaced, item['target'], renamed=True):
                        if _same_tree(_target_tree(root, entry['name']), entry['staged_tree'], renamed=True):
                            _rename_at(root, entry['temp'], entry['name'], 2)
                            entry['backup'] = False
                        raise _Changed()
                else:
                    try: _rename_at(root, entry['temp'], entry['name'], 1)
                    except FileExistsError: raise _Changed()
                    entry['temp'] = None
                copied.append(entry['name'])
                completed.add(item['id'])
                self.connector.record(plan['project_id'], 'import_folder' if item['source']['kind'] == 'directory' else 'import_file', entry['name'])
            for entry in staged:
                if entry['backup']:
                    if not _same_tree(_target_tree(root, entry['temp']), entry['item']['target'], renamed=True):
                        error = ImportFailure('The old version changed while copying and was kept as a recovery copy.', copied)
                        error.backups = [self._retain_backup(root, entry)]
                        raise error
                    _remove_tree_at(root, entry['temp']); entry['temp'] = None
            os.fsync(root)
            return {'status': 'done', 'project_id': plan['project_id'], 'binding': plan['binding'],
                    'names': copied, 'count': len(copied), 'skipped': skipped}
        except _Changed:
            backups = self._recoverable_backups(root, staged)
            remaining = [entry['path'] for entry in plan['items'] if entry['id'] not in completed]
            if not remaining:
                error = ImportFailure('The files changed while copying. Check the project folder.', copied)
                error.backups = backups
                raise error
            try: fresh = self._plan(plan['project_id'], plan['binding'], remaining)
            except (OSError, ValueError) as exc:
                error = ImportFailure('The source files changed while copying. Choose them again.', copied)
                error.backups = backups
                raise error from exc
            result = self._review(fresh, changed=True, copied=copied, skipped=skipped)
            if backups: result['backups'] = backups
            return result
        except ImportFailure as error:
            error.backups = list(getattr(error, 'backups', [])) + self._recoverable_backups(root, staged)
            raise
        except (OSError, ValueError) as exc:
            message = ('Copying failed. Check that the folder and files are available.' if isinstance(exc, OSError) else str(exc))
            error = ImportFailure(message, copied)
            error.backups = self._recoverable_backups(root, staged)
            raise error from exc
        finally:
            if root is not None:
                for entry in staged:
                    if entry['temp'] is not None:
                        if entry['backup']:
                            # Never destroy the displaced original on an uncertain failure.
                            continue
                        try: _remove_tree_at(root, entry['temp'])
                        except FileNotFoundError: pass
                os.close(root)

    @staticmethod
    def _recoverable_backups(root, staged):
        backups = []
        for entry in staged:
            if not entry['backup'] or entry['temp'] is None: continue
            # A later batch failure leaves successful new copies in place.
            # Remove only the verified displaced original; retain anything uncertain.
            try:
                if _same_tree(_target_tree(root, entry['temp']), entry['item']['target'], renamed=True):
                    _remove_tree_at(root, entry['temp']); entry['temp'] = None
                else:
                    backups.append(Manager._retain_backup(root, entry))
            except (OSError, ValueError):
                backups.append(Manager._retain_backup(root, entry))
        return backups

    @staticmethod
    def _retain_backup(root, entry):
        name = '.vibez-backup-' + secrets.token_hex(16)
        try: _rename_at(root, entry['temp'], name, 1)
        except (OSError, ValueError): name = entry['temp']
        entry['temp'] = None
        return name


def _folder_candidate(name, number, max_bytes=255):
    if number == 1: return name
    extra = f' ({number})'
    while name and len((name + extra).encode('utf-8')) > max_bytes: name = name[:-1]
    return name + extra
