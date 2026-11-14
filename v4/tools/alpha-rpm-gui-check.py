#!/usr/bin/python3
"""One-monitor RPM startup fixture, exclusively inside a networkless container.

Docker's default seccomp policy prevents nested WebKit user namespaces. This
fixture therefore disables the WebKit sandbox only in its temporary child
environment; that setting is never added to the packaged app or launcher.
"""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

assert Path('/.dockerenv').exists(), 'Only run inside the isolated Docker test container'
assert os.environ.get('VIBEZ_ALPHA_CONTAINER_GUI_TEST')=='1'
assert os.getuid()!=0, 'Run the native app as an ordinary test user'
assert {p.name for p in Path('/sys/class/net').iterdir()}=={'lo'}, 'Disconnect external networking first'


def processes():
    apps=[];backends=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if os.readlink(p/'exe')=='/usr/bin/vibez4-alpha':apps.append(int(p.name))
            args=(p/'cmdline').read_bytes().split(b'\0')
            if any(arg==b'/usr/lib/VibeZ V4 Alpha/backend/standalone_engine.py' for arg in args):backends.append(int(p.name))
        except OSError:pass
    return apps,backends


with tempfile.TemporaryDirectory(prefix='vibez-alpha-rpm-gui-') as temp:
    root=Path(temp)
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(root/'home'),
         'XDG_CONFIG_HOME':str(root/'config'),'XDG_DATA_HOME':str(root/'data'),
         'XDG_CACHE_HOME':str(root/'cache'),'XDG_RUNTIME_DIR':str(root/'runtime'),
         'DISPLAY':':99','GDK_BACKEND':'x11','GIO_USE_VFS':'local','GSETTINGS_BACKEND':'memory',
         'LIBGL_ALWAYS_SOFTWARE':'1','WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS':'1'}
    for key in ['HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR']:
        Path(env[key]).mkdir(mode=0o700)
    with (root/'xvfb.log').open('w') as xvfb_log,(root/'native.log').open('w') as native_log:
        xvfb=subprocess.Popen(['Xvfb',':99','-screen','0','1280x900x24','-nolisten','tcp'],
                              env=env,stdout=xvfb_log,stderr=xvfb_log,start_new_session=True)
        native=None;worker_pids=[]
        try:
            for _ in range(50):
                if Path('/tmp/.X11-unix/X99').exists():break
                assert xvfb.poll() is None,'Xvfb exited'
                time.sleep(.05)
            else:raise AssertionError('Dedicated virtual screen did not start')
            native=subprocess.Popen(['dbus-run-session','--','/usr/bin/vibez4-alpha'],
                                    env=env,stdout=native_log,stderr=native_log,start_new_session=True)
            window=None;geometry=None
            for _ in range(100):
                assert native.poll() is None, 'Native app exited during startup: '+(root/'native.log').read_text()[-3000:]
                raw=subprocess.check_output(['xwininfo','-root','-tree'],text=True,env=env)
                line=next((line for line in raw.splitlines() if 'VibeZ V4 ' in line and '4.0.0-alpha.3' in line),None)
                if line:
                    window=re.search(r'0x[0-9a-fA-F]+',line)[0]
                    break
                time.sleep(.1)
            assert window,'Alpha window was not mapped: '+(root/'native.log').read_text()[-3000:]
            raw=subprocess.check_output(['xwininfo','-id',window],text=True,env=env)
            def get(key):return int(next(line.split(':')[1].strip() for line in raw.splitlines() if line.strip().startswith(key)))
            geometry=[get(key) for key in ['Absolute upper-left X','Absolute upper-left Y','Width','Height']]
            x,y,width,height=geometry
            assert x>=0 and y>=0 and x+width<=1280 and y+height<=900
            assert 'Map State: IsViewable' in raw
            apps,backends=processes();assert len(apps)==1 and len(backends)==1,(apps,backends)
            worker_pids=apps+backends
            for _ in range(10):
                time.sleep(1);assert native.poll() is None
                assert processes()==(apps,backends),'App or local backend exited during startup'
            profile=root/'data/nl.lecomputeur.vibez4.alpha'
            assert profile.is_dir(),'Independent Alpha profile was not created'
            report={'passed':True,'one_screen':True,'screen_size':[1280,900],'window_geometry':geometry,
                    'native_main_window_mapped':True,'backend_stable_seconds':10,
                    'independent_alpha_profile_created':True,'ordinary_test_user':True,
                    'sandbox_disabled_for_container_fixture_only':True,
                    'external_network_disconnected':True,'remote_account_used':False,
                    'host_display_or_profiles_used':False,
                    'limitations':['Xvfb/software renderer startup fixture, not a real GNOME/Wayland login or Mistral-account test.',
                                   'Docker denies nested user namespaces, so WebKit sandbox is disabled only for this networkless container fixture.']}
        finally:
            if native is not None and native.poll() is None:
                os.killpg(native.pid,signal.SIGTERM)
                try:native.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(native.pid,signal.SIGKILL);native.wait(timeout=5)
            for pid in worker_pids:
                try:
                    args=(Path('/proc')/str(pid)/'cmdline').read_bytes()
                    if b'vibez4-alpha' in args or b'/usr/lib/VibeZ V4 Alpha/backend/standalone_engine.py' in args:os.kill(pid,signal.SIGTERM)
                except OSError:pass
            if xvfb.poll() is None:xvfb.terminate();xvfb.wait(timeout=5)
print(json.dumps(report,indent=2))
