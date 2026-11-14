#!/usr/bin/python3
"""Complete an AppDir after linuxdeploy's known canonical-icon lookup failure.

Tauri supplies the executable/AppRun and performs full GTK/GStreamer dependency
scans. The GStreamer plugin can fail at its final desktop-icon lookup because
Tauri names the copied icon after the binary while the Alpha desktop uses its
application ID. This resume path requires that exact final-stage failure, adds
an identical canonical icon, executes the untouched remaining official plugin
script, and uses the official appimagetool. No library is excluded or removed.
"""
import argparse,hashlib,json,os,platform,re,shutil,subprocess,tempfile,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
APP_ID='nl.lecomputeur.vibez4.alpha'
MODULES={'workspace_engine.py','standalone_engine.py','web_connector.py','automatic_connector.py','project_import.py','multi_workspace.py','capfs.py','document_reader.py','document_writer.py'}

def run(args,**kwargs):
    try:return subprocess.check_output([str(x) for x in args],stderr=subprocess.STDOUT,**kwargs)
    except subprocess.CalledProcessError as error:
        print(error.output.decode(errors='replace') if isinstance(error.output,bytes) else error.output,file=sys.stderr)
        raise
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def elf(path):
    if not path.is_file():return False
    with path.open('rb') as stream:return stream.read(4)==b'\x7fELF'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ['appdir','deployment-log','gstreamer-plugin','patchelf','appimage-tool','runtime-file','output']:parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args()
    # Only the exact pinned AppImage tools may run (see packaging/appimage-tool-sources.json).
    pins=json.loads((BASE/'packaging/appimage-tool-sources.json').read_text())
    assert sha(args.appimage_tool)==pins['appimagetool']['sha256'],'appimagetool differs from the pinned download'
    assert sha(args.runtime_file)==pins['runtime']['sha256'],'AppImage runtime differs from the pinned download'
    app=args.appdir.resolve(strict=True);output=args.output.resolve();assert not output.exists(),'Refusing to replace an existing image'
    assert platform.machine()=='x86_64','This Alpha packaging path is Linux x64 only'
    log=args.deployment_log.read_text();assert '[gstreamer/stdout] -- Deploying files into AppDir root directory --' in log
    assert f'ERROR: Could not find suitable icon for Icon entry: {APP_ID}' in log and 'Failed to run plugin: gstreamer (exit code: 1)' in log,'Only the known post-deployment icon failure can resume here'
    desktop=app/'usr/share/applications/VibeZ V4 Alpha.desktop';text=desktop.read_text();assert f'Icon={APP_ID}\n' in text and 'Exec=vibez4-alpha\n' in text and 'Name=VibeZ V4 Beta\n' in text
    icon=app/f'usr/share/icons/hicolor/512x512/apps/{APP_ID}.png';icon.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/'desktop/src-tauri/icons/icon.png',icon);icon.chmod(0o644)
    assert icon.read_bytes()==(BASE/'desktop/src-tauri/icons/icon.png').read_bytes()
    root_icon=app/f'{APP_ID}.png';shutil.copyfile(icon,root_icon);root_icon.chmod(0o644)
    assert root_icon.read_bytes()==icon.read_bytes()
    resources=app/'usr/lib/VibeZ V4 Alpha/backend';assert {p.name for p in resources.iterdir() if p.is_file()}==MODULES
    assert all((resources/name).read_bytes()==(BASE/'backend'/name).read_bytes() for name in MODULES),'AppDir backend differs from frozen source'
    assert not list(resources.rglob('__pycache__'))
    tunnel=resources/'vendor/cloudflared-linux-amd64';assert sha(tunnel)==sha(BASE/'backend/vendor/cloudflared-linux-amd64')
    assert (app/'apprun-hooks/linuxdeploy-plugin-gtk.sh').is_file(),'The complete GTK phase is required'
    plugins=app/'usr/lib/gstreamer-1.0';host_plugins=Path('/usr/lib/x86_64-linux-gnu/gstreamer-1.0')
    expected={p.name for p in host_plugins.iterdir() if p.is_file()};assert expected and expected<={p.name for p in plugins.iterdir()},'GStreamer dependency-copy phase is incomplete'
    # The official script's inner linuxdeploy already copied every dependency
    # and set ELF rpaths before failing at its final icon lookup. Resume only
    # its exact unmodified tail: plugin rpaths, helpers, and the AppRun hook.
    script=args.gstreamer_plugin.read_text();anchor='for i in "$plugins_target_dir"/*; do'
    assert script.count(anchor)==1,'Upstream plugin changed; review the resume boundary'
    tail=script[script.index(anchor):]
    environment=dict(os.environ);environment['PATH']=str(args.patchelf.resolve().parent)+os.pathsep+environment.get('PATH','/usr/bin:/bin')
    environment.update(APPDIR=str(app),GSTREAMER_VERSION='1.0',plugins_target_dir=str(plugins),helpers_target_dir=str(app/'usr/lib/gstreamer1.0/gstreamer-1.0'),helpers_dir='/usr/lib/x86_64-linux-gnu/gstreamer1.0/gstreamer-1.0')
    run(['/bin/bash','-e','-c',tail],env=environment)
    hook=app/'apprun-hooks/linuxdeploy-plugin-gstreamer.sh';assert hook.is_file()
    helpers=app/'usr/lib/gstreamer1.0/gstreamer-1.0';assert (helpers/'gst-plugin-scanner').is_file()
    # Validate the package's main executable, all multimedia plugins and helpers
    # against the relocated library directory. Static cloudflared is unchanged.
    linkage=dict(environment);linkage['LD_LIBRARY_PATH']=str(app/'usr/lib')
    binaries=[app/'usr/bin/vibez4-alpha',*(p for p in plugins.iterdir() if elf(p)),*(p for p in helpers.iterdir() if elf(p))]
    for binary in binaries:
        linked=run(['ldd',binary],env=linkage,text=True);assert 'not found' not in linked,'Missing dependency for '+str(binary)
    run(['desktop-file-validate',desktop])
    run([sys.executable,BASE/'tools/prepare-alpha-appimage-launcher.py','--appdir',app])
    environment['ARCH']='x86_64';output.parent.mkdir(parents=True,exist_ok=True)
    run([args.appimage_tool.resolve(),'--runtime-file',args.runtime_file.resolve(),'--comp','zstd','--mksquashfs-opt=-processors','--mksquashfs-opt=2',app,output],env=environment)
    output.chmod(0o755)
    # Extracting the artifact runs only its packaging runtime, never the GUI.
    with tempfile.TemporaryDirectory(prefix='alpha-image-check-',dir=output.parent) as temporary:
        run([output,'--appimage-extract'],cwd=temporary)
        extracted=Path(temporary)/'squashfs-root';bundled=extracted/'usr/lib/VibeZ V4 Alpha/backend'
        assert all((bundled/name).read_bytes()==(BASE/'backend'/name).read_bytes() for name in MODULES)
        assert sha(bundled/'vendor/cloudflared-linux-amd64')==sha(tunnel)
        assert (extracted/f'usr/share/icons/hicolor/512x512/apps/{APP_ID}.png').read_bytes()==icon.read_bytes()
        assert not list(bundled.rglob('__pycache__'))
        version=run([extracted/'usr/bin/vibez4-alpha','--version'],text=True).strip()
        release=json.loads((BASE/'desktop/package.json').read_text())['version'];assert release in version
    report={'version':release,'package':str(output),'sha256':sha(output),'size':output.stat().st_size,'all_seven_backend_hashes_match':True,'static_tunnel_unchanged':True,'canonical_icon_alias_same_bytes':True,'gstreamer_plugins':len(expected),'dynamic_linkage_checks':len(binaries),'gtk_and_gstreamer_hooks':True,'official_plugin_tail_sha256':hashlib.sha256(tail.encode()).hexdigest(),'runtime_file_sha256':sha(args.runtime_file),'runtime_metadata':json.loads(args.runtime_file.with_suffix('.json').read_text()),'no_dependency_libraries_omitted':True,'extracted_artifact_verified':True,'headless_version':version,'gui_started':False,'host_installation_changed':False,'passed':True}
    output.with_suffix(output.suffix+'.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
