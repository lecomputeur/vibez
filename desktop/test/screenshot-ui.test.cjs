'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const base=path.join(__dirname,'..'),read=p=>fs.readFileSync(path.join(base,p),'utf8');
const flush=()=>new Promise(r=>setImmediate(r));
function ui(result){
 const elements=new Map(),calls=[],modes=['visible','full','selection'].map(mode=>({dataset:{mode}}));
 function el(id){if(!elements.has(id))elements.set(id,{id,disabled:false,hidden:false,dataset:{},textContent:'',listeners:{},focus(){},setAttribute(){},removeAttribute(name){delete this[name];},addEventListener(n,f){this.listeners[n]=f;}});return elements.get(id);}
 for(const m of modes)Object.assign(m,el(m.dataset.mode),{dataset:m.dataset});
 const buttons=[...modes,...['close','copy','save','again','done'].map(el)];
 const doc={getElementById:el,querySelectorAll:q=>q==='button'?buttons:q==='[data-mode]'?modes:[],querySelector:()=>modes[0],addEventListener(){}};
 const preview={localize(){},currentLanguage:()=> 'nl',errorText:e=>e.message||String(e),invoke:async(c,a)=>{calls.push([c,a]);if(c==='get_state')return{platform:'linux'};if(c==='capture_screenshot'){if(result instanceof Error)throw result;return result;}return{copied:true};}};
 vm.runInNewContext(read('frontend/screenshot.js'),{document:doc,preview});return {el,modes,buttons,calls};
}
test('all three cards capture their named mode and show the real PNG',async()=>{
 for(const mode of ['visible','full','selection']){
 const u=ui({dataUrl:'data:image/png;base64,AAAA',width:120,height:100,copied:true});await flush();u.modes.find(m=>m.dataset.mode===mode).listeners.click();await flush();
 assert.deepEqual(u.calls.filter(c=>c[0]==='capture_screenshot').map(c=>c[1].mode),[mode]);assert.equal(u.el('result').hidden,false);assert.match(u.el('feedback-text').textContent,/Gekopieerd/);assert.equal(u.el('image').src,'data:image/png;base64,AAAA');assert.ok(u.buttons.every(b=>!b.disabled));}
});
test('cancel and errors return to choices without stale image or false success',async()=>{
 for(const result of [{cancelled:true},new Error('native capture unavailable')]){
 const u=ui(result);await flush();u.modes[0].listeners.click();await flush();assert.equal(u.el('result').hidden,true);assert.equal(u.el('choose').hidden,false);assert.equal(u.el('image').src,undefined);assert.ok(u.buttons.every(b=>!b.disabled));assert.doesNotMatch(u.el('feedback-text').textContent,/Gekopieerd/);}
});
test('clipboard failure preserves PNG preview and does not claim copied',async()=>{
 const u=ui({dataUrl:'data:image/png;base64,AAAA',width:120,height:100,copied:false});await flush();u.modes[0].listeners.click();await flush();assert.equal(u.el('result').hidden,false);assert.match(u.el('feedback-text').textContent,/kopiëren is mislukt/);
});
test('screenshot privileges are restricted to the local dialog',()=>{
 const cap=JSON.parse(read('src-tauri/capabilities/local-screenshot.json'));assert.deepEqual(cap.webviews,['screenshot']);assert.equal(cap.local,true);assert.equal(cap.remote,undefined);assert.ok(!cap.permissions.some(p=>/shell:|fs:|opener:/.test(p)));
 assert.doesNotMatch(read('src-tauri/src/capture_page.js'),/__TAURI__|invoke\(/);
 assert.match(read('src-tauri/src/screenshot_native_linux.rs'),/\.snapshot\(/);
});
