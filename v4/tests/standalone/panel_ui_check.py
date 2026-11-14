#!/usr/bin/python3
"""Inspect the shipped files panel with invented data in isolated headless Chromium.

No app profile, visible window, remote account or real workspace is accessed.
"""
import argparse
import asyncio
import base64
import json
import hashlib
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

BASE = Path(__file__).resolve().parents[2]
VERSION = json.loads((BASE / 'desktop/src-tauri/tauri.conf.json').read_text())['version']
PROJECT = {'id': 'cace260d-d95d-4859-b45b-f56f185f15da', 'name': 'CityTripXL'}
FIXTURE_PATH = '/voorbeelden/CityTripXL'
IMPORT_BINDING = 'a'*64
CONVERSATION_ALIAS = 'chat-cace260d-d95d-4859-b45b-f56f185f15da'
CONVERSATION_REMOTE = '44444444-5555-4666-8777-888888888888'
ROOT_ONE='1'*32
ROOT_TWO='2'*32

SHIM = r"""
window.__calls=[];window.__errors=[];window.__listeners={};
window.addEventListener('error',e=>window.__errors.push(String(e.message)));
window.addEventListener('unhandledrejection',e=>window.__errors.push(String(e.reason)));
window.__emit=(name,payload)=>{for(const fn of window.__listeners[name]||[])fn({payload});};
window.__fixtureState=__INITIAL__;
window.__fixtureUpdate={status:'current',kind:'native',automatic:true};
window.__setFixture=(state,status='idle',message='',error_code,pause_reason)=>{
 window.__fixtureState=JSON.parse(JSON.stringify(state));
 window.__emit('app-engine',window.__fixtureState);
 window.__fixtureAuto={type:'web_auto',project_id:state.project?.id,status,message,error_code,pause_reason};
 window.__emit('app-engine',window.__fixtureAuto);
};
window.__TAURI__={event:{listen:async(name,fn)=>{
 (window.__listeners[name]||=[]).push(fn);return ()=>{};
}},core:{invoke:async(name,args)=>{
 window.__calls.push({name,args});
 if(name==='language_get')return {language:'nl',resolved:'nl',site_locale:'nl',revision:1,pending:false};
 if(name==='app_info')return {version:__VERSION__,screen:'Scherm 1'};
 if(name==='alpha_update_state')return window.__fixtureUpdate;
 if(name==='alpha_update_check'){
  if(window.__holdUpdateCheck){window.__holdUpdateCheck=false;return await new Promise(resolve=>window.__resolveUpdateCheck=resolve);}
  return window.__fixtureUpdate;
 }
 if(name==='alpha_update_allow')return {kind:'flatpak',status:'ready',automatic:true,consent_required:false};
 if(name==='web_choose_folder'){
  if(window.__failFolder){window.__failFolder=false;throw new Error('Voorbeeld: map kiezen geweigerd.');}
  if(window.__holdFolderChooser){window.__holdFolderChooser=false;return await new Promise((resolve,reject)=>{window.__resolveFolderChooser=resolve;window.__rejectFolderChooser=reject;});}
  if(Object.prototype.hasOwnProperty.call(window,'__nextFolderResult')){const result=window.__nextFolderResult;delete window.__nextFolderResult;return result;}
  return '/voorbeelden/CityTripXL';
 }
 if(name==='project_open_folder'&&window.__holdFolderOpen){window.__holdFolderOpen=false;return await new Promise((resolve,reject)=>{window.__resolveFolderOpen=resolve;window.__rejectFolderOpen=reject;});}
 if(name==='project_import_choose'||name==='project_import_commit'||name==='project_import_resolve'){
  if(window.__failImport){const message=window.__failImport;window.__failImport='';throw new Error(message);}
  if(window.__cancelImport){window.__cancelImport=false;return false;}
  return true;
 }
 if(name==='project_details_action'&&window.__failDetails){window.__failDetails=false;throw new Error('Voorbeeld: projectinstelling niet gewijzigd.');}
 if(name==='project_rules_edit'){
  if(args.action==='open'){
   if(window.__holdRulesOpen){window.__holdRulesOpen=false;return await new Promise((resolve,reject)=>{window.__resolveRulesOpen=resolve;window.__rejectRulesOpen=reject;});}
   return {project_id:args.projectId,value:window.__rulesValue||'Voorbeeldregels uit het officiële projectformulier.',nonce:'fixture-editor-nonce'};
  }
  if(args.action==='save'){
   if(window.__failRulesSave){window.__failRulesSave=false;throw new Error('Voorbeeld: projectregels niet opgeslagen.');}
   if(window.__holdRulesSave){window.__holdRulesSave=false;return await new Promise((resolve,reject)=>{window.__resolveRulesSave=resolve;window.__rejectRulesSave=reject;});}
   window.__rulesValue=args.value;
   if(window.__rulesDetails){window.__rulesDetails.instructions=args.value;window.__emit('project-details',window.__rulesDetails);}
   return {project_id:args.projectId,saved:true};
  }
  return null;
 }
 if(name==='web_command'){
  const p=args.payload,s=window.__fixtureState;
  if(p.action==='web_hello')window.__emit('app-engine',s);
  if(p.action==='web_create_folder'){
   if(window.__failFolderCreateCommand){window.__failFolderCreateCommand=false;throw new Error('Voorbeeld: de aanvraag kon niet worden verzonden.');}
   const result={type:'web_create_folder_result',project_id:p.project_id,workspace_binding:p.workspace_binding,request_id:p.request_id,name:p.name};
   if(window.__folderCreateError){result.error=window.__folderCreateError;window.__folderCreateError='';}else result.created=true;
   window.__pendingFolderResult=result;
   if(window.__deferFolderResult){window.__deferFolderResult=false;return null;}
   window.__emit('app-engine',result);return null;
  }
  if(p.action==='web_link'){
   const id='1'.repeat(32);s.folders=[{id,path:p.path,alias:'Map1'}];s.target_folder_id=id;s.workspace_binding='d'.repeat(64);
   s.folder=p.path;s.enabled=false;s.auto_approved=false;s.manually_paused=false;s.import_binding='a'.repeat(64);s.local_files=[];
   window.__setFixture(s,'idle');
  }
  if(p.action==='web_connect'){
   s.enabled=true;s.tunnel_status='running';s.url='https://fixture.invalid/mcp/project';s.auto_approved=true;s.manually_paused=false;
   window.__setFixture(s,'connected','Connected to Mistral. You can work with this project folder in your web conversation.');
  }
  if(p.action==='web_abort'||(p.action==='web_enable'&&!p.allow)){
   s.enabled=false;s.manually_paused=true;window.__setFixture(s,'paused','',undefined,'manual');
  }
  if(p.action==='web_approve'){
   s.pending=s.pending.filter(item=>item.id!==p.id);window.__emit('app-engine',s);
  }
  if(p.action==='web_unlink'){
   s.folders=[];s.target_folder_id=null;s.workspace_binding='';s.folder=null;s.enabled=false;s.auto_approved=false;s.manually_paused=false;s.import_binding=null;s.local_files=[];window.__setFixture(s,'idle');
  }
 }
 return null;
}}};
"""


def fixture(*, linked=True, enabled=False, pending=None, auto_approved=False, manually_paused=False):
    data={'type': 'web_connector', 'project': PROJECT,
            'projects': [PROJECT], 'folder': FIXTURE_PATH if linked else None,
            'project_goal':'', 'recent_activity':[],
            'enabled': enabled, 'tunnel_status': 'running' if enabled else 'stopped',
            'auto_approved': auto_approved, 'manually_paused': manually_paused,
            'import_binding': IMPORT_BINDING if linked else None,
            'local_files': [{'name': 'controle.txt'}] if linked else [],
            'url': 'https://fixture.invalid/mcp/project' if enabled else '',
            'token': 'invented-fixture-token-no-real-access',
            'pending': pending or [],
            'activity': [{'project': 'CityTripXL', 'action': 'read_file', 'path': 'README.md'}]}
    return single_root_metadata(data)


def conversation_fixture(*, draft=False, linked=True, enabled=False,
                         alias=CONVERSATION_ALIAS, name=None, binding=IMPORT_BINDING):
    data=fixture(linked=linked,enabled=enabled)
    project={'id':alias,'kind':'conversation','draft':draft,
             'conversation_id':None if draft else CONVERSATION_REMOTE,
             'name':('' if draft else 'Reisideeën') if name is None else name,
             'url':'https://chat.mistral.ai/work' if draft else 'https://chat.mistral.ai/work/'+CONVERSATION_REMOTE}
    data.update(project=project,projects=[project],folder='/voorbeelden/Gespreksmap' if linked else None,
                import_binding=binding if linked else None,activity=[])
    return single_root_metadata(data)


def single_root_metadata(data):
    folder=data.get('folder');project=data.get('project') or {}
    data['folders']=[{'id':ROOT_ONE,'path':folder,'alias':'Map1'}] if folder else []
    data['target_folder_id']=ROOT_ONE if folder else None
    data['workspace_binding']=hashlib.sha256(json.dumps([project.get('id'),folder]).encode()).hexdigest() if folder else ''
    return data




class CDP:
    def __init__(self, ws):
        self.ws = ws
        self.sequence = 0
        self.exceptions = []

    async def call(self, method, params=None):
        self.sequence += 1
        number = self.sequence
        await self.ws.send(json.dumps({'id': number, 'method': method, 'params': params or {}}))
        while True:
            response = json.loads(await asyncio.wait_for(self.ws.recv(), 15))
            if response.get('method') == 'Runtime.exceptionThrown':
                self.exceptions.append(response.get('params', {}).get('exceptionDetails', {}))
            if response.get('id') != number:
                continue
            if 'error' in response:
                raise RuntimeError(response['error'])
            return response.get('result', {})

    async def evaluate(self, expression):
        value = await self.call('Runtime.evaluate', {'expression': expression,
                                'returnByValue': True, 'awaitPromise': True})
        if 'exceptionDetails' in value:
            raise RuntimeError(value['exceptionDetails'])
        return value.get('result', {}).get('value')

    async def set_fixture(self, state, status='idle', message='', error_code=None, pause_reason=None):
        state=json.loads(json.dumps(state))
        if len(state.get('folders',[]))<=1: state=single_root_metadata(state)
        await self.evaluate('window.__setFixture(' + ','.join(json.dumps(x) for x in
                            [state, status, message, error_code, pause_reason]) + ');true')
        await asyncio.sleep(.08)

    async def screenshot(self, path):
        result = await self.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
        path.write_bytes(base64.b64decode(result['data']))


async def exercise(ws_url, url, out, width, height, report):
    async with websockets.connect(ws_url, max_size=10_000_000, ping_interval=None) as ws:
        c = CDP(ws)
        await c.call('Page.enable')
        await c.call('Runtime.enable')
        await c.call('Network.enable')
        await c.call('Network.setBlockedURLs', {'urls': ['http://*', 'https://*']})
        await c.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
                    'deviceScaleFactor': 1, 'mobile': False})
        await c.call('Page.navigate', {'url': url})
        for _ in range(100):
            if await c.evaluate("Boolean(window.__calls?.some(x=>x.name==='web_command'&&x.args.payload.action==='web_hello'))"):
                break
            await asyncio.sleep(.1)
        else:
            raise RuntimeError('The shipped panel did not finish its fixture startup')
        await c.evaluate("window.__visible=id=>{const n=document.getElementById(id);return Boolean(n&&!n.hidden&&n.checkVisibility());};true")
        await c.evaluate("window.__rootName=()=>String(window.__fixtureState.folder||'').split(String.fromCharCode(92)).join('/').split('/').filter(Boolean).pop()||'';window.__folderCopy=key=>window.vibezLanguage.t(key).split('{folder}').join(__rootName());true")
        checks = report['checks']

        async def check(name, expression):
            checks[name] = bool(await c.evaluate(expression))
            if not checks[name]:
                raise AssertionError(name)

        # Backend status alone never opens sign-in or starts a connection.
        await check('startup_does_not_connect_or_open_login', "!window.__calls.some(x=>x.name==='app_open_login'||(x.name==='web_command'&&x.args.payload.action==='web_connect'))")
        await check('language_menu_has_33_languages_plus_system_without_russian', "window.VIBEZ_TRANSLATIONS.options.filter(o=>o.code!=='system').length===33&&document.getElementById('language').options.length===34&&[...document.getElementById('language').options].every(o=>o.value!=='ru'&&!/русский/i.test(o.textContent))")
        await c.set_fixture(fixture(auto_approved=True), 'paused', pause_reason='sign_in')
        await check('missing_sign_in_has_plain_status_and_one_connect_action', "document.getElementById('auto-status').textContent==='Geef Mistral toestemming om automatisch te verbinden'&&__visible('auto-connect')&&document.getElementById('auto-connect').textContent==='Verbinden'&&!__visible('auto-open-login')")
        await c.evaluate("window.__calls=[];window.__emit('language-state',{language:'en',resolved:'en',site_locale:'en',revision:2,pending:false});true")
        await check('automatic_sign_in_status_translates_to_english', "document.getElementById('auto-status').textContent==='Allow Mistral to connect automatically'")
        await c.evaluate("window.__emit('language-state',{language:'ja',resolved:'ja',site_locale:'en',revision:3,pending:false});true")
        await check('automatic_sign_in_status_translates_to_japanese', "document.getElementById('auto-status').textContent===window.VIBEZ_TRANSLATIONS.new.ja.filesSignInRequired")
        await c.evaluate("window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:4,pending:false});window.__emit('chrome-panel','files');true")
        for _ in range(3):
            await c.evaluate("webCommand('web_hello');true")
        other = fixture(auto_approved=True)
        other['project'] = {'id': 'code-229ee257-1234-4567-890a-123456789abc', 'name': 'Code Beta'}
        other['projects'] = [other['project']]
        other['folder'] = '/voorbeelden/Beta'
        await c.set_fixture(other, 'paused', pause_reason='context')
        await c.set_fixture(fixture(auto_approved=True), 'paused', pause_reason='sign_in')
        await check('status_replays_language_and_project_changes_do_not_connect_or_open_login', "!window.__calls.some(x=>x.name==='app_open_login'||(x.name==='web_command'&&x.args.payload.action==='web_connect'))")
        await c.set_fixture(fixture(auto_approved=True, manually_paused=True), 'paused', pause_reason='manual')
        await check('manual_pause_is_explicit_and_keeps_one_resume_action', "document.getElementById('auto-status').textContent==='Door jou gepauzeerd'&&__visible('auto-connect')&&document.getElementById('auto-connect').textContent==='Verbinden'&&!__visible('auto-open-login')")
        await c.set_fixture(fixture(auto_approved=True, manually_paused=True), 'starting')
        await check('automatic_connecting_keeps_existing_cancel_button', "document.getElementById('auto-status').textContent==='Verbinding maken…'&&document.getElementById('auto-connect').textContent==='Annuleren'")
        await c.set_fixture(fixture(auto_approved=True, manually_paused=True), 'error', 'Voorbeeld: opnieuw proberen.')
        await check('connection_error_outranks_stale_pause_flag', "document.getElementById('auto-status').textContent==='Verbinden is niet gelukt. Probeer opnieuw.'&&document.getElementById('auto-connect').textContent==='Opnieuw proberen'")
        await c.set_fixture(fixture(enabled=True, auto_approved=True, manually_paused=True), 'connected')
        await check('connected_outranks_stale_pause_flag', "document.getElementById('auto-status').textContent==='Verbonden met Mistral'&&!__visible('auto-connect')")

        # Connected: the everyday view contains no technical setup controls.
        await c.set_fixture(fixture(enabled=True), 'connected',
                            'Connected to Mistral. You can work with this project folder in your web conversation.')
        await c.evaluate("document.getElementById('files-options').open=false;true")
        await check('connected_folder_visible', "__visible('folder-summary')&&document.getElementById('web-folder').textContent.includes('/voorbeelden/CityTripXL')")
        await check('connected_main_button_hidden', "!__visible('auto-connect')")
        await check('connected_status_short', "__visible('auto-status')&&document.getElementById('auto-status').textContent.length>0&&document.getElementById('auto-status').textContent.length<100")
        await check('technical_setup_hidden_by_default', "!document.getElementById('files-options').open&&!__visible('advanced-setup')&&!__visible('web-token')&&!__visible('web-pause')")
        await check('no_horizontal_overflow', 'document.documentElement.scrollWidth<=innerWidth')
        await c.screenshot(out / 'connected.png')

        # Changing the chosen workspace is available directly on its folder card.
        await check('linked_workspace_change_is_visible_beside_open_without_options', "__visible('web-folder-button')&&!document.getElementById('web-folder-button').disabled&&document.getElementById('web-folder-button').textContent===window.vibezLanguage.t('otherWorkspace')&&document.getElementById('web-folder-button').closest('.folder-actions')?.closest('#folder-summary')&&document.getElementById('open-workspace').parentElement===document.getElementById('web-folder-button').parentElement&&document.querySelectorAll('#web-folder-button').length===1&&!document.getElementById('files-options').open")
        await c.evaluate("window.__calls=[];window.__nextFolderResult='/voorbeelden/Nieuwe-projectmap';document.getElementById('web-folder-button').click();true")
        await asyncio.sleep(.08)
        await check('visible_change_action_replaces_an_already_linked_workspace_only_for_current_project', "window.__calls.filter(x=>x.name==='web_choose_folder').length===1&&window.__calls.filter(x=>x.name==='web_command'&&x.args.payload.action==='web_link').length===1&&window.__calls.some(x=>x.name==='web_command'&&x.args.payload.action==='web_link'&&x.args.payload.project_id==="+json.dumps(PROJECT['id'])+"&&x.args.payload.path==='/voorbeelden/Nieuwe-projectmap')&&document.getElementById('web-folder').textContent==='/voorbeelden/Nieuwe-projectmap'&&document.getElementById('web-folder-name').textContent==='Nieuwe-projectmap'&&__visible('web-folder-button')&&!document.getElementById('web-folder-button').disabled&&__visible('auto-connect')&&!document.getElementById('files-options').open")
        await c.evaluate("window.__calls=[];window.__nextFolderResult=null;document.getElementById('web-folder-button').click();true")
        await asyncio.sleep(.08)
        await check('cancelling_workspace_change_keeps_the_new_folder_and_does_not_relink', "window.__calls.filter(x=>x.name==='web_choose_folder').length===1&&!window.__calls.some(x=>x.name==='web_command'&&x.args.payload.action==='web_link')&&document.getElementById('web-folder').textContent==='/voorbeelden/Nieuwe-projectmap'&&__visible('web-folder-button')&&!document.getElementById('web-folder-button').disabled")
        await c.screenshot(out / 'workspace-change-visible.png')
        await c.set_fixture(fixture(enabled=True),'connected')

        # Less common controls are available in one disclosure, including pause.
        await c.evaluate("document.querySelector('#files-options>summary').click();true")
        await check('options_contains_pause_and_refresh_while_folder_change_stays_on_the_card', "__visible('web-folder-button')&&__visible('web-pause')&&__visible('connection-refresh')")
        await c.evaluate("document.getElementById('web-pause').click();true")
        await asyncio.sleep(.08)
        await check('pause_uses_existing_scoped_action', "window.__calls.some(x=>x.name==='web_command'&&x.args.payload.action==='web_enable'&&x.args.payload.allow===false)&&__visible('auto-connect')")
        await check('explicit_pause_remains_visible_with_options_closed', "!document.getElementById('files-options').open&&document.getElementById('auto-status').textContent==='Door jou gepauzeerd'")
        await c.evaluate("window.__calls=[];document.getElementById('files-options').open=false;document.getElementById('auto-connect').click();true")
        await asyncio.sleep(.08)
        await check('resume_uses_automatic_connection', "window.__calls.filter(x=>x.name==='web_command'&&x.args.payload.action==='web_connect').length===1&&!__visible('auto-connect')")

        # First use: choosing and creating a main folder are distinct native modes.
        await c.set_fixture(fixture(linked=False), 'idle')
        await c.evaluate("document.getElementById('files-options').open=false;true")
        await check('unlinked_has_choose_and_create_actions_and_explains_main_folder', "__visible('auto-connect')&&!document.getElementById('auto-connect').disabled&&document.getElementById('auto-connect').textContent===window.vibezLanguage.t('chooseWorkspace')&&__visible('create-workspace')&&!document.getElementById('create-workspace').disabled&&document.getElementById('create-workspace').textContent===window.vibezLanguage.t('createWorkspace')&&__visible('main-folder-setup')&&document.getElementById('main-folder-setup').textContent===window.vibezLanguage.t('createWorkspaceHelp')&&document.getElementById('files-section-heading').textContent===window.vibezLanguage.t('mainFolderSetup')&&!__visible('project-drop-zone')&&!__visible('web-folder-button')")
        await c.screenshot(out / 'unlinked.png')
        await c.evaluate("document.getElementById('auto-connect').click();true")
        await asyncio.sleep(.12)
        await check('map_choice_links_only_fixture_project', "window.__calls.some(x=>x.name==='web_choose_folder'&&x.args.create===false)&&window.__calls.some(x=>x.name==='web_command'&&x.args.payload.action==='web_link'&&x.args.payload.path==='/voorbeelden/CityTripXL'&&x.args.payload.project_id==='cace260d-d95d-4859-b45b-f56f185f15da')")

        # Creating a root uses the new native create mode and never starts Mistral.
        await c.set_fixture(fixture(linked=False),'idle')
        await c.evaluate("window.__calls=[];window.__holdFolderChooser=true;document.getElementById('create-workspace').click();document.getElementById('create-workspace').click();document.getElementById('auto-connect').click();true")
        await check('main_folder_creation_blocks_duplicate_and_choose_while_native_dialog_is_open', "window.__calls.length===1&&window.__calls[0].name==='web_choose_folder'&&window.__calls[0].args.create===true&&document.getElementById('create-workspace').disabled&&document.getElementById('auto-connect').disabled&&!document.getElementById('web-folder').textContent")
        await c.evaluate("window.__resolveFolderChooser('/voorbeelden/Nieuwe-hoofdmap');true")
        await asyncio.sleep(.04)
        await check('created_main_folder_becomes_the_only_root_with_its_name_as_title', "window.__calls.filter(x=>x.name==='web_command'&&x.args.payload.action==='web_link').length===1&&window.__fixtureState.folders.length===1&&document.getElementById('web-folder').textContent==='/voorbeelden/Nieuwe-hoofdmap'&&document.getElementById('files-section-heading').textContent==='Nieuwe-hoofdmap'&&__visible('project-drop-zone')&&__visible('main-folder-setup')&&document.getElementById('main-folder-setup').textContent===window.vibezLanguage.t('createWorkspaceHelp')&&!__visible('create-workspace')&&!window.__calls.some(x=>x.name==='app_open_login'||x.args?.payload?.action==='web_connect')")
        await c.set_fixture(fixture(linked=False),'idle')
        await c.evaluate("window.__calls=[];window.__nextFolderResult=null;document.getElementById('create-workspace').click();true")
        await asyncio.sleep(.04)
        await check('cancelling_main_folder_creation_leaves_both_actions_ready_and_no_root', "window.__calls.length===1&&window.__calls[0].args.create===true&&!document.getElementById('web-folder').textContent&&!document.getElementById('create-workspace').disabled&&!document.getElementById('auto-connect').disabled&&__visible('main-folder-setup')")
        await c.evaluate("window.__calls=[];window.__failFolder=true;document.getElementById('create-workspace').click();true")
        await asyncio.sleep(.04)
        await check('failed_main_folder_creation_has_localized_error_and_allows_retry', "window.__calls.length===1&&window.__calls[0].args.create===true&&document.getElementById('auto-status').textContent===window.vibezLanguage.t('operationFailed')&&!document.getElementById('create-workspace').disabled&&!document.getElementById('web-folder').textContent")
        await c.set_fixture(fixture(linked=False),'idle')
        await c.evaluate("window.__calls=[];window.__holdFolderChooser=true;document.getElementById('create-workspace').click();true")
        await c.set_fixture(conversation_fixture(draft=True,linked=False),'idle')
        await c.evaluate("window.__resolveFolderChooser('/voorbeelden/Oud-project');true")
        await asyncio.sleep(.04)
        await check('late_created_root_cannot_link_to_a_different_project_or_conversation', "window.__calls.length===1&&!document.getElementById('web-folder').textContent&&!__visible('auto-status')&&!document.getElementById('create-workspace').disabled")
        await c.evaluate("window.__creationLocaleFailures=[];(()=>{let revision=20;for(const option of window.VIBEZ_TRANSLATIONS.options.filter(o=>o.code!=='system')){window.__emit('language-state',{language:option.code,resolved:option.code,site_locale:'en',revision:revision++,pending:false});const expected=window.VIBEZ_TRANSLATIONS.new[option.code],choose=document.getElementById('auto-connect'),create=document.getElementById('create-workspace');if(choose.textContent!==expected.chooseWorkspace||create.textContent!==expected.createWorkspace||document.getElementById('main-folder-setup').textContent!==expected.createWorkspaceHelp||document.getElementById('files-section-heading').textContent!==expected.mainFolderSetup||!__visible('create-workspace')||document.documentElement.scrollWidth>innerWidth)window.__creationLocaleFailures.push(option.code);}window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:60,pending:false});})();true")
        report['creation_locale_failures']=await c.evaluate('window.__creationLocaleFailures')
        await check('main_folder_setup_and_paired_actions_translate_in_all_33_languages_without_overflow', 'window.__creationLocaleFailures.length===0')
        await c.screenshot(out/'new-conversation-choose-or-create-806.png')

        # Busy uses that same main action to cancel, without a permanent extra button.
        await c.set_fixture(fixture(), 'connecting', 'Een veilige fixtureverbinding wordt voorbereid.')
        await check('busy_main_action_cancels', "__visible('auto-connect')&&!document.getElementById('auto-connect').disabled&&/annuleren/i.test(document.getElementById('auto-connect').textContent)")
        await c.evaluate("document.getElementById('auto-connect').click();true")
        await asyncio.sleep(.08)
        await check('cancel_uses_existing_action', "window.__calls.some(x=>x.name==='web_command'&&x.args.payload.action==='web_abort')")

        # Errors remain readable without opening a technical disclosure.
        error = 'Voorbeeldfout: de fictieve verbinding kon niet worden bijgewerkt.'
        await c.set_fixture(fixture(), 'error', error, 'network')
        await c.evaluate("document.getElementById('files-options').open=false;true")
        await check('error_visible_with_options_closed', "__visible('auto-status')&&document.getElementById('auto-status').dataset.state==='error'&&document.getElementById('connection-details').textContent===window.vibezLanguage.t('auto_network')&&document.getElementById('error-details-text').textContent.includes('Voorbeeldfout')&&!document.getElementById('files-options').open")
        await check('error_retry_available', "__visible('auto-connect')&&!document.getElementById('auto-connect').disabled")
        await c.screenshot(out / 'error.png')
        await c.evaluate("document.getElementById('files-options').open=true;true")
        await check('full_connection_error_available_in_options', "__visible('connection-details')&&document.getElementById('connection-details').textContent===window.vibezLanguage.t('auto_network')&&document.getElementById('error-details-text').textContent.includes('Voorbeeldfout')")
        await c.set_fixture(fixture(linked=False), 'idle')
        await c.evaluate("document.getElementById('files-options').open=false;window.__failFolder=true;document.getElementById('auto-connect').click();true")
        await asyncio.sleep(.08)
        await check('generic_action_error_visible_without_options', "__visible('auto-status')&&document.getElementById('auto-status').textContent===window.vibezLanguage.t('operationFailed')&&document.getElementById('error-details-text').textContent.includes('map kiezen geweigerd')&&!document.getElementById('files-options').open")
        await c.evaluate("document.getElementById('auto-connect').click();true")
        await asyncio.sleep(.08)
        await check('generic_error_clears_after_successful_retry', "!document.getElementById('auto-status').textContent.includes('geweigerd')&&document.getElementById('web-folder').textContent.includes('/voorbeelden/CityTripXL')")
        no_project = fixture(linked=False);no_project['project'] = None;no_project['projects'] = []
        await c.set_fixture(no_project, 'idle')
        await c.evaluate("window.__emit('app-engine',{type:'error',message:'Voorbeeld: projectinformatie niet beschikbaar.'});true")
        await check('no_project_action_error_remains_visible', "__visible('auto-status')&&document.getElementById('auto-status').textContent===window.vibezLanguage.t('operationFailed')&&document.getElementById('error-details-text').textContent.includes('projectinformatie niet beschikbaar')")
        await c.set_fixture(fixture(), 'error', 'Voorbeeld: geef Mistral opnieuw toestemming.', 'permission')
        await check('permission_opens_both_disclosures', "document.getElementById('files-options').open&&document.getElementById('advanced-setup').open&&__visible('api-access')")

        await c.evaluate("window.__emit('language-state',{language:'de',resolved:'de',site_locale:'de',revision:100,pending:false});true")
        await check('error_summary_help_and_existing_diagnostics_translate_without_dutch_leak', "document.getElementById('auto-status').textContent===window.VIBEZ_TRANSLATIONS.new.de.filesFailed&&document.getElementById('connection-details').textContent===window.VIBEZ_TRANSLATIONS.new.de.auto_permission&&document.querySelector('#error-details>summary').textContent===window.VIBEZ_TRANSLATIONS.new.de.technicalDetails&&document.getElementById('error-details-text').textContent===window.VIBEZ_TRANSLATIONS.new.de.auto_permission")
        await c.screenshot(out / 'error-de.png')
        for revision, locale in enumerate(['en', 'de', 'fr', 'missing-locale'], 101):
            await c.evaluate("window.__emit('language-state',"+json.dumps({'language':locale,'resolved':locale,'site_locale':'en','revision':revision,'pending':False})+");window.__emit('app-engine',"+json.dumps({'type':'web_import_result','project_id':PROJECT['id'],'binding':IMPORT_BINDING,'error':'Kopiëren is niet gelukt. Controleer de werkmap.'})+");true")
            await check('existing_dutch_errors_and_import_tooltips_follow_'+locale, "document.getElementById('error-details-text').textContent===window.vibezLanguage.t('auto_permission')&&document.getElementById('project-import-error-text').textContent===window.vibezLanguage.t('fileImportFailed')&&document.getElementById('project-import-status').title===window.vibezLanguage.t('fileImportFailed')&&!document.getElementById('error-details-text').textContent.includes('Voorbeeld')")
        await c.evaluate("window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:105,pending:false});true")
        await check('switching_back_to_dutch_restores_dutch_diagnostics_only_in_dutch', "document.getElementById('project-import-error-text').textContent.includes('Kopiëren')&&document.getElementById('error-details-text').textContent.includes('Voorbeeld')")
        await c.evaluate("window.__emit('app-engine',"+json.dumps({'type':'web_import_result','project_id':PROJECT['id'],'binding':IMPORT_BINDING,'count':0})+");true")

        # File contents stay inert and review remains outside all hidden options.
        before = '<img src=x onerror="window.__fixtureInjected=true">'
        after = '<script>window.__fixtureInjected=true</script>\nEen veilige tekstwijziging.'
        proposal = {'id': 'fixture-proposal', 'project_id': PROJECT['id'],
                    'project_name': PROJECT['name'], 'path': 'README.md', 'before': before, 'after': after}
        await c.set_fixture(fixture(enabled=True, pending=[proposal]), 'connected')
        await c.evaluate("document.getElementById('files-options').open=false;true")
        await check('approval_visible_outside_options', "__visible('web-review')&&!document.querySelector('#files-options #web-review')&&document.querySelectorAll('#web-proposals .approval').length===1")
        await check('approval_contents_inert', "!window.__fixtureInjected&&!document.querySelector('#web-proposals img,#web-proposals script')&&document.querySelector('#web-proposals pre').textContent.includes('<img')")
        await check('file_approval_uses_clear_save_label', "document.querySelector('#web-proposals .approval-actions .primary').textContent==='Opslaan'")
        await c.evaluate("document.getElementById('web-review').scrollIntoView({block:'start'});true")
        await c.screenshot(out / 'approval.png')
        await c.evaluate("document.querySelector('#web-proposals .approval-actions .secondary').click();true")
        await asyncio.sleep(.08)
        await check('reject_uses_scoped_approval_action', "window.__calls.some(x=>x.name==='web_command'&&x.args.payload.action==='web_approve'&&x.args.payload.id==='fixture-proposal'&&x.args.payload.allow===false)&&!__visible('web-review')")

        # Native imports use a binding/grant, never browser-supplied file paths.
        files = fixture(enabled=True)
        hostile = '<img src=x onerror="window.__fileInjected=true">'
        files['local_files'] = [{'name': 'controle.txt'}, {'name': hostile}]
        root_name = 'Hoofdmap $& {folder} <svg onload="window.__rootInjected=true">'
        files['folder']='/voorbeelden/'+root_name;files['import_binding']='c'*64
        await c.set_fixture(files, 'connected')
        await c.evaluate("window.__dropPoint=()=>{const n=document.getElementById('project-drop-zone');n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};};window.__importCalls=()=>window.__calls.filter(x=>['project_import_choose','project_import_commit'].includes(x.name));window.__calls=[];true")
        await check('drop_zone_is_compact_with_file_and_new_subfolder_actions_and_no_existing_file_list', "(()=>{const zone=document.getElementById('project-drop-zone');return __visible('project-files')&&!document.getElementById('project-add-files').disabled&&!document.getElementById('project-local-files')&&!zone.textContent.includes('controle.txt')&&!zone.textContent.includes("+json.dumps(hostile)+")&&zone.contains(document.getElementById('project-add-files'))&&!document.getElementById('project-add-folder')&&zone.contains(document.getElementById('project-new-folder'))&&!document.getElementById('project-new-folder').disabled&&zone.querySelector('.project-import-buttons').querySelectorAll('button').length===2&&zone.getBoundingClientRect().height<=180&&!window.__fileInjected&&!window.__rootInjected&&document.getElementById('project-drop-hint').textContent===__folderCopy('dropProjectItems')&&document.getElementById('project-drop-hint').textContent.includes("+json.dumps(root_name)+")&&document.getElementById('files-section-heading').textContent==="+json.dumps(root_name)+"&&document.getElementById('files-section-heading').childElementCount===0&&document.getElementById('project-drop-hint').childElementCount===0&&document.getElementById('subfolder-location').textContent===__folderCopy('subfolderLocation')&&!document.querySelector('#folder-summary svg svg,#project-drop-hint svg,#subfolder-location svg');})()")
        await c.screenshot(out/'main-folder-name-literal-806.png')
        await c.set_fixture(fixture(enabled=True),'connected')
        await c.evaluate("document.getElementById('project-add-files').scrollIntoView({block:'center'});document.getElementById('project-add-files').click();true")
        await asyncio.sleep(.06)
        await check('add_files_uses_scoped_native_picker_and_shows_busy', "__importCalls().length===1&&__importCalls()[0].name==='project_import_choose'&&__importCalls()[0].args.projectId==="+json.dumps(PROJECT['id'])+"&&__importCalls()[0].args.binding==="+json.dumps(IMPORT_BINDING)+"&&document.getElementById('project-add-files').disabled&&document.getElementById('project-drop-zone').getAttribute('aria-disabled')==='true'&&document.getElementById('project-import-status').textContent===window.vibezLanguage.t('copyingFiles')")
        await c.evaluate("document.getElementById('project-add-files').click();window.__emit('project-drop',{kind:'drop',grant:'invented-busy-grant',...__dropPoint()});window.__emit('app-engine',{type:'web_import_result',project_id:'other-project',binding:"+json.dumps(IMPORT_BINDING)+",count:99});window.__emit('app-engine',{type:'web_import_result',project_id:"+json.dumps(PROJECT['id'])+",binding:'b'.repeat(64),count:99});true")
        await check('busy_import_ignores_duplicates_and_stale_results', "__importCalls().length===1&&document.getElementById('project-add-files').disabled&&document.getElementById('project-import-status').textContent===window.vibezLanguage.t('copyingFiles')")
        await c.evaluate("window.__emit('app-engine',{type:'web_import_result',project_id:"+json.dumps(PROJECT['id'])+",binding:"+json.dumps(IMPORT_BINDING)+",count:2});true")
        await check('matching_import_result_confirms_count_and_reenables_controls', "!document.getElementById('project-add-files').disabled&&document.getElementById('project-drop-zone').getAttribute('aria-disabled')==='false'&&document.getElementById('project-import-status').textContent===window.vibezLanguage.t('filesCopied').replace('{count}','2')")
        await c.evaluate("window.__cancelImport=true;document.getElementById('project-add-files').click();true")
        await asyncio.sleep(.06)
        await check('cancelled_native_picker_leaves_import_ready_without_success', "!document.getElementById('project-add-files').disabled&&!document.getElementById('project-import-status').textContent")
        await c.evaluate("window.__failImport='Voorbeeld: bronbestand kon niet worden gekopieerd.';document.getElementById('project-add-files').click();true")
        await asyncio.sleep(.06)
        await check('import_error_is_localized_and_keeps_original_detail', "!document.getElementById('project-add-files').disabled&&document.getElementById('project-import-status').textContent===window.vibezLanguage.t('fileImportFailed')&&document.getElementById('project-import-status').title.includes('Voorbeeld')&&document.getElementById('project-import-status').dataset.error==='true'")
        await c.evaluate("window.__calls=[];window.__emit('project-drop',{kind:'over',...__dropPoint()});true")
        await check('drop_inside_the_zone_highlights_the_target', "document.getElementById('project-drop-zone').dataset.over==='true'")
        await c.evaluate("window.__emit('project-drop',{kind:'drop',grant:'invented-current-grant',...__dropPoint()});true")
        await asyncio.sleep(.06)
        await check('drop_uses_only_the_native_grant_commit', "__importCalls().length===1&&__importCalls()[0].name==='project_import_commit'&&JSON.stringify(__importCalls()[0].args)==='{"+'"grant":"invented-current-grant"'+"}'&&document.getElementById('project-drop-zone').dataset.over==='false'")
        await c.evaluate("window.__emit('app-engine',{type:'web_import_result',project_id:"+json.dumps(PROJECT['id'])+",binding:"+json.dumps(IMPORT_BINDING)+",count:1,error:'Voorbeeld: één bestand is overgeslagen.'});true")
        await check('partial_copy_reports_count_and_failure_without_claiming_all_saved', "!document.getElementById('project-add-files').disabled&&document.getElementById('project-import-status').textContent.includes(window.vibezLanguage.t('filesCopied').replace('{count}','1'))&&document.getElementById('project-import-status').textContent.includes(window.vibezLanguage.t('fileImportFailed'))")
        await c.evaluate("window.__calls=[];window.__emit('project-drop',{kind:'drop',grant:'invented-outside-grant',x:2,y:2});window.__emit('project-drop',{kind:'drop',grant:'invented-invalid-position',x:NaN,y:20});window.__emit('project-drop',{kind:'drop',...__dropPoint()});true")
        await check('outside_invalid_or_missing_grant_drops_are_ignored', '__importCalls().length===0')
        await c.set_fixture(fixture(linked=False), 'idle')
        await c.evaluate("window.__calls=[];window.__emit('project-drop',{kind:'drop',grant:'invented-disabled-grant',...__dropPoint()});document.getElementById('project-add-files').click();true")
        await check('unlinked_project_disables_picker_and_ignores_drop', "document.getElementById('project-add-files').disabled&&document.getElementById('project-drop-zone').getAttribute('aria-disabled')==='true'&&__importCalls().length===0")
        await c.set_fixture(files, 'connected')
        await c.evaluate("window.__savedDropPoint=__dropPoint();window.__emit('chrome-panel','settings');window.__calls=[];window.__emit('project-drop',{kind:'drop',grant:'invented-settings-grant',...window.__savedDropPoint});true")
        await check('settings_panel_ignores_file_drops', "document.getElementById('web-panel').hidden&&!document.getElementById('panel-settings').hidden&&__importCalls().length===0")
        await c.evaluate("window.__emit('chrome-panel','files');true")
        await check('opening_project_panel_returns_to_its_header', '(document.body.scrollTop||document.documentElement.scrollTop)===0')
        rebound = fixture(enabled=True);rebound['import_binding'] = 'b'*64
        await c.set_fixture(rebound, 'connected')
        await c.evaluate("window.__emit('app-engine',{type:'web_import_result',project_id:"+json.dumps(PROJECT['id'])+",binding:"+json.dumps(IMPORT_BINDING)+",count:44});true")
        await check('new_binding_clears_previous_import_and_rejects_old_result', "!document.getElementById('project-add-files').disabled&&!document.getElementById('project-import-status').textContent")
        other = fixture(enabled=True);other['project']={'id':'code-229ee257-1234-4567-890a-123456789abc','name':'Code Beta'};other['import_binding']='c'*64;other['folder']='/voorbeelden/Beta'
        await c.set_fixture(other, 'connected')
        await c.evaluate("window.__emit('app-engine',{type:'web_import_result',project_id:"+json.dumps(PROJECT['id'])+",binding:'b'.repeat(64),count:55});true")
        await check('different_project_rejects_previous_project_import_result', "document.getElementById('web-project-name').textContent==='Code Beta'&&!document.getElementById('project-import-status').textContent&&!document.getElementById('project-add-files').disabled")

        # Mistral's project settings share the pane and remain scoped/inert.
        await c.set_fixture(fixture(enabled=True), 'connected')
        details={'project_id':PROJECT['id'],'available':True,'cached':False,'can_edit':True,'can_open_project':True,'instructions':hostile,'settings':[
            {'kind':'tone','label':'Toon','text':'Standaard (Globaal)'},
            {'kind':'instructions','label':'Instructies','text':hostile,'action':'instructions','action_label':'Aanpassen'},
            {'kind':'context','label':'Aanvullende context','text':'Gebruik gesprekken uit andere projecten als context.','checked':True,'action':'context'}]}
        await c.evaluate("window.__emit('project-details',"+json.dumps(details)+");true")
        await check('project_rules_are_separate_from_compact_tone_and_context', "__visible('project-rules')&&__visible('project-rules-edit')&&document.getElementById('project-rules-text').textContent==="+json.dumps(hostile)+"&&document.getElementById('project-rules-text').childElementCount===0&&!document.querySelector('#project-rules img,#project-rules script')&&__visible('mistral-project-settings')&&document.querySelectorAll('#mistral-project-settings .project-setting').length===2&&!document.getElementById('mistral-project-settings').textContent.includes("+json.dumps(hostile)+")&&!document.querySelector('#mistral-project-settings img,#mistral-project-settings script')&&!window.__fileInjected&&(document.getElementById('mistral-project-settings').compareDocumentPosition(document.getElementById('folder-summary'))&Node.DOCUMENT_POSITION_FOLLOWING)!==0")
        await check('tone_and_context_are_compact_and_collapsed_by_default', "document.getElementById('mistral-project-settings').tagName==='DETAILS'&&!document.getElementById('mistral-project-settings').open&&document.querySelector('#mistral-project-settings>summary').textContent===window.vibezLanguage.t('moreProjectSettings')")
        await c.evaluate("document.getElementById('mistral-project-settings').open=true;window.__emit('language-state',{language:'de',resolved:'de',site_locale:'de',revision:142,pending:false});true")
        await c.set_fixture(fixture(enabled=True),'connected')
        await check('expanded_tone_and_context_stay_open_through_snapshot_and_language_replays', "document.getElementById('mistral-project-settings').open&&document.querySelector('#mistral-project-settings>summary').textContent===window.vibezLanguage.t('moreProjectSettings')")
        await c.evaluate("window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:143,pending:false});true")
        await check('project_context_checkbox_is_compact_and_aligned_with_its_text', "(()=>{const box=document.querySelector('#mistral-project-settings input[type=checkbox]').getBoundingClientRect(),text=document.querySelector('#mistral-project-settings .project-context span').getBoundingClientRect();return box.width>=14&&box.width<=18&&box.height>=14&&box.height<=18&&Math.abs(text.left-box.right-9)<.5;})()")
        await c.evaluate("window.__calls=[];document.querySelector('#mistral-project-settings input[type=checkbox]').click();true")
        await asyncio.sleep(.06)
        await check('context_action_sends_the_requested_checked_state', "window.__calls.length===1&&window.__calls[0].name==='project_details_action'&&window.__calls[0].args.projectId==="+json.dumps(PROJECT['id'])+"&&window.__calls[0].args.action==='context'&&window.__calls[0].args.enabled===false")
        await c.evaluate("window.__failDetails=true;document.querySelector('#mistral-project-settings input[type=checkbox]').click();true")
        await asyncio.sleep(.06)
        await check('failed_context_action_restores_the_known_project_state', "document.querySelector('#mistral-project-settings input[type=checkbox]').checked&&!document.querySelector('#mistral-project-settings input[type=checkbox]').disabled&&document.getElementById('error-details-text').textContent.includes('projectinstelling niet gewijzigd')")
        readonly=json.loads(json.dumps(details));readonly['settings'][2].pop('action')
        await c.evaluate("window.__emit('project-details',"+json.dumps(readonly)+");window.__calls=[];document.querySelector('#mistral-project-settings input[type=checkbox]').click();true")
        await check('read_only_project_context_cannot_invoke_native_action', "document.querySelector('#mistral-project-settings input[type=checkbox]').disabled&&window.__calls.length===0")
        await c.evaluate("window.__emit('project-details',"+json.dumps(details)+");window.__oldProjectSettingButton=document.querySelector('#mistral-project-settings input[type=checkbox]');window.__calls=[];true")
        await c.set_fixture(other, 'connected')
        await c.evaluate('window.__oldProjectSettingButton.click();true')
        await check('stale_project_settings_and_actions_cannot_reuse_the_previous_project', "document.getElementById('mistral-project-settings').hidden&&!document.getElementById('mistral-project-settings-body').childElementCount&&!window.__calls.some(x=>x.name==='project_details_action'&&x.args.projectId==="+json.dumps(PROJECT['id'])+")")
        await c.set_fixture(fixture(enabled=True), 'connected')
        await c.evaluate("window.__emit('project-details',{project_id:"+json.dumps(PROJECT['id'])+",available:false,cached:false,can_open_project:true,settings:[]});true")
        await check('unavailable_mistral_settings_hide_the_proxy_block', "document.getElementById('mistral-project-settings').hidden&&!document.getElementById('mistral-project-settings-body').childElementCount")
        details['settings'][1]['text']='Beantwoord vragen over deze projectmap en controleer wijzigingen vóór opslaan.'
        details['instructions']=details['settings'][1]['text']
        await c.evaluate("window.__emit('project-details',"+json.dumps(details)+");webCommand('web_hello');true")
        for height in [1100,806]:
            await c.call('Emulation.setDeviceMetricsOverride', {'width':width,'height':height,'deviceScaleFactor':1,'mobile':False})
            await c.evaluate("window.__emit('chrome-panel','files');true")
            await c.screenshot(out/('unified-project-'+str(height)+'.png'))
        await c.evaluate('__dropPoint();true')
        await c.screenshot(out/'unified-project-drop-806.png')
        await c.set_fixture(fixture(), 'paused', pause_reason='context')
        await c.evaluate("window.__emit('chrome-panel','files');true")
        await check('paused_unified_panel_keeps_connect_with_mistral_settings_and_folder', "__visible('mistral-project-settings')&&__visible('folder-summary')&&__visible('auto-connect')&&document.getElementById('auto-connect').textContent==='Verbinden'&&document.getElementById('auto-connect').classList.contains('primary')&&__visible('project-files')")
        await c.screenshot(out/'unified-project-paused-806.png')

        # Rules are edited inline through the exact project's native form contract.
        await c.set_fixture(fixture(enabled=True),'connected')
        await c.evaluate("window.__rulesDetails="+json.dumps(details)+";window.__rulesValue=window.__rulesDetails.instructions;window.__emit('project-details',window.__rulesDetails);window.__rulesCalls=()=>window.__calls.filter(x=>x.name==='project_rules_edit');window.__setRules=value=>{const n=document.getElementById('project-rules-input');n.value=value;n.dispatchEvent(new Event('input',{bubbles:true}));};window.__calls=[];document.getElementById('project-rules-edit').click();true")
        await asyncio.sleep(.04)
        await check('rules_edit_opens_the_native_project_form_and_shows_its_actual_value_inline', "__rulesCalls().length===1&&__rulesCalls()[0].args.action==='open'&&__rulesCalls()[0].args.projectId==="+json.dumps(PROJECT['id'])+"&&__visible('project-rules-form')&&document.getElementById('project-rules-input').value===window.__rulesDetails.instructions&&!__visible('project-rules-edit')&&!__visible('project-rules-text')&&document.activeElement===document.getElementById('project-rules-input')&&!document.getElementById('project-rules-save').disabled")
        rules_draft='Behoud deze eigen conceptregels.\n<img src=x onerror="window.__rulesInjected=true">'
        await c.evaluate("__setRules("+json.dumps(rules_draft)+");window.__rulesLocaleFailures=[];(()=>{let revision=150;for(const option of window.VIBEZ_TRANSLATIONS.options.filter(o=>o.code!=='system')){window.__emit('language-state',{language:option.code,resolved:option.code,site_locale:'en',revision:revision++,pending:false});const expected=window.VIBEZ_TRANSLATIONS.new[option.code];if(document.getElementById('project-rules-heading').textContent!==expected.projectRules||document.getElementById('project-rules-save').textContent!==expected.projectRulesSave||document.getElementById('project-rules-cancel').textContent!==expected.projectRulesCancel||document.getElementById('project-rules-input').value!=="+json.dumps(rules_draft)+"||!__visible('project-rules-form')||document.documentElement.scrollWidth>innerWidth)window.__rulesLocaleFailures.push(option.code);}window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:190,pending:false});})();true")
        report['rules_locale_failures']=await c.evaluate('window.__rulesLocaleFailures')
        await check('project_rules_editor_translates_in_all_33_languages_without_losing_the_draft_or_overflow', 'window.__rulesLocaleFailures.length===0')
        await c.evaluate("document.getElementById('project-rules').scrollIntoView({block:'start'});true")
        await c.screenshot(out/'project-rules-editor-806.png')
        await c.evaluate("document.getElementById('project-rules-cancel').click();true")
        await asyncio.sleep(.03)
        await check('cancel_rules_editor_only_discards_its_nonce_and_never_saves', "!__visible('project-rules-form')&&!document.getElementById('project-rules-input').value&&__rulesCalls().filter(x=>x.args.action==='cancel').length===1&&__rulesCalls().find(x=>x.args.action==='cancel').args.nonce==='fixture-editor-nonce'&&!__rulesCalls().some(x=>x.args.action==='save')&&document.getElementById('project-rules-text').textContent===window.__rulesDetails.instructions")
        await c.evaluate("window.__calls=[];document.getElementById('project-rules-edit').click();true")
        await asyncio.sleep(.03)
        await c.evaluate("__setRules("+json.dumps(rules_draft)+");window.__holdRulesSave=true;document.getElementById('project-rules-save').click();document.getElementById('project-rules-save').click();true")
        await check('saving_rules_blocks_duplicate_actions_and_waits_for_confirmed_native_save', "__rulesCalls().filter(x=>x.args.action==='save').length===1&&__rulesCalls().find(x=>x.args.action==='save').args.value==="+json.dumps(rules_draft)+"&&__rulesCalls().find(x=>x.args.action==='save').args.nonce==='fixture-editor-nonce'&&__rulesCalls().find(x=>x.args.action==='save').args.projectId==="+json.dumps(PROJECT['id'])+"&&document.getElementById('project-rules-input').disabled&&document.getElementById('project-rules-save').disabled&&document.getElementById('project-rules-cancel').disabled&&document.getElementById('project-rules-status').textContent===window.vibezLanguage.t('projectRulesSaving')&&__visible('project-rules-form')")
        await c.evaluate("window.__rejectRulesSave(new Error('Voorbeeld: bestaande regels veranderden ondertussen.'));true")
        await asyncio.sleep(.03)
        await check('failed_rules_save_retains_the_draft_and_shows_a_localized_error_with_original_details', "__visible('project-rules-form')&&document.getElementById('project-rules-input').value==="+json.dumps(rules_draft)+"&&!document.getElementById('project-rules-input').disabled&&!document.getElementById('project-rules-save').disabled&&!document.getElementById('project-rules-cancel').disabled&&document.getElementById('project-rules-status').textContent===window.vibezLanguage.t('projectRulesError')&&document.getElementById('project-rules-status').title.includes('veranderden ondertussen')&&document.getElementById('project-rules-status').dataset.error==='true'&&!window.__rulesInjected")
        await c.evaluate("window.__holdRulesSave=true;document.getElementById('project-rules-save').click();true")
        await c.evaluate("window.__resolveRulesSave({project_id:"+json.dumps(PROJECT['id'])+",saved:false});true")
        await asyncio.sleep(.03)
        await check('an_unconfirmed_rules_save_keeps_the_draft_instead_of_claiming_success', "__visible('project-rules-form')&&document.getElementById('project-rules-input').value==="+json.dumps(rules_draft)+"&&document.getElementById('project-rules-status').textContent===window.vibezLanguage.t('projectRulesError')")
        await c.evaluate("document.getElementById('project-rules-save').click();true")
        await asyncio.sleep(.04)
        await check('confirmed_rules_save_updates_the_plaintext_snapshot_and_closes_the_editor', "!__visible('project-rules-form')&&!document.getElementById('project-rules-input').value&&__visible('project-rules-edit')&&document.getElementById('project-rules-text').textContent==="+json.dumps(rules_draft)+"&&document.getElementById('project-rules-status').textContent===window.vibezLanguage.t('projectRulesSaved')&&!document.querySelector('#project-rules-text img,#project-rules-text script')&&!window.__rulesInjected")
        cached_rules=json.loads(json.dumps(details));cached_rules.update(cached=True,can_edit=False)
        await c.evaluate("window.__emit('project-details',"+json.dumps(cached_rules)+");window.__calls=[];true")
        await check('cached_rules_remain_readable_with_open_project_instead_of_edit', "__visible('project-rules')&&document.getElementById('project-rules-text').textContent==="+json.dumps(details['instructions'])+"&&__visible('project-rules-note')&&document.getElementById('project-rules-note').textContent===window.vibezLanguage.t('projectRulesCached')&&!__visible('project-rules-edit')&&__visible('project-rules-open')&&!__visible('project-rules-form')")
        await c.evaluate("document.getElementById('project-rules-open').click();true")
        await asyncio.sleep(.03)
        await check('cached_rules_open_only_the_current_native_verified_project', "window.__calls.length===1&&window.__calls[0].name==='project_details_action'&&window.__calls[0].args.projectId==="+json.dumps(PROJECT['id'])+"&&window.__calls[0].args.action==='open_project'")
        await c.evaluate("window.__emit('project-details',{project_id:"+json.dumps(PROJECT['id'])+",available:false,cached:false,can_open_project:true,settings:[]});true")
        await check('unavailable_rules_explain_opening_the_project_without_inventing_rules', "__visible('project-rules')&&document.getElementById('project-rules-text').textContent===window.vibezLanguage.t('projectRulesUnavailable')&&__visible('project-rules-open')&&!__visible('project-rules-edit')")
        await c.evaluate("window.__emit('project-details',"+json.dumps(details)+");window.__calls=[];window.__holdRulesOpen=true;document.getElementById('project-rules-edit').click();true")
        next_rules_project=fixture(enabled=True);next_rules_project['project']={'id':'229ee257-4177-4f98-969c-3055311c7cae','name':'Werkproject Beta'};next_rules_project['projects']=[next_rules_project['project']]
        next_rules_details=json.loads(json.dumps(details));next_rules_details.update(project_id=next_rules_project['project']['id'],instructions='Regels uitsluitend voor Werkproject Beta.')
        await c.set_fixture(next_rules_project,'connected')
        await c.evaluate("window.__emit('project-details',"+json.dumps(next_rules_details)+");window.__resolveRulesOpen({project_id:"+json.dumps(PROJECT['id'])+",value:'Verouderde regels uit CityTripXL',nonce:'stale-open-nonce'});true")
        await asyncio.sleep(.04)
        await check('a_late_rules_open_cannot_replace_the_next_projects_rules_or_editor', "document.getElementById('project-rules-text').textContent==='Regels uitsluitend voor Werkproject Beta.'&&!__visible('project-rules-form')&&!document.getElementById('project-rules-input').value&&__rulesCalls().some(x=>x.args.action==='cancel'&&x.args.projectId==="+json.dumps(PROJECT['id'])+"&&x.args.nonce==='stale-open-nonce')&&!document.getElementById('project-rules-status').textContent")
        await c.set_fixture(fixture(enabled=True),'connected')
        await c.evaluate("window.__emit('project-details',"+json.dumps(details)+");window.__rulesValue='Eigen projectregels';document.getElementById('project-rules-edit').click();true")
        await asyncio.sleep(.03)
        await c.evaluate("__setRules('Niet naar het volgende project kopiëren');window.__holdRulesSave=true;document.getElementById('project-rules-save').click();true")
        await c.set_fixture(next_rules_project,'connected')
        await c.evaluate("window.__emit('project-details',"+json.dumps(next_rules_details)+");window.__resolveRulesSave({project_id:"+json.dumps(PROJECT['id'])+",saved:true});true")
        await asyncio.sleep(.04)
        await check('a_late_rules_save_cannot_show_success_or_text_in_the_next_project', "document.getElementById('project-rules-text').textContent==='Regels uitsluitend voor Werkproject Beta.'&&!__visible('project-rules-form')&&!document.getElementById('project-rules-input').value&&!document.getElementById('project-rules-status').textContent")
        await c.set_fixture(other,'connected')
        await c.evaluate("window.__emit('project-details',"+json.dumps(details)+");true")
        await check('code_projects_do_not_show_unverified_work_project_rules', "!__visible('project-rules')&&!__visible('project-rules-form')")
        await c.set_fixture(fixture(enabled=True),'connected')
        await c.evaluate("window.__emit('project-details',"+json.dumps(details)+");window.__emit('chrome-panel','files');true")

        # A native import plan never overwrites an existing item without a choice.
        await c.set_fixture(fixture(enabled=True), 'connected')
        await c.evaluate("window.__resolveCalls=()=>window.__calls.filter(x=>x.name==='project_import_resolve');window.__conflictRow=id=>document.querySelector('#import-conflict-items fieldset[data-item-id=\"'+id+'\"]');window.__choice=(id,value)=>{const n=__conflictRow(id).querySelector('input[value=\"'+value+'\"]');n.click();return true;};window.__selected=id=>__conflictRow(id).querySelector('input:checked')?.value;true")
        item_a, item_b, item_c = '1'*24, '2'*24, '3'*24
        conflict_name = '<img src=x onerror="window.__conflictInjected=true">'
        conflict_items = [
            {'id':item_a,'name':conflict_name,'source_kind':'file','target_kind':'file','can_replace':True},
            {'id':item_b,'name':'Reisplan','source_kind':'directory','target_kind':'directory','can_replace':True},
            {'id':item_c,'name':'bezet','source_kind':'file','target_kind':'directory','can_replace':False}]

        def conflict_plan(number, *, status='conflicts', items=None, project_id=None, binding=None):
            return {'type':'web_import_conflicts','status':status,
                    'project_id':project_id or PROJECT['id'],'binding':binding or IMPORT_BINDING,
                    'plan_id':'FixturePlan'+str(number).zfill(21),
                    'items':conflict_items if items is None else items}

        async def emit_plan(plan, *, start=True):
            if start:
                await c.evaluate("document.getElementById('project-add-files').click();true")
                await asyncio.sleep(.03)
            await c.evaluate("window.__emit('app-engine',"+json.dumps(plan)+");true")
            await asyncio.sleep(.04)

        async def finish_import(*, count=0, skipped=0, cancelled=False):
            await c.evaluate("window.__emit('app-engine',"+json.dumps({
                'type':'web_import_result','project_id':PROJECT['id'],'binding':IMPORT_BINDING,
                'count':count,'skipped':skipped,'cancelled':cancelled})+");true")

        await c.evaluate("window.__calls=[];window.__emit('project-drop',{kind:'drop',grant:'invented-directory-grant',...__dropPoint()});true")
        await asyncio.sleep(.04)
        await check('dropped_directory_still_uses_only_the_native_grant_commit', "__importCalls().length===1&&__importCalls()[0].name==='project_import_commit'&&JSON.stringify(__importCalls()[0].args)===JSON.stringify({grant:'invented-directory-grant'})&&document.getElementById('project-add-files').disabled&&document.getElementById('project-drop-zone').getAttribute('aria-disabled')==='true'")
        await finish_import()
        await c.evaluate('window.__calls=[];true')
        first_plan = conflict_plan(1)
        await emit_plan(first_plan)
        await check('file_and_folder_conflicts_open_with_skip_selected_and_no_implicit_resolution', "document.getElementById('import-conflict-dialog').open&&document.querySelectorAll('#import-conflict-items fieldset').length===3&&document.querySelectorAll('#import-conflict-items input[type=radio]').length===9&&[...document.querySelectorAll('#import-conflict-items input:checked')].every(x=>x.value==='skip')&&__resolveCalls().length===0&&document.getElementById('project-add-files').disabled")
        await check('conflict_names_are_inert_and_nonreplaceable_items_cannot_be_replaced', "__conflictRow("+json.dumps(item_a)+").textContent.includes("+json.dumps(conflict_name)+")&&!document.querySelector('#import-conflict-dialog img,#import-conflict-dialog script')&&!window.__conflictInjected&&__conflictRow("+json.dumps(item_c)+").querySelector('input[value=replace]').disabled")
        await c.evaluate("__choice("+json.dumps(item_b)+",'replace');__choice("+json.dumps(item_c)+",'keep_both');true")
        await check('folder_replacement_explains_whole_folder_replacement_before_continue', "__visible('import-conflict-folder-note')&&document.getElementById('import-conflict-folder-note').textContent===window.vibezLanguage.t('importReplaceFolderNote')&&__resolveCalls().length===0")
        await c.screenshot(out/'import-conflicts.png')
        await c.evaluate("document.getElementById('import-conflict-continue').click();true")
        await asyncio.sleep(.05)
        choices={item_a:'skip',item_b:'replace',item_c:'keep_both'}
        expected={'projectId':PROJECT['id'],'binding':IMPORT_BINDING,'planId':first_plan['plan_id'],'choices':choices,'cancel':False}
        await check('continue_sends_only_explicit_choices_for_the_current_native_plan', "__resolveCalls().length===1&&JSON.stringify(__resolveCalls()[0].args)===JSON.stringify("+json.dumps(expected)+")")
        await finish_import(count=2,skipped=1)
        await check('copy_result_reports_copied_and_skipped_items_separately', "document.getElementById('project-import-status').textContent.includes(window.vibezLanguage.t('filesCopied').replace('{count}','2'))&&document.getElementById('project-import-status').textContent.includes(window.vibezLanguage.t('importSkipped').replace('{count}','1'))&&!document.getElementById('project-add-files').disabled&&!document.getElementById('import-conflict-dialog').open")

        await c.evaluate('window.__calls=[];true')
        second_plan = conflict_plan(2)
        await emit_plan(second_plan)
        await c.evaluate("document.getElementById('import-conflict-all').click();__choice("+json.dumps(item_a)+",'replace');true")
        await check('apply_all_respects_items_that_cannot_be_replaced', "__selected("+json.dumps(item_a)+")==='replace'&&__selected("+json.dumps(item_b)+")==='replace'&&__selected("+json.dumps(item_c)+")==='skip'&&__resolveCalls().length===0")
        await c.evaluate("__choice("+json.dumps(item_a)+",'keep_both');window.__emit('language-state',{language:'de',resolved:'de',site_locale:'de',revision:200,pending:false});true")
        await check('apply_all_and_language_changes_keep_explicit_choices_without_submitting', "[...document.querySelectorAll('#import-conflict-items input:checked')].every(x=>x.value==='keep_both')&&document.getElementById('import-conflict-title').textContent===window.vibezLanguage.t('importConflictTitle')&&document.getElementById('import-conflict-continue').textContent===window.vibezLanguage.t('importContinue')&&document.getElementById('import-conflict-all').checked&&__resolveCalls().length===0")
        await c.screenshot(out/'import-conflicts-de.png')
        await c.evaluate("document.getElementById('import-conflict-all').click();__choice("+json.dumps(item_b)+",'skip');document.getElementById('import-conflict-cancel').click();true")
        await asyncio.sleep(.05)
        cancel_expected={'projectId':PROJECT['id'],'binding':IMPORT_BINDING,'planId':second_plan['plan_id'],'choices':{},'cancel':True}
        await check('cancel_discards_choices_and_waits_for_native_cancellation', "__resolveCalls().length===1&&JSON.stringify(__resolveCalls()[0].args)===JSON.stringify("+json.dumps(cancel_expected)+")&&!document.getElementById('import-conflict-dialog').open&&document.getElementById('project-add-files').disabled&&document.getElementById('project-import-status').textContent===window.vibezLanguage.t('importCancel')+'…'")
        await finish_import(cancelled=True)
        await check('native_cancellation_makes_the_import_controls_ready_again', "!document.getElementById('project-add-files').disabled&&!document.getElementById('project-import-status').textContent")
        await c.evaluate("window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:201,pending:false});window.__calls=[];true")
        await emit_plan(conflict_plan(3))
        await c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
        await c.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
        await asyncio.sleep(.06)
        await check('escape_cancels_the_native_plan_once', "!document.getElementById('import-conflict-dialog').open&&__resolveCalls().length===1&&__resolveCalls()[0].args.cancel===true&&Object.keys(__resolveCalls()[0].args.choices).length===0&&document.getElementById('project-add-files').disabled")
        await finish_import(cancelled=True)

        await c.evaluate('window.__calls=[];true')
        await emit_plan(conflict_plan(4,project_id='code-00000000-0000-4000-8000-000000000000'),start=False)
        await emit_plan(conflict_plan(5,binding='b'*64),start=False)
        await check('stale_project_or_binding_conflicts_do_not_open_or_resolve', "!document.getElementById('import-conflict-dialog').open&&__resolveCalls().length===0&&!document.getElementById('project-add-files').disabled")
        await emit_plan(conflict_plan(6))
        await c.set_fixture(rebound,'connected')
        await c.evaluate("document.getElementById('import-conflict-continue').click();true")
        await asyncio.sleep(.04)
        await check('switching_the_folder_binding_discards_an_open_conflict_review', "!document.getElementById('import-conflict-dialog').open&&!__resolveCalls().some(x=>x.args.cancel===false)&&!document.getElementById('project-add-files').disabled")
        await c.set_fixture(fixture(enabled=True),'connected')
        await c.evaluate('window.__calls=[];true')
        changed_plan=conflict_plan(7,status='changed',items=[])
        await emit_plan(changed_plan)
        await check('changed_destination_requires_a_fresh_confirmation_even_without_remaining_conflicts', "document.getElementById('import-conflict-dialog').open&&__visible('import-conflict-changed')&&document.querySelectorAll('#import-conflict-items fieldset').length===0&&!document.getElementById('import-conflict-continue').disabled&&__resolveCalls().length===0")
        await c.evaluate("document.getElementById('import-conflict-continue').click();true")
        await asyncio.sleep(.04)
        await check('fresh_confirmation_uses_the_revised_plan_with_empty_choices', "__resolveCalls().length===1&&__resolveCalls()[0].args.planId==="+json.dumps(changed_plan['plan_id'])+"&&Object.keys(__resolveCalls()[0].args.choices).length===0&&__resolveCalls()[0].args.cancel===false")
        await finish_import(skipped=3)
        await check('skipped_only_result_does_not_claim_files_were_copied', "document.getElementById('project-import-status').textContent===window.vibezLanguage.t('importSkipped').replace('{count}','3')&&!document.getElementById('project-add-files').disabled")
        await c.evaluate("window.__emit('app-engine',"+json.dumps({'type':'web_import_result','project_id':PROJECT['id'],'binding':IMPORT_BINDING,'count':1,'cancelled':True,'error':conflict_name,'backups':['/voorbeelden/bewaard-'+conflict_name]})+");true")
        await check('partial_cancelled_copy_keeps_counts_and_error_backup_details_as_inert_text', "document.getElementById('project-import-status').textContent.includes(window.vibezLanguage.t('filesCopied').replace('{count}','1'))&&__visible('project-import-error-details')&&document.getElementById('project-import-error-text').textContent.includes("+json.dumps(conflict_name)+")&&!document.querySelector('#project-import-error-details img,#project-import-error-details script')&&!window.__conflictInjected")

        # A detached Context control cannot act after another project is loaded.
        await c.set_fixture(fixture(enabled=True),'connected')
        await c.evaluate("window.__emit('project-details',"+json.dumps(details)+");window.__detachedContext=document.querySelector('#mistral-project-settings input[type=checkbox]');true")
        other_work=fixture(enabled=True);other_work['project']={'id':'229ee257-4177-4f98-969c-3055311c7cae','name':'Werkproject Beta'};other_work['projects']=[other_work['project']]
        other_details=json.loads(json.dumps(details));other_details['project_id']=other_work['project']['id'];other_details['settings'][1]['text']='Verborgen instructies voor Werkproject Beta.'
        await c.set_fixture(other_work,'connected')
        await c.evaluate("window.__emit('project-details',"+json.dumps(other_details)+");window.__calls=[];window.__detachedContext.click();true")
        await check('detached_old_context_cannot_act_after_new_project_details_have_loaded', "document.getElementById('web-project-name').textContent==='Werkproject Beta'&&document.querySelectorAll('#mistral-project-settings .project-setting').length===2&&!document.getElementById('mistral-project-settings').textContent.includes('Verborgen instructies')&&!window.__calls.some(x=>x.name==='project_details_action')")
        await c.set_fixture(fixture(),'paused',pause_reason='context')
        await c.evaluate("window.__emit('project-details',"+json.dumps(details)+");window.__emit('chrome-panel','files');true")

        # Stored legacy metadata never brings the removed goal controls back.
        legacy=fixture(enabled=True);legacy['project_goal']='Een eerder opgeslagen projectdoel hoort hier niet meer zichtbaar te zijn.'
        await c.set_fixture(legacy,'connected')
        await c.evaluate("window.__emit('app-engine',{type:'web_goal_result',project_id:"+json.dumps(PROJECT['id'])+",request_id:'obsolete-fixture-request',goal:'Ook een oud resultaat blijft verborgen.'});true")
        await check('removed_goal_stays_absent_while_rules_workspace_and_recent_actions_remain', "!document.querySelector('[id^=project-goal]')&&!document.body.textContent.includes('Een eerder opgeslagen projectdoel')&&!document.body.textContent.includes('Ook een oud resultaat blijft verborgen')&&__visible('project-rules')&&__visible('folder-summary')&&__visible('open-workspace')&&__visible('recent-file-actions')")
        other_overview=fixture(linked=False);other_overview['project']={'id':'229ee257-4177-4f98-969c-3055311c7cae','name':'Werkproject Beta'};other_overview['projects']=[other_overview['project']]

        # Opening a workspace passes only a native binding, never a browser path.
        await c.evaluate("window.__calls=[];document.getElementById('open-workspace').click();true")
        await asyncio.sleep(.04)
        await check('open_workspace_uses_only_the_current_native_binding', "window.__calls.filter(x=>x.name==='project_open_folder').length===1&&JSON.stringify(window.__calls.find(x=>x.name==='project_open_folder').args)===JSON.stringify({projectId:"+json.dumps(PROJECT['id'])+",binding:"+json.dumps(IMPORT_BINDING)+"})&&document.getElementById('folder-summary').contains(document.getElementById('open-workspace'))")
        await c.evaluate("window.__calls=[];window.__holdFolderOpen=true;document.getElementById('open-workspace').click();true")
        await check('workspace_open_waits_for_the_native_result', 'document.getElementById("open-workspace").disabled')
        rebound_open=fixture(enabled=True);rebound_open['import_binding']='b'*64
        await c.set_fixture(rebound_open,'connected')
        await check('same_named_workspace_rebinding_reenables_its_new_open_button', "!document.getElementById('open-workspace').disabled&&__visible('open-workspace')")
        await c.evaluate("document.getElementById('open-workspace').click();window.__rejectFolderOpen(new Error('Voorbeeld: oude werkmap is niet geopend.'));true")
        await asyncio.sleep(.05)
        await check('late_workspace_failure_cannot_change_the_new_binding_or_status', "window.__calls.filter(x=>x.name==='project_open_folder').length===2&&window.__calls.filter(x=>x.name==='project_open_folder')[1].args.binding==='b'.repeat(64)&&!document.getElementById('open-workspace').disabled&&!document.getElementById('auto-status').textContent.includes(window.vibezLanguage.t('operationFailed'))")
        await c.set_fixture(fixture(linked=False),'idle')
        await c.evaluate("window.__calls=[];document.getElementById('open-workspace').click();true")
        await check('unlinked_workspace_button_cannot_open_any_folder', "(!__visible('open-workspace')||document.getElementById('open-workspace').disabled)&&!window.__calls.some(x=>x.name==='project_open_folder')")

        # The compact history shows only three actual file actions for this project.
        recent=fixture(enabled=True);recent['project_goal']='Een eerder opgeslagen projectdoel hoort hier niet meer zichtbaar te zijn.'
        recent['recent_activity']=[
            {'project_id':PROJECT['id'],'action':'read_file','path':'oud.txt','time':100},
            {'project_id':PROJECT['id'],'action':'read_file','path':'bron.md','time':200},
            {'project_id':PROJECT['id'],'action':'propose_file','path':hostile,'time':300},
            {'project_id':PROJECT['id'],'action':'save_file','path':'nieuw.md','time':400},
            {'project_id':other_overview['project']['id'],'action':'save_file','path':'ander-project-geheim.txt','time':500}]
        await c.set_fixture(recent,'connected')
        await c.evaluate("window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:221,pending:false});window.__emit('project-details',"+json.dumps(details)+");window.__emit('chrome-panel','files');true")
        await check('recent_file_actions_are_limited_to_the_latest_three_current_project_records', "__visible('recent-file-actions')&&document.getElementById('recent-file-actions-list').children.length===3&&document.getElementById('recent-file-actions-list').textContent.includes('bron.md')&&document.getElementById('recent-file-actions-list').textContent.includes('nieuw.md')&&!document.getElementById('recent-file-actions-list').textContent.includes('oud.txt')&&!document.getElementById('recent-file-actions-list').textContent.includes('ander-project-geheim.txt')&&!__visible('recent-file-actions-empty')")
        await check('proposed_and_saved_actions_are_distinct_and_paths_are_inert', "document.getElementById('recent-file-actions-list').textContent.includes(window.vibezLanguage.t('fileActionProposed'))&&document.getElementById('recent-file-actions-list').textContent.includes(window.vibezLanguage.t('fileActionSaved'))&&document.getElementById('recent-file-actions-list').textContent.includes("+json.dumps(hostile)+")&&!document.querySelector('#recent-file-actions-list img,#recent-file-actions-list script')&&!window.__fileInjected&&document.documentElement.scrollWidth<=innerWidth")
        await c.screenshot(out/'project-overview-806.png')
        await c.evaluate("document.getElementById('recent-file-actions').scrollIntoView({block:'end'});true")
        await c.screenshot(out/'project-recent-actions-806.png')
        await c.set_fixture(other_overview,'idle')
        await check('switching_project_clears_the_previous_file_action_summary', "__visible('recent-file-actions-empty')&&document.getElementById('recent-file-actions-empty').textContent===window.vibezLanguage.t('noRecentFileActions')&&!document.getElementById('recent-file-actions-list').children.length&&!document.getElementById('recent-file-actions').textContent.includes('nieuw.md')")

        # Only one linked workspace is shown; root-set selection is gone.
        await c.set_fixture(fixture(enabled=True),'connected')
        await c.evaluate("window.__calls=[];window.__emit('chrome-panel','files');window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:300,pending:false});true")
        await check('single_workspace_has_no_destination_selector_or_multi_root_help', "!document.getElementById('workspace-select')&&!document.getElementById('workspace-select-label')&&!document.getElementById('multi-workspace-note')&&__visible('web-folder-name')&&__visible('open-workspace')&&__visible('web-folder-button')&&document.getElementById('web-folder').textContent==="+json.dumps(FIXTURE_PATH)+"&&window.__fixtureState.folders.length===1&&!document.getElementById('project-add-folder')&&document.documentElement.scrollWidth<=innerWidth")
        await c.evaluate("window.__calls=[];window.__holdFolderChooser=true;document.getElementById('web-folder-button').click();true")
        changed=fixture(enabled=True);changed['folder']='/voorbeelden/Andere-werkmap';changed['import_binding']='b'*64
        await c.set_fixture(changed,'connected')
        await c.evaluate("window.__resolveFolderChooser('/voorbeelden/Verouderde-vervanging');true")
        await asyncio.sleep(.04)
        await check('a_late_replace_cannot_apply_to_a_changed_workspace_of_the_same_project', "window.__calls.length===1&&window.__calls[0].name==='web_choose_folder'&&document.getElementById('web-folder').textContent==='/voorbeelden/Andere-werkmap'&&document.getElementById('project-drop-hint').textContent.includes('Andere-werkmap')&&!document.getElementById('project-drop-hint').textContent.includes('CityTripXL')&&!document.getElementById('web-folder-button').disabled")
        await c.set_fixture(fixture(enabled=True),'connected')
        await c.evaluate("window.__calls=[];window.__nextFolderResult='/voorbeelden/Vervangen-werkmap';document.getElementById('web-folder-button').click();true")
        await asyncio.sleep(.04)
        await check('changing_workspace_replaces_the_single_link_instead_of_adding_a_root', "(()=>{const p=window.__calls.find(x=>x.name==='web_command')?.args?.payload;return p?.action==='web_link'&&p.folder_id==="+json.dumps(ROOT_ONE)+"&&window.__fixtureState.folders.length===1&&window.__fixtureState.folders[0].path==='/voorbeelden/Vervangen-werkmap'&&document.getElementById('web-folder').textContent==='/voorbeelden/Vervangen-werkmap'&&document.getElementById('project-drop-hint').textContent.includes('Vervangen-werkmap')&&document.getElementById('subfolder-location').textContent.includes('Vervangen-werkmap')&&!document.getElementById('project-drop-hint').textContent.includes('CityTripXL')&&!window.__calls.some(x=>x.args?.payload?.action==='web_add_folder');})()")

        # Folder creation is an explicit local action in the one linked workspace.
        await c.set_fixture(fixture(enabled=True),'connected')
        await c.evaluate("window.__folderCalls=()=>window.__calls.filter(x=>x.name==='web_command'&&x.args.payload.action==='web_create_folder');window.__setFolderName=value=>{const input=document.getElementById('new-folder-name');input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));};window.__calls=[];document.getElementById('project-new-folder').click();true")
        await check('new_folder_opens_an_inline_local_form_without_another_root_picker', "__visible('new-folder-form')&&document.activeElement===document.getElementById('new-folder-name')&&document.getElementById('project-new-folder').textContent===window.vibezLanguage.t('newFolder')&&__visible('subfolder-location')&&document.getElementById('subfolder-location').textContent===__folderCopy('subfolderLocation')&&document.getElementById('main-folder-label').textContent===window.vibezLanguage.t('mainFolder')&&!window.__calls.some(x=>x.name==='web_choose_folder')&&!document.getElementById('workspace-select')&&!document.getElementById('project-add-folder')")
        await c.evaluate("__setFolderName('Documenten');window.__deferFolderResult=true;document.getElementById('create-folder').click();true")
        await asyncio.sleep(.04)
        await check('new_folder_request_is_scoped_and_transport_ack_does_not_claim_success', "(()=>{const calls=__folderCalls(),p=calls[0]?.args?.payload;return calls.length===1&&p.name==='Documenten'&&p.project_id==="+json.dumps(PROJECT['id'])+"&&p.workspace_binding===window.__fixtureState.workspace_binding&&typeof p.request_id==='string'&&p.request_id.length>0&&!('path'in p)&&document.getElementById('create-folder').disabled&&document.getElementById('cancel-new-folder').disabled&&!document.getElementById('new-folder-status').textContent.includes(__folderCopy('folderCreated'))&&!window.__calls.some(x=>x.name==='app_open_login'||x.args?.payload?.action==='web_connect'||x.args?.payload?.action==='web_add_folder');})()")
        await c.evaluate("window.__emit('app-engine',{...window.__pendingFolderResult,request_id:window.__pendingFolderResult.request_id+'-late'});true")
        await check('unmatched_folder_result_cannot_complete_a_new_folder_request', "document.getElementById('create-folder').disabled&&__visible('new-folder-form')&&!document.getElementById('new-folder-status').textContent.includes(__folderCopy('folderCreated'))")
        await c.evaluate("window.__emit('app-engine',window.__pendingFolderResult);true")
        await check('matching_folder_creation_result_confirms_success_without_changing_the_root', "!__visible('new-folder-form')&&document.getElementById('new-folder-status').textContent.includes(__folderCopy('folderCreated'))&&!document.getElementById('project-new-folder').disabled&&document.getElementById('web-folder').textContent==="+json.dumps(FIXTURE_PATH)+"&&window.__fixtureState.folders.length===1&&document.getElementById('new-folder-status').textContent.includes('CityTripXL')&&document.getElementById('new-folder-status').textContent.includes('Documenten')&&document.getElementById('auto-status').textContent===window.vibezLanguage.t('filesConnected')")
        await c.screenshot(out/'subfolder-created-806.png')
        await c.evaluate("window.__calls=[];document.getElementById('project-new-folder').click();__setFolderName('Documenten');window.__folderCreateError='Er bestaat al een bestand of map met deze naam.';document.getElementById('create-folder').click();true")
        await asyncio.sleep(.04)
        await check('folder_creation_error_keeps_the_name_for_correction_and_allows_retry', "__folderCalls().length===1&&__visible('new-folder-form')&&document.getElementById('new-folder-name').value==='Documenten'&&!document.getElementById('create-folder').disabled&&!document.getElementById('cancel-new-folder').disabled&&document.getElementById('new-folder-status').textContent.includes(window.vibezLanguage.t('folderCreateFailed'))&&!document.getElementById('new-folder-status').textContent.includes(__folderCopy('folderCreated'))")
        await c.screenshot(out/'subfolder-existing-806.png')
        await c.evaluate("window.__subfolderLocaleFailures=[];(()=>{let revision=310;for(const option of window.VIBEZ_TRANSLATIONS.options.filter(o=>o.code!=='system')){window.__emit('language-state',{language:option.code,resolved:option.code,site_locale:'en',revision:revision++,pending:false});const expected=window.VIBEZ_TRANSLATIONS.new[option.code];if(document.getElementById('project-new-folder').textContent!==expected.newFolder||document.querySelector('[for=new-folder-name]').textContent!==expected.folderName||document.getElementById('create-folder').textContent!==expected.createFolder||document.getElementById('main-folder-label').textContent!==expected.mainFolder||document.getElementById('subfolder-location').textContent!==expected.subfolderLocation.split('{folder}').join(__rootName())||document.getElementById('project-drop-hint').textContent!==expected.dropProjectItems.split('{folder}').join(__rootName())||!document.getElementById('new-folder-status').textContent.includes(expected.folderCreateFailed)||document.documentElement.scrollWidth>innerWidth)window.__subfolderLocaleFailures.push(option.code);}window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:399,pending:false});})();true")
        report['subfolder_locale_failures']=await c.evaluate('window.__subfolderLocaleFailures')
        await check('new_folder_form_and_failure_translate_in_all_33_languages_without_overflow', 'window.__subfolderLocaleFailures.length===0')
        await c.evaluate("window.__calls=[];document.getElementById('cancel-new-folder').click();true")
        await check('canceling_a_new_folder_clears_the_form_without_a_filesystem_request', "!__visible('new-folder-form')&&!document.getElementById('new-folder-name').value&&!__folderCalls().length")
        await c.evaluate("document.getElementById('project-new-folder').click();__setFolderName('Later');window.__deferFolderResult=true;document.getElementById('create-folder').click();true")
        await asyncio.sleep(.03)
        changed_folder=fixture(enabled=True);changed_folder['folder']='/voorbeelden/Andere-werkmap';changed_folder['import_binding']='b'*64;single_root_metadata(changed_folder)
        await c.set_fixture(changed_folder,'connected')
        await c.evaluate("window.__emit('app-engine',window.__pendingFolderResult);true")
        await check('late_folder_result_cannot_claim_success_in_a_replaced_workspace', "!__visible('new-folder-form')&&!document.getElementById('new-folder-name').value&&!document.getElementById('new-folder-status').textContent&&document.getElementById('web-folder').textContent==='/voorbeelden/Andere-werkmap'")
        await c.set_fixture(fixture(enabled=True),'connected')
        await c.evaluate("window.__calls=[];document.getElementById('project-new-folder').click();__setFolderName('Andere-context');window.__deferFolderResult=true;document.getElementById('create-folder').click();true")
        await asyncio.sleep(.03)
        foreign=fixture(enabled=True);foreign['project']={'id':'code-229ee257-1234-4567-890a-123456789abc','name':'Code Beta'};foreign['folder']='/voorbeelden/Beta';single_root_metadata(foreign)
        await c.set_fixture(foreign,'connected')
        await c.evaluate("window.__emit('app-engine',window.__pendingFolderResult);true")
        await check('late_folder_result_cannot_reopen_or_confirm_the_previous_context', "document.getElementById('web-project-name').textContent==='Code Beta'&&!__visible('new-folder-form')&&!document.getElementById('new-folder-status').textContent&&!document.getElementById('new-folder-name').value")
        await c.set_fixture(fixture(enabled=True),'connected')
        await c.evaluate("window.__calls=[];document.getElementById('project-new-folder').click();__setFolderName('Opnieuw');window.__failFolderCreateCommand=true;document.getElementById('create-folder').click();true")
        await asyncio.sleep(.04)
        await check('folder_command_failure_keeps_the_form_retryable_without_claiming_success', "__folderCalls().length===1&&__visible('new-folder-form')&&document.getElementById('new-folder-name').value==='Opnieuw'&&!document.getElementById('create-folder').disabled&&document.getElementById('new-folder-status').textContent.includes(window.vibezLanguage.t('folderCreateFailed'))")
        await c.evaluate("document.getElementById('cancel-new-folder').click();true")

        # Standalone conversations keep independent aliases, workspaces and labels.
        chat=conversation_fixture(linked=False)
        await c.set_fixture(chat,'idle')
        await c.evaluate("window.__emit('project-details',"+json.dumps(details)+");window.__emit('chrome-panel','files');true")
        await check('conversation_has_its_own_labels_scope_and_no_project_settings', "document.getElementById('context-panel-label').textContent===window.vibezLanguage.t('conversationPanel')&&document.getElementById('web-project-name').textContent==='Reisideeën'&&document.getElementById('files-section-heading').textContent===window.vibezLanguage.t('mainFolderSetup')&&__visible('web-project-note')&&document.getElementById('web-project-note').textContent===window.vibezLanguage.t('conversationFolderNote')&&document.getElementById('context-scope-note').textContent===window.vibezLanguage.t('conversationScopeNote')&&document.getElementById('context-setup-note').textContent===window.vibezLanguage.t('conversationSetupNote')&&document.getElementById('import-conflict-help').textContent===window.vibezLanguage.t('conversationImportConflictHelp')&&document.getElementById('mistral-project-settings').hidden&&!__visible('project-rules')")
        draft=conversation_fixture(draft=True,linked=False)
        await c.set_fixture(draft,'idle')
        await check('new_conversation_is_localized_and_can_choose_its_own_workspace', "document.getElementById('web-project-name').textContent===window.vibezLanguage.t('newConversation')&&document.getElementById('web-project-note').textContent===window.vibezLanguage.t('draftConversationNote')&&__visible('auto-connect')&&!document.getElementById('auto-connect').disabled&&document.getElementById('project-drop-hint').textContent===window.vibezLanguage.t('dropChooseWorkspace')&&document.getElementById('recent-file-actions-empty').textContent===window.vibezLanguage.t('noRecentConversationActions')&&!document.getElementById('web-project-name').textContent.includes('chat-')")
        await c.screenshot(out/'new-conversation-806.png')
        await c.evaluate("window.__calls=[];window.__holdFolderChooser=true;document.getElementById('auto-connect').click();document.getElementById('auto-connect').click();true")
        promoted=conversation_fixture(linked=False,name='Mijn eerste reisvraag')
        await c.set_fixture(promoted,'idle')
        await c.evaluate("window.__resolveFolderChooser('/voorbeelden/Gespreksmap');true")
        await asyncio.sleep(.05)
        await check('first_message_promotion_keeps_the_alias_for_a_pending_folder_choice', "window.__calls.filter(x=>x.name==='web_choose_folder').length===1&&window.__calls.filter(x=>x.name==='web_command'&&x.args.payload.action==='web_link').length===1&&window.__calls.find(x=>x.name==='web_command'&&x.args.payload.action==='web_link').args.payload.project_id==="+json.dumps(CONVERSATION_ALIAS)+"&&document.getElementById('web-project-name').textContent==='Mijn eerste reisvraag'&&document.getElementById('web-folder').textContent==='/voorbeelden/Gespreksmap'&&!window.__calls.some(x=>x.name==='app_open_login'||x.args?.payload?.action==='web_connect')")
        next_alias='chat-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
        busy_draft=conversation_fixture(draft=True,enabled=True,alias=next_alias)
        busy_draft['recent_activity']=[{'project_id':next_alias,'action':'read_file','path':'eigen-gesprek.txt','time':200}]
        await c.set_fixture(busy_draft,'connected')
        await c.evaluate("window.__calls=[];document.getElementById('project-add-files').click();true")
        await asyncio.sleep(.03)
        busy_promoted=conversation_fixture(enabled=True,alias=next_alias,name='Mijn gestarte gesprek')
        busy_promoted['recent_activity']=busy_draft['recent_activity']
        await c.evaluate("window.__fixtureState="+json.dumps(busy_promoted)+";window.__emit('app-engine',window.__fixtureState);true")
        await check('same_alias_promotion_preserves_import_busy_connection_and_recent_actions', "document.getElementById('web-project-name').textContent==='Mijn gestarte gesprek'&&document.getElementById('project-add-files').disabled&&document.getElementById('project-import-status').textContent===window.vibezLanguage.t('copyingFiles')&&document.getElementById('auto-status').textContent===window.vibezLanguage.t('filesConnected')&&document.getElementById('recent-file-actions-list').textContent.includes('eigen-gesprek.txt')")
        await c.evaluate("window.__emit('app-engine',{type:'web_import_result',project_id:"+json.dumps(next_alias)+",binding:"+json.dumps(IMPORT_BINDING)+",count:1});true")
        await check('promoted_conversation_accepts_only_its_scoped_import_result', "!document.getElementById('project-add-files').disabled&&document.getElementById('project-import-status').textContent===window.vibezLanguage.t('filesCopied').replace('{count}','1')")
        other_chat=conversation_fixture(alias='chat-99999999-8888-4777-8666-555555555555',name='Ander gesprek',binding='b'*64)
        other_chat['folder']='/voorbeelden/Andere-gespreksmap'
        other_chat['project']['conversation_id']='99999999-1111-4222-8333-444444444444'
        await c.set_fixture(other_chat,'idle')
        await c.evaluate("window.__emit('app-engine',{type:'web_import_result',project_id:"+json.dumps(next_alias)+",binding:"+json.dumps(IMPORT_BINDING)+",count:77});true")
        await check('a_different_conversation_clears_import_and_recent_state_from_the_old_alias', "document.getElementById('web-project-name').textContent==='Ander gesprek'&&!document.getElementById('project-import-status').textContent&&document.getElementById('recent-file-actions-empty').textContent===window.vibezLanguage.t('noRecentConversationActions')&&!document.getElementById('recent-file-actions-list').textContent.includes('eigen-gesprek.txt')&&document.getElementById('project-drop-hint').textContent.includes('Andere-gespreksmap')&&!document.getElementById('project-drop-hint').textContent.includes('CityTripXL')")
        await c.set_fixture(conversation_fixture(linked=False),'idle')
        await c.evaluate("window.__calls=[];window.__holdFolderChooser=true;document.getElementById('auto-connect').click();true")
        other_unlinked=conversation_fixture(alias=other_chat['project']['id'],name='Ander gesprek',linked=False)
        await c.set_fixture(other_unlinked,'idle')
        await c.evaluate("window.__resolveFolderChooser('/voorbeelden/Verouderde-gespreksmap');true")
        await asyncio.sleep(.04)
        await check('late_panel_folder_choice_cannot_link_the_previous_conversation', "window.__calls.filter(x=>x.name==='web_choose_folder').length===1&&!window.__calls.some(x=>x.name==='web_command'&&x.args.payload.action==='web_link')&&!document.getElementById('web-folder').textContent&&!__visible('auto-status')")
        await c.set_fixture(conversation_fixture(linked=False),'idle')
        await c.evaluate("window.__holdFolderChooser=true;document.getElementById('auto-connect').click();true")
        await c.set_fixture(other_unlinked,'idle')
        await c.evaluate("window.__rejectFolderChooser(new Error('Voorbeeld: oude mapkeuze mislukt.'));true")
        await asyncio.sleep(.04)
        await check('late_panel_picker_failure_does_not_pollute_the_next_conversation', "document.getElementById('web-project-name').textContent==='Ander gesprek'&&!__visible('auto-status')&&!document.getElementById('auto-connect').disabled")
        await c.set_fixture(conversation_fixture(draft=True,linked=False),'idle')
        await c.evaluate("window.__conversationLocaleFailures=[];(()=>{let revision=400;for(const option of window.VIBEZ_TRANSLATIONS.options.filter(o=>o.code!=='system')){window.__emit('language-state',{language:option.code,resolved:option.code,site_locale:'en',revision:revision++,pending:false});const expected=window.VIBEZ_TRANSLATIONS.new[option.code];if(document.getElementById('context-panel-label').textContent!==expected.conversationPanel||document.getElementById('web-project-name').textContent!==expected.newConversation||document.getElementById('web-project-note').textContent!==expected.draftConversationNote||document.getElementById('files-section-heading').textContent!==expected.mainFolderSetup||document.getElementById('recent-file-actions-empty').textContent!==expected.noRecentConversationActions||document.getElementById('project-drop-hint').textContent!==expected.dropChooseWorkspace||document.documentElement.scrollWidth>innerWidth)window.__conversationLocaleFailures.push(option.code);}window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:500,pending:false});})();true")
        report['conversation_locale_failures']=await c.evaluate('window.__conversationLocaleFailures')
        await check('conversation_labels_and_draft_names_update_in_all_33_languages_without_overflow', 'window.__conversationLocaleFailures.length===0')
        await c.set_fixture(conversation_fixture(enabled=True),'connected')
        await c.evaluate("window.__emit('chrome-panel','files');true")
        await c.screenshot(out/'conversation-overview-806.png')
        await c.set_fixture(fixture(),'paused',pause_reason='context')
        await c.evaluate("window.__emit('project-details',"+json.dumps(details)+");true")
        await check('project_context_restores_project_labels_and_its_existing_settings', "document.getElementById('context-panel-label').textContent===window.vibezLanguage.t('projectPanel')&&document.getElementById('files-section-heading').textContent===__rootName()&&document.getElementById('web-project-note').hidden&&document.getElementById('context-scope-note').textContent===window.vibezLanguage.t('scopeNote')&&!document.getElementById('mistral-project-settings').hidden")
        await c.set_fixture(no_project,'idle')
        await check('no_context_hint_accepts_either_a_project_or_conversation', "document.getElementById('web-project-name').textContent===window.vibezLanguage.t('openProjectOrConversation')&&document.getElementById('web-project-note').textContent===window.vibezLanguage.t('openProjectOrConversation')&&!__visible('auto-connect')&&!__visible('create-workspace')&&!__visible('project-rules')")
        await check('updater_startup_only_reads_native_state_without_requesting_permission', "window.__calls.filter(x=>x.name==='alpha_update_state').length<=1&&!window.__calls.some(x=>x.name==='alpha_update_allow'||x.name==='alpha_update_check')")
        await c.evaluate("window.__emit('chrome-panel','settings');window.__calls=[];true")
        await check('update_controls_only_appear_inside_settings', "__visible('alpha-updates')&&document.getElementById('panel-settings').contains(document.getElementById('alpha-updates'))&&document.getElementById('alpha-update-allow').hidden&&document.getElementById('alpha-update-status').textContent===window.vibezLanguage.t('updateCurrent')")
        await c.evaluate("window.__emit('alpha-flatpak-update',{kind:'flatpak',status:'ready',automatic:true,consent_required:true,available:false});true")
        await check('flatpak_idle_current_still_offers_one_time_permission', "__visible('alpha-update-allow')&&!document.getElementById('alpha-update-allow').disabled&&document.getElementById('alpha-update-status').textContent===window.vibezLanguage.t('updatePermission')&&!window.__calls.some(x=>x.name==='alpha_update_allow')")
        await c.evaluate("document.getElementById('alpha-update-allow').click();document.getElementById('alpha-update-allow').click();true")
        await asyncio.sleep(.04)
        await check('one_explicit_permission_click_hides_consent_after_success', "window.__calls.filter(x=>x.name==='alpha_update_allow').length===1&&document.getElementById('alpha-update-allow').hidden&&document.getElementById('alpha-update-status').textContent===window.vibezLanguage.t('updateCurrent')")
        await c.evaluate("window.__holdUpdateCheck=true;document.getElementById('alpha-update-check').click();document.getElementById('alpha-update-check').click();window.__emit('alpha-update',{kind:'native',status:'downloading'});true")
        await check('checking_blocks_duplicate_clicks_and_displays_live_download_progress', "document.getElementById('alpha-update-check').disabled&&document.getElementById('alpha-update-status').getAttribute('aria-busy')==='true'&&window.__calls.filter(x=>x.name==='alpha_update_check').length===1&&document.getElementById('alpha-update-status').textContent===window.vibezLanguage.t('updateDownloading')")
        await c.evaluate("window.__emit('alpha-update',{kind:'native',status:'ready',restart_required:true});window.__resolveUpdateCheck({kind:'native',status:'current'});true")
        await asyncio.sleep(.04)
        await check('late_check_response_cannot_overwrite_a_downloaded_update', "!document.getElementById('alpha-update-check').disabled&&document.getElementById('alpha-update-status').textContent===window.vibezLanguage.t('updateReady')")
        await c.evaluate("window.__emit('alpha-flatpak-update',{kind:'flatpak',status:'screen_restricted',consent_required:true});true")
        await check('screen_restriction_never_offers_a_portal_permission_prompt', "document.getElementById('alpha-update-allow').hidden&&document.getElementById('alpha-update-status').textContent===window.vibezLanguage.t('updateScreenRestricted')")
        await c.evaluate("window.__emit('alpha-update',{kind:'system',status:'waiting_for_close'});true")
        await check('system_package_update_says_it_waits_for_close', "document.getElementById('alpha-update-status').textContent===window.vibezLanguage.t('updateWaiting')&&document.getElementById('alpha-update-allow').hidden")
        await c.evaluate("window.__updateLocaleFailures=[];window.__emit('alpha-flatpak-update',{kind:'flatpak',status:'ready',consent_required:true});(()=>{let revision=600;for(const option of window.VIBEZ_TRANSLATIONS.options.filter(o=>o.code!=='system')){window.__emit('language-state',{language:option.code,resolved:option.code,site_locale:'en',revision:revision++,pending:false});const t=window.VIBEZ_TRANSLATIONS.new[option.code];if(document.getElementById('alpha-update-heading').textContent!==t.updateTitle||document.getElementById('alpha-update-status').textContent!==t.updatePermission||document.getElementById('alpha-update-check').textContent!==t.updateCheck||document.getElementById('alpha-update-allow').textContent!==t.updateAllow||document.documentElement.scrollWidth>innerWidth)window.__updateLocaleFailures.push(option.code);}window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:700,pending:false});})();true")
        report['update_locale_failures']=await c.evaluate('window.__updateLocaleFailures')
        await check('update_status_and_buttons_follow_all_33_languages_without_overflow', 'window.__updateLocaleFailures.length===0')
        await c.evaluate("window.__updateCalls=window.__calls.length;window.postMessage({name:'alpha_update_allow'},'*');window.dispatchEvent(new CustomEvent('alpha-update',{detail:{status:'ready'}}));window.__emit('alpha-update',{status:'invented'});window.__emit('alpha-update',null);window.__emit('alpha-update',{kind:'native',status:'error',error:'<img src=x onerror=alert(1)>'});true")
        await asyncio.sleep(.04)
        await check('remote_messages_cannot_request_updates_and_errors_remain_inert_text', "window.__calls.length===window.__updateCalls&&document.getElementById('alpha-update-status').textContent===window.vibezLanguage.t('updateError')&&document.getElementById('alpha-update-status').title==='<img src=x onerror=alert(1)>'&&document.getElementById('alpha-update-status').childElementCount===0&&!document.querySelector('#alpha-updates img,#alpha-updates script')")
        await c.evaluate("window.__emit('alpha-update',{kind:'system',status:'automatic',automatic:true});true")
        await c.screenshot(out/'alpha-update-settings.png')
        report['javascript_errors'] = await c.evaluate('window.__errors')
        report['runtime_exceptions'] = c.exceptions
        assert not report['javascript_errors'], report['javascript_errors']
        assert not c.exceptions, c.exceptions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=BASE / 'artifacts' / 'panel-ui-test61')
    parser.add_argument('--width', type=int, default=400)
    parser.add_argument('--height', type=int, default=900)
    args = parser.parse_args()
    out = args.output.resolve();out.mkdir(parents=True, exist_ok=True)
    report = {'version': VERSION, 'passed': False, 'headless': True, 'visible_windows': False,
              'isolated_profile': True, 'fixture_only': True, 'live_mistral': False,
              'viewport': [args.width, args.height], 'checks': {}}
    process = None
    tempdir = None
    try:
        tempdir = tempfile.TemporaryDirectory(prefix='vibez-panel-headless-')
        temp = Path(tempdir.name)
        dist = BASE / 'desktop/dist'
        shim = SHIM.replace('__INITIAL__', json.dumps(fixture())).replace('__VERSION__', json.dumps(VERSION))
        html = (dist / 'panel.html').read_text()
        html = html.replace('<head>', '<head><base href="' + dist.as_uri() + '/"><script>' + shim + '</script>', 1)
        page = temp / 'panel-fixture.html';page.write_text(html)
        profile = temp / 'profile'
        with (out / 'chromium.log').open('w') as log:
            process = subprocess.Popen(['/usr/bin/chromium', '--headless=new', '--no-sandbox',
                '--disable-gpu', '--disable-background-networking', '--disable-component-update',
                '--disable-sync', '--no-first-run', '--no-default-browser-check',
                '--allow-file-access-from-files', '--force-device-scale-factor=1',
                '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
                '--user-data-dir=' + str(profile), 'about:blank'],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            port_file = profile / 'DevToolsActivePort';deadline = time.monotonic() + 12
            while not port_file.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.1)
            if not port_file.exists():raise RuntimeError('Headless Chromium did not expose its isolated debugging endpoint')
            port = int(port_file.read_text().splitlines()[0])
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open('http://127.0.0.1:' + str(port) + '/json/list', timeout=5) as response:
                pages = json.load(response)
            ws_url = next(p['webSocketDebuggerUrl'] for p in pages if p['type'] == 'page')
            asyncio.run(exercise(ws_url, page.as_uri(), out, args.width, args.height, report))
            report['passed'] = True
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        if tempdir is not None:tempdir.cleanup()
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
