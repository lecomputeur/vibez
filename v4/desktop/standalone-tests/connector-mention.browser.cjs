'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{spawn}=require('node:child_process'),assert=require('node:assert/strict');
const base=path.resolve(__dirname,'../..'),out=process.argv[2],pmRoot=process.argv[3]||path.join(__dirname,'editor-fixture/node_modules');fs.mkdirSync(out,{recursive:true});
const source=fs.readFileSync(path.join(base,'desktop/src-tauri/src/connector_mention.js'),'utf8');
const A='aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',B='bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb',C='cccccccc-3333-4333-8333-cccccccccccc',E='eeeeeeee-5555-4555-8555-eeeeeeeeeeee';
const url='https://chat.mistral.ai/work/projects/'+A,title='VibeZ · Fixture';
const html=`<!doctype html><style>button,.ProseMirror{padding:12px;min-width:40px;min-height:20px}body{font-family:sans-serif}.ProseMirror{border:1px solid #aaa}</style><form><div id=root></div><button type=button id=menu>+</button><button type=submit id=send>Send</button></form><div id=overlay></div><script type=importmap>{"imports":{"prosemirror-model":"/vendor/prosemirror-model/dist/index.js","prosemirror-state":"/vendor/prosemirror-state/dist/index.js","prosemirror-view":"/vendor/prosemirror-view/dist/index.js","prosemirror-transform":"/vendor/prosemirror-transform/dist/index.js","orderedmap":"/vendor/orderedmap/dist/index.js"}}</script><script type=module>
import {Schema} from 'prosemirror-model';import {EditorState,TextSelection} from 'prosemirror-state';import {EditorView} from 'prosemirror-view';
const attrs=Object.fromEntries(['slashType','selectedValue','selectedLabel','selectedDescription','subType','icon','iconUrl','componentName','skillId'].map(k=>[k,{default:''}]));
const schema=new Schema({nodes:{doc:{content:'paragraph+'},paragraph:{content:'inline*',group:'block',parseDOM:[{tag:'p'}],toDOM:()=>['p',0]},text:{group:'inline'},hard_break:{inline:true,group:'inline',selectable:false,parseDOM:[{tag:'br'}],toDOM:()=>['br']},slash:{attrs,inline:true,group:'inline',atom:true,parseDOM:[{tag:'span.slash-node',getAttrs:d=>Object.fromEntries(Object.keys(attrs).map(k=>[k,d.getAttribute(k)||'']))}],toDOM:n=>['span',{class:'slash-node',...n.attrs},n.attrs.selectedLabel]}},marks:{strong:{parseDOM:[{tag:'strong'}],toDOM:()=>['strong',0]}}});
window.view=new EditorView(document.querySelector('#root'),{state:EditorState.create({schema}),nodeViews:{slash(node){const dom=document.createElement('span');dom.contentEditable='false';dom.textContent=node.attrs.selectedLabel;return{dom,update(n){if(n.type.name!=='slash')return false;dom.textContent=n.attrs.selectedLabel;return true;}};}}});
window.setDoc=items=>{view.updateState(EditorState.create({schema,doc:schema.node('doc',null,[schema.node('paragraph',null,items.map(x=>typeof x==='string'?schema.text(x):schema.node('slash',x)))])}));};window.refs=()=>{const result=[];view.state.doc.descendants(n=>{if(n.type.name==='slash')result.push({...n.attrs});});return result;};window.doc=()=>view.state.doc.toJSON();window.clicks=0;document.querySelector('#menu').onclick=()=>{window.clicks++;document.querySelector('#overlay').innerHTML='<div role=dialog>User search</div>';};document.querySelector('form').onsubmit=e=>{e.preventDefault();window.lastSubmitted=doc();setDoc([]);};window.fixtureReady=true;
</script>`;
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'vibez-direct-reference-'));let browser,socket,id=0;const awaiting=new Map(),errors=[],checks=[];const wait=ms=>new Promise(r=>setTimeout(r,ms));
function cdp(method,params={}){return new Promise((resolve,reject)=>{const key=++id;awaiting.set(key,{resolve,reject});socket.send(JSON.stringify({id:key,method,params}));});}
async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function fresh(target=url){await cdp('Page.navigate',{url:target});for(let n=0;n<150;n++){if(await evaluate('Boolean(window.fixtureReady)'))return;await wait(25);}throw Error('fixture load failed');}
function config(target=url,p=A,id=B,label=title){return {project:p,connector_id:id,title:label,url:target,attach:true};}
async function hint(value=config()){await evaluate(source.replace('__VIBEZ_CONNECTOR_CONTEXT__',JSON.stringify(value)));await wait(70);}
async function refs(){return evaluate('refs()');}
async function check(name,fn){await fn();checks.push(name);}
(async()=>{try{
let stderr='';browser=spawn('/usr/bin/chromium',['--headless=new','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run','--no-default-browser-check','--password-store=basic','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:['ignore','ignore','pipe'],detached:true});browser.stderr.on('data',v=>stderr=(stderr+v).slice(-20000));let endpoint;for(let n=0;n<200;n++){endpoint=stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/)?.[1];if(endpoint)break;if(browser.exitCode!==null)throw Error(stderr);await wait(30);}assert(endpoint);
const targets=await fetch('http://127.0.0.1:'+new URL(endpoint).port+'/json/list').then(r=>r.json());socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
socket.addEventListener('message',async event=>{const m=JSON.parse(event.data);if(m.id){const p=awaiting.get(m.id);if(!p)return;awaiting.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}else if(m.method==='Fetch.requestPaused'){try{const p=new URL(m.params.request.url).pathname;let body,type;if(m.params.resourceType==='Document'){body=html;type='text/html;charset=utf-8';}else if(p.startsWith('/vendor/')){const rel=p.slice(8);assert(/^(prosemirror-(model|state|view|transform)|orderedmap)\/dist\/index\.js$/.test(rel));body=fs.readFileSync(path.join(pmRoot,rel));type='text/javascript';}if(body!==undefined)await cdp('Fetch.fulfillRequest',{requestId:m.params.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:type}],body:Buffer.from(body).toString('base64')});else await cdp('Fetch.failRequest',{requestId:m.params.requestId,errorReason:'BlockedByClient'});}catch(e){errors.push(String(e));}}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);});
await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
for(const target of [url,'https://chat.mistral.ai/code/'+A,'https://chat.mistral.ai/work/'+C])await check('native reference without menu in '+target,async()=>{await fresh(target);const active=await evaluate('document.activeElement.tagName');await hint(config(target));assert.equal((await refs())[0].selectedValue,B);assert.equal((await refs()).length,1);assert.equal(await evaluate('window.clicks'),0);assert.equal(await evaluate('document.querySelectorAll("[role=dialog]").length'),0);assert.equal(await evaluate('document.activeElement.tagName'),active);await hint(config(target));assert.equal((await refs()).length,1);});
for(const mode of ['draft','other-reference','user-menu','inactive','wrong-url','external','bad-id','unsupported-editor','unsupported-paste'])await check('preserve user control: '+mode,async()=>{
 const target=mode==='external'?'https://evil.invalid/work':url;await fresh(target);
 if(mode==='draft')await evaluate('setDoc(["Private draft stays"]);view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,4)));');
 if(mode==='other-reference')await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(E)+',selectedLabel:"Another connector"}]);');
 if(mode==='user-menu')await evaluate('document.querySelector("#overlay").innerHTML="<div role=dialog>User search<input value=original></div>"');
 if(mode==='unsupported-editor')await evaluate('document.querySelector(".ProseMirror").pmViewDesc.node.type.schema.nodes.slash.spec.parseDOM=[]');
 if(mode==='unsupported-paste')await evaluate('document.querySelector(".ProseMirror").addEventListener("paste",e=>e.stopImmediatePropagation(),true)');
 const before=await evaluate('doc()'),sel=await evaluate('view.state.selection.from');
 const c=mode==='inactive'?null:config(mode==='wrong-url'?url+'/wrong':target);if(mode==='bad-id')c.connector_id='not-an-id';
 await hint(c);assert.deepEqual(await evaluate('doc()'),before);assert.equal(await evaluate('view.state.selection.from'),sel);assert.equal(await evaluate('window.clicks'),0);
 if(mode==='user-menu')assert.equal(await evaluate('document.querySelector("[role=dialog] input").value'),'original');
});
for(const target of [url,'https://chat.mistral.ai/code/'+A,'https://chat.mistral.ai/work/'+C])await check('automatic chip takes no visible typing space in '+target,async()=>{
 await fresh(target);await hint(config(target));assert.equal((await refs())[0].selectedValue,B);
 const result=await evaluate('(()=>{const e=document.querySelector(".ProseMirror"),n=e.querySelector("[contenteditable=false]");return {text:document.body.innerText,rects:n.getClientRects().length,hidden:n.getAttribute("aria-hidden"),model:refs()};})()');
 assert.equal(result.rects,0);assert.equal(result.hidden,'true');assert(!result.text.includes(title));assert.equal(result.model[0].selectedLabel,title);
});
await check('typing and sending retain the hidden connector without changing user text',async()=>{
 await fresh();await hint();await evaluate('view.focus()');await cdp('Input.insertText',{text:'Hello from the project'});await hint();
 assert.equal(await evaluate('view.state.doc.textContent'),'Hello from the project');assert.equal((await refs()).length,1);
 const r=await evaluate('(()=>{const r=document.querySelector("#send").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()');
 await cdp('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...r});await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...r});await wait(50);
 const sent=await evaluate('window.lastSubmitted');assert.equal(sent.content[0].content.filter(n=>n.type==='text').map(n=>n.text).join(''),'Hello from the project');assert(sent.content[0].content.some(n=>n.type==='slash'&&n.attrs.selectedValue===B));
 await hint();assert.equal((await refs()).length,1);assert(!await evaluate('document.querySelector(".ProseMirror").innerText.includes('+JSON.stringify(title)+')'));
});
await check('an existing exact VibeZ connector is concealed without replacing its message model',async()=>{
 await fresh();await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(B)+',selectedLabel:'+JSON.stringify(title)+'}])');await hint();
 assert.equal(await evaluate('document.querySelector(".ProseMirror [contenteditable=false]").getClientRects().length'),0);assert.equal((await refs()).length,1);
});
await check('select all and replace remains a normal editing operation',async()=>{
 await fresh();await hint();await evaluate('view.focus()');await cdp('Input.insertText',{text:'Original text'});
 await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:2});await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:2});
 await cdp('Input.insertText',{text:'Replacement text'});await hint();assert.equal(await evaluate('view.state.doc.textContent'),'Replacement text');assert.equal((await refs()).length,1);
});
await check('text selection after replacing a draft is never overwritten by routing repair',async()=>{
 await fresh();await hint();await evaluate('setDoc(["Keep this selected draft"]);view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,1,10)))');
 const before=await evaluate('doc()'),selection=await evaluate('[view.state.selection.from,view.state.selection.to]');await hint();assert.deepEqual(await evaluate('doc()'),before);assert.deepEqual(await evaluate('[view.state.selection.from,view.state.selection.to]'),selection);
});
await check('unsupported repair paste is tried once without repeated input events',async()=>{
 await fresh();await hint();await evaluate('setDoc(["Keep my text"]);view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,view.state.doc.content.size-1)));window.repairs=0;document.querySelector(".ProseMirror").addEventListener("paste",e=>{window.repairs++;e.stopImmediatePropagation()},true)');
 for(let n=0;n<5;n++)await hint();assert.equal(await evaluate('window.repairs'),1);assert.equal(await evaluate('view.state.doc.textContent'),'Keep my text');
});
await check('a reference lost to Backspace or Delete beside the hidden chip comes back every time',async()=>{
 // The chip is invisible, so deleting it while typing is never meant. Each
 // loss is repaired at once (not only once per draft, and not only at send).
 await fresh();await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(B)+',selectedLabel:'+JSON.stringify(title)+'},"Test"])');await hint();assert.equal((await refs()).length,1,'start: one reference');
 for(let round=0;round<3;round++){
  // Put the caret right after the chip and press Backspace: ProseMirror removes the atom.
  await evaluate('(()=>{let pos=null;view.state.doc.descendants((n,p)=>{if(n.type.name==="slash")pos=p+n.nodeSize;});view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,pos)));})()');
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
  await wait(60);await hint();
  assert.equal((await refs()).length,1,'round '+round+': the reference is back');
  assert.equal(await evaluate('view.state.doc.textContent'),'Test','round '+round+': typed text untouched');
 }
 // Delete with the caret before the chip behaves the same.
 await evaluate('(()=>{let pos=null;view.state.doc.descendants((n,p)=>{if(n.type.name==="slash")pos=p;});view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,pos)));})()');
 await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Delete',code:'Delete',windowsVirtualKeyCode:46});await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Delete',code:'Delete',windowsVirtualKeyCode:46});
 await wait(60);await hint();assert.equal((await refs()).length,1);assert.equal(await evaluate('view.state.doc.textContent'),'Test');
 // Clearing the whole draft on purpose is still respected.
 await evaluate('setDoc([])');await hint();assert.deepEqual(await refs(),[]);assert.equal(await evaluate('window.__vibezLocalConnectorMention.status'),'user_removed');
});
const clickSend=async()=>{const r=await evaluate('(()=>{const r=document.querySelector("#send").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()');await cdp('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...r});await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...r});await wait(50);};
const sentParts=sent=>({first:sent.content[0].content[0]?.type,text:sent.content[0].content.filter(n=>n.type==='text').map(n=>n.text).join(''),ids:sent.content[0].content.filter(n=>n.type==='slash').map(n=>n.attrs.selectedValue)});
await check('a draft typed before VibeZ connected is left alone while edited and gets its reference at send',async()=>{
 // Typed first, connected afterwards: no reference while the text is edited.
 await fresh();await evaluate('view.focus()');await cdp('Input.insertText',{text:'Typed before connecting'});
 await hint();await cdp('Input.insertText',{text:' and after'});await wait(40);await hint();
 assert.deepEqual(await refs(),[]);assert.equal(await evaluate('view.state.doc.textContent'),'Typed before connecting and after');assert.equal(await evaluate('window.__vibezLocalConnectorMention.status'),'preserved_draft');
 await clickSend();const sent=sentParts(await evaluate('window.lastSubmitted'));
 assert.equal(sent.text,'Typed before connecting and after');assert.deepEqual(sent.ids,[B]);assert.equal(sent.first,'slash');
 await hint();assert.equal((await refs()).length,1);
});
await check('a restored draft gets its reference at an Enter send and keeps its text',async()=>{
 await fresh();await evaluate('setDoc(["Restored draft"]);document.querySelector(".ProseMirror").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();window.atEnter=doc();}})');await hint();assert.deepEqual(await refs(),[]);
 await evaluate('view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,view.state.doc.content.size-1)))');
 await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await wait(40);
 const sent=sentParts(await evaluate('window.atEnter'));assert.equal(sent.text,'Restored draft');assert.deepEqual(sent.ids,[B]);
 // The reference leads the message, as it does in an empty composer, and the caret stays where it was.
 assert.equal(sent.first,'slash');assert.equal(await evaluate('view.state.selection.from'),await evaluate('view.state.doc.content.size-1'));
 assert.equal(await evaluate('[...document.querySelectorAll(".ProseMirror [contenteditable=false]")].filter(e=>e.getClientRects().length).length'),0);
});
await check('a reference added at send leaves a caret in the middle of the draft where it was',async()=>{
 await fresh();await evaluate('setDoc(["Middle caret draft"]);document.querySelector(".ProseMirror").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();window.atEnter=doc();}})');await hint();
 await evaluate('view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,8)))');
 await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await wait(40);
 const sent=sentParts(await evaluate('window.atEnter'));assert.equal(sent.text,'Middle caret draft');assert.deepEqual(sent.ids,[B]);assert.equal(sent.first,'slash');
 // Seven characters and the reference now lie before the caret.
 assert.equal(await evaluate('view.state.selection.from'),9);assert.equal(await evaluate('view.state.selection.empty'),true);
 await cdp('Input.insertText',{text:'X'});assert.equal(await evaluate('view.state.doc.textContent'),'Middle Xcaret draft');
});
await check('a selected part of a draft is never replaced by the reference at send',async()=>{
 await fresh();await evaluate('setDoc(["Keep this selected draft"]);view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,1,10)))');await hint();
 await clickSend();const sent=sentParts(await evaluate('window.lastSubmitted'));assert.equal(sent.text,'Keep this selected draft');assert.deepEqual(sent.ids,[]);
});
await check('a replaced connector left in a draft does not hold the current reference back at send',async()=>{
 // Same project label, other UUID: the connector was replaced after the draft was written.
 await fresh();await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(E)+',selectedLabel:'+JSON.stringify(title)+'},"Old draft"])');const before=await evaluate('doc()');
 await hint();assert.deepEqual(await evaluate('doc()'),before);
 await evaluate('view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,view.state.doc.content.size-1)))');
 await clickSend();const sent=sentParts(await evaluate('window.lastSubmitted'));assert.equal(sent.text,'Old draft');assert.deepEqual(sent.ids.sort(),[B,E].sort());
});
await check('another connector or attachment in a draft still keeps VibeZ out at send',async()=>{
 await fresh();await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(E)+',selectedLabel:"Another connector"},"Other draft"]);view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,view.state.doc.content.size-1)))');await hint();
 await clickSend();const sent=sentParts(await evaluate('window.lastSubmitted'));assert.equal(sent.text,'Other draft');assert.deepEqual(sent.ids,[E]);
});
await check('composing text is not interrupted by routing repair',async()=>{
 await fresh();await hint();await evaluate('setDoc(["Keep composing"]);view.focus();window.__vibezLocalConnectorMention.composing=true');const before=await evaluate('doc()');await hint();assert.deepEqual(await evaluate('doc()'),before);
});
await check('duplicate references to the same verified local connector take no typing space',async()=>{
 await fresh();await hint();await evaluate('view.dispatch(view.state.tr.insert(view.state.doc.content.size-1,view.state.schema.nodes.slash.create({slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(B)+',selectedLabel:"Manual choice"})))');await hint();
 assert.equal((await refs()).length,2);assert.equal(await evaluate('[...document.querySelectorAll(".ProseMirror [contenteditable=false]")].filter(e=>e.getClientRects().length).length'),0);
});
for(const target of [url,'https://chat.mistral.ai/code/'+A,'https://chat.mistral.ai/work/'+C])await check('restored draft reference is quiet without editing text in '+target,async()=>{
 await fresh(target);await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(B)+',selectedLabel:'+JSON.stringify(title)+'},"A draft remains intact"]);view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,3,9)))');
 const before=await evaluate('doc()'),selection=await evaluate('[view.state.selection.from,view.state.selection.to]');await hint(config(target));assert.deepEqual(await evaluate('doc()'),before);assert.deepEqual(await evaluate('[view.state.selection.from,view.state.selection.to]'),selection);assert.equal(await evaluate('document.querySelector(".ProseMirror [contenteditable=false]").getClientRects().length'),0);assert.equal((await refs())[0].selectedValue,B);
});
await check('restoring a draft after integration memory is cleared does not leave a visible chip',async()=>{
 await fresh();await hint();const before=await evaluate('doc()');await evaluate('delete window.__vibezLocalConnectorMention');await hint();assert.deepEqual(await evaluate('doc()'),before);assert.equal(await evaluate('document.querySelector(".ProseMirror [contenteditable=false]").getClientRects().length'),0);
});
await check('a connector merely named VibeZ remains visible when its UUID is unrelated',async()=>{
 await fresh();await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(E)+',selectedLabel:'+JSON.stringify(title)+'}])');const before=await evaluate('doc()');await hint();assert.deepEqual(await evaluate('doc()'),before);assert.equal(await evaluate('document.querySelector(".ProseMirror [contenteditable=false]").getClientRects().length'),1);
});
await check('pausing an adopted local reference leaves unrelated connectors and text intact',async()=>{
 await fresh();await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(B)+',selectedLabel:'+JSON.stringify(title)+'},{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(E)+',selectedLabel:"Other connector"},"Draft text"])');await hint();await hint(null);assert.equal(await evaluate('view.state.doc.textContent'),'Draft text');assert.deepEqual((await refs()).map(n=>n.selectedValue),[E]);assert.equal(await evaluate('document.querySelector(".ProseMirror [contenteditable=false]").getClientRects().length'),1);
});
await check('cached identity hides a restored reference while signed out without editing its model',async()=>{
 await fresh();await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(B)+',selectedLabel:'+JSON.stringify(title)+'},"Draft stays unchanged"])');const before=await evaluate('doc()');await hint({...config(),attach:false});assert.deepEqual(await evaluate('doc()'),before);assert.equal(await evaluate('document.querySelector(".ProseMirror [contenteditable=false]").getClientRects().length'),0);assert.equal(await evaluate('window.__vibezLocalConnectorMention.status'),'presentation_only');
});
await check('cached identity never adds or activates a connector while disconnected',async()=>{
 await fresh();for(let n=0;n<3;n++)await hint({...config(),attach:false});assert.deepEqual(await refs(),[]);assert.equal(await evaluate('window.clicks'),0);
});
await check('a passive presentation restores visibility on loss of verified context and keeps the draft',async()=>{
 await fresh();await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(B)+',selectedLabel:'+JSON.stringify(title)+'},"Draft text"])');const before=await evaluate('doc()');await hint({...config(),attach:false});await hint(null);assert.deepEqual(await evaluate('doc()'),before);assert.equal(await evaluate('document.querySelector(".ProseMirror [contenteditable=false]").getClientRects().length'),1);
});
await check('manual pause removes an active automatic reference and never adds it back',async()=>{
 await fresh();await hint();await hint({...config(),attach:false});await hint({...config(),attach:false});assert.deepEqual(await refs(),[]);
});
await check('same title uses exact connector UUID, no name lookup',async()=>{await fresh();await hint(config(url,A,C));assert.deepEqual((await refs()).map(r=>r.selectedValue),[C]);});
await check('Work tag preserves the exact verified provider label',async()=>{const label='vibezwork0123456789abcdef';await fresh();await hint(config(url,A,B,label));assert.deepEqual((await refs()).map(({selectedValue,selectedLabel})=>[selectedValue,selectedLabel]),[[B,label]]);assert(!await evaluate('document.querySelector(".ProseMirror").innerText.includes('+JSON.stringify(label)+')'));});
await check('Work provider label cannot attach to Code or come from an unrelated slug',async()=>{await fresh();await hint(config(url,'code-'+A,B,'vibezwork0123456789abcdef'));assert.deepEqual(await refs(),[]);await hint(config(url,A,B,'vibezwork0123456789abcdeg'));assert.deepEqual(await refs(),[]);});
await check('switch projects on the same editor without stale references or menus',async()=>{await fresh();for(let n=0;n<10;n++){const isA=n%2===0,p=isA?A:C,id=isA?B:E;await hint(config(url,p,id));await hint(config(url,p,id));assert.deepEqual((await refs()).map(r=>r.selectedValue),[id]);assert.equal(await evaluate('window.clicks'),0);}});
await check('pause removes only automatic reference and preserves typed text and marks',async()=>{await fresh();await hint();await evaluate('view.dispatch(view.state.tr.insertText("Private draft",view.state.doc.content.size-1).addMark(2,5,view.state.schema.marks.strong.create()))');const before=await evaluate('view.state.doc.textContent');await hint(null);assert.deepEqual(await refs(),[]);assert.equal(await evaluate('view.state.doc.textContent'),before);await hint(null);assert.equal(await evaluate('window.clicks'),0);});
await check('manual reference removal is respected',async()=>{await fresh();await hint();await evaluate('setDoc([])');await hint();assert.deepEqual(await refs(),[]);assert.equal(await evaluate('window.__vibezLocalConnectorMention.status'),'user_removed');});
await check('new conversation receives a reference after manual removal in an older one',async()=>{await evaluate('history.replaceState(null,"","/work/'+C+'")');const target='https://chat.mistral.ai/work/'+C;await hint(config(target));assert.equal((await refs()).length,1);});
await check('same conversation receives a reference after a real send',async()=>{await fresh();await hint();for(let n=0;n<2;n++){const r=await evaluate('(()=>{const r=document.querySelector("#send").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()');await cdp('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...r});await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...r});await wait(50);await hint();assert.equal((await refs()).length,1);}});
await check('Work folder labels are hidden on screen but kept for Mistral and VibeZ menus',async()=>{
 const work='vibezwork0123456789abcdef';await fresh();
 await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(E)+',selectedLabel:'+JSON.stringify(work)+'}," Welke bestanden?"])');
 await evaluate(`document.body.insertAdjacentHTML('beforeend','<div id=msg><span class=chip><svg width=8 height=8></svg><span>${work}</span></span> Welke bestanden staan er?</div><div id=tool>Gebruikte ${work}: List directory</div><div role=menu><button id=row>${work}</button></div>')`);
 await hint(null);
 // The reference stays; only the separator space beside the hidden chip goes.
 assert.equal((await refs())[0].selectedLabel,work);
 assert.equal(await evaluate('view.state.doc.textContent'),'Welke bestanden?');
 assert.equal(await evaluate('getComputedStyle(document.querySelector(".ProseMirror span[contenteditable=false]")).display'),'none');
 assert.equal(await evaluate('getComputedStyle(document.querySelector("#msg .chip")).display'),'none');
 assert.equal(await evaluate('document.querySelector("#msg").innerText'),'Welke bestanden staan er?','no separator gap is left in a sent message');
 assert.equal(await evaluate('document.querySelector("#tool").textContent'),'Gebruikte: List directory');
 assert.equal(await evaluate('document.querySelector("#row").innerText'),work,'menus keep the label for the setup steps');
 // A chip inside a word or between words (the separator Work adds) leaves
 // the words intact: "Test", not "T est"; typed spacing between words stays.
 await evaluate(`document.body.insertAdjacentHTML('beforeend','<div id=split>T<span class=chip><span>${work}</span></span> est</div><div id=between>Hello <span class=chip><span>${work}</span></span> world</div><div id=tail>Hello <span class=chip><span>${work}</span></span></div><div id=line>Read ${work} now</div>')`);await wait(50);
 assert.equal(await evaluate('document.querySelector("#split").innerText'),'Test');
 assert.equal(await evaluate('document.querySelector("#between").innerText'),'Hello world');
 assert.equal(await evaluate('document.querySelector("#tail").innerText'),'Hello');
 assert.equal(await evaluate('document.querySelector("#line").textContent'),'Read now');
 // Later messages and streamed text are handled too.
 await evaluate(`document.body.insertAdjacentHTML('beforeend','<div id=late>Used ${work}: Read file</div>')`);await wait(50);
 assert.equal(await evaluate('document.querySelector("#late").textContent'),'Used: Read file');
 await evaluate('view.dispatch(view.state.tr.insertText("!"))');
 assert.equal((await refs()).length,1,'typing keeps the reference');
});
await check('Backspace and Delete beside the hidden chip remove the character a person sees, never the chip',async()=>{
 const key=async(name,code)=>{await cdp('Input.dispatchKeyEvent',{type:'rawKeyDown',key:name,code:name,windowsVirtualKeyCode:code,nativeVirtualKeyCode:code});await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:name,code:name,windowsVirtualKeyCode:code});await wait(80);};
 const caret=async after=>{await evaluate('(()=>{let pos=null;view.state.doc.descendants((n,p)=>{if(n.type.name==="slash")pos='+(after?'p+n.nodeSize':'p')+';});view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,pos)));})()');await wait(30);};
 await fresh();await evaluate('setDoc(["ab",{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(B)+',selectedLabel:'+JSON.stringify(title)+'},"cd"])');await hint();
 assert.equal(await evaluate('getComputedStyle(document.querySelector(".ProseMirror [contenteditable=false]")).display'),'none','the chip is hidden');
 // Caret right after the hidden chip: Backspace removes the "b" before it.
 await caret(true);await key('Backspace',8);
 assert.equal(await evaluate('view.state.doc.textContent'),'acd','Backspace took the visible character');
 assert.equal((await refs()).length,1,'the chip stays');
 // Caret right before the hidden chip: Delete removes the "c" after it.
 await caret(false);await key('Delete',46);
 assert.equal(await evaluate('view.state.doc.textContent'),'ad','Delete took the visible character');
 assert.equal((await refs()).length,1,'the chip stays');
 // Nothing visible beside the chip: the key does nothing and the chip stays.
 await evaluate('setDoc([{slashType:"text-tag",subType:"connection",selectedValue:'+JSON.stringify(B)+',selectedLabel:'+JSON.stringify(title)+'},"x"])');await hint();
 await caret(true);await key('Backspace',8);
 assert.equal(await evaluate('view.state.doc.textContent'),'x');assert.equal((await refs()).length,1,'chip at the start survives Backspace');
 // Typing afterwards still works and Ctrl+A, Backspace clears the whole draft on purpose.
 await evaluate('view.dispatch(view.state.tr.insertText("!"))');assert.equal(await evaluate('view.state.doc.textContent'),'!x','the caret stayed beside the chip');
 await evaluate('view.focus();view.dispatch(view.state.tr.setSelection(view.state.selection.constructor.create(view.state.doc,0,view.state.doc.content.size)))');await key('Backspace',8);await hint();
 assert.equal(await evaluate('view.state.doc.textContent'),'','a deliberate clear is respected');
});
await check('a sent message with a hidden reference never starts with white space',async()=>{
 await fresh();await hint();const work='vibezwork0123456789abcdef';
 // Reference added beside a typed draft: Mistral renders " text<chip>" (Work) or "<chip>  text" (Code).
 await evaluate(`document.body.insertAdjacentHTML('beforeend','<main><div style="white-space:pre-wrap"><p id=tail> Typed first, linked later.<span class=chip contenteditable=false><span><img alt="" width=8 height=8><span>${work}</span></span></span></p><p id=head><span class=chip contenteditable=false><span>${title}</span></span>  Two spaces follow the chip.</p><p id=inner>Keep  inner   spacing <span class=chip contenteditable=false><span>${title}</span></span> as typed.</p><p id=plain> No reference here.</p></div></main>')`);await wait(60);
 assert.equal(await evaluate('document.querySelector("#tail").innerText'),'Typed first, linked later.');
 assert.equal(await evaluate('document.querySelector("#head").innerText'),'Two spaces follow the chip.');
 assert.equal(await evaluate('document.querySelector("#inner").innerText'),'Keep  inner   spacing as typed.');
 assert.equal(await evaluate('document.querySelector("#plain").innerText'),' No reference here.');
});
await check('the project connector title is hidden in sent messages only when VibeZ passed that title in',async()=>{
 await fresh();
 // Before the context arrives, a title chip stays visible (nothing is known yet).
 await evaluate(`document.body.insertAdjacentHTML('beforeend','<div id=early><span class=chip><svg width=8 height=8></svg><span>${title}</span></span> Is git gekoppeld?</div>')`);await wait(50);
 assert.equal(await evaluate('getComputedStyle(document.querySelector("#early .chip")).display'),'inline');
 await hint();
 // The context names "VibeZ · Fixture": that chip disappears with its separator, in old and new messages.
 assert.equal(await evaluate('getComputedStyle(document.querySelector("#early .chip")).display'),'none');
 assert.equal(await evaluate('document.querySelector("#early").innerText'),'Is git gekoppeld?','no separator gap is left beside the hidden title chip');
 await evaluate(`document.body.insertAdjacentHTML('beforeend','<div id=late2><span class=chip><span>${title}</span></span> Welke bestanden?</div><div id=other><span class=chip><span>VibeZ · Other project</span></span> Hallo</div><p id=para>${title}</p><div id=prose>Ik noem ${title} in een zin.</div><div role=menu><button id=row2>${title}</button></div>')`);await wait(50);
 assert.equal(await evaluate('getComputedStyle(document.querySelector("#late2 .chip")).display'),'none');
 assert.equal(await evaluate('document.querySelector("#late2").innerText'),'Welke bestanden?');
 // A Code project renders the sent message as " <chip> text": no gap on either side.
 await evaluate(`document.body.insertAdjacentHTML('beforeend','<div id=lead><p> <span class=chip><span>${title}</span></span> Welke bestanden?</p></div>')`);await wait(50);
 assert.equal(await evaluate('document.querySelector("#lead").innerText'),'Welke bestanden?','a whitespace-only node before the hidden chip is gone');
 assert.equal(await evaluate('document.querySelector("#lead p").childNodes.length'),2,'the chip and the typed text remain');
 // Another project's title, a whole paragraph, typed prose and menus are left alone.
 assert.equal(await evaluate('getComputedStyle(document.querySelector("#other .chip")).display'),'inline');
 assert.equal(await evaluate('document.querySelector("#other").innerText'),'VibeZ · Other project Hallo');
 assert.equal(await evaluate('getComputedStyle(document.querySelector("#para")).display'),'block');
 assert.equal(await evaluate('document.querySelector("#prose").textContent'),'Ik noem '+title+' in een zin.');
 assert.equal(await evaluate('document.querySelector("#row2").innerText'),title,'menus keep the title for the setup steps');
 // The composer reference itself keeps its label for Mistral.
 assert.equal((await refs())[0].selectedLabel,title);
});
await check('labels in menus rendered beside main keep their text',async()=>{
 const work='vibezwork0123456789abcdef';await fresh();
 await evaluate(`document.body.insertAdjacentHTML('beforeend','<main id=area><div id=line>Gebruikte ${work}: List directory</div></main><div id=portal><div><button id=prow><span>${work}</span></button></div></div>')`);
 await hint(null);await wait(60);
 assert.equal(await evaluate('document.querySelector("#line").textContent'),'Gebruikte: List directory','inside main the label is quieted');
 assert.equal(await evaluate('document.querySelector("#prow").innerText'),work,'a picker without menu roles beside main keeps the label');
});
assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({passed:true,real_ProseMirror:true,physical_windows_used:false,network_requests_to_Mistral:false,checks},null,2)+'\n');console.log('Passed '+checks.length+' real-editor browser cases.');
}catch(e){fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({passed:false,error:String(e),checks},null,2)+'\n');throw e;}finally{if(socket)socket.close();if(browser){try{process.kill(-browser.pid,'SIGTERM');}catch{}await wait(150);}fs.rmSync(profile,{recursive:true,force:true});}})().catch(e=>{console.error(e);process.exitCode=1;});
