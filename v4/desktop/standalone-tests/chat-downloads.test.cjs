'use strict';
// Cross-platform callback contracts, exercised alongside the real Linux native
// fixture. Windows/macOS runtime execution requires their native build hosts.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),read=p=>fs.readFileSync(path.join(root,p),'utf8');
test('the hosted Mistral view uses the session-owned native download handler and blob navigation guard',()=>{
 const web=read('src-tauri/src/official_web.rs');
 assert.match(web,/\.on_download\(super::chat_downloads::handle\)/);
 assert.match(web,/chat_downloads::navigation\(&download_navigation,u\)/);
 assert.match(web,/chat_downloads::popup\(&popup,u,features\)/);
});
test('renderable blob downloads stay inside their original webview and never select native paths through JavaScript',()=>{
 const native=read('src-tauri/src/chat_downloads.rs'),script=read('src-tauri/src/chat_download.js');
 assert.match(native,/include_str!\("chat_download.js"\)\.replace\("__VIBEZ_DOWNLOAD_URL__",&json!\(url.as_str\(\)\)\.to_string\(\)\)/);
 assert.match(script,/anchor\.download=name/);assert.match(script,/'application\/pdf':'pdf'/);
 assert.doesNotMatch(script,/__TAURI__|invoke\(|file:\/\/|localStorage|document\.cookie/);
 assert.match(native,/if consume_blob_intent\(url\)\{return true;\}/);
});
test('WebKitGTK failures and rejected download completions are scoped to that native transfer',()=>{
 const source=read('src-tauri/vendor/wry/src/webkitgtk/web_context.rs');
 const start=source.indexOf('context.connect_download_started');
 assert(source.indexOf('let failed = Rc::new(RefCell::new(false))',start)>start);
 assert.match(source,/if !accepted\.get\(\) \{ return; \}/);
 assert.match(source,/accepted_start\.set\(true\)/);
});
test('Windows terminal completions and macOS accepted-download identities are consumed once',()=>{
 const win=read('src-tauri/vendor/wry/src/webview2/mod.rs'),mac=read('src-tauri/vendor/wry/src/wkwebview/download.rs');
 assert.match(win,/if !accepted_finish\.replace\(false\) \{ return Ok\(\(\)\); \}/);
 assert.equal((mac.match(/accepted\.borrow_mut\(\)\.remove/g)||[]).length,2);
 assert.match(mac,/accepted\.borrow_mut\(\)\.insert/);
});
test('a blob URL that Mistral revokes in the click task stays alive for the reissued native download',()=>{
 // Measured on 13 Nov 2026: the image download button clicks an anchor, removes
 // it and revokes its blob URL in the same task, before the native reissue.
 const vm=require('node:vm'),source=read('src-tauri/src/chat_download_keep.js');
 assert.match(read('src-tauri/src/official_web.rs'),/\.initialization_script\(include_str!\("chat_download_keep.js"\)\)/);
 assert.match(read('src-tauri/src/chat_download.js'),/window\.__vibezBlobNames\?\.get\(url\)/);
 assert.doesNotMatch(source,/__TAURI__|invoke\(|file:\/\/|localStorage|document\.cookie|fetch\(/);
 function page(hostname){
  const revoked=[],timers=[],listeners=[];
  class Element{closest(){return this.anchor||null;}}
  class Anchor extends Element{constructor(href,download){super();this.href=href;this.download=download;this.clicked=0;}hasAttribute(n){return n==='download'&&this.download!==undefined;}}
  const HTMLAnchorElement=function(){};HTMLAnchorElement.prototype.click=function(){this.clicked++;};
  Object.setPrototypeOf(Anchor.prototype,Element.prototype);Anchor.prototype.click=function(){return HTMLAnchorElement.prototype.click.apply(this,arguments);};
  const URL={revokeObjectURL:u=>{revoked.push(String(u));}};
  const window={},context={window,location:{hostname},URL,Element,HTMLAnchorElement,Map,String,setTimeout:(fn,ms)=>timers.push({fn,ms}),document:{addEventListener:(type,fn,capture)=>listeners.push({type,fn,capture})}};
  vm.runInNewContext(source,context);
  return {window,URL,Anchor,Element,revoked,timers,listeners};
 }
 const p=page('chat.mistral.ai'),url='blob:https://chat.mistral.ai/11111111-2222-4333-8444-555555555555';
 const anchor=new p.Anchor(url,'logo.jpg');
 anchor.click();assert.equal(anchor.clicked,1,'the page still performs its own click');
 p.URL.revokeObjectURL(url);
 assert.deepEqual(p.revoked,[],'the clicked download URL is not revoked in the same task');
 assert.equal(p.window.__vibezBlobNames.get(url),'logo.jpg');
 assert.equal(p.timers.length,1);assert.equal(p.timers[0].ms,30000);
 p.timers[0].fn();assert.deepEqual(p.revoked,[url],'it is revoked afterwards');assert.equal(p.window.__vibezBlobNames.has(url),false);
 p.URL.revokeObjectURL('blob:https://chat.mistral.ai/other');
 assert.deepEqual(p.revoked,[url,'blob:https://chat.mistral.ai/other'],'a blob that was never a clicked download is revoked at once');
 // The capturing listener covers a real pointer click on a child of the anchor.
 const q=page('vibe.mistral.ai'),child=new q.Element();child.anchor=new q.Anchor(url,'a.png');
 assert.equal(q.listeners[0].type,'click');assert.equal(q.listeners[0].capture,true);
 q.listeners[0].fn({target:child});assert.equal(q.window.__vibezBlobNames.get(url),'a.png');
 // A plain link, a non-blob download and any other site are left alone.
 const plain=new q.Anchor(url,undefined);plain.click();assert.equal(q.window.__vibezBlobNames.size,1);
 new q.Anchor('https://chat.mistral.ai/file','x.pdf').click();assert.equal(q.window.__vibezBlobNames.size,1);
 const other=page('accounts.example.com');assert.equal(other.window.__vibezBlobNames,undefined);assert.equal(other.listeners.length,0);
});
