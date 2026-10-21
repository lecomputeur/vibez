import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'measure-linux-cpu.py'
SPEC = importlib.util.spec_from_file_location('measure_linux_cpu', SCRIPT)
sampler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sampler
SPEC.loader.exec_module(sampler)


def stat_fixture(pid=7, name='vibez3', parent=1, user=40, system=10, start=123, rss=20):
    fields = ['0'] * 22
    fields[0] = 'S'
    for index, value in ((1, parent), (11, user), (12, system), (19, start), (21, rss)):
        fields[index] = str(value)
    return f'{pid} ({name}) ' + ' '.join(fields) + '\n'


def process(pid=7, parent=1, start=123, cpu=0, rss=1, webkit=False):
    return sampler.Process(pid, parent, start, cpu, rss, webkit)


def snapshot(at, *processes):
    return sampler.Snapshot(at, {p.pid: p for p in processes})


def write_proc(root, pid=7, parent=1, start=123, uid=1000, name='vibez3'):
    directory = root / str(pid)
    directory.mkdir()
    (directory / 'stat').write_text(stat_fixture(pid=pid, parent=parent, start=start, name=name))
    (directory / 'status').write_text(f'Name:\tignored\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\nNeverRead:\tprivate\n')


class ProcParserTests(unittest.TestCase):
    def test_stat_uses_final_parenthesis_and_exact_counter_fields(self):
        row = sampler.parse_stat(stat_fixture(name='a name ) with ( spaces', user=19, system=31))
        self.assertEqual((row.pid, row.parent, row.start_ticks, row.cpu_ticks, row.rss_pages), (7, 1, 123, 50, 20))
        self.assertFalse(row.webkit)

    def test_webkit_comm_truncation_is_classification_only(self):
        for name in ('WebKitWebProcess', 'WebKitWebProces'):
            self.assertTrue(sampler.parse_stat(stat_fixture(name=name)).webkit)
        self.assertFalse(sampler.parse_stat(stat_fixture(name='WebKitNetworkPr')).webkit)

    def test_malformed_fields_are_rejected(self):
        for text in ('invalid', '7 (x) S', stat_fixture(rss=-1), stat_fixture(user=-1)):
            with self.subTest(text=text):
                with self.assertRaises(sampler.MeasurementError):
                    sampler.parse_stat(text)

    def test_uid_requires_all_four_values_and_same_owner(self):
        self.assertEqual(sampler.parse_uid_line('Uid:\t1000 1000 1000 1000\n'), (1000,) * 4)
        for text in ('Uid: 1 2 3', 'Uid: -1 0 0 0', 'Name: 1 1 1 1'):
            with self.assertRaises(sampler.MeasurementError):
                sampler.parse_uid_line(text)
        with self.assertRaises(sampler.MeasurementError):
            sampler.require_owned((1000, 0, 1000, 1000), 1000)

    def test_tree_includes_grandchildren_and_excludes_unrelated_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_proc(root, 7, 1)
            write_proc(root, 8, 7, name='WebKitWebProces')
            write_proc(root, 9, 8)
            write_proc(root, 10, 1, uid=2000)
            found = sampler.family_snapshot(7, 123, 1000, root, clock=lambda: 42)
            self.assertEqual(set(found.processes), {7, 8, 9})
            self.assertTrue(found.processes[8].webkit)
            self.assertEqual(found.timestamp, 42)

    def test_root_pid_reuse_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_proc(root, start=124)
            with self.assertRaisesRegex(sampler.MeasurementError, 'reused'):
                sampler.family_snapshot(7, 123, 1000, root)

    def test_foreign_root_or_descendant_is_refused(self):
        for foreign_pid in (7, 8):
            with self.subTest(foreign_pid=foreign_pid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                write_proc(root, 7, 1, uid=2000 if foreign_pid == 7 else 1000)
                write_proc(root, 8, 7, uid=2000 if foreign_pid == 8 else 1000)
                with self.assertRaisesRegex(sampler.MeasurementError, 'another UID'):
                    sampler.family_snapshot(7, 123, 1000, root)

    def test_unreadable_entries_are_counted_without_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_proc(root)
            (root / '8').mkdir()
            found = sampler.family_snapshot(7, 123, 1000, root)
            self.assertEqual(found.unreadable_entries, 1)
            self.assertEqual(set(found.processes), {7})


class IntervalTests(unittest.TestCase):
    def record(self, before, after, duration=20):
        return sampler.interval_record(before, after, 0, 100, 1024, duration)

    def test_only_complete_warmup_intervals_contribute_and_means_are_weighted(self):
        points = [snapshot(9, process(cpu=0, rss=1024)), snapshot(11, process(cpu=200, rss=1024)),
                  snapshot(12, process(cpu=300, rss=3072)), snapshot(15, process(cpu=450, rss=5120)),
                  snapshot(16, process(cpu=1000, rss=10240))]
        rows = [self.record(a, b, duration=15) for a, b in zip(points, points[1:])]
        self.assertEqual([r['included_after_warmup'] for r in rows], [False, True, True, False])
        result = sampler.summarize(rows, duration=15)
        self.assertEqual(result['included_seconds'], 4)
        self.assertEqual(result['time_coverage_fraction'], 0.8)
        self.assertEqual(result['family']['cpu_percent_time_weighted_mean'], 62.5)
        self.assertEqual(result['family']['rss_mib_time_weighted_mean'], 3.5)

    def test_exact_warmup_and_end_boundaries_are_included(self):
        row = self.record(snapshot(10, process(cpu=0)), snapshot(20, process(cpu=1000)))
        self.assertTrue(row['included_after_warmup'])
        self.assertEqual(sampler.summarize([row], 20)['family']['cpu_percent_time_weighted_mean'], 100)

    def test_child_pid_reuse_and_new_exited_processes_do_not_invent_cpu(self):
        before = snapshot(10, process(cpu=100), process(8, 7, 1, 500, webkit=True), process(9, 7, 1, 200))
        after = snapshot(11, process(cpu=110), process(8, 7, 2, 99999, webkit=True), process(10, 7, 1, 99999))
        row = self.record(before, after)
        self.assertEqual(row['pid_reuses'], 1)
        self.assertEqual(row['new_identities'], 2)
        self.assertEqual(row['departed_or_exited_identities'], 2)
        self.assertEqual(row['family']['cpu_percent'], 10)
        self.assertEqual(row['webkit_web_process']['cpu_percent'], 0)
        self.assertEqual(row['webkit_web_process']['count_after'], 1)

    def test_webkit_cpu_rss_and_counts_are_separate_from_whole_family(self):
        before = snapshot(10, process(cpu=0, rss=1024), process(8, 7, 1, 10, 2048, True))
        after = snapshot(12, process(cpu=100, rss=1024), process(8, 7, 1, 110, 2048, True))
        result = sampler.summarize([self.record(before, after)], 20)
        self.assertEqual(result['family']['cpu_percent_time_weighted_mean'], 100)
        self.assertEqual(result['webkit_web_process']['cpu_percent_time_weighted_mean'], 50)
        self.assertEqual(result['family']['rss_mib_time_weighted_mean'], 3)
        self.assertEqual(result['webkit_web_process']['rss_mib_time_weighted_mean'], 2)
        self.assertEqual(result['webkit_web_process']['process_count_time_weighted_mean'], 1)

    def test_negative_counter_delta_is_reported_and_excluded(self):
        row = self.record(snapshot(10, process(cpu=100)), snapshot(11, process(cpu=90)))
        self.assertEqual(row['counter_regressions'], 1)
        self.assertEqual(row['family']['cpu_percent'], 0)

    def test_no_measured_intervals_has_no_fabricated_mean(self):
        result = sampler.summarize([], 90)
        self.assertEqual(result['included_seconds'], 0)
        self.assertIsNone(result['family']['cpu_percent_time_weighted_mean'])


class RootIdentityFixtureTests(unittest.TestCase):
    """Synthetic /proc unit fixtures only; never a public CLI identity bypass."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.proc = self.base / 'proc'
        self.proc.mkdir()
        # An arbitrary comm must not determine root identity.
        write_proc(self.proc, name='not-the-exe-name')
        self.binary = self.base / 'vibez3'
        self.binary.write_bytes(b'unit fixture bytes; not an app')
        (self.proc / '7/exe').symlink_to(self.binary)

    def test_root_uses_executable_basename_and_calculated_sha(self):
        identity = sampler.identify_root(7, 1000, self.proc)
        self.assertEqual(identity.executable, 'vibez3')
        self.assertEqual(identity.sha256, hashlib.sha256(self.binary.read_bytes()).hexdigest())
        self.assertEqual(identity.start_ticks, 123)
        sampler.check_root(identity, self.proc)

    def test_other_executable_basename_is_refused_even_with_vibez_comm(self):
        (self.proc / '7/stat').write_text(stat_fixture(name='vibez3'))
        other = self.base / 'another-app'
        other.write_bytes(b'fixture')
        (self.proc / '7/exe').unlink()
        (self.proc / '7/exe').symlink_to(other)
        with self.assertRaisesRegex(sampler.MeasurementError, 'not vibez3'):
            sampler.identify_root(7, 1000, self.proc)

    def test_changed_root_start_time_stops_measurement(self):
        identity = sampler.identify_root(7, 1000, self.proc)
        (self.proc / '7/stat').write_text(stat_fixture(start=124))
        with self.assertRaisesRegex(sampler.MeasurementError, 'reused'):
            sampler.check_root(identity, self.proc)

    def test_changed_root_uid_stops_measurement(self):
        identity = sampler.identify_root(7, 1000, self.proc)
        (self.proc / '7/status').write_text('Uid: 1000 0 1000 1000\n')
        with self.assertRaisesRegex(sampler.MeasurementError, 'another UID'):
            sampler.check_root(identity, self.proc)

    def test_executable_inode_replacement_stops_even_with_same_pid_start_and_basename(self):
        identity = sampler.identify_root(7, 1000, self.proc)
        replacement = self.base / 'replacement'
        replacement.write_bytes(b'different unit fixture bytes')
        replacement.replace(self.binary)
        with self.assertRaisesRegex(sampler.MeasurementError, 'executable changed'):
            sampler.check_root(identity, self.proc)


class OutputAndCliTests(unittest.TestCase):
    def test_new_output_is_private_and_existing_files_and_symlinks_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'cpu.json'
            descriptor = sampler.create_output(output)
            os.write(descriptor, b'preserved')
            os.close(descriptor)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                sampler.create_output(output)
            link = Path(directory) / 'link.json'
            link.symlink_to(output)
            with self.assertRaises(FileExistsError):
                sampler.create_output(link)
            self.assertEqual(output.read_bytes(), b'preserved')

    def test_duration_limits_include_finite_checks(self):
        for value in ('20', '90', '180'):
            self.assertEqual(sampler.bounded_duration(value), float(value))
        for value in ('19', '181', 'nan', 'inf', 'oops'):
            with self.assertRaises(argparse.ArgumentTypeError):
                sampler.bounded_duration(value)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux /proc integration')
    def test_public_cli_refuses_real_non_vibez_process_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'must-not-exist.json'
            result = subprocess.run([sys.executable, str(SCRIPT), '--pid', str(os.getpid()), '--output', str(output)],
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertIn('not vibez3', result.stderr)
            self.assertNotIn(directory, result.stderr)
            self.assertFalse(output.exists())

    @unittest.skipUnless(sys.platform == 'linux', 'Linux /proc integration')
    def test_internal_sampler_observes_our_controlled_cpu_worker_without_cli_bypass(self):
        worker = subprocess.Popen([sys.executable, '-c',
            'import time\nend=time.monotonic()+5\nwhile time.monotonic()<end: pass\n'])
        try:
            initial, _ = sampler.read_process(worker.pid)
            before = sampler.family_snapshot(worker.pid, initial.start_ticks, os.getuid())
            time.sleep(0.2)
            after = sampler.family_snapshot(worker.pid, initial.start_ticks, os.getuid())
            row = sampler.interval_record(before, after, before.timestamp,
                os.sysconf('SC_CLK_TCK'), os.sysconf('SC_PAGE_SIZE'), 1, warmup=0)
            self.assertGreater(row['family']['cpu_seconds'], 0)
            self.assertGreater(row['family']['rss_mib_after'], 0)
            self.assertEqual(row['pid_reuses'], 0)
            self.assertEqual(row['family']['count_after'], 1)
        finally:
            worker.terminate()
            worker.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
