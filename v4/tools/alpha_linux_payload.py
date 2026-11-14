"""Shared Alpha-only Linux packaging checks; no install or service activation."""
import hashlib, importlib.util, json, re, shutil, subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
APP_ID='nl.lecomputeur.vibez4.alpha'; BINARY='vibez4-alpha'; PRODUCT='VibeZ V4 Alpha'
BACKEND=Path('usr/lib')/PRODUCT/'backend'
BACKEND_FILES={'workspace_engine.py','standalone_engine.py','web_connector.py','automatic_connector.py','project_import.py','multi_workspace.py','capfs.py','document_reader.py','document_writer.py'}
def updater():
    spec=importlib.util.spec_from_file_location('alpha_package_updater',BASE/'packaging/alpha-updater/update.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def version():
    value=json.loads((BASE/'desktop/package.json').read_text())['version']
    updater().version(value);return value

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def add_update_files(payload,keyring=None):
    keyring=keyring or BASE/'desktop/src-tauri/alpha-updates.gpg'
    assert keyring.is_file() and not keyring.is_symlink(),'Missing Alpha update public key'
    for source,relative in [(BASE/'packaging/alpha-updater/update.py','usr/lib/vibez4-alpha-updater/update.py'),
        (keyring,'usr/lib/vibez4-alpha-updater/alpha-updates.gpg'),
        *[(BASE/'packaging/alpha-updater'/name,'usr/lib/systemd/system/'+name) for name in ['vibez4-alpha-update.service','vibez4-alpha-update.timer']]]:
        target=payload/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);target.chmod(0o644)

def check_payload(payload,expected=None):
    value=expected or version();binary=payload/'usr/bin'/BINARY
    assert binary.is_file() and not binary.is_symlink(),'Missing Alpha binary'
    assert APP_ID.encode() in binary.read_bytes(),'Missing independent Alpha application identity'
    result=subprocess.check_output([str(binary),'--version'],text=True,timeout=10)
    assert value in result and 'VibeZ V4 ' in result,result
    resources=payload/BACKEND;assert resources.is_dir()
    assert {p.name for p in resources.iterdir() if p.is_file()}==BACKEND_FILES,'All backend modules must be bundled'
    assert (resources/'vendor/cloudflared-linux-amd64').is_file()
    assert (resources/'vendor/LICENSE-cloudflared').is_file()
    for path in payload.rglob('*'):
        assert not path.is_symlink(),f'Unexpected payload symlink: {path}'
        assert '__pycache__' not in path.parts,'Release payload contains Python bytecode'
    desktop=payload/f'usr/share/applications/{APP_ID}.desktop'
    text=desktop.read_text()
    assert re.search(r'^Exec=vibez4-alpha(?:\s.*)?$',text,re.M),'Public launcher must not carry personal screen settings'
    assert 'Name=VibeZ V4 Beta\n' in text and 'vibez3' not in text and '.test' not in text
    for relative in ['usr/lib/vibez4-alpha-updater/update.py','usr/lib/vibez4-alpha-updater/alpha-updates.gpg',
                     'usr/lib/systemd/system/vibez4-alpha-update.service','usr/lib/systemd/system/vibez4-alpha-update.timer']:
        assert (payload/relative).is_file(),relative
    return value

def normalize_modes(payload):
    for path in payload.rglob('*'):
        if path.is_dir():path.chmod(0o755)
        elif path.is_file():path.chmod(0o755 if path.name in {BINARY,'cloudflared-linux-amd64'} else 0o644)
