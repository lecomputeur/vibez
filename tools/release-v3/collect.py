#!/usr/bin/env python3
"""Canonical v3 names; fail closed when any requested format is absent."""
from pathlib import Path
import json, shutil, sys, hashlib, subprocess
ROOT=Path(__file__).resolve().parents[2]; DESK=ROOT/'desktop'; OUT=ROOT/'release-assets';OUT.mkdir(exist_ok=True)
v=json.loads((DESK/'package.json').read_text())['version']; assert v=='3.0.2'
platform=sys.argv[1]
patterns={'linux': [('deb','deb'),('rpm','rpm'),('appimage','AppImage')], 'windows':[('nsis','exe'),('msi','msi')]}
for folder,ext in patterns.get(platform,[]):
    files=list((DESK/'src-tauri/target/release/bundle'/folder).glob('*.'+ext))
    if len(files)!=1: raise SystemExit(f'Expected exactly one {ext}, found {files}')
    suffix='-Setup' if ext=='exe' else ''
    name=f'VibeZ-{v}-{platform.title()}-x64{suffix}.{ext}'
    shutil.copyfile(files[0],OUT/name)
if platform=='linux':
    deb=next(OUT.glob('*.deb'))
    values=subprocess.check_output(['dpkg-deb','-f',str(deb),'Package','Version','Architecture'],text=True)
    assert 'vibe-z-3' in values and v in values and 'amd64' in values,values
    (OUT/'linux-package.txt').write_text(values)
    app=next(OUT.glob('*.AppImage'));app.chmod(0o755)
    temp=ROOT/'appimage-check';temp.mkdir(exist_ok=True)
    subprocess.run([str(app),'--appimage-extract'],cwd=temp,check=True,stdout=subprocess.DEVNULL)
    binary=temp/'squashfs-root/usr/bin/vibez3'
    assert binary.exists(),'AppImage does not contain the v3 binary'
    assert v in subprocess.check_output([str(binary),'--version'],text=True)
    assert subprocess.check_output(['rpm','-qp','--qf','%{VERSION}',str(next(OUT.glob('*.rpm')))],text=True).strip()==v
if platform=='all':
    required=[f'Linux-x64.{e}' for e in ['deb','rpm','AppImage','pkg.tar.zst','flatpak']]+['Windows-x64-Setup.exe','Windows-x64.msi','Windows-x64-Store.msix']+[f'macOS-{a}.{e}' for a in ['x64','arm64'] for e in ['dmg','zip']]
    for suffix in required:
        f=OUT/f'VibeZ-{v}-{suffix}'
        if not f.is_file() or f.stat().st_size<1024: raise SystemExit(f'Missing/empty required release asset: {f.name}')
    files=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='SHA256SUMS')
    (OUT/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in files))
    print(f'ALL_FORMATS_OK: {len(required)} required v{v} installer/archive assets present')
