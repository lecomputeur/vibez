'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),read=p=>fs.readFileSync(path.join(root,p),'utf8');
test('Alpha staging payload keeps its independent identity and has no installation hooks',()=>{const d=JSON.parse(read('src-tauri/tauri.conf.json'));assert.equal(d.identifier,'nl.lecomputeur.vibez4.alpha');assert.equal(d.version,JSON.parse(read('package.json')).version);assert.match(d.version,/^4\.\d+\.\d+-(alpha|beta)\.[1-9]\d*$/);assert.deepEqual(d.bundle.targets,['deb']);assert.equal(d.bundle.linux.deb.preInstallScript,undefined);assert.equal(d.bundle.linux.deb.postInstallScript,undefined);});
test('only bundled toolbar and connector panel receive native permissions',()=>{const c=JSON.parse(read('src-tauri/capabilities/standalone.json'));assert.deepEqual(c.webviews,['main','connector-panel']);assert.equal(c.remote,undefined);assert.equal(c.local,true);assert.ok(!c.permissions.includes('core:default'));const s=read('src-tauri/src/standalone.rs');assert.match(s,/view.label\(\)=="connector-panel"/);assert.match(s,/u.path\(\)=="\/panel.html"/);});
test('portable startup and native dialogs preserve explicit safe-output mode',()=>{const s=read('src-tauri/src/standalone.rs');assert.match(s,/VIBEZ_SAFE_OUTPUT/);assert.doesNotMatch(s,/const SAFE_OUTPUT|monitors.len\(\) < 2/);assert.match(s,/app.primary_monitor\(\)/);assert.match(s,/guard_game\(selected\)/);assert.match(s,/position_dialog\(&handle,&dialog,s\)/);assert.match(s,/FileChooserNative::new/);assert.match(s,/created_child\(&parent,&path\)/);});
test('shipped UI has one familiar toolbar and no mode chooser or project address bar',()=>{const html=read('../standalone-ui/index.html');for(const id of ['back','forward','reload','home','settings'])assert.match(html,new RegExp('id="'+id+'"'));assert.doesNotMatch(html,/Webgesprekken|Webversie|Lokale gesprekken|project-url|<input|id="local-files"|class="folder-plus"/);assert.match(read('../standalone-ui/chrome.js'),/show:true/);});
test('file proposals are rendered as inert text, not model HTML',()=>{for(const name of ['chrome.js','panel.js','panel-tabs.js','connection-status.js']){const s=read('../standalone-ui/'+name);new vm.Script(s);assert.doesNotMatch(s,/innerHTML|new Function|eval\(/);}assert.match(read('../standalone-ui/panel.js'),/textContent/);assert.doesNotMatch(read('../standalone-ui/panel.html'),/id="project-goal/);});
test('automatic setup is the normal path and manual secrets stay under advanced',()=>{const html=read('../standalone-ui/panel.html');assert.match(html,/<details id="files-options"/);assert.ok(html.indexOf('id="advanced-setup"')>html.indexOf('id="files-options"'));assert.match(html,/<details id="advanced-setup" class="web-card"><summary/);assert.ok(html.indexOf('id="studio-api-key"')>html.indexOf('id="advanced-setup"'));assert.match(read('../standalone-ui/panel.js'),/webCommand\('web_connect'\)/);const config=JSON.parse(read('src-tauri/tauri.conf.json'));assert.equal(config.bundle.resources['../../backend/automatic_connector.py'],'backend/automatic_connector.py');});
test('the toolbar Screenshot button opens the V3 dialog with all its files and permissions',()=>{
  const chrome=fs.readFileSync(path.join(root,'../standalone-ui/chrome.js'),'utf8');
  assert.match(chrome,/invoke\('chrome_snapshot'\)/);assert.doesNotMatch(chrome,/screenshotCopied/);
  assert.match(read('src-tauri/src/official_web.rs'),/screenshot_dialog::open\(&app\)/);
  const prepare=read('scripts/prepare-standalone.cjs');
  for(const name of ['screenshot.html','screenshot.js','screenshot.css','common.js','screenshot-file-translations.js','screenshot-login-translations.js'])assert.ok(prepare.includes(`'${name}'`),name);
  assert.match(prepare,/preview-translations\.js/);
  assert.ok(JSON.parse(read('src-tauri/tauri.conf.json')).app.security.capabilities.includes('local-screenshot'));
  const capability=JSON.parse(read('src-tauri/capabilities/local-screenshot.json'));
  assert.deepEqual(capability.webviews,['screenshot']);
  assert.deepEqual(capability.permissions.sort(),['allow-capture-screenshot','allow-get-state','allow-screenshot-action']);
  const standalone=read('src-tauri/src/standalone.rs');
  for(const name of ['get_state','capture_screenshot','screenshot_action'])assert.match(standalone,new RegExp(`async fn ${name}\\(webview: Webview[^]*?screenshot_v4::require_dialog\\(&webview\\)`),name);
});
test('the screenshot memory paste keeps working when Mistral moves focus inside its editor',()=>{
  const source=read('src-tauri/src/paste_png_bridge.js');
  const run=(focusInside,focusLost)=>{let focused=0,dispatched=0;const child={};
    const editor={isConnected:true,disabled:false,readOnly:false,contains:n=>n===editor||n===child,focus(){focused++;root.activeElement=focusInside?child:editor;},dispatchEvent(){dispatched++;receipt.images=1;receipt.bridge=true;}};
    const root={activeElement:focusLost?{}:child};editor.getRootNode=()=>root;
    const receipt={received:true,trusted:true,images:0,editor};
    class DT{constructor(){this.files=[];this.items={add:f=>this.files.push(f)};}}
    const context={window:{__vibezPasteReceipt:receipt},atob:s=>s,Uint8Array,File:class{constructor(p){this.size=p[0].length;}},DataTransfer:DT,ClipboardEvent:class{},JSON,Object};
    const result=JSON.parse(vm.runInNewContext(source.replace('__VIBEZ_SCREENSHOT_PNG__','"abc"'),context));return {result,focused,dispatched};};
  const inside=run(true,false);assert.equal(inside.result.ok,true);assert.equal(inside.focused,0);
  const lost=run(true,true);assert.equal(lost.result.ok,true);assert.equal(lost.focused,1);
});
