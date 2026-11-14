#!/usr/bin/python3
"""Start the actual Alpha AppImage on an owned virtual display for 15 seconds.

HOME is unchanged. All application XDG state and the session bus are private.
No installed app, real display, existing Mistral profile or account is used.
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
import tempfile
import time

BASE=Path(__file__).resolve().parents[1]
APP='nl.lecomputeur.vibez4.alpha'
CAPTURE=r'''
import gi,sys
gi.require_version('Gdk','3.0');gi.require_version('GdkX11','3.0')
from gi.repository import Gdk,GdkX11
display=Gdk.Display.get_default();assert display is not None
window=GdkX11.X11Window.foreign_new_for_display(display,int(sys.argv[1],16));assert window is not None
width,height=window.get_width(),window.get_height()
image=Gdk.pixbuf_get_from_window(window,0,0,width,height);assert image is not None
image.savev(sys.argv[2],'png',[],[])
'''


def stop(process):
    if process is None:return
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:return
    if process.poll() is not None:return
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)


def descendants(parent):
    table={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            fields=(path/'stat').read_text().rsplit(')',1)[1].split()
            table[int(path.name)]=(int(fields[1]),fields[19])
        except (OSError,ValueError,IndexError):pass
    found={parent}
    while True:
        extra={pid for pid,(ppid,_) in table.items() if ppid in found}
        if extra<=found:break
        found|=extra
    return {pid:start for pid,(_,start) in table.items() if pid in found}


def backend_pids(owned,work):
    found=[]
    for pid in owned:
        try:args=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
        except OSError:continue
        if any(arg.endswith(b'/backend/standalone_engine.py') for arg in args):
            assert b'-I' in args and b'-B' in args
            position=args.index(b'--data-dir')
            assert Path(os.fsdecode(args[position+1])).resolve().is_relative_to(work)
            found.append(pid)
    return sorted(found)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--appimage',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--version',default='4.0.0-alpha.4')
    args=parser.parse_args();package=args.appimage.resolve(strict=True)
    assert hashlib.sha256(package.read_bytes()).hexdigest()==args.sha256
    assert re.fullmatch(r'4\.\d+\.\d+-(alpha|beta)\.\d+',args.version)
    work=args.work.resolve();assert not work.exists();work.mkdir()
    env=dict(os.environ);original_home=env.get('HOME')
    for key in ['DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','DBUS_STARTER_ADDRESS','DBUS_STARTER_BUS_TYPE','AT_SPI_BUS_ADDRESS','VIBEZ_SAFE_OUTPUT','APPIMAGE','APPDIR','GDK_BACKEND','LD_LIBRARY_PATH','GIO_MODULE_DIR','GIO_EXTRA_MODULES','GIO_USE_TLS','G_TLS_BACKEND','PYTHONPATH','PYTHONHOME','GNOME_KEYRING_CONTROL','GNOME_KEYRING_PID','SSH_AUTH_SOCK','SSH_AGENT_PID','GPG_AGENT_INFO']:
        env.pop(key,None)
    for key,folder in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state'),('XDG_RUNTIME_DIR','runtime'),('TMPDIR','tmp')]:
        path=work/folder;path.mkdir(mode=0o700);env[key]=str(path)
    # AF_UNIX socket names cannot contain the long workspace prefix.
    runtime=Path(tempfile.mkdtemp(prefix='vibez-appimage-runtime-'));env['XDG_RUNTIME_DIR']=str(runtime)
    assert env.get('HOME')==original_home
    authority=work/'xauthority';authority.touch(mode=0o600)
    # No service directories: desktop/keyring services cannot auto-activate and
    # inherit an unchanged HOME. The app only needs a private bus name here.
    bus_config=work/'session-bus.conf'
    bus_config.write_text('<busconfig><type>session</type><listen>unix:tmpdir='+str(runtime)+'</listen><auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>\n')
    env.update(GDK_BACKEND='x11',GSETTINGS_BACKEND='memory',GIO_USE_VFS='local',
               LIBGL_ALWAYS_SOFTWARE='1',WEBKIT_DISABLE_COMPOSITING_MODE='1',NO_AT_BRIDGE='1',
               DBUS_SYSTEM_BUS_ADDRESS='unix:path='+str(runtime/'no-system-bus'),
               PULSE_SERVER='unix:'+str(runtime/'no-pulse'),XAUTHORITY=str(authority))
    report={'passed':False,'appimage':str(package),'appimage_sha256':args.sha256,'version':args.version,
            'private_xdg_directories':True,'home_unchanged':True,'private_session_bus':True,
            'desktop_and_keyring_service_activation_disabled':True,'inherited_agent_sockets_removed':True,
            'host_displays_used':False,'host_installation_modified':False,'remote_account_used':False,
            'limitations':['Virtual X11/software renderer startup only; no Mistral sign-in or account function was tested.']}
    server=native=None;owned={}
    xlog=(work/'xvfb.log').open('w');log=(work/'native.log').open('w')
    try:
        xvfb=BASE/'artifacts/native-test-tools/root/usr/bin/Xvfb';assert xvfb.is_file()
        read_fd,write_fd=os.pipe()
        server=subprocess.Popen([str(xvfb),'-displayfd',str(write_fd),'-screen','0','1600x1000x24','-nolisten','tcp','-ac'],env=env,pass_fds=(write_fd,),stdout=xlog,stderr=subprocess.STDOUT,start_new_session=True)
        os.close(write_fd)
        with os.fdopen(read_fd) as stream:display=stream.readline().strip()
        assert display.isdigit() and server.poll() is None
        env['DISPLAY']=':'+display
        native=subprocess.Popen(['dbus-run-session','--config-file='+str(bus_config),'--',str(package),'--appimage-extract-and-run'],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        window=None;deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            owned.update(descendants(native.pid))
            assert native.poll() is None,'AppImage exited before its window appeared; see native.log'
            tree=subprocess.check_output(['/usr/bin/xwininfo','-root','-tree'],env=env,text=True)
            match=next((line for line in tree.splitlines() if 'VibeZ V4 ' in line and args.version in line),None)
            if match:
                window=re.search(r'0x[0-9a-fA-F]+',match)[0];(work/'private-window-tree.txt').write_text(tree);break
            time.sleep(.15)
        assert window,'The actual AppImage did not map its Alpha window'
        info=subprocess.check_output(['/usr/bin/xwininfo','-id',window],env=env,text=True);(work/'window-info.txt').write_text(info)
        assert 'Map State: IsViewable' in info
        def number(key):return int(next(line.split(':',1)[1].strip() for line in info.splitlines() if line.strip().startswith(key)))
        geometry=[number(key) for key in ['Absolute upper-left X','Absolute upper-left Y','Width','Height']]
        x,y,width,height=geometry;assert x>=0 and y>=0 and x+width<=1600 and y+height<=1000
        owned.update(descendants(native.pid));backends=backend_pids(owned,work);assert len(backends)==1
        pid_property=subprocess.check_output(['/usr/bin/xprop','-id',window,'_NET_WM_PID'],env=env,text=True)
        actual_pid=int(pid_property.rsplit('=',1)[1].strip());assert actual_pid in owned
        started=time.monotonic()
        while time.monotonic()-started<15:
            assert native.poll() is None,'AppImage exited during the startup stability check'
            current=descendants(native.pid);owned.update(current)
            assert actual_pid in current and backend_pids(current,work)==backends,'The actual app or packaged backend exited during startup'
            time.sleep(.25)
        profile=work/'data'/APP;assert profile.is_dir() and (profile/'webview').is_dir()
        subprocess.run(['/usr/bin/python3','-c',CAPTURE,window,str(work/'appimage-startup.png')],env=env,check=True,capture_output=True,text=True,timeout=10)
        report.update(passed=True,native_window_mapped=True,window_geometry=geometry,
                      actual_app_and_packaged_backend_stable_seconds=15,
                      packaged_backend_started_with_isolation_and_no_bytecode=True,
                      independent_alpha_webview_profile_created=True,
                      screenshot='appimage-startup.png',screenshot_visual_review_pending=True)
    except Exception as error:report['error']=str(error)
    finally:
        if native is not None:owned.update(descendants(native.pid))
        stop(native)
        for pid,start in owned.items():
            try:
                fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
                if fields[19]==start:os.kill(pid,signal.SIGTERM)
            except (OSError,IndexError):pass
        stop(server);xlog.close();log.close();shutil.rmtree(runtime,ignore_errors=True)
    (work/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':main()
