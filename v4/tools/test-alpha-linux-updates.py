#!/usr/bin/python3
"""Build disposable signed package fixtures, then test only inside a private container.

The worker requires /.dockerenv and no external network. The root package
managers, signatures and payload validators are real; only downloading the
known fixture assets is replaced by local copies. No production key is used.
"""
import argparse,fcntl,hashlib,importlib.util,io,json,os,shutil,stat,subprocess,sys,tarfile,tempfile,time
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1]
A='4.0.0-alpha.800001';B='4.0.0-alpha.800002';C='4.0.0-alpha.800003'

def load(path):
    spec=importlib.util.spec_from_file_location('fixture_updater',path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def command(args,**kwargs):
    try:return subprocess.check_output([str(x) for x in args],stderr=subprocess.STDOUT,**kwargs)
    except subprocess.CalledProcessError as error:
        print(error.output.decode(errors='replace') if isinstance(error.output,bytes) else error.output,file=sys.stderr)
        raise

def owner(entry):entry.uid=entry.gid=0;entry.uname=entry.gname='root';return entry

def deb(work,helper,value,foreign=False,stable=False):
    name='vibez3' if stable else 'vibe-z-v4-alpha';binary='vibez3' if stable else 'vibez4-alpha';version='3.0.9' if stable else value
    root=work/('deb-'+('stable' if stable else value)+('-foreign' if foreign else ''));(root/'DEBIAN').mkdir(parents=True)
    (root/'DEBIAN/control').write_text(f'Package: {name}\nVersion: {version}\nArchitecture: amd64\nMaintainer: Fixture\nDescription: Disposable updater fixture\n')
    if not stable:
        for name,body in [('postinst',helper.ENABLE),('prerm',helper.REMOVE)]:
            (root/'DEBIAN'/name).write_text(body);(root/'DEBIAN'/name).chmod(0o755)
    path=root/'usr/bin'/binary;path.parent.mkdir(parents=True);path.write_text('STABLE-UNCHANGED' if stable else value);path.chmod(0o755)
    if foreign:(root/'usr/bin/vibez3').write_text('FORBIDDEN')
    for entry in root.rglob('*'):entry.chmod(0o755 if entry.is_dir() or entry.name in {binary,'postinst','prerm'} else 0o644)
    root.chmod(0o755)
    target=work/('vibez3.deb' if stable else f'VibeZ-{value}-Linux-x64.deb');command(['dpkg-deb','--root-owner-group','-Zxz','--build',root,target]);return target

def rpm(work,helper,value,foreign=False,stable=False,link=False):
    name='vibez3' if stable else 'vibez4-alpha';pre=value.split('-',1)[1];version='3.0.9' if stable else '4.0.0';release='1' if stable else '0.'+pre
    root=work/('rpm-'+('stable' if stable else value)+('-link' if link else ''));root.mkdir()
    for folder in ['BUILD','BUILDROOT','RPMS','SOURCES','SPECS','SRPMS','tmp']:(root/folder).mkdir()
    binary='vibez3' if stable else 'vibez4-alpha';content='STABLE-UNCHANGED' if stable else value
    extra='\nmkdir -p "%{buildroot}/usr/lib/VibeZ V4 Alpha"\nln -s /etc/shadow "%{buildroot}/usr/lib/VibeZ V4 Alpha/unsafe"' if link else ''
    files=f'/usr/bin/{binary}'+('\n"/usr/lib/VibeZ V4 Alpha"' if link else '')
    hooks='' if stable else f'\n%posttrans\n{helper.RPM_ENABLE}\n%preun\n{helper.RPM_REMOVE}\n'
    spec=root/'SPECS/fixture.spec';spec.write_text(f'''%global debug_package %{{nil}}
%global _build_id_links none
%global __os_install_post %{{nil}}
Name: {name}
Version: {version}
Release: {release}
Summary: Disposable updater fixture
License: MIT
BuildArch: x86_64
AutoReqProv: no
%description
Disposable updater fixture.
%prep
%build
%install
mkdir -p %{{buildroot}}/usr/bin
printf '%s' '{content}' > %{{buildroot}}/usr/bin/{binary}
chmod 0755 %{{buildroot}}/usr/bin/{binary}{extra}
{hooks}
%files
{files}
''')
    (root/'build.log').write_bytes(command(['rpmbuild','-bb','--define',f'_topdir {root}','--define',f'_tmppath {root}/tmp',spec]))
    built=list((root/'RPMS').rglob('*.rpm'));assert len(built)==1
    target=work/('vibez3.rpm' if stable else f'VibeZ-{value}-Linux-x64.rpm');shutil.copyfile(built[0],target);return target

def arch(work,helper,value):
    target=work/f'VibeZ-{value}-Linux-x64.pkg.tar.zst';raw=work/'arch.tar'
    with tarfile.open(raw,'w') as stream:
        for name,body in [('.PKGINFO',f'pkgname = vibez4-alpha\npkgver = {value.replace("-","_",1)}-1\narch = x86_64\n'),('.INSTALL',helper.ARCH_INSTALL),('usr/bin/vibez4-alpha',value)]:
            data=body.encode();entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o644;stream.addfile(entry,io.BytesIO(data))
    command(['zstd','-q',raw,'-o',target]);raw.unlink();return target

def prepare(work):
    assert not work.exists();work.mkdir();helper=load(BASE/'packaging/alpha-updater/update.py');shutil.copyfile(BASE/'packaging/alpha-updater/update.py',work/'update.py')
    keys=Path(tempfile.mkdtemp(prefix='vibez-fixture-keys-',dir='/tmp'))
    command(['gpg','--homedir',keys,'--batch','--pinentry-mode','loopback','--passphrase','','--quick-generate-key','VibeZ disposable updater fixture','ed25519','sign','0'])
    public=command(['gpg','--homedir',keys,'--batch','--export']);(work/'public.gpg').write_bytes(public)
    listing=command(['gpg','--homedir',keys,'--with-colons','--list-keys'],text=True);fingerprint=next(x.split(':')[9] for x in listing.splitlines() if x.startswith('fpr:'));(work/'fingerprint').write_text(fingerprint)
    for kind in ['deb','rpm']:
        build=deb if kind=='deb' else rpm
        build(work,helper,A);build(work,helper,B);build(work,helper,C,**({'foreign':True} if kind=='deb' else {'link':True}));build(work,helper,A,stable=True)
        for variant,release,channel in [('valid',B,'v4-alpha'),('older',A,'v4-alpha'),('foreign',C,'v4-alpha'),('wrong-channel',C,'stable')]:
            package=work/f'VibeZ-{release}-Linux-x64.{kind}';name=package.name
            document={'schema':1,'channel':channel,'version':release,'assets':{'linux-x86_64-'+kind:{'name':name,'url':f'https://github.com/lecomputeur/vibez/releases/download/v{release}/{name}','size':package.stat().st_size,'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}}}
            feed=work/f'{kind}-{variant}.json';feed.write_text(json.dumps(document));command(['gpg','--homedir',keys,'--batch','--yes','--armor','--detach-sign',feed])
    arch(work,helper,B)
    # Only a disposable signing key was used. It is no longer needed by tests.
    command(['gpgconf','--homedir',keys,'--kill','gpg-agent']);shutil.rmtree(keys)
    print(json.dumps({'fixture':str(work),'prepared':True,'production_key_used':False}))

def worker(work):
    assert Path('/.dockerenv').is_file(),'The worker may only run in the disposable container'
    assert os.geteuid()==0 and {p.name for p in Path('/sys/class/net').iterdir()}=={'lo'},'Disconnect container networking before running'
    for trusted in [work/'update.py',work/'public.gpg']:os.chown(trusted,0,0)
    helper=load(work/'update.py');helper.KEYRING=work/'public.gpg';(work/'update.py').chmod(0o644);helper.KEYRING.chmod(0o644);helper.FINGERPRINT=(work/'fingerprint').read_text().strip()
    outcomes=[]
    shutil.rmtree(helper.STATE,ignore_errors=True)
    stable=Path('/usr/bin/vibez3');os.environ['PATH']='/fixture/tools:/usr/bin:/bin:/usr/sbin:/sbin';os.environ['LD_LIBRARY_PATH']='/fixture/tools/lib'
    command(['dpkg','--version']);command(['rpm','--version'])
    def update(kind,variant,bad_signature=False):
        feed=work/f'{kind}-{variant}.json';signature=feed.with_suffix('.json.asc')
        document=json.loads(feed.read_text());asset=document['assets']['linux-x86_64-'+kind]
        def local(url,target,limit):
            source=signature if url==helper.FEED+'.asc' else feed if url==helper.FEED else work/asset['name']
            data=source.read_bytes()
            if bad_signature and url==helper.FEED:data+=b'\nchanged'
            assert len(data)<=limit;target.write_bytes(data);target.chmod(0o600)
        with patch.object(helper,'download',side_effect=local):helper.main()
        return json.loads((helper.STATE/'status.json').read_text())
    # Complete real DEB/RPM transactions happen only in this disposable root.
    for kind in ['deb','rpm']:
        if kind=='deb':command(['dpkg','-i',work/'vibez3.deb'])
        elif subprocess.run(['rpm','-q','vibez3'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            command(['rpm','-U','--',work/'vibez3.rpm'])
        else:assert command(['rpm','-q','--qf','%{VERSION}','vibez3'])==b'3.0.9'
        before=stable.read_bytes();package=work/f'VibeZ-{A}-Linux-x64.{kind}'
        command(['dpkg','-i',package]) if kind=='deb' else command(['rpm','-U','--',package])
        assert helper.installed()==(kind,A)
        lock=(helper.STATE/'running.lock').open('rb');fcntl.flock(lock,fcntl.LOCK_SH)
        waiting=update(kind,'valid');assert waiting['status']=='waiting_for_close' and helper.installed()==(kind,A)
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
        # The real /proc fallback also prevents replacing a running Alpha even
        # when an older app did not participate in the shared running lock.
        executable=Path('/tmp/vibez4-alpha');shutil.copyfile('/usr/bin/sleep',executable);executable.chmod(0o755)
        process=subprocess.Popen([str(executable),'30'])
        try:assert update(kind,'valid')['status']=='waiting_for_close' and helper.installed()==(kind,A)
        finally:process.terminate();process.wait()
        updated=update(kind,'valid');assert updated['status']=='updated' and helper.installed()==(kind,B)
        for variant,bad in [('valid',True),('wrong-channel',False),('foreign',False)]:
            try:update(kind,variant,bad);raise AssertionError('Invalid update accepted')
            except (ValueError,subprocess.CalledProcessError):pass
            assert helper.installed()==(kind,B) and stable.read_bytes()==before
        assert update(kind,'older')['status']=='current' and helper.installed()==(kind,B)
        assert stable.read_bytes()==before
        command(['dpkg-query','-W','-f=${Version}','vibez3']) if kind=='deb' else command(['rpm','-q','--qf','%{VERSION}','vibez3'])
        outcomes.append({'format':kind,'actual_package_manager_install_A_to_B':True,'real_gpgv_signature_check':True,'waits_for_shared_running_lock':True,'waits_for_proc_process_fallback':True,'bad_signature_rejected':True,'wrong_channel_rejected':True,'foreign_file_or_symlink_payload_rejected':True,'downgrade_rejected':True,'dummy_3_0_9_unchanged':True})
        command(['dpkg','-r','vibe-z-v4-alpha']) if kind=='deb' else command(['rpm','-e','vibez4-alpha'])
        shutil.rmtree(helper.STATE)
    helper.validate_arch(work/f'VibeZ-{B}-Linux-x64.pkg.tar.zst',B)
    # Lifecycle scripts only enable once. A stub records systemctl calls inside
    # the fixture root; no system manager is started or contacted.
    fake=Path('/fixture/tools/systemctl');fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> /fixture/systemctl.log\n');fake.chmod(0o755)
    systemd=Path('/run/systemd/system');systemd.mkdir(parents=True,exist_ok=True)
    script=Path('/fixture/enable.sh');script.write_text(helper.ENABLE)
    command(['/bin/sh',script,'configure']);command(['/bin/sh',script,'configure',A])
    calls=Path('/fixture/systemctl.log').read_text().splitlines();assert calls.count('enable --now vibez4-alpha-update.timer')==1
    for name in ['usr/bin/vibez3','etc/shadow','usr/share/applications/vibez3.desktop','../usr/bin/vibez4-alpha']:
        assert not helper.package_path(name)
    for name in ['etc','var','usr/lib/other-application']:
        entry=tarfile.TarInfo(name);entry.type=tarfile.DIRTYPE;entry.mode=0o755
        try:helper.safe_entry(entry,set());raise AssertionError('Foreign directory accepted')
        except ValueError:pass
    print(json.dumps({'passed':True,'cases':outcomes,'arch_archive_validation':True,'initial_service_enable_only':True,'foreign_directories_rejected':True,'host_installation_modified':False,'host_services_activated':False,'network_during_test':False,'fixture_only':True},indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--worker',action='store_true');args=parser.parse_args()
    worker(args.work.resolve()) if args.worker else prepare(args.work.resolve())
if __name__=='__main__':main()
