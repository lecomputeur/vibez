#!/usr/bin/python3
"""Build an independent Arch Alpha package from the verified public Linux payload."""
import argparse,io,json,os,shutil,subprocess,tarfile,tempfile,time
from pathlib import Path
from alpha_linux_payload import BASE,APP_ID,BINARY,BACKEND,PRODUCT,version,digest,check_payload,add_update_files,normalize_modes,updater

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--payload',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();payload=args.payload.resolve(strict=True);output=args.output.resolve();release=check_payload(payload)
    assert not output.exists(),'Refusing to replace an existing candidate';output.parent.mkdir(parents=True,exist_ok=True)
    package_version=release.replace('-','_',1)+'-1';helper=updater()
    dependencies=['python>=3.10','webkit2gtk-4.1','gtk3','libayatana-appindicator','xdg-desktop-portal','xdg-utils','ca-certificates','gnupg','systemd','zstd']
    with tempfile.TemporaryDirectory(prefix='alpha-arch-',dir=output.parent) as temporary:
        work=Path(temporary);staged=work/'root';shutil.copytree(payload,staged);add_update_files(staged);normalize_modes(staged)
        size=sum(p.stat().st_size for p in staged.rglob('*') if p.is_file());epoch=int(os.environ.get('SOURCE_DATE_EPOCH',str(int(time.time()))))
        info=f'pkgname = {BINARY}\npkgbase = {BINARY}\npkgver = {package_version}\npkgdesc = Mistral web conversations with local project folders (Alpha)\nurl = https://github.com/lecomputeur/vibez\nbuilddate = {epoch}\npackager = Le Computeur\nsize = {size}\narch = x86_64\nlicense = MIT\n'+''.join(f'depend = {value}\n' for value in dependencies)
        (staged/'.PKGINFO').write_text(info);(staged/'.INSTALL').write_text(helper.ARCH_INSTALL);normalize_modes(staged)
        raw=work/'alpha.tar'
        def owned(entry):
            entry.uid=entry.gid=0;entry.uname=entry.gname='root';entry.mtime=epoch;return entry
        with tarfile.open(raw,'w',format=tarfile.PAX_FORMAT) as stream:
            for entry in sorted(staged.iterdir()):stream.add(entry,arcname=entry.name,filter=owned)
        subprocess.run(['zstd','-q','-T0','-9','-o',output,'--',raw],check=True)
        helper.validate_arch(output,release)
    report={'version':release,'arch_version':package_version,'package':str(output),'sha256':digest(output),'independent_identity':APP_ID,'only_allowlisted_update_service_hooks':True,'installed_on_host':False,'published':False,'passed':True}
    output.with_suffix(output.suffix+'.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
