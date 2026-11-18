'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const rows=require('../v4-notice-i18n.json'),base=require('../../i18n.js').TRANSLATIONS;
const flush=()=>new Promise(r=>setImmediate(r));
function ui(fail=false,agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)'){
 const elts=new Map(),calls=[];
 const el=id=>{if(!elts.has(id))elts.set(id,{hidden:false,textContent:'',listeners:{},addEventListener(n,f){this.listeners[n]=f;}});return elts.get(id);};
 const preview={localize(){},extra:k=>k,errorText:e=>String(e?.message||e),invoke:async(c,a)=>{calls.push([c,a]);if(fail&&c==='v4_notice_action')throw new Error('Could not open');return {settings:{language:'en'},os_locale:'en'};}};
 const document={getElementById:el,addEventListener(){},title:''};
 vm.runInNewContext(read('frontend/v4notice.js'),{document,preview,navigator:{userAgent:agent}});
 return {el,calls,document};
}
test('the farewell notice is translated in all 34 interface languages',()=>{
 assert.deepEqual(Object.keys(rows).sort(),Object.keys(base).sort());
 for(const [code,values] of Object.entries(rows)){
  assert.equal(values.length,9,code);assert.ok(values.every(v=>typeof v==='string'&&v.trim()),code);
  assert.ok(values[0].includes('Mistral Vibe')&&values[3].includes('Vibe Desktop'),code);
  assert.ok(values[1].includes('Vibe Desktop')&&values[1].includes('VibeZ'),code);
  assert.ok(values[2].includes('Windows')&&values[2].includes('Mac'),code);
  assert.ok(values[8].includes('Linux')&&!values[8].includes('Windows'),code);
  assert.ok(!values.join(' ').includes('V4 Beta'),code);
 }
});
test('notice buttons send only fixed link names, never URLs',async()=>{
 const u=ui();await flush();
 for(const id of ['official','discussions','issue','repo','close']){u.el(id).listeners.click();await flush();}
 await flush();
 const sent=u.calls.filter(c=>c[0]==='v4_notice_action').map(c=>c[1].action);
 assert.deepEqual(sent.sort(),['close','discussions','issue','official','repo']);
 assert.doesNotMatch(read('frontend/v4notice.js'),/https?:|window\.open|location/);
 assert.equal(u.document.title,'v4NoticeTitle');
});
test('Windows and macOS read that updates end; Linux reads that it stays supported',async()=>{
 for(const agent of ['Mozilla/5.0 (Windows NT 10.0; Win64; x64)','Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)']){
  const u=ui(false,agent);assert.equal(u.el('stable').hidden,false,agent);assert.equal(u.el('linux').hidden,true,agent);
 }
 const linux=ui(false,'Mozilla/5.0 (X11; Linux x86_64)');assert.equal(linux.el('stable').hidden,true);assert.equal(linux.el('linux').hidden,false);
 const html=read('frontend/v4notice.html');
 assert.match(html,/id="official" class="primary"/);assert.match(html,/data-extra="v4NoticeLinux"/);
});
test('a failed link stays visible as an error',async()=>{
 const u=ui(true);await flush();u.el('repo').listeners.click();await flush();
 assert.equal(u.el('error').hidden,false);assert.match(u.el('error').textContent,/Could not open/);
});
test('only the local notice window may call the link command',()=>{
 const cap=JSON.parse(read('src-tauri/capabilities/local-v4notice.json'));
 assert.deepEqual(cap.webviews,['v4notice']);assert.equal(cap.local,true);assert.equal(cap.remote,undefined);
 assert.deepEqual(cap.permissions.sort(),['allow-get-state','allow-v4-notice-action']);
 assert.ok(read('src-tauri/build.rs').includes('"v4_notice_action"'));
 assert.ok(JSON.parse(read('src-tauri/tauri.conf.json')).app.security.capabilities.includes('local-v4notice'));
 const rust=read('src-tauri/src/v4_notice.rs');
 assert.match(rust,/\("official","https:\/\/mistral\.ai\/products\/vibe\/"\)/);
 assert.match(rust,/const MARKER:&str="farewell-notice-shown";/);
 assert.doesNotMatch(rust,/v4\.0\.0-beta/);
 assert.match(rust,/if path\.exists\(\)\{return;\}/);
 assert.match(read('src-tauri/src/main.rs'),/!smoke && !start_hidden \{ v4_notice::schedule/);
});
