#!/usr/bin/env python3
"""One-time deterministic release promotion of the maintainer-approved Mint source."""
from pathlib import Path
import json, re, os
ROOT=Path(__file__).resolve().parents[2]
MARKER=ROOT/'desktop/.release-302-finalized'
if MARKER.exists():
    print('Release 3.0.2 source already finalized');raise SystemExit(0)
if os.environ.get('GITHUB_REF')!='refs/heads/vibe/release-3.0.2-7e2b46':
    raise SystemExit('Release promotion is restricted to its dedicated branch')
def edit(path,old,new,count=1):
    f=ROOT/path;s=f.read_text()
    if s.count(old)<count:raise RuntimeError(f'Missing source anchor in {path}: {old[:80]}')
    f.write_text(s.replace(old,new,count))
def transform(path,fn):
    f=ROOT/path;f.write_text(fn(f.read_text()))
# Root Electron/preview application inputs intentionally remain untouched.
edit('desktop/src-tauri/Cargo.toml','features = ["Win32_Globalization", "Win32_System_Com"]','features = ["Win32_Globalization", "Win32_System_Com", "Win32_UI_Shell", "Win32_UI_Shell_Common"]')
with (ROOT/'desktop/src-tauri/Cargo.toml').open('a') as f:
    f.write('\nobjc2-app-kit = "=0.3.2"\nblock2 = "=0.6.2"\n\n[target.\'cfg(not(target_os = "linux"))\'.dependencies]\nimage = { version = "=0.25.10", default-features = false, features = ["png"] }\n')
f=ROOT/'desktop/src-tauri/Cargo.lock';s=f.read_text();a=s.index('name = "vibez3"');b=s.index('[[package]]',a)
block=s[a:b].replace(' "gtk",',' "block2",\n "gtk",\n "image",').replace(' "objc2",',' "objc2",\n "objc2-app-kit",')
f.write_text(s[:a]+block+s[b:])
edit('desktop/src-tauri/src/main.rs',' · screenshot test 6','')
edit('desktop/src-tauri/src/main.rs','"build_label": "test 6"','"build_label": ""')
for p in ['desktop/tests/screenshot-e2e.py','desktop/tests/screenshot-monitors.py']:
    transform(p,lambda s:s.replace('VibeZ · .*test 6','VibeZ · .*'))
# All page capture engines take native pixels; Linux's approved path is unchanged.
p='desktop/src-tauri/src/screenshots.rs'
edit(p,'const SCRIPT: &str','#[cfg(not(target_os="linux"))]\n#[path="screenshot_native_other.rs"] pub(super) mod native_other;\nconst SCRIPT: &str')
edit(p,'"native":cfg!(target_os="linux")','"native":true')
edit(p,'let library=if cfg!(target_os="linux") { "" } else { SNAPDOM };','let library="";')
edit(p,'                #[cfg(target_os="linux")]\n                if payload["status"]=="ready" {','                if payload["status"]=="ready" {')
edit(p,'                    let bytes=native_linux::snapshot(view,mode,&payload).await?;','                    #[cfg(target_os="linux")]\n                    let bytes=native_linux::snapshot(view,mode,&payload).await?;\n                    #[cfg(not(target_os="linux"))]\n                    let bytes=native_other::snapshot(view,mode,&payload).await?;')
edit(p,'"engine":"WebKitGTK native snapshot"','"engine":if cfg!(target_os="linux"){"WebKitGTK native snapshot"}else if cfg!(target_os="windows"){"WebView2 native snapshot"}else{"WKWebView native snapshot"}')
edit('desktop/src-tauri/src/capture_page.js',"state.result = JSON.stringify({status:'ready',rect,viewport,geometry:fullGeometry});","state.result = JSON.stringify({status:'ready',rect,viewport,geometry:fullGeometry,scroll:{x:scrollX,y:scrollY}});")
# OS paste remains receipt-verified, with only our own PNG eligible for fallback.
p='desktop/src-tauri/src/screenshot_paste.rs'
edit(p,'''        #[cfg(not(target_os="linux"))]
        {return Err("Direct paste is enabled only in this Linux test. Use Copy.".into());}''','''        #[cfg(target_os="windows")]
        {
            for kind in ["rawKeyDown","keyUp"] {
                screenshots::native_other::devtools(&view,"Input.dispatchKeyEvent",serde_json::json!({
                    "type":kind,"modifiers":2,"key":"v","code":"KeyV","windowsVirtualKeyCode":86,"nativeVirtualKeyCode":86
                })).await?;
            }
        }
        #[cfg(target_os="macos")]
        {
            let(tx,rx)=tokio::sync::oneshot::channel();
            view.with_webview(move |platform|unsafe {
                let native=&*platform.inner().cast::<objc2_web_kit::WKWebView>();
                let _:()=objc2::msg_send![native,paste:std::ptr::null::<objc2::runtime::AnyObject>()];
                let _=tx.send(());
            }).map_err(err)?;
            tokio::time::timeout(Duration::from_secs(3),rx).await.map_err(err)?.map_err(err)?;
        }''')
p='desktop/src-tauri/src/screenshot_dialog.rs'
edit(p,'#[path="screenshot_paste.rs"] mod paste_composer;','''#[path="screenshot_paste.rs"] mod paste_composer;
#[cfg(not(target_os="linux"))]
#[path="screenshot_save_other.rs"] mod save_other;
#[cfg(not(target_os="linux"))]
#[path="screenshot_screen_other.rs"] mod screen_other;
#[cfg(not(target_os="linux"))]
#[path="screenshot_release_probe.rs"] mod release_probe;
#[cfg(not(target_os="linux"))]
pub async fn release_smoke_check(app:&AppHandle)->Result<(),String>{release_probe::run(app).await}''')
edit(p,'VibeZ · {} · test 6','VibeZ · {}')
edit(p,'let builder=builder.center();','let builder=builder.visible(false);')
edit(p,'    show_on_parent(app,&window).await?;','    show_on_parent(app,&window).await?;\n    #[cfg(not(target_os="linux"))]\n    show_on_parent_other(app,&window)?;')
edit(p,'pub async fn capture(app:','''#[cfg(not(target_os="linux"))]
fn show_on_parent_other(app:&AppHandle,child:&tauri::WebviewWindow)->Result<(),String>{
    let parent=app.get_window("main").ok_or("VibeZ window unavailable")?;
    let origin=parent.outer_position().map_err(err)?;let size=parent.outer_size().map_err(err)?;
    let child_size=child.outer_size().map_err(err)?;
    let mut x=i64::from(origin.x)+(i64::from(size.width)-i64::from(child_size.width))/2;
    let mut y=i64::from(origin.y)+(i64::from(size.height)-i64::from(child_size.height))/2;
    if let Some(monitor)=parent.current_monitor().map_err(err)?{
        let left=i64::from(monitor.position().x);let top=i64::from(monitor.position().y);
        let right=left+i64::from(monitor.size().width);let bottom=top+i64::from(monitor.size().height);
        x=x.clamp(left,(right-i64::from(child_size.width)).max(left));
        y=y.clamp(top,(bottom-i64::from(child_size.height)).max(top));
    }
    child.set_position(tauri::PhysicalPosition::new(x as i32,y as i32)).map_err(err)?;
    child.show().map_err(err)
}
pub async fn capture(app:''')
edit(p,'''    #[cfg(target_os="linux")]
    let mut result=if mode=="selection" {capture_desktop(app).await} else {screenshots::capture_preview(app,mode).await};
    #[cfg(not(target_os="linux"))]
    let mut result=screenshots::capture_preview(app,mode).await;''','''    let mut result=if mode=="selection" {capture_desktop(app).await} else {screenshots::capture_preview(app,mode).await};''')
edit(p,'#[cfg(target_os="linux")]\nasync fn capture_desktop','async fn capture_desktop')
edit(p,'    let Some(bytes)=screen_linux::capture(app,desktop_ui::language(app)=="nl").await? else{return Ok(json!({"cancelled":true}));};','''    #[cfg(target_os="linux")]
    let captured=screen_linux::capture(app,desktop_ui::language(app)=="nl").await?;
    #[cfg(not(target_os="linux"))]
    let captured=screen_other::capture().await?;
    let Some(bytes)=captured else{return Ok(json!({"cancelled":true}));};''')
edit(p,'async fn save(_app:&AppHandle,_bytes:Vec<u8>)->Result<Value,String>{Err("Save is not enabled in this Linux test candidate. Use Copy.".into())}','async fn save(app:&AppHandle,bytes:Vec<u8>)->Result<Value,String>{save_other::save(app,bytes).await}')
edit('desktop/frontend/screenshot.js',"$('save').hidden=state.platform!=='linux';","$('save').hidden=false;")
edit('desktop/test/screenshot-monitor.test.cjs','let builder=builder\\.center\\(\\)','let builder=builder\\.visible\\(false\\)')
# New platform receipt checks run last, after the existing auth/layout checks.
p='desktop/src-tauri/src/smoke.rs'
edit(p,'    thread::sleep(Duration::from_millis(500)); check_layout(app)?;\n    Ok(())','    thread::sleep(Duration::from_millis(500)); check_layout(app)?;\n    #[cfg(not(target_os="linux"))]\n    tauri::async_runtime::block_on(crate::screenshot_dialog::release_smoke_check(app))?;\n    Ok(())')
edit('desktop/src-tauri/src/screenshot_fixture.js',"const meta=document.createElement('meta');meta.httpEquiv", "const meta=document.createElement('meta');meta.setAttribute('data-vibez-test-csp','');meta.httpEquiv")
# Canonical versioned package names, packaging metadata and publication verifiers.
for name in ['collect.py','arch.sh','flatpak.py','sign-macos.sh','verify-published-assets.py','legacy-feed.cjs']:
    transform('tools/release-v3/'+name,lambda s:s.replace('3.0.1','3.0.2'))
p='tools/release-v3/collect.py'
edit(p,"files=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='SHA256SUMS')","files=sorted([OUT/f'VibeZ-{v}-{suffix}' for suffix in required]+[OUT/'source-commit.txt'])")
# Public copy changes are held on this release branch until every package passes.
for name in ['README.md','V3-RELEASE.md','docs/index.html','docs/linux.html','docs/windows.html','docs/macos.html','docs/code-signing-policy.html']:
    transform(name,lambda s:s.replace('3.0.1','3.0.2').replace('actions/runs/37346347043','actions/workflows/vibez-v3.yml'))
(ROOT/'V3-RELEASE.md').write_text('''# VibeZ 3.0.2 — Compact screenshots, direct paste, correct monitor

VibeZ 3 is the independent Mistral Vibe desktop client rebuilt in Rust with Tauri.

## New in 3.0.2

The compact screenshot chooser offers Visible page, Full page and Selection. It opens beside VibeZ on the same monitor and follows the selected interface language in all 34 supported languages. Explanatory paragraphs have been removed from the menu.

Screenshots can be pasted directly into the current Chat or Work draft, copied, or saved as PNG. Existing draft text is preserved. VibeZ never sends your message automatically. Linux includes a memory-only compatibility fix for WebKitGTK image pasting and ownership-aware Ctrl+V handling.

Page screenshots use native browser pixels instead of reconstructing website images. Full page captures loaded content, including expanded scroll areas; it cannot capture unloaded or virtualized history. Desktop area selection uses native OS capture. Linux desktop selection currently requires X11; macOS may request Screen Recording permission. Code workflows can save the PNG into the project rather than attach it to a chat.

## Downloads

Linux x64: AppImage, DEB, RPM, Arch/Pacman and Flatpak. Windows x64: EXE installer, MSI and Microsoft Store MSIX. macOS Intel and Apple Silicon: signed and notarized DMG and ZIP packages. All required packages must pass the release gate before publication.

Linux: Ubuntu 24.04 / Linux Mint 22 or compatible glibc 2.39+ systems with WebKitGTK 4.1. macOS: 14 or later. Windows: Windows 10/11 with WebView2.

The Mint build was approved by the maintainer after screenshot, paste, small-menu and two-monitor testing. Automated checks additionally exercise native page capture, actual image receipt, draft preservation, cancellation and package integrity. A successful build is not a claim of manual testing of every hardware combination.

## Updating

Quit VibeZ completely before replacing a previous installation. Reinstall explicitly when replacing a 3.0.2 Mint test package; the production title no longer includes a test marker. Direct installations use GitHub release update checks. Store delivery is separate: the MSIX is an upload package, not evidence of Microsoft submission or approval.

Electron v2 and the separate Tauri preview remain archived and unchanged. Historical Electron update feeds continue to reference their original packages, never an incompatible Tauri executable.
''')
(ROOT/'MICROSOFT-STORE.md').write_text('''# VibeZ Desktop — Microsoft Store package 3.0.2

## Existing product identity — do not create a new Store app

- Product: VibeZ Desktop
- Product ID: 9NR7L2G4MS08
- Identity: LeComputeur.VibeZDesktop
- Publisher: CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95
- Package version: 3.0.2.0, x64
- Application executable: vibez3.exe (Rust/Tauri, not the archived Electron executable)

## Build and validate

Use the all-desktop workflow `.github/workflows/vibez-v3.yml`. It builds the exact frozen source for every platform. The Windows job invokes `desktop/scripts/build-store.ps1`, packs the MSIX with MakeAppx and unpacks it to verify identity, display name and version. The output is `VibeZ-3.0.2-Windows-x64-Store.msix`.

The Store upload package is intentionally unsigned; Microsoft signs delivered Store packages. Use the EXE or MSI for ordinary direct installation. Building the MSIX does not submit or certify the update.

## Submission

Open the existing product in Partner Center, create an update submission, and add the new MSIX under Packages. Retain the existing product identity, pricing and age-rating declarations. Review supported languages and the listing text below, then submit for certification. Do not claim the Store is running 3.0.2 until Partner Center confirms the submission is published.

Retain the product declaration that the app allows purchases without using Microsoft Store commerce when the embedded Mistral service offers its own paid upgrade. VibeZ is independent and is not affiliated with or supported by Mistral AI.

## English update text

VibeZ 3.0.2 adds a compact, translated screenshot menu with Visible page, Full page and Selection. Copy, save PNG or paste directly into a Chat or Work draft without sending the message. Screenshot controls open on the same monitor as VibeZ. Full-page capture includes loaded content, not unloaded history. This independent desktop client opens the official Mistral Vibe service; a Mistral account and service-specific paid plan may be required for some features.

## Nederlandse updatebeschrijving

VibeZ 3.0.2 heeft een compact, vertaald screenshotmenu met Zichtbare pagina, Hele pagina en Selectie. Kopieer de opname, sla hem op als PNG of plak hem meteen in een Chat- of Work-concept, zonder het bericht te versturen. Het screenshotvenster opent op hetzelfde scherm als VibeZ. Hele pagina omvat geladen inhoud, niet nog niet geladen geschiedenis. Deze onafhankelijke desktopclient opent de officiële Mistral Vibe-dienst; voor sommige functies kan een Mistral-account of betaald abonnement nodig zijn.
''')
for p in ['docs/index.html','docs/linux.html','docs/windows.html','docs/macos.html']:
    f=ROOT/p;s=f.read_text()
    extra='<section class="section" id="screenshots-302"><h2>Screenshots in VibeZ 3.0.2</h2><p>A compact menu with Visible page, Full page and Selection, translated into all 34 interface languages. Copy, save a PNG or paste directly into your Chat or Work draft without sending it. The menu opens on the same monitor as VibeZ.</p><p>Full page captures loaded content, not unloaded history. Linux desktop selection requires X11. macOS desktop capture may require Screen Recording permission. The Microsoft Store release follows its separate certification process.</p></section>'
    if '</main>' not in s:raise RuntimeError('Missing main element: '+p)
    f.write_text(s.replace('</main>',extra+'\n</main>',1))
f=ROOT/'README.md';s=f.read_text();s+='\n## Screenshots in 3.0.2\n\nCompact three-option menu, 34 bundled languages, same-monitor placement, direct image paste into a draft, Copy and Save PNG. No automatic message sending. Full page captures loaded content only. Linux desktop selection uses X11; macOS may require Screen Recording permission. The Store MSIX is built separately from Microsoft certification.\n';f.write_text(s)
MARKER.write_text('3.0.2 production source, promoted from maintainer-approved Mint test 6 (8008d50ffb848e9969949a5c5a9ec0ceacf31a2b).\n')
print('Release source finalized; commit this exact tree before building.')
