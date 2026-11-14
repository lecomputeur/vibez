#!/usr/bin/env python3
"""Native Alpha builds. The calling workflow keeps source/build logs private."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parents[1]
DESKTOP = BASE / 'desktop'
VERSION = json.loads((DESKTOP / 'package.json').read_text())['version']
assert re.fullmatch(r'4\.[0-9]+\.[0-9]+-(alpha|beta)\.[1-9][0-9]*', VERSION)
TARGETS = {'windows-x64': 'x86_64-pc-windows-msvc', 'macos-x64': 'x86_64-apple-darwin', 'macos-arm64': 'aarch64-apple-darwin'}


def run(args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, **kwargs)


def wix_version():
    # MSI compares only three fields. Give every Alpha its own third field;
    # a fourth-field prerelease counter would be ignored during upgrades.
    # Alpha N is 4.0.N and Beta N is 4.0.(100+N): every Beta upgrades every Alpha.
    stage,number=re.fullmatch(r'4\.0\.0-(alpha|beta)\.([1-9]\d*)',VERSION).groups()
    number=int(number)+(100 if stage=='beta' else 0)
    if not 0 < number <= 65535 or (stage=='alpha' and number>99):
        raise ValueError('The MSI counter must fit: Alpha 1..99, Beta 1..65435')
    return f'4.0.{number}'


def prepare(target):
    triple = TARGETS[target]
    runtime = BASE / 'prepared/python-runtime'
    run([sys.executable, BASE / 'tools/prepare-alpha-runtime.py', '--target', triple, '--output', runtime])
    run([sys.executable, BASE / 'tools/prepare-alpha-cloudflared.py', '--target', target, '--output', BASE / 'backend/vendor'])
    config = json.loads((DESKTOP / 'src-tauri/tauri.conf.json').read_text())
    config['bundle']['createUpdaterArtifacts'] = False  # Packages are signed locally after download.
    config['bundle']['resources']['../../prepared/python-runtime/'] = 'python-runtime/'
    config['bundle']['resources']['../../backend/capfs.py'] = 'backend/capfs.py'
    config['bundle']['resources']['../../backend/document_reader.py'] = 'backend/document_reader.py'
    config['bundle']['resources']['../../backend/document_writer.py'] = 'backend/document_writer.py'
    # This upgrade identifier belongs solely to V4 Alpha, never to the V3 MSI.
    config['bundle']['windows']['wix'] = {'upgradeCode': '9C2E12C9-8EE2-4C1C-9D4E-02AD0BD79DA7', 'version': wix_version()}
    (DESKTOP / 'src-tauri/tauri.conf.json').write_text(json.dumps(config, indent=2) + '\n')
    if os.name == 'nt':
        node=Path(shutil.which('node')).resolve()
        npm=node.parent/'node_modules/npm/bin/npm-cli.js'
        assert npm.is_file(), 'The setup-node npm CLI is missing'
        run([node,npm,'ci','--ignore-scripts'],cwd=DESKTOP)
    else:
        run(['npm', 'ci', '--ignore-scripts'], cwd=DESKTOP)
    run(['node', 'scripts/prepare.cjs'], cwd=DESKTOP)
    run(['rustup', 'target', 'add', triple])


def native_smoke(executable, target, signed=False, resource_layout=None):
    reported = subprocess.check_output([str(executable), '--version'], text=True)
    assert VERSION in reported and 'VibeZ V4 ' in reported
    # Ephemeral CI runners have no user Mistral account. Only startup is tested.
    launches=[]
    # Each new signed Mac process constructs a new WKWebView, exercising the
    # initial-navigation URL race without any real account or prior user data.
    count=3 if signed and target.startswith('macos') else 1
    for attempt in range(count):
        process = subprocess.Popen([str(executable)], stdin=subprocess.DEVNULL)
        try:
            for _ in range(12):
                time.sleep(1)
                assert process.poll() is None, 'Native Alpha exited during startup'
            launches.append({'process_start':attempt+1,'startup_survived_seconds':12})
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
    out = BASE / 'artifacts/ci-proof'
    out.mkdir(parents=True, exist_ok=True)
    (out / (target + ('-signed' if signed else '') + '.json')).write_text(json.dumps({'version': VERSION, 'target': target,
        'native_version': reported.strip(), 'startup_survived_seconds': 12,
        'independent_process_starts':len(launches),'startup_launches':launches,
        'signed_app_tested': signed, 'resource_layout': resource_layout,
        'msi_product_version': wix_version() if target.startswith('windows') else None,
        'real_mistral_login_tested': False, 'existing_user_profile_used': False,
        'vibez309_installed_or_changed': False, 'msix_built': False}, indent=2) + '\n')


def build(target):
    triple = TARGETS[target]
    run(['node', '--test', *sorted(str(x) for x in (DESKTOP / 'standalone-tests').glob('*.test.cjs'))], cwd=DESKTOP)
    runtime = BASE / 'prepared/python-runtime'
    python = runtime / ('python.exe' if target.startswith('windows') else 'bin/python3')
    env = dict(os.environ)
    env['SSL_CERT_FILE'] = str(runtime / 'certificates/cacert.pem')
    run([python, '-I', '-B', '-X', 'utf8', '-m', 'unittest', 'discover', '-s', BASE / 'tests/standalone', '-p', 'test_capfs.py', '-v'], cwd=BASE, env=env)
    run([python, '-I', '-B', '-X', 'utf8', '-m', 'unittest', 'discover', '-s', BASE / 'tests/standalone', '-p', 'test_alpha9_files.py', '-v'], cwd=BASE, env=env)
    run([python, '-I', '-B', '-X', 'utf8', BASE / 'tools/ci-alpha-backend-check.py', '--target', target, '--output', BASE / 'artifacts/ci-proof' / ('backend-' + target + '.json')], cwd=BASE, env=env)
    run(['cargo', 'test', '--release', '--locked', '--manifest-path', 'src-tauri/Cargo.toml', '--target', triple, '--bin', 'vibez4-alpha'], cwd=DESKTOP)
    bundles = 'nsis,msi' if target.startswith('windows') else 'app'
    run(['node', 'node_modules/@tauri-apps/cli/tauri.js', 'build', '--target', triple, '--bundles', bundles, '--', '--locked'], cwd=DESKTOP)
    root = DESKTOP / 'src-tauri/target' / triple / 'release'
    executable = root / ('vibez4-alpha.exe' if target.startswith('windows') else 'vibez4-alpha')
    if target.startswith('windows'):
        # The raw Cargo output has no resource directory. Stage the exact
        # installer resource mapping beside a copy of the executable. This
        # tests native app.path().resource_dir() without installing on a user PC.
        stage=root / 'ci-installer-layout';stage.mkdir()
        shutil.copy2(executable,stage/executable.name)
        config=json.loads((DESKTOP/'src-tauri/tauri.conf.json').read_text())
        for source,relative in config['bundle']['resources'].items():
            source=(DESKTOP/'src-tauri'/source).resolve();destination=stage/relative
            if source.is_dir():shutil.copytree(source,destination)
            else:destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
        executable=stage/executable.name
        for expected in ['backend/standalone_engine.py','backend/capfs.py','python-runtime/python.exe','python-runtime/certificates/cacert.pem']:
            assert (stage/expected).is_file(), 'Missing installer-layout resource: '+expected
    else:
        apps = list((root / 'bundle/macos').glob('*.app'))
        assert len(apps) == 1
        executable = apps[0] / 'Contents/MacOS/vibez4-alpha'
        info = plistlib.loads((apps[0] / 'Contents/Info.plist').read_bytes())
        assert info['CFBundleIdentifier'] == 'nl.lecomputeur.vibez4.alpha'
    native_smoke(executable, target, resource_layout='installer-equivalent staging' if target.startswith('windows') else 'bundled app Resources')
    if target.startswith('windows'):
        import urllib.request
        spec=json.loads((BASE/'packaging/stable-test-sources.json').read_text())['windows_msi']
        stable=BASE/'prepared/stable-3.0.9.msi'
        with urllib.request.urlopen(spec['url'],timeout=90) as response:stable.write_bytes(response.read())
        assert hashlib.sha256(stable.read_bytes()).hexdigest()==spec['sha256']
        msi=list((root/'bundle/msi').glob('*.msi'));nsis=list((root/'bundle/nsis').glob('*.exe'))
        assert len(msi)==len(nsis)==1
        run([python,'-I','-B','-X','utf8',BASE/'tools/ci-alpha-windows-install-check.py','--stable-msi',stable,'--alpha-msi',msi[0],'--alpha-nsis',nsis[0],'--version',VERSION,'--output',BASE/'artifacts/ci-proof/windows-install.json'],cwd=BASE,env=env)



def sign_mac(target):
    triple = TARGETS[target]
    apps = list((DESKTOP / 'src-tauri/target' / triple / 'release/bundle/macos').glob('*.app'))
    assert len(apps) == 1
    app = apps[0]
    required = ['MAC_CERTIFICATE_P12_BASE64', 'MAC_CERTIFICATE_PASSWORD', 'APPLE_API_KEY_P8_BASE64', 'APPLE_API_KEY_ID', 'APPLE_API_ISSUER', 'APPLE_TEAM_ID']
    if not all(os.environ.get(name) for name in required):
        raise RuntimeError('Existing Apple signing configuration is incomplete')
    with tempfile.TemporaryDirectory(prefix='vibez-alpha-sign-') as temp:
        root = Path(temp).resolve(strict=True)
        certificate, auth, keychain = root / 'identity.p12', root / 'AuthKey.p8', root / 'alpha.keychain-db'
        certificate.write_bytes(base64.b64decode(os.environ['MAC_CERTIFICATE_P12_BASE64']))
        auth.write_bytes(base64.b64decode(os.environ['APPLE_API_KEY_P8_BASE64']))
        certificate.chmod(0o600); auth.chmod(0o600)
        password = base64.urlsafe_b64encode(os.urandom(24)).decode()
        original_keychains = shlex.split(subprocess.check_output(['security', 'list-keychains', '-d', 'user'], text=True))
        run(['security', 'create-keychain', '-p', password, keychain])
        try:
            run(['security', 'unlock-keychain', '-p', password, keychain])
            run(['security', 'set-keychain-settings', '-lut', '7200', keychain])
            # Security.framework also consults the search list when codesign
            # resolves the imported private key, even with --keychain supplied.
            run(['security', 'list-keychains', '-d', 'user', '-s', keychain, *original_keychains])
            run(['security', 'import', certificate, '-k', keychain, '-P', os.environ['MAC_CERTIFICATE_PASSWORD'], '-T', '/usr/bin/codesign'])
            # Match the private key directly; its optional can-sign attribute
            # is not set consistently on PKCS12 imports. Only this disposable
            # keychain is changed; no -A or login/system keychain permissions.
            run(['security', 'set-key-partition-list', '-S', 'apple-tool:,apple:,codesign:', '-t', 'private', '-k', password, keychain], stdout=subprocess.DEVNULL)
            output = subprocess.check_output(['security', 'find-identity', '-v', '-p', 'codesigning', keychain], text=True)
            identities = re.findall(r'"(Developer ID Application:[^"]+)"', output)
            assert len(identities) == 1
            identity = identities[0]
            assert identity.endswith('(' + os.environ['APPLE_TEAM_ID'] + ')'), 'Apple signing identity belongs to a different team'
            vendor = app / 'Contents/Resources/backend/vendor'
            helper_manifest_path = vendor / 'source.json'
            helper_manifest = json.loads(helper_manifest_path.read_text())
            helper_record = helper_manifest['platforms'][target]
            helper_name = 'cloudflared-darwin-' + ('amd64' if target == 'macos-x64' else 'arm64')
            assert helper_record['file'] == helper_name
            helper = vendor / helper_name
            upstream_helper_sha256 = helper_record['sha256']
            assert helper.is_file() and not helper.is_symlink()
            assert hashlib.sha256(helper.read_bytes()).hexdigest() == upstream_helper_sha256, 'Unsigned tunnel helper differs from its pinned supplier input'
            # Sign every nested Mach-O first, including the relocatable runtime.
            for path in sorted(app.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                if not path.is_file() or path.is_symlink():
                    continue
                magic = path.open('rb').read(4)
                if magic in [b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xfe\xed\xfa\xcf']:
                    run(['codesign', '--force', '--options', 'runtime', '--timestamp', '--keychain', keychain, '--sign', identity, path])
            # Signing changes Mach-O bytes. Pin the signed helper inside the
            # outer signed app; keep its verified supplier hash as provenance.
            # Only this bundled manifest changes, never the source/vendor copy.
            helper_record['upstream_sha256'] = upstream_helper_sha256
            helper_record['sha256'] = hashlib.sha256(helper.read_bytes()).hexdigest()
            helper_record['bundle_signature_team_id'] = os.environ['APPLE_TEAM_ID']
            helper_manifest_path.write_text(json.dumps(helper_manifest, indent=2) + '\n')
            run(['codesign', '--force', '--options', 'runtime', '--timestamp', '--keychain', keychain, '--sign', identity,
                 '--entitlements', DESKTOP / 'src-tauri/macos/Entitlements.plist', app])
            run(['codesign', '--verify', '--deep', '--strict', app])
            details = subprocess.check_output(['codesign', '-dv', '--verbose=4', app], stderr=subprocess.STDOUT, text=True)
            assert 'TeamIdentifier=' + os.environ['APPLE_TEAM_ID'] in details.splitlines(), 'Signed app team verification failed'
            submit = root / 'notarize.zip'
            run(['ditto', '-c', '-k', '--keepParent', app, submit])
            result = subprocess.check_output(['xcrun', 'notarytool', 'submit', submit, '--key', auth, '--key-id', os.environ['APPLE_API_KEY_ID'],
                '--issuer', os.environ['APPLE_API_ISSUER'], '--wait', '--timeout', '45m', '--output-format', 'json'], text=True)
            assert json.loads(result)['status'] == 'Accepted', 'Apple did not accept the Alpha app'
            apple_ticket_action(app, 'staple')
            run(['spctl', '--assess', '--type', 'execute', '--verbose=4', app])
        finally:
            subprocess.run(['security', 'list-keychains', '-d', 'user', '-s', *original_keychains], check=False)
            subprocess.run(['security', 'delete-keychain', keychain], check=False)


def smoke_signed(target):
    if target.startswith('windows'):
        raise ValueError('Signed-app smoke is only for macOS')
    # This subcommand belongs to a separate workflow step with no Apple secrets.
    protected=['MAC_CERTIFICATE_P12_BASE64','MAC_CERTIFICATE_PASSWORD','APPLE_API_KEY_P8_BASE64',
               'APPLE_API_KEY_ID','APPLE_API_ISSUER','APPLE_TEAM_ID']
    if any(os.environ.get(name) for name in protected):
        raise RuntimeError('Do not launch the app inside the Apple signing environment')
    apps=list((DESKTOP/'src-tauri/target'/TARGETS[target]/'release/bundle/macos').glob('*.app'))
    assert len(apps)==1
    app=apps[0];resources=app/'Contents/Resources';runtime=resources/'python-runtime'
    for relative in ['bin/python3','certificates/cacert.pem']:
        assert (runtime/relative).is_file(), 'Missing signed-app Python resource: '+relative
    # Loading the signed runtime and its extensions must work with hardened
    # runtime/library validation enabled; no broad exception is added.
    environment=dict(os.environ);environment['SSL_CERT_FILE']=str(runtime/'certificates/cacert.pem')
    run([runtime/'bin/python3','-I','-B','-c','import ssl,sqlite3,ctypes; ssl.create_default_context(); sqlite3.connect(":memory:").close()'],env=environment)
    # Exercise the actual signed resources, including the production tunnel
    # pin check and helper executable, outside the Apple-credential step.
    run([runtime/'bin/python3','-I','-B','-X','utf8',BASE/'tools/ci-alpha-backend-check.py',
         '--target',target,'--backend-dir',resources/'backend',
         '--output',BASE/'artifacts/ci-proof'/('signed-backend-'+target+'.json')],env=environment)
    native_smoke(app/'Contents/MacOS/vibez4-alpha',target,signed=True,resource_layout='signed bundled app Resources')
    run(['codesign', '--verify', '--deep', '--strict', app])


def verify_mac_delivered_tunnel(app):
    """Use the delivered Python and production validator, including on a DMG."""
    resources=app/'Contents/Resources'
    program='''import importlib.util,json,pathlib,subprocess,sys
backend=pathlib.Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('_delivered_capfs',backend/'capfs.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
helper=module.tunnel_helper(backend/'vendor','')
result=subprocess.run([str(helper),'--version'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=module.runtime_env(),timeout=20)
assert result.returncode==0 and b'cloudflared version' in result.stdout.lower()
print(json.dumps({'production_tunnel_helper_resolution':True,'validated_helper_version_started':True}))
'''
    proof=json.loads(subprocess.check_output([resources/'python-runtime/bin/python3','-I','-B','-X','utf8',
        '-c',program,resources/'backend'],text=True))
    assert proof=={'production_tunnel_helper_resolution':True,'validated_helper_version_started':True}


def apple_ticket_action(app, action):
    assert action in {'staple','validate'}
    command=['xcrun','stapler',action,str(app)]
    for attempt in range(4):
        result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        print(result.stdout,flush=True)
        if result.returncode==0:return
        # Only retry the exact observed Apple CloudKit connection-loss error.
        # Missing/invalid tickets, content mismatches and signature failures
        # remain fatal; no verification is skipped after retries are exhausted.
        transient=(result.returncode==68 and 'NSURLErrorDomain Code=-1005' in result.stdout
                   and 'api.apple-cloudkit.com' in result.stdout)
        if not transient or attempt==3:
            raise subprocess.CalledProcessError(result.returncode,command,output=result.stdout)
        time.sleep(2**(attempt+1))


def validate_apple_ticket(app):
    apple_ticket_action(app, 'validate')


def verify_mac_archives(output, target, original):
    """Verify the delivered copies, including their complete signed resources."""
    if sys.platform != 'darwin':
        raise RuntimeError('Mac archive verification requires native macOS')
    arch=target.split('-')[1]
    expected_arch='x86_64' if arch=='x64' else 'arm64'
    actual_arch=subprocess.check_output(['lipo','-archs',original/'Contents/MacOS/vibez4-alpha'],text=True).split()
    assert actual_arch==[expected_arch], 'The packaged app has the wrong native architecture'
    def content(root):
        entries={}
        for path in root.rglob('*'):
            relative=str(path.relative_to(root))
            if path.is_symlink():entries[relative]=['symlink',os.readlink(path)]
            elif path.is_file():entries[relative]=['file',hashlib.sha256(path.read_bytes()).hexdigest()]
        return entries
    expected=content(original)
    results=[]
    def verify(app, suffix):
        assert app.is_dir() and not app.is_symlink(), 'The archive has no independent Alpha app'
        assert content(app)==expected, 'Archive contents differ from the signed app: '+suffix
        assert os.access(app/'Contents/MacOS/vibez4-alpha',os.X_OK)
        vendor=app/'Contents/Resources/backend/vendor'
        record=json.loads((vendor/'source.json').read_text())['platforms'][target]
        helper_name='cloudflared-darwin-'+('amd64' if target=='macos-x64' else 'arm64')
        assert record['file']==helper_name
        assert hashlib.sha256((vendor/helper_name).read_bytes()).hexdigest()==record['sha256'], 'Delivered tunnel helper does not match its signed manifest'
        run(['codesign','--verify','--deep','--strict',app])
        validate_apple_ticket(app)
        run(['spctl','--assess','--type','execute','--verbose=4',app])
        verify_mac_delivered_tunnel(app)
        run(['codesign','--verify','--deep','--strict',app])
        results.append({'format':suffix,'complete_file_and_symlink_contents_preserved':True,
                        'codesign_verified':True,'stapled_ticket_validated':True,'gatekeeper_accepted':True,
                        'signed_tunnel_helper_hash_verified':True,
                        'production_tunnel_helper_resolution':True,'validated_helper_version_started':True})
    prefix=f'VibeZ-{VERSION}-macOS-{arch}'
    with tempfile.TemporaryDirectory(prefix='vibez-alpha-delivery-check-') as temporary:
        root=Path(temporary)
        for suffix in ['zip','app.tar.gz']:
            dest=root/suffix;dest.mkdir()
            if suffix=='zip':run(['ditto','-x','-k',output/(prefix+'.zip'),dest])
            else:
                with tarfile.open(output/(prefix+'.app.tar.gz')) as archive:archive.extractall(dest,filter='data')
            verify(dest/original.name,suffix)
        mount=root/'mounted-dmg';mount.mkdir()
        attached=False
        try:
            run(['hdiutil','attach','-readonly','-nobrowse','-mountpoint',mount,output/(prefix+'.dmg')])
            attached=True
            verify(mount/original.name,'dmg')
        finally:
            if attached:subprocess.run(['hdiutil','detach',mount],check=True)
    proof={'passed':True,'version':VERSION,'target':target,'native_architecture':expected_arch,
           'original_signed_app_files_checked':len(expected),'delivered_formats':results,
           'existing_user_files_used':False,'real_mistral_login_tested':False}
    path=BASE/'artifacts/ci-proof'/('archives-'+target+'.json');path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(proof,indent=2)+'\n')


def existing_input(target):
    if not target.startswith('macos'):
        raise ValueError('Existing-package revalidation is only for macOS')
    request=json.loads((BASE.parent/'alpha-build-request.json').read_text())
    spec=request['verify_existing']
    assert request['version']==VERSION and spec['target']==target
    assert isinstance(spec['run'],int) and spec['run']>0 and isinstance(spec['artifact_id'],int) and spec['artifact_id']>0
    assert re.fullmatch('[0-9a-f]{64}',spec['artifact_sha256'])
    prefix=f'VibeZ-{VERSION}-macOS-{target.split("-")[1]}'
    assert set(spec['packages'])=={prefix+'.zip',prefix+'.app.tar.gz',prefix+'.dmg'}
    assert all(re.fullmatch('[0-9a-f]{64}',value) for value in spec['packages'].values())
    return spec


def download_existing(target):
    # GH_TOKEN is scoped to this download step, never to app execution.
    spec=existing_input(target)
    repo='repos/lecomputeur/vibez/actions/artifacts/'+str(spec['artifact_id'])
    metadata=json.loads(subprocess.check_output(['gh','api',repo],text=True))
    assert metadata['id']==spec['artifact_id'] and metadata['name']=='alpha-'+target+'-1'
    assert metadata['workflow_run']['id']==spec['run'] and not metadata['expired']
    assert metadata['digest']=='sha256:'+spec['artifact_sha256']
    directory=BASE/'prepared/revalidation';directory.mkdir(parents=True,exist_ok=False)
    archive=directory/'download.zip'
    with archive.open('wb') as output:
        run(['gh','api',repo+'/zip'],stdout=output)
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==spec['artifact_sha256']
    found=set()
    with zipfile.ZipFile(archive) as stream:
        for member in stream.infolist():
            normalized=member.filename.replace('\\','/')
            name=normalized.rsplit('/',1)[-1]
            if name not in spec['packages']:continue
            assert '/artifacts/ci-packages/' in '/'+normalized
            assert not normalized.startswith('/') and '..' not in normalized.split('/')
            assert name not in found and member.file_size<200*1024*1024
            data=stream.read(member)
            assert hashlib.sha256(data).hexdigest()==spec['packages'][name]
            (directory/name).write_bytes(data);found.add(name)
    assert found==set(spec['packages'])
    archive.unlink()


def revalidate_existing(target):
    protected=['GH_TOKEN','GITHUB_TOKEN','MAC_CERTIFICATE_P12_BASE64','MAC_CERTIFICATE_PASSWORD',
               'APPLE_API_KEY_P8_BASE64','APPLE_API_KEY_ID','APPLE_API_ISSUER','APPLE_TEAM_ID']
    assert not any(os.environ.get(name) for name in protected), 'Package execution must not inherit download/signing credentials'
    spec=existing_input(target);directory=BASE/'prepared/revalidation'
    output=BASE/'artifacts/ci-packages';output.mkdir(parents=True,exist_ok=False)
    for name,expected in spec['packages'].items():
        path=directory/name
        assert path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==expected
        shutil.copy2(path,output/name)
    app_root=DESKTOP/'src-tauri/target'/TARGETS[target]/'release/bundle/macos';app_root.mkdir(parents=True,exist_ok=False)
    with tarfile.open(output/f'VibeZ-{VERSION}-macOS-{target.split("-")[1]}.app.tar.gz') as archive:
        assert all(m.name=='VibeZ V4 Alpha.app' or m.name.startswith('VibeZ V4 Alpha.app/') for m in archive)
        archive.extractall(app_root,filter='data')
    app=app_root/'VibeZ V4 Alpha.app'
    verify_mac_archives(output,target,app)
    smoke_signed(target)
    # No package is rebuilt, re-signed, re-notarized or recompressed here.
    for name,expected in spec['packages'].items():
        assert hashlib.sha256((output/name).read_bytes()).hexdigest()==expected
    (output/'SHA256SUMS').write_text(''.join(value+'  '+name+'\n' for name,value in sorted(spec['packages'].items())))
    proof={'passed':True,'version':VERSION,'target':target,'producer_run':spec['run'],
           'producer_artifact_id':spec['artifact_id'],'producer_artifact_sha256':spec['artifact_sha256'],
           'verification_run':os.environ.get('GITHUB_RUN_ID'),'exact_original_packages_preserved':True,
           'no_rebuild_resign_or_recompression':True,'packages':spec['packages'],
           'apple_credentials_used':False,'real_mistral_account_used':False,'existing_user_files_used':False}
    path=BASE/'artifacts/ci-proof'/('revalidated-'+target+'.json');path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(proof,indent=2)+'\n')


def update_validation_input(target):
    """Public signatures and exact immutable input digests, never signing keys."""
    request=json.loads((BASE.parent/'alpha-build-request.json').read_text())
    source=request['verify_update']
    if 'targets' in source:
        assert source['version']==VERSION and target in source['targets']
        spec={**source,**source['targets'][target],'target':target}
    else:
        spec=source
    assert request['version']==VERSION and spec['target']==target
    previous=spec['previous_version']
    key=lambda v:(lambda m:m and (int(m[1]),int(m[2]),('alpha','beta').index(m[3]),int(m[4])))(re.fullmatch(r'4\.(\d+)\.(\d+)-(alpha|beta)\.([1-9]\d*)',v))
    assert key(previous) and key(VERSION) and key(VERSION)>key(previous)
    assert spec['feed']['version']==VERSION and isinstance(spec['feed']['platforms'],dict)
    roles={'from_msi','from_nsis','to_msi','to_nsis','stable_msi'} if target.startswith('windows') else {'from_app','to_app'}
    assert set(spec['files'])==roles
    for role,record in spec['files'].items():
        name=record['name'];assert name==Path(name).name and not any(c in name for c in '\\/:\r\n')
        expected='3.0.9' if role=='stable_msi' else previous if role.startswith('from_') else VERSION
        assert name.startswith('VibeZ-'+expected+'-')
        assert re.fullmatch('[0-9a-f]{64}',record['sha256'])
        assert type(record['size']) is int and 0<record['size']<=512*1024*1024
        assert sum(key in record for key in ('asset_id','ci_artifact','url'))==1
        if 'ci_artifact' in record:
            artifact=record['ci_artifact']
            assert role.startswith('to_') and isinstance(artifact,dict) and set(artifact)=={'id','run','sha256'}
            assert all(type(artifact[key]) is int and artifact[key]>0 for key in ('id','run'))
            assert re.fullmatch('[0-9a-f]{64}',artifact['sha256'])
        elif 'asset_id' in record:
            assert type(record['asset_id']) is int and record['asset_id']>0
            assert 'url' not in record
        else:
            parsed=urlsplit(record['url'])
            assert parsed.scheme=='https' and parsed.netloc=='github.com' and not parsed.query and not parsed.fragment
            assert parsed.path=='/lecomputeur/vibez/releases/download/v'+expected+'/'+name
    return spec


def download_updates(target):
    # A separate credential-bearing workflow step. The app is never run here.
    spec=update_validation_input(target)
    directory=BASE/'prepared/update-validation';directory.mkdir(parents=True,exist_ok=False)
    def download(url,path):
        import urllib.request
        request=urllib.request.Request(url,headers={'User-Agent':'VibeZ-Alpha-update-validation'})
        with urllib.request.urlopen(request,timeout=120) as response,path.open('wb') as output:
            shutil.copyfileobj(response,output)
    ci_archives={}
    for record in spec['files'].values():
        path=directory/record['name']
        if 'ci_artifact' in record:
            producer=record['ci_artifact'];identity=producer['id']
            if identity not in ci_archives:
                endpoint='repos/lecomputeur/vibez/actions/artifacts/'+str(identity)
                metadata=json.loads(subprocess.check_output(['gh','api',endpoint],text=True))
                assert metadata['id']==identity and metadata['workflow_run']['id']==producer['run'] and not metadata['expired']
                assert re.fullmatch('alpha-'+re.escape(target)+'-[1-9][0-9]*',metadata['name'])
                assert metadata['digest']=='sha256:'+producer['sha256'] and 0<metadata['size_in_bytes']<2*1024**3
                archive=directory/('producer-'+str(identity)+'.zip')
                with archive.open('wb') as output:run(['gh','api',endpoint+'/zip'],stdout=output)
                assert archive.stat().st_size==metadata['size_in_bytes']
                assert hashlib.sha256(archive.read_bytes()).hexdigest()==producer['sha256']
                ci_archives[identity]=(archive,producer)
            archive,previous=ci_archives[identity];assert previous==producer
            with zipfile.ZipFile(archive) as stream:
                candidates=[]
                for member in stream.infolist():
                    normalized=member.filename.replace('\\','/')
                    if normalized.rsplit('/',1)[-1]!=record['name']:continue
                    assert '/artifacts/ci-packages/' in '/'+normalized
                    assert not normalized.startswith('/') and '..' not in normalized.split('/') and ':' not in normalized.split('/')[0]
                    assert not member.is_dir() and member.file_size==record['size']
                    assert (member.external_attr>>16)&0o170000!=0o120000
                    candidates.append(member)
                assert len(candidates)==1,'The verified CI archive lacks the exact final package'
                with stream.open(candidates[0]) as source,path.open('xb') as output:shutil.copyfileobj(source,output)
        elif 'asset_id' in record:
            endpoint='repos/lecomputeur/vibez/releases/assets/'+str(record['asset_id'])
            metadata=json.loads(subprocess.check_output(['gh','api',endpoint],text=True))
            assert metadata['name']==record['name'] and metadata['size']==record['size']
            if metadata.get('digest'):assert metadata['digest']=='sha256:'+record['sha256']
            with path.open('wb') as output:run(['gh','api',endpoint,'-H','Accept: application/octet-stream'],stdout=output)
        else:download(record['url'],path)
        assert path.is_file() and not path.is_symlink() and path.stat().st_size==record['size']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
    (directory/'alpha.json').write_text(json.dumps(spec['feed'],indent=2)+'\n')
    proof={'target':target,'previous_version':spec['previous_version'],'next_version':VERSION,
           'exact_input_digests_verified':True,'files':{r['name']:r['sha256'] for r in spec['files'].values()},
           'app_executed_in_credential_step':False}
    (directory/'download-proof.json').write_text(json.dumps(proof,indent=2)+'\n')


def verify_updates(target):
    # Deliberately separate from download/signing steps; never pass tokens to apps.
    protected=['GH_TOKEN','GITHUB_TOKEN','MAC_CERTIFICATE_P12_BASE64','MAC_CERTIFICATE_PASSWORD',
               'APPLE_API_KEY_P8_BASE64','APPLE_API_KEY_ID','APPLE_API_ISSUER','APPLE_TEAM_ID',
               'TAURI_SIGNING_PRIVATE_KEY','TAURI_SIGNING_PRIVATE_KEY_PATH','TAURI_SIGNING_PRIVATE_KEY_PASSWORD']
    assert not any(os.environ.get(name) for name in protected), 'Update test must not inherit download/signing credentials'
    spec=update_validation_input(target);directory=BASE/'prepared/update-validation'
    for record in spec['files'].values():
        path=directory/record['name']
        assert path.is_file() and not path.is_symlink() and path.stat().st_size==record['size']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
    files={role:directory/record['name'] for role,record in spec['files'].items()}
    proof=BASE/'artifacts/ci-proof';proof.mkdir(parents=True,exist_ok=True)
    if target.startswith('windows'):
        arguments=[sys.executable,BASE/'tools/ci-alpha-windows-update-check.py','--from-version',spec['previous_version'],
                   '--feed',directory/'alpha.json','--output',proof/'real-update-windows-x64.json']
        for role,path in files.items():arguments.extend(['--'+role.replace('_','-'),path])
    else:
        arguments=[sys.executable,BASE/'tools/test-alpha-real-native-update.py','--target',target,
                   '--from-version',spec['previous_version'],'--from-package',files['from_app'],
                   '--to-package',files['to_app'],'--feed',directory/'alpha.json',
                   '--work',proof/('real-update-'+target)]
    run(arguments)


# Microsoft Store identity reserved in Partner Center for "VibeZ Desktop V4"
# (13 Nov 2026), next to the separate VibeZ Desktop 3.0.9 product.
STORE_IDENTITY = 'LeComputeur.VibezDesktopV4'
STORE_PUBLISHER = 'CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95'
STORE_NAME = 'VibeZ Desktop V4'
STORE_DESCRIPTION = 'Mistral desktop client with local project folders.'
STORE_LOGOS = ['StoreLogo.png', 'Square44x44Logo.png', 'Square150x150Logo.png']


def store_manifest(version):
    return f'''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
 xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
 xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
 IgnorableNamespaces="uap rescap">
 <Identity Name="{STORE_IDENTITY}" Publisher="{STORE_PUBLISHER}" Version="{version}" ProcessorArchitecture="x64" />
 <Properties>
  <DisplayName>{STORE_NAME}</DisplayName>
  <PublisherDisplayName>Le Computeur</PublisherDisplayName>
  <Description>{STORE_DESCRIPTION}</Description>
  <Logo>Assets\\StoreLogo.png</Logo>
 </Properties>
 <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" /></Dependencies>
 <Resources><Resource Language="en-us" /></Resources>
 <Applications>
  <Application Id="VibeZDesktopV4" Executable="vibez4-alpha.exe" EntryPoint="Windows.FullTrustApplication">
   <uap:VisualElements DisplayName="{STORE_NAME}" Description="{STORE_DESCRIPTION}" BackgroundColor="transparent"
    Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png">
    <uap:DefaultTile ShortName="VibeZ V4" />
   </uap:VisualElements>
  </Application>
 </Applications>
 <Capabilities><Capability Name="internetClient" /><rescap:Capability Name="runFullTrust" /></Capabilities>
</Package>
'''


def build_store_package(release_root):
    """The Beta's MSIX for Partner Center: the installer layout of the tested
    executable, the Store identity, and no self-updater (the app sees its
    package identity and leaves updates to the Store). Unsigned: the Store
    signs it on submission. Never a GitHub release asset."""
    output = BASE / 'artifacts/ci-store'; output.mkdir(parents=True, exist_ok=True)
    msix_version = wix_version() + '.0'
    stage = release_root / 'ci-store-layout'
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(release_root / 'ci-installer-layout', stage)
    assets = stage / 'Assets'; assets.mkdir()
    for name in STORE_LOGOS:
        shutil.copy2(DESKTOP / 'src-tauri/icons' / name, assets / name)
    (stage / 'AppxManifest.xml').write_text(store_manifest(msix_version), encoding='utf-8')
    kits = Path(os.environ.get('ProgramFiles(x86)', r'C:\\Program Files (x86)')) / 'Windows Kits/10/bin'
    tools = sorted(kits.glob('*/x64/makeappx.exe'))
    assert tools, 'makeappx.exe not found'
    package = output / f'VibeZ-{VERSION}-Windows-x64-Store.msix'
    run([tools[-1], 'pack', '/d', stage, '/p', package, '/o'])
    verify = release_root / 'ci-store-verify'
    shutil.rmtree(verify, ignore_errors=True)
    run([tools[-1], 'unpack', '/p', package, '/d', verify, '/o'])
    import xml.etree.ElementTree as ET
    ns = {'m': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10', 'uap': 'http://schemas.microsoft.com/appx/manifest/uap/windows10'}
    packed = ET.parse(verify / 'AppxManifest.xml').getroot()
    identity = packed.find('m:Identity', ns)
    assert identity.get('Name') == STORE_IDENTITY and identity.get('Publisher') == STORE_PUBLISHER and identity.get('Version') == msix_version
    assert packed.findtext('m:Properties/m:DisplayName', namespaces=ns) == STORE_NAME
    assert packed.find('.//uap:VisualElements', ns).get('DisplayName') == STORE_NAME
    for expected in ['vibez4-alpha.exe', 'backend/standalone_engine.py', 'python-runtime/python.exe', *('Assets/' + n for n in STORE_LOGOS)]:
        assert (verify / expected).is_file(), 'MSIX lacks ' + expected
    (output / 'SHA256SUMS').write_text(hashlib.sha256(package.read_bytes()).hexdigest() + '  ' + package.name + '\n')
    (BASE / 'artifacts/ci-proof/windows-store.json').write_text(json.dumps({'passed': True, 'identity': STORE_IDENTITY, 'display_name': STORE_NAME,
        'msix_version': msix_version, 'version': VERSION, 'signed': False, 'size': package.stat().st_size,
        'sha256': hashlib.sha256(package.read_bytes()).hexdigest()}, indent=2) + '\n')


def collect(target):
    output = BASE / 'artifacts/ci-packages'
    output.mkdir(parents=True, exist_ok=True)
    triple = TARGETS[target]
    root = DESKTOP / 'src-tauri/target' / triple / 'release/bundle'
    if target.startswith('windows'):
        for pattern, suffix in [('nsis/*.exe', '-Setup.exe'), ('msi/*.msi', '.msi')]:
            files = list(root.glob(pattern)); assert len(files) == 1
            shutil.copy2(files[0], output / f'VibeZ-{VERSION}-Windows-x64{suffix}')
        if '-beta.' in VERSION:
            build_store_package(DESKTOP / 'src-tauri/target' / triple / 'release')
    else:
        arch = target.split('-')[1]
        apps = list((root / 'macos').glob('*.app')); assert len(apps) == 1
        app = apps[0]
        run(['ditto', '-c', '-k', '--keepParent', app, output / f'VibeZ-{VERSION}-macOS-{arch}.zip'])
        with tarfile.open(output / f'VibeZ-{VERSION}-macOS-{arch}.app.tar.gz', 'w:gz') as archive:
            archive.add(app, arcname=app.name)
        with tempfile.TemporaryDirectory(prefix='vibez-alpha-dmg-') as temp:
            stage = Path(temp)
            shutil.copytree(app, stage / app.name, symlinks=True)
            (stage / 'Applications').symlink_to('/Applications', target_is_directory=True)
            run(['hdiutil', 'create', '-volname', 'VibeZ V4 Beta' if '-beta.' in VERSION else 'VibeZ V4 Alpha', '-srcfolder', stage, '-ov', '-format', 'UDZO', output / f'VibeZ-{VERSION}-macOS-{arch}.dmg'])
        verify_mac_archives(output,target,app)
    assert not list(output.glob('*.msix'))
    (output / 'SHA256SUMS').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest() + '  ' + f.name + '\n' for f in sorted(output.iterdir()) if f.is_file() and f.name != 'SHA256SUMS'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'build', 'sign-mac', 'smoke-signed', 'collect', 'download-existing', 'revalidate-existing', 'download-updates', 'verify-updates'])
    parser.add_argument('--target', choices=TARGETS, required=True)
    args = parser.parse_args()
    {'prepare': prepare, 'build': build, 'sign-mac': sign_mac, 'smoke-signed': smoke_signed, 'collect': collect,
     'download-existing':download_existing,'revalidate-existing':revalidate_existing,
     'download-updates':download_updates,'verify-updates':verify_updates}[args.action](args.target)
