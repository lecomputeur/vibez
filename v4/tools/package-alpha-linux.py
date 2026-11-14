#!/usr/bin/python3
"""Create independent public and personal Alpha DEBs from a generated Tauri DEB."""
import argparse,json,re,shutil,subprocess,tempfile
from pathlib import Path
from alpha_linux_payload import BASE,APP_ID,BINARY,PRODUCT,updater,version,digest,add_update_files,check_payload,normalize_modes

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deb',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--payload',type=Path,required=True)
    parser.add_argument('--public-key',type=Path,default=BASE/'desktop/src-tauri/alpha-updates.gpg')
    args=parser.parse_args();release=version();source=args.deb.resolve(strict=True);output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    outputs=[output/f'VibeZ-{release}-Linux-x64.deb',output/f'VibeZ-{release}-Linux-x64-Personal.deb']
    assert all(not p.exists() for p in outputs),'Refusing to replace an existing package'
    payload=args.payload.resolve();assert not payload.exists(),'Refusing to overwrite an existing payload'
    fields=subprocess.check_output(['dpkg-deb','-f',source,'Package','Version','Architecture'],text=True)
    assert fields==f'Package: vibe-z-v4-alpha\nVersion: {release}\nArchitecture: amd64\n',fields
    with tempfile.TemporaryDirectory(prefix='alpha-deb-',dir=output) as temp:
        staged=Path(temp)/'root';subprocess.run(['dpkg-deb','-R',source,staged],check=True)
        controls=staged/'DEBIAN';assert {p.name for p in controls.iterdir()}<={'control','md5sums','postinst','prerm'}
        for hook in ['postinst','prerm']:(controls/hook).unlink(missing_ok=True)
        desktop=staged/f'usr/share/applications/{APP_ID}.desktop'
        original=desktop.read_text()
        duplicate=staged/f'usr/share/applications/{PRODUCT}.desktop'
        if duplicate.exists():
            assert duplicate.is_file() and not duplicate.is_symlink(),'Unexpected duplicate launcher type'
            assert duplicate.read_text()==original,'Generated duplicate launcher does not match Alpha identity'
            assert 'Name=VibeZ V4 Beta\n' in original and f'Exec={BINARY}\n' in original,'Unexpected launcher identity'
            duplicate.unlink()
        public=re.sub(r'^Exec=.*$',f'Exec={BINARY}',original,flags=re.M)
        assert public!=original or f'Exec={BINARY}' in original
        desktop.write_text(public)
        add_update_files(staged,args.public_key.resolve(strict=True));check_payload(staged,release)
        control=(controls/'control').read_text()
        control=re.sub(r'^Installed-Size:.*\n','',control,flags=re.M)
        dependencies=re.search(r'^Depends: (.*)$',control,re.M)
        assert dependencies,'Missing dependency declaration'
        wanted=dependencies[1]
        if not re.search(r'(^|,\s*)gpgv(?:\s|,|$)',wanted):wanted+=', gpgv'
        control=control[:dependencies.start(1)]+wanted+control[dependencies.end(1):]
        assert not re.search(r'^(Conflicts|Replaces|Breaks|Provides):',control,re.M)
        (controls/'control').write_text(control)
        helper=updater();(controls/'postinst').write_text(helper.ENABLE);(controls/'prerm').write_text(helper.REMOVE)
        for hook in ['postinst','prerm']:(controls/hook).chmod(0o755)
        normalize_modes(staged/'usr')
        (controls/'md5sums').unlink(missing_ok=True)
        for index,target in enumerate(outputs):
            if index:desktop.write_text(re.sub(r'^Exec=.*$',f'Exec=env VIBEZ_SAFE_OUTPUT=DisplayPort-1 {BINARY}',public,flags=re.M))
            subprocess.run(['dpkg-deb','--root-owner-group','-Zxz','--build',staged,target],check=True,stdout=subprocess.DEVNULL)
            helper.validate_deb(target,release)
        desktop.write_text(public);shutil.copytree(staged/'usr',payload/'usr')
        (payload/'usr/share/licenses'/BINARY).mkdir(parents=True,exist_ok=True)
        shutil.copyfile(BASE/'LICENSE',payload/'usr/share/licenses'/BINARY/'LICENSE')
        normalize_modes(payload)
    report={'version':release,'public_deb':str(outputs[0]),'personal_deb':str(outputs[1]),'payload':str(payload),
            'sha256':{p.name:digest(p) for p in outputs},'initial_timer_enable_only':True,'service_activated_on_host':False,'installed_on_host':False,'passed':True}
    (output/f'alpha-linux-{release}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
