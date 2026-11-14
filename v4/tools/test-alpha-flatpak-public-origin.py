#!/usr/bin/python3
"""Verify the public Alpha OSTree repository in a new private installation.

Downloads public signed metadata and app objects. Never launches an app or uses
the user's Flatpak remotes, profile or displays.
"""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

APP='nl.lecomputeur.vibez4.alpha'
ORIGIN='https://raw.githubusercontent.com/lecomputeur/vibez/v4-alpha-flatpak/'
REMOTE='vibez-alpha-public-verification'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--public-key',type=Path,required=True)
    parser.add_argument('--expected-commit',required=True)
    parser.add_argument('--expected-binary-sha256',required=True)
    args=parser.parse_args();work=args.work.resolve();assert not work.exists();work.mkdir()
    env=dict(os.environ)
    for key in ['DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','AT_SPI_BUS_ADDRESS','VIBEZ_SAFE_OUTPUT']:
        env.pop(key,None)
    for key,folder in [('HOME','home'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state'),('FLATPAK_USER_DIR','installation'),('FLATPAK_CONFIG_DIR','etc')]:
        path=work/folder;path.mkdir(mode=0o700);env[key]=str(path)
    def run(name,command,timeout=150):
        print(name,flush=True)
        result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=timeout)
        (work/(name+'.log')).write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError(name+' failed; see its private log')
        return result.stdout.strip()
    report={'passed':False,'origin':ORIGIN,'private_installation':True,
            'host_installation_modified':False,'host_displays_used':False,'app_started':False,
            'private_signing_key_used':False,'public_key_sha256':hashlib.sha256(args.public_key.read_bytes()).hexdigest()}
    installed=False;started=time.monotonic()
    try:
        run('add-public-signed-origin',['flatpak','remote-add','--user','--no-use-for-deps','--gpg-import='+str(args.public_key.resolve()),REMOTE,ORIGIN])
        config=configparser.ConfigParser(interpolation=None);config.read(Path(env['FLATPAK_USER_DIR'])/'repo/config')
        remote=config['remote "'+REMOTE+'"'];assert remote['url']==ORIGIN
        assert remote.getboolean('gpg-verify') and remote.getboolean('gpg-verify-summary',fallback=True)
        report.update(gpg_verify=True,gpg_verify_summary=True)
        commit=run('verify-public-summary-and-ref',['flatpak','remote-info','--user','--show-commit',REMOTE,APP+'//alpha'])
        assert commit==args.expected_commit,(commit,args.expected_commit)
        report['public_signed_commit']=commit
        run('download-and-verify-public-app-objects',['flatpak','install','--user','--noninteractive','--assumeyes','--no-deps','--no-related',REMOTE,APP+'//alpha'],240)
        installed=True
        deployed=run('deployed-commit',['flatpak','info','--user','--show-commit',APP]);assert deployed==commit
        location=Path(run('private-deployment-location',['flatpak','info','--user','--show-location',APP])).resolve()
        assert location.is_relative_to(work)
        binary=location/'files/bin/vibez4-alpha'
        actual=hashlib.sha256(binary.read_bytes()).hexdigest();assert actual==args.expected_binary_sha256
        report.update(passed=True,public_summary_ref_commit_and_content_verified=True,
                      deployed_commit=deployed,canonical_binary_sha256=actual,
                      no_python_bytecode=not list((location/'files').rglob('*.pyc')))
    except Exception as error:
        report['error']=str(error)
    finally:
        if installed:
            result=subprocess.run(['flatpak','uninstall','--user','--noninteractive','--assumeyes','--no-related',APP],env=env,capture_output=True,text=True,timeout=60)
            (work/'uninstall.log').write_text(result.stdout+result.stderr)
            report['private_app_uninstalled']=result.returncode==0
        report['elapsed_seconds']=round(time.monotonic()-started,2)
    (work/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':main()
