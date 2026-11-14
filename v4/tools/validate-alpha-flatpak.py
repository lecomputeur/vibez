#!/usr/bin/python3
"""Exercise the Alpha bundle in an owned Xvfb/session/Flatpak installation.

The real desktop and document portals run on a private bus. A tiny private
FileChooser backend returns only pre-approved disposable test paths, so no
chooser or app window can appear on the user's displays.
"""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
APP='nl.lecomputeur.vibez4.alpha'
VERSION=json.loads((ROOT/'desktop/package.json').read_text())['version']
WORK=ROOT/f'artifacts/flatpak-private-validation-{VERSION}'

CLIENT=r'''
import gi,json,os,tempfile,importlib.util
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
PRIVATE_RUNTIME=__PRIVATE_RUNTIME__
def namespace_path(raw):
 # Only this test has a nested private XDG_RUNTIME_DIR. Flatpak maps its
 # document FUSE into /run/user/UID/doc; normal desktop users already receive
 # that standard path, so production code needs no such translation.
 relative=Path(raw).relative_to(Path(PRIVATE_RUNTIME)/'doc')
 return Path('/run/user')/str(os.getuid())/'doc'/relative
window=Gtk.Window(title='Owned Alpha portal validation');window.show_all()
def pick(title,action):
 dialog=Gtk.FileChooserNative.new(title,window,action,'Choose','Cancel');dialog.set_modal(True)
 result=dialog.run();path=dialog.get_filename();dialog.destroy();return result,path
response,parent=pick('AlphaParent',Gtk.FileChooserAction.SELECT_FOLDER)
assert response==Gtk.ResponseType.ACCEPT and parent,parent
parent=namespace_path(parent);assert parent.is_dir(),str(parent)
assert '/doc/' in str(parent),str(parent)
existing=parent/'existing-workspace';assert existing.is_dir()
assert (existing/'existing.txt').read_text()=='unchanged test content\n'
(existing/'new-file.txt').write_text('saved through document portal\n')
created=parent/'new-main';assert not created.exists()
dialog=Gtk.FileChooserDialog(title='Create main folder',transient_for=window,action=Gtk.FileChooserAction.CREATE_FOLDER)
dialog.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Create',Gtk.ResponseType.ACCEPT)
dialog.set_current_folder(str(parent));dialog.set_current_name('new-main')
def accept():dialog.get_widget_for_response(Gtk.ResponseType.ACCEPT).clicked();return False
GLib.timeout_add(400,accept)
deadline=GLib.timeout_add(6000,lambda:(dialog.get_widget_for_response(Gtk.ResponseType.CANCEL).clicked(),False)[1])
response=dialog.run();GLib.source_remove(deadline)
assert response==Gtk.ResponseType.ACCEPT and created.is_dir()
assert Path(dialog.get_filename()).resolve()==created.resolve();dialog.destroy()
response,imported=pick('AlphaImport',Gtk.FileChooserAction.OPEN)
assert response==Gtk.ResponseType.ACCEPT and namespace_path(imported).read_text()=='import test content\n'
imported=namespace_path(imported)
response,imported_tree=pick('AlphaImportFolder',Gtk.FileChooserAction.SELECT_FOLDER)
assert response==Gtk.ResponseType.ACCEPT and imported_tree
imported_tree=namespace_path(imported_tree)
assert (imported_tree/'nested/notes.txt').read_text()=='folder import content\n'
response,cancelled=pick('AlphaCancel',Gtk.FileChooserAction.SELECT_FOLDER)
assert response==Gtk.ResponseType.CANCEL
backend=Path('/app/lib/VibeZ V4 Alpha/backend')
spec=importlib.util.spec_from_file_location('alpha_portal_backend',backend/'web_connector.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix='alpha-portal-backend-') as data:
 c=module.Connector(lambda event:None,Path(data),approval_wait=0)
 try:
  cases=[('aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',existing,None),('chat-bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb',created,'conversation')]
  import_cases=[]
  for key,folder,kind in cases:
   context={'id':key,'name':'Portal test'}
   if kind:context.update(kind=kind,draft=True,conversation_id=None,url='https://chat.mistral.ai/work')
   c.select(context);c.link(key,str(folder));snap=c.snapshot()
   assert snap['folder']==str(folder.resolve()) and len(snap['folders'])==1,{'requested':str(folder),'canonical':str(folder.resolve()),'snapshot_folder':snap['folder'],'root_count':len(snap['folders']),'context':key}
   result=c.create_folder(key,snap['workspace_binding'],'child');assert result['created'] and (folder/'child').is_dir()
   proof=snap['workspace_binding']
   copied=c.import_files(key,proof,[str(imported),str(imported_tree)])
   assert copied['status']=='done' and copied['count']==2,copied
   assert (folder/imported.name).read_text()=='import test content\n'
   assert (folder/imported_tree.name/'nested/notes.txt').read_text()=='folder import content\n'
   conflicts=c.import_files(key,proof,[str(imported),str(imported_tree)])
   assert conflicts['status']=='conflicts' and len(conflicts['items'])==2,conflicts
   kept=c.import_manager.resolve(conflicts['plan_id'],{item['id']:'keep_both' for item in conflicts['items']})
   assert kept['status']=='done' and kept['count']==2,kept
   assert (folder/'imported (2).txt').read_text()=='import test content\n'
   assert (folder/'imported-tree (2)'/'nested/notes.txt').read_text()=='folder import content\n'
   conflicts=c.import_files(key,proof,[str(imported),str(imported_tree)])
   skipped=c.import_manager.resolve(conflicts['plan_id'],{item['id']:'skip' for item in conflicts['items']})
   assert skipped['count']==0 and skipped['skipped']==2,skipped
   (folder/imported.name).write_text('old disposable destination\n')
   conflicts=c.import_files(key,proof,[str(imported)])
   assert conflicts['items'][0]['can_replace'],conflicts
   replaced=c.import_manager.resolve(conflicts['plan_id'],{item['id']:'replace' for item in conflicts['items']})
   assert replaced['count']==1 and (folder/imported.name).read_text()=='import test content\n',replaced
   (folder/imported_tree.name/'nested/notes.txt').write_text('old disposable folder destination\n')
   conflicts=c.import_files(key,proof,[str(imported_tree)])
   assert conflicts['items'][0]['can_replace'],conflicts
   replaced_folder=c.import_manager.resolve(conflicts['plan_id'],{item['id']:'replace' for item in conflicts['items']})
   assert replaced_folder['count']==1 and (folder/imported_tree.name/'nested/notes.txt').read_text()=='folder import content\n',replaced_folder
   workspace=module.base.Workspace(str(folder))
   try:
    proposal=workspace.proposal('approved-new.txt','created after approval\n')
    assert not (folder/'approved-new.txt').exists()
    assert workspace.commit(proposal)['written']
    assert workspace.read('approved-new.txt')['content']=='created after approval\n'
    proposal=workspace.proposal('approved-new.txt','edited after approval\n')
    assert (folder/'approved-new.txt').read_text()=='created after approval\n'
    assert workspace.commit(proposal)['written']
    assert (folder/'approved-new.txt').read_text()=='edited after approval\n'
   finally:workspace.close()
   assert not list(folder.glob('.vibez-import-*'))
   assert not list(folder.glob('.vibez-*'))
   import_cases.append({'context':kind or 'project','file_and_nested_folder_copied':True,'keep_both':True,'skip':True,'replace_file':True,'replace_folder':True,'approved_new_file':True,'approved_existing_edit':True,'staging_clean':True})
 finally:c.close()
assert (existing/'existing.txt').read_text()=='unchanged test content\n'
print(json.dumps({'passed':True,'native_portal_parent':str(parent),'private_runtime_uri_namespace_translation':True,'extra_filesystem_permissions':False,'portal_existing_folder_read_write':True,'native_create_folder_in_granted_parent':True,'native_import_file_grant':True,'native_import_folder_grant':True,'native_cancel':True,'packaged_backend_project_and_new_conversation':True,'packaged_portal_imports':import_cases,'existing_test_file_unchanged':True,'runtime_python':os.sys.version.split()[0]}),flush=True)
window.destroy()
'''

def stop(process):
    if process is None or process.poll() is not None:return
    os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)

def run(command,env,log,timeout=60):
    result=subprocess.run([str(value) for value in command],env=env,capture_output=True,text=True,timeout=timeout)
    log.write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(f'Command failed: {command[0]} ({result.returncode}); see {log}')
    return result.stdout

def launch_exported_desktop(env):
    """Launch only this test installation's exported application entry."""
    import gi
    gi.require_version('Gio','2.0')
    from gi.repository import Gio,GLib
    installation=Path(env['FLATPAK_USER_DIR']).resolve(strict=True)
    assert installation.is_relative_to(WORK.resolve()),'Desktop launch requires the owned installation'
    exported=installation/'exports/share/applications'/f'{APP}.desktop'
    assert exported.resolve(strict=True).is_relative_to(installation),'Unexpected desktop export target'
    config=configparser.ConfigParser(interpolation=None);config.read(exported)
    entry=config['Desktop Entry']
    for key in ['Hidden','NoDisplay','OnlyShowIn','NotShowIn','TryExec']:assert key not in entry,key
    assert not entry.getboolean('DBusActivatable',fallback=False)
    assert 'Development' in entry['Categories'].split(';')
    assert entry['X-Flatpak']==APP
    command=shlex.split(entry['Exec'])
    assert Path(command[0]).name=='flatpak' and command[1]=='run',command
    for argument in ['--branch=alpha','--arch=x86_64','--command=vibez4-alpha',APP]:assert argument in command,command
    desktop=Gio.DesktopAppInfo.new(APP+'.desktop')
    assert desktop and Path(desktop.get_filename()).resolve()==exported.resolve(),'Alpha desktop-id did not resolve to the private export'
    assert desktop.should_show(),'Alpha is hidden from the application menu'
    assert 'Development' in desktop.get_categories().split(';')
    # This override belongs to FLATPAK_USER_DIR under WORK, never the user's
    # actual installation. Keep the real exported Exec unmodified while making
    # its display and rendering equivalent to the other private Xvfb checks.
    run(['flatpak','override','--user','--nosocket=wayland','--socket=x11',
         '--nosocket=pulseaudio','--nodevice=dri','--env=GDK_BACKEND=x11',
         '--env=LIBGL_ALWAYS_SOFTWARE=1','--env=WEBKIT_DISABLE_COMPOSITING_MODE=1',
         '--env=NO_AT_BRIDGE=1',APP],env,WORK/'desktop-private-override.log')
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        before=subprocess.check_output(['xwininfo','-root','-tree'],env=env,text=True)
        if 'VibeZ V4 ' not in before:break
        while GLib.MainContext.default().iteration(False):pass
        time.sleep(.05)
    assert 'VibeZ V4 ' not in before,'Previous direct-launch window was not closed before desktop launch'
    pids=[];statuses={}
    def setup_child(*_):os.setsid()
    def remember_pid(_desktop,pid,*_):pids.append(int(pid))
    def alive(pid):
        if pid in statuses:return False
        try:done,status=os.waitpid(pid,os.WNOHANG)
        except ChildProcessError:return False
        if done:statuses[pid]=os.waitstatus_to_exitcode(status);return False
        return True
    try:
        with (WORK/'desktop-launch.log').open('w') as log:
            launch=Gio.AppLaunchContext()
            for name,value in env.items():launch.setenv(name,value)
            started=desktop.launch_uris_as_manager_with_fds([],launch,
                GLib.SpawnFlags.DO_NOT_REAP_CHILD,setup_child,None,remember_pid,None,
                -1,log.fileno(),log.fileno())
            assert started,'Gio refused the exported Alpha desktop entry'
            deadline=time.monotonic()+3
            while not pids and time.monotonic()<deadline:
                while GLib.MainContext.default().iteration(False):pass
                time.sleep(.02)
            assert len(pids)==1,'Desktop launch must provide exactly one owned process'
            pid=pids[0]
            assert os.getpgid(pid)==pid,'Desktop launch process was not isolated in its own process group'
            tree='';deadline=time.monotonic()+20
            while time.monotonic()<deadline and alive(pid):
                tree=subprocess.check_output(['xwininfo','-root','-tree'],env=env,text=True)
                if 'VibeZ V4 ' in tree:break
                while GLib.MainContext.default().iteration(False):pass
                time.sleep(.1)
            assert 'VibeZ V4 ' in tree and alive(pid),'Exported desktop entry did not open Alpha in private Xvfb'
            (WORK/'desktop-private-x11-tree.txt').write_text(tree)
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                assert alive(pid),'Alpha exited after the exported desktop launch'
                while GLib.MainContext.default().iteration(False):pass
                time.sleep(.05)
            return {'exported_desktop_launch_passed':True,'desktop_id':APP+'.desktop',
                'desktop_visible_in_menu':True,'desktop_category':'Development',
                'desktop_command_rewritten_by_flatpak':True,'desktop_launch_own_process_group':True,
                'desktop_launch_private_xvfb':True,'kde_discover_itself_tested':False}
    finally:
        # No global `flatpak kill`: only process groups created by this exact
        # Gio launch are touched, including children if the launcher exited.
        for pid in pids:
            try:os.killpg(pid,signal.SIGTERM)
            except ProcessLookupError:pass
        deadline=time.monotonic()+5
        while any(alive(pid) for pid in pids) and time.monotonic()<deadline:time.sleep(.05)
        for pid in pids:
            if alive(pid):
                try:os.killpg(pid,signal.SIGKILL)
                except ProcessLookupError:pass
                try:os.waitpid(pid,0)
                except ChildProcessError:pass
            GLib.spawn_close_pid(pid)

def worker():
    # Resolve the same exported desktop-id used by software centres, restricted
    # to the disposable installation before Gio initialises its app database.
    exports=Path(os.environ['FLATPAK_USER_DIR'])/'exports/share'
    assert exports.resolve().is_relative_to(WORK.resolve())
    os.environ['XDG_DATA_DIRS']=str(exports)+':'+os.environ.get('XDG_DATA_DIRS','/usr/share')
    import gi
    gi.require_version('Gio','2.0')
    from gi.repository import Gio,GLib
    assert os.environ['DISPLAY'].startswith(':') and '/run/user/' not in os.environ['DBUS_SESSION_BUS_ADDRESS']
    parent=WORK/'chosen-parent';parent.mkdir();(parent/'existing-workspace').mkdir();(parent/'existing-workspace/existing.txt').write_text('unchanged test content\n')
    imported=WORK/'imported.txt';imported.write_text('import test content\n')
    imported_tree=WORK/'imported-tree';(imported_tree/'nested').mkdir(parents=True);(imported_tree/'nested/notes.txt').write_text('folder import content\n')
    connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    xml='''<node><interface name="org.freedesktop.impl.portal.FileChooser"><method name="OpenFile"><arg type="o" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="u" direction="out"/><arg type="a{sv}" direction="out"/></method><method name="SaveFile"><arg type="o" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="u" direction="out"/><arg type="a{sv}" direction="out"/></method><property name="version" type="u" access="read"/></interface></node>'''
    info=Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0];calls=[]
    def call(bus,sender,path,interface,method,params,invocation):
        values=params.unpack();appid,title=values[1],values[3];assert appid==APP,appid
        calls.append({'method':method,'app_id':appid,'title':title})
        if title=='AlphaCancel':invocation.return_value(GLib.Variant('(ua{sv})',(1,{})));return
        target=imported if title=='AlphaImport' else imported_tree if title=='AlphaImportFolder' else parent
        invocation.return_value(GLib.Variant('(ua{sv})',(0,{'uris':GLib.Variant('as',[target.as_uri()]),'writable':GLib.Variant('b',True)})))
    registration=connection.register_object('/org/freedesktop/portal/desktop',info,call,lambda *args:GLib.Variant('u',4),None)
    owner=Gio.bus_own_name_on_connection(connection,'org.freedesktop.impl.portal.desktop.alpha_test',Gio.BusNameOwnerFlags.NONE,None,None)
    logs=[];processes=[];result={}
    try:
        for name,command in [('document-portal',['/usr/libexec/xdg-document-portal','--verbose']),('flatpak-portal',['/usr/libexec/flatpak-portal','--no-idle-exit']),('desktop-portal',['/usr/libexec/xdg-desktop-portal','--verbose'])]:
            stream=(WORK/(name+'.log')).open('w');logs.append(stream);processes.append(subprocess.Popen(command,env=os.environ.copy(),stdout=stream,stderr=subprocess.STDOUT,start_new_session=True))
        # Process the mock backend name registration while the portals start.
        until=time.monotonic()+1.2
        while time.monotonic()<until:
            while GLib.MainContext.default().iteration(False):pass
            time.sleep(.02)
        common=['flatpak','run','--user','--nosocket=wayland','--socket=x11','--nosocket=pulseaudio','--nodevice=dri','--no-a11y-bus','--env=GDK_BACKEND=x11','--env=LIBGL_ALWAYS_SOFTWARE=1','--env=WEBKIT_DISABLE_COMPOSITING_MODE=1']
        version=run([*common,APP,'--version'],os.environ.copy(),WORK/'version.log')
        assert 'VibeZ V4 ' in version and VERSION in version,version
        gui_log=(WORK/'gui.log').open('w');logs.append(gui_log)
        gui=subprocess.Popen([*common,APP],env=os.environ.copy(),stdout=gui_log,stderr=subprocess.STDOUT,start_new_session=True);processes.append(gui)
        tree='';deadline=time.monotonic()+20
        while time.monotonic()<deadline and gui.poll() is None:
            tree=subprocess.check_output(['xwininfo','-root','-tree'],env=os.environ.copy(),text=True)
            if 'VibeZ V4 ' in tree:break
            while GLib.MainContext.default().iteration(False):pass
            time.sleep(.15)
        assert 'VibeZ V4 ' in tree and gui.poll() is None,'No Alpha window in private Xvfb'
        (WORK/'private-x11-tree.txt').write_text(tree)
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            assert gui.poll() is None,'Alpha exited during startup'
            while GLib.MainContext.default().iteration(False):pass
            time.sleep(.05)
        result['native_gui_started_without_indicator_libraries']=True
        stop(gui)
        result.update(launch_exported_desktop(os.environ.copy()))
        client_log=(WORK/'portal-client.log').open('w');logs.append(client_log)
        client_source=CLIENT.replace('__PRIVATE_RUNTIME__',repr(os.environ['XDG_RUNTIME_DIR']))
        client=subprocess.Popen([*common,'--command=/usr/bin/python3',APP,'-I','-c',client_source],env=os.environ.copy(),stdout=client_log,stderr=subprocess.STDOUT,start_new_session=True);processes.append(client)
        deadline=time.monotonic()+40
        while client.poll() is None and time.monotonic()<deadline:
            while GLib.MainContext.default().iteration(False):pass
            time.sleep(.02)
        assert client.poll()==0,'Portal test failed; see portal-client.log'
        client_log.flush();data=json.loads(next(line for line in (WORK/'portal-client.log').read_text().splitlines() if line.startswith('{"passed"')))
        result.update(data);result.update(version=version.strip(),portal_backend_calls=calls,private_xvfb=True,private_session_bus=True,own_disposable_paths_only=True,real_user_profiles_used=False,indicator_libraries_included=False)
        (WORK/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
        return 0
    finally:
        for process in reversed(processes):stop(process)
        for stream in logs:stream.close()
        connection.unregister_object(registration);Gio.bus_unown_name(owner)

def main():
    global WORK,VERSION
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--work',type=Path,default=WORK)
    parser.add_argument('--expected-version',default=VERSION)
    parser.add_argument('--binary-sha256')
    parser.add_argument('--publication',type=Path)
    parser.add_argument('--worker',action='store_true')
    args=parser.parse_args();WORK=args.work.resolve();VERSION=args.expected_version
    if not re.fullmatch(r'4\.\d+\.\d+-(alpha|beta)\.\d+',VERSION):parser.error('Expected a separate V4 Alpha or Beta version')
    if args.worker:return worker()
    if not args.bundle:parser.error('--bundle is required')
    assert not WORK.exists(),'Use a new private validation directory'
    WORK.mkdir();env=dict(os.environ)
    for key in ['DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','AT_SPI_BUS_ADDRESS','VIBEZ_SAFE_OUTPUT','GDK_BACKEND','LD_LIBRARY_PATH']:env.pop(key,None)
    for variable,name in [('HOME','home'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state'),('XDG_RUNTIME_DIR','runtime'),('FLATPAK_USER_DIR','installation'),('FLATPAK_CONFIG_DIR','etc')]:
        path=WORK/name;path.mkdir(mode=0o700);env[variable]=str(path)
    env.update(XDG_CURRENT_DESKTOP='VibeZTest',GSETTINGS_BACKEND='memory',GTK_USE_PORTAL='1',NO_AT_BRIDGE='1',PATH='/usr/bin:/bin')
    env['XDG_RUNTIME_DIR']=tempfile.mkdtemp(prefix='vibez-alpha-verify-',dir=f'/run/user/{os.getuid()}')
    definitions=WORK/'data/xdg-desktop-portal/portals';definitions.mkdir(parents=True)
    (definitions/'alpha-test.portal').write_text('[portal]\nDBusName=org.freedesktop.impl.portal.desktop.alpha_test\nInterfaces=org.freedesktop.impl.portal.FileChooser;\nUseIn=VibeZTest;\n')
    config=WORK/'config/xdg-desktop-portal';config.mkdir(parents=True)
    (config/'portals.conf').write_text('[preferred]\ndefault=alpha-test\norg.freedesktop.impl.portal.FileChooser=alpha-test\n')
    env['XDG_DATA_DIRS']=str(WORK/'data')+':/usr/share'
    env['XDG_DESKTOP_PORTAL_DIR']=str(definitions)
    server=None;xlog=None;installed=False;package_checks={}
    try:
        run(['flatpak','install','--user','--bundle','--noninteractive','--assumeyes','--no-deps','--no-related',args.bundle.resolve()],env,WORK/'install.log');installed=True
        deployment=Path(run(['flatpak','info','--user','--show-location',APP],env,WORK/'deployment.log').strip())
        if args.binary_sha256:
            assert hashlib.sha256((deployment/'files/bin/vibez4-alpha').read_bytes()).hexdigest()==args.binary_sha256
            package_checks['canonical_binary_sha256']=args.binary_sha256
        origin=run(['flatpak','info','--user','--show-origin',APP],env,WORK/'origin.log').strip()
        config=configparser.ConfigParser(interpolation=None);config.read(Path(env['FLATPAK_USER_DIR'])/'repo/config')
        remote=config['remote "'+origin+'"']
        assert remote.get('url')=='https://raw.githubusercontent.com/lecomputeur/vibez/v4-alpha-flatpak/'
        assert remote.getboolean('gpg-verify') and remote.getboolean('gpg-verify-summary',fallback=True)
        package_checks.update(bundle_has_dedicated_alpha_origin=True,bundle_origin_requires_gpg_verification=True)
        if args.publication:
            publication=args.publication.resolve(strict=True)
            run(['flatpak','remote-add','--user','--no-use-for-deps','--gpg-import='+str(publication/'alpha-updates.gpg'),'alpha-final-verification',publication.as_uri()],env,WORK/'add-signed-local-repo.log')
            signed=run(['flatpak','remote-info','--user','--show-commit','alpha-final-verification',APP+'//alpha'],env,WORK/'verify-signed-local-repo.log').strip()
            installed_commit=run(['flatpak','info','--user','--show-commit',APP],env,WORK/'installed-commit.log').strip()
            assert signed==installed_commit
            package_checks.update(final_published_tree_gpg_verified=True,final_published_commit_matches_bundle=True,commit=installed_commit)
        xvfb=ROOT/'artifacts/native-test-tools/root/usr/bin/Xvfb';assert xvfb.is_file()
        read_fd,write_fd=os.pipe();xlog=(WORK/'xvfb.log').open('w')
        server=subprocess.Popen([str(xvfb),'-displayfd',str(write_fd),'-screen','0','1600x1000x24','-nolisten','tcp','-ac'],env=env,pass_fds=(write_fd,),stdout=xlog,stderr=subprocess.STDOUT,start_new_session=True)
        os.close(write_fd)
        with os.fdopen(read_fd) as pipe:display=pipe.readline().strip()
        assert display.isdigit();env['DISPLAY']=':'+display
        completed=subprocess.run(['dbus-run-session','--',sys.executable,str(Path(__file__).resolve()),'--worker','--work',str(WORK),'--expected-version',VERSION],env=env,capture_output=True,text=True,timeout=95)
        (WORK/'runner.log').write_text(completed.stdout+completed.stderr)
        if completed.returncode==0:
            report=json.loads((WORK/'result.json').read_text());report.update(package_checks)
            report['bundle_sha256']=hashlib.sha256(args.bundle.read_bytes()).hexdigest()
            (WORK/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(completed.stdout,end='');print(completed.stderr[-3500:],end='',file=sys.stderr)
        return completed.returncode
    finally:
        stop(server)
        if xlog:xlog.close()
        if installed:
            result=subprocess.run(['flatpak','uninstall','--user','--noninteractive','--assumeyes','--no-related',APP],env=env,capture_output=True,text=True)
            (WORK/'uninstall.log').write_text(result.stdout+result.stderr)
        shutil.rmtree(env['XDG_RUNTIME_DIR'],ignore_errors=True)

if __name__=='__main__':raise SystemExit(main())
