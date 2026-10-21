#!/usr/bin/env python3
"""Bounded offline active-iframe experiment on an unchanged Linux VibeZ binary."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CHARTS = ROOT / 'desktop/test-tools/canvas/charts'
sys.path.insert(0, str(CHARTS))
import base_runner as base
from run_chart import processes


def summarize(states, samples, helper_disabled=False):
    phases = {}
    for phase in ('visible', 'offscreen', 'hidden', 'returned'):
        selected = [s for s in states if s['phase'] == phase]
        # Exclude transitions and measure deltas within the same phase.
        selected = [s for s in selected if s['elapsedMs'] >= (8000 if phase == 'visible' else
                    {'offscreen': 14000, 'hidden': 26000, 'returned': 38000}[phase] + 3000)]
        if len(selected) < 2:
            raise ValueError('Missing settled samples for ' + phase)
        first, last = selected[0], selected[-1]
        if len(first['frames']) != 8 or len(last['frames']) != 8:
            raise ValueError('Missing frame reports')
        seconds = (last['elapsedMs'] - first['elapsedMs']) / 1000
        expected_visible = 8 if phase in ('visible', 'returned') else 1
        if sum(f['inViewport'] for f in last['frames']) != expected_visible:
            raise ValueError('Incorrect viewport distribution for ' + phase)
        if any((s['helper'] is None) != helper_disabled for s in selected):
            raise ValueError('Requested helper state was not observed')
        deltas = []
        for a, b in zip(first['frames'], last['frames']):
            if a.get('instance') != b.get('instance') or not a.get('instance'):
                raise ValueError('Frame was replaced during phase ' + phase)
            if b.get('sequence', 0) <= a.get('sequence', 0) or b['timers'] <= a['timers']:
                raise ValueError('No fresh frame progress for ' + phase)
            deltas.append({'id': b['id'], 'inViewport': b['inViewport'],
                           'rafPerSecond': (b['raf'] - a['raf']) / seconds,
                           'timerPerSecond': (b['timers'] - a['timers']) / seconds,
                           'documentVisibility': b['visibility'], 'draftPreserved': b['draftPreserved']})
        cpu = [s for s in samples if first['sampledAtSeconds'] <= s['startSeconds']
               and s['endSeconds'] <= last['sampledAtSeconds']]
        duration = sum(s['endSeconds'] - s['startSeconds'] for s in cpu)
        if not cpu or duration < 3 or not all(s['webProcesses'] > 0 for s in cpu):
            raise ValueError('Insufficient web-process CPU coverage for ' + phase)
        phases[phase] = {'seconds': seconds, 'frames': deltas,
                         'cpuSampleSeconds': duration,
                         'webCpuMeanPercentOneCore': sum(s['cpuPercent'] * (s['endSeconds'] - s['startSeconds'])
                                                       for s in cpu) / duration if duration else None,
                         'helperFirst': first['helper'], 'helperLast': last['helper']}
    identities = {s['id']: s['instance'] for s in states[0]['frames'] if s.get('instance')}
    final = states[-1]
    preserved = (len(identities) == 8 and len(final['frames']) == 8 and final.get('stopToken') is not None
                 and all(identities.get(f['id']) == f.get('instance') and f.get('draftPreserved')
                         and f.get('stopAck') == final['stopToken'] for f in final['frames']))
    return {'phases': phases, 'allFrameDocumentsAndSyntheticDraftsPreserved': preserved}


def worker(args):
    out = args.output
    with (out / 'openbox.log').open('w') as wm_log:
        wm = subprocess.Popen(['openbox', '--sm-disable'], stdout=wm_log, stderr=subprocess.STDOUT,
                              start_new_session=True)
        try:
            time.sleep(.7)
            with base.disposable_profile(out, 'vz-active-') as profile:
                env = base.profile_env(profile, out)
                env.update(VIBEZ_CANVAS_MODE='controlled-html', VIBEZ_CANVAS_FIXTURE=str(out / 'fixture.html'),
                           VIBEZ_CANVAS_NATIVE_LOG=str(out / 'native-trace.jsonl'),
                           VIBEZ_CHART_SCREENSHOT=str(out / 'visible.png'), LD_PRELOAD=str(out / 'observer.so'))
                if args.disable_rich_render:
                    env['VIBEZ_DISABLE_RICH_RENDER'] = '1'
                (out / 'opener.jsonl').touch()
                with (out / 'app.log').open('w') as log:
                    proc = subprocess.Popen(['dbus-run-session', '--', str(args.binary)], env=env,
                                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    samples, previous = [], {}
                    begin = last = time.monotonic()
                    try:
                        while proc.poll() is None and time.monotonic() - begin < 57:
                            time.sleep(.5)
                            now = time.monotonic()
                            observed = processes(proc.pid)
                            ticks = sum(max(0, row['ticks'] - previous[pid]['ticks']) for pid, row in observed.items()
                                        if pid in previous)
                            samples.append({'startSeconds': last - begin, 'endSeconds': now - begin,
                                            'cpuPercent': ticks / os.sysconf('SC_CLK_TCK') / (now - last) * 100,
                                            'webProcesses': len(observed)})
                            if sum(row['rss'] for row in observed.values()) > 1800 * 1048576:
                                raise RuntimeError('Own web-process RSS exceeded the experiment bound')
                            previous, last = observed, now
                        if proc.poll() is not None:
                            raise RuntimeError('Test application exited early')
                    finally:
                        base.stop_own(proc)
                events = base.rows(out / 'native-trace.jsonl')
                states = [{**e['ownFixtureState'], 'sampledAtSeconds': e['monotonicUs'] / 1000000 - begin} for e in events
                          if e.get('ownFixtureState', {}).get('experiment') == 'active-frame-lifecycle-v1'
                          and all(f.get('instance') for f in e['ownFixtureState']['frames'])]
                if not states or states[-1]['phase'] != 'stopped':
                    raise ValueError('Fixture did not complete all phases')
                result = summarize(states, samples, args.disable_rich_render)
                result.update(binarySha256=base.digest(args.binary), helperDisabled=args.disable_rich_render,
                              webkitVersion=subprocess.check_output(['pkg-config', '--modversion', 'webkit2gtk-4.1'], text=True).strip(),
                              openerInvocations=len(base.rows(out / 'opener.jsonl')),
                              limitations=['Synthetic eight continuously animated srcdoc charts; no hosted Canvas or private conversation.',
                                           'Dedicated Xvfb and software rendering; not the reporter\'s Wayland/GPU environment.',
                                           'One native state query per second and frame reports are part of both A/B runs.',
                                           'Phase CPU windows use native monotonic query timestamps; fixture state can be up to 0.5 seconds old.',
                                           'This is diagnostic evidence, not a fix or proof of the original issue\'s cause.'])
                result['ok'] = result['allFrameDocumentsAndSyntheticDraftsPreserved'] and result['openerInvocations'] == 0
                base.write(out / 'result.json', result)
                base.write(out / 'cpu-samples.json', samples)
                print(json.dumps({'ok': result['ok'], 'output': str(out), 'helperDisabled': args.disable_rich_render}))
                return 0 if result['ok'] else 1
        finally:
            base.stop_own(wm)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--disable-rich-render', action='store_true')
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args()
    args.binary = args.binary.resolve(strict=True)
    args.output = args.output.resolve()
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        p.error('Output directory must be empty')
    (args.output / 'fixture.html').write_bytes((HERE / 'fixture.html').read_bytes())
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'webkit2gtk-4.1'], text=True))
    subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-DVIBEZ_CHART_POLL_COUNT=60', str(CHARTS / 'observer.c'), '-o', str(args.output / 'observer.so'),
                    *flags, '-ldl'], check=True)
    base.write(args.output / 'metadata.json', {'binarySha256': base.digest(args.binary),
               'fixtureSha256': base.digest(HERE / 'fixture.html'), 'runnerSha256': base.digest(Path(__file__)),
               'observerSha256': base.digest(CHARTS / 'observer.c'), 'helperDisabled': args.disable_rich_render,
               'display': 'Dedicated Xvfb; disposable profile and private D-Bus; no existing client touched',
               'rendering': 'X11; LIBGL_ALWAYS_SOFTWARE=1',
               'inheritedDriverOverrides': {key: os.environ[key] for key in ('MESA_LOADER_DRIVER_OVERRIDE',
                   'GALLIUM_DRIVER', 'DRI_PRIME', '__GLX_VENDOR_LIBRARY_NAME') if key in os.environ}})
    command = ['xvfb-run', '-a', '-s', '-screen 0 1600x1000x24', sys.executable, str(Path(__file__).resolve()),
               '--worker', '--binary', str(args.binary), '--output', str(args.output)]
    if args.disable_rich_render:
        command.append('--disable-rich-render')
    return subprocess.call(command, env=base.clean_env())


if __name__ == '__main__':
    raise SystemExit(main())
