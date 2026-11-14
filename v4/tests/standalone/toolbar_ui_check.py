#!/usr/bin/python3
"""Test the shipped toolbar with invented events in isolated headless Chromium.

No visible window, real account, native application or user project is opened.
"""
import argparse
import asyncio
import base64
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

import websockets
from panel_ui_check import CDP

BASE = Path(__file__).resolve().parents[2]
VERSION = json.loads((BASE/'desktop/src-tauri/tauri.conf.json').read_text())['version']
A = {'id': 'code-11111111-2222-4333-8444-555555555555', 'name': 'Proefproject Alpha'}
B = {'id': 'code-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', 'name': 'Proefproject Beta'}
CONVERSATION = {'id':'chat-11111111-2222-4333-8444-555555555555',
                'kind':'conversation','draft':False,'name':'Reisideeën',
                'conversation_id':'44444444-5555-4666-8777-888888888888'}
DRAFT_CONVERSATION = {**CONVERSATION,'draft':True,'name':'','conversation_id':None}
ROOT_ONE='1'*32


def state(*, project=A, folder='/voorbeelden/Alpha', enabled=True,
          tunnel='running', manual=False, pending=None):
    revision=hashlib.sha256(json.dumps([project and project['id'],folder]).encode()).hexdigest() if folder else ''
    return {'type': 'web_connector', 'project': project, 'folder': folder,
            'folders':[{'id':ROOT_ONE,'path':folder,'alias':'Map1'}] if folder else [],
            'target_folder_id':ROOT_ONE if folder else None,'workspace_binding':revision,
            'enabled': enabled, 'tunnel_status': tunnel,
            'manually_paused': manual, 'auto_approved': True,
            'pending': pending or [], 'activity': []}


def automatic(status='connected', *, project=A, reason=None):
    return {'type': 'web_auto', 'project_id': project['id'],
            'status': status, 'pause_reason': reason}


SHIM = r"""
window.__calls=[];window.__errors=[];window.__listeners={};
window.addEventListener('error',e=>window.__errors.push(String(e.message)));
window.addEventListener('unhandledrejection',e=>window.__errors.push(String(e.reason)));
window.__emit=(name,payload)=>{for(const fn of window.__listeners[name]||[])fn({payload});};
window.__web=__WEB__;window.__auto=__AUTO__;
window.__setToolbar=(web,automatic)=>{
 window.__web=JSON.parse(JSON.stringify(web));window.__emit('app-engine',window.__web);
 if(automatic){window.__auto=JSON.parse(JSON.stringify(automatic));window.__emit('app-engine',window.__auto);}
};
window.__TAURI__={event:{listen:async(name,fn)=>{
 (window.__listeners[name]||=[]).push(fn);return ()=>{};
}},core:{invoke:async(name,args)=>{
 window.__calls.push({name,args});
 if(name==='language_get')return {language:'nl',resolved:'nl',site_locale:'nl',revision:1,pending:false};
 if(name==='app_info')return {version:__VERSION__,screen:'Scherm 1'};
 if(name==='web_surface'){window.__setToolbar(window.__web,window.__auto);return null;}
 if(name==='chrome_panel'){window.__emit('chrome-panel',args.mode);return null;}
 return null;
}}};
"""


async def exercise(ws_url, url, out, report):
    async with websockets.connect(ws_url, max_size=10_000_000, ping_interval=None) as ws:
        c = CDP(ws)
        await c.call('Page.enable')
        await c.call('Runtime.enable')
        await c.call('Network.enable')
        await c.call('Network.setBlockedURLs', {'urls': ['http://*', 'https://*']})
        await c.call('Emulation.setEmulatedMedia', {'features': [
            {'name': 'prefers-reduced-motion', 'value': 'no-preference'}]})

        async def viewport(width):
            await c.call('Emulation.setDeviceMetricsOverride', {'width': width,
                'height': 90, 'deviceScaleFactor': 1, 'mobile': False})
            await asyncio.sleep(.05)

        async def check(name, expression):
            report['checks'][name] = bool(await c.evaluate(expression))
            if not report['checks'][name]:
                raise AssertionError(name)

        async def emit(web, auto=None):
            await c.evaluate('window.__setToolbar('+json.dumps(web)+','+json.dumps(auto)+');true')
            await asyncio.sleep(.05)

        async def screenshot(name, width=1280):
            result = await c.call('Page.captureScreenshot', {'format': 'png',
                'captureBeyondViewport': False,
                'clip': {'x': 0, 'y': 0, 'width': width, 'height': 54, 'scale': 1}})
            (out/name).write_bytes(base64.b64decode(result['data']))

        await viewport(1280)
        await c.call('Page.navigate', {'url': url})
        for _ in range(100):
            if await c.evaluate("Boolean(window.__calls?.some(x=>x.name==='web_surface'))&&document.getElementById('connection-indicator')?.dataset.state==='connected'"):
                break
            await asyncio.sleep(.1)
        else:
            raise RuntimeError('The shipped toolbar did not reach its invented connected state')
        await c.evaluate("window.__indicator=()=>document.getElementById('connection-indicator');window.__link=()=>document.querySelector('.connection-link');window.__cross=()=>document.querySelector('.connection-cross');window.__crossVisible=()=>{const n=__cross(),s=n&&getComputedStyle(n);return !!n&&n.getClientRects().length>0&&s.display!=='none'&&s.visibility!=='hidden'&&parseFloat(s.opacity)>0;};window.__motion=()=>getComputedStyle(__link()).animationName;window.__offset=()=>parseFloat(getComputedStyle(__link()).strokeDashoffset);window.__layout=()=>{const selectors=['.brand-wrap','.nav-controls','#connection-indicator','#status','.toolbar-actions'];const boxes=selectors.map(selector=>{const n=document.querySelector(selector),r=n.getBoundingClientRect();return {selector,x:r.left,y:r.top,right:r.right,bottom:r.bottom,width:r.width,visible:!!r.width&&getComputedStyle(n).display!=='none'&&(selector!=='#status'||!!n.textContent)};}).filter(x=>x.visible).sort((a,b)=>a.x-b.x);return {width:innerWidth,boxes,okay:document.documentElement.scrollWidth<=innerWidth&&boxes.every(x=>x.x>=-.5&&x.right<=innerWidth+.5&&x.y>=-.5&&x.bottom<=54.5)&&boxes.every((x,i)=>!i||boxes[i-1].right<=x.x+.5)};};true")
        await c.evaluate("window.__centeredBetweenControls=()=>{const status=__indicator().getBoundingClientRect(),home=document.getElementById('home').getBoundingClientRect(),language=document.querySelector('.language-control').getBoundingClientRect();return Math.abs(status.left+status.width/2-(home.right+language.left)/2)<.5;};true")
        await c.evaluate("window.__statusOnlyAccessible=()=>{const n=document.getElementById('connection-label'),s=getComputedStyle(n),r=n.getBoundingClientRect();return r.width<=1&&r.height<=1&&s.position==='absolute'&&s.overflow==='hidden'&&s.display!=='none'&&n.getAttribute('role')==='status'&&n.getAttribute('aria-live')==='polite';};window.__namesOnlyTitle=()=>__indicator().title===[...new Set(['connection-project-name','connection-folder-name'].map(id=>document.getElementById(id).textContent).filter(Boolean))].join(' · ');true")
        await c.evaluate("window.__captionGeometry=()=>{const box=n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};return {button:box(__indicator()),visual:box(document.querySelector('.connection-visual')),globe:box(document.querySelector('.connection-globe circle')),folder:box(document.querySelector('.connection-folder')),project:box(document.getElementById('connection-project-name')),folderName:box(document.getElementById('connection-folder-name')),line:box(__link()),cross:box(__cross().querySelector('path'))};};window.__fixedIcons=()=>{const g=__captionGeometry(),cy=r=>r.y+r.height/2;return Math.abs(g.globe.width-22.5)<.1&&Math.abs(g.globe.height-22.5)<.1&&Math.abs(g.folder.width-25)<.1&&Math.abs(g.folder.height-22.5)<.1&&Math.abs(cy(g.globe)-cy(g.button))<.5&&Math.abs(cy(g.folder)-cy(g.button))<.5;};window.__inlineNames=()=>{const g=__captionGeometry(),cy=r=>r.y+r.height/2;return g.project.right<=g.globe.x&&g.folder.right<=g.folderName.x&&Math.abs(cy(g.project)-cy(g.button))<.5&&Math.abs(cy(g.folderName)-cy(g.button))<.5&&getComputedStyle(document.getElementById('connection-project-name')).fontSize==='12px'&&getComputedStyle(document.getElementById('connection-folder-name')).fontSize==='12px';};true")
        await c.evaluate("window.__nameWidths=()=>['connection-project-name','connection-folder-name'].map(id=>{const n=document.getElementById(id),range=document.createRange();range.selectNodeContents(n);return {id,box:n.getBoundingClientRect().width,text:range.getBoundingClientRect().width};});window.__namesFit=()=>__nameWidths().every(n=>n.text<=n.box+.01);true")
        await check('language_menu_has_33_languages_plus_system_without_russian', "window.VIBEZ_TRANSLATIONS.options.filter(o=>o.code!=='system').length===33&&document.getElementById('quick-language').options.length===34&&[...document.getElementById('quick-language').options].every(o=>o.value!=='ru'&&!/русский/i.test(o.textContent))")
        await check('toolbar_has_only_language_screenshot_settings_and_no_workspace_picker', "!document.getElementById('local-files')&&!document.querySelector('.folder-plus')&&document.querySelectorAll('.toolbar-actions .toolbar-action').length===3&&document.querySelector('.language-control').nextElementSibling?.id==='screenshot'&&document.getElementById('screenshot').nextElementSibling?.id==='settings'&&!window.__calls.some(x=>x.name==='web_choose_folder')")
        await check('connected_is_transparent_and_46px_high', "getComputedStyle(__indicator()).backgroundColor==='rgba(0, 0, 0, 0)'&&getComputedStyle(__indicator()).backgroundImage==='none'&&__indicator().getBoundingClientRect().height===46&&__centeredBetweenControls()")
        await check('connected_has_calm_three_second_animation', "__motion()==='connection-flow'&&getComputedStyle(__link()).animationDuration==='3s'")
        await check('connected_cross_is_hidden', "Boolean(__cross())&&!__crossVisible()")
        await asyncio.sleep(.17)
        await check('connected_label_diagram_and_link_are_green', "getComputedStyle(document.querySelector('.connection-label')).color==='rgb(74, 222, 128)'&&getComputedStyle(document.querySelector('.connection-globe')).stroke==='rgb(74, 222, 128)'&&getComputedStyle(document.querySelector('.connection-folder-icon')).stroke==='rgb(74, 222, 128)'&&getComputedStyle(__link()).stroke==='rgb(74, 222, 128)'")
        await check('toolbar_shows_project_and_folder_basename_beside_their_icons', "document.getElementById('connection-project-name').textContent==='Proefproject Alpha'&&document.getElementById('connection-folder-name').textContent==='Alpha'&&document.getElementById('connection-project-name').title==='Proefproject Alpha'&&document.getElementById('connection-folder-name').title==='Alpha'&&document.querySelector('.connection-visual').getBoundingClientRect().width<=255&&document.querySelector('.connection-visual').getBoundingClientRect().width>=120&&document.querySelector('.connection-visual').getBoundingClientRect().height===42&&__inlineNames()&&__fixedIcons()")
        await check('connected_shows_only_names_and_keeps_status_for_screen_readers', "__statusOnlyAccessible()&&__namesOnlyTitle()&&__indicator().getAttribute('aria-label').includes(window.vibezLanguage.t('connectionConnected'))&&__indicator().getAttribute('aria-label').includes(window.vibezLanguage.t('connectionOpenFiles'))&&['connection-project-name','connection-folder-name'].every(id=>document.getElementById(id).checkVisibility()&&document.getElementById(id).getBoundingClientRect().height>1)")
        connected_geometry = await c.evaluate("(()=>{const button=__indicator().getBoundingClientRect(),diagram=document.querySelector('.connection-diagram').getBoundingClientRect();return {buttonX:button.x,buttonWidth:button.width,diagramX:diagram.x,diagramY:diagram.y};})()")
        first = await c.evaluate('__offset()')
        await asyncio.sleep(.32)
        second = await c.evaluate('__offset()')
        report['checks']['connected_dash_offset_moves'] = abs(second-first) > .15
        if not report['checks']['connected_dash_offset_moves']:
            raise AssertionError('connected_dash_offset_moves')
        await screenshot('connected-1280.png')

        # Every inactive or unverified state stops the actual computed motion.
        variations = [
            ('paused', state(enabled=False), automatic('paused')),
            ('manual', state(enabled=False, manual=True), automatic('paused', reason='manual')),
            ('sign_in', state(enabled=False), automatic('paused', reason='sign_in')),
            ('error', state(enabled=False), automatic('error')),
            ('no_project', state(project=None, folder=None, enabled=False, tunnel='stopped'), None),
            ('no_folder', state(folder=None, enabled=False, tunnel='stopped'), automatic('idle')),
            ('disconnected', state(enabled=False), automatic('idle')),
            ('connecting', state(enabled=False, tunnel='starting'), automatic('connecting')),
        ]
        for expected, web, auto in variations:
            await emit(web, auto)
            await check(expected+'_stops_motion', "__indicator().dataset.state==="+json.dumps(expected)+"&&__motion()==='none'")
            await check(expected+'_keeps_transparent_background', "getComputedStyle(__indicator()).backgroundColor==='rgba(0, 0, 0, 0)'&&getComputedStyle(__indicator()).backgroundImage==='none'")
            await check(expected+'_has_no_visible_inline_status_or_status_tooltip', "__statusOnlyAccessible()&&__namesOnlyTitle()&&__indicator().getAttribute('aria-label').includes(document.getElementById('connection-label').textContent)&&__indicator().getAttribute('aria-label').includes(window.vibezLanguage.t('connectionOpenFiles'))")
            if expected == 'connecting':
                await check('connecting_cross_is_hidden', "Boolean(__cross())&&!__crossVisible()")
            else:
                await check(expected+'_shows_red_cross', "__crossVisible()&&getComputedStyle(__cross()).stroke==='rgb(255, 107, 107)'")
                await asyncio.sleep(.17)
                await check(expected+'_label_diagram_and_link_are_red_and_visible', "getComputedStyle(document.querySelector('.connection-label')).color==='rgb(255, 107, 107)'&&getComputedStyle(document.querySelector('.connection-globe')).stroke==='rgb(255, 107, 107)'&&getComputedStyle(document.querySelector('.connection-folder-icon')).stroke==='rgb(255, 107, 107)'&&getComputedStyle(__link()).stroke==='rgb(255, 107, 107)'&&parseFloat(getComputedStyle(__link()).opacity)>=.8")
            old = await c.evaluate('__offset()')
            await asyncio.sleep(.09)
            await check(expected+'_dash_offset_is_static', 'Math.abs(__offset()-'+json.dumps(old)+')<.01')
            if expected == 'paused':
                await screenshot('paused-1280.png')
            if expected in ['no_project', 'connecting', 'sign_in']:
                await screenshot(expected+'-1280.png')
            if expected == 'no_project':
                await check('unknown_project_hides_previous_project_and_folder_names', "document.getElementById('connection-project-name').hidden&&document.getElementById('connection-folder-name').hidden&&!document.getElementById('connection-project-name').textContent&&!document.getElementById('connection-folder-name').textContent")
            if expected == 'no_folder':
                await check('unlinked_project_only_shows_its_project_name', "document.getElementById('connection-project-name').textContent==='Proefproject Alpha'&&!document.getElementById('connection-project-name').hidden&&document.getElementById('connection-folder-name').hidden&&!document.getElementById('connection-folder-name').textContent")
            if expected == 'disconnected':
                await check('inline_names_and_flexible_connection_keep_icon_geometry_aligned_and_stable', "(()=>{const g=__captionGeometry(),before="+json.dumps(connected_geometry)+";const cy=r=>r.y+r.height/2,cx=r=>r.x+r.width/2;return g.button.height===46&&g.visual.width<=255&&g.visual.width>=120&&g.visual.height===42&&__statusOnlyAccessible()&&__fixedIcons()&&__inlineNames()&&cx(g.folder)-cx(g.globe)>=77.9&&cx(g.folder)-cx(g.globe)<=213.1&&Math.abs(cy(g.visual)-cy(g.button))<.5&&Math.abs(cy(g.globe)-cy(g.line))<.01&&Math.abs(cy(g.cross)-cy(g.line))<.01&&Math.abs(cx(g.cross)-cx(g.line))<.01&&Math.abs(g.button.x-before.buttonX)<.5&&Math.abs(g.button.width-before.buttonWidth)<.5&&Math.abs(g.visual.x-before.diagramX)<.5&&Math.abs(g.visual.y-before.diagramY)<.5&&getComputedStyle(__link()).strokeWidth==='3px'&&getComputedStyle(__link()).strokeDasharray==='3px, 7.5px'&&__link().getAttribute('vector-effect')==='non-scaling-stroke';})()")
                await screenshot('disconnected-1280.png')

        # Names remain plain text; only the linked folder's final component is shown.
        await c.evaluate('window.__captionInjected=false;true')
        hostile = '<img src=x onerror="window.__captionInjected=true">'
        cases = [
            ('linux', 'Project met spaties', '/voorbeelden/Map met spaties/', 'Map met spaties'),
            ('windows', 'Windows-project', 'C:\\Voorbeelden\\Werkmap\\', 'Werkmap'),
            ('hostile', hostile, '/voorbeelden/'+hostile, hostile),
            ('rtl', 'رحلة إلى المدينة', '/أمثلة/ملفات المشروع/', 'ملفات المشروع'),
        ]
        for kind, name, folder, basename in cases:
            project = {**A, 'name': name}
            await emit(state(project=project, folder=folder), automatic(project=project))
            await check(kind+'_project_and_folder_names_are_safe_plain_text', "(()=>{const p=document.getElementById('connection-project-name'),f=document.getElementById('connection-folder-name');return p.textContent==="+json.dumps(name)+"&&f.textContent==="+json.dumps(basename)+"&&p.title==="+json.dumps(name)+"&&f.title==="+json.dumps(basename)+"&&p.childElementCount===0&&f.childElementCount===0&&!window.__captionInjected&&__layout().okay;})()")
            if kind == 'rtl':
                await check('rtl_names_use_their_own_text_direction', "['connection-project-name','connection-folder-name'].every(id=>{const n=document.getElementById(id);return n.getAttribute('dir')==='auto'&&getComputedStyle(n).direction==='rtl';})")
                await screenshot('names-rtl-1280.png')
        long_project = {**A, 'name': 'Lang project '+('naam '*18).strip()}
        long_folder = 'Werkmap '+('lange naam '*12).strip()
        await emit(state(project=long_project, folder='/voorbeelden/'+long_folder), automatic(project=long_project))
        await check('long_names_are_truncated_visually_and_kept_in_tooltips', "(()=>{const p=document.getElementById('connection-project-name'),f=document.getElementById('connection-folder-name');return p.textContent==="+json.dumps(long_project['name'])+"&&f.textContent==="+json.dumps(long_folder)+"&&[p,f].every(n=>n.title===n.textContent&&n.scrollWidth>n.clientWidth&&getComputedStyle(n).textOverflow==='ellipsis'&&getComputedStyle(n).overflowX==='hidden'&&n.getBoundingClientRect().width<=240.5)&&__layout().okay&&__fixedIcons()&&__inlineNames()&&Math.abs(__captionGeometry().visual.width-120)<.5;})()")
        await screenshot('names-long-1280.png')

        # The wire yields space before moderate names need to be truncated.
        moderate_project={**A,'name':'Project voor een langere rondreis'}
        moderate_folder='Lokale documenten voor de rondreis'
        await viewport(2560)
        await emit(state(project=moderate_project,folder='/voorbeelden/'+moderate_folder),automatic(project=moderate_project))
        wide_geometry=await c.evaluate("({visual:__captionGeometry().visual.width,actions:[...document.querySelectorAll('.toolbar-action')].map(n=>({width:n.getBoundingClientRect().width,height:n.getBoundingClientRect().height}))})")
        await check('wide_indicator_retains_the_full_connection_span', "Math.abs(__captionGeometry().visual.width-255)<.1&&__fixedIcons()&&__inlineNames()&&__layout().okay&&__centeredBetweenControls()")
        await viewport(1280)
        report['caption_compression']=await c.evaluate('({geometry:__captionGeometry(),names:__nameWidths(),names_fit:__namesFit()})')
        await screenshot('names-inline-compressed-1280.png')
        await check('connection_shortens_before_moderate_names_or_action_buttons', "(()=>{const g=__captionGeometry(),wide="+json.dumps(wide_geometry)+";return g.visual.width<wide.visual-1&&g.visual.width>=120&&__namesFit()&&['connection-project-name','connection-folder-name'].every(id=>{const n=document.getElementById(id);return n.title===n.textContent;})&&[...document.querySelectorAll('.toolbar-action')].every((n,i)=>Math.abs(n.getBoundingClientRect().width-wide.actions[i].width)<.5&&n.getBoundingClientRect().height===wide.actions[i].height)&&__fixedIcons()&&__inlineNames()&&__namesOnlyTitle()&&__centeredBetweenControls()&&__layout().okay;})()")
        for width in [1100,980,960]:
            await viewport(width)
            await emit(state(project=long_project,folder='/voorbeelden/'+long_folder),automatic(project=long_project))
            await check('long_names_width_'+str(width)+'_preserves_icons_and_toolbar_controls', '__fixedIcons()&&__inlineNames()&&__layout().okay&&__centeredBetweenControls()&&__statusOnlyAccessible()&&__namesOnlyTitle()&&__captionGeometry().visual.width>=120&&__captionGeometry().visual.width<=255')
            if width==960:
                await screenshot('names-long-960.png',width=960)
        await viewport(1280)

        # A new project/folder must not inherit a prior verified connection.
        await emit(state(), automatic())
        await emit(state(project=B, folder='/voorbeelden/Beta'))
        await c.evaluate('window.__emit("app-engine",'+json.dumps(automatic())+');true')
        await check('project_change_invalidates_old_connected_state', "__indicator().dataset.state!=='connected'&&__motion()==='none'&&__indicator().title.includes('Proefproject Beta')&&!__indicator().title.includes('Proefproject Alpha')")
        await emit(state(), automatic())
        await emit(state(folder='/voorbeelden/Andere-map'))
        await check('folder_change_invalidates_old_connected_state', "__indicator().dataset.state!=='connected'&&__motion()==='none'")

        # The indicator only opens the familiar files panel, never a connection.
        await emit(state(), automatic())
        await c.evaluate("window.__calls=[];__indicator().click();true")
        await asyncio.sleep(.05)
        await check('indicator_click_only_opens_files_panel', "window.__calls.length===1&&window.__calls[0].name==='chrome_panel'&&window.__calls[0].args.mode==='files'&&__indicator().getAttribute('aria-expanded')==='true'&&!window.__calls.some(x=>x.name==='app_open_login'||x.args?.payload?.action==='web_connect')")
        # The connection caption remains meaningful without a workspace action.
        await check('single_workspace_caption_has_no_extra_root_count', "__indicator().dataset.state==='connected'&&document.getElementById('connection-folder-name').textContent==='Alpha'&&!__indicator().title.includes('/voorbeelden/')&&__statusOnlyAccessible()&&__centeredBetweenControls()&&__layout().okay")

        # Explicit project clicks open the project panel, including repeated clicks.
        await c.evaluate("window.__emit('chrome-panel','closed');window.__calls=[];window.__emit('project-panel-open',{project_id:"+json.dumps(A['id'])+"});true")
        await check('matching_project_click_opens_the_project_panel', "window.__calls.length===1&&window.__calls[0].name==='chrome_panel'&&window.__calls[0].args.mode==='files'&&__indicator().getAttribute('aria-expanded')==='true'")
        await c.evaluate("window.__emit('chrome-panel','closed');window.__calls=[];window.__emit('project-panel-open',{project_id:"+json.dumps(A['id'])+"});true")
        await check('same_project_click_reopens_a_user_closed_panel', "window.__calls.length===1&&window.__calls[0].name==='chrome_panel'&&window.__calls[0].args.mode==='files'&&__indicator().getAttribute('aria-expanded')==='true'")
        await emit(state(enabled=False), automatic('registering'))
        await c.evaluate('window.__calls=[];true')
        await emit(state(), automatic())
        await check('connection_success_keeps_the_project_panel_open', "__indicator().getAttribute('aria-expanded')==='true'&&!window.__calls.some(x=>x.name==='chrome_panel'&&x.args.mode==='closed')")
        await c.evaluate('window.__calls=[];true')
        await emit(state(), automatic())
        await emit(state(), automatic())
        await check('connected_replays_do_not_close_or_reopen_the_panel', "__indicator().getAttribute('aria-expanded')==='true'&&!window.__calls.some(x=>x.name==='chrome_panel')")
        await c.evaluate("window.__emit('chrome-panel','closed');window.__calls=[];true")
        await emit(state(), automatic())
        await c.evaluate("window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:1,pending:false});true")
        await check('user_closed_panel_stays_closed_through_status_and_language_replays', "__indicator().getAttribute('aria-expanded')==='false'&&!window.__calls.some(x=>x.name==='chrome_panel')")
        await c.evaluate("window.__emit('project-panel-open',{project_id:"+json.dumps(A['id'])+"});window.__staleProjectClick=Date.now()-100;window.__emit('chrome-panel','closed');window.__calls=[];window.__emit('project-panel-open',{project_id:"+json.dumps(A['id'])+",clicked_at:window.__staleProjectClick});window.__staleClickStayedClosed=__indicator().getAttribute('aria-expanded')==='false'&&!window.__calls.some(x=>x.name==='chrome_panel');window.__emit('project-panel-open',{project_id:"+json.dumps(A['id'])+",clicked_at:Date.now()+100});true")
        await check('user_dismissal_rejects_a_delayed_project_click_but_allows_a_fresh_click', "window.__staleClickStayedClosed&&__indicator().getAttribute('aria-expanded')==='true'&&window.__calls.filter(x=>x.name==='chrome_panel'&&x.args.mode==='files').length===1")
        await c.evaluate("document.getElementById('settings').click();window.__calls=[];true")
        await emit(state(enabled=False), automatic('registering'))
        await emit(state(), automatic())
        await c.evaluate("window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:1,pending:false});true")
        await check('connection_and_language_replays_leave_settings_open', "document.getElementById('settings').getAttribute('aria-expanded')==='true'&&__indicator().getAttribute('aria-expanded')==='false'&&!window.__calls.some(x=>x.name==='chrome_panel')")
        await c.evaluate("document.getElementById('settings').click();window.__calls=[];window.__emit('project-panel-open',{project_id:"+json.dumps(B['id'])+"});true")
        await emit(state(), automatic())
        await check('nonmatching_project_click_waits_for_its_own_snapshot', "__indicator().getAttribute('aria-expanded')==='false'&&!window.__calls.some(x=>x.name==='chrome_panel')")
        await emit(state(project=B, folder='/voorbeelden/Beta'), automatic(project=B))
        await check('queued_project_click_opens_after_the_matching_snapshot', "__indicator().getAttribute('aria-expanded')==='true'&&window.__calls.filter(x=>x.name==='chrome_panel'&&x.args.mode==='files').length===1&&document.getElementById('connection-project-name').textContent==='Proefproject Beta'")
        await c.evaluate("window.__emit('chrome-panel','closed');window.__calls=[];true")
        await emit(state(project=B, folder='/voorbeelden/Beta'), automatic(project=B))
        await check('consumed_project_click_does_not_reopen_after_user_close', "__indicator().getAttribute('aria-expanded')==='false'&&!window.__calls.some(x=>x.name==='chrome_panel')")
        await emit(state(), automatic())
        await c.evaluate("window.__emit('chrome-panel','closed');document.getElementById('home').focus();true")
        for event in ['keyDown', 'keyUp']:
            await c.call('Input.dispatchKeyEvent', {'type': event, 'key': 'Tab',
                'code': 'Tab', 'windowsVirtualKeyCode': 9, 'nativeVirtualKeyCode': 9})
        await check('keyboard_focus_is_visible', "document.activeElement===__indicator()&&__indicator().matches(':focus-visible')&&getComputedStyle(__indicator()).outlineStyle==='solid'&&parseFloat(getComputedStyle(__indicator()).outlineWidth)>=2")
        await c.evaluate("document.activeElement.blur();window.__emit('language-state',{language:'en',resolved:'en',site_locale:'en',revision:2,pending:false});true")
        await check('english_localizes_accessible_status_without_visible_status_or_status_tooltip', "document.getElementById('connection-label').textContent==='Connected'&&__indicator().getAttribute('aria-label').includes('Connected')&&__indicator().getAttribute('aria-label').includes('Open local files')&&__statusOnlyAccessible()&&__namesOnlyTitle()&&document.getElementById('language-code').textContent==='EN'")
        await c.evaluate("window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:3,pending:false});true")
        # All advertised languages must update live labels and accessible text.
        await c.evaluate("window.__localeFailures=[];(()=>{let revision=10;for(const option of window.VIBEZ_TRANSLATIONS.options.filter(o=>o.code!=='system')){window.__emit('language-state',{language:option.code,resolved:option.code,site_locale:'en',revision:revision++,pending:false});const expected=window.VIBEZ_TRANSLATIONS.new[option.code];if(document.getElementById('connection-label').textContent!==expected.connectionConnected||!__indicator().getAttribute('aria-label').includes(expected.connectionConnected)||!__indicator().getAttribute('aria-label').includes(expected.connectionOpenFiles)||!__statusOnlyAccessible()||!__namesOnlyTitle()||document.querySelector('.nav-controls').getAttribute('aria-label')!==expected.navigation||document.getElementById('language-code').textContent!==option.code.toUpperCase()||document.getElementById('local-files')||!__layout().okay)window.__localeFailures.push(option.code);}window.__emit('language-state',{language:'de',resolved:'de',site_locale:'de',revision:100,pending:false});})();true")
        report['locale_failures'] = await c.evaluate('window.__localeFailures')
        await check('all_33_languages_keep_only_names_visible_and_localize_accessible_status_navigation_and_badge', 'window.__localeFailures.length===0')
        await screenshot('connected-de-1280.png')
        await c.evaluate("window.__emit('language-state',{language:'ar',resolved:'ar',site_locale:'ar',revision:101,pending:false});true")
        await check('arabic_accessible_status_and_direction_follow_selected_language', "document.documentElement.dir==='rtl'&&document.getElementById('connection-label').textContent==='متصل'&&__statusOnlyAccessible()&&__namesOnlyTitle()")
        await screenshot('connected-ar-1280.png')
        await c.evaluate("window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:102,pending:false});true")
        await c.call('Emulation.setEmulatedMedia', {'features': [
            {'name': 'prefers-reduced-motion', 'value': 'reduce'}]})
        await check('reduced_motion_disables_connected_animation', "__indicator().dataset.state==='connected'&&__motion()==='none'&&getComputedStyle(__indicator()).transitionDuration==='0s'")
        await c.call('Emulation.setEmulatedMedia', {'features': [
            {'name': 'prefers-reduced-motion', 'value': 'no-preference'}]})

        # The existing controls remain separate and fit all supported widths.
        report['layouts'] = {}
        for width in [1280, 1100, 980, 960]:
            await viewport(width)
            await emit(state(), automatic())
            layout = await c.evaluate('__layout()')
            report['layouts'][str(width)] = layout
            await check('width_'+str(width)+'_has_no_overflow_or_overlap', '__layout().okay')
            await check('width_'+str(width)+'_keeps_inline_names_fixed_icons_and_flexible_connection', '__statusOnlyAccessible()&&__namesOnlyTitle()&&__fixedIcons()&&__inlineNames()&&__captionGeometry().visual.width>=120&&__captionGeometry().visual.width<=255')
            await check('width_'+str(width)+'_indicator_is_centered_between_home_and_language', '__centeredBetweenControls()')
            if width == 960:
                await screenshot('connected-960.png', width=960)
            pending = [{'id': 'invented-proposal', 'project_name': A['name'], 'path': 'controle.txt'}]
            await emit(state(pending=pending), automatic())
            report['layouts'][str(width)+'_review'] = await c.evaluate('__layout()')
            await check('width_'+str(width)+'_review_status_fits', "__layout().okay&&document.getElementById('status').textContent.length>0&&__indicator().dataset.state==='connected'")
            await check('width_'+str(width)+'_review_keeps_indicator_centered_between_home_and_language', "__centeredBetweenControls()&&document.getElementById('status').getBoundingClientRect().right<=__indicator().getBoundingClientRect().left+.5&&__motion()==='connection-flow'")
        await viewport(2560)
        await emit(state(), automatic())
        await screenshot('connected-2560.png', width=2560)
        # Conversation namespaces and stable draft aliases drive the same toolbar.
        await viewport(1280)
        await emit(state(),automatic())
        await emit(state(project=CONVERSATION,folder='/voorbeelden/Gespreksmap'))
        await check('conversation_namespace_cannot_inherit_the_old_project_connection', "__indicator().dataset.state!=='connected'&&__motion()==='none'&&document.getElementById('connection-project-name').textContent==='Reisideeën'&&!__indicator().title.includes('Proefproject Alpha')")
        await emit(state(project=DRAFT_CONVERSATION,folder='/voorbeelden/Gespreksmap'),automatic(project=DRAFT_CONVERSATION))
        await check('draft_conversation_displays_a_localized_name_and_its_own_folder', "document.getElementById('connection-project-name').textContent===window.vibezLanguage.t('newConversation')&&document.getElementById('connection-folder-name').textContent==='Gespreksmap'&&__indicator().dataset.state==='connected'&&!__indicator().title.includes('chat-')")
        await emit(state(project=CONVERSATION,folder='/voorbeelden/Gespreksmap'))
        await check('same_alias_first_message_updates_the_name_without_resetting_verified_connection', "document.getElementById('connection-project-name').textContent==='Reisideeën'&&document.getElementById('connection-folder-name').textContent==='Gespreksmap'&&__indicator().dataset.state==='connected'&&__motion()==='connection-flow'")
        await screenshot('conversation-connected-1280.png')
        await emit(state(project=DRAFT_CONVERSATION,folder=None,enabled=False,tunnel='stopped'),automatic('idle',project=DRAFT_CONVERSATION))
        await c.evaluate("window.__draftLocaleFailures=[];(()=>{let revision=200;for(const option of window.VIBEZ_TRANSLATIONS.options.filter(o=>o.code!=='system')){window.__emit('language-state',{language:option.code,resolved:option.code,site_locale:'en',revision:revision++,pending:false});const expected=window.VIBEZ_TRANSLATIONS.new[option.code];if(document.getElementById('connection-project-name').textContent!==expected.newConversation||__indicator().title!==expected.newConversation||document.getElementById('local-files')||!__statusOnlyAccessible()||!__layout().okay)window.__draftLocaleFailures.push(option.code);}window.__emit('language-state',{language:'nl',resolved:'nl',site_locale:'nl',revision:300,pending:false});})();true")
        report['draft_locale_failures']=await c.evaluate('window.__draftLocaleFailures')
        await check('draft_conversation_names_update_in_all_33_languages', 'window.__draftLocaleFailures.length===0')
        await screenshot('new-conversation-1280.png')
        await check('existing_idle_action_color_and_height_preserved', "['screenshot','settings','language-button'].every(id=>{const n=document.getElementById(id),s=getComputedStyle(n);return s.backgroundColor==='rgb(49, 95, 128)'&&n.getBoundingClientRect().height===34;})")
        await c.evaluate("window.__emit('app-engine',{type:'error',code:'engine_stopped',message:'Voorbeeld: open VibeZ opnieuw.'});true")
        await check('fatal_engine_shutdown_stops_connection_motion', "__indicator().dataset.state==='error'&&__motion()==='none'&&document.getElementById('status').textContent===window.vibezLanguage.t('engineStopped')&&document.getElementById('status').title===window.vibezLanguage.t('engineStopped')")
        report['javascript_errors'] = await c.evaluate('window.__errors')
        report['runtime_exceptions'] = c.exceptions
        if report['javascript_errors'] or c.exceptions:
            raise AssertionError('Unexpected toolbar JavaScript errors')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=BASE/'artifacts/toolbar-ui-test58')
    args = parser.parse_args()
    out = args.output.resolve();out.mkdir(parents=True, exist_ok=True)
    report = {'version': VERSION, 'passed': False, 'headless': True,
              'visible_windows': False, 'isolated_profile': True,
              'fixture_only': True, 'live_mistral': False, 'checks': {}}
    process = None
    tempdir = None
    try:
        tempdir = tempfile.TemporaryDirectory(prefix='vibez-toolbar-headless-')
        temp = Path(tempdir.name);dist = BASE/'desktop/dist'
        shim = SHIM.replace('__WEB__', json.dumps(state())).replace('__AUTO__', json.dumps(automatic())).replace('__VERSION__', json.dumps(VERSION))
        html = (dist/'index.html').read_text().replace('<head>', '<head><base href="'+dist.as_uri()+'/"><script>'+shim+'</script>', 1)
        page = temp/'toolbar-fixture.html';page.write_text(html)
        profile = temp/'profile'
        with (out/'chromium.log').open('w') as log:
            process = subprocess.Popen(['/usr/bin/chromium', '--headless=new', '--no-sandbox',
                '--disable-gpu', '--disable-background-networking', '--disable-component-update',
                '--disable-sync', '--no-first-run', '--no-default-browser-check',
                '--allow-file-access-from-files', '--force-device-scale-factor=1',
                '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
                '--user-data-dir='+str(profile), 'about:blank'],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            port_file = profile/'DevToolsActivePort';deadline = time.monotonic()+12
            while not port_file.exists() and process.poll() is None and time.monotonic()<deadline:
                time.sleep(.1)
            if not port_file.exists():
                raise RuntimeError('Headless Chromium did not expose its isolated debugging endpoint')
            port = int(port_file.read_text().splitlines()[0])
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open('http://127.0.0.1:'+str(port)+'/json/list', timeout=5) as response:
                pages = json.load(response)
            ws_url = next(p['webSocketDebuggerUrl'] for p in pages if p['type']=='page')
            asyncio.run(exercise(ws_url, page.as_uri(), out, report))
            report['passed'] = True
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        if tempdir is not None:tempdir.cleanup()
        (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
