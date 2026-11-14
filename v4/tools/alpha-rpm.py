#!/usr/bin/python3
"""Build the independent Linux Alpha RPM from the verified Tauri payload.

No installation, profile migration, process termination or GitHub write occurs.
The native RPM dependency generator records the ELF SONAME/version requirements.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

BASE = Path(__file__).resolve().parents[1]
APP_ID = 'nl.lecomputeur.vibez4.alpha'
BINARY = 'vibez4-alpha'
PRODUCT = 'VibeZ V4 Alpha'  # install path; unchanged so updates keep working
LABEL = 'VibeZ V4 Beta'
from alpha_linux_payload import version as alpha_version, updater
VERSION = alpha_version()
NUMERIC_VERSION, PRERELEASE = VERSION.split('-', 1)  # PRERELEASE: alpha.31, beta.1
BACKEND = Path('usr/lib') / PRODUCT / 'backend'
BACKEND_FILES = {'workspace_engine.py', 'standalone_engine.py', 'web_connector.py',
                 'automatic_connector.py', 'project_import.py', 'multi_workspace.py', 'capfs.py','document_reader.py','document_writer.py'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, log):
    done = subprocess.run([str(arg) for arg in args], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with log.open('a') as stream:
        stream.write('$ ' + ' '.join(map(str, args)) + '\n' + done.stdout)
    done.check_returncode()
    return done.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True,
                        help='Extracted verified Alpha DEB root containing usr/')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    payload = args.payload.resolve(strict=True)
    output = args.output.resolve()
    assert not output.exists(), 'Refusing to replace an existing candidate'
    binary = payload / 'usr/bin' / BINARY
    assert binary.is_file() and not binary.is_symlink()
    assert APP_ID.encode() in binary.read_bytes(), 'Missing independent application identity'
    version = subprocess.check_output([str(binary), '--version'], text=True, timeout=10)
    assert VERSION in version and 'VibeZ V4 ' in version, version
    resources = payload / BACKEND
    assert resources.is_dir()
    assert {p.name for p in resources.iterdir() if p.is_file()} == BACKEND_FILES
    assert (resources / 'vendor/cloudflared-linux-amd64').is_file()
    assert (resources / 'vendor/LICENSE-cloudflared').is_file()
    for path in resources.rglob('*'):
        assert not path.is_symlink(), f'Unexpected resource symlink: {path}'
        assert '__pycache__' not in path.parts, 'Remove bytecode from the release payload'
    license_path = BASE / 'LICENSE'
    assert license_path.is_file(), 'Include the project MIT license before building'
    desktop_path = payload / f'usr/share/applications/{APP_ID}.desktop'
    desktop = desktop_path.read_text()
    assert f'Exec={BINARY}' in desktop and f'Name={LABEL}' in desktop
    assert 'vibez3' not in desktop and '.test' not in desktop

    artifacts = BASE / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='alpha-rpm-', dir=artifacts))
    for name in ['BUILD', 'BUILDROOT', 'RPMS', 'SOURCES', 'SPECS', 'SRPMS', 'tmp']:
        (work / name).mkdir()
    staged = work / 'alpha-payload'
    staged.mkdir()

    def put(source, relative):
        target = staged / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    from alpha_linux_payload import add_update_files
    put(binary, Path('usr/bin') / BINARY)
    shutil.copytree(resources, staged / BACKEND)
    put(desktop_path, Path(f'usr/share/applications/{APP_ID}.desktop'))
    icon = payload / f'usr/share/icons/hicolor/512x512/apps/{APP_ID}.png'
    assert icon.is_file()
    put(icon, Path(f'usr/share/icons/hicolor/512x512/apps/{APP_ID}.png'))
    put(icon, Path(f'usr/share/pixmaps/{APP_ID}.png'))
    put(license_path, Path(f'usr/share/licenses/{BINARY}/LICENSE'))
    metadata = staged / f'usr/share/metainfo/{APP_ID}.metainfo.xml'
    metadata.parent.mkdir(parents=True)
    metadata.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>{APP_ID}</id>
  <metadata_license>CC0-1.0</metadata_license><project_license>MIT</project_license>
  <name>{LABEL}</name><summary>Mistral web conversations with local project folders</summary>
  <description><p>An independent alpha of the VibeZ Mistral desktop client, with a local folder per project or conversation and reviewed file changes.</p></description>
  <launchable type="desktop-id">{APP_ID}.desktop</launchable>
  <url type="homepage">https://github.com/lecomputeur/vibez</url>
  <releases><release version="{VERSION}" date="2026-10-31" type="development"/></releases>
  <content_rating type="oars-1.1"/>
</component>
''')
    add_update_files(staged)
    helper = updater()
    for path in staged.rglob('*'):
        if path.is_file():
            path.chmod(0o755 if path == staged / 'usr/bin' / BINARY or path.name == 'cloudflared-linux-amd64' else 0o644)
    archive = work / 'SOURCES/alpha-payload.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        stream.add(staged, arcname='alpha-payload')
    spec = work / 'SPECS/vibez4-alpha.spec'
    spec.write_text(f'''%global debug_package %{{nil}}
%global _build_id_links none
%global __brp_mangle_shebangs %{{nil}}
%global __os_install_post %{{nil}}
Name: {BINARY}
Version: {NUMERIC_VERSION}
Release: 0.{PRERELEASE}
Summary: Mistral desktop client with local project folders (Alpha)
License: MIT
URL: https://github.com/lecomputeur/vibez
Source0: alpha-payload.tar.gz
BuildArch: x86_64
Requires: python3 >= 3.10
Requires: ca-certificates
Requires: /usr/bin/gpgv
Requires: systemd
Requires: coreutils
Requires: xdg-desktop-portal
Requires: xdg-utils
Recommends: xdg-desktop-portal-gtk
AutoReqProv: yes

%description
VibeZ V4 Beta keeps the familiar Mistral web interface and connects one local
folder to each project or conversation. This alpha has its own application
identity and profile, and can coexist with VibeZ 3.0.9.

%prep
%setup -q -n alpha-payload

%build

%install
mkdir -p %{{buildroot}}
cp -a . %{{buildroot}}/

%posttrans
{helper.RPM_ENABLE}

%preun
{helper.RPM_REMOVE}

%files
/usr/bin/{BINARY}
%dir "/usr/lib/{PRODUCT}"
"/usr/lib/{PRODUCT}/backend"
/usr/lib/vibez4-alpha-updater
/usr/lib/systemd/system/vibez4-alpha-update.service
/usr/lib/systemd/system/vibez4-alpha-update.timer
/usr/share/applications/{APP_ID}.desktop
/usr/share/icons/hicolor/512x512/apps/{APP_ID}.png
/usr/share/pixmaps/{APP_ID}.png
/usr/share/metainfo/{APP_ID}.metainfo.xml
%license /usr/share/licenses/{BINARY}/LICENSE
''')
    log = work / 'build.log'
    run(['rpmbuild', '-bb', '--define', f'_topdir {work}', '--define', f'_tmppath {work / "tmp"}', str(spec)], log)
    packages = list((work / 'RPMS').rglob('*.rpm'))
    assert len(packages) == 1
    rpm = packages[0]
    scripts = run(['rpm', '-qp', '--scripts', rpm], log)
    helper.validate_rpm(rpm, VERSION)
    manifest = run(['rpm', '-qpl', rpm], log).splitlines()
    assert not any('vibez3' in line or 'vibez4.test' in line for line in manifest)
    required = run(['rpm', '-qp', '--requires', rpm], log).splitlines()
    assert any(line.startswith('libwebkit2gtk-4.1.so.0') for line in required)
    assert any(line.startswith('libc.so.6(GLIBC_') for line in required)
    assert 'python3 >= 3.10' in required
    assert run(['rpm', '-qp', '--conflicts', rpm], log).strip() == ''
    assert run(['rpm', '-qp', '--obsoletes', rpm], log).strip() == ''
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(rpm, output)
    report = {
        'version': VERSION, 'package': str(output), 'rpm_name': BINARY,
        'rpm_version_release': f'{NUMERIC_VERSION}-0.{PRERELEASE}', 'sha256': digest(output),
        'source_binary_sha256': digest(binary), 'build_directory': str(work),
        'independent_identity': APP_ID, 'only_allowlisted_update_service_hooks': True,
        'no_conflicts_or_obsoletes': True, 'automatic_elf_requires': required,
        'manifest': manifest, 'installed_on_host': False, 'published': False,
        'passed': True,
    }
    output.with_suffix('.rpm.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['version', 'package', 'sha256', 'passed']}, indent=2))


if __name__ == '__main__':
    main()
