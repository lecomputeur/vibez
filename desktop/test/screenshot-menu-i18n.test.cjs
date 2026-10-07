'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const base=path.join(__dirname,'..'),read=p=>fs.readFileSync(path.join(base,p),'utf8');
const data=require('../../i18n.js'),rows=require('../screenshot-i18n.json');
const keys=['screenshotAutoPaste','screenshotPaste','screenshotSavePng','screenshotNew','screenshotCopyFailed','screenshotCancel'];
const flush=()=>new Promise(r=>setImmediate(r));
function environment(setting='system',locale='nl_NL.UTF-8'){
 let state={settings:{language:setting},os_locale:locale,platform:'linux'};
 const elements=new Map(),calls=[],timers=[],listeners={};
 function el(id){if(!elements.has(id))elements.set(id,{id,dataset:{},hidden:false,disabled:true,checked:true,textContent:'',attributes:{},focus(){},setAttribute(k,v){this.attributes[k]=v;},removeAttribute(k){delete this[k];},addEventListener(k,v){this[k]=v;}});return elements.get(id);}
 for(const [id,key] of [['auto-label','auto'],['paste','paste'],['save','save'],['copy','copy'],['again','again']])el(id).dataset.shot=key;
 el('heading').dataset.i18n='screenshot';
 const modes=['visible','full','selection'].map(mode=>{const e=el(mode);e.dataset.mode=mode;return e;});
 const doc={documentElement:{},getElementById:el,addEventListener(){},querySelector:()=>modes[0],querySelectorAll:q=>q==='[data-shot]'?[...elements.values()].filter(e=>e.dataset.shot):q==='[data-i18n]'?[el('heading')]:q==='[data-extra]'?[]:q==='[data-mode]'?modes:q==='button,input'?[...modes,...['close','copy','save','paste','again','auto-paste'].map(el)]:[]};
 const previewData={translations:Object.fromEntries(Object.keys(rows).map(code=>[code,Object.fromEntries(keys.map((key,i)=>[key,rows[code][i]]))]))};
 const window={VIBEZ_TRANSLATIONS:{translations:data.TRANSLATIONS},VIBEZ_PREVIEW_TRANSLATIONS:previewData,addEventListener(k,v){listeners[k]=v;},__TAURI__:{core:{invoke:async(c,a)=>{calls.push([c,a]);return state;}}}};
 const context={window,document:doc,setInterval:f=>{timers.push(f);return timers.length;},clearInterval(){}};vm.createContext(context);
 vm.runInContext(read('frontend/common.js'),context);context.preview=window.preview;
 vm.runInContext(read('frontend/screenshot.js'),context);
 return {el,doc,calls,timers,listeners,change(language){state={...state,settings:{language}};},failRead(){window.__TAURI__.core.invoke=async()=>{throw Error('offline');};}};
}
test('every supported language has all screenshot-menu labels without English fallback',()=>{
 assert.deepEqual(Object.keys(rows).sort(),Object.keys(data.TRANSLATIONS).sort());assert.equal(Object.keys(rows).length,34);
 for(const [code,values] of Object.entries(rows)){assert.equal(values.length,keys.length,code);assert.ok(values.every(v=>typeof v==='string'&&v.trim()),code);if(code!=='en')assert.notEqual(values[0],rows.en[0],code);}
});
test('the compact menu has no descriptions under choices or the paste checkbox',()=>{
 const html=read('frontend/screenshot.html');assert.doesNotMatch(html,/<small\b|class="note"|data-shot="(?:visibleHelp|fullHelp|selectionHelp|note)"/);
 assert.equal((html.match(/data-mode=/g)||[]).length,3);assert.match(html,/id="auto-paste" checked/);
 assert.match(read('src-tauri/src/screenshot_dialog.rs'),/inner_size\(280\.,184\.\)/);
 assert.doesNotMatch(read('frontend/screenshot.js'),/const strings\s*=|\bnl:\s*\{|\ben:\s*\{/);
});
test('all 34 menu languages render from the shared locale, including right-to-left',async()=>{
 for(const code of Object.keys(rows)){
  const u=environment(code);await flush();assert.equal(u.el('auto-label').textContent,rows[code][0],code);assert.equal(u.el('copy').textContent,data.TRANSLATIONS[code].copy,code);assert.equal(u.doc.documentElement.lang,code);assert.equal(u.doc.documentElement.dir,['ar','he','fa','ur'].includes(code)?'rtl':'ltr');assert.equal(u.el('image').alt,data.TRANSLATIONS[code].screenshot);
 }
});
test('system language follows Mint locale; explicit app language overrides it',async()=>{
 const mint=environment();await flush();assert.equal(mint.doc.documentElement.lang,'nl');assert.equal(mint.el('auto-label').textContent,rows.nl[0]);
 const french=environment('fr');await flush();assert.equal(french.el('auto-label').textContent,rows.fr[0]);
 const unknown=environment('system','xx_XX');await flush();assert.equal(unknown.doc.documentElement.lang,'en');
});
test('an open menu follows language changes without resetting the paste checkbox or PNG',async()=>{
 const u=environment();await flush();u.el('auto-paste').checked=false;u.el('image').src='data:image/png;base64,AAAA';u.el('result').hidden=false;u.el('choose').hidden=true;
 u.change('de');u.timers[0]();await flush();assert.equal(u.el('auto-label').textContent,rows.de[0]);assert.equal(u.el('auto-paste').checked,false);assert.equal(u.el('image').src,'data:image/png;base64,AAAA');assert.equal(u.el('result').hidden,false);assert.equal(u.el('choose').hidden,true);
 u.change('ar');u.listeners.focus();await flush();assert.equal(u.doc.documentElement.dir,'rtl');assert.equal(u.el('auto-label').textContent,rows.ar[0]);assert.ok(u.calls.every(c=>c[0]==='get_state'));
});
test('a failed background locale refresh preserves the already usable menu',async()=>{
 const u=environment();await flush();u.failRead();u.timers[0]();await flush();assert.equal(u.el('auto-label').textContent,rows.nl[0]);assert.equal(u.el('visible').disabled,false);assert.equal(u.el('feedback').hidden,true);
});
