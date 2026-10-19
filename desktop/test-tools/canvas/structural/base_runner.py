"""Shared isolated-profile helpers copied from the existing native harness."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
HERE=Path(__file__).resolve().parent

def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    if not path.exists():
        return []
    # The app appends small single records. Ignore only an unfinished last line.
    text = path.read_text()
    lines = text.splitlines()
    if text and not text.endswith('\n'):
        lines = lines[:-1]
    return [json.loads(line) for line in lines if line]


def stop_own(proc):
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=8)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)


def clean_env():
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('VIBEZ_', 'WEBKIT_', 'DBUS_STARTER_')) or key in (
                'LD_PRELOAD', 'DBUS_SESSION_BUS_ADDRESS', 'GNOME_KEYRING_CONTROL',
                'GNOME_KEYRING_PID', 'GDK_SCALE', 'GDK_DPI_SCALE'):
            env.pop(key, None)
    env.update(GDK_BACKEND='x11', GDK_SCALE='1', GDK_DPI_SCALE='1', LIBGL_ALWAYS_SOFTWARE='1', GIO_USE_VFS='local')
    return env


def profile_env(profile, output):
    env = clean_env()
    for key, name in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                      ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state'),
                      ('XDG_RUNTIME_DIR', 'runtime')]:
        folder = profile / name
        folder.mkdir(mode=0o700)
        env[key] = str(folder)
    # Ordinary startup, with update checks disabled only in our disposable profile.
    config = profile / 'config' / 'nl.lecomputeur.vibez3'
    config.mkdir(mode=0o700)
    write(config / 'settings.json', {'schema_version': 1, 'settings': {
        'language': 'en', 'zoom_factor': 1.0, 'show_screenshot': True,
        'close_to_tray': False, 'start_at_login': False, 'auto_updates': False}})
    env['PATH'] = str(HERE / 'opener-recorder') + os.pathsep + env['PATH']
    env['VIBEZ_CANVAS_OPEN_LOG'] = str(output / 'opener.jsonl')
    return env


@contextmanager
def disposable_profile(output, prefix):
    profile = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield profile
    finally:
        # Private DBus-activated portal/GVFS services can leave a disconnected
        # FUSE mount while terminating. Record cleanup failure separately; it
        # must not discard a completed native test or conceal its failed gates.
        try:
            shutil.rmtree(profile)
        except OSError as error:
            write(output / 'profile-cleanup-warning.json', {
                'profile': str(profile), 'errno': error.errno,
                'reason': 'Disposable private-session profile cleanup failed; no user profile is involved.'})

