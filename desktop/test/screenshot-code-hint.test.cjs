'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const hints=require('../screenshot-hints-i18n.json'),languages=require('../../i18n.js').TRANSLATIONS;
const flush=()=>new Promise(r=>setImmediate(r));
function dialog({code=true,language='nl',capture}={}){
 let state={screenshot_code_context:code,platform:'linux',settings:{language},os_locale:'nl'};
 const elements=new Map(),calls=[],timers=[];let current='en';
 function el(id){if(!elements.has(id))elements.set(id,{id,dataset:{},hidden:false,disabled:false,checked:true,textContent:'',listeners:{},focus(){},setAttribute(){},removeAttribute(name){delete this[name];},addEventListener(n,f){this.listeners[n]=f;}});return elements.get(id);}
 el('code-hint').hidden=true;el('result').hidden=true;
 const modes=['visible','full','selection'].map(mode=>{const e=el(mode);e.dataset.mode=mode;return e;});
 const buttons=[...modes,...['paste','copy','save','again','close','auto-paste'].map(el)];
 const document={getElementById:el,querySelector:()=>modes[0],querySelectorAll:q=>q==='[data-mode]'?modes:q==='button,input'?buttons:[],addEventListener(){}};
 const preview={resolve:s=>s,currentLanguage:()=>current,localize(s){current=s.settings.language;return languages[current];},extra:k=>k==='screenshotCodeHint'?hints[current]:k,errorText:e=>String(e),invoke:async(c,a)=>{
  calls.push([c,a]);if(c==='get_state')return state;
  if(c==='capture_screenshot')return capture||{copied:true,dataUrl:'data:image/png;base64,AAAA',width:100,height:120};
  return {copied:true};
 }};
 vm.runInNewContext(read('frontend/screenshot.js'),{document,preview,window:{addEventListener(){}},setInterval:f=>timers.push(f),clearInterval(){}});
 return {el,calls,modes,timers,buttons,update:patch=>{state={...state,...patch};}};
}
test('Code notice is visible immediately, before capture or a manual paste',async()=>{
 const u=dialog();await flush();assert.equal(u.el('code-hint').hidden,false);assert.equal(u.el('code-hint').textContent,hints.nl);
 assert.ok(u.calls.every(([c])=>c==='get_state'));assert.ok(u.buttons.every(b=>!b.disabled));
 assert.equal(u.el('auto-paste').checked,true);assert.equal(u.el('result').hidden,true);
});
test('notice is not shown in normal Chat/Work and does not claim a failed attachment before an attempt',async()=>{
 const u=dialog({code:false});await flush();assert.equal(u.el('code-hint').hidden,true);
 assert.doesNotMatch(hints.nl,/niet bevestigd|log in|ondersteunt geen/i);
});
test('capture from Code still requests auto-paste unchanged; copy-only still respects the checkbox',async()=>{
 for(const auto of [true,false]){const u=dialog();await flush();u.el('auto-paste').checked=auto;await u.modes[0].listeners.click();
  assert.equal(u.calls.find(([c])=>c==='capture_screenshot')[1].paste,auto);assert.equal(u.el('code-hint').hidden,false);assert.equal(u.el('result').hidden,false);
 }
});
test('a successful Code paste still closes normally; notice never blocks paste',async()=>{
 const u=dialog({capture:{pasted:true}});await flush();await u.modes[0].listeners.click();
 assert.ok(u.calls.some(([c,a])=>c==='screenshot_action'&&a.action==='close'));
});
test('real failure feedback and the screenshot survive beside the early notice',async()=>{
 const u=dialog({capture:{copied:true,dataUrl:'data:image/png;base64,AAAA',width:100,height:120,pasteError:'Bijlage niet bevestigd'}});
 await flush();await u.modes[0].listeners.click();
 assert.equal(u.el('feedback').textContent,'Bijlage niet bevestigd');assert.equal(u.el('feedback').dataset.kind,'error');
 assert.equal(u.el('code-hint').textContent,hints.nl);assert.equal(u.el('code-hint').hidden,false);assert.equal(u.el('image').src,'data:image/png;base64,AAAA');
});
test('language and page changes update the advisory without resetting PNG, paste checkbox or feedback',async()=>{
 const u=dialog();await flush();u.el('auto-paste').checked=false;u.el('image').src='existing-png';u.el('feedback').textContent='existing-feedback';
 u.update({settings:{language:'de'}});await u.timers[0]();assert.equal(u.el('code-hint').textContent,hints.de);
 u.update({screenshot_code_context:false});await u.timers[0]();assert.equal(u.el('code-hint').hidden,true);
 assert.equal(u.el('auto-paste').checked,false);assert.equal(u.el('image').src,'existing-png');assert.equal(u.el('feedback').textContent,'existing-feedback');
});
test('all 34 hint languages render, with no key or English fallback',async()=>{
 assert.deepEqual(Object.keys(hints).sort(),Object.keys(languages).sort());
 for(const language of Object.keys(languages)){assert.ok(hints[language]?.trim(),language);const u=dialog({language});await flush();assert.equal(u.el('code-hint').textContent,hints[language]);}
});
test('advisory data is read-only and does not add a native permission or page-wide paste guard',()=>{
 assert.match(read('src-tauri/src/main.rs'),/webview\.label\(\) == "screenshot" && screenshot_dialog::code_context/);
 const source=read('src-tauri/src/paste_composer.js');assert.doesNotMatch(source,/return fail\('code-editor'\)/);
 assert.match(read('frontend/screenshot.html'),/id="code-hint" role="status" aria-live="polite" hidden/);
});
