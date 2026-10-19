#!/usr/bin/env python3
"""Create a disposable, separately identified build; never edit the source checkout."""
import argparse, hashlib, json, shutil
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', required=True, type=Path, help='Original desktop/ source directory')
parser.add_argument('--output', required=True, type=Path, help='New work directory outside source')
args = parser.parse_args()
ROOT = args.output.resolve()
SOURCE = args.source.resolve(strict=True)
assert ROOT != SOURCE and SOURCE not in ROOT.parents, 'Output must be outside the source tree'
DEST = ROOT / 'source' / 'desktop'
APP = 'nl.lecomputeur.vibez3.CanvasTest'
NAME = 'VibeZ Canvas Test'
BIN = 'vibez3-canvas-test'
VERSION = '3.0.9+test.3'

def replace(path, old, new, count=1):
    text = path.read_text()
    assert text.count(old) == count, (path, old, text.count(old))
    path.write_text(text.replace(old, new))

assert not DEST.exists(), 'Refuse to overwrite an existing build source'
shutil.copytree(SOURCE, DEST, ignore=shutil.ignore_patterns('target', 'node_modules', '.git'))
(DEST / 'node_modules').symlink_to((SOURCE / 'node_modules').resolve())
tauri = DEST / 'src-tauri'
config_path = tauri / 'tauri.conf.json'
config = json.loads(config_path.read_text())
config.update(productName=NAME, version=VERSION, identifier=APP, mainBinaryName=BIN)
config['bundle'].update(shortDescription='Isolated Canvas and Cloudflare test for VibeZ', longDescription='Separate test application for issues #49 and #45. Uses its own login and settings; updates and autostart are disabled.')
linux = config['bundle']['linux']
for fmt in ('deb', 'rpm'):
    for key in ('preInstallScript', 'postInstallScript', 'postRemoveScript'):
        linux[fmt].pop(key, None)
linux['deb']['files'] = {
    f'/usr/share/applications/{APP}.desktop': f'linux/{APP}.desktop',
    f'/usr/share/icons/hicolor/512x512/apps/{APP}.png': 'icons/icon.png',
    f'/usr/share/pixmaps/{APP}.png': 'icons/icon.png',
}
config_path.write_text(json.dumps(config, indent=2)+'\n')
package_path = DEST / 'package.json'
package = json.loads(package_path.read_text())
package.update(name=BIN, version=VERSION)
package_path.write_text(json.dumps(package, indent=2)+'\n')
lock_path = DEST / 'package-lock.json'
lock = json.loads(lock_path.read_text())
lock.update(name=BIN, version=VERSION)
lock['packages'][''].update(name=BIN, version=VERSION)
lock_path.write_text(json.dumps(lock, indent=2)+'\n')
replace(tauri/'Cargo.toml', 'name = "vibez3"', f'name = "{BIN}"')
replace(tauri/'Cargo.toml', 'version = "3.0.9+test.2"', f'version = "{VERSION}"')
replace(tauri/'Cargo.lock', 'name = "vibez3"\nversion = "3.0.9+test.2"', f'name = "{BIN}"\nversion = "{VERSION}"')
policy = tauri/'src/policy.rs'
replace(policy, 'pub const APP_ID: &str = "nl.lecomputeur.vibez3";', f'pub const APP_ID: &str = "{APP}";')
replace(policy, 'pub const APP_NAME: &str = "VibeZ 3";', f'pub const APP_NAME: &str = "{NAME}";')
replace(policy, 'start_at_login: false, auto_updates: true', 'start_at_login: false, auto_updates: false')
replace(policy, 'assert_eq!(APP_NAME, "VibeZ 3");', f'assert_eq!(APP_NAME, "{NAME}");')
replace(tauri/'src/desktop_ui.rs', 'assert_eq!(menu_label("nl", "open"), "VibeZ 3 openen");', 'assert_eq!(menu_label("nl", "open"), "VibeZ Canvas Test openen");')
main = tauri/'src/main.rs'
replace(main, 'format!("VibeZ V{}", env!("CARGO_PKG_VERSION"))', 'format!("VibeZ Canvas Test V{}", env!("CARGO_PKG_VERSION"))')
replace(main, 'let settings = patch.apply(&expected, &previous)?;', 'let settings = patch.apply(&expected, &previous)?;\n    if settings.start_at_login || settings.auto_updates { return Err("Autostart and updates are disabled in this isolated test app".into()); }')
replace(main, 'let settings = loaded.settings;', 'let mut settings = loaded.settings;\n            settings.start_at_login = false;\n            settings.auto_updates = false;')
updates = tauri/'src/release_updates.rs'
text = updates.read_text()
start = text.index('pub fn check(app:AppHandle,manual:bool){')
end = text.index('pub async fn action(', start)
text = text[:start]+'''pub fn check(app:AppHandle,manual:bool){
    if let Ok(mut s)=state().lock(){s.phase="error";s.error="Updates are disabled in this isolated test app. Get test builds from the GitHub issue thread.".into();}
    if manual{tauri::async_runtime::spawn(async move{let _=show(&app).await;});}
}
'''+text[end:]
needle = 'pub async fn action(app:&AppHandle,action:&str,name:Option<String>)->Result<Value,String>{'
assert text.count(needle)==1
text=text.replace(needle,needle+'\n    if action != "close" { return Err("Updates are disabled in this isolated test app".into()); }')
start=text.index('pub fn schedule(app:AppHandle){')
end=text.index('// Test helper:',start)
text=text[:start]+'pub fn schedule(_app:AppHandle){}\n'+text[end:]
updates.write_text(text)
desktop = f'''[Desktop Entry]
Type=Application
Name={NAME}
Comment=Separate VibeZ Canvas and Cloudflare test
Exec={BIN}
Icon={BIN}
Categories=Development;
Terminal=false
StartupWMClass={APP}
'''
(tauri/'linux/themed.desktop.hbs').write_text(desktop)
(tauri/f'linux/{APP}.desktop').write_text(desktop.replace(f'Icon={BIN}', f'Icon=/usr/share/pixmaps/{APP}.png'))
(tauri/'linux/hidden-generated.desktop.hbs').write_text(desktop+'NoDisplay=true\n')
# Remove unused original installation scripts and launchers from the build source.
for name in ('preinst.sh', 'postinst.sh', 'postrm.sh', 'nl.lecomputeur.vibez3.desktop'):
    (tauri/'linux'/name).unlink()
files = {str(p.relative_to(DEST)):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in DEST.rglob('*') if p.is_file() and 'node_modules' not in p.parts}
(ROOT/'prepared-source.json').write_text(json.dumps({'appId':APP,'name':NAME,'binary':BIN,'version':VERSION,'source':str(SOURCE),'files':files},indent=2)+'\n')
print(DEST)
