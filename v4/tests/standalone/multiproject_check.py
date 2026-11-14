#!/usr/bin/python3
"""Exercise three invented projects over real local HTTP MCP, with no user data.

Only connector registration is simulated by the in-memory Service fixture. An
optional official MCP client check uses a separate temporary Cloudflare tunnel.
No Mistral account credentials or remote account mutations are involved.
"""
import importlib.util
import json
import logging
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from types import SimpleNamespace

BASE = Path(__file__).resolve().parents[2]
OUT = BASE / 'artifacts/multiproject-test26.json'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


web = module('multi_web', BASE / 'backend/web_connector.py')
auto = module('multi_auto', BASE / 'backend/automatic_connector.py')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from connector_service_fixture import Service


class Client:
    def __init__(self, connector, project, *, token=None, sid=None):
        self.connector = connector;self.project = project
        self.token = token if token is not None else connector.projects[project]['token']
        self.sid = sid;self.number = 0

    def request(self, method, params=None, *, project=None, token=None, sid=True, notification=False):
        self.number += 1
        message = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if not notification:message['id'] = self.number
        headers = {'Authorization': 'Bearer ' + (self.token if token is None else token),
                   'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                   'MCP-Protocol-Version': '2025-06-18'}
        if sid and self.sid:headers['Mcp-Session-Id'] = self.sid
        url = 'http://127.0.0.1:' + str(self.connector.server.server_port) + '/mcp/' + (project or self.project)
        request = urllib.request.Request(url, data=json.dumps(message).encode(), headers=headers)
        try:response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:response = error
        with response:
            raw = response.read();body = json.loads(raw) if raw else None
            return response.status, response.headers, body

    def initialize(self):
        status, headers, body = self.request('initialize', {'protocolVersion': '2025-06-18',
                    'capabilities': {}, 'clientInfo': {'name': 'Invented multi-project check', 'version': '1'}}, sid=False)
        assert status == 200, ('initialize', status)
        self.sid = headers['Mcp-Session-Id']
        assert body['result']['serverInfo']['name'] == 'VibeZ-local-files'
        assert self.request('notifications/initialized', notification=True)[0] == 202
        return self

    def tool(self, name, arguments=None, *, expect_error=False):
        status, _, body = self.request('tools/call', {'name': name, 'arguments': arguments or {}})
        assert status == 200, ('tool', name, status)
        result = body['result']
        if expect_error:
            assert result.get('isError'), ('expected rejected tool', name)
            return result
        assert not result.get('isError'), ('unexpected rejected tool', name, result)
        return json.loads(result['content'][0]['text'])


def official_sdk_child():
    # The parent supplies only a generated fixture URL/token/content via stdin.
    import asyncio
    import importlib.metadata
    from datetime import timedelta
    from urllib.parse import urlsplit
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    logging.disable(logging.CRITICAL)
    data = json.load(sys.stdin)
    host = urlsplit(data['url']).hostname
    import socket, ipaddress
    try:address = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    except socket.gaierror:address = auto.public_addresses(host)[0]
    assert ipaddress.ip_address(address).is_global, 'Only public fixture addresses are accepted'
    class PublicTransport(httpx.AsyncHTTPTransport):
        async def handle_async_request(self, request):
            if request.url.host != host:raise ValueError('Unexpected fixture destination')
            request.headers['Host'] = host
            request.extensions['sni_hostname'] = host
            request.url = request.url.copy_with(host=address)
            return await super().handle_async_request(request)
    def factory(**kwargs):
        return httpx.AsyncClient(transport=PublicTransport(), trust_env=False, **kwargs)
    async def check():
        async with streamablehttp_client(data['url'], httpx_client_factory=factory,
                    headers={'Authorization': 'Bearer ' + data['token']}, timeout=12,
                    sse_read_timeout=12) as (read, write, _):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=12)) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                result = await session.call_tool('read_file', {'path': 'marker.txt'})
                assert not result.isError
                value = json.loads(result.content[0].text)
                assert value['content'] == data['expected']
                return {'passed': True, 'sdk': importlib.metadata.version('mcp'),
                        'initialized': True, 'protocol': initialized.protocolVersion,
                        'tools': sorted(tool.name for tool in tools.tools),
                        'invented_fixture_read': True, 'certificate_validation': True,
                        'original_hostname_sni': True, 'live_mistral': False}
    print(json.dumps(asyncio.run(check())))


def run():
    report = {'version': web.VERSION, 'passed': False, 'fixture_only': True,
              'real_local_http_mcp': True, 'live_mistral': False,
              'mistral_account_mutations': False, 'user_profiles_accessed': False,
              'user_projects_accessed': False,
              'registration': 'in-memory Service fixture with real local HTTP discovery and overview',
              'projects': {}, 'checks': {}}
    c = None;manager = None;service = None
    try:
        with tempfile.TemporaryDirectory(prefix='vibez-multiproject-') as temp:
            root = Path(temp);private = root / 'private';events = [];auth_calls = [];tunnel_generation = []
            projects = []
            for label in ['Alpha', 'Beta', 'Gamma']:
                folder = root / label;folder.mkdir();(folder / 'notes').mkdir()
                original = 'Only invented project ' + label + ' contains this marker.\n'
                (folder / 'marker.txt').write_text(original)
                (folder / 'notes/info.md').write_text('Invented notes for ' + label + '.\n')
                (folder / '.private-fixture').write_text('Hidden invented text for ' + label)
                projects.append({'id': str(uuid.uuid4()), 'name': 'Fixture ' + label,
                                 'label': label, 'folder': folder, 'original': original,
                                 'approved': 'Approved invented text for ' + label + '.\n'})

            def configure(connector, *, fresh=False):
                nonlocal service
                def authenticate(cancel, announce):
                    auth_calls.append(True)
                    return 'invented-account-fixture-credential-never-sent-to-mistral'
                engine = SimpleNamespace(web=connector, key='', lock=threading.RLock(),
                            external_output=events.append, auth=SimpleNamespace(authenticate=authenticate))
                if service is None:service = Service(auto.SetupError, connector)
                else:service.web = connector
                def fake_tunnel():
                    if connector.tunnel_status != 'running':tunnel_generation.append(True)
                    connector.tunnel_url = 'https://fixture-' + str(len(tunnel_generation)) + '.trycloudflare.com'
                    connector.tunnel_status = 'running';connector.state()
                connector.start_tunnel = fake_tunnel
                return auto.AutomaticConnector(engine, api_factory=service.api,
                    probe=lambda url, token, guard, cancel: (guard(), service.discover(url.rsplit('/', 1)[1], token), guard()))

            def connect(project):
                manager.connect(project['id']);manager.job['thread'].join(8)
                assert not manager.job['thread'].is_alive(), 'Fixture setup timeout'
                assert manager.states[project['id']]['status'] == 'connected', manager.states[project['id']]
                assert c.enabled == {project['id']}, 'Only the chosen project may be enabled'
                return Client(c, project['id']).initialize()

            def check(name, condition):
                report['checks'][name] = bool(condition)
                assert condition, name

            c = web.Connector(events.append, private, approval_wait=0)
            for p in projects:
                c.select(p);c.link(p['id'], p['folder'])
            manager = configure(c)
            previous = None;previous_proposal = None;previous_folder_text = None
            for index, p in enumerate(projects):
                c.select(p);manager.context()
                if previous is not None:
                    check(p['label'] + '_switch_pauses_previous', previous.request('ping')[0] == 403)
                    check(p['label'] + '_switch_revokes_pending_proposal', c.proposals[previous_proposal]['status'] == 'revoked')
                    try:c.resolve(previous_proposal, True)
                    except ValueError:pass
                    else:raise AssertionError('Old project proposal was accepted after switch')
                    check(p['label'] + '_previous_disk_unchanged_after_switch', previous_folder_text[0].read_text() == previous_folder_text[1])
                client = connect(p);project_checks = report['projects'][p['label']] = {}
                names = {t['name'] for t in client.request('tools/list')[2]['result']['tools']}
                project_checks['all_five_tools'] = names == auto.REQUIRED
                entries = client.tool('list_directory', {'path': '.'})['entries']
                project_checks['own_listing'] = {e['name'] for e in entries} == {'marker.txt', 'notes'}
                overview = client.tool('workspace_overview')
                project_checks['own_overview'] = overview['files'] == 2 and overview['directories'] == 1
                project_checks['own_read'] = client.tool('read_file', {'path': 'marker.txt'})['content'] == p['original']
                other = projects[(index + 1) % len(projects)]
                project_checks['other_token_denied'] = client.request('initialize', token=c.projects[other['id']]['token'], sid=False)[0] == 401
                project_checks['token_cannot_select_other_project'] = client.request('initialize', project=other['id'], sid=False)[0] == 401
                if previous is not None:
                    project_checks['previous_session_cannot_be_reused'] = client.request('ping', sid=False)[0] == 400
                    cross = Client(c, p['id'], sid=previous.sid)
                    project_checks['previous_session_bound_to_previous_project'] = cross.request('ping')[0] == 404
                symlink = p['folder'] / 'cross-project-link';symlink.symlink_to(other['folder'] / 'marker.txt')
                blocked = ['../' + other['label'] + '/marker.txt', str(other['folder'] / 'marker.txt'),
                           'cross-project-link', '.private-fixture']
                rejected = [client.tool('read_file', {'path': path}, expect_error=True) for path in blocked]
                project_checks['parent_absolute_symlink_hidden_reads_denied'] = all(r['isError'] for r in rejected)
                project_checks['other_project_marker_not_disclosed'] = all(other['original'] not in json.dumps(r) for r in rejected)
                client.tool('write_file', {'path': '../' + other['label'] + '/marker.txt', 'content': 'Never save'}, expect_error=True)
                project_checks['cross_project_write_denied'] = (other['folder'] / 'marker.txt').read_text() == (other['approved'] if index == len(projects) - 1 else other['original'])
                symlink.unlink()
                rejected = client.tool('write_file', {'path': 'marker.txt', 'content': 'Rejected fixture edit'})
                project_checks['proposal_does_not_save'] = (p['folder'] / 'marker.txt').read_text() == p['original'] and rejected['status'] == 'pending'
                c.resolve(rejected['proposal_id'], False)
                project_checks['rejection_keeps_disk'] = client.tool('change_status', {'proposal_id': rejected['proposal_id']})['status'] == 'rejected' and (p['folder'] / 'marker.txt').read_text() == p['original']
                proposed = client.tool('write_file', {'path': 'marker.txt', 'content': p['approved']})
                c.resolve(proposed['proposal_id'], True)
                project_checks['approval_saves_only_current_project'] = (p['folder'] / 'marker.txt').read_text() == p['approved'] and client.tool('change_status', {'proposal_id': proposed['proposal_id']})['written']
                client.tool('read_file', {'path': 'marker.txt'})
                pending = client.tool('write_file', {'path': 'marker.txt', 'content': 'Pending fixture edit must be revoked on switch'})
                project_checks['remote_cannot_approve'] = client.request('vibez/resolve', {'allow': True})[2]['error']['code'] == -32601
                for name, passed in project_checks.items():assert passed, p['label'] + ': ' + name
                previous = client;previous_proposal = pending['proposal_id'];previous_folder_text = (p['folder'] / 'marker.txt', p['approved'])

            check('three_distinct_private_connectors', len(service.connectors) == 3 and all(v['visibility'] == 'private' for v in service.connectors.values()))
            check('three_distinct_project_tokens', len({p['token'] for p in c.projects.values()}) == 3)
            check('one_authorization_for_three_projects_in_one_session', len(auth_calls) == 1)
            first = projects[0];c.select(first);manager.context();client = connect(first)
            connector_id = manager.registry.records[first['id']]['id']
            client.tool('read_file', {'path': 'marker.txt'})
            proposal = client.tool('write_file', {'path': 'marker.txt', 'content': 'Must never move to replacement root'})
            old_sid = client.sid;old_token = client.token
            replacement = root / 'AlphaReplacement';replacement.mkdir()
            replacement_text = 'Replacement Alpha invented fixture only.\n';(replacement / 'marker.txt').write_text(replacement_text)
            c.link(first['id'], replacement);manager.context()
            check('relink_rotates_token', c.projects[first['id']]['token'] != old_token)
            check('relink_invalidates_old_token', client.request('ping')[0] == 401)
            check('relink_starts_paused', Client(c, first['id']).request('initialize', sid=False)[0] == 403)
            try:c.resolve(proposal['proposal_id'], True)
            except ValueError:pass
            else:raise AssertionError('Relinked proposal was accepted')
            check('relink_invalidates_old_proposal', c.proposals[proposal['proposal_id']]['status'] == 'revoked')
            client = connect(first)
            check('relink_reuses_same_connector', manager.registry.records[first['id']]['id'] == connector_id and len(service.connectors) == 3)
            check('relink_invalidates_old_session', Client(c, first['id'], sid=old_sid).request('ping')[0] == 404)
            check('replacement_root_readable', client.tool('read_file', {'path': 'marker.txt'})['content'] == replacement_text)
            check('relink_changes_neither_root_without_approval', (first['folder'] / 'marker.txt').read_text() == first['approved'] and (replacement / 'marker.txt').read_text() == replacement_text)

            saved = {key: dict(value) for key, value in c.projects.items()}
            saved_ids = {key: value['id'] for key, value in manager.registry.records.items()}
            manager.close();c.close();manager = None
            c = web.Connector(events.append, private, approval_wait=0)
            check('restart_preserves_all_three_bindings', c.projects == saved)
            check('restart_has_no_active_project_or_network_access', not c.enabled and c.active is None and c.server is None)
            check('bindings_remain_private_permissions', c.file.stat().st_mode & 0o777 == 0o600)
            manager = configure(c, fresh=True);c.select(first);manager.context();client = connect(first)
            check('restart_connect_reuses_existing_project_connector', manager.registry.records[first['id']]['id'] == saved_ids[first['id']] and len(service.connectors) == 3)
            check('restart_refreshes_temporary_address', len(tunnel_generation) == 2)
            check('restart_actual_http_reads_selected_saved_root', client.tool('read_file', {'path': 'marker.txt'})['content'] == replacement_text)
            check('restart_does_not_enable_other_projects', c.enabled == {first['id']})
            check('project_registry_contains_no_tokens', all(p['token'] not in manager.registry.path.read_text() for p in c.projects.values()))
            check('all_other_fixture_disks_keep_approved_contents', all((p['folder'] / 'marker.txt').read_text() == p['approved'] for p in projects))

            sdk_python = Path('/tmp/vibez-mcp-client-check/bin/python')
            if sdk_python.is_file():
                c.tunnel_status = 'stopped';c.tunnel_url = ''
                type(c).start_tunnel(c)
                deadline = time.monotonic() + 50
                while c.tunnel_status == 'starting' and time.monotonic() < deadline:time.sleep(.1)
                assert c.tunnel_status == 'running', 'Temporary fixture HTTPS tunnel did not start'
                url = c.tunnel_url + '/mcp/' + first['id'];token = c.projects[first['id']]['token']
                auto.wait_ready(url, token, lambda: None, threading.Event())
                result = subprocess.run([str(sdk_python), str(Path(__file__).resolve()), '--sdk-child'],
                    input=json.dumps({'url': url, 'token': token, 'expected': replacement_text}),
                    text=True, capture_output=True, timeout=45)
                if result.returncode != 0:raise AssertionError('Official SDK fixture HTTPS check failed: ' + result.stderr[-1500:])
                report['official_sdk_https'] = json.loads(result.stdout)
            else:
                report['official_sdk_https'] = {'passed': False, 'skipped': True, 'reason': 'Temporary official SDK runtime absent'}
            report['passed'] = True
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if manager is not None:manager.close()
        if c is not None:
            c.close();report['fixture_network_stopped'] = c.tunnel is None and c.server is None
        report['check_count'] = len(report['checks']) + sum(len(p) for p in report['projects'].values())
        OUT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    if '--sdk-child' in sys.argv:official_sdk_child()
    else:run()
