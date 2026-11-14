#!/usr/bin/env python3
"""Native, disposable backend integration proof; no account or network required.

Use the bundled Python with -I -X utf8. --backend-dir can point to installed
resources, so the exact package runtime and resource copy are exercised too.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]


def load(name, filename, backend):
    spec = importlib.util.spec_from_file_location(name, backend / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def rejected(function, message):
    try:
        function()
    except (OSError, ValueError):
        return
    raise AssertionError(message)


def check(target, backend):
    require((os.name == 'nt') == target.startswith('windows'), 'Target and native Python OS differ')
    if target.startswith('macos'):
        require(sys.platform == 'darwin', 'macOS proof must run on macOS')
    require(backend.is_dir(), 'Installed backend resource folder is absent')
    workspace = load('_ci_alpha_workspace', 'workspace_engine.py', backend)
    imports = load('_ci_alpha_import', 'project_import.py', backend)
    cap = workspace.os
    require(cap is imports.os, 'Backend modules do not share the capability facade')
    proof = {'target': target, 'python': platform.python_version(), 'fixture_only': True,
             'real_mistral_account_used': False, 'network_used': False,
             'existing_user_files_used': False, 'native_ntfs_junction_checked': False}
    expected_version = json.loads((BASE/'desktop/package.json').read_text(encoding='utf-8'))['version']
    for filename in ['workspace_engine.py', 'standalone_engine.py', 'web_connector.py']:
        values = [ast.literal_eval(statement.value)
                  for statement in ast.parse((backend/filename).read_text(encoding='utf-8')).body
                  if isinstance(statement, ast.Assign)
                  and any(isinstance(name, ast.Name) and name.id == 'VERSION'
                          for name in statement.targets)]
        require(values == [expected_version], 'Packaged service release identity differs: '+filename)
    proof['all_packaged_service_versions_match_release'] = True
    proof['backend_release_version'] = expected_version
    if target.startswith(('windows', 'macos')):
        # Use the production pin validator before executing the packaged
        # helper. On macOS its code signature changes the original bytes.
        helper = cap.tunnel_helper(backend/'vendor', '')
        result = subprocess.run([str(helper), '--version'], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=cap.runtime_env(), timeout=20,
            creationflags=0x08000000 if os.name == 'nt' else 0)
        require(result.returncode == 0 and b'cloudflared version' in result.stdout.lower(),
                'Packaged tunnel helper did not start with its validated pin')
        proof['packaged_tunnel_helper_hash_verified'] = True
        proof['packaged_tunnel_helper_version_started'] = True
    with tempfile.TemporaryDirectory(prefix='vibez-alpha-native-check-') as temporary:
        # macOS TMPDIR commonly uses /var -> /private/var. Resolve only the
        # trusted newly-created fixture root; imported user paths are never resolved.
        base = Path(temporary).resolve(strict=True)
        roots = [base / 'project-één', base / 'project-二']
        for root in roots:
            root.mkdir()
        outside = base / 'outside'; outside.mkdir()
        sentinel = outside / 'sentinel.txt'
        sentinel.write_text('outside unchanged — 不变', encoding='utf-8')
        sentinel_digest = hashlib.sha256(sentinel.read_bytes()).hexdigest()
        for index, root in enumerate(roots):
            text = f'Projet {index} — Résumé 中文\n'
            filename = 'résumé.txt'
            # Keep exact fixture bytes on Windows too: ordinary write_text
            # translates LF to CRLF, while the backend preserves source bytes.
            (root / filename).write_text(text, encoding='utf-8', newline='\n')
            client = workspace.MCPClient(str(root))
            try:
                require(client.tool('read_file', {'path': filename})['content'] == text, 'MCP UTF-8 read failed')
                denied = client.tool('write_file', {'path': filename, 'content': 'DENIED'})
                require((root / filename).read_text(encoding='utf-8') == text, 'Proposal wrote before approval')
                require(client.call('vibez/resolve', {'proposal_id': denied['proposal_id'], 'allow': False})['written'] is False,
                        'Denied proposal was reported as written')
                require((root / filename).read_text(encoding='utf-8') == text, 'Denied proposal changed a file')
                updated = text + 'Goedgekeurd — 批准\n'
                proposal = client.tool('write_file', {'path': filename, 'content': updated})
                require((root / filename).read_text(encoding='utf-8') == text, 'Proposal wrote before approval')
                require(client.call('vibez/resolve', {'proposal_id': proposal['proposal_id'], 'allow': True})['written'] is True,
                        'Approved existing-file write failed')
                require(client.tool('read_file', {'path': filename})['content'] == updated, 'Approved UTF-8 update differs')
                fresh = client.tool('write_file', {'path': 'nieuw-新.txt', 'content': updated})
                require(not (root / 'nieuw-新.txt').exists(), 'New-file proposal wrote before approval')
                require(client.call('vibez/resolve', {'proposal_id': fresh['proposal_id'], 'allow': True})['written'] is True,
                        'Approved new-file write failed')
                rejected(lambda: client.tool('read_file', {'path': '../outside/sentinel.txt'}), 'MCP escaped project boundary')
            finally:
                client.close()
        proof['two_project_mcp_utf8_read_deny_approve_create_update'] = True

        # Exercise the actual delivered stdio MCP in an isolated interpreter,
        # including new Office resources rather than only source-tree imports.
        document_root=base/'office-documents';document_root.mkdir()
        client=workspace.MCPClient(str(document_root))
        try:
            for extension in ['.odt','.docx','.ods','.xlsx','.odp','.pptx']:
                name='approved'+extension
                text='SAVE — Résumé 中文' if extension not in ['.ods','.xlsx'] else 'Name\tValue\nSAVE\tRésumé 中文'
                proposal=client.tool('create_document',{'path':name,'content':text})
                require(not (document_root/name).exists(),'Office document saved before approval')
                require(proposal.get('document_format')==extension,'Office preview lost format metadata')
                result=client.call('vibez/resolve',{'proposal_id':proposal['proposal_id'],'allow':True})
                require(result['written'] is True,'Approved Office creation failed')
                read=client.tool('read_file',{'path':name})
                require(all(value in read['content'] for value in ['SAVE','Résumé','中文']),'Created Office document cannot be read back')
                before=(document_root/name).read_bytes()
                rejected(lambda:client.tool('create_document',{'path':name,'content':'not an overwrite'}),'Existing Office document was overwritten')
                require((document_root/name).read_bytes()==before,'Existing Office bytes changed')
            proposal=client.tool('create_document',{'path':'rejected.odt','content':'Not saved'})
            require(client.call('vibez/resolve',{'proposal_id':proposal['proposal_id'],'allow':False})['written'] is False,'Denied Office creation was saved')
            require(not (document_root/'rejected.odt').exists(),'Denied Office creation changed the filesystem')
        finally:
            client.close()
        proof['packaged_six_format_office_create_approve_read_no_clobber_and_deny'] = True


        key = 'disposable-native-project'
        class Connector:
            def __init__(self):
                self.lock = threading.RLock()
                self.active = {'id': key}
                self.projects = {key: {'folder': str(roots[0]), 'token': 'disposable-fixture-only'}}
            def record(self, *args):
                pass
        connector = Connector()
        manager = imports.Manager(connector)
        tree = outside / 'nested-é'; (tree / 'sub-二').mkdir(parents=True)
        source = tree / 'sub-二' / 'résumé.txt'
        source.write_text('original source — 甲', encoding='utf-8')
        binding = imports.binding(connector, key)
        result = manager.prepare(key, binding, [str(tree)])
        require(result['status'] == 'done', 'Nested-folder import failed')
        copied = roots[0] / tree.name / 'sub-二' / 'résumé.txt'
        require(copied.read_text(encoding='utf-8') == 'original source — 甲', 'Nested import contents differ')
        source.write_text('updated source — 乙', encoding='utf-8')
        conflict = manager.prepare(key, binding, [str(tree)])
        require(conflict['status'] == 'conflicts' and len(conflict['items']) == 1, 'Existing folder did not require a choice')
        if os.name == 'nt':
            require(not conflict['items'][0]['can_replace'], 'Windows advertised unsupported atomic exchange')
        result = manager.resolve(conflict['plan_id'], {conflict['items'][0]['id']: 'keep_both'})
        require(result['status'] == 'done', 'Keep-both import failed')
        require(copied.read_text(encoding='utf-8') == 'original source — 甲', 'Keep-both replaced original destination')
        second = roots[0] / (tree.name + ' (2)') / 'sub-二' / 'résumé.txt'
        require(second.read_text(encoding='utf-8') == 'updated source — 乙', 'Keep-both copy differs')
        require(source.read_text(encoding='utf-8') == 'updated source — 乙', 'Import changed its source')
        require(not (roots[1] / tree.name).exists(), 'Import leaked into another project')
        proof['nested_folder_import_keep_both_preserves_source_and_destination'] = True

        w = workspace.Workspace(str(roots[0]))
        try:
            alias = roots[0] / 'hardlink.txt'; os.link(sentinel, alias)
            rejected(lambda: w.read('hardlink.txt'), 'Hardlink expanded workspace access')
            alias.unlink()
            link = roots[0] / 'outside-link'
            if os.name == 'nt':
                command = str(Path(cap.runtime_env()['SystemRoot']) / 'System32' / 'cmd.exe')
                created = subprocess.run([command, '/d', '/c', 'mklink', '/J', str(link), str(outside)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env=cap.runtime_env(), creationflags=0x08000000, timeout=15)
                is_wine = hasattr(cap._nt, 'wine_get_version')
                try:
                    info = os.lstat(link)
                except FileNotFoundError:
                    require(is_wine, 'Native Windows failed to create required NTFS junction fixture')
                    proof['wine_junction_fixture_unavailable'] = True
                else:
                    require(created.returncode == 0, 'Junction creation command failed')
                    require(getattr(info, 'st_file_attributes', 0) & 0x400, 'Fixture is not a Windows reparse point')
                    rejected(lambda: w.read('outside-link/sentinel.txt'), 'Junction expanded workspace access')
                    rejected(lambda: workspace.Workspace(str(link)), 'Junction root was accepted')
                    link.rmdir()
                    proof['native_ntfs_junction_checked'] = not is_wine
                if not is_wine:
                    require(proof['native_ntfs_junction_checked'], 'Native NTFS junction check was skipped')
            else:
                link.symlink_to(outside, target_is_directory=True)
                rejected(lambda: w.read('outside-link/sentinel.txt'), 'Symlink expanded workspace access')
                rejected(lambda: imports._directory(str(link)), 'Import followed a symlink source')
                link.unlink()
                proof['posix_symlink_checked'] = True
        finally:
            w.close()
        require(hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_digest, 'Outside sentinel changed')
        require(not any(p.name.startswith('.vibez-') for root in roots for p in root.iterdir()), 'Staging files leaked')
        proof['outside_sentinel_unchanged_and_no_staging_leak'] = True
    require(not list(backend.rglob('__pycache__')), 'Bundled backend was changed by Python bytecode caches')
    proof['bundled_backend_no_bytecode_cache'] = True
    proof['passed'] = True
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=['linux-x64', 'windows-x64', 'macos-x64', 'macos-arm64'], required=True)
    parser.add_argument('--backend-dir', type=Path, default=BASE / 'backend')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = check(args.target, args.backend_dir.resolve(strict=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
