#!/usr/bin/python3
"""Windows-Python file-boundary tests in a disposable Wine/private-Xvfb session.

Never uses the user's display, Wine prefix, Mistral account or project files.
Wine is a compatibility check, not a substitute for a native Windows/NTFS run.
"""
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time

BASE = Path(__file__).resolve().parents[1]
OUT = BASE/'artifacts/alpha-auto-update/windows-capfs'
OUT.mkdir(parents=True, exist_ok=True)
PYTHON = BASE/'.cache/alpha-runtime-windows/python-runtime/python.exe'
XVFB = BASE/'artifacts/native-test-tools/root/usr/bin/Xvfb'
assert PYTHON.is_file() and XVFB.is_file()

def windows_path(path): return 'Z:' + str(path.resolve()).replace('/', '\\')

with tempfile.TemporaryDirectory(prefix='private-wine-', dir=OUT) as temporary:
    private = Path(temporary)
    prefix = private/'prefix'
    home = private/'home'; home.mkdir()
    env = {'PATH':'/usr/bin:/bin', 'HOME':str(home), 'XDG_CONFIG_HOME':str(private/'config'),
           'XDG_DATA_HOME':str(private/'data'), 'XDG_CACHE_HOME':str(private/'cache'),
           'XDG_RUNTIME_DIR':str(private/'runtime'), 'WINEPREFIX':str(prefix), 'WINEARCH':'win64',
           'WINEDEBUG':'-all', 'WINEDLLOVERRIDES':'winemenubuilder.exe=d', 'LANG':'C.UTF-8',
           'LD_LIBRARY_PATH':str(BASE/'artifacts/native-test-tools/root/usr/lib/x86_64-linux-gnu')}
    for key in ['XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR']:
        Path(env[key]).mkdir(mode=0o700)
    read_fd, write_fd = os.pipe()
    xvfb = None
    result = None
    try:
        with (OUT/'xvfb.log').open('w') as log:
            xvfb = subprocess.Popen([str(XVFB), '-displayfd', str(write_fd), '-screen','0','1280x900x24','-nolisten','tcp'],
                                    env=env, pass_fds=(write_fd,), stdout=log, stderr=log, start_new_session=True)
        os.close(write_fd); write_fd = None
        select = selectors.DefaultSelector(); select.register(read_fd, selectors.EVENT_READ)
        assert select.select(timeout=10), 'Private Xvfb display did not start'
        display = os.read(read_fd, 64).decode().strip()
        select.close(); assert display.isdigit() and int(display)>0
        env['DISPLAY'] = ':' + display
        # cmd opens genuine Windows standard handles for Python. Direct Wine
        # inheritance of this Linux tool's redirected stdio is not equivalent.
        batch = private/'run-tests.cmd'
        batch.write_text('@"' + windows_path(PYTHON) + '" -I "' + windows_path(BASE/'tests/standalone/test_capfs.py') + '" > "C:\\vibez-capfs-tests.log" 2>&1 < NUL\r\n@exit /b %errorlevel%\r\n')
        with (OUT/'wine-bootstrap.log').open('w') as log:
            result = subprocess.run(['/usr/bin/wine', 'cmd.exe', '/d', '/c', windows_path(batch)],
                                    env=env, cwd=private, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        windows_log = prefix/'drive_c/vibez-capfs-tests.log'
        (OUT/'windows-python-tests.log').write_bytes(windows_log.read_bytes() if windows_log.exists() else (OUT/'wine-bootstrap.log').read_bytes())
    finally:
        if write_fd is not None: os.close(write_fd)
        os.close(read_fd)
        # This exact, newly-created prefix is the only Wine instance addressed.
        assert prefix.parent==private and private.parent==OUT
        subprocess.run(['/usr/bin/wineserver','-k'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        if xvfb is not None and xvfb.poll() is None:
            os.killpg(xvfb.pid, signal.SIGTERM)
            xvfb.wait(timeout=5)
    report = {'passed':result is not None and result.returncode==0, 'windows_python':str(PYTHON.relative_to(BASE)),
              'private_wine_prefix':True, 'private_xvfb':True, 'host_displays_used':False,
              'real_user_profiles_or_files_used':False, 'native_windows_ntfs_validation':False,
              'limitations':['Wine tests the Windows Python/API binding path; native Windows/NTFS validation remains required.']}
    (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if not report['passed']:
        print((OUT/'windows-python-tests.log').read_text()[-6000:])
        raise SystemExit(1)
