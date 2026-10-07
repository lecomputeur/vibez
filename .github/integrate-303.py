"""One-time integration on the isolated candidate branch; commit source before tests."""
from pathlib import Path
import json,os
if os.environ.get('GITHUB_REF')!='refs/heads/vibe/windows-real-paste-303-91c4':raise SystemExit('Candidate branch only')
d=Path('desktop');marker=d/'.candidate-303-integrated'
if marker.exists():raise SystemExit(0)
def change(name,old,new):
 p=Path(name);s=p.read_text();assert old in s,name;p.write_text(s.replace(old,new))
for name in ['package.json','package-lock.json','src-tauri/tauri.conf.json']:
 p=d/name;a=json.loads(p.read_text());a['version']='3.0.3'
 if name=='package-lock.json':a['packages']['']['version']='3.0.3'
 if name=='src-tauri/tauri.conf.json':a['app']['security']['capabilities'].append('local-updates')
 p.write_text(json.dumps(a,indent=2,ensure_ascii=False)+'\n')
change('desktop/src-tauri/Cargo.toml','version = "3.0.2"','version = "3.0.3"')
change('desktop/src-tauri/Cargo.toml','base64 = "0.22"','base64 = "0.22"\nsha2 = "=0.10.9"')
p=d/'src-tauri/Cargo.lock';s=p.read_text();a=s.index('name = "vibez3"');b=s.index('\n[[package]]',a);part=s[a:b].replace('version = "3.0.2"','version = "3.0.3"').replace(' "serde_json",',' "serde_json",\n "sha2",');p.write_text(s[:a]+part+s[b:])
change('desktop/scripts/prepare.cjs','const baseLanguages = Object.keys(TRANSLATIONS).sort();', '''const updateRows=JSON.parse(fs.readFileSync(path.join(project,'updates-i18n.json'),'utf8'));
const updateKeys=['updateAvailable','updateDownload','updateDownloading','updateOpenFile','updateShowFile','updateConfirmInstall','updateStoreManaged','pasteConfirmed','pasteUnconfirmed'];
if(JSON.stringify(Object.keys(updateRows).sort())!==JSON.stringify(Object.keys(TRANSLATIONS).sort()))throw new Error('Update locale codes differ');
for(const [code,values] of Object.entries(updateRows)){
  if(values.length!==updateKeys.length||values.some(v=>typeof v!=='string'||!v.trim()))throw new Error('Missing update translation: '+code);
  Object.assign(previewData.translations[code],Object.fromEntries(updateKeys.map((key,i)=>[key,values[i]])));
}
const baseLanguages = Object.keys(TRANSLATIONS).sort();''')
change('desktop/src-tauri/build.rs','"get_diagnostics",','"get_diagnostics", "check_for_updates", "update_state", "update_action",')
p=d/'src-tauri/capabilities/local-shell.json';a=json.loads(p.read_text());a['permissions'].append('allow-check-for-updates');p.write_text(json.dumps(a,indent=2)+'\n')
change('desktop/src-tauri/src/policy.rs','"shell" | "settings" | "screenshot"','"shell" | "settings" | "screenshot" | "updates"')
change('desktop/src-tauri/src/main.rs','mod screenshot_dialog;','mod screenshot_dialog;\nmod update_download;')
change('desktop/src-tauri/src/main.rs','format!("{APP_NAME} v{}", env!("CARGO_PKG_VERSION"))','format!("{APP_NAME} v{} · test 1", env!("CARGO_PKG_VERSION"))')
change('desktop/src-tauri/src/main.rs','"build_label": ""','"build_label": "test 1"')
change('desktop/src-tauri/src/main.rs','#[tauri::command]\nasync fn get_diagnostics','''#[tauri::command]
async fn update_state(webview:Webview)->Result<Value,String>{
    require_local(&webview)?;
    if webview.label()!="updates"{return Err("Use the local update window".into());}
    preview_updates::snapshot()
}
#[tauri::command]
async fn update_action(webview:Webview,app:AppHandle,action:String,name:Option<String>)->Result<Value,String>{
    require_local(&webview)?;
    if webview.label()!="updates"{return Err("Use the local update window".into());}
    preview_updates::action(&app,&action,name).await
}
#[tauri::command]
async fn get_diagnostics''')
change('desktop/src-tauri/src/main.rs','check_for_updates, get_diagnostics]','check_for_updates, update_state, update_action, get_diagnostics]')
change('desktop/src-tauri/src/main.rs','automatic installation: disabled','downloads: in-app with SHA-256 verification; automatic installation: disabled')
change('desktop/src-tauri/src/screenshot_dialog.rs','#[cfg(not(target_os="linux"))]\n#[path="screenshot_release_probe.rs"]','#[path="screenshot_release_probe.rs"]')
change('desktop/src-tauri/src/screenshot_dialog.rs','#[cfg(not(target_os="linux"))]\npub async fn release_smoke_check','pub async fn release_smoke_check')
change('desktop/src-tauri/src/smoke.rs','    #[cfg(not(target_os="linux"))]\n    tauri::async_runtime::block_on(crate::screenshot_dialog::release_smoke_check(app))?;','    tauri::async_runtime::block_on(crate::screenshot_dialog::release_smoke_check(app))?;\n    tauri::async_runtime::block_on(crate::preview_updates::smoke_check(app))?;')
change('tools/release-v3/native-smoke.py',"[str(binary),'--smoke-test']","[str(binary),'--smoke-test','--update-download-probe']")
change('tools/release-v3/native-smoke.py','timeout=150','timeout=240')
for name in ['desktop/tests/screenshot-e2e.py','desktop/tests/screenshot-monitors.py']:change(name,'v3.0.2','v3.0.3')
change('tools/release-v3/sign-macos.sh','arch="$1"','arch="$1"\nversion="$(python3 -c \'import json; print(json.load(open("desktop/package.json"))["version"])\')"')
change('tools/release-v3/sign-macos.sh','VibeZ-3.0.2-macOS-','VibeZ-$version-macOS-')
p=d/'test/isolation.test.cjs';s=p.read_text();s=s.replace("read('src-tauri/src/release_updates.rs')","read('src-tauri/src/update_download.rs')").replace('release\\["draft"\\]','value\\["draft"\\]').replace('release\\["prerelease"\\]','value\\["prerelease"\\]').replace('version.major < 3','version.major!=3');p.write_text(s)
marker.write_text('Integration complete; platform jobs build this committed source.\n')
