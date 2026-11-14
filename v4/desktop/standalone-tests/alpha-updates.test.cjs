'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {presentation,attach}=require('../../standalone-ui/alpha-updates.js');
const translations=require('../../standalone-ui/language-extra.json');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function environment(initial={status:'current',kind:'native',automatic:true}){
 const calls=[],listeners={},changes=[],nodes={};let locale='nl',handler;
 for(const id of ['alpha-update-status','alpha-update-check','alpha-update-allow'])nodes[id]={textContent:'',title:'',hidden:false,disabled:false,attributes:{},handlers:{},setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,fn){this.handlers[k]=fn;}};
 const language={t:key=>translations[locale][key],ready:async()=>{},onChange:fn=>changes.push(fn)};
 const tauri={event:{listen:async(name,fn)=>{(listeners[name]||=[]).push(fn);}},core:{invoke:async name=>{calls.push(name);return handler?handler(name):initial;}}};
 return {nodes,calls,listeners,language,tauri,document:{getElementById:id=>nodes[id]},
  emit(name,payload){for(const fn of listeners[name]||[])fn({payload});},
  setLanguage(next){locale=next;for(const fn of changes)fn();},
  setHandler(fn){handler=fn;},click(id){nodes[id].handlers.click();}};
}
test('idle Flatpak consent is visible even without an available update',()=>{
 const view=presentation({kind:'flatpak',status:'ready',consent_required:true,available:false,automatic:true});
 assert.equal(view.key,'updatePermission');assert.equal(view.allow,true);assert.equal(view.busy,false);
 assert.equal(presentation({kind:'flatpak',status:'ready',consent_required:false}).key,'updateCurrent');
 assert.equal(presentation({kind:'native',status:'ready'}).key,'updateReady');
});
test('a Microsoft Store install says updates are automatic and offers no check of its own',()=>{
 const view=presentation({kind:'store',status:'automatic',automatic:true,channel:'store'});
 assert.equal(view.key,'updateAutomatic');assert.equal(view.store,true);assert.equal(view.allow,false);
 assert.equal(presentation({kind:'system',status:'automatic',automatic:true}).store,false);
});
test('permission and check actions cannot interrupt an active transaction',()=>{
 for(const status of ['checking','downloading','installing'])assert.equal(presentation({kind:'flatpak',status,consent_required:true}).busy,true,status);
 assert.equal(presentation({kind:'flatpak',status:'ready',busy:true}).busy,true);
 for(const status of ['screen_restricted','not_flatpak','disabled'])assert.equal(presentation({kind:'flatpak',status,consent_required:true}).allow,false,status);
 assert.equal(presentation({kind:'flatpak',status:'ready',automatic:false,consent_required:true}).allow,false);
 assert.equal(presentation({kind:'system',status:'current',consent_required:true}).allow,false);
});
test('download, next-start and close-first statuses describe distinct behavior',()=>{
 const expected={checking:'updateChecking',downloading:'updateDownloading',waiting_for_close:'updateWaiting',current:'updateCurrent',updated:'updateCurrent',error:'updateError',disabled:'updateDisabled',screen_restricted:'updateScreenRestricted'};
 for(const [status,key]of Object.entries(expected))assert.equal(presentation({kind:'system',status}).key,key);
 assert.equal(presentation({kind:'flatpak',status:'ready',restart_required:true}).key,'updateReady');
 assert.equal(presentation({kind:'flatpak',status:'error',consent_required:true,error:'denied'}).key,'updateError');
});
test('settings startup only reads state and listens to native updater events',async()=>{
 const e=environment();await attach(e);
 assert.deepEqual(e.calls,['alpha_update_state']);
 assert.deepEqual(Object.keys(e.listeners).sort(),['alpha-flatpak-update','alpha-update']);
 assert.equal(e.nodes['alpha-update-allow'].hidden,true);
 assert.equal(e.nodes['alpha-update-status'].textContent,translations.nl.updateCurrent);
 e.emit('message',{status:'consent_required'});e.emit('app-engine',{status:'error'});
 e.emit('alpha-update',null);e.emit('alpha-update',{status:'invented'});e.emit('alpha-update',[]);
 assert.deepEqual(e.calls,['alpha_update_state']);assert.equal(e.nodes['alpha-update-status'].textContent,translations.nl.updateCurrent);
});
test('every supported language updates live status and action labels',async()=>{
 const e=environment({kind:'flatpak',status:'ready',consent_required:true});await attach(e);
 assert.equal(Object.keys(translations).length,33);assert.equal(translations.ru,undefined);
 for(const [locale,t]of Object.entries(translations)){
  e.setLanguage(locale);
  for(const key of ['updateTitle','updateAutomatic','updateCurrent','updateChecking','updateDownloading','updateReady','updateWaiting','updateError','updatePermission','updateAllow','updateCheck','updateDisabled','updateScreenRestricted'])assert.ok(t[key]?.trim(),locale+':'+key);
  assert.equal(e.nodes['alpha-update-status'].textContent,t.updatePermission,locale);
  assert.equal(e.nodes['alpha-update-check'].textContent,t.updateCheck,locale);
  assert.equal(e.nodes['alpha-update-allow'].textContent,t.updateAllow,locale);
 }
});
test('consent requires a local click and blocks duplicate actions while pending',async()=>{
 const e=environment({kind:'flatpak',status:'ready',automatic:true,consent_required:true});await attach(e);
 const response=deferred();e.setHandler(()=>response.promise);
 e.click('alpha-update-allow');e.click('alpha-update-allow');e.click('alpha-update-check');
 assert.deepEqual(e.calls,['alpha_update_state','alpha_update_allow']);assert.equal(e.nodes['alpha-update-check'].disabled,true);
 response.resolve({kind:'flatpak',status:'ready',consent_required:false});await tick();
 assert.equal(e.nodes['alpha-update-allow'].hidden,true);assert.equal(e.nodes['alpha-update-check'].disabled,false);
 e.click('alpha-update-allow');assert.equal(e.calls.length,2);
});
test('late initial and command responses cannot undo newer progress',async()=>{
 const e=environment(),initial=deferred();e.setHandler(()=>initial.promise);
 const boot=attach(e);await tick();
 e.emit('alpha-update',{status:'downloading'});initial.resolve({status:'current'});await boot;
 assert.equal(e.nodes['alpha-update-status'].textContent,translations.nl.updateDownloading);
 e.emit('alpha-update',{status:'current'});const check=deferred();e.setHandler(()=>check.promise);e.click('alpha-update-check');
 e.emit('alpha-flatpak-update',{kind:'flatpak',status:'ready',restart_required:true});check.resolve({status:'current'});await tick();
 assert.equal(e.nodes['alpha-update-status'].textContent,translations.nl.updateReady);
});
test('a user action also supersedes an outstanding initial state read',async()=>{
 const e=environment(),initial=deferred();e.setHandler(name=>name==='alpha_update_state'?initial.promise:{status:'checking'});
 const boot=attach(e);await tick();e.click('alpha-update-check');await tick();initial.resolve({status:'current'});await boot;
 assert.equal(e.nodes['alpha-update-status'].textContent,translations.nl.updateChecking);
});
test('native errors remain literal text and controls recover after a failed request',async()=>{
 const e=environment();await attach(e);const error='<img src=x onerror=alert(1)>'.repeat(100);
 e.setHandler(()=>Promise.reject(error));e.click('alpha-update-check');await tick();
 assert.equal(e.nodes['alpha-update-status'].textContent,translations.nl.updateError);
 assert.equal(e.nodes['alpha-update-status'].title,translations.nl.updateError);assert.equal(e.nodes['alpha-update-check'].disabled,false);
 assert.equal(Object.hasOwn(e.nodes['alpha-update-status'],'innerHTML'),false);
});
