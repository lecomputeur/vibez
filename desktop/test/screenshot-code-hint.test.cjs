'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const labels={window:{}};vm.runInNewContext(read('frontend/screenshot-file-translations.js'),labels);
const hints=require('../screenshot-hints-i18n.json'),files=labels.window.VIBEZ_SCREENSHOT_FILES,languages=require('../../i18n.js').TRANSLATIONS;
const flush=()=>new Promise(r=>setImmediate(r));
function dialog({mode='code',language='nl',capture,save={saved:true}}={}){
 let state={screenshot_mode:mode,platform:'linux',settings:{language},os_locale:'nl'};
 const elements=new Map(),calls=[],timers=[];let current='en',saveResult=save;
 function el(id){if(!elements.has(id))elements.set(id,{id,dataset:{},hidden:false,disabled:false,checked:id==='auto-paste',textContent:'',listeners:{},focus(){},setAttribute(){},removeAttribute(name){delete this[name];},addEventListener(n,f){this.listeners[n]=f;}});return elements.get(id);}
 el('result').hidden=true;
 const modes=['visible','full','selection'].map(mode=>{const e=el(mode);e.dataset.mode=mode;return e;});
 const buttons=[...modes,...['paste','copy','save','save-file','again','close','auto-paste','as-file'].map(el)];
 const document={getElementById:el,querySelector:()=>modes[0],querySelectorAll:q=>q==='[data-mode]'?modes:q==='button,input'?buttons:[],addEventListener(){}};
 const preview={resolve:s=>s,currentLanguage:()=>current,localize(s){current=s.settings.language;return languages[current];},extra:k=>({screenshotCodeHint:hints[current],screenshotAsFile:files[current][0],screenshotFileSaved:files[current][1]})[k]||k,errorText:e=>String(e),invoke:async(c,a)=>{
  calls.push([c,a]);if(c==='get_state')return state;
  if(c==='capture_screenshot')return capture||{copied:true,dataUrl:'data:image/png;base64,AAAA',width:100,height:120};
  if(a?.action==='save'){if(saveResult instanceof Error)throw saveResult;return saveResult;}
  return {copied:true};
 }};
 vm.runInNewContext(read('frontend/screenshot.js'),{document,preview,window:{VIBEZ_SCREENSHOT_FILES:files,addEventListener(){}},setInterval:f=>timers.push(f),clearInterval(){}});
 return {el,calls,modes,timers,buttons,setSave:s=>saveResult=s,update:patch=>{state={...state,...patch};}};
}
test('Code immediately offers checked Screenshot as file with concise Code versus Chat/Work explanation',async()=>{
 const u=dialog();await flush();assert.equal(u.el('file-option').hidden,false);assert.equal(u.el('code-hint').textContent,hints.nl);
 assert.match(hints.nl,/In Code:/);assert.match(hints.nl,/PNG/);assert.match(hints.nl,/In Chat en Work kun je direct plakken/);assert.doesNotMatch(hints.nl,/binaire data|app\.py|index\.js|kan mislukken/);
 assert.equal(u.el('as-file').checked,true);assert.equal(u.el('as-file').disabled,true);assert.equal(u.el('auto-choice').hidden,true);
 assert.ok(u.calls.every(([c])=>c==='get_state'));assert.equal(u.el('result').hidden,true);
});
for(const kind of ['visible','full','selection'])test(`${kind} in Code captures once, never pastes, then opens Save exactly once`,async()=>{
 const u=dialog();await flush();await u.modes.find(m=>m.dataset.mode===kind).listeners.click();
 const caps=u.calls.filter(([c])=>c==='capture_screenshot');assert.equal(caps.length,1);assert.equal(caps[0][1].paste,false);
 assert.equal(u.calls.filter(([,a])=>a?.action==='save').length,1);assert.ok(!u.calls.some(([,a])=>a?.action==='paste'));
 assert.equal(u.el('paste').hidden,true);assert.equal(u.el('save-file').hidden,false);assert.equal(u.el('feedback').textContent,files.nl[1]);
 await u.timers[0]();assert.equal(u.calls.filter(([,a])=>a?.action==='save').length,1,'polling reopened Save');
});
test('cancelled Save preserves the PNG and retries saving without recapture or paste',async()=>{
 const u=dialog({save:{cancelled:true}});await flush();await u.modes[0].listeners.click();
 assert.equal(u.el('image').src,'data:image/png;base64,AAAA');assert.equal(u.el('result').hidden,false);assert.notEqual(u.el('feedback').textContent,files.nl[1]);
 u.setSave({saved:true});await u.el('save-file').listeners.click();assert.equal(u.calls.filter(([c])=>c==='capture_screenshot').length,1);
 assert.equal(u.calls.filter(([,a])=>a?.action==='save').length,2);assert.equal(u.el('feedback').textContent,files.nl[1]);
});
test('Save error does not fake success, discard the PNG or switch to paste',async()=>{
 const u=dialog({save:new Error('Disk full')});await flush();await u.modes[0].listeners.click();
 assert.equal(u.el('result').hidden,false);assert.match(u.el('feedback').textContent,/Disk full/);assert.equal(u.el('feedback').dataset.kind,'error');assert.equal(u.el('paste').hidden,true);
 u.setSave({});await u.el('save-file').listeners.click();assert.equal(u.el('feedback').dataset.kind,'error');
});
test('cancelled selection never opens Save or pastes',async()=>{
 const u=dialog({capture:{cancelled:true}});await flush();await u.modes[2].listeners.click();assert.ok(!u.calls.some(([,a])=>['save','paste'].includes(a?.action)));assert.equal(u.el('result').hidden,true);
});
for(const mode of ['chat','work'])test(`${mode} keeps the accepted auto-paste and copy-only paths`,async()=>{
 for(const auto of [true,false]){const u=dialog({mode});await flush();assert.equal(u.el('file-option').hidden,true);assert.equal(u.el('auto-choice').hidden,false);
 u.el('auto-paste').checked=auto;await u.modes[0].listeners.click();assert.equal(u.calls.find(([c])=>c==='capture_screenshot')[1].paste,auto);assert.ok(!u.calls.some(([,a])=>a?.action==='save'));}
 const u=dialog({mode,capture:{pasted:true}});await flush();await u.modes[0].listeners.click();assert.ok(u.calls.some(([,a])=>a?.action==='close'));
});
test('unrecognized mode still offers the file option without breaking ordinary paste',async()=>{
 for(const mode of [undefined,null,'unknown']){const u=dialog({mode:mode||'unknown'});await flush();assert.equal(u.el('file-option').hidden,false);assert.equal(u.el('as-file').disabled,false);
 u.el('as-file').checked=true;u.el('as-file').listeners.change();await u.modes[1].listeners.click();assert.equal(u.calls.find(([c])=>c==='capture_screenshot')[1].paste,false);assert.ok(u.calls.some(([,a])=>a?.action==='save'));}
 const u=dialog({mode:'unknown'});await flush();await u.modes[0].listeners.click();assert.equal(u.calls.find(([c])=>c==='capture_screenshot')[1].paste,true);
});
test('mode changed to Code after opening is rechecked at capture, with no URL dependency',async()=>{
 const u=dialog({mode:'chat'});await flush();u.update({screenshot_mode:'code'});await u.modes[0].listeners.click();assert.equal(u.calls.find(([c])=>c==='capture_screenshot')[1].paste,false);assert.ok(u.calls.some(([,a])=>a?.action==='save'));
});
test('Code result never invokes a hidden manual paste action',async()=>{
 const u=dialog();await flush();await u.modes[0].listeners.click();await u.el('paste').listeners.click();assert.ok(!u.calls.some(([,a])=>a?.action==='paste'));
});
test('file result and user choices survive language/mode refresh without a second save',async()=>{
 const u=dialog({mode:'unknown'});await flush();u.el('auto-paste').checked=false;u.el('as-file').checked=true;u.el('as-file').listeners.change();await u.modes[0].listeners.click();
 u.update({settings:{language:'de'},screenshot_mode:'chat'});await u.timers[0]();assert.equal(u.el('code-hint').textContent,hints.de);assert.equal(u.el('feedback').textContent,files.de[1]);assert.equal(u.el('image').src,'data:image/png;base64,AAAA');assert.equal(u.el('auto-paste').checked,false);assert.equal(u.el('save-file').hidden,false);
 assert.equal(u.calls.filter(([,a])=>a?.action==='save').length,1);
});
test('all 34 languages include option, concise mode explanation and share-separately success',async()=>{
 assert.deepEqual(Object.keys(hints).sort(),Object.keys(languages).sort());assert.deepEqual(Object.keys(files).sort(),Object.keys(languages).sort());
 for(const language of Object.keys(languages)){assert.ok(hints[language]?.trim());assert.equal(files[language].length,2);assert.ok(files[language].every(s=>s.trim()));for(const word of ['Code','Chat','Work'])assert.ok(hints[language].includes(word),language+': '+word);assert.match(hints[language],/PNG/);const u=dialog({language});await flush();assert.equal(u.el('code-hint').textContent,hints[language]);}
});
test('initial HTML includes a real file option and explanation, not a may-fail notice',()=>{
 const html=read('frontend/screenshot.html');assert.match(html,/id="as-file"/);assert.match(html,/Screenshot as file/);assert.match(html,/In Code, save as PNG/);assert.match(html,/In Chat and Work, paste directly/);assert.doesNotMatch(html,/Pasting in Code may fail/);
 assert.doesNotMatch(read('src-tauri/src/paste_composer.js'),/return fail\('code-editor'\)/);
});
