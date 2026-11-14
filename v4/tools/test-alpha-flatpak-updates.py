#!/usr/bin/python3
"""A real signed Flatpak A->B deployment on a private bus and Xvfb display.

Only disposable fixture app data and a private Flatpak installation are used.
The fixture is never published, and the user's Flatpak remotes are untouched.
"""
import argparse,concurrent.futures,hashlib,json,os,shutil,signal,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP='nl.lecomputeur.vibez4.alpha'
CLIENT=r'''
import gi,json,sys
from pathlib import Path
gi.require_version('Gtk','3.0');gi.require_version('GdkX11','3.0')
from gi.repository import Gtk,Gio,GLib,GdkX11
window=Gtk.Window(title='Private Flatpak update test');window.show_all()
while Gtk.events_pending():Gtk.main_iteration()
parent='x11:%x'%window.get_window().get_xid()
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
reply=bus.call_sync('org.freedesktop.portal.Flatpak','/org/freedesktop/portal/Flatpak','org.freedesktop.portal.Flatpak','CreateUpdateMonitor',GLib.Variant('(a{sv})',({},)),GLib.VariantType.new('(o)'),Gio.DBusCallFlags.NONE,10000,None)
path=reply.unpack()[0];loop=GLib.MainLoop();requested=False;values={};outcome={};marker=Path('/app/share/update-marker').read_text().strip();assert marker=='A'
def observe(connection,sender,object_path,interface,signal,params):
 global requested
 info=params.unpack()[0]
 if signal=='UpdateAvailable':
  values.update(info)
  if values.get('remote-commit')!=values.get('local-commit') and not requested:
   requested=True
   connection.call('org.freedesktop.portal.Flatpak',path,'org.freedesktop.portal.Flatpak.UpdateMonitor','Update',GLib.Variant('(sa{sv})',(parent,{})),None,Gio.DBusCallFlags.NONE,-1,None,lambda bus,result:bus.call_finish(result))
 elif signal=='Progress':
  if info.get('status')==3:outcome.update(passed=False,error=info.get('error_message'));loop.quit()
  elif info.get('status')==2:
   outcome.update(passed=True,old_running_mount_unchanged=Path('/app/share/update-marker').read_text().strip()=='A',update_requested=requested,parent_window_supplied=parent.startswith('x11:') and parent!='x11:0');loop.quit()
bus.signal_subscribe('org.freedesktop.portal.Flatpak','org.freedesktop.portal.Flatpak.UpdateMonitor',None,path,None,Gio.DBusSignalFlags.NONE,observe)
print(json.dumps({'ready':True,'marker':marker,'monitor_alive':True}),flush=True)
GLib.timeout_add_seconds(35,lambda:(outcome.update(passed=False,error='portal update timeout'),loop.quit(),False)[2])
loop.run();print(json.dumps(outcome),flush=True);window.destroy();raise SystemExit(0 if outcome.get('passed') else 1)
'''

def stop(process):
 if process is None or process.poll() is not None:return
 os.killpg(process.pid,signal.SIGTERM)
 try:process.wait(timeout=5)
 except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)

def run(args,env,log,timeout=60):
 p=subprocess.run([str(x) for x in args],env=env,text=True,capture_output=True,timeout=timeout)
 log.write_text(p.stdout+p.stderr)
 if p.returncode:raise RuntimeError('Fixture command failed; see '+str(log))
 return p.stdout

def export(args,work,env,marker,signed=True):
 build=work/('build-'+marker);files=build/'files';(files/'bin').mkdir(parents=True);(files/'share').mkdir()
 (files/'bin/vibez4-alpha').write_text('#!/bin/sh\nexec /usr/bin/python3 /app/share/update-client.py\n');(files/'bin/vibez4-alpha').chmod(0o755)
 (files/'share/update-marker').write_text(marker+'\n');(files/'share/update-client.py').write_text(CLIENT)
 (build/'metadata').write_text('[Application]\nname='+APP+'\nruntime=org.gnome.Platform/x86_64/51\nsdk=org.gnome.Sdk/x86_64/51\ncommand=vibez4-alpha\n[Context]\nshared=network;ipc;\nsockets=x11;\n[Environment]\nGTK_USE_PORTAL=1\n')
 signing=['--gpg-sign='+args.gpg_key,'--gpg-homedir='+str(args.gpg_homedir)] if signed else []
 run(['flatpak','build-finish',build],env,work/('finish-'+marker+'.log'))
 run(['flatpak','build-export','--disable-sandbox',*signing,work/'repo',build,'alpha'],env,work/('export-'+marker+'.log'))
 run(['flatpak','build-update-repo',*signing,work/'repo'],env,work/('summary-'+marker+'.log'))
 return build

def worker(args):
 import gi
 gi.require_version('Gio','2.0');from gi.repository import Gio,GLib
 work=args.work;assert os.environ['DISPLAY'].startswith(':') and '/run/user/' not in os.environ['DBUS_SESSION_BUS_ADDRESS']
 logs=[];processes=[]
 try:
  for name,command in [('permission-store',['/usr/libexec/xdg-permission-store']),('flatpak-portal',['/usr/libexec/flatpak-portal','--no-idle-exit','--poll-timeout=1','--poll-when-metered'])]:
   stream=(work/(name+'.log')).open('w');logs.append(stream);processes.append(subprocess.Popen(command,env=os.environ.copy(),stdout=stream,stderr=subprocess.STDOUT,start_new_session=True))
  time.sleep(.3)
  run(['flatpak','permission-set','flatpak','updates',APP,'yes'],os.environ.copy(),work/'private-update-permission.log')
  client_log=(work/'client.log').open('w');logs.append(client_log)
  client=subprocess.Popen(['flatpak','run','--user','--nosocket=wayland','--socket=x11','--nodevice=dri','--no-a11y-bus',APP],env=os.environ.copy(),stdout=client_log,stderr=subprocess.STDOUT,start_new_session=True);processes.append(client)
  deadline=time.monotonic()+20
  while time.monotonic()<deadline:
   client_log.flush()
   if '"ready": true' in (work/'client.log').read_text():break
   assert client.poll() is None,'Fixture app exited; see client.log'
   while GLib.MainContext.default().iteration(False):pass
   time.sleep(.05)
  else:raise RuntimeError('Fixture monitor did not start; see client.log')
  before=run(['flatpak','info','--user','--show-commit',APP],os.environ.copy(),work/'commit-before.log').strip()
  export(args,work,os.environ.copy(),'B')
  deadline=time.monotonic()+40
  while client.poll() is None and time.monotonic()<deadline:
   while GLib.MainContext.default().iteration(False):pass
   time.sleep(.03)
  client_log.flush();assert client.poll()==0,'Update fixture failed; see client.log'
  results=[json.loads(x) for x in (work/'client.log').read_text().splitlines() if x.startswith('{')];result=results[-1];assert result['passed'] and result['old_running_mount_unchanged']
  after=run(['flatpak','info','--user','--show-commit',APP],os.environ.copy(),work/'commit-after.log').strip();assert before!=after
  marker=run(['flatpak','run','--user','--command=cat',APP,'/app/share/update-marker'],os.environ.copy(),work/'new-start.log').strip();assert marker=='B'
  # An unsigned candidate must never replace the verified deployment, even
  # though it is advertised by the configured private origin.
  export(args,work,os.environ.copy(),'C',signed=False)
  rejected=subprocess.run(['flatpak','update','--user','--assumeyes','--noninteractive','--no-related',APP],env=os.environ.copy(),capture_output=True,text=True,timeout=30)
  (work/'unsigned-update.log').write_text(rejected.stdout+rejected.stderr)
  # Flatpak deliberately treats remote fetch errors as non-fatal when the
  # existing deployment is usable. Exit code zero must not be mistaken for
  # a successful installation: compare the actual deployed commit instead.
  assert 'Nothing to do.' in rejected.stdout or rejected.returncode!=0,'Unexpected unsigned-update response'
  unchanged=run(['flatpak','info','--user','--show-commit',APP],os.environ.copy(),work/'commit-after-rejection.log').strip();assert unchanged==after
  result.update(unsigned_candidate_not_installed=True,verified_deployment_preserved_after_invalid_update=True,signed_repository=True,origin_configured_from_bundle=True,actual_flatpak_portal_update=True,commit_changed=True,next_start_uses_new_deployment=True,no_force_restart=True,private_xvfb=True,private_session_bus=True,private_permission_store_only=True,host_flatpak_installation_modified=False,host_displays_used=False,source_profile_used=False,fixture_only=True)
  (work/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return 0
 finally:
  for process in reversed(processes):stop(process)
  for stream in logs:stream.close()

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--gpg-homedir',type=Path,required=True);parser.add_argument('--gpg-key',required=True);parser.add_argument('--gpg-public-key',type=Path,required=True);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--worker',action='store_true');args=parser.parse_args()
 args.work=args.work.resolve();args.gpg_homedir=args.gpg_homedir.resolve();args.gpg_public_key=args.gpg_public_key.resolve()
 if args.worker:return worker(args)
 assert not args.work.exists();args.work.mkdir();work=args.work;env=dict(os.environ)
 for key in ['DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','AT_SPI_BUS_ADDRESS','VIBEZ_SAFE_OUTPUT','GDK_BACKEND','LD_LIBRARY_PATH']:env.pop(key,None)
 for variable,name in [('HOME','home'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state'),('FLATPAK_USER_DIR','installation'),('FLATPAK_CONFIG_DIR','etc')]:
  path=work/name;path.mkdir(mode=0o700);env[variable]=str(path)
 runtime=tempfile.mkdtemp(prefix='vibez-update-test-',dir=f'/run/user/{os.getuid()}');env.update(XDG_RUNTIME_DIR=runtime,GDK_BACKEND='x11',GSETTINGS_BACKEND='memory',NO_AT_BRIDGE='1',PATH='/usr/bin:/bin')
 # The signing agent is reached only through its explicit private homedir.
 # No signing key or unrelated real user profile is copied into the fixture.
 export(args,work,env,'A')
 bundle=work/'fixture.flatpak';run(['flatpak','build-bundle',work/'repo',bundle,APP,'alpha','--repo-url='+(work/'repo').as_uri(),'--gpg-keys='+str(args.gpg_public_key)],env,work/'bundle.log')
 run(['flatpak','install','--user','--bundle','--noninteractive','--assumeyes','--no-deps','--no-related',bundle],env,work/'install.log')
 xvfb=ROOT/'artifacts/native-test-tools/root/usr/bin/Xvfb';assert xvfb.is_file();read_fd,write_fd=os.pipe();log=(work/'xvfb.log').open('w');server=subprocess.Popen([str(xvfb),'-displayfd',str(write_fd),'-screen','0','1280x900x24','-nolisten','tcp','-ac'],env=env,pass_fds=(write_fd,),stdout=log,stderr=subprocess.STDOUT,start_new_session=True);os.close(write_fd)
 try:
  with os.fdopen(read_fd) as stream:display=stream.readline().strip()
  assert display.isdigit();env['DISPLAY']=':'+display
  command=['dbus-run-session','--',sys.executable,str(Path(__file__).resolve()),'--worker','--work',work,'--gpg-homedir',args.gpg_homedir,'--gpg-key',args.gpg_key,'--gpg-public-key',args.gpg_public_key]
  completed=subprocess.run([str(x) for x in command],env=env,capture_output=True,text=True,timeout=90);(work/'runner.log').write_text(completed.stdout+completed.stderr);print(completed.stdout,end='');return completed.returncode
 finally:
  stop(server);log.close();run(['flatpak','uninstall','--user','--noninteractive','--assumeyes','--no-related',APP],env,work/'uninstall.log');shutil.rmtree(runtime,ignore_errors=True)

if __name__=='__main__':raise SystemExit(main())
