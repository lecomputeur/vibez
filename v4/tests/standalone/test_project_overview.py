"""Project-overview metadata and honest activity, using only temporary folders."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('project_overview_connector', Path(__file__).parents[2]/'backend/web_connector.py')
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)
A = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'
CODE = 'code-' + A
B = 'bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb'


class ProjectOverviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='vibez-project-overview-')
        self.root = Path(self.tmp.name)
        self.events = []
        self.opened = []
        self.c = self.connector()
        self.select(A)

    def tearDown(self):
        for connector in self.opened: connector.close()
        self.tmp.cleanup()

    def connector(self):
        connector = web.Connector(self.events.append, self.root/'private', approval_wait=0)
        self.opened.append(connector)
        return connector

    def select(self, key, name='Same project name'):
        self.c.select({'id': key, 'name': name} if key else None)

    def link(self, key=A):
        self.select(key)
        folder = self.root/('Work' if key == A else 'Code' if key == CODE else 'Other')
        folder.mkdir(exist_ok=True)
        (folder/'fixture.txt').write_text('Original fixture contents')
        self.c.link(key, folder)
        return folder

    def restart(self, key=A):
        self.c.close()
        self.c = self.connector()
        self.select(key)

    def proposal(self, content='Proposed fixture contents'):
        folder = self.link()
        self.c.enabled.add(A)
        ws = self.c.project_workspace(A)
        with self.c.lock:
            self.c.tool(A, {'workspace': ws}, 'read_file', {'path': 'fixture.txt'})
            result = self.c.tool(A, {'workspace': ws}, 'write_file', {'path': 'fixture.txt', 'content': content})
        return folder, result['proposal_id']

    def recent(self):
        return self.c.snapshot()['recent_activity']

    def test_goal_works_before_folder_and_survives_restart_without_linking(self):
        self.assertEqual(self.c.snapshot()['project_goal'], '')
        self.c.set_goal(A, '  Een praktische reisplanner maken.  ')
        self.assertEqual(self.c.snapshot()['project_goal'], 'Een praktische reisplanner maken.')
        self.assertEqual(self.c.projects, {})
        self.assertIsNone(self.c.snapshot()['folder'])
        self.assertIsNone(self.c.server)
        stored = json.loads(self.c.file.read_text())
        self.assertEqual(stored['project_metadata'], {A: {'goal': 'Een praktische reisplanner maken.'}})
        self.assertEqual(stored['projects'], {})
        self.restart()
        self.assertEqual(self.c.snapshot()['project_goal'], 'Een praktische reisplanner maken.')
        self.assertEqual(self.c.projects, {})
        self.assertEqual(self.recent(), [])

    def test_work_code_and_duplicate_names_keep_independent_goals(self):
        self.c.set_goal(A, 'Work goal')
        self.select(CODE); self.c.set_goal(CODE, 'Code goal')
        self.select(B); self.c.set_goal(B, 'Other goal')
        for key, expected in [(A, 'Work goal'), (CODE, 'Code goal'), (B, 'Other goal')]:
            self.select(key)
            self.assertEqual(self.c.snapshot()['project_goal'], expected)
        self.restart(CODE)
        self.assertEqual(self.c.snapshot()['project_goal'], 'Code goal')

    def test_clear_goal_removes_only_its_metadata(self):
        self.link(); self.c.set_goal(A, 'Goal to clear')
        linked = copy.deepcopy(self.c.projects[A])
        self.select(CODE); self.c.set_goal(CODE, 'Keep code goal')
        self.select(A); self.assertEqual(self.c.set_goal(A, '   '), '')
        self.assertEqual(self.c.snapshot()['project_goal'], '')
        self.assertNotIn(A, self.c.project_metadata)
        self.assertEqual(self.c.projects[A], linked)
        self.restart(CODE)
        self.assertEqual(self.c.snapshot()['project_goal'], 'Keep code goal')

    def test_unlink_and_relink_preserve_goal_as_independent_project_metadata(self):
        self.c.set_goal(A, 'Keep this project goal')
        self.link(); self.c.unlink(A)
        self.assertEqual(self.c.snapshot()['project_goal'], 'Keep this project goal')
        self.assertEqual(self.c.projects, {})
        self.restart()
        self.assertEqual(self.c.snapshot()['project_goal'], 'Keep this project goal')
        self.link()
        self.assertEqual(self.c.snapshot()['project_goal'], 'Keep this project goal')

    def test_goal_does_not_change_tokens_approval_pause_or_folder_binding(self):
        self.link()
        self.c.enabled.add(A)
        token = self.c.projects[A]['token']
        self.c.approve_auto(A, (self.c.projects[A]['folder'], token))
        original = copy.deepcopy(self.c.projects[A])
        binding = self.c.snapshot()['import_binding']
        self.c.set_goal(A, 'Metadata without file permissions changes')
        self.assertEqual(self.c.projects[A], original)
        self.assertEqual(self.c.snapshot()['import_binding'], binding)
        self.assertTrue(self.c.auto_approved(A)); self.assertIn(A, self.c.enabled)
        self.c.pause(A); paused = copy.deepcopy(self.c.projects[A])
        self.c.set_goal(A, 'Changed goal while deliberately paused')
        self.assertEqual(self.c.projects[A], paused)
        self.assertTrue(self.c.projects[A]['manually_paused'])
        self.assertNotIn(A, self.c.enabled)
        self.assertEqual(self.recent(), [])

    def test_goal_requires_the_exact_current_valid_project(self):
        self.c.set_goal(A, 'Original')
        before = self.c.file.read_bytes()
        for key in [CODE, B, 'not-a-project', A.upper(), 'code-code-'+A, None]:
            with self.subTest(key=key), self.assertRaises(ValueError): self.c.set_goal(key, 'Wrong project')
        self.select(None)
        with self.assertRaises(ValueError): self.c.set_goal(A, 'No selected project')
        self.assertEqual(self.c.file.read_bytes(), before)
        self.assertEqual(self.c.snapshot()['project_goal'], '')

    def test_goal_has_unicode_character_limit_and_rejects_controls_without_truncation(self):
        goal = '🙂'*240
        self.c.set_goal(A, goal)
        self.assertEqual(self.c.snapshot()['project_goal'], goal)
        for invalid in ['🙂'*241, 'Line\nBreak', 'Line\rBreak', '\tText', 'Null\0Text', 'DEL\x7fText',
                        'NEL\x85Text', 'Line\u2028Break', 'Paragraph\u2029Break', '\ud800', None, 3, {}, []]:
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ValueError): self.c.set_goal(A, invalid)
            self.assertEqual(self.c.snapshot()['project_goal'], goal)
        unicode_goal = '  مشروع مفيد · नमस्ते · café · 👩\u200d💻  '
        self.c.set_goal(A, unicode_goal)
        self.assertEqual(self.c.snapshot()['project_goal'], unicode_goal.strip())

    def test_goal_save_failure_restores_memory_and_atomic_persisted_value(self):
        self.c.set_goal(A, 'Original goal')
        before = self.c.file.read_bytes(); events = len(self.events)
        with patch.object(web.os, 'replace', side_effect=OSError('Controlled atomic save failure')):
            with self.assertRaises(OSError): self.c.set_goal(A, 'Uncommitted replacement')
        self.assertEqual(self.c.snapshot()['project_goal'], 'Original goal')
        self.assertEqual(self.c.file.read_bytes(), before)
        self.assertEqual(len(self.events), events)
        self.restart()
        self.assertEqual(self.c.snapshot()['project_goal'], 'Original goal')

    def test_first_goal_save_failure_does_not_leave_unsaved_metadata(self):
        with patch.object(self.c, 'save', side_effect=OSError('Controlled failure')):
            with self.assertRaises(OSError): self.c.set_goal(A, 'Uncommitted goal')
        self.assertEqual(self.c.project_metadata, {})
        self.assertFalse(self.c.file.exists())
        self.assertEqual(self.c.snapshot()['project_goal'], '')

    def test_legacy_store_without_metadata_still_loads_links_and_default_empty_goal(self):
        self.link(); linked = copy.deepcopy(self.c.projects[A])
        self.c.file.write_text(json.dumps({'projects': self.c.projects}))
        self.restart()
        self.assertEqual(self.c.projects[A], linked)
        self.assertEqual(self.c.snapshot()['project_goal'], '')

    def test_invalid_metadata_is_ignored_without_breaking_existing_links(self):
        self.link(); linked = copy.deepcopy(self.c.projects[A])
        original = {'projects': self.c.projects}
        for metadata in [None, [], 'invalid', {A: {'goal': 'x'*241}}, {A: {'goal': 'New\nline'}},
                         {A: {'goal': 3}}, {A: []}, {'invalid-key': {'goal': 'Wrong'}}]:
            with self.subTest(metadata=metadata):
                self.c.file.write_text(json.dumps({**original, 'project_metadata': metadata}))
                loaded = self.connector()
                self.assertEqual(loaded.projects[A], linked)
                self.assertEqual(loaded.project_metadata, {})

    def test_metadata_count_is_bounded_and_clearing_still_works_at_capacity(self):
        with patch.object(web, 'MAX_PROJECT_METADATA', 2):
            self.c.set_goal(A, 'A goal')
            self.select(CODE); self.c.set_goal(CODE, 'Code goal')
            self.select(B)
            with self.assertRaises(ValueError): self.c.set_goal(B, 'Over limit')
            self.select(A); self.c.set_goal(A, '')
            self.select(B); self.c.set_goal(B, 'Space made available')
            self.c.file.write_text(json.dumps({'projects': {}, 'project_metadata': {
                A: {'goal': 'A goal'}, CODE: {'goal': 'Code goal'}, B: {'goal': 'Ignored beyond bound'}}}))
            loaded = self.connector()
            self.assertEqual(len(loaded.project_metadata), 2)
            self.assertNotIn(B, loaded.project_metadata)

    def test_recent_rows_have_project_ids_and_are_latest_three_current_project_only(self):
        self.link()
        with patch.object(web.time, 'time', side_effect=[10., 20., 30., 40.]):
            self.c.record(A, 'read_file', 'first.txt')
            self.c.record(A, 'import_file', 'second.txt')
            self.c.record(A, 'save_file', 'third.txt', outcome='saved')
            self.c.record(A, 'import_folder', 'fourth')
        recent = self.recent()
        self.assertEqual([item['path'] for item in recent], ['second.txt', 'third.txt', 'fourth'])
        self.assertEqual([item['time'] for item in recent], [20., 30., 40.])
        self.assertTrue(all(item['project_id'] == A for item in recent))
        self.select(None); self.assertEqual(self.recent(), [])

    def test_duplicate_project_names_work_code_and_busy_other_project_never_mix_activity(self):
        self.link(A)
        for i in range(3): self.c.record(A, 'read_file', f'Work-{i}.txt')
        self.link(CODE)
        for i in range(40): self.c.record(CODE, 'read_file', f'Code-{i}.txt')
        self.assertEqual([item['path'] for item in self.recent()], ['Code-37.txt', 'Code-38.txt', 'Code-39.txt'])
        self.assertTrue(all(item['project_id'] == CODE for item in self.recent()))
        self.select(A)
        self.assertEqual([item['path'] for item in self.recent()], ['Work-0.txt', 'Work-1.txt', 'Work-2.txt'])
        self.assertEqual(len(self.c.activity), 30)

    def test_browsing_and_legacy_name_only_rows_do_not_displace_file_actions(self):
        self.link()
        self.c.record(A, 'read_file', 'real-file.txt')
        self.c.record(A, 'list_directory', '.')
        self.c.record(A, 'workspace_overview', '')
        self.c.activity.append({'project': self.c.projects[A]['name'], 'action': 'save_file', 'path': 'unscoped.txt', 'time': 100.})
        self.assertEqual([item['path'] for item in self.recent()], ['real-file.txt'])
        self.assertIn('list_directory', [item['action'] for item in self.c.activity])

    def test_read_file_emits_safe_recent_metadata_without_file_content(self):
        folder = self.link(); ws = self.c.project_workspace(A)
        events = len(self.events)
        with self.c.lock:
            result = self.c.tool(A, {'workspace': ws}, 'read_file', {'path': 'fixture.txt'})
        self.assertEqual(result['content'], 'Original fixture contents')
        self.assertTrue(any(event['type'] == 'web_connector' for event in self.events[events:]))
        self.assertEqual(self.recent()[-1]['action'], 'read_file')
        self.assertNotIn('Original fixture contents', json.dumps(self.recent()))
        self.assertEqual((folder/'fixture.txt').read_text(), 'Original fixture contents')

    def test_pending_and_rejected_proposal_never_claim_saved_changes(self):
        folder, pid = self.proposal()
        self.assertEqual(self.recent()[-1]['action'], 'propose_file')
        self.assertEqual(self.recent()[-1]['outcome'], 'pending')
        self.assertFalse(any(item['action'] == 'save_file' for item in self.recent()))
        self.c.resolve(pid, False)
        self.assertEqual(self.recent()[-1]['outcome'], 'rejected')
        self.assertFalse(any(item['action'] == 'save_file' for item in self.recent()))
        self.assertEqual((folder/'fixture.txt').read_text(), 'Original fixture contents')

    def test_only_successful_committed_write_is_recorded_as_saved(self):
        folder, pid = self.proposal()
        self.c.resolve(pid, True)
        recent = self.recent()
        self.assertEqual(recent[-1]['action'], 'save_file')
        self.assertEqual(recent[-1]['outcome'], 'saved')
        self.assertEqual(recent[-2]['action'], 'propose_file')
        self.assertEqual(recent[-2]['outcome'], 'saved')
        self.assertNotIn('Proposed fixture contents', json.dumps(recent))
        self.assertEqual((folder/'fixture.txt').read_text(), 'Proposed fixture contents')

    def test_failed_proposal_is_not_reported_as_saved(self):
        folder, pid = self.proposal()
        (folder/'fixture.txt').write_text('External edit')
        with self.assertRaises(ValueError): self.c.resolve(pid, True)
        self.assertEqual(self.recent()[-1]['outcome'], 'failed')
        self.assertFalse(any(item['action'] == 'save_file' for item in self.recent()))
        self.assertEqual((folder/'fixture.txt').read_text(), 'External edit')

    def test_revoked_and_expired_proposals_have_honest_status(self):
        folder, pid = self.proposal()
        self.select(CODE)
        self.assertEqual(self.recent(), [])
        self.select(A)
        self.assertEqual(self.recent()[-1]['outcome'], 'revoked')
        self.assertEqual((folder/'fixture.txt').read_text(), 'Original fixture contents')
        _, pid = self.proposal()
        self.c.proposals[pid]['created'] -= 601
        with self.c.lock: self.c.expire()
        self.assertEqual(self.recent()[-1]['outcome'], 'expired')

    def test_unchanged_write_does_not_invent_a_proposal_or_save(self):
        folder = self.link(); ws = self.c.project_workspace(A)
        with self.c.lock:
            self.c.tool(A, {'workspace': ws}, 'read_file', {'path': 'fixture.txt'})
            result = self.c.tool(A, {'workspace': ws}, 'write_file', {'path': 'fixture.txt', 'content': 'Original fixture contents'})
        self.assertTrue(result['unchanged'])
        self.assertEqual([item['action'] for item in self.recent()], ['read_file'])
        self.assertEqual((folder/'fixture.txt').read_text(), 'Original fixture contents')

    def test_activity_paths_are_plain_untrusted_data_and_cache_is_bounded(self):
        self.link(A)
        hostile = '<img src=x onerror=alert(1)>.txt'
        self.c.record(A, 'import_file', hostile)
        self.assertEqual(self.recent()[0]['path'], hostile)
        with patch.object(web, 'MAX_PROJECT_METADATA', 2):
            self.link(CODE); self.c.record(CODE, 'read_file', 'Code.txt')
            self.link(B); self.c.record(B, 'read_file', 'Other.txt')
            self.assertEqual(len(self.c.recent_actions), 2)
        self.assertTrue(all('project_id' in item for item in self.c.activity))

    def test_recent_activity_survives_restart_and_unlink_without_mixing_work_and_code(self):
        self.link(A); self.c.set_goal(A, 'Persistent local goal')
        for index in range(4): self.c.record(A, 'read_file', f'Work-{index}.txt', outcome='read')
        self.link(CODE); self.c.record(CODE, 'import_folder', 'Code-folder')
        self.select(A); self.c.unlink(A)
        self.restart(A)
        self.assertEqual(self.c.snapshot()['project_goal'], 'Persistent local goal')
        self.assertEqual([row['path'] for row in self.recent()], ['Work-1.txt', 'Work-2.txt', 'Work-3.txt'])
        self.assertIsNone(self.c.snapshot()['folder'])
        self.select(CODE)
        self.assertEqual([row['path'] for row in self.recent()], ['Code-folder'])
        self.assertEqual({row['project_id'] for row in self.recent()}, {CODE})

    def test_persistent_activity_is_whitelisted_and_old_pending_proposals_expire_after_restart(self):
        _, pid = self.proposal()
        raw = self.c.file.read_bytes(); stored = json.loads(raw)
        rows = stored['project_activity'][A]
        self.assertNotIn(pid, json.dumps(rows))
        self.assertNotIn(self.c.projects[A]['token'], json.dumps(rows))
        self.assertNotIn('Original fixture contents', json.dumps(rows))
        self.assertNotIn('Proposed fixture contents', json.dumps(rows))
        self.assertEqual(rows[-1]['outcome'], 'pending')
        self.c.close()
        self.c.file.write_bytes(raw)  # Simulate the last atomic snapshot before an abrupt exit.
        self.c = self.connector(); self.select(A)
        self.assertEqual(self.recent()[-1]['action'], 'propose_file')
        self.assertEqual(self.recent()[-1]['outcome'], 'expired')
        self.assertEqual(self.c.proposals, {})

    def test_malformed_persistent_activity_is_bounded_and_never_uses_name_fallback(self):
        valid = {'project_id': A, 'project': 'Same project name', 'action': 'read_file', 'path': 'valid.txt', 'time': 10.}
        self.c.file.write_text(json.dumps({'projects': {}, 'project_activity': {
            A: [{**valid, 'content': 'Body must not survive', 'token': 'Token must not survive'}],
            CODE: [{**valid, 'path': 'Wrong namespace.txt'}],
            'invalid': [valid], B: [{**valid, 'project_id': B, 'action': []}]}}))
        loaded = self.connector()
        self.assertEqual(loaded.recent_actions[A], [valid])
        self.assertNotIn(CODE, loaded.recent_actions); self.assertNotIn(B, loaded.recent_actions)
        for invalid in [None, [], {**valid, 'time': float('nan')}, {**valid, 'time': 10**400},
                        {**valid, 'time': True}, {**valid, 'path': 'x'*4097}, {**valid, 'path': 'bad\npath'}]:
            self.assertIsNone(web.activity_row(A, invalid))

    def test_activity_persistence_failure_does_not_turn_a_successful_read_into_failure(self):
        folder = self.link(); ws = self.c.project_workspace(A)
        with patch.object(self.c, 'save', side_effect=OSError('Controlled history failure')):
            with self.c.lock:
                result = self.c.tool(A, {'workspace': ws}, 'read_file', {'path': 'fixture.txt'})
        self.assertEqual(result['content'], 'Original fixture contents')
        self.assertEqual(self.recent()[-1]['action'], 'read_file')
        self.assertEqual((folder/'fixture.txt').read_text(), 'Original fixture contents')

    def test_goal_is_local_metadata_and_not_added_to_mistral_connector_instructions(self):
        self.link(); self.c.set_goal(A, 'Local goal never sent as Mistral instructions')
        with self.c.lock:
            code, _, message = self.c.rpc(A, None, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}})
        self.assertEqual(code, 200)
        self.assertNotIn('Local goal never sent', json.dumps(message))
        self.assertNotIn('goal', self.c.projects[A])

    def test_history_budget_discards_oldest_history_without_removing_goals_or_links(self):
        self.link(A); self.c.set_goal(A, 'Keep Work goal')
        self.link(CODE); self.c.set_goal(CODE, 'Keep Code goal')
        linked = copy.deepcopy(self.c.projects)
        with patch.object(web, 'MAX_ACTIVITY_BYTES', 500):
            self.c.record(A, 'read_file', 'Work-'+('a'*120)+'.txt')
            self.c.record(CODE, 'read_file', 'Code-'+('b'*120)+'.txt')
            self.c.set_goal(CODE, 'Updated Code goal')
        stored = json.loads(self.c.file.read_text())
        self.assertLessEqual(len(json.dumps(stored['project_activity'], ensure_ascii=False).encode('utf-8')), 500)
        self.assertNotIn(A, stored['project_activity'])
        self.assertIn(CODE, stored['project_activity'])
        self.assertEqual(stored['projects'], linked)
        self.assertEqual(stored['project_metadata'][A]['goal'], 'Keep Work goal')
        self.assertEqual(stored['project_metadata'][CODE]['goal'], 'Updated Code goal')


if __name__ == '__main__': unittest.main()
