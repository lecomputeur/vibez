'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const rows=require('../v4-notice-i18n.json'),base=require('../../i18n.js').TRANSLATIONS;
const flush=()=>new Promise(r=>setImmediate(r));
function ui(fail=false){
 const elts=new Map(),calls=[];
 const el=id=>{if(!elts.has(id))elts.set(id,{hidden:false,textContent:'',listeners:{},addEventListener(n,f){this.listeners[n]=f;}});return elts.get(id);};
 const preview={localize(){},extra:k=>k,errorText:e=>String(e?.message||e),invoke:async(c,a)=>{calls.push([c,a]);if(fail&&c==='v4_notice_action')throw new Error('Could not open');return {settings:{language:'en'},os_locale:'en'};}};
 const document={getElementById:el,addEventListener(){},title:''};
 vm.runInNewContext(read('frontend/v4notice.js'),{document,preview});
 return {el,calls,document};
}
test('V4 Beta notice is translated in all 34 interface languages (six locale groups)',()=>{
 assert.deepEqual(Object.keys(rows).sort(),Object.keys(base).sort());
 for(const [code,values] of Object.entries(rows)){
  assert.equal(values.length,8,code);assert.ok(values.every(v=>typeof v==='string'&&v.trim()),code);
  assert.ok(values[0].includes('VibeZ V4')&&values[3].includes('VibeZ V4'),code);
 }
});
test('notice buttons send only fixed link names, never URLs',async()=>{
 const u=ui();await flush();
 for(const id of ['v4beta','discussions','issue','repo','close']){u.el(id).listeners.click();await flush();}
 await flush();
 const sent=u.calls.filter(c=>c[0]==='v4_notice_action').map(c=>c[1].action);
 assert.deepEqual(sent.sort(),['close','discussions','issue','repo','v4beta']);
 assert.doesNotMatch(read('frontend/v4notice.js'),/https?:|window\.open|location/);
 assert.equal(u.document.title,'v4NoticeTitle');
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
 assert.match(rust,/releases\/tag\/v4\.0\.0-beta\.2/);
 assert.match(rust,/if path\.exists\(\)\{return;\}/);
 assert.match(read('src-tauri/src/main.rs'),/!smoke && !start_hidden \{ v4_notice::schedule/);
});
