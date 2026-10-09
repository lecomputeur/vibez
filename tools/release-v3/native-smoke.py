#!/usr/bin/env python3
"""Run the real native integration suite on macOS/Windows with a fresh profile."""
import subprocess,sys,os,pathlib,tempfile
binary=pathlib.Path(sys.argv[1]).resolve(); log=pathlib.Path(sys.argv[2]);log.parent.mkdir(parents=True,exist_ok=True)
env=os.environ.copy()
with tempfile.TemporaryDirectory(prefix='vibez3-native-') as temp:
    for variable,sub in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')]:
        folder=pathlib.Path(temp)/sub;folder.mkdir();env[variable]=str(folder)
    with log.open('w') as output:
        result=subprocess.run([str(binary),'--smoke-test','--update-download-probe'],env=env,stdout=output,stderr=subprocess.STDOUT,timeout=240)
    text=log.read_text(errors='replace');print(text)
    if result.returncode: raise SystemExit(result.returncode)
    for marker in ['SMOKE_OK:','HISTORY_OK:','LANGUAGE_BOOTSTRAP_OK:','HIDDEN_OK:']:
        if marker not in text: raise SystemExit('Missing native success marker '+marker)
