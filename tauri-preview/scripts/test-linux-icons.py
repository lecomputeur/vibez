#!/usr/bin/env python3
"""Installed-package X11/StatusNotifier integration test. Never opens Mistral."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GLib, GdkPixbuf, Gtk

APP_ID = 'nl.lecomputeur.vibez.tauri.preview'
WATCHER = 'org.kde.StatusNotifierWatcher'
WATCHER_PATH = '/StatusNotifierWatcher'
SNI = 'org.kde.StatusNotifierItem'
XML = '''<node><interface name="org.kde.StatusNotifierWatcher">
<method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
<method name="RegisterStatusNotifierHost"><arg type="s" direction="in"/></method>
<property name="RegisteredStatusNotifierItems" type="as" access="read"/>
<property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
<property name="ProtocolVersion" type="i" access="read"/>
<signal name="StatusNotifierItemRegistered"><arg type="s"/></signal>
<signal name="StatusNotifierHostRegistered"/>
</interface></node>'''


def pump(seconds=0.05):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)
        time.sleep(0.005)


class Watcher:
    """A minimal, actual D-Bus tray host; validates exported icon files."""
    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.items = []
        self.registration = None

    def start(self):
        self.items.clear()
        result = self.bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'RequestName', GLib.Variant('(su)', (WATCHER, 0)),
            GLib.VariantType.new('(u)'), Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
        assert result in (1, 4), 'Could not acquire isolated StatusNotifier watcher'
        interface = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
        self.registration = self.bus.register_object(WATCHER_PATH, interface, self.method, self.property, None)
        self.bus.emit_signal(None, WATCHER_PATH, WATCHER, 'StatusNotifierHostRegistered', None)
        pump(0.1)

    def stop(self):
        if self.registration:
            self.bus.unregister_object(self.registration)
            self.registration = None
        self.bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'ReleaseName', GLib.Variant('(s)', (WATCHER,)),
            None, Gio.DBusCallFlags.NONE, 3000, None)
        self.items.clear()
        pump(0.1)

    def method(self, connection, sender, object_path, interface_name, method, params, invocation):
        if method == 'RegisterStatusNotifierItem':
            service = params.unpack()[0]
            destination, path = (sender, service) if service.startswith('/') else (service, '/StatusNotifierItem')
            if (destination, path) not in self.items:
                self.items.append((destination, path))
            self.bus.emit_signal(None, WATCHER_PATH, WATCHER, 'StatusNotifierItemRegistered',
                GLib.Variant('(s)', (destination + path,)))
        invocation.return_value(None)

    def property(self, connection, sender, object_path, interface_name, name):
        if name == 'RegisteredStatusNotifierItems':
            return GLib.Variant('as', [dest + path for dest, path in self.items])
        if name == 'IsStatusNotifierHostRegistered':
            return GLib.Variant('b', True)
        return GLib.Variant('i', 0)

    def tray(self, process_id, expected_pixels, cache):
        for dest, path in self.items:
            # Do not accept a tray registration left behind by a previous start.
            owner_pid = self.bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                'org.freedesktop.DBus', 'GetConnectionUnixProcessID', GLib.Variant('(s)', (dest,)),
                None, Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
            if owner_pid != process_id:
                continue
            props = self.bus.call_sync(dest, path, 'org.freedesktop.DBus.Properties', 'GetAll',
                GLib.Variant('(s)', (SNI,)), None, Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
            name = props.get('IconName', '')
            theme = props.get('IconThemePath', '')
            candidates = [Path(name), Path(name + '.png')]
            if theme:
                candidates.extend([Path(theme) / name, Path(theme) / (name + '.png')])
            for candidate in candidates:
                if not candidate.is_file():
                    continue
                image = candidate.resolve()
                assert cache.resolve() in image.parents, 'Tray image is outside app-private cache'
                assert str(process_id) in image.parts, 'Tray file not process-isolated'
                assert image_pixels(image) == expected_pixels, 'Tray image does not match the VibeZ PNG'
                assert props.get('Status') == 'Active', props
                return {'status': props['Status'], 'icon_file': str(image.relative_to(cache)), 'pixels_match': True}
        return None


class X11:
    """Read the real server-side window properties, not in-app getters."""
    def __init__(self):
        self.lib = C.CDLL('libX11.so.6')
        self.lib.XOpenDisplay.argtypes = [C.c_char_p]
        self.lib.XOpenDisplay.restype = C.c_void_p
        self.lib.XDefaultRootWindow.argtypes = [C.c_void_p]
        self.lib.XDefaultRootWindow.restype = C.c_ulong
        self.lib.XInternAtom.argtypes = [C.c_void_p, C.c_char_p, C.c_int]
        self.lib.XInternAtom.restype = C.c_ulong
        self.lib.XGetWindowProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long,
            C.c_int, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong),
            C.POINTER(C.c_ulong), C.POINTER(C.POINTER(C.c_ubyte))]
        self.lib.XFree.argtypes = [C.c_void_p]
        self.lib.XCloseDisplay.argtypes = [C.c_void_p]
        self.display = self.lib.XOpenDisplay(None)
        assert self.display, 'No isolated X11 display'
        self.root = self.lib.XDefaultRootWindow(self.display)

    def property(self, window, name):
        actual, fmt, count, after = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong()
        data = C.POINTER(C.c_ubyte)()
        atom = self.lib.XInternAtom(self.display, name.encode(), False)
        result = self.lib.XGetWindowProperty(self.display, window, atom, 0, 1024 * 1024, False,
            0, C.byref(actual), C.byref(fmt), C.byref(count), C.byref(after), C.byref(data))
        assert result == 0 and after.value == 0, f'Cannot read complete {name}'
        try:
            if fmt.value == 8:
                return C.string_at(data, count.value)
            if fmt.value == 32:
                return list(C.cast(data, C.POINTER(C.c_ulong))[:count.value])
            return []
        finally:
            if data:
                self.lib.XFree(data)

    def window(self, pid):
        for window in self.property(self.root, '_NET_CLIENT_LIST'):
            if self.property(window, '_NET_WM_PID') == [pid]:
                return window
        return None

    def inspect(self, window, expected):
        klass = self.property(window, 'WM_CLASS').rstrip(b'\x00').decode().split('\x00')
        app_id = self.property(window, '_GTK_APPLICATION_ID').rstrip(b'\x00').decode()
        assert klass == [APP_ID, APP_ID], f'Window/launcher mismatch: WM_CLASS={klass!r}'
        assert app_id == APP_ID, f'GTK application ID mismatch: {app_id!r}'
        icons = self.property(window, '_NET_WM_ICON')
        assert icons, '_NET_WM_ICON is absent'
        found, sizes, position = False, [], 0
        while position < len(icons):
            assert position + 2 <= len(icons), 'Truncated icon dimensions'
            w, h = icons[position:position + 2]
            assert 0 < w <= 4096 and 0 < h <= 4096, 'Invalid window icon dimensions'
            end = position + 2 + w * h
            assert end <= len(icons), 'Truncated icon pixels'
            pixels = icons[position + 2:end]
            if (w, h, pixels) == expected:
                found = True
            sizes.append([w, h])
            position = end
        assert found, f'Window icon differs from embedded VibeZ image; offered sizes: {sizes}'
        return {'wm_class': klass, 'gtk_app_id': app_id, 'icon_sizes': sizes, 'pixels_match': found}

    def close(self):
        self.lib.XCloseDisplay(self.display)


def image_pixels(filename):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(filename))
    width, height = pixbuf.get_width(), pixbuf.get_height()
    channels, stride, raw = pixbuf.get_n_channels(), pixbuf.get_rowstride(), pixbuf.get_pixels()
    pixels = []
    for y in range(height):
        for x in range(width):
            offset = y * stride + x * channels
            r, g, b = raw[offset:offset + 3]
            alpha = raw[offset + 3] if channels == 4 else 255
            pixels.append((alpha << 24) | (r << 16) | (g << 8) | b)
    return width, height, pixels


def wait_for(callback, process, timeout=15):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        assert process.poll() is None, f'Preview exited early: {process.returncode}'
        pump(0.05)
        try:
            result = callback()
            if result:
                return result
        except GLib.Error as error:
            last = str(error)
    raise AssertionError(f'Timed out waiting for desktop/tray registration: {last}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True)
    parser.add_argument('--source-icon', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    launcher = Gio.DesktopAppInfo.new(APP_ID + '.desktop')
    assert launcher and not launcher.get_nodisplay(), 'Canonical launcher missing or hidden'
    assert launcher.get_startup_wm_class() == APP_ID, 'Desktop StartupWMClass is wrong'
    icon = launcher.get_icon()
    assert isinstance(icon, Gio.FileIcon), 'Launcher still depends on icon-theme cache lookup'
    icon_path = Path(icon.get_file().get_path())
    assert icon_path.is_file(), 'Installed launcher pixmap missing'
    source = Path(args.source_icon).resolve()
    assert icon_path.read_bytes() == source.read_bytes(), 'Installed image differs from source PNG'
    expected = image_pixels(source)
    command = shlex.split(launcher.get_commandline())
    assert command == ['vibez-tauri-preview'], command
    results = []
    watcher = Watcher()
    x11 = X11()
    try:
        with tempfile.TemporaryDirectory(prefix='vibez-icon-profile-') as profile:
            env = dict(os.environ)
            for key, suffix in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')]:
                env[key] = str(Path(profile) / suffix)
                Path(env[key]).mkdir()
            env['LANG'] = 'en_US.UTF-8'
            cache = Path(env['XDG_CACHE_HOME']) / APP_ID / 'tray-icons'
            for run, mode in enumerate(['cold-launcher', 'warm-launcher', 'second-restart', 'direct-executable', 'late-tray-host'], 1):
                watcher.items.clear()
                late = mode == 'late-tray-host'
                if not late:
                    watcher.start()
                executable = [str(Path(args.binary).resolve())] if mode == 'direct-executable' else command
                with (output / f'icon-start-{run}.log').open('w') as log:
                    process = subprocess.Popen(executable + ['--icon-smoke-test'], env=env, stdout=log, stderr=subprocess.STDOUT)
                    try:
                        window = wait_for(lambda: x11.window(process.pid), process)
                        # Validate immediately on first mapped appearance, not only after a restart.
                        metadata = x11.inspect(window, expected)
                        if late:
                            pump(0.5)
                            watcher.start()
                        tray = wait_for(lambda: watcher.tray(process.pid, expected, cache), process)
                        pump(1.0)
                        assert x11.inspect(window, expected) == metadata, 'Metadata changed after startup'
                        assert watcher.tray(process.pid, expected, cache), 'Tray image disappeared'
                        record = {'mode': mode, 'window': metadata, 'tray': tray}
                        results.append(record)
                        print('ICON_START_OK: ' + json.dumps(record), flush=True)
                    finally:
                        process.terminate()
                        try:
                            process.wait(5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                watcher.stop()
            report = {'version': subprocess.check_output([args.binary, '--version'], text=True).strip(),
                'launcher': launcher.get_filename(), 'launcher_icon': str(icon_path),
                'source_icon_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'starts': results}
            (output / 'icon-report.json').write_text(json.dumps(report, indent=2) + '\n')
            print('ICON_SMOKE_OK: installed launcher, exact window icon pixels, identity, five starts and late tray host', flush=True)
    finally:
        if watcher.registration:
            watcher.stop()
        x11.close()


if __name__ == '__main__':
    main()
