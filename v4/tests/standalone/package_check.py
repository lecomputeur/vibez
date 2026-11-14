#!/usr/bin/python3
"""Launch this DEB on screen 1, in an isolated session, without installing it."""
import argparse,hashlib,json,os,shutil,sqlite3,subprocess,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[2];VERSION=json.loads((BASE/'desktop/src-tauri/tauri.conf.json').read_text())['version']
p=argparse.ArgumentParser();p.add_argument('--native',action='store_true');args=p.parse_args()
out=BASE/'artifacts'/('standalone-native-'+VERSION if args.native else 'standalone-package-'+VERSION);out.mkdir(parents=True,exist_ok=True)
deb=BASE/'desktop/src-tauri/target/release/bundle/deb'/f'VibeZ 4 Test_{VERSION}_amd64.deb'
control=subprocess.check_output(['dpkg-deb','-f',str(deb)],text=True);(out/'control.txt').write_text(control)
assert 'Package: vibe-z-4-test\n' in control and f'Version: {VERSION}\n' in control
assert not any(line.startswith(('Conflicts:','Replaces:','Provides:')) for line in control.splitlines())
root=out/'root';root.mkdir(exist_ok=True);subprocess.run(['dpkg-deb','-x',str(deb),str(root)],check=True)
ctrl=out/'control';ctrl.mkdir(exist_ok=True);subprocess.run(['dpkg-deb','-e',str(deb),str(ctrl)],check=True)
assert not any((ctrl/n).exists() for n in ['preinst','postinst','prerm','postrm']);assert not(root/'usr/bin/vibez3').exists()
assert 'Categories=Development;' in(root/'usr/share/applications/nl.lecomputeur.vibez4.test.desktop').read_text()
for name in ['workspace_engine.py','standalone_engine.py','web_connector.py','automatic_connector.py']:assert(root/'usr/lib/VibeZ 4 Test/backend'/name).read_bytes()==(BASE/'backend'/name).read_bytes()
helper=root/'usr/lib/VibeZ 4 Test/backend/vendor/cloudflared-linux-amd64';assert helper.is_file() and os.access(helper,os.X_OK);assert hashlib.sha256(helper.read_bytes()).hexdigest()=='ae5e8add7884b0531d66bbca4570d1de491ff6da51e4ebe7eb160cdf241d9e42'
assert '2026.10.4' in subprocess.check_output([str(helper),'--version'],text=True)
binary=root/'usr/bin/vibez4-test';assert b'VIBEZ4_STANDALONE_TEST_OUTPUT' not in binary.read_bytes()
if args.native:shutil.copyfile(BASE/'desktop/src-tauri/target/release/vibez4-test',binary)
profile=tempfile.TemporaryDirectory(prefix='vibez4-standalone-');env=dict(os.environ)
for key in ['XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME']:
 target=Path(profile.name)/key;target.mkdir();env[key]=str(target)
env.update(NO_AT_BRIDGE='1',GIO_USE_VFS='local',GTK_USE_PORTAL='0');env.pop('MISTRAL_API_KEY',None)
project=Path(profile.name)/'Proefproject';project.mkdir();(project/'tekst.txt').write_text('Originele tekst.\n')
report_path=out/'result-ui.json';report_path.unlink(missing_ok=True)
if args.native:env.update(VIBEZ4_STANDALONE_TEST_OUTPUT=str(report_path),VIBEZ4_STANDALONE_ROOT=str(project),VIBEZ4_STANDALONE_DRIVER=str(BASE/'tests/standalone/fixture_backend.py'))
process=subprocess.Popen([str(binary)]+(['--standalone-smoke-test'] if args.native else []),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
try:
 if args.native:
  stdout,stderr=process.communicate(timeout=25)
  (out/'stdout.log').write_text(stdout);(out/'stderr.log').write_text(stderr)
  assert process.returncode==0,(process.returncode,stderr)
  report=json.loads(report_path.read_text())
  for key in ['keptChat','sameConversation','inertApproval','honestSync','noCredential','localPage','on_safe_screen','login_on_safe_screen','folder_on_safe_screen','export_on_safe_screen','written','web_child_inside_main','web_has_no_native_permissions','web_project_name','web_project_folder']:assert report[key],key
  assert report['users']==3 and report['answers']==3 and report['files']==1
  database=next(Path(profile.name).rglob('conversations.sqlite3'));assert b'fixture-account-secret-never-shown' not in database.read_bytes()
  db=sqlite3.connect(database);assert db.execute('SELECT COUNT(*) FROM conversations').fetchone()[0]>=3;db.close();shutil.copyfile(database,out/'fixture-history.sqlite3')
  report.update(real_mcp=True,real_files=True,local_persistence=True,live_mistral=False)
 else:
  time.sleep(4);assert process.poll() is None,(process.poll(),process.stderr.read())
  report={'production_started':True,'test_feature_absent':True,'live_mistral':False}
 report.update(passed=True,version=VERSION,deb_sha256=hashlib.sha256(deb.read_bytes()).hexdigest(),system_installation=False,vibez3_paths_absent=True)
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
finally:
 if process.poll() is None:process.terminate()
 stdout,stderr=process.communicate(timeout=5)
 if stdout:(out/'stdout.log').write_text(stdout)
 if stderr:(out/'stderr.log').write_text(stderr)
 profile.cleanup()
