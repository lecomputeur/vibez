#!/usr/bin/env python3
"""Run explicit rich-chat tests in the ordinary Linux binary, with an isolated bus/profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

PREFIX = 'SCROLL_PROBE '


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def available_mib():
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) / 1024
    except (OSError, ValueError):
        pass
    return None


def process_tree(root_pid):
    """Inspect only the launched process's descendants; never enumerate other clients."""
    pending = [root_pid]
    seen = set()
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        try:
            for entry in (Path('/proc') / str(pid) / 'task').iterdir():
                try:
                    pending.extend(int(v) for v in (entry / 'children').read_text().split())
                except (OSError, ValueError):
                    continue
        except OSError:
            continue
    return seen


def read_process(pid, ticks, page_size):
    try:
        p = Path('/proc') / str(pid)
        # comm can contain spaces and parentheses; fields after the last ')' are stable.
        fields = (p / 'stat').read_text().rsplit(')', 1)[1].split()
        exe = Path(os.readlink(p / 'exe')).name
        return {'identity': (pid, int(fields[19])),
                'cpuSeconds': (int(fields[11]) + int(fields[12])) / ticks,
                'rssMiB': int(fields[21]) * page_size / (1024 * 1024),
                'webContent': exe == 'WebKitWebProcess'}
    except (OSError, ValueError, IndexError):
        return None


def stop_own_group(proc):
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)


def summarize(samples):
    summaries = {}
    for phase in sorted({row['phase'] for row in samples}):
        rows = [row for row in samples if row['phase'] == phase and row['cpuPercent'] is not None]
        elapsed = sum(row['intervalSeconds'] for row in rows)
        cpu = sum(row['cpuDeltaSeconds'] for row in rows)
        summaries[phase] = {
            'sampleCount': len(rows), 'sampledSeconds': elapsed,
            'cpuMeanPercent': 100 * cpu / elapsed if elapsed else None,
            'cpuPeakSamplePercent': max((row['cpuPercent'] for row in rows), default=None),
            'samplesAbove100Percent': sum(row['cpuPercent'] > 100 for row in rows),
            'webContentRssPeakMiB': max((row['webContentRssMiB'] for row in rows), default=None),
            'ownTreeRssPeakMiB': max((row['ownTreeRssMiB'] for row in rows), default=None),
        }
    return summaries


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', required=True, type=Path)
    p.add_argument('--mode', required=True, choices=('lifecycle', 'resize', 'wheel', 'fullscreen', 'mistral'))
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--baseline', action='store_true', help='Pause containment for the wheel-only control')
    p.add_argument('--sections', type=int, choices=(2, 16), default=16, help='Only fullscreen may use 2 sections per answer')
    p.add_argument('--disable-compositing', action='store_true')
    p.add_argument('--disable-dmabuf', action='store_true')
    p.add_argument('--timeout', type=float, default=600)
    p.add_argument('--min-available-mib', type=float, default=600)
    p.add_argument('--max-own-rss-mib', type=float, default=2400)
    args = p.parse_args()
    if args.baseline and args.mode != 'wheel':
        p.error('--baseline is valid only for --mode wheel')
    if args.sections != 16 and args.mode != 'fullscreen':
        p.error('Only --mode fullscreen may use --sections 2')
    if min(args.timeout, args.min_available_mib, args.max_own_rss_mib) <= 0:
        p.error('Timeout and memory limits must be positive')
    return args


def main():
    args = parse_args()
    binary = args.binary.resolve(strict=True)
    if platform.system() != 'Linux' or not os.environ.get('DISPLAY'):
        raise SystemExit('Linux with an existing DISPLAY is required; CI must supply Xvfb and a window manager.')
    if not os.access(binary, os.X_OK) or not shutil.which('dbus-run-session'):
        raise SystemExit('An executable binary and dbus-run-session are required.')
    free = available_mib()
    if free is None or free < args.min_available_mib:
        raise SystemExit(f'Insufficient available RAM: {free!r} MiB; need {args.min_available_mib} MiB. No app was launched.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise SystemExit('Output directory must be empty, to prevent stale evidence from passing a rerun.')
    harness = Path(__file__).resolve().parent
    metadata = {'mode': args.mode, 'baseline': args.baseline, 'binary': str(binary),
                'binarySha256': digest(binary), 'sectionsPerAnswer': args.sections,
                'platform': platform.platform(), 'display': os.environ['DISPLAY'],
                'gtkEnvironment': {'GDK_BACKEND': 'x11', 'GDK_SCALE': '1', 'GDK_DPI_SCALE': '1'},
                'clearedInheritedTestKeys': sorted(k for k in os.environ if k.startswith(('VIBEZ_', 'WEBKIT_')) or k in ('GDK_SCALE', 'GDK_DPI_SCALE')),
                'inheritedGraphicsEnvironment': {k: os.environ[k] for k in ('LIBGL_ALWAYS_SOFTWARE', 'MESA_LOADER_DRIVER_OVERRIDE', 'DRI_PRIME') if k in os.environ},
                'cpuDefinition': '100% is one logical CPU core; summed CPU deltas of this test process tree\'s WebKitWebProcess only',
                'sampling': 'Approximately 0.5-second samples; interval-weighted mean; phase-crossing intervals excluded',
                'memoryDefinition': 'Sum of process RSS, not proportional/shared memory; no DOM memory estimate',
                'captureLimitation': 'Own-WebKit PNG pixels are not evidence of OS compositor presentation',
                'fixtureLimitation': 'Synthetic structure, not a captured Mistral conversation',
                'harnessSha256': {p.name: digest(p) for p in sorted(harness.iterdir()) if p.is_file()},
                'webkitOverrides': {key: ('1' if enabled else None) for key, enabled in (
                    ('WEBKIT_DISABLE_COMPOSITING_MODE', args.disable_compositing),
                    ('WEBKIT_DISABLE_DMABUF_RENDERER', args.disable_dmabuf))},
                'memoryGuard': {'initialAvailableMiB': free, 'minimumAvailableMiB': args.min_available_mib,
                                'maximumOwnTreeRssMiB': args.max_own_rss_mib}}
    write_json(output / 'metadata.json', metadata)
    events, samples = [], []
    event_queue = queue.Queue()
    failure = None
    returncode = None
    with tempfile.TemporaryDirectory(prefix='vibez-rich-test-') as temporary:
        profile = Path(temporary)
        env = os.environ.copy()
        # Do not inherit another test's bypasses, profile or renderer settings.
        for key in list(env):
            if key.startswith(('VIBEZ_', 'WEBKIT_')) or key in ('GDK_SCALE', 'GDK_DPI_SCALE'):
                env.pop(key)
        for key, sub in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state')]:
            path = profile / sub
            path.mkdir()
            env[key] = str(path)
        env.update(VIBEZ_RICH_TEST_MODE=args.mode, VIBEZ_RICH_TEST_PROFILE=str(profile),
                   VIBEZ_RICH_TEST_BUS='1', VIBEZ_RICH_TEST_OUTPUT=str(output),
                   VIBEZ_RICH_TEST_LABEL=args.mode, VIBEZ_RICH_TEST_SECTIONS=str(args.sections),
                   VIBEZ_RESIZE_TEST='1', VIBEZ_OFFLINE_LEFT_SCREEN='1', GDK_BACKEND='x11',
                   GDK_SCALE='1', GDK_DPI_SCALE='1')
        if args.baseline:
            env['VIBEZ_RICH_TEST_BASELINE'] = '1'
        for key, value in metadata['webkitOverrides'].items():
            if value is not None:
                env[key] = value
        proc = subprocess.Popen(['dbus-run-session', '--', str(binary), '--rich-offline-test'],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', errors='replace', bufsize=1,
                                start_new_session=True)
        start = time.monotonic()

        def reader():
            with (output / 'app.log').open('w') as log:
                for line in proc.stdout:
                    log.write(line)
                    log.flush()
                    if line.startswith(PREFIX):
                        try:
                            event_queue.put((time.monotonic(), json.loads(line[len(PREFIX):])))
                        except json.JSONDecodeError:
                            event_queue.put((time.monotonic(), {'event': 'launcher-parse-error'}))
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        previous = {}
        last_at = start
        phase = 'startup'
        last_phase = phase
        memory_bad = 0
        ticks, page_size = os.sysconf('SC_CLK_TCK'), os.sysconf('SC_PAGE_SIZE')
        try:
            with (output / 'cpu-samples.jsonl').open('w') as sample_log:
                while True:
                    now = time.monotonic()
                    while True:
                        try:
                            received_at, event = event_queue.get_nowait()
                        except queue.Empty:
                            break
                        event['launcherElapsedSeconds'] = received_at - start
                        events.append(event)
                        if event.get('event') == 'phase':
                            phase = event.get('name', 'unknown')
                            print(f"{args.mode}: {phase}", flush=True)
                        if event.get('event') in ('error', 'launcher-parse-error'):
                            failure = failure or event.get('error', 'Malformed test event')
                    current = {}
                    for pid in process_tree(proc.pid):
                        row = read_process(pid, ticks, page_size)
                        if row is not None:
                            current[row['identity']] = row
                    dt = now - last_at
                    stable = phase == last_phase and bool(previous) and dt > 0
                    delta = sum(max(0, row['cpuSeconds'] - previous[identity]['cpuSeconds'])
                                for identity, row in current.items()
                                if row['webContent'] and identity in previous) if stable else 0
                    row = {'elapsedSeconds': now - start, 'phase': phase, 'intervalSeconds': dt,
                           'cpuDeltaSeconds': delta if stable else 0,
                           'cpuPercent': 100 * delta / dt if stable else None,
                           'webContentProcesses': sum(v['webContent'] for v in current.values()),
                           'webContentRssMiB': sum(v['rssMiB'] for v in current.values() if v['webContent']),
                           'ownTreeRssMiB': sum(v['rssMiB'] for v in current.values()),
                           'availableMiB': available_mib()}
                    samples.append(row)
                    sample_log.write(json.dumps(row) + '\n')
                    sample_log.flush()
                    bad = row['ownTreeRssMiB'] > args.max_own_rss_mib or row['availableMiB'] is None or row['availableMiB'] < args.min_available_mib
                    memory_bad = memory_bad + 1 if bad else 0
                    previous, last_at, last_phase = current, now, phase
                    if proc.poll() is not None:
                        returncode = proc.returncode
                        break
                    if memory_bad >= 3:
                        failure = f"Memory guard stopped only this test process group: {row}"
                        break
                    if now - start > args.timeout:
                        failure = f'Test exceeded {args.timeout} seconds'
                        break
                    time.sleep(0.5)
        except KeyboardInterrupt:
            failure = 'Interrupted; stopped only the launched test process group'
        finally:
            stop_own_group(proc)
            returncode = proc.returncode
            thread.join(timeout=5)
            while True:
                try:
                    received_at, event = event_queue.get_nowait()
                except queue.Empty:
                    break
                event['launcherElapsedSeconds'] = received_at - start
                events.append(event)
                if event.get('event') == 'error':
                    failure = failure or event.get('error')
    complete = next((e for e in reversed(events) if e.get('event') == 'complete'), None)
    if complete is None:
        failure = failure or 'No completion event; evidence is incomplete'
    if returncode != 0:
        failure = failure or f'Test process exited {returncode}'
    summary = {'ok': failure is None, 'error': failure, 'exitCode': returncode,
               'elapsedSeconds': time.monotonic() - start, 'mode': args.mode, 'baseline': args.baseline,
               'complete': complete, 'cpuByPhase': summarize(samples), 'metadata': metadata}
    write_json(output / 'events.json', events)
    write_json(output / 'summary.json', summary)
    print(json.dumps({'ok': summary['ok'], 'error': failure, 'output': str(output),
                      'cpuByPhase': summary['cpuByPhase']}, indent=2), flush=True)
    return 0 if summary['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
