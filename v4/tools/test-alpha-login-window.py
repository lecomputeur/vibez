#!/usr/bin/python3
"""Exercise the feature-gated native login popup on a private virtual display.

No installed app, existing account/profile, physical monitor or backend is used.
The existing private Xvfb is preferred; --xvfb may name an equivalent binary.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import tempfile

BASE=Path(__file__).resolve().parents[1]


def stop(process):
    if process is None:
        return
    try:
        os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL)
        process.wait(timeout=4)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True,help='Native binary built with --features native-smoke')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--xvfb',type=Path,default=BASE/'artifacts/native-test-tools/root/usr/bin/Xvfb')
    args=parser.parse_args()
    binary=args.binary.resolve(strict=True);xvfb=args.xvfb.resolve(strict=True)
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    report={'passed':False,'binary':str(binary),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
        'host_displays_used':False,'existing_profiles_used':False,'host_installation_modified':False,
        'backend_started':False,'remote_mistral_accessed':False}
    with tempfile.TemporaryDirectory(prefix='vibez-login-smoke-') as temporary:
        root=Path(temporary)
        environment=dict(os.environ)
        for key in ['DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','DBUS_STARTER_ADDRESS',
            'DBUS_STARTER_BUS_TYPE','AT_SPI_BUS_ADDRESS','VIBEZ_SAFE_OUTPUT','BROADWAY_DISPLAY',
            'APPIMAGE','APPDIR','LD_LIBRARY_PATH','PYTHONPATH','PYTHONHOME','GNOME_KEYRING_CONTROL',
            'GNOME_KEYRING_PID','SSH_AUTH_SOCK','SSH_AGENT_PID','GPG_AGENT_INFO']:
            environment.pop(key,None)
        for key,name in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),
            ('XDG_STATE_HOME','state'),('XDG_RUNTIME_DIR','runtime'),('TMPDIR','tmp')]:
            folder=root/name;folder.mkdir(mode=0o700);environment[key]=str(folder)
        environment.update(GDK_BACKEND='x11',GSETTINGS_BACKEND='memory',GIO_USE_VFS='local',
            LIBGL_ALWAYS_SOFTWARE='1',WEBKIT_DISABLE_COMPOSITING_MODE='1',NO_AT_BRIDGE='1',
            DBUS_SESSION_BUS_ADDRESS='disabled:',DBUS_SYSTEM_BUS_ADDRESS='unix:path='+str(root/'no-system-bus'),
            PULSE_SERVER='unix:'+str(root/'no-pulse'),VIBEZ4_LOGIN_SMOKE_ROOT=str(root))
        authority=root/'xauthority';authority.touch(mode=0o600);environment['XAUTHORITY']=str(authority)
        server=native=None
        try:
            with (output/'xvfb.log').open('w') as xlog,(output/'native.log').open('w') as log:
                read_fd,write_fd=os.pipe()
                try:
                    server=subprocess.Popen([str(xvfb),'-displayfd',str(write_fd),'-screen','0','1600x1000x24',
                        '-nolisten','tcp','-ac'],env=environment,pass_fds=(write_fd,),stdout=xlog,
                        stderr=subprocess.STDOUT,start_new_session=True)
                finally:
                    os.close(write_fd)
                try:
                    if not select.select([read_fd],[],[],10)[0]:
                        raise RuntimeError('Private Xvfb startup timed out')
                    display=os.read(read_fd,64).decode().strip()
                finally:
                    os.close(read_fd)
                if not display.isdigit() or server.poll() is not None:
                    raise RuntimeError('Private Xvfb failed to start')
                environment['DISPLAY']=':'+display
                native=subprocess.Popen([str(binary),'--login-window-smoke-test'],env=environment,
                    stdout=log,stderr=subprocess.STDOUT,start_new_session=True,cwd=root)
                exit_code=native.wait(timeout=40)
                native_result=root/'native-result.json'
                if not native_result.is_file():
                    raise RuntimeError('Native test produced no report; see native.log')
                result=json.loads(native_result.read_text())
                shutil.copyfile(native_result,output/'native-result.json')
                report.update(native=result,exit_code=exit_code,private_x11_display=True,
                    passed=exit_code==0 and result.get('passed') is True,
                    all_test_xdg_state_discarded_after_run=True)
        except Exception as error:
            report['error']=str(error)
        finally:
            stop(native);stop(server)
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':
    main()
