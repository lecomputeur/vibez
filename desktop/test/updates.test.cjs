'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const labels=require('../updates-i18n.json'),base=require('../../i18n.js').TRANSLATIONS;
const keys=['updateAvailable','updateDownload','updateDownloading','updateOpenFile','updateShowFile','updateConfirmInstall','updateStoreManaged','pasteConfirmed','pasteUnconfirmed'];
const flush=()=>new Promise(r=>setImmediate(r));
function ui(phase,lang='nl',failAction=false){
 let state={phase,current:'3.0.3',release:{version:'3.0.4',assets:[{name:'VibeZ-3.0.4-Windows-x64-Setup.exe',kind:'EXE',size:1000}]},total:1000,received:400,busy:false,error:''};
 if(phase==='ready')state.fileName=state.release.assets[0].name;
 const elts=new Map(),calls=[],timers=[];
 function el(id){if(!elts.has(id))elts.set(id,{dataset:{},hidden:false,disabled:false,textContent:'',value:'',children:[],listeners:{},replaceChildren(){this.children=[];},append(e){this.children.push(e);if(!this.value)this.value=e.value;},addEventListener(n,f){this.listeners[n]=f;}});return elts.get(id);}
 const strings=Object.fromEntries(keys.map((k,i)=>[k,labels[lang][i]]));
 const preview={localize:()=>base[lang],extra:k=>strings[k]||k,errorText:e=>String(e),invoke:async(c,a)=>{calls.push([c,a]);if(c==='update_action'&&failAction)throw new Error('Native opening failed');return c==='get_state'?{settings:{language:lang},os_locale:lang}:state;}};
 vm.runInNewContext(read('frontend/updates.js'),{document:{getElementById:el,createElement:()=>({}),addEventListener(){}},preview,window:{addEventListener(){}},setInterval:f=>timers.push(f),clearInterval(){}});
 return {el,calls,timers,set:s=>{state={...state,...s};}};
}
test('update and attachment status labels cover all 34 interface languages',()=>{
 assert.deepEqual(Object.keys(labels).sort(),Object.keys(base).sort());
 for(const [code,text]of Object.entries(labels)){assert.equal(text.length,keys.length,code);assert.ok(text.every(t=>typeof t==='string'&&t.trim()),code);}
});
test('the new update commands are generated and only local controls have access',()=>{
 const manifest=read('src-tauri/build.rs');for(const name of ['check_for_updates','update_state','update_action'])assert.ok(manifest.includes('"'+name+'"'),name);
 assert.ok(JSON.parse(read('src-tauri/capabilities/local-shell.json')).permissions.includes('allow-check-for-updates'));
 const cap=JSON.parse(read('src-tauri/capabilities/local-updates.json'));assert.deepEqual(cap.webviews,['updates']);assert.equal(cap.local,true);assert.equal(cap.remote,undefined);assert.ok(!cap.permissions.some(p=>/shell:|fs:|http:/.test(p)));
 assert.match(read('src-tauri/src/release_updates.rs'),/verify_file\(&p,&checked\)/);
});
test('update availability shows a clear download action without auto installation',async()=>{
 const u=ui('available');await flush();assert.equal(u.el('download').hidden,false);assert.equal(u.el('open').hidden,true);assert.match(u.el('status').textContent,/nieuwe versie/);
 u.el('download').listeners.click();await flush();assert.equal(u.calls.find(c=>c[0]==='update_action')[1].action,'download');assert.ok(!u.calls.some(c=>c[1]?.action==='open'));
});
test('progress and cancellation never report an incomplete file as installable',async()=>{
 const u=ui('downloading');await flush();assert.equal(u.el('progress').value,40);assert.equal(u.el('open').hidden,true);assert.equal(u.el('cancel').hidden,false);
 u.el('cancel').listeners.click();await flush();assert.ok(u.calls.some(c=>c[1]?.action==='cancel'));
});
test('ready state offers separate explicit open and show-file actions',async()=>{
 const u=ui('ready');await flush();assert.equal(u.el('open').hidden,false);assert.equal(u.el('reveal').hidden,false);assert.ok(!u.calls.some(c=>c[1]?.action==='open'));
 u.el('open').listeners.click();await flush();assert.ok(u.calls.some(c=>c[1]?.action==='open'));
});
test('verified updates explain automatic shutdown and Show file only reveals the download',async()=>{
 assert.match(labels.en[5],/closes automatically/);
 assert.match(labels.nl[5],/sluit automatisch af/);
 const u=ui('ready');await flush();
 u.el('reveal').listeners.click();await flush();
 assert.ok(u.calls.some(c=>c[1]?.action==='reveal'));
 assert.ok(!u.calls.some(c=>c[1]?.action==='open'));
});
test('Store updates do not show a GitHub download button',async()=>{
 const u=ui('store');await flush();assert.equal(u.el('download').hidden,true);assert.equal(u.el('store').hidden,false);assert.match(u.el('status').textContent,/Microsoft Store/);
});
test('a checksum/network error stays visible and offers retry, not Open',async()=>{
 const u=ui('error');u.set({error:'Checksum mismatch'});await flush();assert.equal(u.el('error').hidden,false);assert.match(u.el('error').textContent,/Checksum/);assert.equal(u.el('open').hidden,true);
});
test('a received paste event alone is not an attachment confirmation',()=>{
 const source=read('src-tauri/src/screenshot_paste.rs');assert.doesNotMatch(source,/return Ok\("native"\)|return Ok\("memory"\)/);
 assert.match(source,/receipt\["attached"\]==true/);assert.match(source,/confirmed\(&view/);
 const js=read('src-tauri/src/paste_file_input.js');new vm.Script(js);assert.doesNotMatch(js,/\.submit\(|requestSubmit|fetch\(|\.click\(|__TAURI__|invoke\(/);
 const observer=read('src-tauri/src/paste_composer.js');assert.match(observer,/initial\.get\(el\)===signature\(el\)/);assert.match(observer,/site-alert/);
});
test('metadata check failure offers Check again without stale download choices',async()=>{
 const u=ui('available');await flush();
 u.set({phase:'checking',release:null,received:0,total:0});await u.timers[0]();
 assert.equal(u.el('download').hidden,true);
 u.set({phase:'error',error:'Metadata request failed'});await u.timers[0]();
 assert.equal(u.el('retry').hidden,false);assert.equal(u.el('download').hidden,true);
 assert.equal(u.el('package').hidden,true);assert.match(u.el('error').textContent,/Metadata/);
 u.el('retry').listeners.click();await flush();assert.ok(u.calls.some(c=>c[1]?.action==='check'));
});

test('native action failure stays visible after status refresh',async()=>{
 const u=ui('ready','nl',true);await flush();u.el('open').listeners.click();await flush();
 assert.match(u.el('error').textContent,/Native opening failed/);assert.equal(u.el('error').hidden,false);
 await u.timers[0]();assert.match(u.el('error').textContent,/Native opening failed/);
});
