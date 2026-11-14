"""Explicit local roots, exposed to MCP as safe virtual directory prefixes.

The directory handles and file approval rules are supplied by the existing
Workspace implementation. No model-provided path ever selects an OS root.
"""
import hashlib
import os
from pathlib import Path
import re

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

MAX_ROOTS = 16
ROOT_ID = re.compile(r'^[0-9a-f]{32}$')
ALIAS = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


def entry(path):
    if not isinstance(path, str) or not os.is_absolute(path):
        raise ValueError('Invalid linked workspace')
    key = hashlib.sha256(path.encode('utf-8')).hexdigest()[:32]
    label = re.sub(r'[^A-Za-z0-9_-]+', '-', Path(path).name).strip('-_')[:48] or 'workspace'
    return {'id': key, 'path': path, 'alias': label + '-' + key[:8]}


def roots(project):
    if not project:
        return []
    if 'folders' not in project:
        return [entry(project['folder'])]
    items = project['folders']
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ROOTS:
        raise ValueError('Invalid list of linked workspaces')
    result = []
    ids, paths, aliases = set(), set(), set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {'id', 'path', 'alias'}:
            raise ValueError('Invalid linked workspace')
        wanted = entry(item.get('path'))
        if not isinstance(item.get('id'), str) or not ROOT_ID.fullmatch(item['id']) or item['id'] != wanted['id']:
            raise ValueError('Invalid workspace code')
        alias = item.get('alias')
        if not isinstance(alias, str) or not ALIAS.fullmatch(alias):
            raise ValueError('Invalid workspace prefix')
        if item['id'] in ids or item['path'] in paths or alias.casefold() in aliases:
            raise ValueError('This workspace folder is linked more than once')
        ids.add(item['id']); paths.add(item['path']); aliases.add(alias.casefold())
        result.append(dict(item))
    if project['folder'] not in paths or project.get('target_folder_id') not in ids:
        raise ValueError('The chosen workspace does not belong to this project')
    return result


def target(project):
    items = roots(project)
    if not items:
        return None
    key = project.get('target_folder_id', items[0]['id'])
    return next(item for item in items if item['id'] == key)


class MultiWorkspace:
    def __init__(self, base, entries):
        self.base = base
        self.entries = [dict(item) for item in entries]
        self.workspaces = {}
        self.aliases = {item['alias']: item['id'] for item in self.entries}
        self.root = self.entries[0]['path']
        try:
            for item in self.entries:
                workspace = base.Workspace(item['path'])
                if workspace.root != item['path']:
                    workspace.close()
                    raise ValueError('A linked workspace folder was moved or redirected; choose the folder again')
                self.workspaces[item['id']] = workspace
        except BaseException:
            self.close()
            raise

    @property
    def fd(self):
        return next(iter(self.workspaces.values())).fd if self.workspaces else -1

    def close(self):
        for workspace in self.workspaces.values():
            workspace.close()
        self.workspaces.clear()

    def _route(self, path, *, directory=False):
        parts = self.base.Workspace.parts(path, directory)
        if not parts or parts[0] not in self.aliases or (not directory and len(parts) < 2):
            raise ValueError('Use the folder prefix from list_directory(".") for the file path')
        key = self.aliases[parts[0]]
        return self.workspaces[key], key, '/'.join(parts[1:]) or '.'

    def listing(self, path='.'):
        if path in ('', '.'):
            return {'entries': [{'name': item['alias'], 'type': 'directory', 'label': Path(item['path']).name} for item in self.entries],
                    'truncated': False, 'multiple_workspaces': True,
                    'instructions': 'Use these directory names as prefixes for all file paths.'}
        workspace, _, inner = self._route(path, directory=True)
        return workspace.listing(inner)

    def read(self, path):
        workspace, _, inner = self._route(path)
        return {**workspace.read(inner), 'path': path}

    def read_image(self, path):
        workspace, _, inner = self._route(path)
        return workspace.read_image(inner)

    def proposal(self, path, content):
        workspace, key, inner = self._route(path)
        return {**workspace.proposal(inner, content), 'path': path,
                '_workspace_id': key, '_workspace_path': inner}

    def create_document(self, path, content):
        workspace, key, inner = self._route(path)
        return {**workspace.create_document(inner, content), 'path': path,
                '_workspace_id': key, '_workspace_path': inner}

    def validate(self, proposal):
        workspace, key, inner = self._route(proposal['path'])
        if proposal.get('_workspace_id') != key or proposal.get('_workspace_path') != inner:
            raise ValueError('The workspace folder of this proposal has changed')
        current = os.stat(workspace.root, follow_symlinks=False)
        anchored = os.fstat(workspace.fd)
        if (current.st_dev, current.st_ino) != (anchored.st_dev, anchored.st_ino) or os.same_root_name(workspace.root) != workspace.root:
            raise ValueError('The workspace folder was replaced in the meantime; link the folder again')
        return workspace, inner

    def commit(self, proposal):
        workspace, inner = self.validate(proposal)
        local = {key: value for key, value in proposal.items() if not key.startswith('_workspace_')}
        local['path'] = inner
        return {**workspace.commit(local), 'path': proposal['path']}

    def overview(self):
        combined = {'files': 0, 'directories': 0, 'bytes': 0, 'extensions': {}, 'truncated': False,
                    'source': self.base.WORKSPACE_SOURCE, 'workspaces': []}
        for item in self.entries:
            value = self.workspaces[item['id']].overview()
            combined['workspaces'].append({'path': item['alias'], 'name': Path(item['path']).name,
                                           **{key: value[key] for key in ['files', 'directories', 'bytes', 'truncated']}})
            for key in ['files', 'directories', 'bytes']:
                combined[key] += value[key]
            combined['truncated'] = combined['truncated'] or value['truncated']
            for extension, count in value['extensions'].items():
                combined['extensions'][extension] = combined['extensions'].get(extension, 0) + count
        return combined


def open_workspace(base, entries):
    if len(entries) > 1:
        return MultiWorkspace(base, entries)
    workspace = base.Workspace(entries[0]['path'])
    if workspace.root != entries[0]['path']:
        workspace.close()
        raise ValueError('The workspace folder was moved or redirected; choose the folder again')
    return workspace
