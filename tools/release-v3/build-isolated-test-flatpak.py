#!/usr/bin/env python3
"""Repackage the verified Flatpak base under an independent test identity.

Never installs or runs a GUI. Existing app/profile/system files are untouched.
The supplied test executable must already have disabled updates and autostart.
"""
import argparse
import configparser
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from datetime import date
from xml.sax.saxutils import escape

APP = 'nl.lecomputeur.vibez3.CanvasTest'
BIN = 'vibez3-canvas-test'
NAME = 'VibeZ Canvas Test'
VERSION = '3.0.9+test.3'
BRANCH = 'canvas-test'
BASE_SHA = '0c8e1d9dfc172f851897757fd40fbc20d88ba1d99143eda66d5f889f466ba22c'
BASE_COMMIT = '39aac7756b1be2ffe5d528aeed69315045f72898cc7ebdbf29e8dec7f4f115b6'
BASE_TREE_SHA = '97e12ff2bed486c7fb4d66e76ce869d3d39dc621fb807151f75543410bf93a37'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_tree_digest(base):
    records = []
    for path in sorted(base.rglob('*')):
        relative = str(path.relative_to(base))
        if path.is_symlink():
            records.append([relative, 'symlink', str(path.readlink())])
        elif path.is_file():
            records.append([relative, 'file', digest(path)])
    return hashlib.sha256(json.dumps(records, separators=(',', ':')).encode()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def run(command, log):
    completed = subprocess.run([str(arg) for arg in command], text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with log.open('a') as stream:
        stream.write('$ ' + ' '.join(str(arg) for arg in command) + '\n' + completed.stdout)
    print(completed.stdout, end='', flush=True)
    completed.check_returncode()
    return completed.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-bundle', type=Path, required=True, help='Verified published VibeZ 3.0.8 Flatpak')
    parser.add_argument('--base-checkout', type=Path, required=True, help='OSTree checkout of that exact published bundle')
    parser.add_argument('--ostree-path', type=Path, help='OSTree CLI, required with --build if absent from PATH')
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--binary-sha256', required=True)
    parser.add_argument('--work', type=Path, required=True, help='New, empty output directory')
    parser.add_argument('--build', action='store_true', help='Export and bundle; still never installs')
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    if binary.name != BIN or digest(binary) != args.binary_sha256:
        parser.error('Expected exact, hashed side-by-side test executable')
    if APP.encode() not in binary.read_bytes():
        parser.error('Executable lacks the independent test application ID')
    version = subprocess.check_output([str(binary), '--version'], text=True,
                                     env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}).strip()
    if version != f'{NAME} V{VERSION}':
        parser.error(f'Unexpected test version: {version!r}')
    base = args.base_checkout.resolve(strict=True)
    bundle = args.base_bundle.resolve(strict=True)
    if digest(bundle) != BASE_SHA:
        parser.error('Published Flatpak base checksum changed')
    if base_tree_digest(base) != BASE_TREE_SHA:
        parser.error('Base checkout is not the exact verified published bundle tree')
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.optionxform = str
    metadata.read(base / 'metadata')
    if metadata['Application']['runtime'] != 'org.gnome.Platform/x86_64/50':
        parser.error('Unexpected base runtime; no silent runtime migration')
    work = args.work.resolve()
    if work.exists() and any(work.iterdir()):
        parser.error('Work directory must be empty; refusing to overwrite evidence')
    work.mkdir(parents=True, exist_ok=True)
    build, repo, log = work / 'build', work / 'repo', work / 'build.log'
    files = build / 'files'
    shutil.copytree(base / 'files', files, symlinks=True)
    libraries = {str(p.relative_to(files)): digest(p) for p in (files / 'lib').rglob('*')
                 if p.is_file() and not p.is_symlink()}
    (files / 'bin/vibez3').unlink()
    shutil.copy2(binary, files / 'bin' / BIN)
    (files / 'bin' / BIN).chmod(0o755)
    # Remove only copied metadata/exports; original base and installations stay intact.
    for relative in ['share/applications', 'share/metainfo', 'share/app-info']:
        target = files / relative
        if target.exists():
            shutil.rmtree(target)
    icons = files / 'share/icons/hicolor/512x512/apps'
    (icons / 'nl.lecomputeur.vibez3.png').rename(icons / f'{APP}.png')
    docs = files / 'share/doc' / APP
    docs.mkdir(parents=True)
    shutil.copy2(files / 'manifest.json', docs / 'original-flatpak-manifest.json')
    (files / 'manifest.json').unlink()
    metadata['Application']['name'] = APP
    metadata['Application']['command'] = BIN
    for section in list(metadata.sections()):
        if section.startswith('Extension ') or section == 'Build':
            metadata.remove_section(section)
    with (build / 'metadata').open('w') as stream:
        metadata.write(stream, space_around_delimiters=False)
    applications = files / 'share/applications'
    applications.mkdir(parents=True)
    (applications / f'{APP}.desktop').write_text(
        f'[Desktop Entry]\nType=Application\nName={NAME}\nComment=Separate experimental Canvas/Cloudflare test build\n'
        f'Exec={BIN}\nIcon={APP}\nTerminal=false\nCategories=Development;\nStartupWMClass={APP}\n')
    metainfo = files / 'share/metainfo'
    metainfo.mkdir(parents=True)
    (metainfo / f'{APP}.metainfo.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<component type="desktop-application">'
        f'<id>{APP}</id><metadata_license>CC0-1.0</metadata_license><project_license>MIT</project_license>'
        f'<name>{NAME}</name><summary>Separate experimental Canvas and Cloudflare test build</summary>'
        '<description><p>Experimental VibeZ test build with an independent application identity and profile. '
        'It does not replace the ordinary VibeZ installation.</p></description>'
        f'<launchable type="desktop-id">{APP}.desktop</launchable>'
        '<url type="homepage">https://github.com/lecomputeur/vibez</url>'
        f'<releases><release version="{escape(VERSION)}" date="{date.today().isoformat()}"/></releases>'
        '<content_rating type="oars-1.1"/></component>\n')
    provenance = {'appId': APP, 'command': BIN, 'productName': NAME, 'version': VERSION,
                  'branch': BRANCH, 'binarySha256': digest(binary), 'baseBundleSha256': BASE_SHA,
                  'baseCommit': BASE_COMMIT, 'runtime': metadata['Application']['runtime'],
                  'preservedLibrarySha256': libraries, 'scriptSha256': digest(Path(__file__)),
                  'installed': False, 'originalBaseModified': False,
                  'note': 'Dependencies copied from verified published Flatpak. Test binary rebuilt separately; updates/autostart must be disabled there.'}
    write(docs / 'test-build-provenance.json', provenance)
    write(files / 'manifest.json', provenance)
    for relative, expected in libraries.items():
        assert digest(files / relative) == expected, relative
    write(work / 'provenance.json', provenance)
    if args.build:
        ostree = args.ostree_path or shutil.which('ostree')
        if ostree is None:
            parser.error('OSTree CLI required for --build; pass --ostree-path')
        run([ostree, f'--repo={repo}', 'init', '--mode=archive-z2'], log)
        run(['flatpak', 'build-finish', f'--command={BIN}', build], log)
        run(['flatpak', 'build-export', '--disable-sandbox', '--arch=x86_64', repo, build, BRANCH], log)
        output = work / f'VibeZ-Canvas-Test-{VERSION}-Linux-x64.flatpak'
        run(['flatpak', 'build-bundle', repo, output, APP, BRANCH,
             '--runtime-repo=https://flathub.org/repo/flathub.flatpakrepo'], log)
        provenance['bundle'] = str(output)
        provenance['bundleSha256'] = digest(output)
        write(work / 'provenance.json', provenance)
    print(json.dumps(provenance, indent=2))


if __name__ == '__main__':
    main()
