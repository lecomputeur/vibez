#!/usr/bin/env python3
"""Controlled Linux routing regression on an unchanged old/candidate executable.

Always owns a new Xvfb, Openbox, DBus session and short /tmp profile. The preload
replaces one initial document and observes signals; application policy is real.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
CF = 'https://canvas.mistralusercontent.com'
FRAME_CASES = ('unnamed', 'named', 'unnamed-retry')


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    if not path.exists():
        return []
    # The app appends small single records. Ignore only an unfinished last line.
    text = path.read_text()
    lines = text.splitlines()
    if text and not text.endswith('\n'):
        lines = lines[:-1]
    return [json.loads(line) for line in lines if line]


def stop_own(proc):
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=8)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)


def clean_env():
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('VIBEZ_', 'WEBKIT_', 'DBUS_STARTER_')) or key in (
                'LD_PRELOAD', 'DBUS_SESSION_BUS_ADDRESS', 'GNOME_KEYRING_CONTROL',
                'GNOME_KEYRING_PID', 'GDK_SCALE', 'GDK_DPI_SCALE'):
            env.pop(key, None)
    env.update(GDK_BACKEND='x11', GDK_SCALE='1', GDK_DPI_SCALE='1', LIBGL_ALWAYS_SOFTWARE='1', GIO_USE_VFS='local')
    return env


def profile_env(profile, output):
    env = clean_env()
    for key, name in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                      ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state'),
                      ('XDG_RUNTIME_DIR', 'runtime')]:
        folder = profile / name
        folder.mkdir(mode=0o700)
        env[key] = str(folder)
    # Ordinary startup, with update checks disabled only in our disposable profile.
    config = profile / 'config' / 'nl.lecomputeur.vibez3'
    config.mkdir(mode=0o700)
    write(config / 'settings.json', {'schema_version': 1, 'settings': {
        'language': 'en', 'zoom_factor': 1.0, 'show_screenshot': True,
        'close_to_tray': False, 'start_at_login': False, 'auto_updates': False}})
    env['PATH'] = str(HERE / 'opener-recorder') + os.pathsep + env['PATH']
    env['VIBEZ_CANVAS_OPEN_LOG'] = str(output / 'opener.jsonl')
    return env


@contextmanager
def disposable_profile(output, prefix):
    profile = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield profile
    finally:
        # Private DBus-activated portal/GVFS services can leave a disconnected
        # FUSE mount while terminating. Record cleanup failure separately; it
        # must not discard a completed native test or conceal its failed gates.
        try:
            shutil.rmtree(profile)
        except OSError as error:
            write(output / 'profile-cleanup-warning.json', {
                'profile': str(profile), 'errno': error.errno,
                'reason': 'Disposable private-session profile cleanup failed; no user profile is involved.'})


def check_report(events, opens, expected):
    states=[event['ownFixtureState'] for event in events if event.get('ownFixtureState',{}).get('controlledFixture')]
    last=states[-1] if states else {};scenario=last.get('scenario');target='https://canvas.mistralusercontent.com' if scenario=='canvas' else 'https://accounts.google.com'
    def count(kind,case,origin):return sum(event.get('event')==kind and event.get('fixtureCase')==case and event.get('origin')==origin for event in events)
    external_opens=sum(row.get('fixtureCase')=='external-normal' for row in opens)
    external_starts=count('resource-load-started','external-normal','https://example.com')
    probes=[event.get('probe',{}) for event in events if event.get('event')=='auxiliary-probe']
    checks={
      'fixture finished':last.get('finished') is True,
      'trusted popup click':last.get('popupEventTrusted') is True,
      'blank popup retained':last.get('popupReturnedNull') is False,
      'blank child script ran':last.get('bootstrapMessages')==1,
      'nested srcdoc script ran':last.get('srcdocMessages')==1,
      'challenge frame native callback observed':count('policy-observed','unnamed','https://challenges.cloudflare.com')>=1,
      'challenge frame request started':count('resource-load-started','unnamed','https://challenges.cloudflare.com')==1,
      'expected final target request started':count('resource-load-started','preview-popup',target)==1,
      'external target follows intended popup purpose':external_opens==(1 if scenario=='canvas' else 0) and external_starts==(0 if scenario=='canvas' else 1),
      'related popup retains opener':any(p.get('openerPresent') is True for p in probes),
      'optional native state probe returned no successful native state':not any(p.get('nativeIPC')=='UNSAFE' for p in probes),
      'no real browser launched':all(row.get('browserStarted') is False for row in opens),
    }
    return {'ok':all(checks.values()),'scenario':scenario,'checks':checks,'finalFixtureState':last,'externalOpenerInvocations':external_opens,'externalResourceStarts':external_starts,'challengeResourceStarts':count('resource-load-started','unnamed','https://challenges.cloudflare.com'),'targetResourceStarts':count('resource-load-started','preview-popup',target),'optionalRemoteIPCProbe':{'observed':sorted({p.get('nativeIPC','unavailable') for p in probes if p.get('kind')=='canvas-popup'}),'explicitDenialConfirmed':any(p.get('nativeIPC')=='denied' for p in probes)},'limitations':['Synthetic blank-popup and srcdoc flow; not a real Canvas or identity-provider login.','Deliberately nonexistent remote paths; resource starts do not imply accepted service requests.','Optional remote IPC may stay pending; that is not explicit privilege-denial proof. The separate native smoke checks actual rejected IPC in local OAuth models.']}


def controlled(args, output):
    (output / 'opener.jsonl').touch()
    start = time.monotonic()
    with disposable_profile(output, 'vz-ts-') as profile:
        env = profile_env(profile, output)
        env.update(VIBEZ_CANVAS_MODE='controlled-html', VIBEZ_CANVAS_FIXTURE=str(output / 'fixture.html'),
                   VIBEZ_CANVAS_NATIVE_LOG=str(output / 'native-trace.jsonl'), LD_PRELOAD=str(output / 'observer.so'))
        settled = None
        with (output / 'app.log').open('w') as log:
            proc = subprocess.Popen(['dbus-run-session', '--', str(args.binary)], env=env,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                while proc.poll() is None and time.monotonic() - start < args.timeout:
                    events = rows(output / 'native-trace.jsonl')
                    opens = rows(output / 'opener.jsonl')
                    finished = any(event.get('ownFixtureState', {}).get('finished') is True for event in events)
                    # Always observe several seconds after requests, independently of expected pass/fail.
                    if finished:
                        if settled is None:
                            settled = time.monotonic()
                        if time.monotonic() - settled >= 5:
                            break
                    time.sleep(0.2)
                exited_early = proc.poll() is not None
            finally:
                stop_own(proc)
        result = check_report(rows(output / 'native-trace.jsonl'), rows(output / 'opener.jsonl'), args.expect)
        result.update(elapsedSeconds=time.monotonic() - start, appExitedBeforeObservation=exited_early,
                      binary=str(args.binary), binarySha256=digest(args.binary))
        if exited_early:
            result['ok'] = False
        write(output / 'result.json', result)
    return result


def smoke(args, output):
    output.mkdir()
    (output / 'opener.jsonl').touch()
    with disposable_profile(output, 'vz-ts-smoke-') as profile:
        env = profile_env(profile, output)
        with (output / 'app.log').open('w') as log:
            proc = subprocess.Popen(['dbus-run-session', '--', str(args.binary), '--smoke-test', '--update-download-probe'],
                                    env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = proc.wait(timeout=240)
            except subprocess.TimeoutExpired:
                code = None
            finally:
                stop_own(proc)
        text = (output / 'app.log').read_text(errors='replace')
        required = ('SMOKE_OK:', 'HISTORY_OK:', 'LANGUAGE_BOOTSTRAP_OK:', 'HIDDEN_OK:')
        popups = [line for line in text.splitlines() if line.startswith('POPUP_OK:')]
        result = {'ok': code == 0 and all(marker in text for marker in required) and len(popups) == 2,
                  'exitCode': code, 'markers': {marker: marker in text for marker in required},
                  'popupChecks': popups, 'nativeOpenerInvocations': len(rows(output / 'opener.jsonl')),
                  'scope': 'Existing native smoke: related/nested local OAuth-model popups, opener/postMessage callbacks, denied IPC; no provider login.'}
        write(output / 'result.json', result)
    return result


def private_worker(args):
    if os.environ.get('VIBEZ_CANVAS_PRIVATE_XVFB') != '1' or not os.environ.get('DISPLAY'):
        raise SystemExit('Private worker must be launched by this test runner under its own Xvfb.')
    with (args.output / 'openbox.log').open('w') as log:
        wm = subprocess.Popen(['openbox', '--sm-disable'], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            time.sleep(0.7)
            if wm.poll() is not None:
                raise RuntimeError('Private Openbox failed to start')
            result = controlled(args, args.output)
            if args.with_smoke:
                result['nativeSmoke'] = smoke(args, args.output / 'native-smoke')
                result['ok'] = result['ok'] and result['nativeSmoke']['ok']
                write(args.output / 'result.json', result)
        finally:
            stop_own(wm)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--expect', choices=('old', 'fixed'), required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--with-smoke', action='store_true')
    parser.add_argument('--scenario', choices=('canvas','oauth'), required=True)
    parser.add_argument('--timeout', type=float, default=35)
    parser.add_argument('--_private-worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.binary = args.binary.resolve(strict=True)
    args.output = args.output.resolve()
    if args._private_worker:
        return private_worker(args)
    if platform.system() != 'Linux' or args.timeout < 12:
        parser.error('Linux and a timeout of at least 12 seconds are required')
    for tool in ('cc', 'pkg-config', 'xvfb-run', 'Xvfb', 'openbox', 'dbus-run-session'):
        if not shutil.which(tool):
            parser.error(f'Required test dependency is unavailable: {tool}; no system changes were made')
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error('Output directory must be empty; stale evidence cannot pass a rerun')
    (args.output / 'fixture.html').write_text((HERE / 'bootstrap.html').read_text().replace('__SCENARIO__', args.scenario))
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'webkit2gtk-4.1'], text=True))
    command = ['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror', str(HERE / 'observer.c'),
               '-o', str(args.output / 'observer.so'), *flags, '-ldl']
    subprocess.run(command, check=True)
    write(args.output / 'metadata.json', {'binary': str(args.binary), 'binarySha256': digest(args.binary),
        'expectation': args.expect, 'platform': platform.platform(),
        'webkitVersion': subprocess.check_output(['pkg-config', '--modversion', 'webkit2gtk-4.1'], text=True).strip(),
        'display': 'Dedicated Xvfb 1600x1000x24 with Openbox; never the inherited desktop',
        'profile': 'New disposable short /tmp directory for each app run', 'bus': 'New dbus-run-session for each app run',
        'renderer': 'LIBGL_ALWAYS_SOFTWARE=1 for this isolated virtual display',
        'compileCommand': command, 'harnessSha256': {str(path.relative_to(HERE)): digest(path)
            for path in sorted(HERE.rglob('*')) if path.is_file() and '__pycache__' not in str(path)}})
    env = clean_env()
    env['VIBEZ_CANVAS_PRIVATE_XVFB'] = '1'
    command = ['xvfb-run', '-a', '-s', '-screen 0 1600x1000x24', sys.executable, str(Path(__file__).resolve()),
               '--_private-worker', '--binary', str(args.binary), '--expect', args.expect,
               '--output', str(args.output), '--timeout', str(args.timeout), '--scenario', args.scenario]
    if args.with_smoke:
        command.append('--with-smoke')
    proc = subprocess.Popen(command, env=env, start_new_session=True)
    try:
        return proc.wait(timeout=args.timeout + (260 if args.with_smoke else 0) + 35)
    finally:
        stop_own(proc)


if __name__ == '__main__':
    raise SystemExit(main())
