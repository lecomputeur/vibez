#!/usr/bin/env python3
"""Real executable, closed HTTPS fixture, native observations, unchanged policies."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import base_runner as base
import fixture_server
import report

HERE=Path(__file__).resolve().parent

def worker(args):
    out=args.output;server,cert=fixture_server.start(out)
    wm=subprocess.Popen(['openbox','--sm-disable'],stdout=(out/'openbox.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
    try:
        time.sleep(.7)
        if wm.poll() is not None:raise RuntimeError('Private Openbox did not start')
        with base.disposable_profile(out,'vz-struct-') as profile:
            env=base.profile_env(profile,out)
            env.update(VIBEZ_CANVAS_MODE='controlled-html',VIBEZ_CANVAS_FIXTURE=str(out/'fixture.html'),
                       VIBEZ_CANVAS_NATIVE_LOG=str(out/'native.jsonl'),LD_PRELOAD=str(out/'observer.so'),
                       VIBEZ_STRUCTURAL_CERT=str(cert),VIBEZ_STRUCTURAL_PROXY=f'http://127.0.0.1:{server.server_port}')
            (out/'opener.jsonl').touch();start=time.monotonic();settled=None
            with (out/'app.log').open('w') as log:
                app=subprocess.Popen(['dbus-run-session','--',str(args.binary)],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    while app.poll() is None and time.monotonic()-start<args.timeout:
                        events=base.rows(out/'native.jsonl')
                        if any(e.get('ownFixtureState',{}).get('finished') is True for e in events):
                            if settled is None:settled=time.monotonic()
                            if time.monotonic()-settled>2:break
                        time.sleep(.25)
                    exited=app.poll() is not None
                finally:base.stop_own(app)
            events=base.rows(out/'native.jsonl');requests=base.rows(out/'server.jsonl');opens=base.rows(out/'opener.jsonl')
            result=(report.check_auth_popup_boundary if args.scenario=='auth-popup-boundary' else report.check)(events,requests,opens)
            result.update(binary=str(args.binary),binarySha256=base.digest(args.binary),elapsedSeconds=round(time.monotonic()-start,3),appExitedBeforeObservation=exited)
            if exited:result['ok']=False
            base.write(out/'result.json',result)
            print(json.dumps({'ok':result['ok'],'elapsedSeconds':result['elapsedSeconds'],
                              'checks':len(result['checks']),'failedChecks':[c for c in result['checks'] if not c['passed']],
                              'binarySha256':result['binarySha256']},indent=2),flush=True)
            return 0 if result['ok'] else 1
    finally:
        base.stop_own(wm);server.shutdown();server.server_close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=float,default=100);p.add_argument('--scenario',choices=('full','auth-popup-boundary'),default='full');p.add_argument('--worker',action='store_true');args=p.parse_args()
    args.binary=args.binary.resolve(strict=True);args.output=args.output.resolve()
    if args.worker:return worker(args)
    args.output.mkdir(parents=True,exist_ok=True)
    if any(args.output.iterdir()):p.error('Output must be empty')
    fixture='auth_popup_boundary.html' if args.scenario=='auth-popup-boundary' else 'fixture.html'
    (args.output/'fixture.html').write_text((HERE/fixture).read_text().replace('__RESUME__','false'))
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','webkit2gtk-4.1'],text=True))
    subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',str(HERE/'observer.c'),'-o',str(args.output/'observer.so'),*flags,'-ldl'],check=True)
    base.write(args.output/'metadata.json',{'binary':str(args.binary),'binarySha256':base.digest(args.binary),
        'webkitVersion':subprocess.check_output(['pkg-config','--modversion','webkit2gtk-4.1'],text=True).strip(),
        'fixtureNetwork':'Closed loopback CONNECT proxy with certificate exceptions only in private WebKit contexts; no forwarding',
        'harnessSha256':{str(f.relative_to(HERE)):base.digest(f) for f in sorted(HERE.rglob('*')) if f.is_file() and '__pycache__' not in str(f)},
        'navigationHandlersChanged':False,'scenario':args.scenario,'display':'Own Xvfb/Openbox; never inherited user display'})
    env=base.clean_env();proc=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1600x1000x24',sys.executable,str(Path(__file__).resolve()),'--worker','--binary',str(args.binary),'--output',str(args.output),'--timeout',str(args.timeout),'--scenario',args.scenario],env=env,start_new_session=True)
    try:return proc.wait(timeout=args.timeout+35)
    finally:base.stop_own(proc)

if __name__=='__main__':raise SystemExit(main())
