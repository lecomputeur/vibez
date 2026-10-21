#!/usr/bin/env python3
"""Read-only /proc CPU/RSS sampling of one explicitly selected, owned VibeZ tree."""
import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

WARMUP = 10.0
INTERVAL = 1.0
ALLOWED_EXECUTABLES = {'vibez3', 'vibez3-canvas-test'}
WEBKIT_COMM = {'WebKitWebProcess', 'WebKitWebProcess'[:15]}
LIMITATIONS = [
    'Only the selected root and descendants visible at each /proc scan are measured; scans are not atomic.',
    'CPU is a lower bound when processes appear, exit, are reparented, or cannot be read between scans. Processes born and exited between scans are unseen.',
    'Only matching PID/start-time identities at both interval endpoints contribute CPU; child CPU is not added again from parent waited-child counters.',
    'WebKitWebProcess classification uses its Linux comm name (possibly truncated), not a verified child executable or frame attribution.',
    'RSS sums can count shared pages repeatedly; they are not unique physical-memory consumption.',
    'Other applications, shared services, GPU work outside the tree and sampling overhead outside the tree are not included.',
    'No conversation, Canvas state or idle state is observed; a user must describe the workload separately. These measurements do not establish an issue #49 fix.',
]


class MeasurementError(ValueError):
    """A safe error message containing no user paths or process names."""


@dataclass(frozen=True)
class Process:
    pid: int
    parent: int
    start_ticks: int
    cpu_ticks: int
    rss_pages: int
    webkit: bool

    @property
    def identity(self):
        return self.pid, self.start_ticks


@dataclass(frozen=True)
class Snapshot:
    timestamp: float
    processes: dict
    unreadable_entries: int = 0


@dataclass(frozen=True)
class RootIdentity:
    pid: int
    start_ticks: int
    uid: int
    executable: str
    sha256: str
    device: int
    inode: int


def parse_stat(text):
    """Parse fields after the final ')' so spaces/parentheses in comm are safe."""
    left, right = text.find('('), text.rfind(')')
    if left < 1 or right <= left:
        raise MeasurementError('Malformed process stat data.')
    try:
        pid = int(text[:left].strip())
        fields = text[right + 1:].split()
        name = text[left + 1:right]
        parent, user, system, start, rss = (int(fields[i]) for i in (1, 11, 12, 19, 21))
        if pid <= 0 or min(parent, user, system, start) < 0 or rss < 0:
            raise ValueError
    except (IndexError, ValueError) as error:
        raise MeasurementError('Malformed process stat counters.') from error
    return Process(pid, parent, start, user + system, rss, name in WEBKIT_COMM)


def parse_uid_line(line):
    try:
        label, values = line.split(':', 1)
        uids = tuple(int(value) for value in values.split())
        if label != 'Uid' or len(uids) != 4 or min(uids) < 0:
            raise ValueError
        return uids
    except ValueError as error:
        raise MeasurementError('Missing or malformed process UID metadata.') from error


def read_uids(path):
    # Stop at Uid; do not retain the other status fields.
    with path.open() as stream:
        for line in stream:
            if line.startswith('Uid:'):
                return parse_uid_line(line)
    raise MeasurementError('Process UID metadata is unavailable.')


def read_process(pid, proc=Path('/proc')):
    directory = proc / str(pid)
    before = parse_stat((directory / 'stat').read_text())
    uids = read_uids(directory / 'status')
    after = parse_stat((directory / 'stat').read_text())
    if before.pid != pid or after.pid != pid or before.identity != after.identity:
        raise MeasurementError('PID identity changed while reading process metadata.')
    return after, uids


def require_owned(uids, owner):
    if any(uid != owner for uid in uids):
        raise MeasurementError('Refusing a process owned by another UID or with changed credentials.')


def identify_root(pid, owner, proc=Path('/proc')):
    process, uids = read_process(pid, proc)
    require_owned(uids, owner)
    exe = proc / str(pid) / 'exe'
    name = Path(os.readlink(exe)).name
    if name not in ALLOWED_EXECUTABLES:
        raise MeasurementError('The selected executable is not vibez3 or vibez3-canvas-test.')
    digest = hashlib.sha256()
    with exe.open('rb') as stream:
        metadata = os.fstat(stream.fileno())
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    root = RootIdentity(pid, process.start_ticks, owner, name, digest.hexdigest(), metadata.st_dev, metadata.st_ino)
    check_root(root, proc)
    return root


def check_root(root, proc=Path('/proc')):
    process, uids = read_process(root.pid, proc)
    require_owned(uids, root.uid)
    if process.start_ticks != root.start_ticks:
        raise MeasurementError('The selected root PID was reused; measurement stopped.')
    exe = proc / str(root.pid) / 'exe'
    # An exec can keep the same PID and start time, so check its file identity too.
    metadata = exe.stat()
    if (Path(os.readlink(exe)).name != root.executable or
            (metadata.st_dev, metadata.st_ino) != (root.device, root.inode)):
        raise MeasurementError('The selected root executable changed; measurement stopped.')


def family_snapshot(pid, expected_start, owner, proc=Path('/proc'), clock=time.monotonic):
    """Internal sampler. The public entry point separately requires VibeZ identity."""
    begin = clock()
    rows, credentials, unreadable = {}, {}, 0
    for directory in proc.iterdir():
        if not directory.name.isdigit():
            continue
        child_pid = int(directory.name)
        try:
            rows[child_pid], credentials[child_pid] = read_process(child_pid, proc)
        except (OSError, MeasurementError, UnicodeError):
            unreadable += 1
    if pid not in rows:
        raise MeasurementError('The selected root is no longer readable or running.')
    if rows[pid].start_ticks != expected_start:
        raise MeasurementError('The selected root PID was reused; measurement stopped.')
    children = {}
    for row in rows.values():
        children.setdefault(row.parent, []).append(row.pid)
    family, pending = {}, [pid]
    while pending:
        current = pending.pop()
        if current in family:
            continue
        require_owned(credentials[current], owner)
        family[current] = rows[current]
        pending.extend(children.get(current, []))
    return Snapshot((begin + clock()) / 2, family, unreadable)


def interval_record(previous, current, origin, hz, page_size, duration, warmup=WARMUP):
    start, end = previous.timestamp - origin, current.timestamp - origin
    seconds = end - start
    if seconds <= 0:
        raise MeasurementError('Sampling timestamps must increase.')
    before = {row.identity: row for row in previous.processes.values()}
    after = {row.identity: row for row in current.processes.values()}
    common = before.keys() & after.keys()
    reused = sum(previous.processes[pid].identity != current.processes[pid].identity
                 for pid in previous.processes.keys() & current.processes.keys())
    eligible = start >= warmup and end <= duration
    row = {
        'start_seconds': start, 'end_seconds': end, 'seconds': seconds,
        'included_after_warmup': eligible,
        'new_identities': len(after.keys() - before.keys()),
        'departed_or_exited_identities': len(before.keys() - after.keys()),
        'pid_reuses': reused, 'counter_regressions': 0,
        'classification_changes': sum(before[key].webkit != after[key].webkit for key in common),
        'matching_identities': len(common), 'union_identities': len(before.keys() | after.keys()),
    }
    valid = {key for key in common if after[key].cpu_ticks >= before[key].cpu_ticks}
    row['counter_regressions'] = len(common - valid)
    for group in ('family', 'webkit_web_process'):
        selected_before = [p for p in before.values() if group == 'family' or p.webkit]
        selected_after = [p for p in after.values() if group == 'family' or p.webkit]
        selected_common = [key for key in valid if group == 'family' or (before[key].webkit and after[key].webkit)]
        cpu_seconds = sum(after[key].cpu_ticks - before[key].cpu_ticks for key in selected_common) / hz
        rss_before = sum(p.rss_pages for p in selected_before) * page_size / 1048576
        rss_after = sum(p.rss_pages for p in selected_after) * page_size / 1048576
        row[group] = {
            'cpu_seconds': cpu_seconds, 'cpu_percent': 100 * cpu_seconds / seconds,
            'count_before': len(selected_before), 'count_after': len(selected_after),
            'rss_mib_before': rss_before, 'rss_mib_after': rss_after,
        }
    return row


def summarize(records, duration, warmup=WARMUP):
    included = [row for row in records if row['included_after_warmup']]
    seconds = sum(row['seconds'] for row in included)
    potential = duration - warmup
    summary = {
        'included_seconds': seconds, 'requested_post_warmup_seconds': potential,
        'time_coverage_fraction': seconds / potential if potential > 0 else 0,
        'included_intervals': len(included), 'excluded_intervals': len(records) - len(included),
        'matching_identity_fraction': (
            sum(row['matching_identities'] * row['seconds'] for row in included) /
            sum(row['union_identities'] * row['seconds'] for row in included)
        ) if any(row['union_identities'] for row in included) else None,
    }
    for group in ('family', 'webkit_web_process'):
        cpu = sum(row[group]['cpu_seconds'] for row in included)
        summary[group] = {
            'cpu_seconds_observed': cpu,
            'cpu_percent_time_weighted_mean': 100 * cpu / seconds if seconds else None,
            'cpu_percent_peak_interval': max((row[group]['cpu_percent'] for row in included), default=None),
            'process_count_time_weighted_mean': sum(
                (row[group]['count_before'] + row[group]['count_after']) / 2 * row['seconds']
                for row in included) / seconds if seconds else None,
            'process_count_peak_endpoint': max(
                (max(row[group]['count_before'], row[group]['count_after']) for row in included), default=None),
            'rss_mib_time_weighted_mean': sum(
                (row[group]['rss_mib_before'] + row[group]['rss_mib_after']) / 2 * row['seconds']
                for row in included) / seconds if seconds else None,
            'rss_mib_peak_endpoint': max(
                (max(row[group]['rss_mib_before'], row[group]['rss_mib_after']) for row in included), default=None),
        }
    return summary


def measure(root, duration, hz, page_size):
    first = family_snapshot(root.pid, root.start_ticks, root.uid)
    origin, previous = first.timestamp, first
    seen = {row.identity for row in first.processes.values()}
    records, snapshots, failure = [], [first], None
    next_sample = origin + INTERVAL
    try:
        while previous.timestamp - origin < duration:
            time.sleep(max(0, next_sample - time.monotonic()))
            check_root(root)
            current = family_snapshot(root.pid, root.start_ticks, root.uid)
            check_root(root)
            records.append(interval_record(previous, current, origin, hz, page_size, duration))
            snapshots.append(current)
            seen.update(row.identity for row in current.processes.values())
            previous = current
            next_sample += INTERVAL
            # If a scan was slow, skip missed deadlines instead of busy catching up.
            if next_sample < time.monotonic():
                next_sample = time.monotonic() + INTERVAL
    except KeyboardInterrupt:
        failure = 'Interrupted by the user; only completed intervals are reported.'
    except (OSError, MeasurementError, UnicodeError):
        failure = 'The root, its identity/credentials, or required /proc metadata changed or became unavailable.'
    report = {
        'schema_version': 1, 'complete': failure is None,
        'stop_reason': failure or 'Requested sampling period completed.',
        'root': {'pid': root.pid, 'start_ticks': root.start_ticks, 'uid': root.uid,
                 'executable_basename': root.executable, 'executable_sha256': root.sha256},
        'method': {
            'requested_seconds': duration, 'warmup_seconds': WARMUP, 'target_interval_seconds': INTERVAL,
            'observed_seconds': previous.timestamp - origin, 'clock_ticks_per_second': hz,
            'page_size_bytes': page_size, 'cpu_denominator': '100% = one logical CPU core; totals may exceed 100%',
            'cpu_counters': 'utime + stime only; deltas require the same PID/start-time identity at both endpoints',
            'mean_window': 'Only complete intervals starting at/after warmup and ending at/before requested duration',
            'rss_and_count_average': 'Time-weighted trapezoids of interval endpoint totals',
        },
        'coverage': summarize(records, duration),
        'churn': {
            'observed_unique_identities': len(seen),
            'new_identity_observations': sum(row['new_identities'] for row in records),
            'departed_or_exited_observations': sum(row['departed_or_exited_identities'] for row in records),
            'pid_reuses_observed': sum(row['pid_reuses'] for row in records),
            'counter_regressions': sum(row['counter_regressions'] for row in records),
            'classification_changes': sum(row['classification_changes'] for row in records),
            'unreadable_proc_entries_across_scans': sum(s.unreadable_entries for s in snapshots),
            'unreadable_entries_scope': 'All scanned /proc entries; unreadable entries cannot be reliably attributed to this family',
            'unseen_short_lived_processes': 'Unknown; the polling method cannot count them',
        },
        'limitations': LIMITATIONS, 'intervals': records,
    }
    return report


def bounded_duration(value):
    try:
        duration = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('Duration must be a number from 20 to 180 seconds.') from error
    if not math.isfinite(duration) or not 20 <= duration <= 180:
        raise argparse.ArgumentTypeError('Duration must be from 20 to 180 seconds.')
    return duration


def create_output(path):
    """Create exclusively, including refusing an existing symlink."""
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True, help='Existing VibeZ root PID owned by your current UID')
    parser.add_argument('--output', type=Path, required=True, help='New JSON file; existing files are never overwritten')
    parser.add_argument('--duration', type=bounded_duration, default=90.0, help='Total seconds including fixed 10-second warmup (20–180; default 90)')
    args = parser.parse_args(argv)
    if sys.platform != 'linux' or args.pid <= 0:
        parser.error('A positive existing PID on Linux is required.')
    try:
        root = identify_root(args.pid, os.getuid())
        # O_EXCL also rejects existing symlinks. Diagnostics are private by default.
        descriptor = create_output(args.output)
        with os.fdopen(descriptor, 'w') as stream:
            report = measure(root, args.duration, os.sysconf('SC_CLK_TCK'), os.sysconf('SC_PAGE_SIZE'))
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
        print('Saved private CPU/RSS diagnostics to the new output file.')
        return 0 if report['complete'] else 2
    except FileExistsError:
        parser.exit(2, 'Output already exists; choose a new file. Nothing was overwritten.\n')
    except MeasurementError as error:
        parser.exit(2, str(error) + '\n')
    except (OSError, UnicodeError):
        parser.exit(2, 'Cannot read required process metadata or create the new output file.\n')


if __name__ == '__main__':
    sys.exit(main())
