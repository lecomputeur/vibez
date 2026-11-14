'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
const {connectionFeedback}=require('../../standalone-ui/connection-feedback.js');
const messages=JSON.parse(fs.readFileSync(path.join(root,'standalone-ui/language-extra.json'),'utf8'));
const restore=['connector_sync','connector_cleanup','readiness_auth','connector_auth','connector_auth_schema','authentication_unconfirmed','execution','readiness','server_unreachable','network','tunnel','tools','not_found','invalid_response','invalid_request','mistral_error'];

test('file-auth and reachability failures restore the connection without signing the account out',()=>{
 for(const error_code of restore){
  const view=connectionFeedback({automatic:{status:'error',error_code},linked:true});
  assert.equal(view.action,'connect',error_code);assert.equal(view.buttonKey,'connectionRestore',error_code);
  assert.ok(messages.en[view.messageKey],error_code);assert.notEqual(view.messageKey,'auto_sign_in',error_code);
 }
 const expiry=connectionFeedback({automatic:{status:'error',error_code:'sign_in'},linked:true});
 assert.equal(expiry.messageKey,'auto_sign_in');assert.equal(expiry.buttonKey,'connectionSignIn');
 // An HTTP 401 alone may be a connector credential failure, not account expiry.
 assert.notEqual(connectionFeedback({automatic:{status:'error',http_status:401},linked:true}).buttonKey,'connectionSignIn');
});

test('an unavailable workspace checks the folder, while scope and ownership errors open settings',()=>{
 const folder=connectionFeedback({automatic:{status:'error',error_code:'workspace_unavailable'},linked:true});
 assert.equal(folder.action,'folder');assert.equal(folder.buttonKey,'connectionCheckFolder');
 for(const code of ['permission','ownership'])assert.equal(connectionFeedback({automatic:{status:'error',error_code:code},linked:true}).action,'settings');
 const rate=connectionFeedback({automatic:{status:'error',error_code:'rate_limit'},linked:true});
 assert.equal(rate.messageKey,'connectionRateLimitHelp');assert.equal(rate.buttonKey,'filesRetry');
});

test('normal connection states and intentional pauses do not show recovery errors or resume anything',()=>{
 for(const status of ['idle','starting','authorizing','connecting','registering','connected','paused','cancelled']){
  const view=connectionFeedback({automatic:{status,pause_reason:'manual'},linked:true});
  assert.equal(view.messageKey,null,status);assert.equal(view.buttonKey,null,status);
 }
 const expired=connectionFeedback({automatic:{status:'paused',pause_reason:'sign_in'},linked:true});
 assert.equal(expired.buttonKey,'connectionSignIn');assert.equal(expired.messageKey,null);
});

test('encoded native errors retain stable actions without reflecting provider text or secrets',()=>{
 const secret='DO_NOT_DISPLAY_PRIVATE_CREDENTIAL';
 const encoded=JSON.stringify({code:'engine_stopped',message:'De verbinding is gestopt.',message_en:secret});
 const stopped=connectionFeedback({actionError:encoded,linked:true});
 assert.equal(stopped.action,'none');assert.equal(stopped.messageKey,'engineStopped');
 for(const actionError of [secret,{error_code:'connector_auth',provider_message:secret},'Kopiëren is niet gelukt.',{error_code:'__proto__',message:secret}]){
  const view=connectionFeedback({automatic:{status:'error'},actionError,linked:true});
  assert.ok(!JSON.stringify(view).includes(secret));assert.ok(!JSON.stringify(view).includes('Kopiëren'));
 }
});

test('all recovery labels have local or explicit English text across every advertised language',()=>{
 const codes=[...restore,'sign_in','permission','ownership','workspace_unavailable','rate_limit'];
 for(const [locale,dictionary]of Object.entries(messages)){
  for(const error_code of codes){
   const view=connectionFeedback({automatic:{status:'error',error_code},linked:true});
   for(const key of [view.messageKey,view.buttonKey].filter(Boolean)){
    const value=dictionary[key]||messages.en[key];assert.ok(value&&value!==key,locale+':'+key);
    if(locale!=='nl'&&key.startsWith('connection'))assert.notEqual(value,messages.nl[key],locale+':'+key);
   }
  }
 }
 assert.equal(Object.keys(messages).length,33);
});

function panel(){
 const nodes=new Map(),calls=[];let locale='en';
 function node(id){if(!nodes.has(id))nodes.set(id,{dataset:{},hidden:true,disabled:false,open:false,value:'',textContent:'',events:{},focus(){this.focused=true;},addEventListener(type,fn){(this.events[type]??=[]).push(fn);},removeAttribute(){},setAttribute(k,v){this[k]=v;},querySelector(){return {focus(){}};},contains(){return false;},replaceChildren(){},append(){}});return nodes.get(id);}
 const language={t:key=>messages[locale]?.[key]||messages.en[key]||key,errorText:(error,key)=>error?messages[locale]?.[key]||messages.en[key]||key:'',ready:()=>new Promise(()=>{}),onChange(){},state:()=>({resolved:locale})};
 const document={getElementById:node,addEventListener(){},documentElement:{},body:{},createElement:()=>node('generated')};
 const context={window:{vibezLanguage:language,vibezConnectionFeedback:{connectionFeedback},__TAURI__:{core:{invoke:async(name,args)=>{calls.push({name,args});return name==='web_choose_folder'?null:undefined;}},event:{listen:async()=>{}}}},document,console,Intl,Date};
 vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'standalone-ui/panel.js'),'utf8'),context);
 const render=(automatic,extra={})=>{const state={project:{id:'cace260d-d95d-4859-b45b-f56f185f15da',name:'Fixture'},folder:'/fixtures/Main',enabled:false,tunnel_status:'running',...extra};vm.runInContext('webState='+JSON.stringify(state)+';auto='+JSON.stringify(automatic)+';actionError="";renderAutomatic();',context);};
 const click=async id=>{for(const fn of node(id).events.click||[])await fn({});};
 return {node,calls,render,click,setLocale:value=>{locale=value;vm.runInContext('renderAutomatic()',context);}};
}

test('the actual panel shows recovery guidance outside the options menu and uses one existing action',async()=>{
 const p=panel();p.render({status:'error',error_code:'connector_auth'});
 assert.equal(p.node('connection-details').hidden,false);assert.equal(p.node('connection-details').textContent,messages.en.connectionFilesAuthHelp);
 assert.equal(p.node('auto-connect').textContent,messages.en.connectionRestore);assert.equal(p.node('files-options').open,false);
 await p.click('auto-connect');assert.equal(p.calls.at(-1).name,'web_command');assert.equal(p.calls.at(-1).args.payload.action,'web_connect');
 assert.ok(!p.calls.some(c=>String(c.args?.payload?.action).includes('logout')));
 const html=fs.readFileSync(path.join(root,'standalone-ui/panel.html'),'utf8');
 assert.ok(html.indexOf('id="connection-details"')>html.indexOf('id="auto-status"'));
});

test('the actual panel opens account settings only on request and checks unavailable folders without unlinking',async()=>{
 const p=panel();p.render({status:'error',error_code:'permission'});
 assert.equal(p.node('files-options').open,false);assert.equal(p.node('advanced-setup').open,false);
 await p.click('auto-connect');assert.equal(p.node('files-options').open,true);assert.equal(p.node('advanced-setup').open,true);assert.equal(p.node('studio-api-key').focused,true);assert.equal(p.calls.length,0);
 p.render({status:'error',error_code:'workspace_unavailable'});await p.click('auto-connect');
 assert.equal(p.calls.at(-1).name,'web_choose_folder');assert.equal(p.calls.at(-1).args.create,false);
 assert.ok(!p.calls.some(c=>c.args?.payload?.action==='web_unlink'));
});

test('visible recovery guidance and button follow live language changes; a manual pause stays quiet',()=>{
 const p=panel();p.render({status:'error',error_code:'execution'});
 for(const locale of ['nl','de','fr','missing-locale']){
  p.setLocale(locale);const catalog=messages[locale]||messages.en;
  assert.equal(p.node('connection-details').textContent,catalog.connectionReachabilityHelp);assert.equal(p.node('auto-connect').textContent,catalog.connectionRestore);
 }
 p.render({status:'paused',pause_reason:'manual'},{manually_paused:true});
 assert.equal(p.node('connection-details').hidden,true);assert.equal(p.node('auto-status').textContent,messages.en.filesPausedByYou);assert.equal(p.calls.length,0);
});


test('provider propagation uses connection recovery without asking for another account sign-in',()=>{
 const value=connectionFeedback({automatic:{status:'error',error_code:'connector_sync'},linked:true});
 assert.equal(value.messageKey,'connectionSyncHelp');assert.equal(value.buttonKey,'connectionRestore');assert.equal(value.action,'connect');
});
test('failed cleanup preserves the working connection and exposes one retry without claiming all scopes were paused',()=>{
 for(const connector_cleanup_pending of [1,3]){
  const value=connectionFeedback({automatic:{status:'connected',connector_cleanup_pending},linked:true});
  assert.equal(value.messageKey,'connectionCleanupHelp');assert.equal(value.action,'connect');assert.equal(value.buttonKey,'connectionRestore');
 }
 for(const connector_cleanup_pending of [undefined,0,-1,'1',1.5])assert.equal(connectionFeedback({automatic:{status:'connected',connector_cleanup_pending},linked:true}).messageKey,null);
 assert.equal(connectionFeedback({automatic:{status:'paused',pause_reason:'manual',connector_cleanup_pending:1},linked:true}).messageKey,null);
});
test('new Office proposal help states creation and never substitutes executable markup or changes the selected language',()=>{
 const p=panel();
 for(const [locale,format]of [['en','.odt'],['nl','.docx'],['fr','.xlsx'],['pl','.odp']]){
  p.setLocale(locale);
  // Reuse the actual panel helper with only invented proposal metadata.
  const source=fs.readFileSync(path.join(root,'standalone-ui/panel.js'),'utf8');
  const line=source.split('\n').find(x=>x.startsWith('function proposalHelp('));
  const context={t:key=>messages[locale]?.[key]||messages.en[key],proposal:{new:true,document_format:format}};
  vm.createContext(context);vm.runInContext(line,context);
  assert.equal(vm.runInContext('proposalHelp(proposal)',context),messages[locale].documentProposalNote.replace('{format}',format.slice(1).toUpperCase()));
  context.proposal.document_format='<script>';assert.equal(vm.runInContext('proposalHelp(proposal)',context),messages[locale].proposalNote);
 }
});

test('a failed Work setup names the failed part and offers to restore the connection',()=>{
 const setup=connectionFeedback({automatic:{status:'error',error_code:'work_setup_failed',work_failure:'setup'},linked:true});
 assert.equal(setup.messageKey,'connectionWorkSetupHelp');assert.equal(setup.buttonKey,'connectionRestore');assert.equal(setup.action,'connect');
 const verify=connectionFeedback({automatic:{status:'error',error_code:'work_setup_failed',work_failure:'verify'},linked:true});
 assert.equal(verify.messageKey,'connectionWorkVerifyHelp');
 // Without a known part, or with an unexpected value, the setup message is shown.
 for(const work_failure of [undefined,'<b>other</b>'])assert.equal(connectionFeedback({automatic:{status:'error',error_code:'work_setup_failed',work_failure},linked:true}).messageKey,'connectionWorkSetupHelp');
 for(const [lang,values] of Object.entries(messages))for(const key of ['connectionWorkSetupHelp','connectionWorkVerifyHelp'])assert.ok(values[key],lang+' '+key);
});
test('a tunnel that never started says which side failed, in every language, and shows the retry while it runs',()=>{
 for(const [error_code,key] of [['tunnel_cloudflare','auto_tunnel_cloudflare'],['tunnel_network','auto_tunnel_network']]){
  const view=connectionFeedback({automatic:{status:'error',error_code},linked:true});
  assert.equal(view.messageKey,key);assert.equal(view.action,'connect');assert.equal(view.buttonKey,'connectionRestore');
 }
 assert.match(messages.en.auto_tunnel_cloudflare,/Cloudflare/);assert.doesNotMatch(messages.en.auto_tunnel_network,/Cloudflare/);
 for(const [language,catalog] of Object.entries(messages))for(const key of ['auto_tunnel_cloudflare','auto_tunnel_network','phaseTunnelRetry']){
  assert.equal(typeof catalog[key],'string',language+' '+key);assert.ok(catalog[key].length>10,language+' '+key);
 }
 for(const language of Object.keys(messages))assert.match(messages[language].auto_tunnel_cloudflare,/Cloudflare/,language);
 const panel=fs.readFileSync(path.join(root,'standalone-ui/panel.js'),'utf8');
 assert.match(panel,/tunnel_retry:'phaseTunnelRetry'/);
});
