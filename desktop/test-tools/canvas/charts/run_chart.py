#!/usr/bin/env python3
"""Native A/B srcdoc graph readiness, screenshots and bounded idle CPU control."""
import argparse, json, math, os, shlex, subprocess, sys, time
from pathlib import Path
import base_runner as base
from chart_report import check_chart

HERE=Path(__file__).resolve().parent

def processes(root):
    all_processes={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            raw=(path/'stat').read_text();fields=raw[raw.rindex(')')+2:].split()
            all_processes[int(path.name)]={'parent':int(fields[1]),'ticks':int(fields[11])+int(fields[12]),'rss':int(fields[21])*os.sysconf('SC_PAGE_SIZE'),'name':raw[raw.index('(')+1:raw.rindex(')')]}
        except (OSError,ValueError,IndexError):pass
    owned={root}
    while True:
        added={pid for pid,p in all_processes.items() if p['parent'] in owned}-owned
        if not added:break
        owned|=added
    return {pid:p for pid,p in all_processes.items() if pid in owned and p['name'].startswith('WebKitWebProces')}

def host_cpu():
    values=[int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    return sum(values),values[3]+values[4]

def worker(args):
    out=args.output
    wm=subprocess.Popen(['openbox','--sm-disable'],stdout=(out/'openbox.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
    try:
        time.sleep(.7)
        with base.disposable_profile(out,'vz-chart-') as profile:
            env=base.profile_env(profile,out)
            env.update(VIBEZ_CANVAS_MODE='controlled-html',VIBEZ_CANVAS_FIXTURE=str(out/'fixture.html'),VIBEZ_CANVAS_NATIVE_LOG=str(out/'native-trace.jsonl'),VIBEZ_CHART_SCREENSHOT=str(out/'chart.png'),LD_PRELOAD=str(out/'observer.so'))
            (out/'opener.jsonl').touch()
            proc=subprocess.Popen(['dbus-run-session','--',str(args.binary)],env=env,stdout=(out/'app.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
            samples=[];previous={};previous_host=host_cpu();last=time.monotonic();start=last
            try:
                while proc.poll() is None and time.monotonic()-start<args.duration:
                    time.sleep(.5);now=time.monotonic();observed=processes(proc.pid)
                    ticks=sum(max(0,p['ticks']-previous[pid]['ticks']) for pid,p in observed.items() if pid in previous)
                    host=host_cpu();host_total=host[0]-previous_host[0];host_idle=host[1]-previous_host[1];previous_host=host
                    samples.append({'hostCpuPercent':round((1-host_idle/host_total)*100,3) if host_total else None,'hostLoadAverage':os.getloadavg(),'seconds':round(now-start,3),'cpuPercent':round(ticks/os.sysconf('SC_CLK_TCK')/(now-last)*100,3),'rssMiB':round(sum(p['rss'] for p in observed.values())/1048576,3),'webProcesses':len(observed)})
                    previous=observed;last=now
                observed_duration=time.monotonic()-start;exited_early=proc.poll() is not None
            finally:base.stop_own(proc)
            events=base.rows(out/'native-trace.jsonl');states=[e['ownFixtureState'] for e in events if e.get('ownFixtureState',{}).get('controlledFixture')]
            state=states[-1] if states else {};idle=[s for s in samples if 8<=s['seconds']<=args.idle_end]
            queries=[e for e in events if e.get('ownFixtureState',{}).get('controlledFixture')]
            last_query=queries[-1]['monotonicUs']/1000000-start if queries else None
            gate=check_chart(state,args.count,args.expect)
            fixed=gate['fixedContractPassed']
            result={'ok':bool(gate['expectedStatePassed'] and (out/'chart.png').exists() and idle and all(s['webProcesses'] for s in idle) and not exited_early and observed_duration>=args.duration and last_query is not None and last_query>=args.idle_end-2), 'expectation':args.expect,'fixedContractPassed':fixed,'finalFixtureState':state,'idleCpuMean':sum(s['cpuPercent'] for s in idle)/len(idle) if idle else None,'idleCpuMax':max((s['cpuPercent'] for s in idle),default=None),'idleSeconds':[8,args.idle_end],'requestedDurationSeconds':args.duration,'observedDurationSeconds':observed_duration,'appExitedEarly':exited_early,'stateQueryCount':len(queries),'lastStateQuerySeconds':last_query,'stateQueryIntervalSeconds':1,'sampleIntervalSeconds':.5,'hostLogicalCpuCount':os.cpu_count(),'hostCpuMeanDuringIdle':sum(s['hostCpuPercent'] for s in idle)/len(idle) if idle else None,'hostCpuMaxDuringIdle':max((s['hostCpuPercent'] for s in idle),default=None),'openerInvocations':len(base.rows(out/'opener.jsonl')),'screenshotExists':(out/'chart.png').exists(),'snapshotRecords':[e for e in events if e.get('event')=='chart-snapshot'],'samples':samples,'binary':str(args.binary),'binarySha256':base.digest(args.binary),'limitations':['Controlled synthetic srcdoc charts, not a real Mistral Canvas or conversation.','Xvfb/software renderer; these local CPU figures do not establish original idle-CPU root cause.','Each iframe retries only every 1.2 seconds until validated ready. No artificial CPU load.','Native policy handlers are unmodified; preload replaces only first Mistral document and observes signals.','Idle includes one native state-query per second, equally in baseline/candidate.']}
            base.write(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k!='samples'},indent=2));return 0 if result['ok'] else 1
    finally:base.stop_own(wm)

def main():
    p=argparse.ArgumentParser();p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expect',choices=['old','fixed'],required=True);p.add_argument('--count',type=int,choices=[1,8],required=True);p.add_argument('--duration',type=float,default=26);p.add_argument('--idle-end',type=float,default=20);p.add_argument('--worker',action='store_true');args=p.parse_args();args.binary=args.binary.resolve(strict=True);args.output=args.output.resolve()
    if not math.isfinite(args.duration) or not math.isfinite(args.idle_end) or not 8<args.idle_end<args.duration:p.error('Require finite 8 < idle-end < duration')
    if args.worker:return worker(args)
    args.output.mkdir(parents=True,exist_ok=True)
    if any(args.output.iterdir()):p.error('Output must be empty')
    (args.output/'fixture.html').write_text((HERE/'fixture.html').read_text().replace('__COUNT__',str(args.count)))
    polls=math.ceil(args.duration)
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','webkit2gtk-4.1'],text=True));subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',f'-DVIBEZ_CHART_POLL_COUNT={polls}',str(HERE/'observer.c'),'-o',str(args.output/'observer.so'),*flags,'-ldl'],check=True)
    base.write(args.output/'metadata.json',{'binary':str(args.binary),'binarySha256':base.digest(args.binary),'count':args.count,'expect':args.expect,'durationSeconds':args.duration,'observerPollCount':polls,'stateQueryIntervalSeconds':1,'webkitVersion':subprocess.check_output(['pkg-config','--modversion','webkit2gtk-4.1'],text=True).strip(),'harnessSha256':{path.name:base.digest(path) for path in HERE.iterdir() if path.is_file()},'display':'Dedicated Xvfb 1600x1000x24; never user display','warmupSeconds':8,'idleSamplingEndSeconds':args.idle_end})
    env=base.clean_env();return subprocess.call(['xvfb-run','-a','-s','-screen 0 1600x1000x24',sys.executable,str(Path(__file__).resolve()),'--worker','--binary',str(args.binary),'--output',str(args.output),'--expect',args.expect,'--count',str(args.count),'--duration',str(args.duration),'--idle-end',str(args.idle_end)],env=env)

if __name__=='__main__':raise SystemExit(main())
