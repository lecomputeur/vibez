import importlib.util
import errno
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('project_import', Path(__file__).parents[2]/'backend/project_import.py')
imports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imports)
engine_spec = importlib.util.spec_from_file_location('project_import_engine', Path(__file__).parents[2]/'backend/standalone_engine.py')
app = importlib.util.module_from_spec(engine_spec)
engine_spec.loader.exec_module(app)


class Connector:
    def __init__(self, root):
        self.lock = threading.RLock()
        self.active = {'id': 'work-a'}
        self.projects = {
            'work-a': {'folder': str(root/'Alpha'), 'token': 'fixture-A'},
            'code-a': {'folder': str(root/'Code'), 'token': 'fixture-Code'},
        }
        self.activity = []

    def record(self, key, action, name):
        self.activity.append((key, action, name))


class ProjectImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root/'Sources'; self.source.mkdir()
        self.a = self.root/'Alpha'; self.a.mkdir()
        self.code = self.root/'Code'; self.code.mkdir()
        self.c = Connector(self.root)
        self.proof = imports.binding(self.c)

    def tearDown(self):
        self.tmp.cleanup()

    def source_file(self, name='example.txt', content=b'Original source\x00\xff'):
        path = self.source/name
        path.write_bytes(content)
        return path

    def run_copy(self, *paths, key='work-a', proof=None):
        return imports.copy_files(self.c, key, self.proof if proof is None else proof, [str(p) for p in paths])

    def clean(self):
        self.assertFalse(any(self.a.glob('.vibez-import-*')))

    def test_binary_copy_preserves_source_and_records_only_local_copy(self):
        source = self.source_file()
        before = source.read_bytes()
        result = self.run_copy(source)
        self.assertEqual(result, {'project_id': 'work-a', 'binding': self.proof, 'names': ['example.txt'], 'count': 1})
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual((self.a/source.name).read_bytes(), before)
        self.assertEqual(self.c.activity, [('work-a', 'import_file', 'example.txt')])
        self.clean()

    def test_collisions_keep_existing_files_and_assign_incrementing_names(self):
        source = self.source_file('rapport.md', b'New')
        (self.a/source.name).write_bytes(b'Existing')
        (self.a/'rapport (2).md').write_bytes(b'Other')
        self.assertEqual(self.run_copy(source)['names'], ['rapport (3).md'])
        self.assertEqual((self.a/source.name).read_bytes(), b'Existing')
        self.assertEqual((self.a/'rapport (2).md').read_bytes(), b'Other')
        self.assertEqual((self.a/'rapport (3).md').read_bytes(), b'New')

    def test_existing_destination_symlink_is_never_followed_or_overwritten(self):
        outside = self.root/'outside'; outside.write_bytes(b'Outside')
        source = self.source_file()
        (self.a/source.name).symlink_to(outside)
        self.assertEqual(self.run_copy(source)['names'], ['example (2).txt'])
        self.assertTrue((self.a/source.name).is_symlink())
        self.assertEqual(outside.read_bytes(), b'Outside')

    def test_copy_on_a_filesystem_without_hardlinks_keeps_existing_names_intact(self):
        source = self.source_file('portal-file.bin', b'Complete portal copy\x00\xff')
        (self.a/source.name).write_bytes(b'Existing file')
        with patch.object(imports.os, 'link', side_effect=OSError(errno.EPERM, 'Hard links are unsupported')) as link:
            copied = self.run_copy(source)
        self.assertEqual(copied['names'], ['portal-file (2).bin'])
        self.assertEqual((self.a/source.name).read_bytes(), b'Existing file')
        self.assertEqual((self.a/copied['names'][0]).read_bytes(), source.read_bytes())
        self.assertEqual(source.read_bytes(), b'Complete portal copy\x00\xff')
        link.assert_not_called()
        self.clean()

    def test_publish_race_keeps_the_concurrent_file_and_uses_a_free_name(self):
        source = self.source_file('race.txt', b'Our complete bytes')
        rename = imports._rename_at
        def raced(root, temporary, target, flag):
            if target == source.name:
                (self.a/target).write_bytes(b'Concurrent destination')
            return rename(root, temporary, target, flag)
        with patch.object(imports, '_rename_at', side_effect=raced):
            result = self.run_copy(source)
        self.assertEqual(result['names'], ['race (2).txt'])
        self.assertEqual((self.a/source.name).read_bytes(), b'Concurrent destination')
        self.assertEqual((self.a/result['names'][0]).read_bytes(), b'Our complete bytes')
        self.clean()

    def test_duplicate_source_names_in_one_batch_get_distinct_copies(self):
        source = self.source_file()
        self.assertEqual(self.run_copy(source, source)['names'], ['example.txt', 'example (2).txt'])

    def test_long_multibyte_collision_name_stays_within_filesystem_limit(self):
        source = self.source_file('ä'*124+'.md')
        (self.a/source.name).write_bytes(b'Existing')
        name = self.run_copy(source)['names'][0]
        self.assertLessEqual(len(name.encode()), 255)
        self.assertTrue(name.endswith(' (2).md'))
        self.assertEqual((self.a/source.name).read_bytes(), b'Existing')

    def test_work_and_code_keep_separate_destinations(self):
        source = self.source_file()
        self.run_copy(source)
        self.c.active = {'id': 'code-a'}
        code_proof = imports.binding(self.c)
        self.assertNotEqual(self.proof, code_proof)
        result = self.run_copy(source, key='code-a', proof=code_proof)
        self.assertEqual(result['project_id'], 'code-a')
        self.assertEqual((self.a/source.name).read_bytes(), source.read_bytes())
        self.assertEqual((self.code/source.name).read_bytes(), source.read_bytes())

    def test_project_switch_rejects_stale_drop_before_any_copy(self):
        source = self.source_file()
        self.c.active = {'id': 'code-a'}
        with self.assertRaises(ValueError): self.run_copy(source)
        self.assertEqual(list(self.a.iterdir()), [])
        self.assertEqual(list(self.code.iterdir()), [])

    def test_folder_relink_rejects_old_grant(self):
        source = self.source_file()
        self.c.projects['work-a']['folder'] = str(self.code)
        with self.assertRaises(ValueError): self.run_copy(source)
        self.assertEqual(list(self.code.iterdir()), [])

    def test_relink_or_key_rotation_at_same_folder_invalidates_grant(self):
        source = self.source_file()
        self.c.projects['work-a']['token'] = 'replacement'
        with self.assertRaises(ValueError): self.run_copy(source)
        self.assertEqual(list(self.a.iterdir()), [])

    def test_no_active_project_or_no_binding_cannot_import(self):
        source = self.source_file()
        self.c.active = None
        with self.assertRaises(ValueError): self.run_copy(source)
        self.c.active = {'id': 'work-a'}
        with self.assertRaises(ValueError): self.run_copy(source, proof='')
        self.assertEqual(list(self.a.iterdir()), [])

    def test_source_symlinks_and_symlinked_parent_are_rejected(self):
        source = self.source_file()
        link = self.source/'linked.txt'; link.symlink_to(source)
        alias = self.root/'Sources-link'; alias.symlink_to(self.source, target_is_directory=True)
        for path in [link, alias/source.name]:
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                self.run_copy(path)
        self.assertEqual(list(self.a.iterdir()), [])

    def test_destination_symlink_or_symlinked_parent_is_rejected(self):
        source = self.source_file()
        alias = self.root/'Alias'; alias.symlink_to(self.a, target_is_directory=True)
        self.c.projects['work-a']['folder'] = str(alias)
        proof = imports.binding(self.c)
        with self.assertRaises((ValueError, OSError)): self.run_copy(source, proof=proof)
        self.assertEqual(list(self.a.iterdir()), [])

    def test_directory_fifo_and_traversal_source_are_rejected_without_blocking(self):
        fifo = self.source/'fifo'; os.mkfifo(fifo)
        source = self.source_file()
        for path in [self.source, fifo, str(self.source)+'/../Sources/'+source.name]:
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                self.run_copy(path)
        self.assertEqual(list(self.a.iterdir()), [])

    def test_invalid_second_source_is_prevalidated_before_any_copy(self):
        source = self.source_file()
        with self.assertRaises((ValueError, OSError)):
            self.run_copy(source, self.source/'absent.txt')
        self.assertEqual(list(self.a.iterdir()), [])

    def test_batch_count_and_sizes_are_bounded(self):
        source = self.source_file(content=b'1234')
        for paths in [[], [source]*51]:
            with self.assertRaises(ValueError): self.run_copy(*paths)
        with patch.object(imports, 'MAX_FILE_BYTES', 3):
            with self.assertRaises(ValueError): self.run_copy(source)
        with patch.object(imports, 'MAX_TOTAL_BYTES', 6):
            with self.assertRaises(ValueError): self.run_copy(source, source)
        self.assertEqual(list(self.a.iterdir()), [])

    def test_source_mutation_during_copy_rejects_partial_file_and_cleans_temp(self):
        source = self.source_file()
        original = imports.os.read
        def read(fd, size):
            value = original(fd, size)
            if value:
                source.write_bytes(b'Changed')
            return value
        with patch.object(imports.os, 'read', side_effect=read):
            with self.assertRaises(ValueError): self.run_copy(source)
        self.assertEqual(list(self.a.iterdir()), [])
        self.clean()

    def test_destination_path_replacement_cannot_redirect_copy(self):
        source = self.source_file()
        original = imports.os.read
        changed = False
        moved = self.root/'Moved'
        def read(fd, size):
            nonlocal changed
            value = original(fd, size)
            if value and not changed:
                changed = True
                self.a.rename(moved)
                self.a.mkdir()
            return value
        with patch.object(imports.os, 'read', side_effect=read):
            with self.assertRaises(ValueError): self.run_copy(source)
        self.assertEqual(list(self.a.iterdir()), [])
        self.assertEqual(list(moved.iterdir()), [])

    def test_mid_batch_disk_failure_reports_completed_copies_without_source_paths(self):
        first = self.source_file('first.txt', b'First content')
        second = self.source_file('second.txt', b'Second content')
        original = imports._rename_at
        def rename(root, source, target, flag):
            if target == second.name:
                raise OSError('private/source/path must not appear')
            return original(root, source, target, flag)
        with patch.object(imports, '_rename_at', side_effect=rename):
            with self.assertRaises(imports.ImportFailure) as raised:
                self.run_copy(first, second)
        self.assertEqual(raised.exception.copied, ['first.txt'])
        self.assertEqual(raised.exception.count, 1)
        self.assertNotIn('private/source/path', str(raised.exception))
        self.assertEqual((self.a/'first.txt').read_bytes(), first.read_bytes())
        self.assertFalse((self.a/'second.txt').exists())
        self.assertEqual(second.read_bytes(), b'Second content')
        self.clean()

    def test_mid_batch_source_mutation_reports_prior_success_and_cleans_partial_copy(self):
        first = self.source_file('first.txt', b'First content')
        second = self.source_file('second.txt', b'Second content')
        original = imports.os.read
        def read(fd, size):
            value = original(fd, size)
            if value == b'Second content':
                second.write_bytes(b'Changed')
            return value
        with patch.object(imports.os, 'read', side_effect=read):
            with self.assertRaises(imports.ImportFailure) as raised:
                self.run_copy(first, second)
        self.assertEqual(raised.exception.copied, ['first.txt'])
        self.assertEqual((self.a/'first.txt').read_bytes(), first.read_bytes())
        self.assertFalse((self.a/'second.txt').exists())
        self.clean()

    def test_listing_is_bounded_regular_filenames_only_and_contains_no_content(self):
        (self.a/'first.txt').write_bytes(b'Secret body')
        (self.a/'folder').mkdir()
        (self.a/'symlink').symlink_to(self.a/'first.txt')
        (self.a/'.vibez-import-hidden').write_bytes(b'Temporary')
        self.assertEqual(imports.listing(self.c), [{'name': 'first.txt'}, {'name': 'folder', 'kind': 'directory'}])
        for index in range(110): (self.a/f'{index}.txt').touch()
        self.assertEqual(len(imports.listing(self.c)), 100)


class PlannedImportTests(unittest.TestCase):
    setUp = ProjectImportTests.setUp
    tearDown = ProjectImportTests.tearDown
    source_file = ProjectImportTests.source_file

    def manager(self):
        if not hasattr(self, '_manager'): self._manager = imports.Manager(self.c)
        return self._manager

    def prepare(self, *paths):
        return self.manager().prepare('work-a', self.proof, [str(p) for p in paths])

    def resolve(self, plan, action):
        return self.manager().resolve(plan['plan_id'], {item['id']: action for item in plan['items']})

    def folder(self, name='Project.v1'):
        path = self.source/name; path.mkdir()
        (path/'nested').mkdir(); (path/'empty').mkdir()
        (path/'nested'/'binary.bin').write_bytes(b'Binary\x00\xffsource')
        (path/'README.md').write_bytes(b'Source project')
        return path

    def no_temporary(self):
        self.assertFalse(any(self.a.glob('.vibez-import-*')))

    def test_conflict_preview_defers_entire_batch_and_contains_only_safe_metadata(self):
        existing = self.source_file('report.txt', b'New body never disclosed')
        fresh = self.source_file('fresh.txt', b'Fresh')
        (self.a/existing.name).write_bytes(b'Existing')
        result = self.prepare(existing, fresh)
        self.assertEqual(result['status'], 'conflicts'); self.assertEqual(result['count'], 0)
        self.assertEqual(list(self.a.iterdir()), [self.a/existing.name])
        self.assertEqual(set(result['items'][0]), {'id', 'name', 'source_kind', 'target_kind', 'can_replace'})
        self.assertRegex(result['plan_id'], r'^[A-Za-z0-9_-]{32}$')
        self.assertRegex(result['items'][0]['id'], r'^[0-9a-f]{24}$')
        self.assertNotIn(str(self.source), json.dumps(result))
        self.assertNotIn('New body never disclosed', json.dumps(result))
        self.no_temporary()
        done = self.resolve(result, 'skip')
        self.assertEqual(done['names'], ['fresh.txt']); self.assertEqual(done['skipped'], 1)
        self.assertEqual((self.a/existing.name).read_bytes(), b'Existing')

    def test_file_replace_requires_choice_and_preserves_source(self):
        source = self.source_file('report.txt', b'New body')
        (self.a/source.name).write_bytes(b'Old body')
        result = self.prepare(source)
        self.assertEqual((self.a/source.name).read_bytes(), b'Old body')
        self.assertTrue(result['items'][0]['can_replace'])
        done = self.resolve(result, 'replace')
        self.assertEqual(done['count'], 1); self.assertEqual(done['names'], ['report.txt'])
        self.assertEqual((self.a/source.name).read_bytes(), b'New body')
        self.assertEqual(source.read_bytes(), b'New body')
        self.no_temporary()

    def test_file_keep_both_numbers_before_extension(self):
        source = self.source_file('report.txt')
        (self.a/source.name).write_bytes(b'Original')
        done = self.resolve(self.prepare(source), 'keep_both')
        self.assertEqual(done['names'], ['report (2).txt'])
        self.assertEqual((self.a/source.name).read_bytes(), b'Original')

    def test_directory_copy_is_recursive_binary_and_preserves_empty_folders(self):
        source = self.folder()
        done = self.prepare(source)
        self.assertEqual(done['status'], 'done'); self.assertEqual(done['names'], ['Project.v1'])
        self.assertEqual((self.a/source.name/'nested'/'binary.bin').read_bytes(), b'Binary\x00\xffsource')
        self.assertTrue((self.a/source.name/'empty').is_dir())
        self.assertEqual((source/'README.md').read_bytes(), b'Source project')
        self.assertIn({'name': 'Project.v1', 'kind': 'directory'}, imports.listing(self.c))

    def test_planned_files_folders_and_conflict_choices_do_not_require_hardlinks(self):
        source = self.source_file('portal.txt', b'New file')
        folder = self.folder('PortalFolder')
        with patch.object(imports.os, 'link', side_effect=OSError(errno.EPERM, 'No portal hardlinks')) as link:
            first = self.prepare(source, folder)
            self.assertEqual(first['status'], 'done')
            self.assertEqual(first['names'], ['portal.txt', 'PortalFolder'])
            kept = self.resolve(self.prepare(source, folder), 'keep_both')
            self.assertEqual(kept['names'], ['portal (2).txt', 'PortalFolder (2)'])
            (self.a/source.name).write_bytes(b'Existing edited file')
            skipped = self.resolve(self.prepare(source), 'skip')
            self.assertEqual(skipped['skipped'], 1)
            self.assertEqual((self.a/source.name).read_bytes(), b'Existing edited file')
            replaced = self.resolve(self.prepare(source), 'replace')
            self.assertEqual(replaced['names'], ['portal.txt'])
            link.assert_not_called()
        self.assertEqual((self.a/source.name).read_bytes(), b'New file')
        self.assertEqual((self.a/'PortalFolder (2)'/'nested'/'binary.bin').read_bytes(), b'Binary\x00\xffsource')
        self.assertEqual(source.read_bytes(), b'New file')
        self.no_temporary()

    def test_directory_keep_both_numbers_whole_name(self):
        source = self.folder()
        (self.a/source.name).mkdir(); (self.a/source.name/'existing').touch()
        done = self.resolve(self.prepare(source), 'keep_both')
        self.assertEqual(done['names'], ['Project.v1 (2)'])
        self.assertTrue((self.a/source.name/'existing').exists())
        self.assertTrue((self.a/'Project.v1 (2)'/'README.md').exists())

    def test_directory_replace_replaces_entire_tree_without_merging(self):
        source = self.folder()
        (self.a/source.name).mkdir(); (self.a/source.name/'old-only.txt').write_bytes(b'Old')
        done = self.resolve(self.prepare(source), 'replace')
        self.assertEqual(done['status'], 'done')
        self.assertFalse((self.a/source.name/'old-only.txt').exists())
        self.assertEqual((self.a/source.name/'README.md').read_bytes(), b'Source project')
        self.assertEqual((source/'README.md').read_bytes(), b'Source project')
        self.no_temporary()

    def test_type_conflicts_replace_file_with_directory_and_directory_with_file(self):
        source = self.folder('same')
        (self.a/'same').write_bytes(b'Existing file')
        first = self.prepare(source)
        self.assertEqual(first['items'][0]['target_kind'], 'file')
        self.resolve(first, 'replace')
        self.assertTrue((self.a/'same').is_dir())
        other = self.source_file('same-file', b'Replacement file')
        (self.a/'same-file').mkdir(); (self.a/'same-file'/'old').touch()
        second = self.prepare(other)
        self.assertEqual(second['items'][0]['target_kind'], 'directory')
        self.resolve(second, 'replace')
        self.assertEqual((self.a/'same-file').read_bytes(), b'Replacement file')

    def test_symlink_and_special_destinations_cannot_be_replaced(self):
        source = self.source_file('linked.txt')
        outside = self.root/'outside'; outside.write_bytes(b'Original')
        (self.a/source.name).symlink_to(outside)
        result = self.prepare(source)
        self.assertFalse(result['items'][0]['can_replace'])
        with self.assertRaises(ValueError): self.resolve(result, 'replace')
        self.resolve(result, 'keep_both')
        self.assertEqual(outside.read_bytes(), b'Original')
        fifo_source = self.source_file('fifo')
        os.mkfifo(self.a/'fifo')
        result = self.prepare(fifo_source)
        self.assertFalse(result['items'][0]['can_replace'])
        self.resolve(result, 'skip')

    def test_source_same_file_or_inside_replaced_target_cannot_be_replaced(self):
        same = self.a/'same.txt'; same.write_bytes(b'Original')
        result = self.prepare(same)
        self.assertFalse(result['items'][0]['can_replace'])
        self.resolve(result, 'keep_both')
        self.assertEqual(same.read_bytes(), b'Original')
        target = self.a/'nested.txt'; target.mkdir()
        inside = target/'nested.txt'; inside.write_bytes(b'Nested source')
        result = self.prepare(inside)
        self.assertFalse(result['items'][0]['can_replace'])
        self.resolve(result, 'keep_both')
        self.assertEqual(inside.read_bytes(), b'Nested source')

    def test_cross_item_directory_replace_cannot_erase_another_selected_source_file(self):
        original_folder = self.a/'A'; original_folder.mkdir()
        original_source = original_folder/'inside.txt'; original_source.write_bytes(b'Original source file')
        incoming_folder = self.source/'A'; incoming_folder.mkdir()
        (incoming_folder/'replacement.txt').write_bytes(b'Incoming folder')
        for paths in [(original_source, incoming_folder), (incoming_folder, original_source)]:
            with self.subTest(order=[p.name for p in paths]):
                plan = self.prepare(*paths)
                conflict = next(item for item in plan['items'] if item['name'] == 'A')
                self.assertFalse(conflict['can_replace'])
                with self.assertRaises(ValueError): self.resolve(plan, 'replace')
                self.assertEqual(original_source.read_bytes(), b'Original source file')
                self.manager().cancel(plan['plan_id'])
        plan = self.prepare(original_source, incoming_folder)
        done = self.resolve(plan, 'keep_both')
        self.assertEqual(done['names'], ['inside.txt', 'A (2)'])
        self.assertEqual(original_source.read_bytes(), b'Original source file')
        self.assertEqual((self.a/'inside.txt').read_bytes(), b'Original source file')
        self.assertEqual((self.a/'A (2)'/'replacement.txt').read_bytes(), b'Incoming folder')

    def test_cross_item_directory_replace_cannot_erase_another_selected_source_directory(self):
        original_folder = self.a/'A'; original_folder.mkdir()
        original_source = original_folder/'Sub'; original_source.mkdir()
        (original_source/'original.bin').write_bytes(b'Original\x00source directory')
        incoming_folder = self.source/'A'; incoming_folder.mkdir()
        (incoming_folder/'replacement.txt').write_bytes(b'Incoming folder')
        for paths in [(original_source, incoming_folder), (incoming_folder, original_source)]:
            with self.subTest(order=[p.name for p in paths]):
                plan = self.prepare(*paths)
                conflict = next(item for item in plan['items'] if item['name'] == 'A')
                self.assertFalse(conflict['can_replace'])
                with self.assertRaises(ValueError): self.resolve(plan, 'replace')
                self.assertEqual((original_source/'original.bin').read_bytes(), b'Original\x00source directory')
                self.manager().cancel(plan['plan_id'])
        plan = self.prepare(original_source, incoming_folder)
        done = self.resolve(plan, 'keep_both')
        self.assertEqual(done['names'], ['Sub', 'A (2)'])
        self.assertEqual((original_source/'original.bin').read_bytes(), b'Original\x00source directory')
        self.assertEqual((self.a/'Sub'/'original.bin').read_bytes(), b'Original\x00source directory')
        self.assertEqual((self.a/'A (2)'/'replacement.txt').read_bytes(), b'Incoming folder')

    def test_source_unsafe_trees_and_destination_inside_source_are_rejected(self):
        source = self.folder()
        (source/'linked').symlink_to(source/'README.md')
        with self.assertRaises(ValueError): self.prepare(source)
        (source/'linked').unlink(); os.mkfifo(source/'pipe')
        with self.assertRaises(ValueError): self.prepare(source)
        (source/'pipe').unlink()
        self.c.projects['work-a']['folder'] = str(source/'empty')
        proof = imports.binding(self.c)
        with self.assertRaises(ValueError): self.manager().prepare('work-a', proof, [str(source)])
        self.assertEqual(list((source/'empty').iterdir()), [])

    def test_cancel_expired_and_consumed_plans_cannot_copy(self):
        source = self.source_file(); (self.a/source.name).write_bytes(b'Old')
        plan = self.prepare(source)
        self.assertTrue(self.manager().cancel(plan['plan_id'])['cancelled'])
        with self.assertRaises(ValueError): self.resolve(plan, 'replace')
        plan = self.prepare(source)
        self.manager().plans[plan['plan_id']]['created'] -= 301
        with self.assertRaises(ValueError): self.resolve(plan, 'replace')
        plan = self.prepare(source); self.resolve(plan, 'skip')
        with self.assertRaises(ValueError): self.resolve(plan, 'replace')
        self.assertEqual((self.a/source.name).read_bytes(), b'Old')

    def test_choices_are_exact_and_nonreplaceable_targets_reject_replace(self):
        source = self.source_file(); (self.a/source.name).write_bytes(b'Old')
        plan = self.prepare(source)
        for choices in [{}, {'unknown': 'replace'}, {plan['items'][0]['id']: '../replace'}, []]:
            with self.assertRaises(ValueError): self.manager().resolve(plan['plan_id'], choices)
        self.assertEqual((self.a/source.name).read_bytes(), b'Old')

    def test_project_folder_and_destination_root_changes_invalidate_plan(self):
        source = self.source_file(); (self.a/source.name).write_bytes(b'Old')
        plan = self.prepare(source); self.c.active = {'id': 'code-a'}
        with self.assertRaises(ValueError): self.resolve(plan, 'replace')
        self.c.active = {'id': 'work-a'}
        plan = self.prepare(source); self.c.projects['work-a']['token'] = 'Changed'
        with self.assertRaises(ValueError): self.resolve(plan, 'replace')
        self.c.projects['work-a']['token'] = 'fixture-A'
        plan = self.prepare(source)
        moved = self.root/'OldAlpha'; self.a.rename(moved); self.a.mkdir()
        with self.assertRaises(ValueError): self.resolve(plan, 'replace')
        self.assertEqual((moved/source.name).read_bytes(), b'Old')
        self.assertEqual(list(self.a.iterdir()), [])

    def test_source_and_existing_destination_changes_require_another_confirmation(self):
        source = self.source_file(); (self.a/source.name).write_bytes(b'Old')
        plan = self.prepare(source); source.write_bytes(b'Changed source')
        changed = self.resolve(plan, 'replace')
        self.assertEqual(changed['status'], 'changed'); self.assertTrue(changed['confirm_required'])
        self.assertEqual((self.a/source.name).read_bytes(), b'Old')
        (self.a/source.name).write_bytes(b'Changed destination')
        changed_again = self.resolve(changed, 'replace')
        self.assertEqual(changed_again['status'], 'changed')
        self.assertEqual((self.a/source.name).read_bytes(), b'Changed destination')
        self.resolve(changed_again, 'replace')
        self.assertEqual((self.a/source.name).read_bytes(), b'Changed source')

    def test_new_collision_during_staging_reprompts_without_overwriting(self):
        source = self.source_file()
        original = imports._stage_tree
        def stage(*args):
            temporary = original(*args)
            (self.a/source.name).write_bytes(b'Arrived during copy')
            return temporary
        with patch.object(imports, '_stage_tree', side_effect=stage): result = self.prepare(source)
        self.assertEqual(result['status'], 'changed'); self.assertTrue(result['items'])
        self.assertEqual((self.a/source.name).read_bytes(), b'Arrived during copy')
        self.no_temporary()

    def test_new_collision_at_atomic_commit_reprompts_without_overwriting(self):
        source = self.source_file()
        original = imports._rename_at
        def rename(root, temporary, target, flag):
            if flag == 1: (self.a/target).write_bytes(b'Arrived at commit')
            return original(root, temporary, target, flag)
        with patch.object(imports, '_rename_at', side_effect=rename): result = self.prepare(source)
        self.assertEqual(result['status'], 'changed')
        self.assertEqual((self.a/source.name).read_bytes(), b'Arrived at commit')
        self.no_temporary()

    def test_source_change_without_conflict_requires_explicit_empty_choice_confirmation(self):
        source = self.source_file('report.txt', b'Before')
        original = imports._stage_tree
        def stage(*args):
            temporary = original(*args)
            source.write_bytes(b'Changed after staging')
            return temporary
        with patch.object(imports, '_stage_tree', side_effect=stage): result = self.prepare(source)
        self.assertEqual(result['status'], 'changed')
        self.assertEqual(result['items'], []); self.assertTrue(result['confirm_required'])
        self.assertFalse((self.a/source.name).exists())
        self.no_temporary()
        done = self.manager().resolve(result['plan_id'], {})
        self.assertEqual(done['status'], 'done')
        self.assertEqual((self.a/source.name).read_bytes(), b'Changed after staging')

    def test_missing_source_error_contains_no_path_and_leaves_destination_unchanged(self):
        with self.assertRaises(imports.ImportFailure) as raised:
            self.prepare(self.source/'missing-private-name.txt')
        self.assertNotIn('missing-private-name', str(raised.exception))
        self.assertEqual(raised.exception.copied, [])
        self.assertEqual(list(self.a.iterdir()), [])

    def test_replacement_race_rolls_back_and_preserves_changed_destination(self):
        source = self.source_file(); (self.a/source.name).write_bytes(b'Old')
        plan = self.prepare(source); original = imports._rename_at; raced = False
        def rename(root, temporary, target, flag):
            nonlocal raced
            if flag == 2 and not raced:
                raced = True; (self.a/target).write_bytes(b'Concurrent destination edit')
            return original(root, temporary, target, flag)
        with patch.object(imports, '_rename_at', side_effect=rename): result = self.resolve(plan, 'replace')
        self.assertEqual(result['status'], 'changed')
        self.assertEqual((self.a/source.name).read_bytes(), b'Concurrent destination edit')
        self.no_temporary()

    def test_replacement_directory_race_preserves_new_nested_file(self):
        source = self.folder(); target = self.a/source.name; target.mkdir()
        (target/'Old.txt').write_bytes(b'Old')
        plan = self.prepare(source); original = imports._rename_at; raced = False
        def rename(root, temporary, name, flag):
            nonlocal raced
            if flag == 2 and not raced:
                raced = True; (target/'Arrived.txt').write_bytes(b'Concurrent content')
            return original(root, temporary, name, flag)
        with patch.object(imports, '_rename_at', side_effect=rename): result = self.resolve(plan, 'replace')
        self.assertEqual(result['status'], 'changed')
        self.assertEqual((target/'Arrived.txt').read_bytes(), b'Concurrent content')
        self.assertEqual((target/'Old.txt').read_bytes(), b'Old')
        self.no_temporary()

    def test_replacement_hash_detects_same_size_edit_with_restored_mtime(self):
        source = self.source_file('report.txt', b'NEW123')
        target = self.a/source.name; target.write_bytes(b'OLD123')
        plan = self.prepare(source); original = imports._rename_at; raced = False
        before = target.stat()
        def rename(root, temporary, name, flag):
            nonlocal raced
            if flag == 2 and not raced:
                raced = True
                target.write_bytes(b'EDIT!!')
                os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
            return original(root, temporary, name, flag)
        with patch.object(imports, '_rename_at', side_effect=rename): result = self.resolve(plan, 'replace')
        self.assertEqual(result['status'], 'changed')
        self.assertEqual(target.read_bytes(), b'EDIT!!')
        self.assertEqual(source.read_bytes(), b'NEW123')
        self.no_temporary()

    def test_duplicate_batch_names_need_choice_and_do_not_overwrite_each_other(self):
        first = self.source_file('same.txt', b'First')
        sub = self.source/'sub'; sub.mkdir(); second = sub/'same.txt'; second.write_bytes(b'Second')
        plan = self.prepare(first, second)
        self.assertEqual(len(plan['items']), 1); self.assertFalse(plan['items'][0]['can_replace'])
        done = self.resolve(plan, 'keep_both')
        self.assertEqual(done['names'], ['same.txt', 'same (2).txt'])
        self.assertEqual((self.a/'same.txt').read_bytes(), b'First')
        self.assertEqual((self.a/'same (2).txt').read_bytes(), b'Second')

    def test_missing_renameat2_fails_safe_without_overwrite(self):
        source = self.source_file(); (self.a/source.name).write_bytes(b'Old')
        plan = self.prepare(source)
        with patch.object(imports.ctypes, 'CDLL', return_value=object()):
            with self.assertRaises(ValueError): self.resolve(plan, 'replace')
        self.assertEqual((self.a/source.name).read_bytes(), b'Old')
        self.no_temporary()

    def test_reprompt_carries_completed_names_and_prior_skips_into_final_result(self):
        skipped = self.source_file('skip.txt', b'Skipped source')
        first = self.source_file('first.txt', b'First')
        second = self.source_file('second.txt', b'Second')
        (self.a/skipped.name).write_bytes(b'Existing skipped')
        plan = self.prepare(skipped, first, second)
        original = imports._rename_at
        def rename(root, temporary, target, flag):
            if target == second.name and flag == 1:
                (self.a/target).write_bytes(b'Concurrent destination')
            return original(root, temporary, target, flag)
        with patch.object(imports, '_rename_at', side_effect=rename): changed = self.resolve(plan, 'skip')
        self.assertEqual(changed['status'], 'changed')
        self.assertEqual(changed['names'], ['first.txt']); self.assertEqual(changed['count'], 1)
        self.assertEqual(changed['skipped'], 1)
        (self.a/'second.txt').write_bytes(b'Another concurrent destination')
        changed_again = self.resolve(changed, 'keep_both')
        self.assertEqual(changed_again['status'], 'changed')
        self.assertEqual(changed_again['count'], 1); self.assertEqual(changed_again['skipped'], 1)
        changed = changed_again
        result = self.resolve(changed, 'keep_both')
        self.assertEqual(result['names'], ['first.txt', 'second (2).txt'])
        self.assertEqual(result['count'], 2); self.assertEqual(result['skipped'], 1)
        self.assertEqual((self.a/'second.txt').read_bytes(), b'Another concurrent destination')

    def test_cancel_reprompt_preserves_completed_names_and_counts_only_remaining_as_skipped(self):
        first = self.source_file('first.txt', b'First')
        second = self.source_file('second.txt', b'Second')
        original = imports._rename_at
        def rename(root, temporary, target, flag):
            if target == second.name and flag == 1:
                (self.a/target).write_bytes(b'Concurrent destination')
            return original(root, temporary, target, flag)
        with patch.object(imports, '_rename_at', side_effect=rename): changed = self.prepare(first, second)
        cancelled = self.manager().cancel(changed['plan_id'])
        self.assertTrue(cancelled['cancelled'])
        self.assertEqual(cancelled['names'], ['first.txt']); self.assertEqual(cancelled['count'], 1)
        self.assertEqual(cancelled['skipped'], 1)
        self.assertEqual((self.a/'first.txt').read_bytes(), b'First')

    def test_partial_batch_failure_reports_only_completed_copies(self):
        first = self.source_file('first.txt', b'First')
        second = self.source_file('second.txt', b'Second')
        original = imports._rename_at
        def rename(root, temporary, target, flag):
            if target == second.name: raise OSError('private/source/path')
            return original(root, temporary, target, flag)
        with patch.object(imports, '_rename_at', side_effect=rename):
            with self.assertRaises(imports.ImportFailure) as raised: self.prepare(first, second)
        self.assertEqual(raised.exception.copied, ['first.txt'])
        self.assertNotIn('private/source/path', str(raised.exception))
        self.assertEqual((self.a/first.name).read_bytes(), b'First')
        self.assertFalse((self.a/second.name).exists())
        self.no_temporary()

    def test_partial_batch_after_successful_replace_removes_only_verified_old_backup(self):
        first = self.source_file('first.txt', b'New first')
        second = self.source_file('second.txt', b'Second')
        (self.a/first.name).write_bytes(b'Old first')
        plan = self.prepare(first, second); original = imports._rename_at
        def rename(root, temporary, target, flag):
            if target == second.name: raise OSError('Controlled disk failure')
            return original(root, temporary, target, flag)
        with patch.object(imports, '_rename_at', side_effect=rename):
            with self.assertRaises(imports.ImportFailure) as raised: self.resolve(plan, 'replace')
        self.assertEqual(raised.exception.copied, ['first.txt'])
        self.assertEqual(raised.exception.backups, [])
        self.assertEqual((self.a/first.name).read_bytes(), b'New first')
        self.assertEqual(first.read_bytes(), b'New first')
        self.assertFalse((self.a/second.name).exists())
        self.no_temporary()

    def test_uncertain_concurrent_edits_retain_recovery_copy_without_deleting_either_edit(self):
        source = self.source_file('report.txt', b'Source')
        target = self.a/source.name; target.write_bytes(b'Original')
        plan = self.prepare(source); original = imports._rename_at; raced = False
        def rename(root, temporary, name, flag):
            nonlocal raced
            if flag == 2 and not raced:
                raced = True
                target.write_bytes(b'Concurrent old edit')
                original(root, temporary, name, flag)
                target.write_bytes(b'Concurrent new edit')
                return
            return original(root, temporary, name, flag)
        with patch.object(imports, '_rename_at', side_effect=rename): result = self.resolve(plan, 'replace')
        self.assertEqual(result['status'], 'changed')
        self.assertEqual(target.read_bytes(), b'Concurrent new edit')
        self.assertEqual(source.read_bytes(), b'Source')
        self.assertEqual(len(result['backups']), 1)
        backup = result['backups'][0]
        self.assertTrue(backup.startswith('.vibez-backup-'))
        self.assertEqual((self.a/backup).read_bytes(), b'Concurrent old edit')
        self.no_temporary()

    def test_readonly_source_tree_copies_and_cleans_without_changing_source_modes(self):
        source = self.folder()
        (source/'nested').chmod(0o500); source.chmod(0o500)
        try:
            result = self.prepare(source)
            self.assertEqual(result['status'], 'done')
            self.assertEqual(source.stat().st_mode & 0o777, 0o500)
            (self.a/source.name).chmod(0o700)
            plan = self.prepare(source)
            self.resolve(plan, 'replace')
            self.assertEqual(source.stat().st_mode & 0o777, 0o500)
            self.no_temporary()
        finally:
            source.chmod(0o700); (source/'nested').chmod(0o700)
            if (self.a/source.name).is_dir():
                (self.a/source.name).chmod(0o700)
                (self.a/source.name/'nested').chmod(0o700)


class NoAccountAccess:
    def __init__(self): self.calls = 0
    def authenticate(self, *_):
        self.calls += 1
        raise AssertionError('File copying must not request an account')


class ProjectImportDispatchTests(unittest.TestCase):
    A = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'
    B = 'code-' + A

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='vibez-file-import-dispatch-')
        self.root = Path(self.tmp.name)
        self.events = []
        self.auth = NoAccountAccess()
        self.network_calls = 0
        def unexpected_api(*_):
            self.network_calls += 1
            raise AssertionError('Local file imports must not call Mistral')
        self.e = app.StandaloneEngine(self.events.append, self.root/'private', auth=self.auth,
                                      auto_api_factory=unexpected_api)
        self.a = self.root/'Alpha'; self.a.mkdir()
        self.b = self.root/'Beta'; self.b.mkdir()
        self.sources = self.root/'Sources'; self.sources.mkdir()

    def tearDown(self):
        self.e.close()
        self.assertEqual(self.auth.calls, 0)
        self.assertEqual(self.network_calls, 0)
        self.tmp.cleanup()

    def select(self, key, folder=None):
        self.e.dispatch({'action': 'web_context', 'project': {'id': key, 'name': 'Fixture project'}})
        if folder is not None:
            self.e.dispatch({'action': 'web_link', 'project_id': key, 'path': str(folder)})
        return self.e.web.snapshot()['import_binding']

    def copy(self, key, binding, *paths):
        before = len(self.events)
        self.e.dispatch({'action': 'web_import', 'project_id': key, 'binding': binding,
                         'paths': [str(p) for p in paths]})
        results = [event for event in self.events[before:] if event['type'] in ('web_import_result', 'web_import_conflicts')]
        self.assertEqual(len(results), 1)
        self.assertEqual(self.events[-1]['type'], 'web_connector')
        return results[0]

    def resolve_plan(self, plan, action='keep_both', cancel=False):
        before = len(self.events)
        self.e.dispatch({'action': 'web_import_cancel' if cancel else 'web_import_resolve',
                         'project_id': plan['project_id'], 'binding': plan['binding'],
                         'plan_id': plan['plan_id'], 'choices': {item['id']: action for item in plan['items']}})
        results = [event for event in self.events[before:] if event['type'] in ('web_import_result', 'web_import_conflicts')]
        self.assertEqual(len(results), 1)
        return results[0]

    def test_dispatch_copies_binary_locally_without_signin_or_connection(self):
        source = self.sources/'document.bin'; source.write_bytes(b'Binary\x00\xfffixture contents')
        binding = self.select(self.A, self.a)
        self.assertFalse(self.e.web.snapshot()['enabled'])
        result = self.copy(self.A, binding, source)
        self.assertEqual(result, {'type': 'web_import_result', 'status': 'done', 'project_id': self.A,
                                 'binding': binding, 'names': ['document.bin'], 'count': 1, 'skipped': 0})
        self.assertEqual((self.a/source.name).read_bytes(), source.read_bytes())
        self.assertFalse(self.e.web.snapshot()['enabled'])

    def failed_copy_clears_busy(self, binding, source):
        busy = {'value': True}
        before = len(self.events)
        def output(event):
            self.events.append(event)
            if event['type'] == 'web_import_result' and event.get('project_id') == self.A and event.get('binding') == binding:
                busy['value'] = False
        self.e.external_output = output
        try: result = self.copy(self.A, binding, source)
        finally: self.e.external_output = self.events.append
        results = [event for event in self.events[before:] if event['type'] == 'web_import_result']
        self.assertEqual(len(results), 1)
        self.assertFalse(any(event['type'] == 'error' for event in self.events[before:]))
        self.assertEqual(result['count'], 0); self.assertEqual(result['names'], [])
        self.assertIsInstance(result.get('error'), str); self.assertTrue(result['error'])
        self.assertFalse(busy['value'])
        self.assertEqual(list(self.a.iterdir()), [])
        return result

    def test_dispatch_deleted_source_returns_one_nonempty_error_result_and_clears_busy(self):
        source = self.sources/'deleted-private-source.txt'; source.write_bytes(b'Before deletion')
        binding = self.select(self.A, self.a)
        source.unlink()
        result = self.failed_copy_clears_busy(binding, source)
        self.assertNotIn(str(source), result['error'])
        self.assertNotIn('deleted-private-source', result['error'])

    def test_dispatch_source_mutating_initial_hash_returns_nonempty_error_and_clears_busy(self):
        source = self.sources/'changing-private-source.txt'; source.write_bytes(b'Original source')
        binding = self.select(self.A, self.a)
        engine_imports = self.e.web.import_files.__func__.__globals__['imports']
        original = engine_imports.os.read; changed = False
        def read(fd, size):
            nonlocal changed
            value = original(fd, size)
            if value and not changed and os.path.samefile('/proc/self/fd/'+str(fd), source):
                changed = True
                source.write_bytes(b'Changed during the initial hash')
            return value
        with patch.object(engine_imports.os, 'read', side_effect=read):
            result = self.failed_copy_clears_busy(binding, source)
        self.assertTrue(changed)
        self.assertNotIn(str(source), result['error'])
        self.assertNotIn('changing-private-source', result['error'])

    def test_dispatch_keeps_project_namespace_and_collision_sources_separate(self):
        source = self.sources/'README.md'; source.write_bytes(b'Fixture source')
        (self.a/source.name).write_bytes(b'Original Alpha')
        binding_a = self.select(self.A, self.a)
        result_a = self.copy(self.A, binding_a, source)
        self.assertEqual(result_a['type'], 'web_import_conflicts')
        self.assertEqual((self.a/'README.md').read_bytes(), b'Original Alpha')
        self.assertFalse((self.a/'README (2).md').exists())
        result_a = self.resolve_plan(result_a)
        self.assertEqual(result_a['names'], ['README (2).md'])
        binding_b = self.select(self.B, self.b)
        result_b = self.copy(self.B, binding_b, source)
        self.assertEqual(result_b['names'], ['README.md'])
        self.assertEqual((self.a/'README.md').read_bytes(), b'Original Alpha')
        self.assertEqual((self.a/'README (2).md').read_bytes(), b'Fixture source')
        self.assertEqual((self.b/'README.md').read_bytes(), b'Fixture source')
        self.assertEqual(source.read_bytes(), b'Fixture source')

    def test_dispatch_reports_stale_project_or_folder_with_zero_copies(self):
        source = self.sources/'fixture.txt'; source.write_bytes(b'Fixture source')
        binding_a = self.select(self.A, self.a)
        self.select(self.B, self.b)
        result = self.copy(self.A, binding_a, source)
        self.assertEqual(result['count'], 0); self.assertEqual(result['names'], [])
        self.assertTrue(result['error'])
        self.select(self.A, self.b)
        result = self.copy(self.A, binding_a, source)
        self.assertEqual(result['count'], 0); self.assertEqual(result['names'], [])
        self.assertEqual(list(self.a.iterdir()), []); self.assertEqual(list(self.b.iterdir()), [])

    def test_dispatch_without_linked_folder_reports_error_and_empty_snapshot_binding(self):
        source = self.sources/'fixture.txt'; source.write_bytes(b'Fixture source')
        binding = self.select(self.A)
        self.assertEqual(binding, '')
        self.assertEqual(self.e.web.snapshot()['local_files'], [])
        result = self.copy(self.A, binding, source)
        self.assertEqual(result['count'], 0); self.assertEqual(result['names'], [])
        self.assertTrue(result['error'])

    def test_snapshot_lists_only_names_without_content_and_clears_on_project_exit(self):
        (self.a/'fixture.txt').write_text('fixture body never exposed in snapshot')
        binding = self.select(self.A, self.a)
        snapshot = self.e.web.snapshot()
        self.assertEqual(len(binding), 64)
        self.assertEqual(snapshot['local_files'], [{'name': 'fixture.txt'}])
        self.assertNotIn('fixture body never exposed', json.dumps(snapshot))
        self.e.dispatch({'action': 'web_context', 'project': None})
        self.assertEqual(self.e.web.snapshot()['import_binding'], '')
        self.assertEqual(self.e.web.snapshot()['local_files'], [])

    def test_dispatch_reports_partial_disk_failure_with_safe_completed_names_and_count(self):
        first = self.sources/'first.bin'; first.write_bytes(b'First source')
        second = self.sources/'second.bin'; second.write_bytes(b'Second source')
        binding = self.select(self.A, self.a)
        engine_imports = self.e.web.import_files.__func__.__globals__['imports']
        original = engine_imports._rename_at
        def rename(root, source, target, flag):
            if target == 'second.bin':
                raise OSError('private source path must not appear')
            return original(root, source, target, flag)
        with patch.object(engine_imports, '_rename_at', side_effect=rename):
            result = self.copy(self.A, binding, first, second)
        self.assertEqual(result['count'], 1); self.assertEqual(result['names'], ['first.bin'])
        self.assertTrue(result['error'])
        self.assertNotIn('private source path', result['error'])
        self.assertEqual((self.a/'first.bin').read_bytes(), first.read_bytes())
        self.assertFalse((self.a/'second.bin').exists())
        self.assertEqual(first.read_bytes(), b'First source')
        self.assertEqual(second.read_bytes(), b'Second source')
        self.assertFalse(any(self.a.glob('.vibez-import-*')))

    def test_dispatch_skip_replace_and_cancel_respect_explicit_user_choice(self):
        source = self.sources/'report.txt'; source.write_bytes(b'New source')
        target = self.a/source.name; target.write_bytes(b'Original target')
        binding = self.select(self.A, self.a)
        plan = self.copy(self.A, binding, source)
        skipped = self.resolve_plan(plan, 'skip')
        self.assertEqual(skipped['count'], 0); self.assertEqual(skipped['skipped'], 1)
        self.assertEqual(target.read_bytes(), b'Original target')
        plan = self.copy(self.A, binding, source)
        cancelled = self.resolve_plan(plan, cancel=True)
        self.assertTrue(cancelled['cancelled']); self.assertEqual(cancelled['count'], 0)
        self.assertEqual(target.read_bytes(), b'Original target')
        plan = self.copy(self.A, binding, source)
        replaced = self.resolve_plan(plan, 'replace')
        self.assertEqual(replaced['count'], 1)
        self.assertEqual(target.read_bytes(), b'New source')
        self.assertEqual(source.read_bytes(), b'New source')

    def test_dispatch_directory_replacement_has_no_merge_or_source_changes(self):
        source = self.sources/'Folder'; source.mkdir()
        (source/'nested').mkdir(); (source/'nested'/'new.bin').write_bytes(b'Binary\x00\xff')
        target = self.a/source.name; target.mkdir(); (target/'old.txt').touch()
        binding = self.select(self.A, self.a)
        plan = self.copy(self.A, binding, source)
        self.assertEqual(plan['type'], 'web_import_conflicts')
        self.assertEqual(plan['items'][0]['source_kind'], 'directory')
        result = self.resolve_plan(plan, 'replace')
        self.assertEqual(result['count'], 1)
        self.assertFalse((target/'old.txt').exists())
        self.assertEqual((target/'nested'/'new.bin').read_bytes(), b'Binary\x00\xff')
        self.assertEqual((source/'nested'/'new.bin').read_bytes(), b'Binary\x00\xff')

    def test_dispatch_project_switch_blocks_pending_conflict_resolution(self):
        source = self.sources/'report.txt'; source.write_bytes(b'New source')
        target = self.a/source.name; target.write_bytes(b'Original target')
        binding = self.select(self.A, self.a)
        plan = self.copy(self.A, binding, source)
        self.select(self.B, self.b)
        result = self.resolve_plan(plan, 'replace')
        self.assertTrue(result['error']); self.assertEqual(result['count'], 0)
        self.assertEqual(target.read_bytes(), b'Original target')
        self.assertEqual(list(self.b.iterdir()), [])

    def test_dispatch_target_change_reprompts_before_replacement_and_plan_replay_fails(self):
        source = self.sources/'report.txt'; source.write_bytes(b'New source')
        target = self.a/source.name; target.write_bytes(b'Original target')
        binding = self.select(self.A, self.a)
        plan = self.copy(self.A, binding, source)
        target.write_bytes(b'Changed target')
        refreshed = self.resolve_plan(plan, 'replace')
        self.assertEqual(refreshed['type'], 'web_import_conflicts')
        self.assertEqual(refreshed['status'], 'changed'); self.assertTrue(refreshed['confirm_required'])
        self.assertEqual(target.read_bytes(), b'Changed target')
        final = self.resolve_plan(refreshed, 'replace')
        self.assertEqual(final['count'], 1)
        replayed = self.resolve_plan(refreshed, 'replace')
        self.assertTrue(replayed['error']); self.assertEqual(replayed['count'], 0)


if __name__ == '__main__':
    unittest.main()
