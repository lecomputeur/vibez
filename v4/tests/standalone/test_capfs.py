"""Cross-platform file-boundary tests; Windows cases run on Windows Python.

All files, links and folders are disposable. No live Mistral account is used.
"""
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'backend'/filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

cap = sys.modules.get('_vibez_capfs') or load('_vibez_capfs', 'capfs.py')
workspace = load('capfs_workspace_test', 'workspace_engine.py')
imports = load('capfs_import_test', 'project_import.py')


class PathPolicyTests(unittest.TestCase):
    def test_windows_single_components_reject_device_ads_alias_and_escape_names(self):
        for value in ['', 'x.txt:secret', 'C:drive.txt', 'NUL', 'con.txt', 'COM¹.txt', 'LPT9', '.', '..',
                      'folder/name', 'folder\\name', 'trailing.', 'trailing ', 'a\0b', '?', 'bad|name']:
            with self.subTest(value=value), self.assertRaises((ValueError, UnicodeError)):
                cap.windows_component(value)
        for value in ['file.txt', 'résumé.md', '普通文件.txt', '.vibez-stage-abc']:
            self.assertEqual(cap.windows_component(value), value)

    def test_windows_absolute_paths_do_not_accept_unc_device_or_drive_relative_names(self):
        for value in ['C:relative.txt', '\\rooted', '\\\\server\\share\\file', '\\\\.\\C:\\file',
                      '\\\\?\\GLOBALROOT\\Device\\HarddiskVolume1\\file', 'C:\\a\\..\\file',
                      'C:\\a\\.\\file', 'C:\\a\\CON.txt', 'C:\\file:stream', 'C:\\a\\\\file']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                cap.windows_absolute(value)
        self.assertEqual(cap.windows_absolute('c:/Users/test/project')[0], 'C:\\Users\\test\\project')
        self.assertEqual(cap.windows_absolute('\\\\?\\C:\\Users\\test\\project')[0], 'C:\\Users\\test\\project')

    def test_backend_modules_share_one_capability_facade(self):
        self.assertIs(workspace.os, cap)
        self.assertIs(imports.os, cap)


@unittest.skipIf(os.name == 'nt', 'POSIX no-follow regression')
class PosixCapabilityTests(unittest.TestCase):
    def test_approved_new_file_does_not_require_filesystem_hardlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            w = workspace.Workspace(str(root))
            try:
                proposal = w.proposal('new.txt', 'approved text')
                self.assertFalse((root/'new.txt').exists())
                with mock.patch.object(cap._os, 'link', side_effect=OSError('Hardlinks unsupported')):
                    self.assertTrue(w.commit(proposal)['written'])
                self.assertEqual((root/'new.txt').read_text(), 'approved text')
                self.assertEqual([p.name for p in root.iterdir()], ['new.txt'])
            finally:
                w.close()

    def test_new_file_publication_race_never_overwrites_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            w = workspace.Workspace(str(root))
            original = cap.rename_noreplace
            def competing_file(fd, source, target):
                (root/target).write_text('concurrent existing file')
                return original(fd, source, target)
            try:
                proposal = w.proposal('new.txt', 'proposed content')
                with mock.patch.object(cap, 'rename_noreplace', side_effect=competing_file):
                    with self.assertRaises(FileExistsError):
                        w.commit(proposal)
                self.assertEqual((root/'new.txt').read_text(), 'concurrent existing file')
                self.assertEqual([p.name for p in root.iterdir()], ['new.txt'])
            finally:
                w.close()

    def test_existing_directory_handle_boundary_and_hardlink_policy_remain(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); root = base/'project'; root.mkdir(); outside = base/'outside'; outside.mkdir()
            (outside/'secret.txt').write_text('outside unchanged')
            (root/'note.txt').write_text('original')
            (root/'jump').symlink_to(outside, target_is_directory=True)
            (root/'alias.txt').hardlink_to(outside/'secret.txt')
            w = workspace.Workspace(str(root))
            try:
                self.assertEqual(w.read('note.txt')['content'], 'original')
                for name in ['jump/secret.txt', 'alias.txt', '../outside/secret.txt']:
                    with self.subTest(name=name), self.assertRaises((OSError, ValueError)):
                        w.read(name)
                proposal = w.proposal('created.txt', 'approved content')
                w.commit(proposal)
                self.assertEqual((root/'created.txt').read_text(), 'approved content')
                self.assertEqual((outside/'secret.txt').read_text(), 'outside unchanged')
            finally: w.close()

    def test_absolute_import_walk_does_not_follow_parent_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            # macOS's trusted temporary root may start at /var -> /private/var.
            # Resolve the fixture root, retaining the deliberately untrusted link.
            base = Path(temporary).resolve(strict=True)
            real = base/'real'; real.mkdir(); link = base/'link'; link.symlink_to(real, target_is_directory=True)
            with self.assertRaises((OSError, ValueError)):
                imports._directory(str(link))
            root = imports._directory(str(real))
            try:
                imports.create_directory(str(real), 'child', expected_fd=root)
                self.assertTrue((real/'child').is_dir())
            finally: cap.close(root)


@unittest.skipUnless(sys.platform == 'linux', 'Flatpak runtime-directory alias policy')
class FlatpakDocumentAliasTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='vibez-portal-alias-')
        self.root = Path(self.temporary.name)
        self.uid = str(os.getuid())
        self.user = self.root/'run/user'/self.uid
        self.user.mkdir(parents=True)
        self.portal = self.root/'run/flatpak/doc'
        self.portal.mkdir(parents=True)
        self.selected = self.portal/'chosen-id/project'
        self.selected.mkdir(parents=True)
        (self.selected/'marker.txt').write_text('selected portal content')
        self.alias = self.user/'doc'
        self.alias.symlink_to('../../flatpak/doc')
        self.marker = self.root/'.flatpak-info'
        self.marker.write_text('[Application]\nname=nl.lecomputeur.vibez4.alpha\n')
        native_open = os.open
        def sandbox_open(path, flags, *args, **kwargs):
            # Test the actual no-follow walk against a disposable sandbox tree;
            # only its two OS-owned absolute starting points are remapped.
            if path == '/': path = str(self.root)
            elif path == '/.flatpak-info': path = str(self.marker)
            return native_open(path, flags, *args, **kwargs)
        self.patch_open = mock.patch.object(cap._os, 'open', side_effect=sandbox_open)
        self.patch_open.start()

    def tearDown(self):
        self.patch_open.stop()
        self.temporary.cleanup()

    def alias_path(self, tail='chosen-id/project'):
        return '/run/user/' + self.uid + '/doc/' + tail

    def test_trusted_runtime_alias_opens_only_the_app_scoped_portal_mount(self):
        for target in ['../../flatpak/doc', '/run/flatpak/doc']:
            with self.subTest(target=target):
                self.alias.unlink(); self.alias.symlink_to(target)
                fd = cap.open_directory(self.alias_path())
                try:
                    self.assertEqual(os.fstat(fd).st_ino, self.selected.stat().st_ino)
                    self.assertEqual(set(cap.listdir(fd)), {'marker.txt'})
                finally: cap.close(fd)

    def test_portal_leaf_symlinks_and_traversal_remain_forbidden(self):
        outside = self.root/'outside'; outside.mkdir()
        (outside/'sentinel.txt').write_text('outside untouched')
        (self.portal/'chosen-id/escape').symlink_to(outside)
        for value in [self.alias_path('chosen-id/escape'), self.alias_path('chosen-id/../chosen-id/project')]:
            with self.subTest(path=value), self.assertRaises((OSError, ValueError)):
                cap.open_directory(value)
        self.assertEqual((outside/'sentinel.txt').read_text(), 'outside untouched')

    def test_unexpected_alias_targets_are_rejected(self):
        for target in ['/tmp', '../../../flatpak/doc', '../../flatpak/doc/other', '/run/user/0/doc']:
            with self.subTest(target=target):
                self.alias.unlink(); self.alias.symlink_to(target)
                with self.assertRaises((OSError, ValueError)):
                    cap.open_directory(self.alias_path())

    def test_other_users_and_prefix_lookalikes_receive_no_alias_exception(self):
        for folder in [self.root/'run/user'/(self.uid+'1'), self.user]:
            folder.mkdir(parents=True, exist_ok=True)
        (self.root/'run/user'/(self.uid+'1')/'doc').symlink_to('../../flatpak/doc')
        (self.user/'documents').symlink_to('../../flatpak/doc')
        for path in ['/run/user/'+self.uid+'1/doc/chosen-id/project', '/run/user/'+self.uid+'/documents/chosen-id/project']:
            with self.subTest(path=path), self.assertRaises((OSError, ValueError)):
                cap.open_directory(path)

    def test_missing_forged_or_symlinked_sandbox_marker_never_authorizes_alias(self):
        for content in [None, '[Application]\nname=other.app\n', '[Application]\nname=nl.lecomputeur.vibez4.alpha\n'*2, 'x'*65537]:
            with self.subTest(marker=content is None or content[:40]):
                self.marker.unlink(missing_ok=True)
                if content is not None: self.marker.write_text(content)
                with self.assertRaises((OSError, ValueError)):
                    cap.open_directory(self.alias_path())
        self.marker.unlink(missing_ok=True)
        forged = self.root/'forged-marker'; forged.write_text('[Application]\nname=nl.lecomputeur.vibez4.alpha\n')
        self.marker.symlink_to(forged)
        with self.assertRaises((OSError, ValueError)):
            cap.open_directory(self.alias_path())

    def test_replacing_the_alias_after_validation_cannot_redirect_the_fixed_mount_open(self):
        original = cap._os.readlink
        outside = self.root/'outside'; outside.mkdir()
        def raced(path, **kwargs):
            target = original(path, **kwargs)
            self.alias.unlink(); self.alias.symlink_to(outside)
            return target
        with mock.patch.object(cap._os, 'readlink', side_effect=raced):
            fd = cap.open_directory(self.alias_path())
            try: self.assertEqual(os.fstat(fd).st_ino, self.selected.stat().st_ino)
            finally: cap.close(fd)

    def test_real_runtime_directory_needs_no_sandbox_marker_or_exception(self):
        self.alias.unlink(); self.alias.mkdir()
        child = self.alias/'direct'; child.mkdir()
        self.marker.unlink()
        fd = cap.open_directory(self.alias_path('direct'))
        try: self.assertEqual(os.fstat(fd).st_ino, child.stat().st_ino)
        finally: cap.close(fd)


@unittest.skipUnless(os.name == 'nt', 'Requires Windows handles; not claimed by POSIX tests')
class WindowsCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='vibez-capfs-')
        self.base = Path(self.temporary.name); self.root = self.base/'project'; self.root.mkdir()
        self.outside = self.base/'outside'; self.outside.mkdir(); (self.outside/'sentinel.txt').write_text('outside unchanged', encoding='utf-8')
        self.w = workspace.Workspace(str(self.root))
    def tearDown(self):
        self.w.close(); self.temporary.cleanup()

    def test_real_handles_list_read_approved_write_and_no_clobber(self):
        proposal = self.w.proposal('note.txt', 'first')
        self.w.commit(proposal)
        self.assertEqual(self.w.read('note.txt')['content'], 'first')
        proposal = self.w.proposal('note.txt', 'second')
        self.w.commit(proposal)
        self.assertEqual((self.root/'note.txt').read_text(), 'second')
        imports.create_directory(str(self.root), 'child', expected_fd=self.w.fd)
        names = {entry['name'] for entry in self.w.listing()['entries']}
        self.assertEqual(names, {'note.txt', 'child'})
        with self.assertRaises(FileExistsError):
            cap.open('note.txt', cap.O_WRONLY | cap.O_CREAT | cap.O_EXCL | cap.O_NOFOLLOW, dir_fd=self.w.fd)
        self.assertEqual((self.root/'note.txt').read_text(), 'second')
        self.assertEqual((self.outside/'sentinel.txt').read_text(), 'outside unchanged')

    def test_native_noreplace_publishes_staging_without_clobber(self):
        for name, content in [('stage', b'new'), ('existing', b'old')]:
            fd = cap.open(name, cap.O_WRONLY | cap.O_CREAT | cap.O_EXCL | cap.O_NOFOLLOW, dir_fd=self.w.fd)
            try: cap.write(fd, content)
            finally: cap.close(fd)
        with self.assertRaises(FileExistsError): imports._rename_at(self.w.fd, 'stage', 'existing', 1)
        imports._rename_at(self.w.fd, 'stage', 'published', 1)
        self.assertEqual((self.root/'published').read_bytes(), b'new')
        self.assertEqual((self.root/'existing').read_bytes(), b'old')
        with self.assertRaises(ValueError): imports._rename_at(self.w.fd, 'existing', 'published', 2)
        self.assertEqual((self.root/'existing').read_bytes(), b'old')

    def test_directory_enumerations_have_independent_cursors(self):
        # Exceed one 64 KiB native enumeration batch, so two scans cannot pass
        # merely because both prefetched a small directory into Python memory.
        count = 900
        for index in range(count): (self.root/f'{index:04}.txt').write_text(str(index))
        with cap.scandir(self.w.fd) as a, cap.scandir(self.w.fd) as b:
            first_a, first_b = next(a).name, next(b).name
            self.assertEqual(first_a, first_b)
            all_a = {first_a, *(entry.name for entry in a)}
            all_b = {first_b, *(entry.name for entry in b)}
        self.assertEqual(all_a, all_b)
        self.assertEqual(len(all_a), count)

    def test_hardlinks_and_alternate_data_streams_cannot_be_read_or_written(self):
        os.link(self.outside/'sentinel.txt', self.root/'alias.txt')
        for name in ['alias.txt', 'alias.txt:secret', 'NUL.txt', 'C:relative.txt', '../outside/sentinel.txt']:
            with self.subTest(name=name), self.assertRaises((OSError, ValueError)):
                self.w.read(name)
        with self.assertRaises((OSError, ValueError)):
            self.w.proposal('alias.txt', 'changed')
        self.assertEqual((self.outside/'sentinel.txt').read_text(), 'outside unchanged')

    def test_retained_root_handle_blocks_ancestor_substitution(self):
        with self.assertRaises(OSError): os.rename(self.root, self.base/'moved-project')
        self.assertTrue(self.root.is_dir())

    def test_junction_and_symbolic_link_roots_cannot_expand_access(self):
        junction = self.root/'junction'
        command = str(Path(os.environ['SystemRoot'])/'System32/cmd.exe')
        done = subprocess.run([command, '/d', '/c', 'mklink', '/J', str(junction), str(self.outside)],
                              env=cap.runtime_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if done.returncode:
            self.skipTest('This Windows fixture filesystem does not support junction creation')
        try:
            os.lstat(junction)
        except FileNotFoundError:
            if hasattr(cap._nt, 'wine_get_version'):
                self.skipTest('Wine cmd reported success without creating a junction; native NTFS run required')
            self.fail('The Windows fixture did not create the requested junction')
        with self.assertRaises((OSError, ValueError)): self.w.read('junction/sentinel.txt')
        with self.assertRaises((OSError, ValueError)): workspace.Workspace(str(junction))
        try:
            info = cap.stat('junction', dir_fd=self.w.fd, follow_symlinks=False)
        except OSError:
            # Unsupported reparse metadata still fails closed; never resolve it.
            pass
        else:
            self.assertTrue(stat.S_ISLNK(info.st_mode))
        # The trusted fixture removes the junction entry; it never walks target.
        junction.rmdir()
        self.assertEqual((self.outside/'sentinel.txt').read_text(), 'outside unchanged')

    def test_imported_tree_preserves_sources_and_conflicts_offer_only_safe_choices(self):
        key = 'windows-fixture'
        class Connector:
            lock = threading.RLock()
            active = {'id': key}
            projects = {key: {'folder': str(self.root), 'token': 'fixture-token'}}
            def record(self, *args): pass
        connector = Connector(); manager = imports.Manager(connector)
        tree = self.outside/'copied-tree'; tree.mkdir(); (tree/'résumé.txt').write_text('source', encoding='utf-8')
        proof = imports.binding(connector, key)
        result = manager.prepare(key, proof, [str(tree)])
        self.assertEqual(result['status'], 'done')
        self.assertEqual((self.root/'copied-tree/résumé.txt').read_text(encoding='utf-8'), 'source')
        (tree/'résumé.txt').write_text('new source', encoding='utf-8')
        conflict = manager.prepare(key, proof, [str(tree)])
        self.assertEqual(conflict['status'], 'conflicts')
        self.assertFalse(conflict['items'][0]['can_replace'])
        with self.assertRaises(ValueError):
            manager.resolve(conflict['plan_id'], {conflict['items'][0]['id']: 'replace'})
        result = manager.resolve(conflict['plan_id'], {conflict['items'][0]['id']: 'keep_both'})
        self.assertEqual(result['status'], 'done')
        self.assertEqual((self.root/'copied-tree/résumé.txt').read_text(encoding='utf-8'), 'source')
        self.assertEqual((self.root/'copied-tree (2)/résumé.txt').read_text(encoding='utf-8'), 'new source')
        self.assertEqual((tree/'résumé.txt').read_text(encoding='utf-8'), 'new source')

    def test_packaged_mcp_child_uses_utf8_without_environment_credentials(self):
        (self.root/'résumé.txt').write_text('Résumé 中文', encoding='utf-8')
        original = workspace.subprocess.Popen
        log_path = self.base/'mcp-child-error.log'
        with log_path.open('wb') as log:
            def start(*args, **kwargs):
                kwargs['stderr'] = log
                return original(*args, **kwargs)
            with mock.patch.object(workspace.subprocess, 'Popen', side_effect=start):
                try:
                    client = workspace.MCPClient(str(self.root))
                except Exception as error:
                    log.flush()
                    self.fail(str(error) + ': ' + log_path.read_text(errors='replace'))
        try:
            result = client.tool('read_file', {'path': 'résumé.txt'})
            self.assertIn('Résumé 中文', str(result))
        finally: client.close()

    def test_child_environment_keeps_os_locations_without_proxy_or_credentials(self):
        with mock.patch.dict(os.environ, {'HTTP_PROXY': 'http://invalid.test', 'AWS_SECRET_ACCESS_KEY': 'fixture-only'}):
            env = cap.runtime_env()
        self.assertNotIn('HTTP_PROXY', env)
        self.assertNotIn('AWS_SECRET_ACCESS_KEY', env)
        self.assertTrue(Path(env['SystemRoot']).is_dir())
        self.assertEqual(env['USERPROFILE'], cap.user_home())

    def test_broad_roots_and_unknown_crt_descriptors_are_rejected(self):
        drive = Path(self.root.anchor)
        with self.assertRaises(ValueError): workspace.Workspace(str(drive))
        with self.assertRaises(ValueError): workspace.Workspace(str(Path.home()))
        fd = os.open(self.root/'ordinary.txt', os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            with self.assertRaises(ValueError): cap.fstat(fd)
        finally: os.close(fd)


if __name__ == '__main__':
    unittest.main(verbosity=2)
