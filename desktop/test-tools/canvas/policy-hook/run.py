#!/usr/bin/env python3
"""Synthetic native Wry hook lifecycle, isolated from the user's desktop/profile."""
import argparse,hashlib,json,os,shutil,signal,subprocess,tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
NAME='vibez-native-policy-hook-test'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--output',required=True,type=Path)
 p.add_argument('--target-dir',type=Path,default=HERE/'target')
 a=p.parse_args();out=a.output.resolve();target=a.target_dir.resolve()
 out.mkdir(parents=True,exist_ok=True)
 if any(out.iterdir()):p.error('Use an empty evidence directory')
 for tool in ['cargo','xvfb-run','Xvfb','dbus-run-session']:
  if not shutil.which(tool):p.error(f'Missing {tool}; no system changes were made')
 build=['cargo','build','--offline','--locked','--manifest-path',str(HERE/'Cargo.toml'),'--target-dir',str(target),'-j2']
 with (out/'build.log').open('w') as log:
  subprocess.run(build,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
 binary=target/'debug'/NAME
 env=os.environ.copy()
 for key in list(env):
  if key.startswith(('VIBEZ_','WEBKIT_','DBUS_STARTER_')) or key in ['LD_PRELOAD','DBUS_SESSION_BUS_ADDRESS','GNOME_KEYRING_CONTROL','GNOME_KEYRING_PID','DISPLAY','WAYLAND_DISPLAY']:
   env.pop(key,None)
 env.update(GDK_BACKEND='x11',GDK_SCALE='1',GDK_DPI_SCALE='1',LIBGL_ALWAYS_SOFTWARE='1',GIO_USE_VFS='local',NO_AT_BRIDGE='1')
 with tempfile.TemporaryDirectory(prefix='vz-hook-') as tmp:
  for key,name in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state'),('XDG_RUNTIME_DIR','runtime')]:
   d=Path(tmp)/name;d.mkdir(mode=0o700);env[key]=str(d)
  command=['xvfb-run','-a','-s','-screen 0 800x600x24','dbus-run-session','--',str(binary)]
  with (out/'stdout.txt').open('w') as stdout,(out/'stderr.log').open('w') as stderr:
   proc=subprocess.Popen(command,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
   try:code=proc.wait(timeout=90)
   except subprocess.TimeoutExpired:
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
    raise
 tagged=[line.removeprefix('VIBEZ_POLICY_HOOK_RESULT ') for line in (out/'stdout.txt').read_text().splitlines() if line.startswith('VIBEZ_POLICY_HOOK_RESULT ')]
 if len(tagged)!=1:raise RuntimeError('Expected exactly one native test result marker; see stdout/stderr')
 result=json.loads(tagged[0])
 result['exitCode']=code
 result['ok']=result.get('ok') is True and code==0
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 vendor=HERE.parents[2]/'src-tauri/vendor/wry'
 meta={'scope':'Synthetic native library hook lifecycle; actual Wry navigation wrapper and GTK signals, own inline HTML only. No VibeZ application, service login, challenge solve or real Canvas rendering.',
       'binary':str(binary),'binarySha256':sha(binary),'buildCommand':build,'runCommand':command,
       'display':'Own xvfb-run display; inherited DISPLAY removed','bus':'Own dbus-run-session','profile':'Disposable private XDG directories',
       'webkitVersion':subprocess.check_output(['pkg-config','--modversion','webkit2gtk-4.1'],text=True).strip(),
       'sourceSha256':{str(x.relative_to(HERE)):sha(x) for x in [HERE/'Cargo.toml',HERE/'Cargo.lock',HERE/'src/main.rs',HERE/'run.py']},
       'vendorSha256':{str(x.relative_to(vendor)):sha(x) for x in [vendor/'src/lib.rs',vendor/'src/webkitgtk/mod.rs',vendor/'README.patch']},
       'limits':['Reentry deliberately re-emits the same live policy object; this is a synthetic library lifecycle stress case, not a natural site navigation.',
                 'No inference about real authentication, Canvas service compatibility, idle CPU, or non-Linux behavior follows from this test.']}
 (out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
 print(json.dumps({'ok':result['ok'],'checks':len(result['checks']),'result':str(out/'result.json')},indent=2))
 return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
