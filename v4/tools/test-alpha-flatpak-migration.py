#!/usr/bin/python3
"""Verify an old origin-less Alpha bundle adopts the signed update channel.

Only a private Flatpak installation is changed. No app or display is started.
"""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import subprocess

APP='nl.lecomputeur.vibez4.alpha'
ORIGIN='https://raw.githubusercontent.com/lecomputeur/vibez/v4-alpha-flatpak/'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-bundle',type=Path,required=True)
    parser.add_argument('--new-bundle',type=Path)
    parser.add_argument('--flatpakref',type=Path)
    parser.add_argument('--repair-existing-origin',action='store_true')
    parser.add_argument('--verify-local-repo',type=Path)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args();work=args.work.resolve();assert not work.exists();work.mkdir()
    assert bool(args.new_bundle)!=bool(args.flatpakref),'Choose either a new bundle or a flatpakref'
    expected_origin=ORIGIN
    if args.flatpakref:
        reference=configparser.ConfigParser(interpolation=None);reference.read(args.flatpakref)
        expected_origin=reference['Flatpak Ref']['Url']
    env=dict(os.environ)
    for key in ['DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','AT_SPI_BUS_ADDRESS','VIBEZ_SAFE_OUTPUT']:
        env.pop(key,None)
    for key,folder in [('HOME','home'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state'),('FLATPAK_USER_DIR','installation'),('FLATPAK_CONFIG_DIR','etc')]:
        path=work/folder;path.mkdir(mode=0o700);env[key]=str(path)
    def run(name,command):
        result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
        (work/(name+'.log')).write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError(name+' failed; see its private log')
        return result.stdout.strip()
    def origin_state(name):
        origin=run(name+'-name',['flatpak','info','--user','--show-origin',APP])
        config=configparser.ConfigParser(interpolation=None);config.read(Path(env['FLATPAK_USER_DIR'])/'repo/config')
        remote=config['remote "'+origin+'"']
        return {'name':origin,'url':remote.get('url',''),'gpg_verify':remote.getboolean('gpg-verify',fallback=True),'gpg_verify_summary':remote.getboolean('gpg-verify-summary',fallback=True)}
    report={'passed':False,'fixture_only':True,'host_installation_modified':False,'app_started':False,'host_displays_used':False}
    try:
        for name,bundle in [('old',args.old_bundle),('new',args.new_bundle or args.flatpakref)]:
            report[name+'_input_sha256']=hashlib.sha256(bundle.read_bytes()).hexdigest()
            mode=['--reinstall','--from'] if name=='new' and args.flatpakref else ['--bundle']
            run('install-'+name,['flatpak','install','--user',*mode,'--noninteractive','--assumeyes','--no-deps','--no-related',str(bundle.resolve())])
            report[name+'_origin']=origin_state(name)
            report[name+'_commit']=run(name+'-commit',['flatpak','info','--user','--show-commit',APP])
            marker=Path(env['HOME'])/'.var/app'/APP/'data/existing-profile.txt'
            if name=='old':
                marker.parent.mkdir(parents=True,exist_ok=True);marker.write_text('keep this existing Alpha profile\n')
            else:assert marker.read_text()=='keep this existing Alpha profile\n'
        assert not report['old_origin']['url'],'The baseline bundle already has an update origin'
        if args.repair_existing_origin:
            name=report['new_origin']['name']
            run('enable-own-origin-verification',['flatpak','remote-modify','--user','--gpg-verify',name])
            report['new_origin_before_repair']=report['new_origin']
            report['new_origin']=origin_state('repaired')
        assert report['new_origin']['url']==expected_origin
        assert report['new_origin']['gpg_verify'] and report['new_origin']['gpg_verify_summary']
        assert report['old_commit']!=report['new_commit']
        if args.verify_local_repo:
            run('private-local-origin',['flatpak','remote-modify','--user','--url='+args.verify_local_repo.resolve().as_uri(),report['new_origin']['name']])
        verified=run('verify-new-origin',['flatpak','remote-info','--user','--show-commit',report['new_origin']['name'],APP+'//alpha'])
        assert verified==report['new_commit']
        if args.verify_local_repo:
            run('restore-channel-url',['flatpak','remote-modify','--user','--url='+expected_origin,report['new_origin']['name']])
            assert origin_state('restored')==report['new_origin']
        report.update(passed=True,new_channel_and_trust_adopted=True,existing_alpha_profile_preserved=True,
                      final_repository_cryptographically_verified=True,explicit_reinstall_from_flatpakref=bool(args.flatpakref),
                      one_time_own_origin_verification_enabled=bool(args.repair_existing_origin))
    except Exception as error:
        report['error']=str(error)
    finally:
        result=subprocess.run(['flatpak','uninstall','--user','--noninteractive','--assumeyes','--no-related',APP],env=env,capture_output=True,text=True,timeout=45)
        (work/'uninstall.log').write_text(result.stdout+result.stderr)
        report['private_app_uninstalled']=result.returncode==0
    (work/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':main()
