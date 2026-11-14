"""OS facade for VibeZ's capability-scoped file operations.

POSIX calls delegate unchanged to os. Windows uses single-component NT opens
relative to retained directory handles, never joined-path containment checks.
Reparse points, device paths and alternate data streams cannot become file
capabilities. Unsupported operations fail closed rather than following paths.
"""
from __future__ import annotations
import collections
import configparser
import contextlib
import ctypes
import errno
import hashlib
import json
import ntpath
import os as _os
from pathlib import Path
import platform
import re
import stat as _stat
import sys
import threading
import uuid


def __getattr__(key):
    return getattr(_os, key)


def windows_component(value):
    """Validate one NT filename, including names Win32 would silently alias."""
    if (not isinstance(value, str) or not value or value in ('.', '..') or
            any(ord(c) < 32 or c in '<>:"/\\|?*\0' for c in value) or
            value[-1] in ' .' or len(value.encode('utf-16-le', errors='strict')) > 510):
        raise ValueError('Invalid Windows file name')
    stem = value.split('.', 1)[0].upper()
    if stem in {'CON', 'PRN', 'AUX', 'NUL'} or re.fullmatch(r'(?:COM|LPT)[1-9¹²³]', stem):
        raise ValueError('Device names are not allowed')
    return value


def windows_absolute(value):
    """Local drive paths only. No UNC, device namespace, drive-relative or .."""
    value = _os.fspath(value)
    if not isinstance(value, str) or '\0' in value:
        raise ValueError('Invalid absolute file path')
    value = value.replace('/', '\\')
    if value.startswith('\\\\?\\'):
        value = value[4:]
    if not re.match(r'^[A-Za-z]:\\', value):
        raise ValueError('Choose a local Windows folder, not a network or device path')
    tail = value[3:]
    parts = tail.split('\\') if tail else []
    if parts and parts[-1] == '':
        parts.pop()
    for part in parts:
        windows_component(part)
    drive = value[:2].upper() + '\\'
    return drive + '\\'.join(parts), drive, parts


def absolute_parts(value):
    if _os.name == 'nt':
        _, drive, parts = windows_absolute(value)
        return drive, parts
    if not isinstance(value, str) or not value.startswith('/') or '\0' in value:
        raise ValueError('Invalid file path')
    parts = value.split('/')
    if any(part in ('.', '..') for part in parts):
        raise ValueError('Invalid file path')
    return '/', list(filter(None, parts))


def is_absolute(value):
    try:
        absolute_parts(value)
        return True
    except (ValueError, TypeError, UnicodeError):
        return False


def canonical_root(value):
    if _os.name == 'nt':
        return windows_absolute(value)[0]
    return str(Path(value).resolve(strict=True))


def split_absolute(value):
    absolute_parts(value)
    if _os.name == 'nt':
        normalized = windows_absolute(value)[0].rstrip('\\')
        parent, name = ntpath.split(normalized)
        if not parent or not name:
            raise ValueError('Choose a file or a specific folder')
        return parent, name
    parent, name = value.rstrip('/').rsplit('/', 1)
    if not name or name in ('.', '..') or any(ord(c) < 32 for c in name):
        raise ValueError('Invalid file name')
    return parent or '/', name


def user_home():
    return _windows_home() if _os.name == 'nt' else str(Path.home())


def runtime_env():
    """No inherited credentials/proxies; retain only Windows loader essentials."""
    if _os.name != 'nt':
        return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}
    root = _windows_directory()
    home = user_home()
    drive, tail = ntpath.splitdrive(home)
    return {'SystemRoot': root, 'WINDIR': root, 'USERPROFILE': home,
            'HOMEDRIVE': drive, 'HOMEPATH': tail,
            'PATH': ntpath.join(root, 'System32') + ';' + root,
            'LANG': 'C.UTF-8', 'PYTHONUTF8': '1'}


def tunnel_helper(directory, legacy_hash):
    """Select only a bundled, manifest-pinned helper for this OS/architecture."""
    machine = platform.machine().lower()
    arch = 'arm64' if machine in ('arm64', 'aarch64') else 'x64' if machine in ('x86_64', 'amd64') else None
    system = {'linux': 'linux', 'darwin': 'macos', 'win32': 'windows'}.get(sys.platform)
    if not arch or not system:
        raise ValueError('The file connection does not support this system yet')
    key = system + '-' + arch
    names = {'linux-x64': 'cloudflared-linux-amd64', 'linux-arm64': 'cloudflared-linux-arm64',
             'windows-x64': 'cloudflared-windows-amd64.exe', 'windows-arm64': 'cloudflared-windows-arm64.exe',
             'macos-x64': 'cloudflared-darwin-amd64', 'macos-arm64': 'cloudflared-darwin-arm64'}
    manifest_path = Path(directory) / 'source.json'
    raw = manifest_path.read_bytes()
    if len(raw) > 65536:
        raise ValueError('Invalid connection helper data')
    manifest = json.loads(raw)
    platforms = manifest.get('platforms', {})
    if not isinstance(platforms, dict):
        raise ValueError('Invalid connection helper data')
    record = platforms.get(key)
    if record is None and key == 'linux-x64':
        record = {'file': names[key], 'sha256': legacy_hash}
    if (not isinstance(record, dict) or record.get('file') != names[key] or
            not re.fullmatch(r'[0-9a-f]{64}', str(record.get('sha256', '')))):
        raise ValueError('The bundled connection helper is missing for this system')
    binary = Path(directory) / record['file']
    if not binary.is_file() or binary.is_symlink() or hashlib.sha256(binary.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError('The bundled connection helper is not valid; reinstall VibeZ')
    return binary


if _os.name == 'nt':
    import msvcrt
    from ctypes import wintypes as W
    O_DIRECTORY = 0x40000000
    O_NOFOLLOW = 0x20000000
    O_NONBLOCK = 0x10000000
    _O_RDONLY, _O_WRONLY, _O_RDWR = _os.O_RDONLY, _os.O_WRONLY, _os.O_RDWR
    _nt = ctypes.WinDLL('ntdll', use_last_error=True)
    _k = ctypes.WinDLL('kernel32', use_last_error=True)
    _ULONG_PTR = ctypes.c_size_t
    class _GUID(ctypes.Structure):
        _fields_ = [('Data1', W.DWORD), ('Data2', W.WORD), ('Data3', W.WORD), ('Data4', ctypes.c_ubyte * 8)]
    _shell = ctypes.WinDLL('shell32', use_last_error=True)
    _ole = ctypes.WinDLL('ole32', use_last_error=True)
    _shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(_GUID), W.DWORD, W.HANDLE, ctypes.POINTER(W.LPWSTR)]
    _shell.SHGetKnownFolderPath.restype = W.LONG
    _ole.CoTaskMemFree.argtypes = [W.LPVOID]
    _k.GetDriveTypeW.argtypes = [W.LPCWSTR]
    _k.GetDriveTypeW.restype = W.UINT
    _k.GetWindowsDirectoryW.argtypes = [W.LPWSTR, W.UINT]
    _k.GetWindowsDirectoryW.restype = W.UINT

    def _windows_directory():
        buffer = ctypes.create_unicode_buffer(32768)
        length = _k.GetWindowsDirectoryW(buffer, len(buffer))
        if not length or length >= len(buffer):
            raise ValueError('The Windows runtime is not available')
        return buffer.value


    def _windows_home():
        folder = _GUID.from_buffer_copy(uuid.UUID('5e6c858f-0e22-4760-9afe-ea3317b67173').bytes_le)
        out = W.LPWSTR()
        if _shell.SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(out)) < 0:
            raise ValueError('The Windows user folder is not available')
        try: return out.value
        finally: _ole.CoTaskMemFree(ctypes.cast(out, W.LPVOID))

    class _UNICODE_STRING(ctypes.Structure):
        _fields_ = [('Length', W.USHORT), ('MaximumLength', W.USHORT), ('Buffer', W.LPWSTR)]
    class _OBJECT_ATTRIBUTES(ctypes.Structure):
        _fields_ = [('Length', W.ULONG), ('RootDirectory', W.HANDLE), ('ObjectName', ctypes.POINTER(_UNICODE_STRING)),
                    ('Attributes', W.ULONG), ('SecurityDescriptor', W.LPVOID), ('SecurityQualityOfService', W.LPVOID)]
    class _IOS_UNION(ctypes.Union):
        _fields_ = [('Status', W.LONG), ('Pointer', W.LPVOID)]
    class _IO_STATUS_BLOCK(ctypes.Structure):
        _fields_ = [('value', _IOS_UNION), ('Information', _ULONG_PTR)]
    class _FILE_BASIC_INFO(ctypes.Structure):
        _fields_ = [('CreationTime', ctypes.c_int64), ('LastAccessTime', ctypes.c_int64),
                    ('LastWriteTime', ctypes.c_int64), ('ChangeTime', ctypes.c_int64), ('FileAttributes', W.DWORD)]
    class _FILE_STANDARD_INFO(ctypes.Structure):
        _fields_ = [('AllocationSize', ctypes.c_int64), ('EndOfFile', ctypes.c_int64),
                    ('NumberOfLinks', W.DWORD), ('DeletePending', ctypes.c_ubyte), ('Directory', ctypes.c_ubyte)]
    class _FILE_ID_INFO(ctypes.Structure):
        _fields_ = [('VolumeSerialNumber', ctypes.c_uint64), ('FileId', ctypes.c_ubyte * 16)]
    class _RENAME_HEADER(ctypes.Structure):
        _fields_ = [('Flags', W.DWORD), ('RootDirectory', W.HANDLE), ('FileNameLength', W.DWORD), ('FileName', W.WCHAR)]
    _nt.NtCreateFile.argtypes = [ctypes.POINTER(W.HANDLE), W.ULONG, ctypes.POINTER(_OBJECT_ATTRIBUTES), ctypes.POINTER(_IO_STATUS_BLOCK),
                               W.LPVOID, W.ULONG, W.ULONG, W.ULONG, W.ULONG, W.LPVOID, W.ULONG]
    _nt.NtCreateFile.restype = W.LONG
    _nt.NtSetInformationFile.argtypes = [W.HANDLE, ctypes.POINTER(_IO_STATUS_BLOCK), W.LPVOID, W.ULONG, W.ULONG]
    _nt.NtSetInformationFile.restype = W.LONG
    _nt.NtQueryDirectoryFile.argtypes = [W.HANDLE, W.HANDLE, W.LPVOID, W.LPVOID, ctypes.POINTER(_IO_STATUS_BLOCK), W.LPVOID,
                                       W.ULONG, W.ULONG, ctypes.c_ubyte, W.LPVOID, ctypes.c_ubyte]
    _nt.NtQueryDirectoryFile.restype = W.LONG
    _nt.RtlNtStatusToDosError.argtypes = [W.LONG]
    _nt.RtlNtStatusToDosError.restype = W.ULONG
    _k.GetFileInformationByHandleEx.argtypes = [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD]
    _k.GetFileInformationByHandleEx.restype = W.BOOL
    _k.GetFileType.argtypes = [W.HANDLE]
    _k.GetFileType.restype = W.DWORD
    _k.CloseHandle.argtypes = [W.HANDLE]
    _k.CloseHandle.restype = W.BOOL
    _k.FlushFileBuffers.argtypes = [W.HANDLE]
    _k.FlushFileBuffers.restype = W.BOOL
    _k.GetCurrentProcess.restype = W.HANDLE
    _k.DuplicateHandle.argtypes = [W.HANDLE, W.HANDLE, W.HANDLE, ctypes.POINTER(W.HANDLE), W.DWORD, W.BOOL, W.DWORD]
    _k.DuplicateHandle.restype = W.BOOL
    _FILE_READ_DATA, _FILE_WRITE_DATA, _FILE_LIST_DIRECTORY = 1, 2, 1
    _FILE_READ_ATTRIBUTES, _FILE_WRITE_ATTRIBUTES, _DELETE, _SYNCHRONIZE = 0x80, 0x100, 0x10000, 0x100000
    _FILE_ATTRIBUTE_REPARSE_POINT, _FILE_ATTRIBUTE_DIRECTORY = 0x400, 0x10
    _FILE_ATTRIBUTE_READONLY = 1
    _FILE_OPEN, _FILE_CREATE, _FILE_OPEN_IF = 1, 2, 3
    _FILE_DIRECTORY_FILE, _FILE_NON_DIRECTORY_FILE = 1, 0x40
    _FILE_SYNCHRONOUS_IO_NONALERT, _FILE_OPEN_REPARSE_POINT = 0x20, 0x00200000
    _FSInfo = collections.namedtuple('FSInfo', 'st_dev st_ino st_mode st_size st_nlink st_mtime_ns st_ctime_ns st_mtime st_ctime')
    _registry = {}
    _registry_lock = threading.RLock()

    def _win_error():
        raise ctypes.WinError(ctypes.get_last_error())

    def _status(code):
        if code < 0:
            raise ctypes.WinError(_nt.RtlNtStatusToDosError(code))

    def _query(handle, kind, structure):
        out = structure()
        if not _k.GetFileInformationByHandleEx(handle, kind, ctypes.byref(out), ctypes.sizeof(out)):
            _win_error()
        return out

    def _info(handle, *, allow_reparse=False):
        if _k.GetFileType(handle) != 1:
            raise ValueError('Only regular disk files are allowed')
        basic = _query(handle, 0, _FILE_BASIC_INFO)
        standard = _query(handle, 1, _FILE_STANDARD_INFO)
        identity = _query(handle, 18, _FILE_ID_INFO)
        if standard.DeletePending:
            raise ValueError('The file is being deleted; try again')
        reparse = bool(basic.FileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT)
        if reparse and not allow_reparse:
            raise ValueError('Symbolic links, junctions and redirected files are not allowed')
        kind = _stat.S_IFLNK if reparse else _stat.S_IFDIR if standard.Directory else _stat.S_IFREG
        permission = 0o555 if basic.FileAttributes & _FILE_ATTRIBUTE_READONLY else 0o777 if standard.Directory else 0o666
        modified = (int(basic.LastWriteTime) - 116444736000000000) * 100
        changed = (int(basic.ChangeTime) - 116444736000000000) * 100
        return _FSInfo(int(identity.VolumeSerialNumber), int.from_bytes(bytes(identity.FileId), 'little'), kind | permission,
                       int(standard.EndOfFile), int(standard.NumberOfLinks), modified, changed, modified / 1e9, changed / 1e9)

    def _native_open(name, parent, access, disposition, directory=None, *, allow_reparse=False):
        # A relative ObjectName contains exactly one validated filename. There
        # are no intermediate components for FILE_OPEN_REPARSE_POINT to miss.
        if parent is not None:
            windows_component(name)
        buffer = ctypes.create_unicode_buffer(name)
        string = _UNICODE_STRING(len(name.encode('utf-16-le')), len(name.encode('utf-16-le')) + 2,
                                 ctypes.cast(buffer, W.LPWSTR))
        attributes = _OBJECT_ATTRIBUTES(ctypes.sizeof(_OBJECT_ATTRIBUTES), parent, ctypes.pointer(string), 0x40, None, None)
        out = W.HANDLE()
        ios = _IO_STATUS_BLOCK()
        options = _FILE_OPEN_REPARSE_POINT | _FILE_SYNCHRONOUS_IO_NONALERT
        if directory is True: options |= _FILE_DIRECTORY_FILE
        elif directory is False: options |= _FILE_NON_DIRECTORY_FILE
        # Retained directory handles deny delete sharing, pinning each ancestor
        # against junction/rename substitution while its capability is alive.
        share = 3 if directory is True else 7
        _status(_nt.NtCreateFile(ctypes.byref(out), access | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE,
                                ctypes.byref(attributes), ctypes.byref(ios), None, 0x80, share,
                                disposition, options, None, 0))
        try:
            info = _info(out, allow_reparse=allow_reparse)
            if directory is True and not _stat.S_ISDIR(info.st_mode):
                raise ValueError('This is not a regular folder')
            if directory is False and not allow_reparse and not _stat.S_ISREG(info.st_mode):
                raise ValueError('This is not a regular file')
            return out.value, info
        except BaseException:
            _k.CloseHandle(out)
            raise

    def _adopt(handle, flags, info):
        try:
            fd = msvcrt.open_osfhandle(handle, (flags & (_os.O_WRONLY | _os.O_RDWR | _os.O_APPEND)) | _os.O_BINARY)
        except BaseException:
            raise
        with _registry_lock:
            _registry[fd] = (handle, info.st_dev, info.st_ino)
        return fd

    def _reopen_directory(fd):
        parent, identity = _handle(fd, directory=True)
        # A relative empty NT name reopens the retained directory itself with
        # a fresh file object/cursor. ReOpenFile requires a CreateFile handle;
        # our capabilities were opened by NtCreateFile. No user-supplied name
        # reaches this path, and ordinary relative names remain validated.
        buffer = ctypes.create_unicode_buffer('')
        string = _UNICODE_STRING(0, 2, ctypes.cast(buffer, W.LPWSTR))
        attributes = _OBJECT_ATTRIBUTES(ctypes.sizeof(_OBJECT_ATTRIBUTES), parent, ctypes.pointer(string), 0x40, None, None)
        out = W.HANDLE(); ios = _IO_STATUS_BLOCK()
        options = _FILE_DIRECTORY_FILE | _FILE_OPEN_REPARSE_POINT | _FILE_SYNCHRONOUS_IO_NONALERT
        _status(_nt.NtCreateFile(ctypes.byref(out), _FILE_LIST_DIRECTORY | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE,
                                ctypes.byref(attributes), ctypes.byref(ios), None, 0x80, 3,
                                _FILE_OPEN, options, None, 0))
        try:
            info = _info(out)
            if not _stat.S_ISDIR(info.st_mode) or info[:2] != identity[:2]:
                raise ValueError('The folder capability has changed')
            return out.value, info
        except BaseException:
            _k.CloseHandle(out)
            raise

    def _handle(fd, *, directory=False):
        if not isinstance(fd, int):
            raise ValueError('Invalid file capability')
        with _registry_lock:
            saved = _registry.get(fd)
        if saved is None:
            raise ValueError('File handle does not belong to this workspace')
        try:
            handle = msvcrt.get_osfhandle(fd)
        except OSError:
            raise ValueError('Bestandshandle is gesloten') from None
        if handle != saved[0]:
            raise ValueError('File handle was replaced')
        info = _info(handle)
        if (info.st_dev, info.st_ino) != saved[1:]:
            raise ValueError('File handle has changed')
        if directory and not _stat.S_ISDIR(info.st_mode):
            raise ValueError('This is not a folder capability')
        return handle, info

    def _absolute_open(path, access, disposition, directory=None, *, allow_reparse=False):
        normalized, drive, parts = windows_absolute(path)
        if _k.GetDriveTypeW(drive) == 4:
            raise ValueError('Network drives are not opened as a local workspace')
        current, root_info = _native_open('\\??\\' + drive, None, _FILE_LIST_DIRECTORY, _FILE_OPEN, True)
        try:
            if not parts:
                if disposition != _FILE_OPEN or directory is False:
                    raise ValueError('Invalid operation on a drive root')
                return current, root_info
            for component in parts[:-1]:
                child, _ = _native_open(component, current, _FILE_LIST_DIRECTORY, _FILE_OPEN, True)
                _k.CloseHandle(current); current = child
            result = _native_open(parts[-1], current, access, disposition, directory, allow_reparse=allow_reparse)
            return result
        finally:
            if parts: _k.CloseHandle(current)

    def open(path, flags, mode=0o777, *, dir_fd=None):
        directory = bool(flags & O_DIRECTORY)
        writing = bool(flags & (_os.O_WRONLY | _os.O_RDWR))
        access = _FILE_LIST_DIRECTORY if directory else (_FILE_WRITE_DATA if writing else _FILE_READ_DATA)
        if flags & _os.O_RDWR: access |= _FILE_READ_DATA
        disposition = _FILE_CREATE if flags & _os.O_CREAT and flags & _os.O_EXCL else _FILE_OPEN_IF if flags & _os.O_CREAT else _FILE_OPEN
        parent = _handle(dir_fd, directory=True)[0] if dir_fd is not None else None
        handle, info = (_native_open(_os.fspath(path), parent, access, disposition, directory) if parent is not None
                        else _absolute_open(path, access, disposition, directory))
        try:
            if writing and info.st_nlink != 1:
                raise ValueError('Writing to hard links is not allowed')
            if flags & _os.O_TRUNC:
                size = ctypes.c_int64(0); ios = _IO_STATUS_BLOCK()
                _status(_nt.NtSetInformationFile(handle, ctypes.byref(ios), ctypes.byref(size), ctypes.sizeof(size), 20))
            return _adopt(handle, flags, info)
        except BaseException:
            _k.CloseHandle(handle)
            raise

    def close(fd):
        with _registry_lock: _registry.pop(fd, None)
        return _os.close(fd)

    def dup(fd):
        handle, info = _handle(fd)
        new = W.HANDLE(); process = _k.GetCurrentProcess()
        if not _k.DuplicateHandle(process, handle, process, ctypes.byref(new), 0, False, 2): _win_error()
        try:
            return _adopt(new.value, _os.O_RDONLY, info)
        except BaseException:
            _k.CloseHandle(new)
            raise

    def fstat(fd):
        return _handle(fd)[1]

    def read(fd, size):
        _handle(fd)
        return _os.read(fd, size)

    def write(fd, data):
        _, info = _handle(fd)
        if not _stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Writing to links is not allowed')
        return _os.write(fd, data)

    class _FileProxy:
        def __init__(self, stream, fd): self._stream, self._fd = stream, fd
        def __getattr__(self, key): return getattr(self._stream, key)
        def __enter__(self): return self
        def __exit__(self, *exc): self.close()
        def __iter__(self): return iter(self._stream)
        def close(self):
            with _registry_lock: _registry.pop(self._fd, None)
            self._stream.close()

    def fdopen(fd, *args, **kwargs):
        _handle(fd)
        return _FileProxy(_os.fdopen(fd, *args, **kwargs), fd)

    def stat(path, *, dir_fd=None, follow_symlinks=True):
        if isinstance(path, int): return fstat(path)
        handle, info = (_native_open(_os.fspath(path), _handle(dir_fd, directory=True)[0], _FILE_READ_ATTRIBUTES, _FILE_OPEN,
                                      allow_reparse=not follow_symlinks) if dir_fd is not None
                        else _absolute_open(path, _FILE_READ_ATTRIBUTES, _FILE_OPEN, allow_reparse=not follow_symlinks))
        _k.CloseHandle(handle)
        return info

    def fsync(fd):
        handle, info = _handle(fd)
        if _stat.S_ISDIR(info.st_mode):
            # Windows does not expose POSIX directory-fsync. File contents are
            # flushed before an atomic handle-relative namespace operation.
            return
        if not _k.FlushFileBuffers(handle): _win_error()

    def fchmod(fd, mode):
        # POSIX rwx bits have no Windows DACL equivalent. Preserve the DACL
        # inherited when the new staged entry was created; never broaden it.
        _handle(fd)
        return None

    class _Entry:
        def __init__(self, parent, name): self._parent, self.name = parent, name
        def stat(self, *, follow_symlinks=True): return stat(self.name, dir_fd=self._parent, follow_symlinks=follow_symlinks)
        def is_file(self, *, follow_symlinks=True): return _stat.S_ISREG(self.stat(follow_symlinks=follow_symlinks).st_mode)
        def is_dir(self, *, follow_symlinks=True): return _stat.S_ISDIR(self.stat(follow_symlinks=follow_symlinks).st_mode)
        def is_symlink(self): return _stat.S_ISLNK(self.stat(follow_symlinks=False).st_mode)

    class _Scan:
        def __init__(self, path):
            if isinstance(path, int):
                # Reopen the retained object, not its pathname. DuplicateHandle
                # shares an enumeration cursor and cannot back two scans safely.
                handle, info = _reopen_directory(path)
                try:
                    self.fd = _adopt(handle, _os.O_RDONLY, info)
                except BaseException:
                    _k.CloseHandle(handle)
                    raise
            else:
                self.fd = open(path, O_DIRECTORY | O_NOFOLLOW)
            self.pending = collections.deque(); self.first = True; self.done = False
        def __enter__(self): return self
        def __exit__(self, *exc): self.close()
        def __iter__(self): return self
        def close(self):
            if self.fd is not None: close(self.fd); self.fd = None
        def __next__(self):
            while not self.pending:
                if self.done or self.fd is None: raise StopIteration
                buf = ctypes.create_string_buffer(65536); ios = _IO_STATUS_BLOCK()
                code = _nt.NtQueryDirectoryFile(_handle(self.fd, directory=True)[0], None, None, None, ctypes.byref(ios),
                                                buf, len(buf), 1, False, None, self.first)
                self.first = False
                if code & 0xffffffff == 0x80000006: self.done = True; self.close(); raise StopIteration
                _status(code)
                raw = buf.raw[:int(ios.Information)]; offset = 0
                while True:
                    if offset + 64 > len(raw): raise ValueError('Invalid folder data')
                    next_offset = int.from_bytes(raw[offset:offset+4], 'little')
                    length = int.from_bytes(raw[offset+60:offset+64], 'little')
                    end = offset + 64 + length
                    if length % 2 or length > 510 or end > len(raw): raise ValueError('Invalid file name data')
                    name = raw[offset+64:end].decode('utf-16-le')
                    if name not in ('.', '..'): self.pending.append(_Entry(self.fd, name))
                    if not next_offset: break
                    if next_offset < 64 + length or offset + next_offset <= offset: raise ValueError('Invalid folder order')
                    offset += next_offset
            return self.pending.popleft()

    def scandir(path='.'): return _Scan(path)

    def listdir(path='.'):
        with scandir(path) as entries: return [entry.name for entry in entries]

    def _relative_or_absolute(path, dir_fd, access, *, directory=None):
        if dir_fd is not None:
            return _native_open(_os.fspath(path), _handle(dir_fd, directory=True)[0], access, _FILE_OPEN, directory)
        return _absolute_open(path, access, _FILE_OPEN, directory)

    def _set_name(source, target, src_dir_fd, dst_dir_fd, *, replace=False, link=False):
        target_parent = None
        if dst_dir_fd is None:
            parent_path, target = split_absolute(target)
            target_parent = open(parent_path, O_DIRECTORY | O_NOFOLLOW)
            dst_dir_fd = target_parent
        try:
            windows_component(_os.fspath(target))
            handle, info = _relative_or_absolute(source, src_dir_fd, _DELETE | (_FILE_WRITE_ATTRIBUTES if link else 0))
            try:
                if link and not _stat.S_ISREG(info.st_mode): raise ValueError('Hard links to folders are not allowed')
                encoded = target.encode('utf-16-le')
                offset = _RENAME_HEADER.FileName.offset
                buf = ctypes.create_string_buffer(offset + len(encoded) + 2)
                header = _RENAME_HEADER.from_buffer(buf)
                header.Flags = int(replace); header.RootDirectory = _handle(dst_dir_fd, directory=True)[0]; header.FileNameLength = len(encoded)
                ctypes.memmove(ctypes.addressof(buf) + offset, encoded, len(encoded))
                ios = _IO_STATUS_BLOCK()
                _status(_nt.NtSetInformationFile(handle, ctypes.byref(ios), buf, len(buf), 11 if link else 10))
            finally: _k.CloseHandle(handle)
        finally:
            if target_parent is not None: close(target_parent)

    def replace(source, target, *, src_dir_fd=None, dst_dir_fd=None):
        return _set_name(source, target, src_dir_fd, dst_dir_fd, replace=True)

    def link(source, target, *, src_dir_fd=None, dst_dir_fd=None, follow_symlinks=True):
        return _set_name(source, target, src_dir_fd, dst_dir_fd, link=True)

    def rename_noreplace(root, source, target, target_root=None):
        return _set_name(source, target, root, root if target_root is None else target_root)

    def mkdir(path, mode=0o777, *, dir_fd=None):
        if dir_fd is not None:
            handle, _ = _native_open(_os.fspath(path), _handle(dir_fd, directory=True)[0], _FILE_LIST_DIRECTORY,
                                      _FILE_CREATE, True)
        else:
            handle, _ = _absolute_open(path, _FILE_LIST_DIRECTORY, _FILE_CREATE, True)
        _k.CloseHandle(handle)

    def _remove(path, dir_fd, directory):
        handle, _ = _relative_or_absolute(path, dir_fd, _DELETE, directory=directory)
        try:
            delete = ctypes.c_ubyte(1); ios = _IO_STATUS_BLOCK()
            _status(_nt.NtSetInformationFile(handle, ctypes.byref(ios), ctypes.byref(delete), ctypes.sizeof(delete), 13))
        finally: _k.CloseHandle(handle)

    def unlink(path, *, dir_fd=None): return _remove(path, dir_fd, False)
    def rmdir(path, *, dir_fd=None): return _remove(path, dir_fd, True)
    def fpathconf(fd, name):
        _handle(fd, directory=True)
        if name != 'PC_NAME_MAX': raise ValueError('Onbekende naamgrens')
        # Import's UTF-8 truncation limit is conservative for UTF-16 names.
        return 255


if _os.name != 'nt':
    def rename_noreplace(root, source, target, target_root=None):
        """Publish one complete staged entry without links or overwriting."""
        for name in (source, target):
            if not isinstance(name, str) or name in ('', '.', '..') or '/' in name or '\0' in name:
                raise ValueError('Invalid file name for saving')
        libc = ctypes.CDLL(None, use_errno=True)
        darwin = sys.platform == 'darwin'
        rename = getattr(libc, 'renameatx_np' if darwin else 'renameat2', None)
        if rename is None:
            raise ValueError('Safely saving a new file is not available here')
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        target_root = root if target_root is None else target_root
        code = _native_rename_noreplace(rename, root, source, target_root, target, 4 if darwin else 1)
        if code in (errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP):
            # NFS, sshfs, ntfs-3g and other FUSE mounts refuse the no-replace
            # flag. Claim the free name exclusively, then move the staged entry
            # over our own empty claim: an existing entry is never overwritten.
            info = _os.stat(source, dir_fd=root, follow_symlinks=False)
            if _stat.S_ISDIR(info.st_mode):
                _os.mkdir(target, 0o700, dir_fd=target_root)
                undo = _os.rmdir
            else:
                _os.close(_os.open(target, _os.O_WRONLY | _os.O_CREAT | _os.O_EXCL | _os.O_NOFOLLOW, 0o600, dir_fd=target_root))
                undo = _os.unlink
            try:
                _os.rename(source, target, src_dir_fd=root, dst_dir_fd=target_root)
            except BaseException:
                with contextlib.suppress(OSError): undo(target, dir_fd=target_root)
                raise
            return
        if code:
            raise OSError(code, _os.strerror(code))

    def _native_rename_noreplace(rename, root, source, target_root, target, flag):
        if rename(root, _os.fsencode(source), target_root, _os.fsencode(target), flag) != 0:
            return ctypes.get_errno() or errno.EIO
        return 0

    def fsync(fd):
        """Flush to disk where the file system can; some FUSE and network mounts cannot."""
        try:
            _os.fsync(fd)
        except OSError as error:
            if error.errno not in (errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP): raise


def _flatpak_application():
    """Read the immutable sandbox marker, never an environment assertion."""
    try:
        fd = _os.open('/.flatpak-info', _os.O_RDONLY | _os.O_NOFOLLOW | _os.O_NONBLOCK)
        try:
            info = _os.fstat(fd)
            if not _stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                return False
            raw = _os.read(fd, 65537)
            if len(raw) > 65536:
                return False
            marker = configparser.ConfigParser(interpolation=None)
            marker.read_string(raw.decode('utf-8'))
            return marker.get('Application', 'name', fallback='') == 'nl.lecomputeur.vibez4.alpha'
        finally:
            _os.close(fd)
    except (OSError, UnicodeError, configparser.Error):
        return False


def _directory_parts(path):
    anchor, parts = absolute_parts(path)
    if _os.name == 'nt' or sys.platform != 'linux':
        return anchor, parts
    # Flatpak exposes precisely this runtime-dir alias to its app-scoped portal
    # mount. Do not resolve user-selected symlinks or any other runtime entry.
    alias = ['run', 'user', str(_os.getuid()), 'doc']
    if parts[:4] != alias:
        return anchor, parts
    parent = _os.open('/', _os.O_RDONLY | _os.O_DIRECTORY | _os.O_NOFOLLOW)
    try:
        for part in alias[:-1]:
            child = _os.open(part, _os.O_RDONLY | _os.O_DIRECTORY | _os.O_NOFOLLOW, dir_fd=parent)
            _os.close(parent)
            parent = child
        info = _os.stat('doc', dir_fd=parent, follow_symlinks=False)
        if not _stat.S_ISLNK(info.st_mode):
            return anchor, parts
        target = _os.readlink('doc', dir_fd=parent)
        if target not in ('../../flatpak/doc', '/run/flatpak/doc') or not _flatpak_application():
            raise ValueError('The document portal folder is not available. Choose the files again.')
    finally:
        _os.close(parent)
    # Walk the known mount directly with no-follow handles. A concurrent alias
    # replacement cannot redirect this open to another path or another user.
    return '/', ['run', 'flatpak', 'doc', *parts[4:]]


def open_directory(path):
    anchor, parts = _directory_parts(path)
    fd = open(anchor, O_DIRECTORY | O_NOFOLLOW | _os.O_RDONLY) if _os.name == 'nt' else _os.open(anchor, _os.O_RDONLY | _os.O_DIRECTORY | _os.O_NOFOLLOW)
    try:
        for part in parts:
            child = open(part, _os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW, dir_fd=fd) if _os.name == 'nt' else _os.open(part, _os.O_RDONLY | _os.O_DIRECTORY | _os.O_NOFOLLOW, dir_fd=fd)
            close(fd) if _os.name == 'nt' else _os.close(fd)
            fd = child
        return fd
    except BaseException:
        close(fd) if _os.name == 'nt' else _os.close(fd)
        raise


def reject_broad_root(fd, root):
    if _os.name != 'nt': return
    normalized, _, parts = windows_absolute(root)
    if not parts: raise ValueError('Choose a specific project folder, not a whole drive')
    home_path = user_home()
    if not is_absolute(home_path):
        # A remote Windows profile cannot equal an allowed local drive root.
        return
    home = open_directory(home_path)
    try:
        if fstat(fd)[:2] == fstat(home)[:2]:
            raise ValueError('Choose a specific project folder, not your whole home folder')
    finally: close(home)


def same_root_name(path):
    return canonical_root(path)


def atomic_exchange_available():
    return _os.name != 'nt'
