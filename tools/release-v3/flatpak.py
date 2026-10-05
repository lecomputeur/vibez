#!/usr/bin/env python3
"""Build the v3 Flatpak with a consistent /app/lib dependency layout."""
from pathlib import Path
import json
import subprocess

APP = 'nl.lecomputeur.vibez3'
SHARED_REVISION = 'cb9ec602a1ece1c76d5a4f8aa1d87c4a6bf99c3e'


def fix_cmake_libdirs(module):
    """Keep CMake's libraries and pkg-config metadata in Flatpak's search path.

    Newer CMake/SDK combinations choose /app/lib64 for these shared modules.
    The next module searches /app/lib/pkgconfig and cannot find ayatana-ido.
    Apply the explicit install directory to each CMake module, not a linker
    search-path workaround or a disabled dependency check.
    """
    changed = []
    if not isinstance(module, dict):
        return changed
    if module.get('buildsystem') in ('cmake', 'cmake-ninja'):
        options = module.setdefault('config-opts', [])
        options[:] = [option for option in options
                      if not option.startswith('-DCMAKE_INSTALL_LIBDIR=')]
        options.append('-DCMAKE_INSTALL_LIBDIR=lib')
        changed.append(module['name'])
    for child in module.get('modules', []):
        changed.extend(fix_cmake_libdirs(child))
    return changed


def main():
    root = Path.cwd()
    out = root / 'release-assets'
    stage = root / 'flatpak-stage'
    stage.mkdir(exist_ok=True)
    packages = list(out.glob('*Linux-x64.deb'))
    if len(packages) != 1:
        raise SystemExit('Expected exactly one validated Linux DEB payload')
    subprocess.run(['dpkg-deb', '-x', str(packages[0]), str(stage / 'payload')], check=True)
    subprocess.run(['git', 'clone', 'https://github.com/flathub/shared-modules',
                    str(stage / 'shared-modules')], check=True)
    subprocess.run(['git', 'checkout', SHARED_REVISION],
                   cwd=stage / 'shared-modules', check=True)
    shared = stage / 'shared-modules/libayatana-appindicator/libayatana-appindicator-gtk3.json'
    dependencies = json.loads(shared.read_text())
    fixed = fix_cmake_libdirs(dependencies)
    if set(fixed) != {'libayatana-appindicator', 'ayatana-ido', 'libayatana-indicator'}:
        raise SystemExit(f'Unexpected shared-module layout: {fixed}')
    shared.write_text(json.dumps(dependencies, indent=2) + '\n')
    print('Flatpak library directory fixed to /app/lib for: ' + ', '.join(fixed), flush=True)

    (stage / 'vibez3.desktop').write_text(
        f'[Desktop Entry]\nName=VibeZ 3\nType=Application\nExec=vibez3\nIcon={APP}\n'
        f'Terminal=false\nCategories=Development;\nStartupWMClass={APP}\n')
    (stage / 'metainfo.xml').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application"><id>{APP}</id><metadata_license>CC0-1.0</metadata_license><project_license>MIT</project_license><name>VibeZ 3</name><summary>Desktop client for Mistral Vibe</summary><description><p>A dedicated Rust/Tauri desktop window for Mistral Vibe, with language selection and screenshot tools.</p></description><launchable type="desktop-id">{APP}.desktop</launchable><url type="homepage">https://github.com/lecomputeur/vibez</url><releases><release version="3.0.1" date="2026-10-05"/></releases><content_rating type="oars-1.1"/></component>''')
    manifest = {
        'app-id': APP, 'runtime': 'org.gnome.Platform', 'runtime-version': '50',
        'sdk': 'org.gnome.Sdk', 'command': 'vibez3',
        'finish-args': ['--share=network', '--share=ipc', '--socket=fallback-x11',
                        '--socket=wayland', '--device=dri', '--socket=pulseaudio',
                        '--talk-name=org.kde.StatusNotifierWatcher'],
        'modules': [
            'shared-modules/libayatana-appindicator/libayatana-appindicator-gtk3.json',
            {'name': 'vibez3', 'buildsystem': 'simple',
             'build-commands': [
                 'install -Dm755 payload/usr/bin/vibez3 /app/bin/vibez3',
                 f'install -Dm644 payload/usr/share/pixmaps/{APP}.png /app/share/icons/hicolor/512x512/apps/{APP}.png',
                 f'install -Dm644 vibez3.desktop /app/share/applications/{APP}.desktop',
                 f'install -Dm644 metainfo.xml /app/share/metainfo/{APP}.metainfo.xml'],
             'sources': [{'type': 'dir', 'path': 'payload', 'dest': 'payload'},
                         {'type': 'file', 'path': 'vibez3.desktop'},
                         {'type': 'file', 'path': 'metainfo.xml'}]}
        ]
    }
    (stage / f'{APP}.json').write_text(json.dumps(manifest, indent=2) + '\n')
    subprocess.run(['flatpak-builder', '--user', '--install', '--force-clean',
                    '--repo=repo', 'build', f'{APP}.json'], cwd=stage, check=True)
    version = subprocess.check_output(['flatpak', 'run', APP, '--version'], text=True)
    print(version, end='')
    if '3.0.1' not in version:
        raise SystemExit('Installed Flatpak does not report version 3.0.1')
    subprocess.run(['flatpak', 'build-bundle', 'repo',
                    str(out / 'VibeZ-3.0.1-Linux-x64.flatpak'), APP,
                    '--runtime-repo=https://flathub.org/repo/flathub.flatpakrepo'],
                   cwd=stage, check=True)


if __name__ == '__main__':
    main()
