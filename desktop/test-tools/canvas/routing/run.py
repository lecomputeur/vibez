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
    fixture = [event['ownFixtureState'] for event in events
               if event.get('ownFixtureState', {}).get('controlledFixture') is True]
    last = fixture[-1] if fixture else {}
    def matching(event, kind, case):
        return event.get('event') == kind and event.get('fixtureCase') == case
    nav = {case: [event for event in events if matching(event, 'policy-observed', case)
                 and event.get('type') == 'navigation-action' and event.get('origin') == CF]
           for case in FRAME_CASES}
    started = {case: [event for event in events if matching(event, 'resource-load-started', case)
                     and event.get('origin') == CF] for case in FRAME_CASES}
    responses = {case: [event for event in events if matching(event, 'policy-observed', case)
                       and event.get('type') == 'response' and event.get('origin') == CF]
                 for case in FRAME_CASES}
    create = [event for event in events if matching(event, 'create-request-observed', 'preview-popup')
              and event.get('origin') == CF]
    preview_opens = [row for row in opens if row.get('canvasPreviewTarget')]
    external_opens = [row for row in opens if row.get('fixtureCase') == 'external-normal'
                      and row.get('origin') == 'https://example.com']
    windows = [event['ownWebviewWindows'] for event in events if event.get('event') == 'own-window-count']
    checks = []
    def add(name, passed, evidence=None):
        checks.append({'name': name, 'passed': bool(passed), 'evidence': evidence})
    add('Native signal observers installed without changing application handlers',
        all(any(event.get('event') == 'observer-installed' and event.get('signal') == name
                and event.get('hookInstalled') is True for event in events) for name in ('decide-policy', 'create')))
    add('Exactly one controlled document replacement',
        sum(event.get('event') == 'controlled-html-replacement' for event in events) == 1)
    add('Own fixture completed on public Mistral base origin', last.get('finished') is True
        and last.get('origin') == 'https://chat.mistral.ai', last)
    for case in FRAME_CASES:
        add(f'{case}: actual native NavigationAction callback', len(nav[case]) == 1, len(nav[case]))
    add('Preview popup reached actual native WebKit create callback', len(create) == 1, len(create))
    add('Popup test used a trusted event scoped to the own WebKit fixture', last.get('popupEventTrusted') is True
        and sum(event.get('event') == 'native-click-dispatched' and event.get('scopedToOwnWebview') is True for event in events) == 2)
    add('External link test used a trusted native LinkClicked action', last.get('externalEventTrusted') is True
        and any(event.get('fixtureCase') == 'external-normal' and event.get('userGesture') is True
            and event.get('navigationType') == 0 for event in events))
    add('Preview popup uses expected old/fixed in-app window contract', last.get('popupAttempted') is True
        and last.get('popupReturnedNull') is (expected == 'old'))
    add('Preview creates exactly one related window only in fixed build', bool(windows)
        and windows[0] == 1 and max(windows) == (2 if expected == 'fixed' else 1), {'first': windows[0] if windows else None, 'max': max(windows) if windows else None})
    aux=[event.get('probe',{}) for event in events if event.get('event')=='auxiliary-probe']
    if expected == 'fixed':
        popup=[row for row in aux if row.get('kind')=='canvas-popup']
        add('Canvas related popup retains opener', any(row.get('openerPresent') is True for row in popup),popup[-1:] if popup else [])
        add('Optional native state probe returned no successful native state', not any(row.get('nativeIPC')=='UNSAFE' for row in popup),popup[-1:] if popup else [])
        shell=[row for row in aux if row.get('kind')=='local-shell']
        add('Optional auth-mode probe returned no active authentication state', not any(row.get('authMode')=='active-or-unavailable' for row in shell),shell[-1:] if shell else [])
    add('Normal external navigation still invokes the native opener once', len(external_opens) == 1, len(external_opens))
    allowed_cases = {*FRAME_CASES, 'preview-popup', 'external-normal'}
    add('No unexpected opener target and no actual browser launched', all(row.get('fixtureCase') in allowed_cases
        and row.get('browserStarted') is False for row in opens), len(opens))
    fixed_contract = len(preview_opens) == 0 and all(started[case] for case in FRAME_CASES)
    add('Expected old/fixed controlled routing result',
        fixed_contract if expected == 'fixed' else len(preview_opens) == 4 and
        all(sum(row.get('fixtureCase') == case for row in preview_opens) == 1 for case in (*FRAME_CASES, 'preview-popup'))
        and not any(started.values()), {'expectation': expected, 'previewOpenerInvocations': len(preview_opens),
                                      'resourceStarts': {case: len(value) for case, value in started.items()}})
    for case in FRAME_CASES:
        add(f'{case}: any received response is independently classified as a subframe',
            all(event.get('mainFrameMainResource') is False for event in responses[case]),
            {'responseObserved': bool(responses[case]), 'statuses': [event.get('httpStatus') for event in responses[case]]})
    return {'ok': all(check['passed'] for check in checks), 'expectation': expected,
            'fixedContractPassed': expected == 'fixed' and all(check['passed'] for check in checks), 'checks': checks,
            'actualNativeFrameCallbacks': {case: len(value) for case, value in nav.items()},
            'actualPreviewPopupCreateCallbacks': len(create),
            'actualNativePreviewOpenerInvocations': len(preview_opens),
            'actualNormalExternalOpenerInvocations': len(external_opens),
            'actualCanvasResourceStarts': {case: len(value) for case, value in started.items()},
            'actualCanvasSubframeResponses': {case: [event.get('httpStatus') for event in value] for case, value in responses.items()},
            'actualBrowserStarted': False, 'nativeNavigationHandlersChanged': False,
            'controlledInitialDocumentReplacement': True, 'realCanvasPreviewTested': False,
            'optionalRemoteIPCProbe': {'observed': sorted({row.get('nativeIPC','unavailable') for row in aux if row.get('kind')=='canvas-popup'}), 'explicitDenialConfirmed': any(row.get('nativeIPC')=='denied' for row in aux)},
            'optionalLocalAuthProbe': {'observed': sorted({row.get('authMode','unavailable') for row in aux if row.get('kind')=='local-shell'}), 'inactiveConfirmed': any(row.get('authMode')=='inactive' for row in aux)},
            'frameNameUsedAsMainFrameOracle': False,
            'limitations': ['Synthetic routing URLs, not a real Canvas widget/preview or verification.',
                            'A resource-start event proves WebKit initiated a request, not that Canvas accepted or completed it.',
                            'Response status and native subframe classification are reported separately when available.',
                            'Canvas related-window behavior is observed through native create callback, non-null return, own-window counts and opener. Remote IPC may remain pending; that is not explicit denial. Separate native smoke validates local OAuth-model privilege rejection.',
                            'Local auth-mode diagnostics are optional and may be unavailable; no inactive-authentication claim follows from missing output.',
                            'This is the selected executable on this Linux WebKitGTK/Xvfb environment, not openSUSE.']}


def controlled(args, output):
    (output / 'opener.jsonl').touch()
    start = time.monotonic()
    with disposable_profile(output, 'vz-ts-') as profile:
        env = profile_env(profile, output)
        env.update(VIBEZ_CANVAS_MODE='controlled-html', VIBEZ_CANVAS_FIXTURE=str(HERE / 'fixture.html'),
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
                    if finished and any(row.get('fixtureCase') == 'external-normal' for row in opens):
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
               '--output', str(args.output), '--timeout', str(args.timeout)]
    if args.with_smoke:
        command.append('--with-smoke')
    proc = subprocess.Popen(command, env=env, start_new_session=True)
    try:
        return proc.wait(timeout=args.timeout + (260 if args.with_smoke else 0) + 35)
    finally:
        stop_own(proc)


if __name__ == '__main__':
    raise SystemExit(main())
