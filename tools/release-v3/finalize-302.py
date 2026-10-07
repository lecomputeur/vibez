#!/usr/bin/env python3
"""Freeze the additional platform dependency edges before any installer build."""
from pathlib import Path
import hashlib, os, subprocess, tomllib
ROOT=Path(__file__).resolve().parents[2]
if os.environ.get('GITHUB_REF')!='refs/heads/vibe/release-3.0.2-7e2b46':
    raise SystemExit('Release promotion is restricted to its dedicated branch')
if not (ROOT/'desktop/.release-302-finalized').is_file():
    raise SystemExit('The maintainer-approved production source must be materialized first')
desktop=ROOT/'desktop';manifest=desktop/'src-tauri/Cargo.toml';stamp=desktop/'.release-302-locks'
digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
if not stamp.exists() or stamp.read_text().strip()!=digest:
    version=tomllib.loads((desktop/'rust-toolchain.toml').read_text())['toolchain']['channel']
    subprocess.run(['rustup','toolchain','install',version,'--profile','minimal'],check=True)
    # cargo fetch preserves existing locked versions and resolves missing feature
    # dependencies. Commit its resulting lock before the --locked platform builds.
    subprocess.run(['cargo','+'+version,'fetch','--manifest-path','src-tauri/Cargo.toml'],cwd=desktop,check=True)
    stamp.write_text(digest+'\n')
for filename in ['index.html','linux.html','windows.html','macos.html']:
    p=ROOT/'docs'/filename;s=p.read_text();s=s.replace('<section class="section" id="screenshots-302">','<section class="details" id="screenshots-302">');p.write_text(s)
p=ROOT/'README.md';s=p.read_text();s=s.replace("Screenshots use the operating system's interactive tools; updates are installed manually.","Screenshots offer native visible-page, full-loaded-page and desktop-area capture, with optional direct paste into a draft. Updates are installed manually.");p.write_text(s)
p=ROOT/'docs/sitemap.xml';s=p.read_text()
import re
p.write_text(re.sub(r'<lastmod>[^<]+</lastmod>','<lastmod>2026-10-07</lastmod>',s))
print('Resolved dependencies and release inputs ready to commit; every platform build remains --locked.')
