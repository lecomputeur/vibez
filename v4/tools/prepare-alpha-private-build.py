#!/usr/bin/env python3
"""Prepare encrypted native-build input without publishing app source or keys."""
import hashlib,json,os,secrets,subprocess,tarfile,tempfile
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
private=BASE/'.private';private.mkdir(mode=0o700,exist_ok=True)
password=private/'alpha-build-passphrase'
if not password.exists():
    password.write_text(secrets.token_urlsafe(48));password.chmod(0o600)
version=json.loads((BASE/'desktop/package.json').read_text())['version']
public=BASE/'artifacts/alpha-auto-update';public.mkdir(parents=True,exist_ok=True)
plain=private/'alpha-native-source.tar.gz'
encrypted=private/'alpha-native-source.tar.gz.gpg'
files=[]
for folder in ['backend','locales','standalone-ui','packaging','tests/standalone','desktop/src-tauri','desktop/frontend','desktop/scripts','desktop/standalone-tests']:
    for p in (BASE/folder).rglob('*'):
        rel=p.relative_to(BASE)
        if any(x in {'target','node_modules','dist','__pycache__','.git','.private','.cache','artifacts'} for x in rel.parts):continue
        if p.is_symlink():raise ValueError('Unexpected source symlink: '+str(rel))
        if not p.is_file():continue
        if p.suffix in {'.key','.p12','.pfx','.pem'}:raise ValueError('Unexpected private-key-like input: '+str(rel))
        if p.parent==BASE/'backend/vendor' and p.name.startswith('cloudflared-'):continue
        files.append(p)
for name in ['LICENSE','icon.png','shell.css','i18n.js','desktop/package.json','desktop/package-lock.json','desktop/rust-toolchain.toml','desktop/preview-i18n.json','tools/ci-alpha-build.py','tools/ci-alpha-backend-check.py','tools/ci-alpha-windows-install-check.py','tools/ci-alpha-windows-update-check.py','tools/test-alpha-real-native-update.py','tools/prepare-alpha-runtime.py','tools/prepare-alpha-cloudflared.py','tools/alpha-flatpak.py','tools/prepare-alpha-appimage-launcher.py']:
    files.append(BASE/name)
files=sorted(set(files))
with tarfile.open(plain,'w:gz') as stream:
    for p in files:stream.add(p,arcname=str(p.relative_to(BASE)),recursive=False)
plain.chmod(0o600)
try:
    # Validate the exact archive before it leaves the computer. This avoids
    # relying on extra files that happen to exist in the developer checkout.
    with tempfile.TemporaryDirectory(prefix='alpha-input-check-',dir=private) as temporary:
        source=Path(temporary)
        with tarfile.open(plain) as stream:stream.extractall(source,filter='data')
        prepared=subprocess.run(['node','scripts/prepare.cjs'],cwd=source/'desktop',stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if prepared.returncode:
            raise RuntimeError('Archived frontend preparation failed: '+prepared.stdout.decode(errors='replace')[-8000:])
        tests=sorted((source/'desktop/standalone-tests').glob('*.test.cjs'))
        assert tests, 'The archived frontend test suite is missing'
        checked=subprocess.run(['node','--test',*[str(path) for path in tests]],cwd=source/'desktop',stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if checked.returncode:
            raise RuntimeError('Archived frontend tests failed: '+checked.stdout.decode(errors='replace')[-8000:])
    subprocess.run(['gpg','--batch','--yes','--no-symkey-cache','--pinentry-mode','loopback','--passphrase-file',str(password),'--cipher-algo','AES256','--symmetric','--output',str(encrypted),str(plain)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
finally:plain.unlink(missing_ok=True)
assert encrypted.stat().st_size<40*1024*1024
encrypted_digest=hashlib.sha256(encrypted.read_bytes()).hexdigest()
asset=public/f'VibeZ-{version}-native-source-{encrypted_digest[:16]}.tar.gz.gpg'
if asset.exists():
    assert hashlib.sha256(asset.read_bytes()).hexdigest()==encrypted_digest
    encrypted.unlink()
else:
    encrypted.rename(asset)
asset.chmod(0o644)
manifest={'version':version,'files':[{'path':str(p.relative_to(BASE)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files], 'encrypted_asset_name':asset.name,'encrypted_sha256':encrypted_digest,'encrypted_size':asset.stat().st_size,'private_keys_included':False,'plaintext_source_published':False,'archived_frontend_preparation_passed':True,'archived_node_test_entrypoints_passed':len(tests)}
(public/'private-build-input.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'version':version,'files':len(files),'encrypted_asset_name':asset.name,'encrypted_size':asset.stat().st_size,'sha256':manifest['encrypted_sha256']}))
