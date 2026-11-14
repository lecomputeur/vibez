'use strict';
// Exercise the shipped panel in a private headless Chromium profile. No native
// app, desktop window, real account or user workspace is opened by this fixture.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),os=require('node:os'),{spawn}=require('node:child_process'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),dist=path.join(root,'desktop/dist');
const output=path.resolve(process.argv[2]||path.join(root,'artifacts/alpha7-actionable-errors-browser'));
fs.mkdirSync(output,{recursive:true});
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'vibez-errors-browser-'));
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let browser,socket,server,id=0;const awaiting=new Map(),errors=[],checks=[],screenshots=[];
const mime={'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.json':'application/json'};
function cdp(method,params={}){return new Promise((resolve,reject)=>{const request=++id;awaiting.set(request,{resolve,reject});socket.send(JSON.stringify({id:request,method,params}));});}
async function evaluate(expression){const result=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;}
const fixture=String.raw`
window.__fixtureCalls=[];window.__fixtureEvents={};
window.__TAURI__={core:{invoke:async(name,args)=>{window.__fixtureCalls.push({name,args});
 if(name==='language_get')return {language:'en',resolved:'en',site_locale:'en',pending:false,revision:1};
 if(name==='app_info')return {version:'4.0.0-alpha.10'};
 if(name==='web_choose_folder')return window.__fixtureChoose?window.__fixtureChoose():null;return true;
}},event:{listen:async(name,callback)=>{(window.__fixtureEvents[name]??=[]).push(callback);return ()=>{};}}};
`;
const project='cace260d-d95d-4859-b45b-f56f185f15da';
function show(code,status='error',extra={}){
 const web={type:'web_connector',project:{id:project,name:'Example project'},folder:'/fixtures/Example folder',workspace_binding:'a'.repeat(64),import_binding:'b'.repeat(64),enabled:false,tunnel_status:'running',pending:[],activity:[],recent_activity:[],...extra};
 const automatic={project_id:project,status,error_code:code,...(extra.manually_paused?{pause_reason:'manual'}:{})};
 return evaluate('actionError="";renderWeb('+JSON.stringify(web)+');auto='+JSON.stringify(automatic)+';renderAutomatic();true');
}
async function inspect(){return evaluate(`(()=>{const d=document.getElementById('connection-details'),b=document.getElementById('auto-connect');return {help:d.textContent,helpVisible:!d.hidden&&getComputedStyle(d).display!=='none',button:b.textContent,buttonVisible:!b.hidden,options:document.getElementById('files-options').open,advanced:document.getElementById('advanced-setup').open,focused:document.activeElement?.id,overflow:document.documentElement.scrollWidth>innerWidth+1};})()`);}
async function screenshot(name){const image=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(output,name),Buffer.from(image.data,'base64'));screenshots.push(name);}
(async()=>{
 try{
  server=http.createServer((req,res)=>{const requested=decodeURIComponent(new URL(req.url,'http://localhost').pathname);const file=path.resolve(dist,'.'+(requested==='/'?'/panel.html':requested));if(!file.startsWith(dist+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const port=server.address().port;
  let stderr='';browser=spawn('/usr/bin/chromium',['--headless=new','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run','--no-default-browser-check','--password-store=basic','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:['ignore','ignore','pipe'],detached:true});
  browser.stderr.on('data',chunk=>{stderr=(stderr+chunk).slice(-20000);});
  let endpoint;
  for(let n=0;n<200;n++){if(browser.exitCode!==null)throw new Error('Headless browser exited: '+stderr);endpoint=stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/)?.[1];if(endpoint)break;await wait(50);}
  assert.ok(endpoint,'Missing private debugging endpoint');
  const origin=new URL(endpoint);const targets=await fetch('http://127.0.0.1:'+origin.port+'/json/list').then(r=>r.json());
  const target=targets.find(t=>t.type==='page');assert.ok(target);
  socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const pending=awaiting.get(message.id);if(!pending)return;awaiting.delete(message.id);if(message.error)pending.reject(new Error(JSON.stringify(message.error)));else pending.resolve(message.result);}else if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);});
  await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Page.addScriptToEvaluateOnNewDocument',{source:fixture});
  await cdp('Emulation.setDeviceMetricsOverride',{width:400,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp('Page.navigate',{url:'http://127.0.0.1:'+port+'/panel.html'});
  let ready=false;for(let n=0;n<100;n++){ready=await evaluate('typeof renderAutomatic==="function"&&window.vibezLanguage?.state().resolved==="en"&&Boolean(document.getElementById("panel-version").textContent)');if(ready)break;await wait(50);}assert.ok(ready,'Panel did not finish its local mock boot');
  const catalog=JSON.parse(fs.readFileSync(path.join(root,'standalone-ui/language-extra.json'),'utf8'));let revision=1;
  for(const locale of Object.keys(catalog)){
   await evaluate('window.vibezLanguage.apply('+JSON.stringify({language:locale,resolved:locale,site_locale:'en',pending:false,revision:++revision})+');true');
   for(const code of ['connector_auth','workspace_unavailable','sign_in','connector_sync','connector_cleanup']){
    await show(code);const view=await inspect(),expected={connector_auth:'connectionFilesAuthHelp',workspace_unavailable:'connectionFolderHelp',sign_in:'auto_sign_in',connector_sync:'connectionSyncHelp',connector_cleanup:'connectionCleanupHelp'}[code];
    assert.equal(view.help,catalog[locale][expected]||catalog.en[expected],locale+':'+code);assert.equal(view.helpVisible,true);assert.equal(view.buttonVisible,true);assert.equal(view.options,false);assert.equal(view.overflow,false,locale+':'+code);checks.push({locale,code,passed:true});
   }
  }
  for(const [locale,code,file]of [['en','connector_auth','connector-auth-en.png'],['nl','workspace_unavailable','folder-unavailable-nl.png'],['de','sign_in','sign-in-de.png'],['fr','permission','permission-fr.png']]){
   await evaluate('window.vibezLanguage.apply('+JSON.stringify({language:locale,resolved:locale,site_locale:'en',pending:false,revision:++revision})+');true');await show(code);await screenshot(file);
  }
  await evaluate('document.getElementById("auto-connect").click();true');let view=await inspect();assert.equal(view.options,true);assert.equal(view.advanced,true);assert.equal(view.focused,'studio-api-key');checks.push({case:'real DOM permission button survives bubbling and focuses settings',passed:true});
  await evaluate('document.getElementById("files-options").open=false;window.vibezLanguage.apply('+JSON.stringify({language:'en',resolved:'en',site_locale:'en',pending:false,revision:++revision})+');true');
  await show('workspace_unavailable');await evaluate('document.getElementById("auto-connect").click();true');
  assert.ok((await evaluate('window.__fixtureCalls')).some(c=>c.name==='web_choose_folder'));checks.push({case:'real DOM folder recovery opens chooser',passed:true});
  await show('connector_auth');await evaluate('document.getElementById("auto-connect").click();true');
  assert.ok((await evaluate('window.__fixtureCalls')).some(c=>c.name==='web_command'&&c.args.payload.action==='web_connect'));checks.push({case:'real DOM file auth recovery uses existing connect path',passed:true});
  await show(null,'paused',{manually_paused:true});view=await inspect();assert.equal(view.helpVisible,false);await screenshot('paused-en.png');checks.push({case:'manual pause has no error callout or automatic resume',passed:true});

  await show(null,'connected',{enabled:true});await evaluate('auto.connector_cleanup_pending=2;renderAutomatic();true');
  view=await inspect();assert.equal(view.help,catalog.en.connectionCleanupHelp);assert.equal(view.buttonVisible,true);checks.push({case:'working connection retains visible retry for safely-pausing old connectors',passed:true});
  await evaluate('auto.connector_cleanup_pending=0;renderAutomatic();true');assert.equal((await inspect()).helpVisible,false);checks.push({case:'successful cleanup removes recovery guidance',passed:true});
  for(const [locale,format]of [['en','.odt'],['nl','.docx'],['fr','.xlsx'],['pl','.pptx']]){
   await evaluate('window.vibezLanguage.apply('+JSON.stringify({language:locale,resolved:locale,site_locale:'en',pending:false,revision:++revision})+');true');
   await show(null,'connected',{enabled:true,pending:[{id:'office-fixture',project_id:project,project_name:'Fixture',path:'draft'+format,before:'',after:'<script>Private fixture</script>',new:true,document_format:format}]});
   const result=await evaluate(`(()=>{const card=document.querySelector('#web-proposals .approval');return{note:card.querySelector('.approval-head p').textContent,title:card.querySelector('h3').textContent,hasMarkup:Boolean(card.querySelector('script')),text:card.querySelectorAll('pre')[1].textContent,buttons:card.querySelectorAll('button').length};})()`);
   assert.equal(result.note,catalog[locale].documentProposalNote.replace('{format}',format.slice(1).toUpperCase()));assert.equal(result.title,'draft'+format);assert.equal(result.hasMarkup,false);assert.equal(result.buttons,2);assert.equal(result.text,'<script>Private fixture</script>');checks.push({case:'Office creation review remains explicit, inert and localized: '+locale,passed:true});
  }
  await evaluate('window.vibezLanguage.apply('+JSON.stringify({language:'en',resolved:'en',site_locale:'en',pending:false,revision:++revision})+');true');
  const folders=[{id:'1'.repeat(32),path:'/fixtures/CityTripXL'},{id:'2'.repeat(32),path:'/fixtures/Travel documents'}];
  const linked={folders,folder:folders[0].path,target_folder_id:folders[0].id};
  const tick=()=>wait(30);
  async function click(selector){await evaluate('document.querySelector('+JSON.stringify(selector)+').click();true');await tick();}
  async function lastCall(){return evaluate('window.__fixtureCalls.at(-1)');}
  await show(null,'paused',{...linked,folders:[folders[0]]});
  assert.equal(await evaluate('document.querySelectorAll(".linked-folder").length'),1);
  assert.equal(await evaluate('document.querySelectorAll("#linked-folders input[type=radio]").length'),0);
  assert.equal(await evaluate('document.getElementById("workspace-target")'),null);
  assert.equal(await evaluate('document.getElementById("folder-summary").hidden'),true);
  assert.equal(await evaluate('document.getElementById("workspace-destination").hidden'),true);
  checks.push({case:'one folder appears once without a duplicate destination picker',passed:true});
  await show(null,'connected',{...linked,enabled:true});
  assert.equal(await evaluate('document.getElementById("web-pause").hidden'),false);
  assert.equal(await evaluate('document.getElementById("auto-connect").hidden'),true);
  await click('#web-pause');assert.equal((await lastCall()).args.payload.allow,false);
  checks.push({case:'connected status has one visible pause action',passed:true});
  await show(null,'paused',linked);
  await click('.linked-folder:nth-child(2) input');
  let called=await lastCall();assert.equal(called.args.payload.action,'web_select_folder');assert.equal(called.args.payload.folder_id,folders[1].id);assert.equal(called.args.payload.workspace_binding,'a'.repeat(64));
  await show(null,'paused',{...linked,folder:folders[1].path,target_folder_id:folders[1].id});
  assert.equal(await evaluate('document.querySelector(".linked-folder:nth-child(2) input").checked'),true);
  assert.equal(await evaluate('document.getElementById("files-section-heading").textContent'),'Travel documents');
  checks.push({case:'direct destination selection updates imports and the displayed destination',passed:true});
  await click('.linked-folder:first-child .folder-actions button');called=await lastCall();
  assert.equal(called.name,'project_open_folder');assert.equal(called.args.folderId,folders[0].id);assert.equal(called.args.binding,'b'.repeat(64));
  assert.equal(await evaluate('document.querySelector(".linked-folder:nth-child(2) input").checked'),true);
  checks.push({case:'opening a nonselected folder passes only its ID and does not change destination',passed:true});
  await evaluate('window.__fixtureChoose=async()=>"/fixtures/Replacement";true');
  await click('.linked-folder:first-child summary');await click('.linked-folder:first-child .linked-folder-menu button:first-child');called=await lastCall();
  assert.equal(called.args.payload.action,'web_link');assert.equal(called.args.payload.folder_id,folders[0].id);assert.equal(called.args.payload.path,'/fixtures/Replacement');
  checks.push({case:'each folder menu changes that folder, even when another destination is selected',passed:true});
  await show(null,'paused',linked);await click('.linked-folder:nth-child(2) summary');await click('.linked-folder:nth-child(2) .linked-folder-menu button:last-child');called=await lastCall();
  assert.equal(called.args.payload.action,'web_remove_folder');assert.equal(called.args.payload.folder_id,folders[1].id);
  checks.push({case:'unlink addresses the requested folder without deleting its files',passed:true});
  await show(null,'paused',linked);await evaluate('window.__fixtureChoose=async()=>"/fixtures/Extra";true');await click('#workspace-add');called=await lastCall();assert.equal(called.args.payload.action,'web_add_folder');
  await show(null,'paused',linked);await evaluate('window.__fixtureChoose=()=>new Promise(resolve=>window.__resolveChooser=resolve);true');await click('#workspace-add');
  const before=await evaluate('window.__fixtureCalls.length');
  await show(null,'paused',{...linked,project:{id:'chat-11111111-2222-3333-4444-555555555555',kind:'conversation',name:'Other chat'}});
  await evaluate('window.__resolveChooser("/fixtures/Must not link");true');await tick();
  assert.equal(await evaluate('window.__fixtureCalls.length'),before);
  checks.push({case:'a project switch during folder selection cannot attach to the wrong project or chat',passed:true});
  await evaluate('window.__fixtureChoose=async()=>null;true');
  for(const locale of Object.keys(catalog)){
   await evaluate('window.vibezLanguage.apply('+JSON.stringify({language:locale,resolved:locale,site_locale:'en',pending:false,revision:++revision})+');true');
   for(const width of [320,400]){
    await cdp('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
    await show(null,'connected',{...linked,enabled:true});
    assert.equal((await inspect()).overflow,false,'folder overflow: '+locale+':'+width);
    await click('.linked-folder:nth-child(2) summary');
    const bounds=await evaluate('(()=>{const r=document.querySelector(".linked-folder:nth-child(2) .linked-folder-menu").getBoundingClientRect();return {left:r.left,right:r.right,width:innerWidth}})()');
    assert.ok(bounds.left>=0&&bounds.right<=bounds.width,'menu overflow: '+locale+':'+width);
    if(width===400&&['nl','fr'].includes(locale))await screenshot('folders-two-'+locale+'.png');
    checks.push({case:'folder layout and menu fit '+width+'px in '+locale,passed:true});
   }
  }
  await cdp('Emulation.setDeviceMetricsOverride',{width:400,height:900,deviceScaleFactor:1,mobile:false});
  await evaluate('window.vibezLanguage.apply('+JSON.stringify({language:'nl',resolved:'nl',site_locale:'nl',pending:false,revision:++revision})+');true');
  await show(null,'paused',{...linked,folders:[folders[0]],manually_paused:true});await screenshot('folders-one-nl.png');
  assert.equal(errors.length,0,JSON.stringify(errors));
  const report={passed:true,checks:checks.length,languages:Object.keys(catalog).length,physical_windows_opened:false,native_app_or_account_used:false,private_profile:true,screenshots,details:checks};fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({passed:true,checks:checks.length,languages:report.languages,output}));
 }catch(error){fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({passed:false,error:String(error),errors,checks},null,2)+'\n');console.error(error);process.exitCode=1;}
 finally{if(socket)socket.close();if(browser&&browser.exitCode===null){process.kill(-browser.pid,'SIGTERM');await new Promise(resolve=>{browser.once('exit',resolve);setTimeout(resolve,2000).unref();});if(browser.exitCode===null)process.kill(-browser.pid,'SIGKILL');}if(server)await new Promise(resolve=>server.close(resolve));fs.rmSync(profile,{recursive:true,force:true,maxRetries:20,retryDelay:100});}
})();
