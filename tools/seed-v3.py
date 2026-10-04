#!/usr/bin/env python3
"""One-time promotion; commit generated source and locks before building.
Never overwrites the proven preview or the existing Electron implementation.
"""
from pathlib import Path
import json, shutil, re
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'desktop'; SOURCE=ROOT/'tauri-preview'
if OUT.exists(): raise SystemExit('desktop/ already exists; edit its tracked source instead')
assert json.loads((SOURCE/'package.json').read_text())['version']=='0.1.17'
shutil.copytree(SOURCE,OUT,ignore=shutil.ignore_patterns('node_modules','dist','target','gen','icons','artifacts'))
rules=[('nl.lecomputeur.vibez.tauri.preview','nl.lecomputeur.vibez3'),('VibeZ-Tauri-Preview','VibeZ'),('VibeZ Tauri Preview','VibeZ 3'),('vibe-z-tauri-preview','vibe-z-3'),('vibez-tauri-preview','vibez3'),('0.1.17','3.0.0')]
for p in list(OUT.rglob('*')):
    if not p.is_file(): continue
    try: s=p.read_text()
    except UnicodeError: continue
    for old,new in rules: s=s.replace(old,new).replace(old.replace('.',r'\.'),new.replace('.',r'\.'))
    p.write_text(s)
for p in sorted(OUT.rglob('*'),key=lambda p:len(p.parts),reverse=True):
    if not p.is_file(): continue
    name=p.name
    for old,new in rules: name=name.replace(old,new)
    if name!=p.name: p.rename(p.with_name(name))
def read(p): return (OUT/p).read_text()
def write(p,s):
    dest=OUT/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(s)
def replace(p,old,new):
    s=read(p)
    if old not in s: raise RuntimeError(f'Missing migration anchor in {p}: {old[:80]}')
    write(p,s.replace(old,new))
pkg=json.loads(read('package.json'));pkg.update(name='vibez3',description='VibeZ 3 — Rust/Tauri desktop client for Mistral Vibe')
write('package.json',json.dumps(pkg,indent=2)+'\n')
replace('src-tauri/Cargo.toml','Experimental Tauri desktop client for Mistral Vibe','VibeZ 3 desktop client for Mistral Vibe')
replace('src-tauri/Cargo.toml','features = ["Win32_Globalization"]','features = ["Win32_Globalization", "Win32_System_Com"]')
with (OUT/'src-tauri/Cargo.toml').open('a') as f:
    f.write('''\n[target.'cfg(target_os = "windows")'.dependencies]\nwebview2-com = "=0.39.1"\n\n[target.'cfg(target_os = "macos")'.dependencies]\nobjc2 = "=0.6.4"\nobjc2-foundation = "=0.3.2"\nobjc2-web-kit = "=0.3.2"\n''')
conf=json.loads(read('src-tauri/tauri.conf.json'));conf['bundle']['targets']='all'
conf['bundle']['shortDescription']='Mistral Vibe in a dedicated Rust-powered desktop app'
conf['bundle']['longDescription']='VibeZ 3 is an independent desktop client for Mistral Vibe with native webviews, system language support, screenshot tools and a dedicated desktop window.'
conf['bundle']['icon']=['icons/128x128.png','icons/icon.png','icons/icon.icns','icons/icon.ico']
conf['bundle']['macOS']={'minimumSystemVersion':'14.0','entitlements':'macos/Entitlements.plist'}
conf['bundle']['windows']={'webviewInstallMode':{'type':'embedBootstrapper'},'nsis':{'languages':['English','Dutch','German','French','Spanish'],'displayLanguageSelector':True}}
conf['bundle']['linux']['rpm']={'depends':['webkit2gtk4.1','gtk3','xdg-desktop-portal'],'desktopTemplate':'linux/themed.desktop.hbs'}
conf['bundle']['linux']['appimage']={'bundleMediaFramework':True}
write('src-tauri/tauri.conf.json',json.dumps(conf,indent=2)+'\n')
write('src-tauri/macos/Entitlements.plist','<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict/></plist>\n')
write('src-tauri/linux/themed.desktop.hbs','[Desktop Entry]\nType=Application\nName=VibeZ 3\nExec=vibez3\nIcon=vibez3\nCategories=Development;\nTerminal=false\nStartupWMClass=nl.lecomputeur.vibez3\n')
replace('src-tauri/linux/nl.lecomputeur.vibez3.desktop','Experimental Rust/Tauri client alongside VibeZ','Rust-powered desktop client for Mistral Vibe')
replace('src-tauri/src/policy.rs','assert!(APP_NAME.contains("Preview"));','assert_eq!(APP_NAME, "VibeZ 3");')
# Use actual browser state on every platform, preserving Linux layout behavior.
p='src-tauri/src/main.rs';s=read(p).replace('mod policy;','mod policy;\nmod browser;',1)
s=s.replace('#[cfg(target_os = "windows")]\n#[path = "native_layout_windows.rs"]','#[cfg(any(target_os = "windows", target_os = "macos"))]\n#[path = "native_layout_windows.rs"]',1)
s=re.sub(r'#\[cfg\(target_os = "linux"\)\]\n#\[path = "preview_updates.rs"\]\nmod preview_updates;\n#\[cfg\(target_os = "windows"\)\]\n#\[path = "preview_updates_windows.rs"\]\nmod preview_updates;','#[path = "release_updates.rs"]\nmod preview_updates;',s)
a=s.index('    #[cfg(target_os = "linux")]\n    let (back, forward, loading) = {',s.index('async fn get_state'));b=s.index('    let state = app.state::<PreviewState>();',a)
s=s[:a]+'    let (back, forward, loading) = browser::state(&view, &app).await?;\n'+s[b:]
a=s.index('        "back" => {',s.index('async fn navigate'));b=s.index('        "reload" =>',a)
s=s[:a]+'        "back" => browser::history(&view, false).await,\n        "forward" => browser::history(&view, true).await,\n'+s[b:]
local='[118,105,98,101,122,51,0,0,0,0,0,0,0,0,0,1]';remote='[118,105,98,101,122,51,0,0,0,0,0,0,0,0,0,2]'
s=s.replace('.data_directory(data.join("controls"))',f'.data_directory(data.join("controls")).data_store_identifier({local})')
s=s.replace('.data_directory(app.path().app_data_dir().map_err(err)?.join("controls"))',f'.data_directory(app.path().app_data_dir().map_err(err)?.join("controls")).data_store_identifier({local})')
s=s.replace('.data_directory(data.join("webview"))',f'.data_directory(data.join("webview")).data_store_identifier({remote})')
s=s.replace('"os_locale": os_locale(),','"os_locale": os_locale(), "platform": std::env::consts::OS,')
s=s.replace('    } else {\n        ("Tauri 2 / system WebKitGTK"','    } else if cfg!(target_os = "macos") {\n        ("Tauri 2 / Apple WKWebView", "macOS", String::new(), String::new(), "Updates: published VibeZ 3 releases; manual installation")\n    } else {\n        ("Tauri 2 / system WebKitGTK"')
s=s.replace('Preview update checks: manual Windows preview artifacts; Store delivery is separate','Updates: published VibeZ 3 releases; Store delivery is separate').replace('Preview update checks: manual, separate tested Linux artifacts; installation is manual','Updates: published VibeZ 3 releases; manual installation').replace('not enabled in this preview','not enabled in this version')
s=s.replace('.icon(tauri::image::Image::from_bytes(include_bytes!("../icons/icon.png"))?)?', '.icon(tauri::image::Image::from_bytes(include_bytes!("../icons/128x128.png"))?)?')
insert='''#[cfg(target_os = "macos")]
async fn take_screenshot(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<PreviewState>();
    if state.capture_busy.swap(true, Ordering::SeqCst) { return Err(desktop_ui::status(app, "A screenshot is already in progress")); }
    let result = tauri::async_runtime::spawn_blocking(|| {
        let status = std::process::Command::new("/usr/sbin/screencapture").args(["-i", "-c"]).status().map_err(err)?;
        if status.success() { Ok(()) } else { Err("Capture cancelled or permission denied".to_string()) }
    }).await.map_err(err).and_then(|r| r);
    state.capture_busy.store(false, Ordering::SeqCst);
    match &result {
        Ok(()) => message(app, "Screenshot copied — paste it into Vibe with Ctrl+V."),
        Err(error) => message(app, format!("Screenshot cancelled or unavailable: {error}")),
    }
    result
}
'''
s=s.replace('#[tauri::command]\nasync fn capture_screenshot',insert+'#[tauri::command]\nasync fn capture_screenshot');write(p,s)
# Native cookie preparation is verified on Linux, Windows and macOS.
p='src-tauri/src/site_language.rs';s=read(p)
s=s.replace('#[cfg(target_os = "windows")]\nasync fn preferred(_view: &Webview, _locale: &str) -> Result<(), String> { Ok(()) }','#[cfg(any(target_os = "windows", target_os = "macos"))]\nasync fn preferred(view: &Webview, locale: &str) -> Result<(), String> { crate::browser::preferred(view, locale).await }')
s=s.replace('    #[cfg(target_os = "linux")]\n    for host','    for host').replace('#[cfg(target_os = "linux")]\nasync fn confirm','async fn confirm')
s=s.replace('#[cfg(target_os = "windows")]\nasync fn confirm(_view: &Webview, _locale: &str) -> Result<(), String> { Ok(()) }','')
s=s.replace('#[cfg(target_os = "linux")]\npub async fn smoke_check','pub async fn smoke_check')
a=s.index('            // Inspect the native URI without parsing it:');b=s.index('        }\n        println!("LANGUAGE_BOOTSTRAP_OK:',a)
s=s[:a]+'''            if let Ok(uri) = view.url() {
                if uri.as_str() != "about:blank" { return Err("Language probe navigated remotely".into()); }
            }
'''+s[b:];write(p,s)
p='src-tauri/src/auth.rs';s=read(p).replace('#[cfg(target_os = "windows")]\npub fn attach_errors','#[cfg(any(target_os = "windows", target_os = "macos"))]\npub fn attach_errors').replace('.data_directory(data)',f'.data_directory(data).data_store_identifier({remote})');write(p,s)
p='src-tauri/src/native_layout_windows.rs';write(p,read(p)+'\npub fn repair(app: &AppHandle) -> Result<(), String> { layout(app) }\n')
p='src-tauri/src/smoke.rs';s=read(p).replace('    #[cfg(target_os = "linux")]\n    tauri::async_runtime::block_on','    tauri::async_runtime::block_on')
s=s.replace('    for (width,height) in [(1100.,720.),(760.,560.),(1450.,950.),(1280.,840.)] {','    let sizes = if cfg!(target_os="linux") { [(1100.,720.),(760.,560.),(1450.,950.),(1280.,840.)] } else { [(900.,600.),(760.,560.),(1000.,650.),(850.,600.)] };\n    for (width,height) in sizes {')
s=s.replace('    popup_checks(app)?;','    history_check(app)?;\n    popup_checks(app)?;');s+='\n'+(ROOT/'tools/v3-seed/history_probe.rs').read_text();write(p,s)
p='src-tauri/src/desktop_ui.rs';s=read(p).replace('pub fn status(app: &AppHandle, raw: &str) -> String {','pub fn status(app: &AppHandle, raw: &str) -> String {\n    let value = status_inner(app, raw);\n    if cfg!(target_os="macos") { value.replace("Ctrl+V", "⌘V") } else { value }\n}\nfn status_inner(app: &AppHandle, raw: &str) -> String {');write(p,s)
# Preserve all 34 bundles; update the v3-specific presentation.
p='scripts/prepare.cjs';s=read(p)
extra='''for (const [code, strings] of Object.entries(previewData.translations)) {
  strings.previewTitle='VibeZ 3'; strings.intro='VibeZ 3 · Rust / Tauri'; strings.isolatedStatus='VibeZ 3 · Rust / Tauri';
  const base=TRANSLATIONS[code]; strings.saved=base.saved||strings.saved;
  strings.updateManualHelp=base.openReleases||strings.updateManualHelp; strings.noDownloadHelp=base.updateFailed||strings.noDownloadHelp;
}
Object.assign(previewData.translations.en,{saved:'Saved.',limits:'Screenshots use your operating system tools. Updates are installed manually. Global shortcuts and microphone/camera access are not enabled.',trayHint:'Enable only when the system tray icon is available.',updateManualHelp:'Open the published VibeZ 3 release and install the package for your system.',bridgeError:'The application connection is unavailable',returningVibe:'Back to Vibe. Your profile is preserved.',noDownloadHelp:'No published VibeZ 3 download was found for this platform.'});
Object.assign(previewData.translations.nl,{saved:'Opgeslagen.',limits:'Schermafbeeldingen gebruiken de hulpmiddelen van je besturingssysteem. Updates installeer je handmatig. Globale sneltoetsen en microfoon/camera zijn niet ingeschakeld.',trayHint:'Alleen inschakelen wanneer het systeemvakpictogram beschikbaar is.',updateManualHelp:'Open de gepubliceerde VibeZ 3-release en installeer het pakket voor je systeem.',bridgeError:'De verbinding met de toepassing is niet beschikbaar',returningVibe:'Terug naar Vibe. Je profiel blijft behouden.',noDownloadHelp:'Geen gepubliceerde VibeZ 3-download gevonden voor dit platform.'});
'''
s=s.replace('const baseLanguages = Object.keys(TRANSLATIONS).sort();',extra+'const baseLanguages = Object.keys(TRANSLATIONS).sort();');write(p,s)
replace('frontend/index.html','>PREVIEW<','>3<');replace('frontend/index.html','Rust / Tauri · separate preview','Rust / Tauri')
for name in ['browser.rs','release_updates.rs']: shutil.copyfile(ROOT/'tools/v3-seed'/name,OUT/'src-tauri/src'/name)
for name in ['preview_updates.rs','preview_updates_windows.rs']: (OUT/'src-tauri/src'/name).unlink()
p='test/isolation.test.cjs';s=read(p).replace("assert.deepEqual(config.bundle.targets,['deb']);","assert.equal(config.bundle.targets,'all');")
a=s.index("test('manual update feed validates");b=s.index("test('native routing",a)
s=s[:a]+'''test('updates select published releases rather than CI artifacts', () => {
  const source=read('src-tauri/src/release_updates.rs');
  assert.match(source,/release\\["draft"\\]/); assert.match(source,/release\\["prerelease"\\]/);
  assert.match(source,/version.major < 3/); assert.doesNotMatch(source,/actions\\/runs/);
});
'''+s[b:]
s=s.replace("test('no production updater, URL protocol or Store identity is introduced'","test('native binary is separate and Store packaging uses the approved product'")
s=s.replace('scripts/build-windows-store-preview.ps1','scripts/build-store.ps1').replace(r'LeComputeur\.VibeZTauriPreview',r'LeComputeur\.VibeZDesktop');write(p,s)
store=read('scripts/build-windows-store-preview.ps1').replace('LeComputeur.VibeZTauriPreview','LeComputeur.VibeZDesktop').replace('Id="VibeZTauriPreview"','Id="VibeZDesktop"').replace('Experimental VibeZ desktop preview using Tauri and Microsoft WebView2.','VibeZ 3 desktop client for Mistral Vibe.').replace('-Store-Preview.msix','-Store.msix').replace('ShortName="VibeZ Preview"','ShortName="VibeZ 3"')
store=store.replace("if ($packed.Package.Identity.Name -eq 'LeComputeur.VibeZDesktop') { throw 'Refusing production Store identity' }",'# Package creation is not Store submission.')
write('scripts/build-store.ps1',store);(OUT/'scripts/build-windows-store-preview.ps1').unlink()
write('README.md','# VibeZ 3\n\nRust/Tauri 3.0.0 source for Linux AppImage/DEB/RPM/Arch/Flatpak, Windows EXE/MSI/MSIX and macOS Intel/Apple Silicon app/DMG/ZIP.\n\nApp identity: `nl.lecomputeur.vibez3`. Existing Electron and preview profiles are not silently copied or deleted. See ../V3-RELEASE.md for compatibility and release gates.\n\nBuild: `npm ci`, `npm test`, `npm run build -- -- --locked`. Resolved lockfiles are committed before native builds.\n')
write('RELEASE-GATE.md','# VibeZ 3 release gate\n\nAll required packaging jobs must succeed for one exact source commit. Native integration tests and dependency advisory audit are required. macOS deliverables require Developer ID signing and accepted notarization. Store MSIX creation is not Store submission. Failed or missing platforms block stable all-platform publication.\n')
for p in OUT.glob('TESTING-0.1.*.md'): p.unlink()
print('Created desktop/ for VibeZ 3.0.0; Electron and preview source untouched.')
