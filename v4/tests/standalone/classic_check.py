#!/usr/bin/python3
"""Native GTK allocation regression test: full window vs optional side panel."""
import hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
BASE=Path(__file__).resolve().parents[2];OUT=BASE/'artifacts/classic-native-test21';OUT.mkdir(parents=True,exist_ok=True)
root=OUT/'root';root.mkdir(exist_ok=True)
subprocess.run(['dpkg-deb','-x',str(BASE/'artifacts/VibeZ-4.0.0-test.7-Linux-x64.deb'),str(root)],check=True)
shutil.copyfile(BASE/'desktop/src-tauri/target/release/vibez4-test',root/'usr/bin/vibez4-test')
for name in ['standalone_engine.py','workspace_engine.py','web_connector.py','automatic_connector.py']:shutil.copyfile(BASE/'backend'/name,root/'usr/lib/VibeZ 4 Test/backend'/name)
with tempfile.TemporaryDirectory(prefix='vibez4-standalone-classic-') as t:
 tmp=Path(t);env=dict(os.environ)
 for key in ['XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME']:
  p=tmp/key;p.mkdir();env[key]=str(p)
 folder=tmp/'Proefproject';folder.mkdir();(folder/'tekst.txt').write_text('Originele tekst.\n')
 report=OUT/'result-ui.json';report.unlink(missing_ok=True)
 env.update(NO_AT_BRIDGE='1',GIO_USE_VFS='local',GTK_USE_PORTAL='0',VIBEZ4_STANDALONE_TEST_OUTPUT=str(report),VIBEZ4_STANDALONE_ROOT=str(folder),VIBEZ4_STANDALONE_DRIVER=str(BASE/'tests/standalone/fixture_backend.py'))
 process=subprocess.Popen([str(root/'usr/bin/vibez4-test'),'--standalone-smoke-test'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 try:
  stdout,stderr=process.communicate(timeout=65)
 finally:
  if process.poll() is None:process.terminate();stdout,stderr=process.communicate(timeout=6)
  (OUT/'stdout.log').write_text(stdout);(OUT/'stderr.log').write_text(stderr)
 assert process.returncode==0,(process.returncode,stderr[-1500:])
 d=json.loads(report.read_text());assert d['clean_toolbar'] and d['project_name'] and d['written'] and d['on_safe_screen'],d
 assert d['language_restored'] and d['automatic_connected']
 assert not d['probes']['language']['panel']['mapped']
 for code in ['nl','en','ar']:
  language=d['languages'][code];assert language['state']['language']==code and not language['state']['pending'],language
  assert language['locale_cookies'] and set(language['locale_cookies'])=={code},language
  assert language['auth_preserved'],language
 assert d['languages']['auth']['state']['pending'] and d['languages']['auth']['url'].startswith('https://accounts.google.com/')
 preference=next(tmp.rglob('language.json'));assert json.loads(preference.read_text())['language']=='nl'
 shutil.copyfile(preference,OUT/'language-preference.json')
 for name in ['closed','files','proposal','settings','restored']:
  p=d['probes'][name];assert 'error' not in p,p
  t,v,b=p['toolbar'],p['web'],p['panel'];assert t['height']==54,p
  assert v['x']==t['x'] and v['y']==t['y']+54,p
  if name in ['closed','restored']:assert v['width']==t['width'] and not b['mapped'],p
  else:assert v['width']+b['width']==t['width'] and b['x']==v['x']+v['width'] and b['height']==v['height'] and b['mapped'],p
 d.update(passed=True,real_gtk_geometry=True,real_http_mcp=True,live_mistral=False)
 (OUT/'result.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
