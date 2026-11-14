#!/usr/bin/python3
"""Build an independent V4 Alpha Flatpak from the checked native executable.

Only the requested new build directory and output bundle are written. This
does not install, launch, change remotes, or alter any VibeZ 3/Test profile.
"""
import argparse
import configparser
from datetime import date
import hashlib
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[1]
APP='nl.lecomputeur.vibez4.alpha'
BIN='vibez4-alpha'
NAME='VibeZ V4 Alpha'  # install path inside the Flatpak; unchanged so updates keep working
LABEL='VibeZ V4 Beta'  # the name people see
VERSION=json.loads((ROOT/'desktop/package.json').read_text())['version']
BRANCH='alpha'
RUNTIME='org.gnome.Platform/x86_64/51'
BASE_TREE_SHA='97e12ff2bed486c7fb4d66e76ce869d3d39dc621fb807151f75543410bf93a37'
BASE_URL='https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-Linux-x64.flatpak'
BASE_BUNDLE_SHA='0c8e1d9dfc172f851897757fd40fbc20d88ba1d99143eda66d5f889f466ba22c'
BASE_COMMIT='39aac7756b1be2ffe5d528aeed69315045f72898cc7ebdbf29e8dec7f4f115b6'
BACKENDS=('standalone_engine.py','workspace_engine.py','web_connector.py','automatic_connector.py','project_import.py','multi_workspace.py','capfs.py','document_reader.py','document_writer.py')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def tree_digest(base):
    rows=[]
    for path in sorted(base.rglob('*')):
        relative=str(path.relative_to(base))
        if path.is_symlink():rows.append([relative,'symlink',str(path.readlink())])
        elif path.is_file():rows.append([relative,'file',digest(path)])
    return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()

def write_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def desktop_entry():
    # Flatpak rewrites Exec for the host on installation. In particular, never
    # add a TryExec=/app/... path: it does not exist outside the sandbox and
    # would hide an otherwise installed application from desktop menus.
    return ('[Desktop Entry]\nType=Application\n'+f'Name={LABEL}\n'
        'GenericName=Mistral client\nKeywords=Mistral;AI;Chat;VibeZ;\n'
        'Comment=Mistral web conversations with chosen local workspaces\n'
        f'Exec={BIN}\nIcon={APP}\nTerminal=false\nCategories=Development;\n'
        f'StartupWMClass={APP}\nDBusActivatable=false\n')

def check_appstream_catalog(files):
    directory=files/'share/app-info/xmls'
    paths=sorted(directory.glob('*.xml'))+sorted(directory.glob('*.xml.gz'))
    if not paths:raise RuntimeError('Composed Flatpak AppStream catalogue is missing')
    components=[]
    for path in paths:
        source=gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes()
        root=ET.fromstring(source)
        if root.tag!='components':raise RuntimeError('Expected composed AppStream catalogue, not raw MetaInfo')
        components.extend(root.findall('component'))
    owned=[component for component in components if component.findtext('id')==APP]
    if len(owned)!=1:raise RuntimeError('AppStream catalogue must contain exactly the Alpha application')
    component=owned[0]
    launchable=component.find('launchable[@type="desktop-id"]')
    if launchable is None or launchable.text!=APP+'.desktop':raise RuntimeError('AppStream launchable does not match the exported Alpha desktop file')
    if component.findtext('name')!=LABEL:raise RuntimeError('AppStream application name differs from desktop entry')
    if 'Development' not in [category.text for category in component.findall('categories/category')]:raise RuntimeError('AppStream development menu category is missing')
    if not component.findall('icon'):raise RuntimeError('AppStream application icon is missing')
    return {'catalogues':[str(path.relative_to(files)) for path in paths],
            'launchable':launchable.text,'category':'Development','component_id':APP}

def compose_appstream(files,composer,log):
    # Unlike flatpak-builder, the low-level build-export commands do not compose
    # MetaInfo automatically. Without this step the repository's appstream
    # branch is empty and app stores do not receive the launchable/icon/category.
    command=[str(composer.resolve(strict=True))] if composer else ['appstreamcli','compose']
    run([*command,'--no-net','--prefix=/',f'--origin={APP}',
         '--icon-policy=48x48=cached,48x48@2=cached,64x64=cached,64x64@2=cached,128x128=cached,128x128@2=cached',
         f'--result-root={files}',f'--data-dir={files}/share/app-info/xmls',
         f'--icons-dir={files}/share/app-info/icons/flatpak',f'--components={APP}',files],log)
    return check_appstream_catalog(files)

def run(command,log,*,env=None):
    process=subprocess.run([str(value) for value in command],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    with log.open('a') as stream:stream.write('$ '+' '.join(str(value) for value in command)+'\n'+process.stdout+'\n')
    if process.returncode:raise RuntimeError(f'Command failed ({process.returncode}): {command[0]}; see {log}')
    return process.stdout

def dependency_base(args,log):
    if args.base_checkout:return args.base_checkout.resolve(strict=True)
    cache=ROOT/'.cache/flatpak-dependencies';cache.mkdir(parents=True,exist_ok=True)
    checkout=cache/'checkout'
    if checkout.exists():return checkout
    bundle=cache/'VibeZ-3.0.8-Linux-x64.flatpak'
    if not bundle.exists():
        request=urllib.request.Request(BASE_URL,headers={'User-Agent':'VibeZ-release-builder'})
        with urllib.request.urlopen(request,timeout=90) as response:
            with bundle.open('wb') as stream:shutil.copyfileobj(response,stream)
    if digest(bundle)!=BASE_BUNDLE_SHA:raise RuntimeError('Published dependency bundle checksum mismatch')
    ostree=args.ostree or shutil.which('ostree')
    if not ostree:raise RuntimeError('Install the OSTree CLI or pass --ostree to extract the public dependency base')
    repo=cache/'repo'
    run(['flatpak','build-import-bundle',repo,bundle],log)
    run([ostree,f'--repo={repo}','checkout','--user-mode',BASE_COMMIT,checkout],log)
    return checkout

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--binary-sha256',required=True)
    parser.add_argument('--base-checkout',type=Path,help='Optional exact verified cache; otherwise fetch the public pinned dependency bundle')
    parser.add_argument('--ostree',type=Path,help='OSTree CLI for extracting the public dependency bundle')
    parser.add_argument('--legacy-indicators',action='store_true',help='Include the older optional indicator libraries; V4 Alpha has no tray and does not need them')
    parser.add_argument('--work',type=Path,default=ROOT/f'artifacts/flatpak-{VERSION}')
    parser.add_argument('--repo-dir',type=Path,default=ROOT/'.cache/alpha-flatpak-repository',help='Persistent signed OSTree repository; reuse it for subsequent Alpha versions')
    parser.add_argument('--repo-url',default='https://raw.githubusercontent.com/lecomputeur/vibez/v4-alpha-flatpak/',help='Public read-only update origin embedded in the bundle')
    parser.add_argument('--gpg-homedir',type=Path,help='Private signing home; never copied into publication files')
    parser.add_argument('--gpg-key',help='Public signing fingerprint')
    parser.add_argument('--gpg-public-key',type=Path,help='Binary public key to embed in the bundle and publish')
    parser.add_argument('--output',type=Path,default=ROOT/f'artifacts/VibeZ-{VERSION}-Linux-x64.flatpak')
    parser.add_argument('--release-date',default='2026-10-31')
    parser.add_argument('--appstream-compose',type=Path,help='Optional AppStream compose executable; default: appstreamcli compose')
    parser.add_argument('--build',action='store_true')
    args=parser.parse_args()
    release_date=date.fromisoformat(args.release_date).isoformat()
    import re
    if not re.fullmatch(r'4\.\d+\.\d+-(alpha|beta)\.\d+',VERSION):parser.error('This builder only publishes the separate V4 channel')
    expected_origin='https://raw.githubusercontent.com/lecomputeur/vibez/v4-alpha-flatpak/'
    if args.repo_url!=expected_origin:parser.error('Only the dedicated V4 Alpha update origin is accepted')
    if args.build:
        if not all([args.gpg_homedir,args.gpg_key,args.gpg_public_key]):parser.error('Signed Alpha publication requires --gpg-homedir, --gpg-key and --gpg-public-key')
        if not re.fullmatch(r'[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64}',args.gpg_key):parser.error('Use the full public signing fingerprint')
        args.gpg_homedir=args.gpg_homedir.resolve(strict=True);args.gpg_public_key=args.gpg_public_key.resolve(strict=True)
        if args.gpg_homedir.stat().st_mode&0o077:parser.error('Private signing directory must not be accessible to other users')
        if args.gpg_public_key.stat().st_size>65536:parser.error('Public signing key is unexpectedly large')
    binary=args.binary.resolve(strict=True)
    if binary.name!=BIN or digest(binary)!=args.binary_sha256:parser.error('Expected the exact hashed Alpha executable')
    binary_data=binary.read_bytes()
    if APP.encode() not in binary_data:parser.error('Independent Alpha application identity missing')
    for marker in [b'VIBEZ4_CODE_PROBE_DIR',b'VIBEZ4_STANDALONE_TEST_OUTPUT',b'VIBEZ4_LIVE_TEST_OUTPUT']:
        if marker in binary_data:parser.error('Diagnostic command paths must not be shipped')
    work=args.work.resolve();output=args.output.resolve()
    if work.exists() and any(work.iterdir()):parser.error('Work directory must be new and empty')
    if output.exists():parser.error('Refusing to replace an existing bundle')
    work.mkdir(parents=True,exist_ok=True);build=work/'build';files=build/'files';files.mkdir(parents=True)
    log=work/'build.log'
    base=dependency_base(args,log) if args.legacy_indicators else None
    if base is not None and tree_digest(base)!=BASE_TREE_SHA:parser.error('Dependency base differs from the verified published Flatpak tree')
    version=run([binary,'--version'],log).strip()
    if VERSION not in version or 'VibeZ V4 ' not in version:parser.error(f'Unexpected executable identity: {version}')

    # Dynamic indicator libraries are copied from a hashed published dependency
    # base, not from this host. Preserve their original source/commit manifest.
    libraries=files/'lib';libraries.mkdir()
    copied_libraries={}
    for path in sorted((base/'files/lib').glob('*.so*')) if base is not None else []:
        dest=libraries/path.name
        if path.is_symlink():dest.symlink_to(path.readlink())
        else:shutil.copy2(path,dest);copied_libraries[path.name]=digest(dest)
    assert len(copied_libraries)==(5 if base is not None else 0)
    binary_dir=files/'bin';binary_dir.mkdir();shutil.copy2(binary,binary_dir/BIN);(binary_dir/BIN).chmod(0o755)
    backend=files/'lib'/NAME/'backend';backend.mkdir(parents=True)
    copied_backend={}
    for name in BACKENDS:
        shutil.copy2(ROOT/'backend'/name,backend/name);copied_backend[name]=digest(backend/name)
    shutil.copytree(ROOT/'backend/vendor',backend/'vendor',ignore=shutil.ignore_patterns('__pycache__'))
    assert (backend/'vendor/cloudflared-linux-amd64').is_file()
    (backend/'vendor/cloudflared-linux-amd64').chmod(0o755)

    applications=files/'share/applications';applications.mkdir(parents=True)
    (applications/f'{APP}.desktop').write_text(desktop_entry())
    icons=files/'share/icons/hicolor/512x512/apps';icons.mkdir(parents=True)
    shutil.copy2(ROOT/'icon.png',icons/f'{APP}.png')
    for size,source in [('128x128','128x128.png'),('256x256','128x128@2x.png')]:
        icon_dir=files/'share/icons/hicolor'/size/'apps';icon_dir.mkdir(parents=True)
        shutil.copy2(ROOT/'desktop/src-tauri/icons'/source,icon_dir/f'{APP}.png')
    metadata_dir=files/'share/metainfo';metadata_dir.mkdir(parents=True)
    (metadata_dir/f'{APP}.metainfo.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<component type="desktop-application">'
        f'<id>{APP}</id><metadata_license>CC0-1.0</metadata_license><project_license>MIT</project_license>'
        f'<name>{LABEL}</name><summary>Mistral client with local project workspaces</summary>'
        '<description><p>An early VibeZ 4 Alpha that uses the familiar Mistral web interface. '
        'Link local folders to each project or conversation, read text, Office documents and images, and review changes before saving. '
        'This independent application does not replace VibeZ 3.</p></description>'
        f'<launchable type="desktop-id">{APP}.desktop</launchable>'
        '<url type="homepage">https://github.com/lecomputeur/vibez</url>'
        f'<releases><release version="{escape(VERSION)}" date="{release_date}"/></releases>'
        '<content_rating type="oars-1.1"/></component>\n')
    docs=files/'share/doc'/APP;docs.mkdir(parents=True)
    if base is not None:shutil.copy2(base/'files/manifest.json',docs/'original-dependency-source-manifest.json')
    if (ROOT/'LICENSE').is_file():shutil.copy2(ROOT/'LICENSE',docs/'LICENSE-VibeZ')
    if base is not None:shutil.copytree(ROOT/'third_party/flatpak-indicators',docs/'indicator-dependencies')

    metadata=configparser.ConfigParser(interpolation=None);metadata.optionxform=str
    metadata['Application']={'name':APP,'runtime':RUNTIME,'sdk':'org.gnome.Sdk/x86_64/51','command':BIN}
    metadata['Context']={'shared':'network;ipc;','sockets':'wayland;fallback-x11;pulseaudio;','devices':'dri;'}
    if base is not None:metadata['Session Bus Policy']={'org.kde.StatusNotifierWatcher':'talk'}
    metadata['Environment']={'GTK_USE_PORTAL':'1'}
    with (build/'metadata').open('w') as stream:metadata.write(stream,space_around_delimiters=False)
    provenance={'app_id':APP,'version':VERSION,'product_name':NAME,'command':BIN,'branch':BRANCH,
                'runtime':RUNTIME,'binary_sha256':digest(binary),'backend_sha256':copied_backend,
                'vendored_cloudflared_sha256':digest(backend/'vendor/cloudflared-linux-amd64'),
                'legacy_indicators_included':base is not None,'preserved_libraries_sha256':copied_libraries,
                'permissions':{'home':False,'host_filesystem':False,'selected_files_via_document_portal':True},
                'installed':False,'published':False,'source_script_sha256':digest(Path(__file__)),
                'update_origin':args.repo_url,'update_branch':BRANCH,
                'update_public_key_sha256':digest(args.gpg_public_key) if args.gpg_public_key else None,
                'update_signing_fingerprint':args.gpg_key}
    write_json(docs/'flatpak-build-provenance.json',provenance);write_json(work/'provenance.json',provenance)
    if args.build:
        run(['desktop-file-validate',applications/f'{APP}.desktop'],log)
        run(['appstreamcli','validate','--no-net',metadata_dir/f'{APP}.metainfo.xml'],log)
        provenance['appstream_catalogue']=compose_appstream(files,args.appstream_compose,log)
        write_json(docs/'flatpak-build-provenance.json',provenance)
        repo=args.repo_dir.resolve();repo.parent.mkdir(parents=True,exist_ok=True)
        if repo==args.gpg_homedir or args.gpg_homedir in repo.parents or repo in args.gpg_homedir.parents:parser.error('Keep the private signing key outside the update repository')
        key_info=run(['gpg','--batch','--homedir',args.gpg_homedir,'--with-colons','--show-keys',args.gpg_public_key],log)
        fingerprints=[line.split(':')[9] for line in key_info.splitlines() if line.startswith('fpr:')]
        if args.gpg_key.upper() not in fingerprints:parser.error('Public key does not match the signing fingerprint')
        signing=[f'--gpg-sign={args.gpg_key}',f'--gpg-homedir={args.gpg_homedir}']
        run(['flatpak','build-finish',f'--command={BIN}','--require-version=1.14.0',build],log)
        run(['flatpak','build-export','--disable-sandbox','--arch=x86_64',*signing,repo,build,BRANCH],log)
        run(['flatpak','build-update-repo',*signing,'--title=VibeZ V4 Beta','--default-branch=alpha','--generate-static-deltas',repo],log)
        output.parent.mkdir(parents=True,exist_ok=True)
        run(['flatpak','build-bundle',repo,output,APP,BRANCH,f'--repo-url={args.repo_url}',f'--gpg-keys={args.gpg_public_key}','--runtime-repo=https://flathub.org/repo/flathub.flatpakrepo'],log)
        # Publish compiled OSTree objects and public trust data only. Private
        # signing material is outside this tree and never traversed/copied.
        branches=run(['flatpak','repo','--branches',repo],log)
        for line in branches.splitlines():
            if line.startswith(('app/','runtime/')) and line.split()[0]!=f'app/{APP}/x86_64/{BRANCH}':
                parser.error('The update repository contains an unrelated application or branch')
        if any(path.is_symlink() for path in repo.rglob('*')):parser.error('Unexpected symlink in repository publication')
        publication=work/'publication';publication.mkdir()
        for name in ['config','summary','summary.sig','summary.idx','summary.idx.sig']:
            if (repo/name).is_file():shutil.copy2(repo/name,publication/name)
        for name in ['objects','refs','deltas','summaries','extensions']:
            if (repo/name).is_dir():shutil.copytree(repo/name,publication/name,symlinks=False)
        public=publication/'alpha-updates.gpg';shutil.copy2(args.gpg_public_key,public)
        import base64
        public64=base64.b64encode(public.read_bytes()).decode()
        (publication/'vibez4-alpha.flatpakrepo').write_text('[Flatpak Repo]\nTitle=VibeZ V4 Beta\n'+f'Url={args.repo_url}\nDefaultBranch=alpha\nGPGKey={public64}\n')
        (publication/'vibez4-alpha.flatpakref').write_text('[Flatpak Ref]\n'+f'Name={APP}\nBranch=alpha\nTitle=VibeZ V4 Beta\nSuggestRemoteName=vibez4-alpha-channel\nIsRuntime=false\nUrl={args.repo_url}\nGPGKey={public64}\nRuntimeRepo=https://flathub.org/repo/flathub.flatpakrepo\n')
        (publication/'.nojekyll').touch()
        if not (publication/'summary.sig').is_file():parser.error('Signed repository summary is missing')
        for path in publication.rglob('*'):
            if path.is_symlink() or 'private-keys-v1.d' in path.parts or path.name in ['secring.gpg','trustdb.gpg']:parser.error('Unexpected private or linked file in repository publication')
        provenance.update(bundle=str(output),bundle_sha256=digest(output),bundle_bytes=output.stat().st_size,
                          persistent_repository=str(repo),publication_directory=str(publication),repository_signed=True,summary_signed=True)
        write_json(work/'provenance.json',provenance)
    print(json.dumps(provenance,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
