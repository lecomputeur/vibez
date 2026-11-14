'use strict';
// Real-editor regression for the Work conversation step: a hidden, stale
// VibeZ folder chip left in the composer (for example after a restart replaced
// the connector) must be removed by the automation itself, and the hidden
// chip must leave no separator gap. Runs headless Chromium with the real
// ProseMirror library; no network, no Mistral, no VibeZ installation.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{spawn}=require('node:child_process'),assert=require('node:assert/strict');
const base=path.resolve(__dirname,'../..'),out=process.argv[2],pmRoot=process.argv[3]||path.join(__dirname,'editor-fixture/node_modules');fs.mkdirSync(out,{recursive:true});
const attach=fs.readFileSync(path.join(base,'desktop/src-tauri/src/work_chat_authorize.js'),'utf8');
const mention=fs.readFileSync(path.join(base,'desktop/src-tauri/src/connector_mention.js'),'utf8');
const project='2055311c-7cae-499c-b45b-f56f185f15da',chat='4055311c-7cae-499c-b45b-f56f185f15da';
const connectorId='3055311c-7cae-499c-b45b-f56f185f15da',oldId='5055311c-7cae-499c-b45b-f56f185f15da';
const title='vibezwork0123456789abcdef',connectorName=title+'_abcd',oldTitle='vibezworkfedcba9876543210';
const marker='[VibeZ-work:'+'a'.repeat(32)+':'+project+':'+title+']',token='a'.repeat(56),job='b'.repeat(32);
const url='https://chat.mistral.ai/work/'+chat;
const html=`<!doctype html><style>button,.ProseMirror{padding:12px;min-width:40px;min-height:20px}body{font-family:sans-serif}.ProseMirror{border:1px solid #aaa}</style>
<main><form><div id=root></div><button type=button data-coachmark-target="chat-input-settings" aria-haspopup="dialog" aria-expanded="false" id=plus>+</button><button type=submit id=send>Send</button></form></main><div id=overlay></div>
<script type=importmap>{"imports":{"prosemirror-model":"/vendor/prosemirror-model/dist/index.js","prosemirror-state":"/vendor/prosemirror-state/dist/index.js","prosemirror-view":"/vendor/prosemirror-view/dist/index.js","prosemirror-transform":"/vendor/prosemirror-transform/dist/index.js","orderedmap":"/vendor/orderedmap/dist/index.js"}}</script><script type=module>
import {Schema} from 'prosemirror-model';import {EditorState} from 'prosemirror-state';import {EditorView} from 'prosemirror-view';
const attrs=Object.fromEntries(['slashType','selectedValue','selectedLabel','selectedDescription','subType','icon','iconUrl','componentName','skillId'].map(k=>[k,{default:''}]));
const schema=new Schema({nodes:{doc:{content:'paragraph+'},paragraph:{content:'inline*',group:'block',parseDOM:[{tag:'p'}],toDOM:()=>['p',0]},text:{group:'inline'},slash:{attrs,inline:true,group:'inline',atom:true,parseDOM:[{tag:'span.slash-node',getAttrs:d=>Object.fromEntries(Object.keys(attrs).map(k=>[k,d.getAttribute(k)||'']))}],toDOM:n=>['span',{class:'slash-node',...n.attrs},n.attrs.selectedLabel]}}});
window.view=new EditorView(document.querySelector('#root'),{state:EditorState.create({schema}),nodeViews:{slash(node){const dom=document.createElement('span');dom.contentEditable='false';dom.className='slash-node';dom.textContent=node.attrs.selectedLabel;return{dom,update(n){if(n.type.name!=='slash')return false;dom.textContent=n.attrs.selectedLabel;return true;}};}}});
window.setDoc=items=>{view.updateState(EditorState.create({schema,doc:schema.node('doc',null,[schema.node('paragraph',null,items.map(x=>typeof x==='string'?schema.text(x):schema.node('slash',x)))])}));};
window.refs=()=>{const result=[];view.state.doc.descendants(n=>{if(n.type.name==='slash')result.push({...n.attrs});});return result;};
window.text=()=>view.state.doc.textContent;window.plusClicks=0;document.querySelector('#plus').onclick=()=>{window.plusClicks++;};window.fixtureReady=true;
</script>`;
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'vibez-work-attach-'));let browser,socket,id=0;const awaiting=new Map(),errors=[],checks=[];const wait=ms=>new Promise(r=>setTimeout(r,ms));
function cdp(method,params={}){return new Promise((resolve,reject)=>{const key=++id;awaiting.set(key,{resolve,reject});socket.send(JSON.stringify({id:key,method,params}));});}
async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function fresh(){await cdp('Page.navigate',{url});for(let n=0;n<150;n++){if(await evaluate('Boolean(window.fixtureReady)'))return;await wait(25);}throw Error('fixture load failed');}
const input=(stage,extra={})=>JSON.stringify({url,job,project,connectorId,connectorName,marker,stage,...extra});
async function step(stage,extra){return evaluate('('+attach+')('+input(stage,extra)+')');}
async function quiet(){await evaluate(mention.replace('__VIBEZ_CONNECTOR_CONTEXT__','null'));await wait(60);}
const chip=(value,label)=>({slashType:'text-tag',subType:'connection',selectedValue:value,selectedLabel:label});
async function check(name,fn){await fn();checks.push(name);}
(async()=>{try{
let stderr='';browser=spawn('/usr/bin/chromium',['--headless=new','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run','--no-default-browser-check','--password-store=basic','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:['ignore','ignore','pipe'],detached:true});browser.stderr.on('data',v=>stderr=(stderr+v).slice(-20000));let endpoint;for(let n=0;n<200;n++){endpoint=stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/)?.[1];if(endpoint)break;if(browser.exitCode!==null)throw Error(stderr);await wait(30);}assert(endpoint);
const targets=await fetch('http://127.0.0.1:'+new URL(endpoint).port+'/json/list').then(r=>r.json());socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
socket.addEventListener('message',async event=>{const m=JSON.parse(event.data);if(m.id){const p=awaiting.get(m.id);if(!p)return;awaiting.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}else if(m.method==='Fetch.requestPaused'){try{const p=new URL(m.params.request.url).pathname;let body,type;if(m.params.resourceType==='Document'){body=html;type='text/html;charset=utf-8';}else if(p.startsWith('/vendor/')){const rel=p.slice(8);assert(/^(prosemirror-(model|state|view|transform)|orderedmap)\/dist\/index\.js$/.test(rel));body=fs.readFileSync(path.join(pmRoot,rel));type='text/javascript';}if(body!==undefined)await cdp('Fetch.fulfillRequest',{requestId:m.params.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:type}],body:Buffer.from(body).toString('base64')});else await cdp('Fetch.failRequest',{requestId:m.params.requestId,errorReason:'BlockedByClient'});}catch(e){errors.push(String(e));}}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);});
await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});

await check('a hidden stale chip after a restart is removed and the route continues',async()=>{
 await fresh();
 // Work's own draft after a restart: the old connector's chip plus its separator space.
 await evaluate('setDoc(['+JSON.stringify(chip(oldId,oldTitle))+'," "])');
 await quiet();
 assert.equal(await evaluate('getComputedStyle(document.querySelector(".ProseMirror span.slash-node")).display'),'none','the chip is hidden on screen');
 const first=await step('open-menu');
 assert.deepEqual(first,{state:'wait',reason:'removing-old-reference'});
 await wait(80);
 assert.deepEqual(await evaluate('refs()'),[],'ProseMirror dropped the stale reference');
 const second=await step('open-menu');
 assert.equal(second.state,'advanced',JSON.stringify(second));
 assert.equal(await evaluate('window.plusClicks'),1);
});
await check('a hidden chip leaves no separator gap beside typed text',async()=>{
 await fresh();
 await evaluate('setDoc(['+JSON.stringify(chip(connectorId,title))+'," ","Hallo"])');
 await quiet();
 assert.equal(await evaluate('text()'),'Hallo','the separator space is gone, typed text stays');
 assert.equal((await evaluate('refs()')).length,1,'the reference itself stays');
 assert.equal(await evaluate('document.querySelector(".ProseMirror").innerText.trim()'),'Hallo');
});
await check('typed text next to a stale chip is never cleared',async()=>{
 await fresh();
 await evaluate('setDoc(['+JSON.stringify(chip(oldId,oldTitle))+'," ","my draft"])');
 await quiet();
 const first=await step('open-menu');
 assert.deepEqual(first,{state:'wait',reason:'removing-old-reference'});
 await wait(80);
 assert.equal(await evaluate('text()'),'my draft');
 assert.deepEqual(await evaluate('refs()'),[]);
});
await check('a connector row in a role-less overlay beside main is found by its hidden text and keeps its label',async()=>{
 await fresh();await quiet();
 const first=await step('open-menu');assert.equal(first.state,'advanced',JSON.stringify(first));
 await evaluate(`document.querySelector('#overlay').innerHTML='<div role=dialog id=menu><button id=conn>Connectors</button></div>'`);await wait(60);
 const opened=await step('open-picker');assert.equal(opened.state,'advanced',JSON.stringify(opened));
 await evaluate(`document.querySelector('#overlay').innerHTML='<div data-state=open id=pick><input placeholder="Filter connectors"><ul><li><button id=row><p><span class=lbl>${title}</span></p></button></li></ul></div>';document.querySelector('#row').onclick=()=>{setDoc([${JSON.stringify(chip(connectorName,title))}," "]);document.querySelector('#overlay').innerHTML='';};`);
 await wait(80);
 assert.equal(await evaluate('getComputedStyle(document.querySelector("#row .lbl")).display'),'inline','the label in a picker beside main stays visible');
 const chosen=await step('choose');assert.equal(chosen.state,'advanced',JSON.stringify(chosen));
 assert.equal((await evaluate('refs()')).length,1,'the picker inserted the reference');
 const after=await step('authorize');assert.equal(after.state,'selected',JSON.stringify(after));
});
assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({passed:true,real_ProseMirror:true,network_requests_to_Mistral:false,checks},null,2)+'\n');console.log('Passed '+checks.length+' real-editor Work attach cases.');
}catch(e){fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({passed:false,error:String(e),checks},null,2)+'\n');throw e;}finally{if(socket)socket.close();if(browser){try{process.kill(-browser.pid,'SIGTERM');}catch{}await wait(150);}fs.rmSync(profile,{recursive:true,force:true});}})().catch(e=>{console.error(e);process.exitCode=1;});
