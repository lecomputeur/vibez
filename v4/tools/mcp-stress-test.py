#!/usr/bin/python3
"""Stress and robustness test of the local MCP file server, apart from Mistral.

Starts the real server of backend/web_connector.py on 127.0.0.1 against a
generated folder full of awkward files, and talks to it over real HTTP the way
a remote client (or a hostile one) would. Nothing leaves the computer: no
tunnel is started and no Mistral account is used.

Every reply is held to the same rules:
  * the server answers (no dropped connection, no hang) and never with a 5xx;
  * a 200 body is JSON, a JSON-RPC reply names the request id;
  * nothing from outside the linked folder, no absolute path and no access key
    ever shows up in a reply.

  python3 tools/mcp-stress-test.py [--seconds 60] [--seed N] [--output DIR]
"""
import argparse, base64, contextlib, http.client, importlib.util, io, json, os, random, socket, stat, sys, tempfile, threading, time, traceback, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('web_stress', ROOT / 'backend/web_connector.py')
web = importlib.util.module_from_spec(spec); spec.loader.exec_module(web)
A = 'cace260d-d95d-4859-b45b-f56f185f15da'
B = 'code-229ee257-1234-4567-890a-123456789abc'
CANARY = 'CANARY-outside-the-folder-7f3a91'
LEGACY = web.VERSIONS
MODERN = web.MODERN_VERSIONS[0]
META = web.META
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


class Fail(Exception):
    pass


if os.name == 'nt':
    # The fixtures and checks mean exact UTF-8 bytes, also where the system
    # default is another code page and line ending.
    import pathlib
    _write_text, _read_text = pathlib.Path.write_text, pathlib.Path.read_text
    def _write(self, data, encoding='utf-8', errors=None, newline=''): return _write_text(self, data, encoding, errors, newline)
    def _read(self, encoding='utf-8', errors=None): return _read_text(self, encoding, errors)
    pathlib.Path.write_text, pathlib.Path.read_text = _write, _read


def open_handles():
    """How many files, sockets and the like this process holds open."""
    if os.path.isdir('/proc/self/fd'): return len(os.listdir('/proc/self/fd'))
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        count = wintypes.DWORD()
        return count.value if kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(count)) else 0
    return len(os.listdir('/dev/fd'))

class Bench:
    def __init__(self, seed):
        self.random = random.Random(seed)
        self.tmp = tempfile.TemporaryDirectory(prefix='vibez-mcp-stress-')
        self.root = Path(self.tmp.name)
        self.outside = self.root / 'outside'; self.outside.mkdir()
        (self.outside / 'secret.txt').write_text(CANARY)
        self.folder = self.root / 'linked'; self.folder.mkdir()
        self.other = self.root / 'other'; self.other.mkdir(); (self.other / 'b.txt').write_text('Only B ' + CANARY.replace('outside', 'otherproject'))
        self.events = []
        self.failures = []; self.checks = 0; self.groups = {}
        self.group = 'setup'
        self.make_files()
        self.c = web.Connector(self.events.append, self.root / 'private', approval_wait=0)
        # Only the project that is open in VibeZ is reachable; B is linked but not open.
        self.c.select({'id': B, 'name': 'Other project'}); self.c.link(B, self.other)
        self.c.select({'id': A, 'name': 'Stress project'}); self.c.link(A, self.folder); self.c.enable(A, True)
        self.port = self.c.server.server_port
        self.forbidden = [CANARY, str(self.root), 'otherproject']
        self.id = 0

    def activate(self, key):
        self.c.select({'id': key, 'name': 'Stress project' if key == A else 'Other project'}); self.c.enable(key, True, manual=True)

    def close(self):
        try: self.c.close()
        finally:
            for path in self.folder.rglob('*'):
                try:
                    if not path.is_symlink(): os.chmod(path, 0o700)
                except OSError: pass
            try: self.tmp.cleanup()
            except OSError: pass  # Windows keeps a folder while a scanner still has it open

    # ---- fixture -------------------------------------------------------
    def office(self, name, inner, text='<x/>', broken=None):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr(inner, text)
        raw = data.getvalue()
        if broken == 'cut': raw = raw[:len(raw) // 2]
        (self.folder / name).write_bytes(raw)

    def make_files(self):
        f = self.folder
        # Not every system has every kind of entry (Windows: no pipes, sockets, odd names).
        skip = contextlib.suppress(OSError, AttributeError, NotImplementedError)
        (f / 'plain.txt').write_text('Hello plain\n')
        (f / 'empty.txt').write_bytes(b'')
        (f / 'crlf.txt').write_bytes(b'one\r\ntwo\r\n')
        (f / 'bom.txt').write_bytes(b'\xef\xbb\xbfwith bom')
        (f / 'utf16.txt').write_bytes('utf sixteen'.encode('utf-16'))
        (f / 'latin1.txt').write_bytes('caf\xe9'.encode('latin-1'))
        (f / 'nul.txt').write_bytes(b'a\x00b')
        (f / 'binary.bin').write_bytes(bytes(range(256)) * 8)
        (f / 'longline.txt').write_text('x' * 200_000)
        (f / 'big.txt').write_bytes(b'y' * (12 * 1024 * 1024))
        (f / 'Zażółć gęślą jaźń.txt').write_text('polski')
        (f / 'café nfd.txt').write_text('nfd')
        (f / 'emoji 😀.txt').write_text('emoji')
        with skip: (f / 'new\nline.txt').write_text('newline in name')
        with skip: (f / ' leading space.txt').write_text('space')
        with skip: (f / 'trailing dot.').write_text('dot')
        (f / '.hidden').write_text('hidden file')
        (f / '.env').write_text('SECRET=inside-hidden')
        with skip: (f / ('a' * 200)).write_text('long name')
        deep = f
        for n in range(40): deep = deep / ('d%d' % n)
        deep.mkdir(parents=True); (deep / 'deep.txt').write_text('deep')
        many = f / 'many'; many.mkdir()
        for n in range(3000): (many / ('f%04d.txt' % n)).write_text(str(n))
        (f / 'sub').mkdir(); (f / 'sub' / 'inner.txt').write_text('inner')
        with skip: os.symlink(self.outside / 'secret.txt', f / 'link-out.txt')
        with skip: os.symlink(self.outside, f / 'dir-out')
        with skip: os.symlink('/etc/passwd', f / 'link-passwd')
        with skip: os.symlink('/dev/zero', f / 'link-zero')
        with skip:
            os.symlink('loop-b', f / 'loop-a')
            os.symlink('loop-a', f / 'loop-b')
        with skip: os.symlink('plain.txt', f / 'link-in.txt')
        with skip: os.symlink('.', f / 'self-dir')
        with skip: os.symlink('missing-target', f / 'dangling')
        with skip:
            (f / 'hard-src.txt').write_text('hard linked\n')
            os.link(f / 'hard-src.txt', f / 'hardlink-in.txt')
        with skip: os.mkfifo(f / 'fifo')
        with skip:
            s = socket.socket(socket.AF_UNIX)
            s.bind(str(f / 'sock'))
            s.close()
        with skip:
            (f / 'noperm.txt').write_text('no permission')
            os.chmod(f / 'noperm.txt', 0)
        with skip:
            (f / 'nopermdir').mkdir()
            (f / 'nopermdir' / 'x.txt').write_text('x')
            os.chmod(f / 'nopermdir', 0)
        (f / 'ok.png').write_bytes(PNG)
        (f / 'cut.png').write_bytes(PNG[:20])
        (f / 'text-as.png').write_text('not an image')
        (f / 'png-as.txt').write_bytes(PNG)
        (f / 'empty.png').write_bytes(b'')
        (f / 'huge.png').write_bytes(PNG + b'\0' * (11 * 1024 * 1024))
        (f / 'fake.jpg').write_bytes(b'\xff\xd8\xff' + b'\0' * 50)
        (f / 'fake.gif').write_bytes(b'GIF89a' + b'\0' * 5)
        (f / 'fake.webp').write_bytes(b'RIFF\x00\x00\x00\x00WEBP')
        (f / 'image.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
        xml = '<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text><text:p>Odt words</text:p></office:text></office:body></office:document-content>'
        self.office('good.odt', 'content.xml', xml)
        self.office('cut.odt', 'content.xml', xml, broken='cut')
        self.office('nocontent.odt', 'other.xml', xml)
        self.office('badxml.odt', 'content.xml', '<a><b></a>')
        self.office('xxe.odt', 'content.xml', '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY e SYSTEM "file://%s">]><d>&e;</d>' % (self.outside / 'secret.txt'))
        self.office('bomb.odt', 'content.xml', '<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa">' + ''.join('<!ENTITY %s "%s">' % (chr(98 + n), ('&%s;' % chr(97 + n)) * 10) for n in range(9)) + ']><l>&j;</l>')
        self.office('zipbomb.odt', 'content.xml', '<a>' + 'A' * (300 * 1024 * 1024 // 10) + '</a>')
        self.office('deepxml.odt', 'content.xml', '<a>' * 200000 + '</a>' * 200000)
        for ext, inner in (('docx', 'word/document.xml'), ('xlsx', 'xl/workbook.xml'), ('ods', 'content.xml'), ('pptx', 'ppt/presentation.xml'), ('odp', 'content.xml')):
            self.office('junk.' + ext, inner, '<a>junk</a>')
            self.office('cut.' + ext, inner, '<a>junk</a>', broken='cut')
            (f / ('text.' + ext)).write_text('plain text with office name')
            (f / ('empty.' + ext)).write_bytes(b'')
        (f / 'notzip.odt').write_bytes(b'PK\x03\x04' + os.urandom(2000))
        (f / 'old.doc').write_bytes(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + os.urandom(3000))
        (f / 'paper.pdf').write_bytes(b'%PDF-1.4\n' + os.urandom(3000))
        with zipfile.ZipFile(f / 'slip.odt', 'w') as z:
            z.writestr('../../outside/planted.txt', 'x'); z.writestr('content.xml', '<a>slip</a>')

    # ---- transport -----------------------------------------------------
    def raw(self, method, path, body=None, headers=None, timeout=30):
        """One HTTP exchange. Returns (status, headers, bytes) or raises Fail when the server does not answer."""
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=timeout)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            r = conn.getresponse(); data = r.read()
            return r.status, dict(r.getheaders()), data
        except (OSError, http.client.HTTPException) as error:
            raise Fail('no HTTP answer: %s' % type(error).__name__)
        finally:
            conn.close()

    def headers(self, key=A, version=LEGACY[0], sid=None, extra=None, token=None):
        h = {'Authorization': 'Bearer ' + (self.c.projects[key]['token'] if token is None else token), 'Content-Type': 'application/json',
             'Accept': 'application/json, text/event-stream'}
        if version: h['MCP-Protocol-Version'] = version
        if sid: h['Mcp-Session-Id'] = sid
        h.update(extra or {})
        return h

    def judge(self, label, status, headers, data, allow=(), expect_id=None):
        text = data.decode('utf-8', 'replace') + json.dumps(headers)
        if status == 503 and b'"busy"' in data: raise Fail('%s: server busy' % label)
        if status >= 500: raise Fail('%s: status %s' % (label, status))
        for word in self.forbidden + [self.c.projects[A]['token'], self.c.projects[B]['token']]:
            if word in text and word not in allow: raise Fail('%s: reply leaks %r' % (label, word[:24]))
        parsed = None
        if data and headers.get('Content-Type') == 'application/json':
            try: parsed = json.loads(data)
            except ValueError: raise Fail('%s: body is not JSON' % label)
        if status == 200 and expect_id is not None:
            if not isinstance(parsed, dict) or parsed.get('id') != expect_id or parsed.get('jsonrpc') != '2.0' or ('result' in parsed) == ('error' in parsed):
                raise Fail('%s: not a JSON-RPC reply for id %r: %s' % (label, expect_id, str(parsed)[:120]))
        return parsed

    def check(self, label, fn):
        """Run one check; a failure is recorded with its label and the run goes on."""
        self.checks += 1
        g = self.groups.setdefault(self.group, [0, 0]); g[0] += 1
        try:
            return fn()
        except Fail as error:
            g[1] += 1; self.failures.append({'group': self.group, 'check': label[:200], 'problem': str(error)[:300]})
        except Exception as error:  # a fault of this script counts too: it must be looked at
            g[1] += 1; self.failures.append({'group': self.group, 'check': label[:200], 'problem': 'script: ' + ''.join(traceback.format_exception_only(type(error), error)).strip()[:300]})
        return None

    def post(self, msg, label, key=A, version=LEGACY[0], sid=None, extra=None, timeout=30, allow=()):
        body = json.dumps(msg).encode()
        status, headers, data = self.raw('POST', '/mcp/' + key, body, self.headers(key, version, sid, extra), timeout)
        parsed = self.judge(label, status, headers, data, allow, msg.get('id') if isinstance(msg, dict) and status == 200 else None)
        return status, headers, parsed

    def next_id(self):
        self.id += 1; return self.id

    def session(self, key=A, version=LEGACY[0]):
        status, headers, parsed = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'initialize',
                                             'params': {'protocolVersion': version, 'capabilities': {}, 'clientInfo': {'name': 'stress', 'version': '1'}}}, 'initialize', key, version)
        if status != 200 or 'Mcp-Session-Id' not in headers: raise Fail('initialize failed: %s' % status)
        return headers['Mcp-Session-Id']

    def call(self, sid, name, args, label=None, key=A, timeout=30, allow=()):
        """Legacy tools/call. Returns (is_error, value)."""
        label = label or '%s %r' % (name, args)
        status, _, parsed = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'tools/call', 'params': {'name': name, 'arguments': args}}, label, key, sid=sid, timeout=timeout, allow=allow)
        if status != 200: raise Fail('%s: status %s' % (label, status))
        result = parsed.get('result')
        if not isinstance(result, dict) or not isinstance(result.get('content'), list) or not isinstance(result.get('isError'), bool):
            raise Fail('%s: malformed tool result %s' % (label, str(parsed)[:160]))
        first = result['content'][0] if result['content'] else {}
        value = first
        if first.get('type') == 'text':
            try: value = json.loads(first['text'])
            except ValueError: raise Fail('%s: tool text is not JSON' % label)
        return result['isError'], value

    def modern(self, method, params=None, label=None, key=A, extra=None, name=None):
        params = dict(params or {}); params['_meta'] = {META + 'protocolVersion': MODERN, META + 'clientCapabilities': {}}
        h = {'Mcp-Method': method}
        if name: h['Mcp-Name'] = name
        h.update(extra or {})
        return self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': method, 'params': params}, label or 'modern ' + method, key, MODERN, extra=h)

    def alive(self, label='still answering'):
        def ping():
            start = time.monotonic(); sid = self.session()
            status, _, _ = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'ping'}, 'ping', sid=sid, timeout=10)
            self.raw('DELETE', '/mcp/' + A, None, self.headers(sid=sid))
            if status != 200: raise Fail('ping status %s' % status)
            if time.monotonic() - start > 5: raise Fail('server slow after test: %.1fs' % (time.monotonic() - start))
        self.check(label, ping)

    # ---- groups --------------------------------------------------------
    def g_protocol(self):
        self.group = 'protocol'
        for version in LEGACY:
            def cycle(version=version):
                sid = self.session(version=version)
                status, _, _ = self.post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, 'initialized', version=version, sid=sid)
                if status != 202: raise Fail('notification answered %s' % status)
                _, _, tools = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'tools/list'}, 'tools/list', version=version, sid=sid)
                names = [t['name'] for t in tools['result']['tools']]
                for t in tools['result']['tools']:
                    if not isinstance(t.get('inputSchema'), dict) or t['inputSchema'].get('type') != 'object' or not t.get('description'): raise Fail('tool %s has no usable schema' % t.get('name'))
                for name in ('list_directory', 'read_file', 'write_file', 'workspace_overview', 'create_document', 'change_status', 'read_image'):
                    if name not in names: raise Fail('tool %s missing' % name)
                error, value = self.call(sid, 'list_directory', {'path': '.'})
                if error: raise Fail('list_directory . fails: %s' % value)
                error, value = self.call(sid, 'read_file', {'path': 'plain.txt'})
                if error or 'Hello plain' not in json.dumps(value): raise Fail('read_file plain.txt: %s' % str(value)[:100])
                error, value = self.call(sid, 'workspace_overview', {})
                if error: raise Fail('workspace_overview fails: %s' % value)
                error, value = self.call(sid, 'read_image', {'path': 'ok.png'})
                if error or value.get('type') != 'image' or base64.b64decode(value.get('data', '')) != PNG: raise Fail('read_image ok.png wrong: %s' % str(value)[:100])
                status, _, _ = self.raw('DELETE', '/mcp/' + A, None, self.headers(version=version, sid=sid))
                if status != 204: raise Fail('DELETE answered %s' % status)
                status, _, _ = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'ping'}, 'ping after delete', version=version, sid=sid)
                if status != 404: raise Fail('deleted session answered %s' % status)
            self.check('legacy cycle ' + version, cycle)
        def modern():
            status, _, d = self.modern('server/discover')
            if status != 200 or MODERN not in d['result']['supportedVersions'] or d['result'].get('resultType') != 'complete': raise Fail('discover: %s %s' % (status, str(d)[:120]))
            status, _, d = self.modern('tools/list')
            if status != 200 or len(d['result']['tools']) < 7: raise Fail('modern tools/list: %s' % status)
            for name, args in (('list_directory', {'path': '.'}), ('read_file', {'path': 'plain.txt'}), ('workspace_overview', {}), ('read_image', {'path': 'ok.png'})):
                status, _, d = self.modern('tools/call', {'name': name, 'arguments': args}, name=name)
                if status != 200 or d['result'].get('isError') is not False: raise Fail('modern %s: %s %s' % (name, status, str(d)[:160]))
        self.check('modern cycle', modern)
        def other_methods():
            for method in ('GET', 'HEAD', 'OPTIONS'):
                status, headers, data = self.raw(method, '/mcp/' + A, None, self.headers(extra={'Accept': 'text/event-stream'}), timeout=40)
                self.judge(method, status, headers, data)
                if status not in (200, 204): raise Fail('%s answered %s' % (method, status))
            for method in ('PUT', 'PATCH', 'TRACE', 'CONNECT'):
                try:
                    status, headers, data = self.raw(method, '/mcp/' + A, b'{}', self.headers())
                except Fail:
                    raise Fail('%s: connection dropped' % method)
                self.judge(method, status, headers, data)
                if status < 400: raise Fail('%s answered %s' % (method, status))
        self.check('other HTTP methods', other_methods)
        self.alive()

    def g_malformed(self):
        self.group = 'malformed requests'
        sid = self.session()
        good = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'read_file', 'arguments': {'path': 'plain.txt'}}}
        meta = {META + 'protocolVersion': MODERN, META + 'clientCapabilities': {}}
        values = [None, True, False, 0, -1, 1.5, 1e308, '', 'x', [], [1], {}, {'a': 1}, 'tools/call', '\ud800', 'a' * 70000, {'name': 'read_file'}, [{'path': 'plain.txt'}]]
        bodies = []
        for field in ('jsonrpc', 'id', 'method', 'params'):
            for value in values:
                m = json.loads(json.dumps(good)); m[field] = value; bodies.append(m)
            m = json.loads(json.dumps(good)); m.pop(field); bodies.append(m)
        for field in ('name', 'arguments', '_meta'):
            for value in values + [meta, {META + 'protocolVersion': 5}, {META + 'protocolVersion': 'nope'}, {META + 'protocolVersion': MODERN, META + 'clientCapabilities': 7}]:
                m = json.loads(json.dumps(good)); m['params'][field] = value; bodies.append(m)
        for value in values:
            m = json.loads(json.dumps(good)); m['params']['arguments'] = {'path': value}; bodies.append(m)
            m = json.loads(json.dumps(good)); m['params']['arguments'] = {'path': 'plain.txt', 'extra': value}; bodies.append(m)
            for method in ('initialize', 'ping', 'tools/list', 'notifications/initialized', 'notifications/cancelled', 'resources/list', 'prompts/list', 'logging/setLevel', 'completion/complete', 'server/discover', 'sampling/createMessage', 'rpc.discover', ''):
                bodies.append({'jsonrpc': '2.0', 'id': 3, 'method': method, 'params': value})
        bodies += [values, [good, good], [], 'text', 5, None, True]
        # the same shapes in the modern era, with and without matching headers
        modern_bodies = []
        for b in bodies:
            if isinstance(b, dict) and isinstance(b.get('params'), dict) and '_meta' not in b['params']:
                m = json.loads(json.dumps(b)); m['params']['_meta'] = meta; modern_bodies.append(m)
        for field in ('id', 'method'):
            m = json.loads(json.dumps(good)); m['params']['_meta'] = meta; m.pop(field); modern_bodies.append(m)
        def send(body, version, extra, with_sid=True):
            label = 'body %s (%s)' % (json.dumps(body)[:110], version)
            raw = json.dumps(body).encode()
            status, headers, data = self.raw('POST', '/mcp/' + A, raw, self.headers(version=version, sid=sid if with_sid else None, extra=extra))
            parsed = self.judge(label, status, headers, data)
            if status == 200 and isinstance(body, dict) and 'id' in body:
                if not isinstance(parsed, dict) or parsed.get('jsonrpc') != '2.0' or ('result' in parsed) == ('error' in parsed): raise Fail('%s: 200 without a JSON-RPC reply: %s' % (label, str(parsed)[:100]))
            if status == 200 and not data: raise Fail('%s: 200 with an empty body' % label)
        for body in bodies:
            self.check('legacy ' + json.dumps(body)[:120], lambda body=body: send(body, LEGACY[0], None))
        for body in modern_bodies:
            method = body.get('method') if isinstance(body.get('method'), str) else 'tools/call'
            name = body.get('params', {}).get('name')
            extra = {'Mcp-Method': method.encode('utf-8', 'replace').decode('latin-1', 'replace')[:200]}
            if isinstance(name, str): extra['Mcp-Name'] = name.encode('utf-8', 'replace').decode('latin-1', 'replace')[:200]
            self.check('modern ' + json.dumps(body)[:120], lambda body=body, extra=extra: send(body, MODERN, extra))
            self.check('modern, no headers ' + json.dumps(body)[:100], lambda body=body: send(body, MODERN, None))
        # raw bytes that are not JSON at all, and odd headers
        raws = [b'', b'{', b'}', b'[', b'null', b'\xff\xfe', b'{"a":' + b'[' * 100000, b'{"jsonrpc":"2.0","id":1,"method":"ping"}' + b' ' * 10, b'\x00' * 100,
                b'{"jsonrpc":"2.0","id":1,"method":"ping","id":2}', b'{"jsonrpc":"2.0","id":NaN,"method":"ping"}', b'{"jsonrpc":"2.0","id":1e999,"method":"ping"}',
                b'{"jsonrpc":"2.0","id":' + b'9' * 5000 + b',"method":"ping"}', b'\xef\xbb\xbf{"jsonrpc":"2.0","id":1,"method":"ping"}', json.dumps(good).encode('utf-16')]
        for body in raws:
            def raw_case(body=body):
                status, headers, data = self.raw('POST', '/mcp/' + A, body, self.headers(sid=sid))
                self.judge('raw body %r' % body[:40], status, headers, data)
            self.check('raw body %r' % body[:60], raw_case)
        header_cases = [{'Content-Type': 'text/plain'}, {'Content-Type': 'application/json; charset=utf-16'}, {'Accept': 'text/html'}, {'Accept': ''}, {'MCP-Protocol-Version': '1999-01-01'},
                        {'MCP-Protocol-Version': ''}, {'MCP-Protocol-Version': 'x' * 5000}, {'Mcp-Session-Id': 'x' * 5000}, {'Mcp-Session-Id': '../../etc'}, {'Authorization': 'Bearer'},
                        {'Authorization': 'Basic abc'}, {'Authorization': 'Bearer ' + 'x' * 9000}, {'Authorization': 'bearer  ' + self.c.projects[A]['token']}, {'Origin': 'https://evil.example'},
                        {'Origin': 'null'}, {'Host': 'evil.example'}, {'Host': ''}, {'Content-Length': '-1'}, {'Content-Length': 'abc'}, {'Content-Length': '99999999999'}, {'Content-Length': '0'},
                        {'Transfer-Encoding': 'chunked'}, {'Expect': '100-continue'}, {'Mcp-Method': 'ping', 'Mcp-Name': '=?base64?' + 'x' * 100 + '?='}, {'X-Forwarded-For': '1.2.3.4', 'Cf-Connecting-Ip': '1.2.3.4'}]
        for case in header_cases:
            def header_case(case=case):
                body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).encode()
                h = self.headers(sid=sid, extra=case)
                s = socket.create_connection(('127.0.0.1', self.port), timeout=15)
                try:
                    if 'Content-Length' not in case: h['Content-Length'] = str(len(body))
                    if 'Host' not in case: h['Host'] = '127.0.0.1:%d' % self.port
                    s.sendall(('POST /mcp/%s HTTP/1.1\r\n' % A + ''.join('%s: %s\r\n' % kv for kv in h.items()) + '\r\n').encode('latin-1') + body)
                    data = b''
                    while True:
                        part = s.recv(65536)
                        if not part: break
                        data += part
                except OSError as error:
                    raise Fail('headers %s: %s' % (list(case), type(error).__name__))
                finally: s.close()
                if not data.startswith(b'HTTP/1.'): raise Fail('headers %s: no HTTP answer (%r)' % (list(case), data[:30]))
                status = int(data.split(b' ', 2)[1])
                if status >= 500: raise Fail('headers %s: status %s' % (list(case), status))
                for word in self.forbidden + [self.c.projects[A]['token']]:
                    if word.encode() in data: raise Fail('headers %s: leak' % list(case))
            self.check('headers %s' % json.dumps(case)[:100], header_case)
        paths = ['/', '/mcp', '/mcp/', '/mcp/' + A + '/', '/mcp/' + A + '/x', '/mcp/' + A.upper(), '/mcp/' + A + '?x=1', '/mcp/' + A + '#f', '/mcp/../mcp/' + A, '/mcp/%2e%2e/',
                 '/mcp/' + A + '/' + 'A' * 43, '/mcp/' + A + '/' + 'A' * 86, '/mcp/' + A + '/' + 'A' * 5000, '/' + 'a' * 70000, '/mcp/' + B.replace('code-', 'chat-'), '/mcp/work-' + A, '/.well-known/oauth-authorization-server',
                 '/.well-known/oauth-protected-resource', '/favicon.ico', '/mcp/' + A + '/%00', '*']
        for path in paths:
            def path_case(path=path):
                for method in ('POST', 'GET', 'DELETE'):
                    status, headers, data = self.raw(method, path, json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).encode() if method == 'POST' else None, self.headers(sid=sid))
                    self.judge('%s %s' % (method, path[:50]), status, headers, data)
                    if status < 400: raise Fail('%s %s answered %s' % (method, path[:50], status))
            self.check('path %s' % path[:80], path_case)
        self.alive()

    def all_paths(self):
        out = ['.']
        for base, dirs, files in os.walk(self.folder, followlinks=False):
            rel = os.path.relpath(base, self.folder)
            if rel.count(os.sep) > 3 and 'd0' in rel: continue
            names = dirs + files
            if rel.startswith('many') : names = names[:5]
            for name in names: out.append(os.path.normpath(os.path.join(rel, name)))
        return out

    def g_reads(self):
        self.group = 'reading every kind of file'
        sid = self.session()
        paths = self.all_paths()
        for path in paths:
            for tool in ('read_file', 'read_image', 'list_directory'):
                def one(path=path, tool=tool):
                    start = time.monotonic()
                    error, value = self.call(sid, tool, {'path': path}, timeout=30)
                    took = time.monotonic() - start
                    if took > 15: raise Fail('%s %r took %.0f s' % (tool, path, took))
                    if error and not (isinstance(value, dict) and isinstance(value.get('error') or value.get('message'), str)): raise Fail('%s %r: error without a message: %s' % (tool, path, str(value)[:100]))
                    text = json.dumps(value)
                    if len(text) > 16 * 1024 * 1024: raise Fail('%s %r: reply of %d bytes' % (tool, path, len(text)))
                    if not error and ('link-out' in path or 'dir-out' in path or 'link-passwd' in path or 'link-zero' in path): raise Fail('%s %r: followed a link out of the folder' % (tool, path))
                    if not error and tool == 'read_file' and 'root:' in text and 'passwd' in path: raise Fail('passwd content returned')
                self.check('%s %r' % (tool, path), one)
        def known_answers():
            expect = {'plain.txt': 'Hello plain', 'crlf.txt': 'two', 'bom.txt': 'with bom', 'Zażółć gęślą jaźń.txt': 'polski', 'emoji 😀.txt': 'emoji', 'sub/inner.txt': 'inner', 'good.odt': 'Odt words', 'longline.txt': 'xxxx'}
            for path, word in expect.items():
                error, value = self.call(sid, 'read_file', {'path': path})
                if error or word not in json.dumps(value, ensure_ascii=False): raise Fail('read_file %r: expected %r, got %s' % (path, word, str(value)[:140]))
            error, value = self.call(sid, 'list_directory', {'path': 'many'})
            if error: raise Fail('listing 3000 files fails: %s' % value)
            error, value = self.call(sid, 'read_file', {'path': 'empty.txt'})
            if error: raise Fail('an empty text file cannot be read: %s' % value)
            if (self.outside / 'planted.txt').exists(): raise Fail('a file was written outside the folder')
        self.check('known answers', known_answers)
        self.alive()

    def g_paths(self):
        self.group = 'path arguments'
        sid = self.session()
        tricky = ['', ' ', '..', '../', '../outside/secret.txt', '../../etc/passwd', '/etc/passwd', str(self.outside / 'secret.txt'), 'sub/../../outside/secret.txt', 'sub/../plain.txt', './plain.txt', 'sub//inner.txt',
                  'sub/./inner.txt', 'sub/', 'plain.txt/', 'plain.txt/x', 'plain.txt\x00', '\x00', 'plain.txt\x00.png', '..\\outside\\secret.txt', 'C:\\Windows\\win.ini', '\\\\server\\share', 'file:///etc/passwd',
                  'http://example.com/x', '~', '~/x', '$HOME', '%2e%2e/outside/secret.txt', '..%2foutside', '....//outside/secret.txt', 'dir-out/secret.txt', 'self-dir/self-dir/self-dir/plain.txt',
                  'loop-a', 'dangling', 'fifo', 'sock', 'CON', 'NUL', 'aux.txt', 'a' * 255, 'a' * 256, 'a' * 5000, ('d/' * 3000) + 'x', 'PLAIN.TXT', 'plain.TXT', 'café nfd.txt', 'cafe\u0301 nfd.txt',
                  '.hidden', '.env', '.git/config', 'sub/.hidden', '*', '?', '[a-z]*', 'plain.txt:stream', 'plain.txt::$DATA', ' plain.txt', 'plain.txt ', 'plain.txt.', '\ud83d', '\u202eplain.txt', '\ufeffplain.txt',
                  'new\nline.txt', 'tab\tname', '-rf', '--help', '.', './', '/', '//', '/.', 'many/../many/f0001.txt', 'proc/self/environ', '/proc/self/environ', '/dev/stdin']
        for path in tricky:
            for tool in ('read_file', 'read_image', 'list_directory', 'write_file', 'create_document'):
                def one(path=path, tool=tool):
                    args = {'path': path}
                    if tool in ('write_file', 'create_document'): args['content'] = 'stress content'
                    try: json.dumps(args).encode()
                    except UnicodeEncodeError: return
                    before = set(os.listdir(self.outside))
                    error, value = self.call(sid, tool, args, timeout=30)
                    text = json.dumps(value)
                    if tool in ('write_file', 'create_document') and not error:
                        pid = value.get('proposal_id')
                        if pid:
                            try: self.c.resolve(pid, True)
                            except (ValueError, OSError): pass
                    if set(os.listdir(self.outside)) != before: raise Fail('%s %r: changed the folder outside the workspace' % (tool, path))
                    if (self.outside / 'secret.txt').read_text() != CANARY: raise Fail('%s %r: changed a file outside the workspace' % (tool, path))
                self.check('%s %r' % (tool, path[:60]), one)
        def nothing_escaped():
            if (self.outside / 'secret.txt').read_text() != CANARY or sorted(os.listdir(self.outside)) != ['secret.txt']: raise Fail('outside folder changed: %s' % os.listdir(self.outside))
            if os.path.exists('/tmp/planted.txt'): raise Fail('planted file')
            for name in os.listdir(self.root):
                if name not in ('outside', 'linked', 'other', 'private'): raise Fail('unexpected item next to the folder: %s' % name)
        self.check('nothing written outside', nothing_escaped)
        # Where names ignore case, reading PLAIN.TXT and then writing it is a
        # proper change of plain.txt; put the fixture back for the next groups.
        (self.folder / 'plain.txt').write_text('Hello plain\n')
        self.alive()

    def write(self, sid, path, content, allow=True, tool='write_file'):
        """Propose and settle one write the way the panel does. Returns the final status."""
        error, value = self.call(sid, tool, {'path': path, 'content': content})
        if error: return 'refused', value
        if value.get('unchanged'): return 'unchanged', value
        pid = value.get('proposal_id')
        if value.get('status') != 'pending' or not pid: raise Fail('%s %r: unexpected proposal %s' % (tool, path, str(value)[:120]))
        try: self.c.resolve(pid, allow)
        except (ValueError, OSError) as error: return 'failed', {'error': str(error)}
        error, status = self.call(sid, 'change_status', {'proposal_id': pid})
        if error: raise Fail('change_status fails after resolve: %s' % status)
        if status.get('written') != (status.get('status') == 'saved'): raise Fail('written flag disagrees with status: %s' % status)
        return status['status'], status

    def g_writes(self):
        self.group = 'writing'
        sid = self.session()
        out = self.folder / 'out'; out.mkdir()
        def new_text():
            status, _ = self.write(sid, 'out/new.txt', 'First\n')
            if status != 'saved' or (out / 'new.txt').read_text() != 'First\n': raise Fail('new file not saved: %s' % status)
            self.call(sid, 'read_file', {'path': 'out/new.txt'})
            status, _ = self.write(sid, 'out/new.txt', 'Second ąę 😀\n')
            if status != 'saved' or (out / 'new.txt').read_text() != 'Second ąę 😀\n': raise Fail('overwrite after read not saved: %s' % status)
            status, _ = self.write(sid, 'out/new.txt', 'Rejected', allow=False)
            if status != 'rejected' or (out / 'new.txt').read_text() != 'Second ąę 😀\n': raise Fail('reject changed the file or status: %s' % status)
            status, _ = self.write(sid, 'out/a/b/c/nested.txt', 'nested')
            if status != 'saved' or (out / 'a/b/c/nested.txt').read_text() != 'nested': raise Fail('file in new subfolders not saved: %s' % status)
        self.check('text files: new, overwrite, reject, nested', new_text)
        def unread_overwrite():
            (out / 'unread.txt').write_text('made by the user')
            status, value = self.write(self.session(), 'out/unread.txt', 'blind overwrite')
            if status == 'saved': raise Fail('an existing file was overwritten without reading it first')
            if (out / 'unread.txt').read_text() != 'made by the user': raise Fail('file changed')
        self.check('existing file is not overwritten blind', unread_overwrite)
        def changed_meanwhile():
            (out / 'race.txt').write_text('v1'); self.call(sid, 'read_file', {'path': 'out/race.txt'})
            error, value = self.call(sid, 'write_file', {'path': 'out/race.txt', 'content': 'v2 by assistant'})
            (out / 'race.txt').write_text('v1b by user')
            try: self.c.resolve(value['proposal_id'], True); raise Fail('approve succeeded over a newer user edit')
            except ValueError: pass
            if (out / 'race.txt').read_text() != 'v1b by user': raise Fail('user edit lost')
            error, status = self.call(sid, 'change_status', {'proposal_id': value['proposal_id']})
            if status.get('written'): raise Fail('status claims written')
        self.check('user edit between proposal and approval wins', changed_meanwhile)
        def documents():
            for ext in ('odt', 'docx', 'ods', 'xlsx', 'odp', 'pptx'):
                for tool in ('create_document', 'write_file'):
                    name = 'out/doc-%s.%s' % (tool, ext)
                    content = 'Title\n\nA,B,C\n1,2,3\nZażółć 😀 <tag> & "quotes"\n'
                    status, value = self.write(sid, name, content, tool=tool)
                    if status != 'saved': raise Fail('%s %s: %s %s' % (tool, ext, status, str(value)[:120]))
                    path = self.folder / name
                    if not zipfile.is_zipfile(path): raise Fail('%s is not a real office file' % name)
                    with zipfile.ZipFile(path) as z:
                        if z.testzip() is not None: raise Fail('%s is a damaged zip' % name)
                    error, back = self.call(sid, 'read_file', {'path': name})
                    if error: raise Fail('%s cannot be read back: %s' % (name, back))
                    if ext in ('odt', 'docx') and 'Zażółć' not in json.dumps(back, ensure_ascii=False): raise Fail('%s lost its text: %s' % (name, str(back)[:160]))
        self.check('office documents are created and read back', documents)
        contents = ['', ' ', '\n', 'x' * 1_000_000, 'x' * 9_000_000, '\x00', 'a\x00b', '﻿bom', 'line\r\nline', '‮ rtl', '😀' * 10000, '\x1b[31mred', '<?xml version="1.0"?><a/>', '\x0c\x0b\x01', 'a b', '\ud83d']
        for n, content in enumerate(contents):
            for ext in ('txt', 'md', 'json', 'csv', 'odt', 'xlsx', 'py', 'html', ''):
                def one(n=n, content=content, ext=ext):
                    try: json.dumps(content).encode()
                    except UnicodeEncodeError: return
                    name = 'out/content-%d%s' % (n, '.' + ext if ext else '')
                    try:
                        status, value = self.write(sid, name, content, tool='create_document' if ext in ('odt', 'xlsx') else 'write_file')
                    except Fail as error:
                        # More than the request limit: a clear refusal, never a broken connection.
                        if len(content) > 1_000_000 and 'status 413' in str(error): status = 'refused'
                        else: raise
                    path = self.folder / name
                    if status == 'saved':
                        if not path.is_file(): raise Fail('%s: saved but no file' % name)
                        if ext not in ('odt', 'xlsx') and path.read_bytes() != content.encode('utf-8'): raise Fail('%s: bytes on disk differ from the content' % name)
                        error, back = self.call(sid, 'read_file', {'path': name})
                        if error and ext not in ('odt', 'xlsx') and len(content) < 2_000_000 and '\x00' not in content: raise Fail('%s: saved file cannot be read back: %s' % (name, str(back)[:120]))
                    elif path.exists(): raise Fail('%s: status %s but the file exists' % (name, status))
                self.check('content %d (%r…) as .%s' % (n, content[:12], ext), one)
        names = ['out/UPPER.TXT', 'out/noext', 'out/.dotfile', 'out/sp ace.txt', 'out/ąę.txt', 'out/😀.txt', 'out/a.b.c.txt', 'out/trailing.', 'out/x.exe', 'out/x.sh', 'out/x.desktop', 'out/x.lnk', 'out/x.bat',
                 'out/x.svg', 'out/x.png', 'out/x.pdf', 'out/x.zip', 'out/x.doc', 'out/' + 'n' * 251 + '.txt', 'out/' + 'n' * 300 + '.txt', 'link-in.txt', 'link-out.txt', 'dir-out/new.txt', 'fifo', 'sock', 'sub',
                 'out', 'noperm.txt', 'nopermdir/new.txt', 'plain.txt/new.txt', 'dangling', 'loop-a', 'self-dir/out/viaself.txt', 'out/con.txt', 'out/aux', 'out/a:b.txt', 'out/a|b.txt', 'out/a?b.txt', 'out/a*b.txt']
        for name in names:
            def one(name=name):
                status, value = self.write(sid, name, 'name test')
                if (self.outside / 'secret.txt').read_text() != CANARY or sorted(os.listdir(self.outside)) != ['secret.txt']: raise Fail('%r: wrote outside the folder' % name)
                if status == 'saved':
                    target = self.folder / name
                    if not os.path.realpath(target).startswith(str(self.folder) + os.sep): raise Fail('%r: saved through a link' % name)
                    if name in ('link-in.txt',) and os.path.islink(target) is False and (self.folder / 'plain.txt').read_text() != 'Hello plain\n': raise Fail('link target changed')
                if hasattr(os, 'mkfifo') and stat.S_ISFIFO(os.lstat(self.folder / 'fifo').st_mode) is False: raise Fail('fifo was replaced')
            self.check('write to %r' % name[:60], one)
        def many_pending():
            pids = []
            for n in range(20):
                error, value = self.call(sid, 'write_file', {'path': 'out/pending-%d.txt' % n, 'content': 'p'})
                if not error: pids.append(value['proposal_id'])
            if len(pids) != 16: raise Fail('%d pending proposals accepted, expected the limit of 16' % len(pids))
            for pid in pids[:8]: self.c.resolve(pid, True)
            for pid in pids[8:]: self.c.resolve(pid, False)
            error, value = self.call(sid, 'write_file', {'path': 'out/after-limit.txt', 'content': 'p'})
            if error: raise Fail('still refused after the proposals were handled: %s' % value)
            self.c.resolve(value['proposal_id'], False)
            if len([p for p in os.listdir(out) if p.startswith('pending-')]) != 8: raise Fail('wrong number of saved files')
        self.check('pending proposal limit and recovery', many_pending)
        def same_call_approval():
            self.c.approval_wait = 5; done = []
            def approve():
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    with self.c.lock: pending = [pid for pid, p in self.c.proposals.items() if p['status'] == 'pending']
                    if pending:
                        self.c.resolve(pending[0], True); done.append(1); return
                    time.sleep(.02)
            t = threading.Thread(target=approve); t.start()
            try:
                start = time.monotonic()
                error, value = self.call(sid, 'write_file', {'path': 'out/same-call.txt', 'content': 'same call'})
            finally:
                t.join(); self.c.approval_wait = 0
            if error or value.get('status') != 'saved' or not value.get('written'): raise Fail('approval during the call not reported: %s' % str(value)[:140])
            if time.monotonic() - start > 3: raise Fail('call did not return right after approval')
            self.c.approval_wait = 1
            try:
                error, value = self.call(sid, 'write_file', {'path': 'out/slow-user.txt', 'content': 'slow'})
            finally: self.c.approval_wait = 0
            if error or value.get('status') != 'pending' or value.get('written'): raise Fail('unanswered proposal not reported pending: %s' % str(value)[:140])
            self.c.resolve(value['proposal_id'], True)
            error, status = self.call(sid, 'change_status', {'proposal_id': value['proposal_id']})
            if not status.get('written'): raise Fail('late approval not visible in change_status')
        self.check('approval inside and after the tool call', same_call_approval)
        def status_misuse():
            for pid in ('', 'x', 'a' * 5000, '../x', '\x00'):
                error, value = self.call(sid, 'change_status', {'proposal_id': pid})
                if not error: raise Fail('unknown proposal id %r accepted' % pid[:10])
            error, value = self.call(self.session(), 'write_file', {'path': 'out/cross.txt', 'content': 'x'})
            self.activate(B)
            try:
                error2, seen = self.call(self.session(B), 'change_status', {'proposal_id': value['proposal_id']}, key=B)
            finally: self.activate(A)
            if not error2: raise Fail('another project can read the status of this proposal')
            if (self.folder / 'out/cross.txt').exists(): raise Fail('file written without approval')
        self.check('change_status misuse', status_misuse)
        self.alive()

    def g_concurrency(self):
        self.group = 'many requests at once'
        sid = self.session()
        def burst(n, fn):
            problems = []; threads = []
            def run(i):
                try: fn(i)
                except Fail as error: problems.append(str(error))
                except Exception as error: problems.append('script: %r' % error)
            for i in range(n):
                t = threading.Thread(target=run, args=(i,)); threads.append(t); t.start()
            for t in threads: t.join(120)
            if any(t.is_alive() for t in threads): raise Fail('requests still hanging after 120 s')
            return problems
        def parallel_reads():
            def one(i):
                for _ in range(3):
                    for attempt in range(4):
                        try:
                            error, value = self.call(sid, 'read_file', {'path': 'plain.txt'}); break
                        except Fail as error_:
                            # the server sheds load above 16 connections; a client retries
                            if 'server busy' not in str(error_) or attempt == 3: raise
                            time.sleep(.2 * (attempt + 1))
                    if error or 'Hello plain' not in json.dumps(value): raise Fail('wrong content under load: %s' % str(value)[:200])
            problems = burst(12, one)
            if problems: raise Fail('%d of 12 clients failed: %s' % (len(problems), problems[0]))
        self.check('12 clients reading together', parallel_reads)
        def overload():
            dropped = []; other = []
            def one(i):
                try: self.call(sid, 'read_file', {'path': 'longline.txt'})
                except Fail as error:
                    (dropped if 'server busy' in str(error) else other).append(str(error))
            burst(60, one)
            if other: raise Fail('wrong answers under overload: %s' % other[0])
            return len(dropped)
        self.check('60 clients at once: only clean refusals', overload)
        self.alive('answers after overload')
        def writes_together():
            results = []
            def one(i):
                s = self.session()
                error, value = self.call(s, 'write_file', {'path': 'out/together.txt', 'content': 'writer %d' % i})
                if error: results.append('refused'); return
                try: self.c.resolve(value['proposal_id'], True); results.append('saved')
                except ValueError: results.append('failed')
            problems = burst(8, one)
            if problems: raise Fail(problems[0])
            text = (self.folder / 'out/together.txt').read_text()
            if not text.startswith('writer ') or len(text) > 9: raise Fail('mixed content after concurrent writes: %r' % text[:40])
            if results.count('saved') < 1: raise Fail('no writer succeeded: %s' % results)
        self.check('8 writers on one new file: one clean winner', writes_together)
        def streams():
            socks = []
            try:
                for n in range(8):
                    s = socket.create_connection(('127.0.0.1', self.port), timeout=5)
                    h = self.headers(sid=sid, extra={'Accept': 'text/event-stream', 'Host': '127.0.0.1:%d' % self.port})
                    s.sendall(('GET /mcp/%s HTTP/1.1\r\n' % A + ''.join('%s: %s\r\n' % kv for kv in h.items()) + '\r\n').encode()); socks.append(s)
                time.sleep(.5)
                self.alive('answers with 8 event streams open')
            finally:
                for s in socks: s.close()
        self.check('event streams do not block requests', streams)
        def slow_clients():
            socks = []
            try:
                for n in range(40):
                    s = socket.create_connection(('127.0.0.1', self.port), timeout=5)
                    s.sendall(b'POST /mcp/' + A.encode() + b' HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 100\r\n' + (b'' if n % 2 else b'\r\n{"a"')); socks.append(s)
                time.sleep(10)  # the server gives up on a silent client after 8 seconds
                start = time.monotonic(); s = self.session()
                if time.monotonic() - start > 3: raise Fail('server stayed blocked by silent clients')
            finally:
                for s in socks: s.close()
        self.check('40 silent clients are dropped within 10 s', slow_clients)
        self.alive()

    def g_lifecycle(self):
        self.group = 'pause, relink, restart'
        def pause_resume():
            sid = self.session(); self.c.pause(A)
            status, _, d = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'ping'}, 'ping while paused', sid=sid)
            if status != 403: raise Fail('paused project answered %s' % status)
            status, _, _ = self.raw('POST', '/mcp/' + A, b'{}', {'Content-Type': 'application/json', 'Accept': 'application/json'})
            if status != 404: raise Fail('paused project without key answered %s' % status)
            self.c.enable(A, True, manual=True)
            status, _, _ = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'ping'}, 'old session after resume', sid=sid)
            new = self.session()
            error, value = self.call(new, 'read_file', {'path': 'plain.txt'})
            if error: raise Fail('reading fails after resume: %s' % value)
        self.check('pause and resume', pause_resume)
        def pending_and_pause():
            sid = self.session()
            error, value = self.call(sid, 'write_file', {'path': 'out/paused-write.txt', 'content': 'x'})
            self.c.pause(A)
            try: self.c.resolve(value['proposal_id'], True); raise Fail('a write was approved while the project is paused')
            except ValueError: pass
            if (self.folder / 'out/paused-write.txt').exists(): raise Fail('file written while paused')
            self.c.enable(A, True, manual=True)
        self.check('pending write is withdrawn by a pause', pending_and_pause)
        def rotate():
            old = self.c.projects[A]['token']; sid = self.session()
            self.c.rotate(A); self.c.enable(A, True, manual=True)
            status, headers, data = self.raw('POST', '/mcp/' + A, json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).encode(), self.headers(sid=sid, token=old))
            if status not in (401, 404): raise Fail('old key answered %s' % status)
            status, headers, data = self.raw('POST', '/mcp/' + A + '/' + old, json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).encode(), {'Content-Type': 'application/json', 'Accept': 'application/json', 'Mcp-Session-Id': sid})
            if status != 404: raise Fail('old secret address answered %s' % status)
            error, value = self.call(self.session(), 'read_file', {'path': 'plain.txt'})
            if error: raise Fail('new key cannot read: %s' % value)
        self.check('key rotation closes the old key', rotate)
        def relink():
            sid = self.session(); self.call(sid, 'read_file', {'path': 'plain.txt'})
            second = self.root / 'private' / 'second-folder'; second.mkdir(); (second / 'second.txt').write_text('second folder')
            self.forbidden.remove(str(self.root)); self.forbidden.append(str(self.root) + os.sep)
            self.c.link(A, second); self.c.enable(A, True, manual=True)
            status, _, d = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'tools/call', 'params': {'name': 'read_file', 'arguments': {'path': 'plain.txt'}}}, 'old session after relink', sid=sid)
            if status == 200 and d.get('result', {}).get('isError') is False: raise Fail('old session still reads the previous folder')
            new = self.session()
            error, value = self.call(new, 'read_file', {'path': 'second.txt'})
            if error: raise Fail('new folder not readable: %s' % value)
            error, value = self.call(new, 'read_file', {'path': 'plain.txt'})
            if not error: raise Fail('previous folder still readable after relink')
            self.c.link(A, self.folder); self.c.enable(A, True, manual=True)
        self.check('relink switches the folder for everyone', relink)
        def cross_project():
            a = self.session(A)
            error, value = self.call(a, 'read_file', {'path': '../other/b.txt'})
            if not error: raise Fail('project A reads the folder of project B')
            status, _, d = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'initialize', 'params': {'protocolVersion': LEGACY[0], 'capabilities': {}}}, 'B while A is open', key=B)
            # A paused project answers the handshake (Mistral shows "Token verification
            # failed" for a 403), but hands out no session and never opens a file.
            if status != 200 or 'Mcp-Session-Id' in _ or 'paused' not in json.dumps(d): raise Fail('a paused project does not answer the handshake as paused: %s' % status)
            status, _, d = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'tools/call', 'params': {'name': 'read_file', 'arguments': {'path': 'b.txt'}}}, 'B read while A is open', key=B)
            if status != 200 or d.get('result', {}).get('isError') is not True or 'otherproject' in json.dumps(d): raise Fail('a project that is not open hands out a file')
            self.activate(B)
            try:
                b = self.session(B)
                status, _, d = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'ping'}, 'A session on B', key=B, sid=a)
                if status == 200: raise Fail("project B accepts project A's session")
                status, headers, data = self.raw('POST', '/mcp/' + B, json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).encode(), self.headers(key=B, sid=b, token=self.c.projects[A]['token']))
                if status == 200: raise Fail("project B accepts project A's key")
                status, _, d = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'ping'}, 'A after switching to B', sid=a)
                if status == 200: raise Fail('project A still answers after switching to B')
                error, value = self.call(b, 'read_file', {'path': '../linked/plain.txt'}, key=B)
                if not error: raise Fail('project B reads the folder of project A')
                self.forbidden.remove('otherproject')
                try: error, value = self.call(b, 'read_file', {'path': 'b.txt'}, key=B)
                finally: self.forbidden.append('otherproject')
                if error: raise Fail('project B cannot read its own file: %s' % value)
            finally: self.activate(A)
            error, value = self.call(self.session(), 'read_file', {'path': 'plain.txt'})
            if error: raise Fail('project A cannot read after switching back: %s' % value)
        self.check('projects stay apart', cross_project)
        def sessions_bounded():
            opened = 0
            for n in range(80):
                status, headers, d = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'initialize', 'params': {'protocolVersion': LEGACY[0], 'capabilities': {}}}, 'initialize %d' % n)
                if status == 200: opened += 1
            # A client that never closes sessions (Mistral does not) must not lock itself out.
            status, headers, d = self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'initialize', 'params': {'protocolVersion': LEGACY[0], 'capabilities': {}}}, 'initialize after many')
            if status != 200: raise Fail('after %d unclosed sessions a new one is refused with %s' % (opened, status))
            if len(self.c.sessions) > 64: raise Fail('%d sessions kept' % len(self.c.sessions))
        self.check('many unclosed sessions do not lock the client out', sessions_bounded)
        def restart():
            token = self.c.projects[A]['token']; port = self.port
            self.c.close()
            self.c = web.Connector(self.events.append, self.root / 'private', approval_wait=0)
            if A in self.c.enabled: raise Fail('network access is open right after a restart')
            if self.c.projects.get(A, {}).get('folder') != str(self.folder): raise Fail('folder link lost in restart')
            self.activate(A); self.port = self.c.server.server_port
            error, value = self.call(self.session(), 'read_file', {'path': 'plain.txt'})
            if error: raise Fail('reading fails after restart: %s' % value)
        self.check('restart keeps the link and reopens only on request', restart)
        def corrupt_store():
            self.c.close()
            private = self.root / 'private'
            saved = {p: p.read_bytes() for p in private.iterdir() if p.is_file()}
            problems = []
            for path, original in saved.items():
                for damage in (b'', b'{', b'null', b'[]', b'{"projects": 5}', original[:len(original) // 2], b'\xff' * 100, original.replace(b'"', b"'")):
                    path.write_bytes(damage)
                    try:
                        c = web.Connector(self.events.append, private, approval_wait=0); c.close()
                    except Exception as error:
                        problems.append('%s damaged as %r: %s' % (path.name, damage[:12], type(error).__name__))
                    path.write_bytes(original)
            for path, original in saved.items(): path.write_bytes(original)
            self.c = web.Connector(self.events.append, private, approval_wait=0)
            for key in (A, B):
                if key not in self.c.projects: self.c.select({'id': key, 'name': 'x'}); self.c.link(key, self.folder if key == A else self.other)
            self.activate(A)
            self.port = self.c.server.server_port
            if problems: raise Fail('%d damaged state files stop the start: %s' % (len(problems), problems[0]))
        self.check('damaged state files never stop the start', corrupt_store)
        self.alive()

    def g_filesystem(self):
        self.group = 'disk and folder trouble'
        sid = self.session()
        capfs = sys.modules['_vibez_capfs']
        # The injected faults are those of Linux file systems (no hard links,
        # no fsync, no renameat2, mode bits); Windows saves along another route.
        posix = os.name != 'nt'
        real = {name: getattr(os, name) for name in ('link', 'fsync')}
        real['renameat2'] = getattr(capfs, '_native_rename_noreplace', None)
        def put(name, value):
            if name == 'renameat2': capfs._native_rename_noreplace = value
            else: setattr(os, name, value)
        def with_fault(names, errno_, label):
            def run():
                import errno as E
                def broken(*a, **k):
                    if names == ('dirsync',):
                        if stat.S_ISDIR(os.fstat(a[0]).st_mode): raise OSError(errno_, os.strerror(errno_))
                        return real['fsync'](*a, **k)
                    raise OSError(errno_, os.strerror(errno_))
                target = self.folder / 'out' / ('fault-%s.txt' % label)
                for name in names: put('fsync' if name == 'dirsync' else name, (lambda *a, **k: errno_) if name == 'renameat2' else broken)
                try:
                    status, value = self.write(sid, 'out/fault-%s.txt' % label, 'fault test')
                    if status == 'saved':
                        self.call(sid, 'read_file', {'path': 'out/fault-%s.txt' % label})
                        status, value = self.write(sid, 'out/fault-%s.txt' % label, 'fault test')  # unchanged
                        status, value = self.write(sid, 'out/fault-%s.txt' % label, 'fault test 2')
                        if status == 'saved' and target.read_text() != 'fault test 2': raise Fail('overwrite reported saved, file is wrong')
                        if status == 'saved': target.write_text('fault test')
                        doc, _ = self.write(sid, 'out/fault-%s.odt' % label, 'fault doc', tool='create_document')
                        if doc != 'saved': raise Fail('text file saved but document not: %s' % doc)
                finally:
                    for name in names: put('fsync' if name == 'dirsync' else name, real['fsync' if name == 'dirsync' else name])
                leftovers = [n for n in os.listdir(self.folder / 'out') if n.startswith('.') or 'tmp' in n.lower() or n.endswith('.part')]
                if status == 'saved' and (not target.is_file() or target.read_text() != 'fault test'): raise Fail('reported saved, file is wrong')
                if status != 'saved' and target.exists() and target.read_text() != 'fault test': raise Fail('half-written file left behind')
                if leftovers: raise Fail('temporary files left in the folder: %s' % leftovers[:3])
                return status
            return run
        import errno
        # A folder on a file system without hard links (Flatpak document portal, FAT, some network shares).
        self.results = {}
        for names, code, label in ((('link',), errno.EPERM, 'nolink-eperm'), (('link',), errno.EOPNOTSUPP, 'nolink-notsup'), (('link',), errno.EINVAL, 'nolink-einval'), (('link',), errno.EXDEV, 'nolink-exdev'),
                                   (('fsync',), errno.EINVAL, 'nofsync'), (('fsync',), errno.ENOSYS, 'nofsync-enosys'), (('fsync',), errno.EIO, 'fsync-eio'), (('dirsync',), errno.EIO, 'dirsync-eio'),
                                   (('renameat2',), errno.EINVAL, 'norename-einval'), (('renameat2',), errno.ENOSYS, 'norename-enosys'), (('renameat2', 'link'), errno.EINVAL, 'norename-nolink'),
                                   (('renameat2', 'link', 'fsync'), errno.EOPNOTSUPP, 'bare-filesystem')):
            def one(names=names, code=code, label=label):
                status = with_fault(names, code, label)()
                self.results[label] = status
                if label != 'fsync-eio':
                    if status != 'saved': raise Fail('a new file cannot be saved on a file system without %s (%s): %s' % (names[0], os.strerror(code), status))
            if posix: self.check('write when %s fails with %s' % (names[0], errno.errorcode[code]), one)
        def read_only():
            ro = self.folder / 'readonly'; ro.mkdir(); (ro / 'r.txt').write_text('ro'); os.chmod(ro, 0o500)
            try:
                error, value = self.call(sid, 'read_file', {'path': 'readonly/r.txt'})
                if error: raise Fail('read-only folder cannot be read: %s' % value)
                status, value = self.write(sid, 'readonly/new.txt', 'x')
                if status == 'saved': raise Fail('saved in a read-only folder?')
            finally: os.chmod(ro, 0o700)
        if posix: self.check('read-only folder: reads work, writes fail cleanly', read_only)
        def vanish():
            gone = self.root / 'private' / 'vanishing'; gone.mkdir(); (gone / 'v.txt').write_text('v')
            self.c.link(A, gone); self.c.enable(A, True, manual=True); s = self.session()
            self.call(s, 'read_file', {'path': 'v.txt'})
            error, value = self.call(s, 'write_file', {'path': 'new.txt', 'content': 'x'})
            import shutil; shutil.rmtree(gone)
            for tool, args in (('list_directory', {'path': '.'}), ('read_file', {'path': 'v.txt'}), ('workspace_overview', {}), ('write_file', {'path': 'n2.txt', 'content': 'x'})):
                try: self.call(s, tool, args)
                except Fail as e:
                    if 'status 4' not in str(e): raise
            try: self.c.resolve(value['proposal_id'], True)
            except (ValueError, OSError): pass
            if gone.exists(): raise Fail('the removed folder was created again')
            gone.mkdir(); (gone / 'fresh.txt').write_text('other folder, same path')
            try:
                error, value = self.call(s, 'read_file', {'path': 'fresh.txt'})
            except Fail: error = True
            self.c.link(A, self.folder); self.c.enable(A, True, manual=True)
        # Windows does not let a folder be removed while a program has it open.
        if posix: self.check('folder removed while linked', vanish)
        def churn():
            stop = threading.Event(); d = self.folder / 'churn'; d.mkdir()
            def mutate():
                n = 0
                while not stop.is_set():
                    n += 1; p = d / ('c%d.txt' % (n % 20))
                    try:
                        if n % 3 == 0 and p.exists(): p.unlink()
                        elif n % 7 == 0:
                            if p.exists(): p.unlink()
                            os.symlink(self.outside / 'secret.txt', p)
                        else:
                            if p.is_symlink(): p.unlink()
                            p.write_text('churn %d' % n)
                    except OSError: pass
            t = threading.Thread(target=mutate); t.start()
            try:
                s = self.session(); end = time.monotonic() + 6
                while time.monotonic() < end:
                    self.call(s, 'list_directory', {'path': 'churn'})
                    self.call(s, 'read_file', {'path': 'churn/c%d.txt' % self.random.randrange(20)})
                    self.call(s, 'workspace_overview', {})
            finally:
                stop.set(); t.join()
        self.check('files appear, vanish and turn into links while being read', churn)
        self.alive()

    def g_soak(self, seconds):
        self.group = 'random use for %d s' % seconds
        fds = open_handles(); threads = threading.active_count()
        paths = self.all_paths(); end = time.monotonic() + seconds; count = [0]
        def worker(seed):
            r = random.Random(seed); sid = None
            while time.monotonic() < end:
                count[0] += 1
                def step():
                    nonlocal sid
                    try:
                        if sid is None or r.random() < .02: sid = self.session()
                        roll = r.random(); path = r.choice(paths)
                        if roll < .45: self.call(sid, r.choice(['read_file', 'list_directory', 'read_image']), {'path': path})
                        elif roll < .55: self.call(sid, 'workspace_overview', {})
                        elif roll < .75:
                            self.write(sid, 'out/soak-%d.%s' % (r.randrange(30), r.choice(['txt', 'md', 'odt', 'xlsx', 'docx'])), 'soak %d' % r.randrange(10 ** 6), allow=r.random() < .7, tool=r.choice(['write_file', 'create_document']))
                        elif roll < .85: self.modern('tools/call', {'name': 'read_file', 'arguments': {'path': path}}, name='read_file')
                        elif roll < .9: self.modern('tools/list')
                        elif roll < .95:
                            self.raw('DELETE', '/mcp/' + A, None, self.headers(sid=sid)); sid = None
                        else: self.post({'jsonrpc': '2.0', 'id': self.next_id(), 'method': 'ping'}, 'ping', sid=sid)
                    except Fail as error:
                        if 'server busy' in str(error): time.sleep(.2); sid = None; return 'shed'
                        raise
                self.check('soak step', step)
        ts = [threading.Thread(target=worker, args=(self.random.random(),)) for _ in range(6)]
        for t in ts: t.start()
        for t in ts: t.join(seconds + 180)
        def resources():
            if any(t.is_alive() for t in ts): raise Fail('a client is still hanging')
            time.sleep(10)
            now_fds = open_handles(); now_threads = threading.active_count()
            if now_fds > fds + 12: raise Fail('open files grew from %d to %d' % (fds, now_fds))
            if now_threads > threads + 4: raise Fail('threads grew from %d to %d' % (threads, now_threads))
            if len(self.c.proposals) > 600: raise Fail('%d proposals kept in memory' % len(self.c.proposals))
        self.check('no leaked files or threads after %d steps' % count[0], resources)
        self.alive()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--seconds', type=int, default=60, help='length of the random-use part')
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--output', default=None, help='folder for report.json')
    parser.add_argument('--only', default=None, help='comma separated group names: protocol,malformed,reads,paths,writes,concurrency,lifecycle,filesystem,soak')
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else int(time.time())
    bench = Bench(seed); started = time.time()
    order = ['protocol', 'malformed', 'reads', 'paths', 'writes', 'concurrency', 'lifecycle', 'filesystem', 'soak']
    chosen = args.only.split(',') if args.only else order
    try:
        for name in order:
            if name not in chosen: continue
            start = time.time()
            try:
                bench.g_soak(args.seconds) if name == 'soak' else getattr(bench, 'g_' + name)()
            except Exception as error:
                bench.failures.append({'group': bench.group, 'check': 'group stopped', 'problem': ''.join(traceback.format_exception_only(type(error), error)).strip()[:300]})
            g = bench.groups.get(bench.group, [0, 0])
            print('%-40s %5d checks, %3d failed, %5.1f s' % (bench.group, g[0], g[1], time.time() - start), flush=True)
    finally:
        report = {'passed': not bench.failures, 'seed': seed, 'checks': bench.checks, 'seconds': round(time.time() - started, 1),
                  'groups': {k: {'checks': v[0], 'failed': v[1]} for k, v in bench.groups.items()}, 'failures': bench.failures}
        bench.close()
    if args.output:
        os.makedirs(args.output, exist_ok=True)
        with open(os.path.join(args.output, 'report.json'), 'w') as f: json.dump(report, f, indent=1, ensure_ascii=False)
    seen = {}
    for failure in bench.failures:
        key = (failure['group'], failure['problem'][:70])
        seen.setdefault(key, []).append(failure)
    for (group, _), items in seen.items():
        print('FAIL [%s] %s\n     %s%s' % (group, items[0]['check'], items[0]['problem'], '  (+%d alike)' % (len(items) - 1) if len(items) > 1 else ''))
    print('%s: %d checks, %d failed, seed %d' % ('PASSED' if report['passed'] else 'FAILED', bench.checks, len(bench.failures), seed))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
