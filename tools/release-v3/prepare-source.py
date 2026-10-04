#!/usr/bin/env python3
"""Freeze the next reviewed integration fixes before all native builds."""
from pathlib import Path
import json
r=Path(__file__).resolve().parents[2]/'desktop'; marker=r/'.v3-integration-revision'
revision=marker.read_text().strip()
if revision=='2': raise SystemExit(0)
if revision!='1': raise SystemExit('Expected the committed first native integration corrections')
p=r/'src-tauri/src/auth.rs';s=p.read_text()
old='''#[cfg(target_os = "macos")]
pub fn attach_errors(_app: &AppHandle, _view: &Webview) -> Result<(), String> { Ok(()) }'''
new='''#[cfg(target_os = "macos")]
#[path = "macos_popup.rs"]
mod macos_popup;
#[cfg(target_os = "macos")]
pub fn attach_errors(app: &AppHandle, view: &Webview) -> Result<(), String> { macos_popup::attach(app, view) }'''
assert old in s;p.write_text(s.replace(old,new,1))
p=r/'package.json';pkg=json.loads(p.read_text());pkg['scripts']['build']='node scripts/build.cjs';p.write_text(json.dumps(pkg,indent=2)+'\n')
marker.write_text('2\n')
print('Recorded WKWebView popup closure and AppImage-specific desktop icon configuration.')
