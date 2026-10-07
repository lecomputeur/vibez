#!/usr/bin/env python3
"""Freeze complete platform inputs before any installer build."""
from pathlib import Path
import hashlib, os, subprocess, tomllib, re
ROOT=Path(__file__).resolve().parents[2]
if os.environ.get('GITHUB_REF')!='refs/heads/vibe/release-3.0.2-7e2b46':
    raise SystemExit('Release promotion is restricted to its dedicated branch')
if not (ROOT/'desktop/.release-302-finalized').is_file():
    raise SystemExit('The maintainer-approved production source must be materialized first')
def replace(path,old,new):
    p=ROOT/path;s=p.read_text()
    if old in s:p.write_text(s.replace(old,new))
    elif new not in s:raise RuntimeError('Unexpected platform source: '+path)
replace('desktop/src-tauri/src/screenshot_native_other.rs',
    'let config=WKSnapshotConfiguration::new();',
    '''let Some(mtm)=objc2::MainThreadMarker::new() else {
            if let Ok(mut slot)=tx.lock(){if let Some(tx)=slot.take(){let _=tx.send(Err("Snapshot requires main thread".into()));}}
            return;
        };
        let config=WKSnapshotConfiguration::new(mtm);''')
replace('desktop/src-tauri/src/screenshot_save_other.rs',
    'panel.setTitle(&NSString::from_str(&title));',
    'panel.setTitle(Some(&NSString::from_str(&title)));')
replace('desktop/src-tauri/src/screenshot_screen_windows.ps1',
    'public static string Select() {','public new static string Select() {')
desktop=ROOT/'desktop';manifest=desktop/'src-tauri/Cargo.toml';stamp=desktop/'.release-302-locks'
digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
if not stamp.exists() or stamp.read_text().strip()!=digest:
    version=tomllib.loads((desktop/'rust-toolchain.toml').read_text())['toolchain']['channel']
    subprocess.run(['rustup','toolchain','install',version,'--profile','minimal'],check=True)
    subprocess.run(['cargo','+'+version,'fetch','--manifest-path','src-tauri/Cargo.toml'],cwd=desktop,check=True)
    stamp.write_text(digest+'\n')
for filename in ['index.html','linux.html','windows.html','macos.html']:
    p=ROOT/'docs'/filename;s=p.read_text();s=s.replace('<section class="section" id="screenshots-302">','<section class="details" id="screenshots-302">');p.write_text(s)
p=ROOT/'README.md';s=p.read_text();s=s.replace("Screenshots use the operating system's interactive tools; updates are installed manually.","Screenshots offer native visible-page, full-loaded-page and desktop-area capture, with optional direct paste into a draft. Updates are installed manually.");p.write_text(s)
p=ROOT/'desktop/README.md';s=p.read_text();p.write_text(s.replace('3.0.0','3.0.2'))
(ROOT/'desktop/SCREENSHOT-3.0.2.md').write_text('''# VibeZ 3.0.2 screenshots

Production source promoted from maintainer-approved Mint test 6.

The compact chooser has three labels (Visible page, Full page, Selection) and the immediate-paste checkbox, translated in all 34 UI languages. It opens on VibeZ's monitor; manual repositioning remains possible.

Native WebKitGTK, WebView2 and WKWebView snapshots capture rendered page pixels. Full page expands loaded scroll areas and restores the original layout; unloaded or virtualized history is not available. Desktop selection uses native OS capture; Linux currently requires X11 and macOS may request Screen Recording permission.

Copy, Save PNG and immediate paste are separate user actions. Immediate paste preserves the draft and never presses Send. Attaching an image may cause the embedded Mistral service to upload it before a message is sent. Linux's own-PNG memory bridge repairs WebKitGTK image-paste limitations without giving remote pages native commands or arbitrary clipboard access.

All formats are built from one committed source with locked dependencies. Native tests check actual pixels, received PNGs, draft preservation and cancellation. The maintainer has tested Mint; automated Windows/macOS tests are not a claim of manual testing on every computer.
''')
p=ROOT/'docs/sitemap.xml';p.write_text(re.sub(r'<lastmod>[^<]+</lastmod>','<lastmod>2026-10-07</lastmod>',p.read_text()))
print('Platform source and dependencies ready to commit; every platform build remains --locked.')
