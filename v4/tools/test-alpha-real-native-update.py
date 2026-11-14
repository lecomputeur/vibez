#!/usr/bin/env python3
"""Apply a genuine signed Alpha package using the previous production app.

Linux uses an owned Xvfb/private D-Bus/profile. Mac/Windows execution is allowed
only on an otherwise empty disposable GitHub-hosted runner. This is the actual
staged-install path, not a simulated installer or an invented version. No real
Mistral credentials are used: profile-preservation markers are explicitly dummy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time

BASE = Path(__file__).resolve().parents[1]
APP = 'nl.lecomputeur.vibez4.alpha'
VERSION = re.compile(r'^4\.\d+\.\d+-(?:alpha|beta)\.[1-9]\d*$')
PROTECTED = ('GH_TOKEN', 'GITHUB_TOKEN', 'MAC_CERTIFICATE_P12_BASE64', 'MAC_CERTIFICATE_PASSWORD',
             'APPLE_API_KEY_P8_BASE64', 'APPLE_API_KEY_ID', 'APPLE_API_ISSUER', 'APPLE_TEAM_ID',
             'TAURI_SIGNING_PRIVATE_KEY', 'TAURI_SIGNING_PRIVATE_KEY_PATH', 'TAURI_SIGNING_PRIVATE_KEY_PASSWORD')


def require(value, message):
    if not value:
        raise AssertionError(message)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(command, **kwargs):
    return subprocess.check_output([str(x) for x in command], stderr=subprocess.STDOUT, **kwargs)


def version(executable, expected, env):
    found = run([executable, '--version'], env=env, text=True, timeout=20)
    require('VibeZ V4 ' in found and expected in found, 'Installed app reports an unexpected Alpha version')
    return found.strip()


def stop(process):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def native_ci_only(target):
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted',
            'Native update execution is restricted to disposable GitHub-hosted runners')
    require(sys.platform == ('darwin' if target.startswith('macos') else 'win32'), 'Wrong native OS')
    require(not any(os.environ.get(key) for key in PROTECTED), 'App execution must not inherit build/download/signing credentials')


def profile_paths(target, env):
    if target == 'linux-appimage':
        return (Path(env['XDG_CONFIG_HOME']) / APP, Path(env['XDG_DATA_HOME']) / APP,
                Path(env['XDG_CACHE_HOME']) / APP)
    if target.startswith('macos'):
        return (Path.home() / 'Library/Application Support' / APP,
                Path.home() / 'Library/Application Support' / APP,
                Path.home() / 'Library/Caches' / APP)
    return (Path(env['APPDATA']) / APP, Path(env['APPDATA']) / APP, Path(env['LOCALAPPDATA']) / APP)


def seed_profile(target, env, work):
    config, data, cache = profile_paths(target, env)
    # CI uses a brand-new runner; refusing existing profiles is intentional.
    # Linux paths were made private by our parent, but the app ID is still new.
    for path in set((config, data, cache)):
        require(not path.exists(), 'Refusing to use an existing Alpha profile: ' + str(path))
    for path in set((config, data, cache)):
        path.mkdir(parents=True, mode=0o700)
    folders = [work / 'linked-workspace', work / 'linked-chat-workspace', work / 'linked-code-workspace']
    for path in folders:
        path.mkdir(); (path / 'unchanged.txt').write_bytes(b'Update fixture workspace: do not modify.\n')
    settings = config / 'language.json'; settings.write_text('{"language":"de"}\n', encoding='utf-8')
    fixture_profile = data / 'webview/update-preservation-marker.bin'
    fixture_profile.parent.mkdir(parents=True)
    fixture_profile.write_bytes(b'Dummy anonymous WebKit profile marker; NOT a real sign-in token.\n')
    standalone = data / 'standalone/web-connector'; standalone.mkdir(parents=True)
    ids = ['00000000-0000-4000-8000-000000000071', 'chat-00000000-0000-4000-8000-000000000072',
           'code-00000000-0000-4000-8000-000000000073']
    projects = {}
    for index, (key, folder) in enumerate(zip(ids, folders)):
        value = {'id': key, 'name': 'Update fixture ' + str(index), 'folder': str(folder),
                 'token': 'disposable-update-fixture-not-a-real-token-00000000' + str(index),
                 'manually_paused': True}
        value['auto_approved'] = hashlib.sha256(json.dumps([key,str(folder),value['token']],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        if key.startswith('chat-'):
            value.update(kind='conversation', conversation_id=key[5:], draft=False,
                         url='https://chat.mistral.ai/work/' + key[5:])
        elif key.startswith('code-'):
            value['url'] = 'https://chat.mistral.ai/code/' + key[5:]
        else:
            value['url'] = 'https://chat.mistral.ai/work/projects/' + key
        projects[key] = value
    bindings = standalone / 'web-projects.json'
    bindings.write_text(json.dumps({'projects': projects, 'project_metadata': {}, 'project_activity': {}}), encoding='utf-8')
    (work / 'expected-bindings.json').write_text(json.dumps(projects),encoding='utf-8')
    stable_marker = work / 'stable-3.0.9-sentinel.bin'
    stable_marker.write_bytes(b'Stable 3.0.9 isolation sentinel; not an installed app.\n')
    paths = [settings, fixture_profile, bindings, stable_marker, *(path / 'unchanged.txt' for path in folders)]
    return cache, {str(path): digest(path) for path in paths}


def markers_unchanged(markers):
    require(all(Path(path).is_file() and digest(Path(path)) == value for path, value in markers.items()),
            'The update changed a preserved profile/settings/binding/workspace marker')


BINDING_CHECK = r'''
import importlib.util,json,sys
from pathlib import Path
backend,directory,expected=map(Path,sys.argv[1:])
spec=importlib.util.spec_from_file_location('update_profile_connector',backend/'web_connector.py')
value=importlib.util.module_from_spec(spec);sys.modules[spec.name]=value;spec.loader.exec_module(value)
connector=value.Connector(lambda message:None,directory)
try:
 wanted=json.loads(expected.read_text(encoding='utf-8'))
 assert connector.projects==wanted,'The bundled backend did not load the real seeded project bindings'
 assert len(connector.projects)==3 and any(k.startswith('chat-') for k in connector.projects) and any(k.startswith('code-') for k in connector.projects)
 assert all(connector.auto_approved(key) for key in connector.projects),'Previously approved folder fingerprints were not preserved'
 assert all(not connector.can_auto_connect(key) and row['manually_paused'] for key,row in connector.projects.items()),'A manually paused fixture binding was resumed'
 assert all(Path(row['folder'],'unchanged.txt').is_file() for row in connector.projects.values())
 print(json.dumps({'passed':True,'actual_bundled_connector_loaded_profile':True,'binding_count':len(connector.projects),'work_code_conversation_bindings_loaded':True,'approval_fingerprints_valid':True,'manual_pause_preserved':True}))
finally:connector.close()
'''


def check_bundled_bindings(backend, runtime, target, env, work, phase):
    data=profile_paths(target,env)[1]
    checked=json.loads(run([runtime,'-I','-B','-X','utf8','-c',BINDING_CHECK,backend,
        data/'standalone/web-connector',work/'expected-bindings.json'],env=env,text=True,timeout=30))
    require(checked.get('passed') and checked.get('actual_bundled_connector_loaded_profile'),
            'Actual bundled backend did not verify preserved bindings')
    (work/('bundled-profile-'+phase+'.json')).write_text(json.dumps(checked,indent=2)+'\n')
    return checked


def check_appimage_bindings(package, target, env, work, phase):
    mount=None
    try:
        mount=subprocess.Popen([str(package),'--appimage-mount'],env=env,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        path=mount.stdout.readline().strip()
        (work/('appimage-mount-'+phase+'.json')).write_text(json.dumps({'mountpoint':path})+'\n')
        resolved=Path(path).resolve()
        roots=[Path('/tmp'),Path(env['TMPDIR']).resolve()]
        require(path and any(resolved!=root and resolved.is_relative_to(root) for root in roots)
                and resolved.is_dir() and mount.poll() is None,
                'Cannot mount actual AppImage for profile loading check')
        backend=resolved/'usr/lib/VibeZ V4 Alpha/backend'
        require((backend/'web_connector.py').is_file(),'AppImage has no packaged connector')
        return check_bundled_bindings(backend,Path('/usr/bin/python3'),target,env,work,phase)
    finally:
        stop(mount)
        if mount:
            mount.stdout.close();mount.stderr.close()


def unix_app_processes(executable):
    prefix = str(executable)
    result = []
    for row in run(['ps', '-axo', 'pid=,command='], text=True).splitlines():
        pid, _, command = row.strip().partition(' ')
        if pid.isdigit() and (command == prefix or command.startswith(prefix + ' ')):
            result.append(int(pid))
    return result


def linux_descendants(parent):
    """Capture owned children even if the backend deliberately has its own PGID."""
    table = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            table[int(path.name)] = (int(fields[1]), fields[19])
        except (OSError, ValueError, IndexError): pass
    found = {parent}
    while True:
        extra = {pid for pid, (ppid, _) in table.items() if ppid in found}
        if extra <= found: break
        found |= extra
    return {pid: started for pid, (_, started) in table.items() if pid in found}


def linux_fixture_processes(work):
    """An app restart may reparent B before A exits; identify only our mount/exe."""
    owned={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            image=Path(os.readlink(path/'exe').removesuffix(' (deleted)'))
            if any(image.is_relative_to(work/name) for name in ('installed','tmp')):
                owned.update(linux_descendants(int(path.name)))
        except (OSError,ValueError):pass
    return owned


def stage(cache, feed, package, target):
    body = json.loads(feed.read_text(encoding='utf-8'))
    require(VERSION.fullmatch(body['version']), 'Malformed target release')
    wanted = {'linux-appimage': 'linux-x86_64-appimage', 'macos-x64': 'darwin-x86_64-app',
              'macos-arm64': 'darwin-aarch64-app', 'windows-nsis': 'windows-x86_64-nsis',
              'windows-msi': 'windows-x86_64-msi'}[target]
    require(wanted in body['platforms'], 'The signed update feed lacks this installer target')
    asset = body['platforms'][wanted]
    require(asset['url'].endswith('/' + package.name), 'Package name differs from the signed release feed')
    require(isinstance(asset['signature'], str) and len(asset['signature']) > 100, 'No real package signature')
    directory = cache / 'alpha-update'; directory.mkdir(parents=True, mode=0o700)
    shutil.copy2(package, directory / 'package')
    (directory / 'package').chmod(0o600)
    (directory / 'release.json').write_text(json.dumps(body), encoding='utf-8')
    (directory / 'release.json').chmod(0o600)
    return directory, body['version']


def linux_prepare(work):
    env = dict(os.environ)
    for key in [*PROTECTED, 'DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'DBUS_STARTER_ADDRESS',
                'DBUS_STARTER_BUS_TYPE', 'AT_SPI_BUS_ADDRESS', 'VIBEZ_SAFE_OUTPUT', 'APPIMAGE', 'APPDIR',
                'LD_LIBRARY_PATH', 'PYTHONPATH', 'PYTHONHOME', 'GNOME_KEYRING_CONTROL', 'GNOME_KEYRING_PID',
                'SSH_AUTH_SOCK', 'SSH_AGENT_PID', 'GPG_AGENT_INFO']:
        env.pop(key, None)
    for key, folder in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache'),
                        ('XDG_STATE_HOME', 'state'), ('TMPDIR', 'tmp')]:
        path = work / folder; path.mkdir(mode=0o700); env[key] = str(path)
    runtime = Path(tempfile.mkdtemp(prefix='vibez-real-update-runtime-'))
    env.update(XDG_RUNTIME_DIR=str(runtime), GDK_BACKEND='x11', GSETTINGS_BACKEND='memory',
               GIO_USE_VFS='local', LIBGL_ALWAYS_SOFTWARE='1', WEBKIT_DISABLE_COMPOSITING_MODE='1',
               NO_AT_BRIDGE='1', DBUS_SYSTEM_BUS_ADDRESS='unix:path=' + str(runtime / 'no-system-bus'),
               PULSE_SERVER='unix:' + str(runtime / 'no-pulse'))
    authority = work / 'xauthority'; authority.touch(mode=0o600); env['XAUTHORITY'] = str(authority)
    bus = work / 'session-bus.conf'
    bus.write_text('<busconfig><type>session</type><listen>unix:tmpdir=' + str(runtime) +
        '</listen><auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/>' +
        '<allow receive_sender="*"/><allow own="*"/></policy></busconfig>\n')
    return env, runtime, bus


def verify_unix(args):
    target, work = args.target, args.work.resolve()
    require(not work.exists(), 'The update fixture directory must be new')
    work.mkdir(parents=True)
    native = not target == 'linux-appimage'
    if native:
        native_ci_only(target)
        env = dict(os.environ); runtime = bus = None
    else:
        require(sys.platform.startswith('linux'), 'AppImage transition requires Linux')
        env, runtime, bus = linux_prepare(work)
    report = {'passed': False, 'from_version': args.from_version,
              'to_version': json.loads(args.feed.read_text())['version'], 'target': target,
              'actual_previous_production_app': True, 'actual_signed_target_package': True,
              'test_route': 'Production apply_staged at next app startup; package/feed staged locally',
              'network_download_route_tested': False, 'real_mistral_sign_in_tested': False,
              'dummy_profile_markers_only': True, 'existing_user_profile_used': False,
              'existing_user_installation_changed': False, 'physical_user_displays_used': False,
              'stable_sentinel_is_not_installed_309': True,
              'input_sha256': {'from_package': digest(args.from_package), 'to_package': digest(args.to_package), 'feed': digest(args.feed)}}
    server = process = bus_process = None; streams = []; owned = {}
    try:
        if target == 'linux-appimage':
            installed = work / 'installed'; installed.mkdir()
            executable = installed / 'VibeZ-V4-Alpha.AppImage'
            shutil.copy2(args.from_package, executable); executable.chmod(0o755)
            display_binary = BASE / 'artifacts/native-test-tools/root/usr/bin/Xvfb'
            require(display_binary.is_file(), 'Owned virtual X server is absent')
            read_fd, write_fd = os.pipe(); xlog = (work / 'xvfb.log').open('w'); streams.append(xlog)
            server = subprocess.Popen([str(display_binary), '-displayfd', str(write_fd), '-screen', '0',
                '1600x1000x24', '-nolisten', 'tcp', '-ac'], env=env, pass_fds=(write_fd,),
                stdout=xlog, stderr=subprocess.STDOUT, start_new_session=True)
            os.close(write_fd)
            with os.fdopen(read_fd) as read: display = read.readline().strip()
            require(display.isdigit() and server.poll() is None, 'The private display failed')
            env['DISPLAY'] = ':' + display
            # Keep the bus independently alive: dbus-run-session would kill it
            # when the original A process exits for its legitimate B restart.
            buslog=(work/'dbus.log').open('w');streams.append(buslog)
            bus_process=subprocess.Popen(['dbus-daemon','--config-file='+str(bus),'--nofork','--print-address=1'],
                env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=buslog,text=True,start_new_session=True)
            address=bus_process.stdout.readline().strip()
            require(address.startswith('unix:') and bus_process.poll() is None,'Private persistent D-Bus failed')
            env['DBUS_SESSION_BUS_ADDRESS']=address
            command_prefix = []
        else:
            installed = work / 'installed'; installed.mkdir()
            with tarfile.open(args.from_package, 'r:gz') as archive:
                require(all(entry.name == 'VibeZ V4 Alpha.app' or entry.name.startswith('VibeZ V4 Alpha.app/') for entry in archive), 'Unexpected previous Mac archive paths')
                archive.extractall(installed, filter='data')
            app = installed / 'VibeZ V4 Alpha.app'
            run(['codesign', '--verify', '--deep', '--strict', app], env=env)
            executable = app / 'Contents/MacOS/vibez4-alpha'
            command_prefix = []
        version(executable, args.from_version, env)
        cache, markers = seed_profile(target, env, work)
        if target=='linux-appimage':
            before_bindings=check_appimage_bindings(executable,target,env,work,'before')
        else:
            before_bindings=check_bundled_bindings(app/'Contents/Resources/backend',
                app/'Contents/Resources/python-runtime/bin/python3',target,env,work,'before')
        markers_unchanged(markers)
        staged, expected = stage(cache, args.feed, args.to_package, target)
        require(expected != args.from_version, 'A real newer target version is required')
        log = (work / 'transition.log').open('w'); streams.append(log)
        process = subprocess.Popen([*command_prefix, str(executable)], env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + 90; actual_window = False
        while time.monotonic() < deadline:
            if target == 'linux-appimage':
                owned.update(linux_descendants(process.pid))
                owned.update(linux_fixture_processes(work))
                if digest(executable) == digest(args.to_package):
                    tree = run(['xwininfo', '-root', '-tree'], env=env, text=True)
                    if 'VibeZ V4 ' in tree and expected in tree:
                        (work / 'updated-window-tree.txt').write_text(tree)
                        actual_window = True; break
            elif not (staged / 'release.json').exists():
                if (expected in run([executable, '--version'], env=env, text=True, timeout=20)
                        and unix_app_processes(executable)):
                    actual_window = True; break
            require(process.poll() is None or target.startswith('macos') or digest(executable)==digest(args.to_package),
                    'Previous app exited before installing the update')
            time.sleep(.25)
        require(actual_window, 'The previous app did not install/start the expected signed update; see transition.log')
        require(not (staged / 'release.json').exists() and not (staged / 'package').exists(), 'Successful update staging was not cleaned up')
        version(executable, expected, env)
        markers_unchanged(markers)
        if target=='linux-appimage':
            after_bindings=check_appimage_bindings(executable,target,env,work,'after')
        else:
            after_bindings=check_bundled_bindings(app/'Contents/Resources/backend',
                app/'Contents/Resources/python-runtime/bin/python3',target,env,work,'after')
        markers_unchanged(markers)
        if native:
            run(['codesign', '--verify', '--deep', '--strict', app], env=env)
            run(['spctl', '--assess', '--type', 'execute', '--verbose=4', app], env=env)
        # Keep the actual updated app alive briefly, then check again.
        time.sleep(5); markers_unchanged(markers)
        if target == 'linux-appimage':
            tree = run(['xwininfo', '-root', '-tree'], env=env, text=True)
            require(expected in tree, 'Updated app did not remain running')
        else:
            require(unix_app_processes(executable), 'Updated Mac app did not remain running')
        report.update(passed=True, previous_app_installed_new_signed_payload=True,
            current_version=expected, automatic_next_start_apply=True, startup_after_update_verified=True,
            settings_bytes_preserved=True, webview_dummy_profile_marker_preserved=True,
            project_and_conversation_bindings_preserved=True, manually_paused_bindings_preserved=True,
            work_code_and_chat_bindings_loaded_by_actual_previous_backend=before_bindings,
            work_code_and_chat_bindings_loaded_by_actual_updated_backend=after_bindings,
            linked_workspace_file_bytes_preserved=True, stable_sentinel_bytes_preserved=True,
            staging_cleaned_after_install=True, markers_sha256=markers)
    except Exception as error:
        report['error'] = str(error)
    finally:
        if process is not None and target == 'linux-appimage':
            owned.update(linux_descendants(process.pid));owned.update(linux_fixture_processes(work))
        stop(process)
        for pid, started in owned.items():
            try:
                current = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
                if current[19] == started: os.kill(pid, signal.SIGTERM)
            except (OSError, IndexError): pass
        stop(bus_process);stop(server)
        if bus_process:bus_process.stdout.close()
        if native:
            # The app can restart through LaunchServices outside our process group.
            listing = run(['ps', '-axo', 'pid=,command='], text=True)
            prefix = str(work / 'installed')
            for row in listing.splitlines():
                pid, _, command = row.strip().partition(' ')
                if pid.isdigit() and command.startswith(prefix + '/'):
                    try: os.kill(int(pid), signal.SIGTERM)
                    except ProcessLookupError: pass
        for stream in streams: stream.close()
        if runtime: shutil.rmtree(runtime, ignore_errors=True)
        # CI directories belong to this runner and were verified absent above.
        # Keep reports and fixture data for inspection; never touch user profiles.
    (work / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=['linux-appimage', 'macos-x64', 'macos-arm64'], required=True)
    parser.add_argument('--from-version', required=True)
    parser.add_argument('--from-package', type=Path, required=True)
    parser.add_argument('--to-package', type=Path, required=True)
    parser.add_argument('--feed', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    require(VERSION.fullmatch(args.from_version), 'Invalid previous Alpha version')
    for key in ('from_package', 'to_package', 'feed'):
        setattr(args, key, getattr(args, key).resolve(strict=True))
    return verify_unix(args)


if __name__ == '__main__':
    raise SystemExit(main())
