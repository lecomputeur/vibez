'use strict';
// The Advanced tab beside Files: remembered order and last tab, Files first
// on a fresh start and after a new folder link, Environment, project rules,
// tone and context and Changes as its content, and the diagnostics dialog
// reached from Settings and from a failed connection.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
const {createPanelTabs,normalizeOrder,normalizePrefs}=require(path.join(root,'standalone-ui/panel-tabs.js'));
const messages=require(path.join(root,'standalone-ui/language-extra.json'));
const {connectionFeedback}=require(path.join(root,'standalone-ui/connection-feedback.js'));

function model(options={}){const persisted=[],remembered=[];const m=createPanelTabs({persist:p=>persisted.push(p),remember:n=>remembered.push(n),...options});return {m,persisted,remembered};}

test('a fresh installation has Files and Advanced, Files open, and stored names of the former Project tab are dropped',()=>{
 const {m,persisted}=model();
 assert.deepEqual(m.state(),{order:['files','advanced'],current:'files',tab_order:['files','advanced']});
 assert.equal(persisted.length,0);
 assert.deepEqual(normalizePrefs(undefined),{tab_order:['files','advanced']});
 assert.deepEqual(normalizePrefs({advanced:false,tab_order:['project','bogus','project']}),{tab_order:['files','advanced']},'the former switch is ignored');
 assert.deepEqual(normalizeOrder(['advanced']),['advanced','files']);assert.deepEqual(normalizeOrder(['project','advanced','files']),['advanced','files']);
});

test('selecting remembers the viewer’s choice and unknown names fall back to the first tab',()=>{
 const {m,persisted,remembered}=model();
 assert.equal(m.select('advanced'),'advanced');assert.deepEqual(remembered,['advanced']);
 assert.equal(m.select('project'),'files','the former Project tab falls back to the first tab');assert.deepEqual(remembered,['advanced','files'],'the fallback is remembered, not the unknown name');
 assert.equal(m.select('advanced',true),'advanced');assert.deepEqual(remembered,['advanced','files'],'an automatic selection is not remembered');
 assert.equal(persisted.length,0,'selecting stores no installation preference');
});

test('drag order is normalized, persisted and reset on request',()=>{
 const {m,persisted}=model();
 m.move('advanced','files',false);
 assert.deepEqual(m.state().order,['advanced','files']);assert.deepEqual(persisted.at(-1),{tab_order:['advanced','files']});
 m.move('files','project',true);assert.deepEqual(m.state().order,['advanced','files'],'dropping on an unknown tab changes nothing');
 m.move('files','files');assert.equal(persisted.length,1,'dropping a tab on itself changes nothing');
 m.resetOrder();assert.deepEqual(m.state().tab_order,['files','advanced']);assert.deepEqual(persisted.at(-1),{tab_order:['files','advanced']});
 m.resetOrder();assert.equal(persisted.length,2);
 assert.deepEqual(m.reorder(['bogus','project']).tab_order,['files','advanced']);
});

test('a start restores the viewer’s last tab, Files when nothing valid is stored, and keeps the stored order',()=>{
 for(const savedTab of [null,undefined,'bogus','project']){
  const {m}=model({prefs:{advanced:false,tab_order:['advanced','files','project']},savedTab});
  assert.deepEqual(m.state().order,['advanced','files']);assert.equal(m.state().current,'files',String(savedTab));
 }
 assert.equal(model({savedTab:'advanced'}).m.state().current,'advanced','Advanced is an ordinary tab and comes back like Project used to');
 // Preferences arrive after the engine answers; applying them keeps the open tab.
 const {m}=model({savedTab:'advanced'});m.apply({advanced:false,tab_order:['advanced','project','files']});
 assert.equal(m.state().current,'advanced');assert.deepEqual(m.state().order,['advanced','files']);
});

test('a new folder link opens Files whatever the order, without recording a viewer choice',()=>{
 const {m,remembered}=model({prefs:{tab_order:['advanced','files']}});
 m.select('advanced');assert.deepEqual(remembered,['advanced']);
 assert.equal(m.folderLinked(),'files');assert.equal(m.state().current,'files');assert.deepEqual(remembered,['advanced']);
 m.select('advanced');assert.equal(m.folderLinked(),'files');
});

// A small DOM for the real panel.js: enough for tab buttons, sections and the settings view.
function dom(){
 const byId=new Map();
 class Node{
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.parentNode=null;this.dataset={};this.attrs={};this.hidden=false;this.disabled=false;this.checked=false;this.open=false;this.value='';this.text='';this.listeners={};this.style={};}
  get id(){return this.attrs.id||'';}set id(v){this.attrs.id=v;byId.set(v,this);}
  get textContent(){return this.text+this.children.map(c=>c.textContent).join('');}set textContent(v){this.children=[];this.text=String(v);}
  get firstChild(){return this.children[0]||null;}
  setAttribute(k,v){if(k==='id')this.id=String(v);else this.attrs[k]=String(v);}getAttribute(k){return k==='id'?this.id:this.attrs[k]??null;}removeAttribute(k){delete this.attrs[k];}
  append(...nodes){for(const n of nodes){if(n.parentNode)n.parentNode.children.splice(n.parentNode.children.indexOf(n),1);n.parentNode=this;this.children.push(n);}}
  before(...nodes){const parent=this.parentNode;for(const n of nodes){if(n.parentNode)n.parentNode.children.splice(n.parentNode.children.indexOf(n),1);n.parentNode=parent;parent.children.splice(parent.children.indexOf(this),0,n);}}
  remove(){if(this.parentNode){this.parentNode.children.splice(this.parentNode.children.indexOf(this),1);this.parentNode=null;}}
  replaceChildren(...nodes){for(const c of this.children)c.parentNode=null;this.children=[];this.append(...nodes);}
  contains(n){for(let x=n;x;x=x.parentNode)if(x===this)return true;return false;}
  querySelector(){return new Node('div');}querySelectorAll(){return [];}
  focus(){this.focused=true;}
  showModal(){this.open=true;}close(){this.open=false;}
  addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
  dispatch(type,event={}){for(const fn of this.listeners[type]||[])fn({type,target:this,preventDefault(){},stopPropagation(){},dataTransfer:{setData(){}},...event});}
 }
 const html=fs.readFileSync(path.join(root,'standalone-ui/panel.html'),'utf8');
 const body=new Node('body');
 // Every element with an id exists; nesting is reconstructed only for the tab strip and its row.
 for(const match of html.matchAll(/<(\w+)[^>]*\sid="([^"]+)"[^>]*?(?:\shidden)?[^>]*>/g)){const node=new Node(match[1]);node.id=match[2];node.hidden=/\shidden[\s>]/.test(match[0]);body.append(node);}
 byId.get('panel-tabs-row').append(byId.get('panel-tabs'));byId.get('panel-tabs').append(byId.get('tab-files-button'),byId.get('tab-advanced-button'));
 byId.get('auto-open-login').before(byId.get('error-details'));
 for(const id of ['tab-files','tab-advanced'])byId.get(id).setAttribute('data-active',id==='tab-files'?'true':'false');
 const document={getElementById:id=>byId.get(id)||null,createElement:tag=>new Node(tag),addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);},listeners:{},body:{},documentElement:{},querySelector:()=>new Node('option')};
 return {document,byId,body};
}
function panel({prefs,storage={},answers={},clock}={}){
 const {document,byId}=dom(),calls=[],listeners={};let locale='en';
 const language={t:key=>messages[locale]?.[key]||messages.en[key]||key,errorText:(e,key)=>e?messages.en[key]||key:'',ready:async()=>{},onChange(){},state:()=>({resolved:'en'})};
 const invoke=async(name,args)=>{calls.push({name,args});if(answers[name])return answers[name](args);if(name==='panel_prefs_get')return prefs;if(name==='app_info')return {version:'test'};return undefined;};
 const context={window:{vibezLanguage:language,vibezConnectionFeedback:{connectionFeedback},VIBEZ_TRANSLATIONS:{options:[]},__TAURI__:{core:{invoke},event:{listen:async(name,fn)=>{(listeners[name]??=[]).push(fn);}}}},document,console,Intl,Date:clock?clock.Date:Date,setTimeout:clock?clock.setTimeout:setTimeout,clearTimeout,
  localStorage:{getItem:k=>storage[k]??null,setItem:(k,v)=>{storage[k]=v;}}};
 context.window.window=context.window;
 vm.createContext(context);
 vm.runInContext(fs.readFileSync(path.join(root,'standalone-ui/panel-tabs.js'),'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(root,'standalone-ui/panel.js'),'utf8'),context);
 const strip=()=>byId.get('panel-tabs').children.map(b=>b.dataset.tab);
 const run=code=>vm.runInContext(code,context);
 const state=()=>vm.runInContext('panelTabsView.state()',context);
 const renderWeb=extra=>{vm.runInContext('renderWeb('+JSON.stringify({type:'web_connector',project:{id:'cace260d-d95d-4859-b45b-f56f185f15da',name:'Fixture'},folder:null,folders:[],pending:[],activity:[],recent_activity:[],tunnel_status:'stopped',...extra})+')',context);};
 const settle=()=>new Promise(resolve=>setTimeout(resolve,10));
 return {byId,calls,listeners,strip,state,run,renderWeb,settle,storage,emit(name,payload){for(const fn of listeners[name]||[])fn({payload});}};
}

test('the real panel always shows Files and Advanced, opens Files first and shows Advanced content only with a project',async()=>{
 const p=panel({prefs:{advanced:false,tab_order:['files','project','advanced']}});await p.settle();
 assert.deepEqual(p.strip(),['files','advanced']);assert.equal(p.state().current,'files');
 assert.equal(p.byId.get('tab-files-button').getAttribute('aria-selected'),'true');assert.equal(p.byId.get('tab-advanced-button').getAttribute('aria-selected'),'false');
 assert.equal(p.byId.get('advanced-environment').hidden,true,'no project, no environment');
 p.renderWeb({folder:'/fixtures/Main',workspace_binding:'b1'});
 assert.equal(p.byId.get('panel-tabs-row').hidden,false);assert.equal(p.byId.get('advanced-environment').hidden,false);assert.equal(p.byId.get('advanced-changes').hidden,false);
 assert.equal(p.byId.get('tab-advanced').getAttribute('data-active'),'false');assert.equal(p.byId.get('tab-files').getAttribute('data-active'),'true');
 p.byId.get('tab-advanced-button').dispatch('click');
 assert.equal(p.state().current,'advanced');assert.equal(p.byId.get('tab-advanced').getAttribute('data-active'),'true');assert.equal(p.byId.get('tab-advanced-button').tabIndex,0);assert.equal(p.byId.get('tab-files-button').tabIndex,-1);
 assert.equal(p.byId.get('error-details').parentNode,p.byId.get('auto-open-login').parentNode,'technical details stay with the connection status');
 assert.ok(!p.calls.some(c=>c.args?.payload?.action==='web_diagnostics'),'the tab itself never asks for diagnostics');
 assert.ok(p.calls.some(c=>c.name==='panel_prefs_get'));assert.ok(!p.calls.some(c=>c.name==='panel_prefs_set'),'nothing is stored until the order changes');
 assert.equal(p.storage['vibez-panel-tab-v2'],'advanced');
});

test('stored order and last tab are restored, an old Project choice falls back to Files, and a new folder link returns to Files',async()=>{
 const p=panel({prefs:{advanced:false,tab_order:['advanced','project','files']},storage:{'vibez-panel-tab-v2':'advanced'}});await p.settle();
 assert.deepEqual(p.strip(),['advanced','files']);assert.equal(p.state().current,'advanced','the last open tab comes back, even with the former switch off');
 const old=panel({prefs:{tab_order:['files','project','advanced']},storage:{'vibez-panel-tab-v2':'project'}});await old.settle();
 assert.equal(old.state().current,'files','a stored Project tab from an older installation lands on Files');assert.deepEqual(old.strip(),['files','advanced']);
 p.renderWeb({folder:null});assert.equal(p.state().current,'advanced');
 p.renderWeb({folder:'/fixtures/Main',workspace_binding:'b1'});
 assert.equal(p.state().current,'files','linking a folder opens Files');assert.equal(p.storage['vibez-panel-tab-v2'],'advanced','the automatic switch is not stored as a choice');
 p.byId.get('tab-advanced-button').dispatch('click');p.renderWeb({folder:'/fixtures/Main',workspace_binding:'b1'});
 assert.equal(p.state().current,'advanced','an unchanged link does not switch tabs');
 p.byId.get('panel-tabs-reset').dispatch('click');assert.deepEqual(p.strip(),['files','advanced']);
 assert.equal(JSON.stringify(p.calls.filter(c=>c.name==='panel_prefs_set').at(-1).args),JSON.stringify({tabOrder:['files','advanced']}));
 assert.equal(p.byId.get('panel-tabs-reset').disabled,true,'reset is idle in the default order');
});

const ID='cace260d-d95d-4859-b45b-f56f185f15da';
const SNAPSHOT={folder:'/fixtures/Main',workspace_binding:'b1',enabled:true,local_connector_id:'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',tunnel_status:'running',token:'private-token-value',url:'https://quiet-river.trycloudflare.com/mcp/'+ID,
 environment:{host:'studio-pc',git:{branch:'feature/advanced',remote:'lecomputeur/vibez'}},
 recent_activity:[{project_id:ID,project:'Fixture',action:'propose_file',path:'notes/plan.md',time:1700000200,outcome:'saved'}],
 activity:[{project_id:ID,project:'Fixture',action:'read_file',path:'README.md',time:1700000100},{project_id:'other',project:'Other',action:'read_file',path:'secret.txt',time:1700000300},{project_id:ID,project:'Fixture',action:'propose_file',path:'notes/plan.md',time:1700000200,outcome:'saved'},{project_id:ID,project:'Fixture',action:'bogus',path:'x',time:1700000400}]};

test('the Advanced tab shows the environment of the project and its changes newest first',async()=>{
 const p=panel({prefs:{advanced:true,tab_order:['files','project','advanced']}});await p.settle();
 p.renderWeb(SNAPSHOT);p.byId.get('tab-advanced-button').dispatch('click');
 const facts=p.byId.get('advanced-environment-facts');
 assert.deepEqual(facts.children.map(n=>n.textContent),[messages.en.advancedHost,'studio-pc',messages.en.advancedFolder,'/fixtures/Main',messages.en.advancedBranch,'feature/advanced',messages.en.advancedRepository,'lecomputeur/vibez']);
 const rows=p.byId.get('advanced-changes-list').children;
 assert.deepEqual(rows.map(r=>r.children[0].title),['notes/plan.md','README.md'],'newest first, other projects and unknown actions left out');
 assert.equal(rows[0].children[1].textContent,'saved');assert.equal(p.byId.get('advanced-changes-empty').hidden,true);
 assert.ok(!p.calls.some(c=>c.args?.payload?.action==='web_enable'),'the tab only shows data and sends no permission commands');
 // A folder that is not a repository shows no branch or repository line.
 p.renderWeb({...SNAPSHOT,environment:{host:'studio-pc',git:null}});
 assert.deepEqual(p.byId.get('advanced-environment-facts').children.map(n=>n.textContent).filter((_,i)=>i%2===0),[messages.en.advancedHost,messages.en.advancedFolder]);
 p.renderWeb({...SNAPSHOT,folder:null,enabled:false,environment:{host:'studio-pc',git:null}});
 assert.equal(p.byId.get('advanced-environment-facts').children.map(n=>n.textContent)[3],messages.en.advancedNone,'no folder shows none');
 assert.equal(p.byId.get('advanced-changes-list').children.length,2,'the activity stays while the project is open');
 for(const secret of ['private-token-value','quiet-river.trycloudflare.com','secret.txt'])assert.ok(!(facts.textContent+p.byId.get('advanced-changes-list').textContent).includes(secret),secret);
});

test('the diagnostics dialog opens from Settings, shows connection facts and activity without secrets, and copies one report',async()=>{
 const p=panel({prefs:{advanced:false,tab_order:['files','project','advanced']}});await p.settle();
 p.renderWeb(SNAPSHOT);
 const dialog=p.byId.get('diagnostics-dialog');assert.equal(dialog.open,false);
 p.byId.get('settings-diagnostics').dispatch('click');
 assert.equal(dialog.open,true);assert.ok(p.calls.some(c=>c.args?.payload?.action==='web_diagnostics'),'opening the dialog asks the engine for diagnostics');
 assert.equal(p.byId.get('diagnostics-unavailable').hidden,true);assert.equal(p.byId.get('advanced-connection').hidden,false);assert.equal(p.byId.get('advanced-activity').hidden,false);
 assert.ok(p.byId.get('advanced-connection-facts').textContent.includes(messages.en.advancedUnavailable),'before the engine answers the counts are marked unavailable');
 p.emit('app-engine',{type:'web_diagnostics',project_id:ID,tunnel_status:'running',tunnel_host:'quie….trycloudflare.com',local_connector_id:'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',enabled:true,sse_streams:1,
  protocol_versions:['2025-03-26','2025-06-18'],request_counts:{'tools/list:200':4,'tools/call:200':2},request_total:6,rejections:{token:1},recent_rejections:[{reason:'token',http_status:401}],
  recent_errors:[{time:1700000500,verb:'POST',phase:'rpc',method:'tools/call',http_status:200,tool:'read_file',tool_error:true}],timing:{outcome:'connected',method:'work',steps:[['tunnel',6],['enroll:create',17.2]]}});
 const facts=p.byId.get('advanced-connection-facts').textContent;
 for(const expected of [messages.en.advancedTunnel,'running','quie….trycloudflare.com',messages.en.advancedConnectorId,'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa','2025-03-26, 2025-06-18','tools/list:200 ×4','token ×1','connected (work)','enroll:create 17.2 s'])assert.ok(facts.includes(expected),expected);
 const errors=p.byId.get('advanced-connection-errors').textContent;
 assert.ok(errors.includes('tools/call · read_file · rpc · HTTP 200 · tool error'));assert.ok(errors.includes('rejected: token · HTTP 401'));
 const activity=p.byId.get('advanced-activity-list').children;
 assert.deepEqual(activity.map(r=>r.children[0].title),['README.md','notes/plan.md'],'oldest first in the diagnostics');
 assert.equal(p.byId.get('diagnostics-details').hidden,true,'no technical details without an error');
 for(const secret of ['private-token-value','quiet-river.trycloudflare.com','secret.txt'])assert.ok(!(facts+errors+p.byId.get('advanced-activity-list').textContent).includes(secret),secret);
 // Diagnostics of another project are ignored.
 p.emit('app-engine',{type:'web_diagnostics',project_id:'other',protocol_versions:['1999-01-01'],request_counts:{},rejections:{},recent_errors:[],recent_rejections:[]});
 assert.ok(!p.byId.get('advanced-connection-facts').textContent.includes('1999-01-01'));
 // The report goes through the app clipboard command and carries the same facts, never a key or the full tunnel host.
 p.byId.get('diagnostics-copy').dispatch('click');await p.settle();
 const copy=p.calls.find(c=>c.name==='app_copy');assert.ok(copy,'app_copy called');const report=copy.args.text;
 for(const expected of ['VibeZ test','feature/advanced','lecomputeur/vibez','quie….trycloudflare.com','tools/list:200 ×4','rejected: token · HTTP 401','README.md','notes/plan.md · saved'])assert.ok(report.includes(expected),expected);
 for(const secret of ['private-token-value','quiet-river.trycloudflare.com','secret.txt','studio-pc','/fixtures/Main'])assert.ok(!report.includes(secret),secret);
 assert.equal(p.byId.get('diagnostics-status').textContent,messages.en.diagnosticsCopied);
 p.byId.get('diagnostics-close').dispatch('click');assert.equal(dialog.open,false);
 // Without a project the dialog says so and offers nothing to copy.
 p.run("renderWeb({type:'web_connector',project:null,folder:null,folders:[],pending:[],activity:[],recent_activity:[],tunnel_status:'stopped'})");
 p.byId.get('settings-diagnostics').dispatch('click');
 assert.equal(p.byId.get('diagnostics-unavailable').hidden,false);assert.equal(p.byId.get('advanced-connection').hidden,true);assert.equal(p.byId.get('diagnostics-copy').disabled,true);
});

test('the report lists each rejected request once, names its HTTP verb instead of none, and always fills the environment line',async()=>{
 const p=panel({prefs:{advanced:false}});await p.settle();
 p.renderWeb({...SNAPSHOT,environment:{host:'studio-pc',system:'Linux · Flatpak',git:null}});
 p.byId.get('settings-diagnostics').dispatch('click');
 p.emit('app-engine',{type:'web_diagnostics',project_id:ID,tunnel_status:'running',protocol_versions:['2025-06-18'],request_counts:{'GET:404':3,'DELETE:204':1},request_total:4,rejections:{token:3},
  recent_rejections:[1,2,3].map(()=>({reason:'token',http_status:404})),
  recent_errors:[1700000500,1700000501,1700000512].map(time=>({time,verb:'GET',phase:'auth',method:'none',http_status:404,rejection:'token'}))});
 const errors=p.byId.get('advanced-connection-errors').children[1].children.map(li=>li.textContent);
 assert.equal(errors.length,3,'three rejected probes are three lines, not six');
 for(const line of errors){assert.ok(line.endsWith('GET · auth · rejected: token · HTTP 404'),line);assert.ok(!line.includes('none'),line);}
 p.byId.get('diagnostics-copy').dispatch('click');await p.settle();
 const report=p.calls.find(c=>c.name==='app_copy').args.text;
 assert.ok(report.includes(messages.en.advancedEnvironment+': Linux · Flatpak\n'),'the environment line names the system when the folder has no git');
 assert.ok(!report.includes('studio-pc')&&!report.includes('/fixtures/Main'),'no host name or folder path in the report');
 assert.ok(!report.includes('\n- rejected: token'),'no second copy of the rejections');
});

test('a failed connection offers an Open diagnostics link next to the technical details, and the dialog repeats those details',async()=>{
 const p=panel({prefs:{advanced:false,tab_order:['files','project','advanced']}});await p.settle();
 p.renderWeb(SNAPSHOT);
 assert.equal(p.byId.get('error-open-diagnostics').hidden,true);
 p.run("actionError='tunnel exploded';renderAutomatic()");
 assert.equal(p.byId.get('error-open-diagnostics').hidden,false);assert.equal(p.byId.get('error-details').hidden,false);
 p.byId.get('error-open-diagnostics').dispatch('click');
 assert.equal(p.byId.get('diagnostics-dialog').open,true);
 assert.equal(p.byId.get('diagnostics-details').hidden,false);assert.equal(p.byId.get('diagnostics-details-text').textContent,p.byId.get('error-details-text').textContent);
 p.byId.get('diagnostics-copy').dispatch('click');await p.settle();
 assert.ok(p.calls.find(c=>c.name==='app_copy').args.text.includes(p.byId.get('error-details-text').textContent));
 p.run("actionError='';renderAutomatic()");
 assert.equal(p.byId.get('error-open-diagnostics').hidden,true);assert.equal(p.byId.get('diagnostics-details').hidden,true,'an open dialog follows the connection status');
});

test('every new Advanced key exists in all 33 languages and the HTML uses only known keys',()=>{
 const keys=['tabAdvanced','tabShowAdvanced','advancedToggle','advancedToggleHelp','tabOrderHelp','tabOrderReset','advancedActivity','advancedActivityHelp','advancedConnection','advancedTunnel','advancedConnectorId','advancedProtocolVersions','advancedRequests','advancedRejections','advancedTiming','advancedErrors','advancedNone','advancedRefresh','advancedUnavailable','advancedEnvironment','advancedHost','advancedFolder','advancedBranch','advancedRepository','advancedChanges','advancedChangesHelp','diagnosticsTitle','diagnosticsOpen','diagnosticsHelp','diagnosticsCopy','diagnosticsCopied'];
 assert.equal(Object.keys(messages).length,33);
 for(const [code,dictionary]of Object.entries(messages))for(const key of keys)assert.ok(typeof dictionary[key]==='string'&&dictionary[key].trim(),code+':'+key);
 assert.notEqual(messages.nl.tabAdvanced,messages.en.tabAdvanced);assert.notEqual(messages.nl.diagnosticsOpen,messages.en.diagnosticsOpen);assert.notEqual(messages.de.advancedToggleHelp,messages.en.advancedToggleHelp);
 const html=fs.readFileSync(path.join(root,'standalone-ui/panel.html'),'utf8');
 assert.ok(html.indexOf('id="tab-advanced-button"')>html.indexOf('id="tab-files-button"'),'Advanced follows Files in the strip');
 for(const gone of ['panel-tabs-switch','panel-advanced-switch','panel-advanced-toggle','advancedToggle'])assert.ok(!html.includes(gone),gone+' is gone');
 assert.ok(!html.includes('tab-project')&&!html.includes('recent-file-actions')&&!html.includes('tabProject'),'no Project tab and no second file-action list');
 const advancedAt=html.indexOf('id="tab-advanced"');for(const id of ['advanced-environment','project-rules','mistral-project-settings','advanced-changes'])assert.ok(html.indexOf('id="'+id+'"')>advancedAt,id+' lives in Advanced');
 assert.ok(html.indexOf('id="project-rules"')>html.indexOf('id="advanced-environment"')&&html.indexOf('id="project-rules"')<html.indexOf('id="advanced-changes"'),'rules sit under Environment');
 assert.match(html,/<script src="panel-tabs.js" defer><\/script><script src="panel.js" defer>/);
 for(const id of ['advanced-environment','advanced-changes','diagnostics-dialog','settings-diagnostics','error-open-diagnostics','diagnostics-copy'])assert.ok(html.includes('id="'+id+'"'),id);
 assert.ok(!html.includes('advanced-details-slot')&&!html.includes('panel-tabs-more')&&!html.includes('advanced-allow'),'the Advanced tab holds no permission switch');
 const dialogAt=html.indexOf('<dialog id="diagnostics-dialog"');assert.ok(dialogAt>0&&html.indexOf('id="advanced-connection"')>dialogAt&&html.indexOf('id="advanced-activity"')>dialogAt,'connection and activity live in the dialog');
 for(const match of html.matchAll(/data-v4="([^"]+)"/g))assert.ok(typeof messages.en[match[1]]==='string'||match[1] in (require(path.join(root,'standalone-ui/language-extra.json')).en),match[1]);
});

test('move and delete proposals have their own wording and several proposals can be saved at once',async()=>{
 const p=panel();await p.settle();
 const base={project_id:ID,project_name:'Fixture',diff:'',new:false};
 p.renderWeb({folder:'/fixtures/Main',workspace_binding:'b1',pending:[
  {...base,id:'m1',action:'move',path:'old.txt',new_path:'archive/new.txt',before:'',after:''},
  {...base,id:'d1',action:'delete',path:'gone.txt',before:'Old text',after:''},
  {...base,id:'w1',path:'notes.md',before:'a',after:'b'}]});
 const list=p.byId.get('web-proposals').children,all=list[0];
 assert.equal(all.className,'approval-actions approval-all');assert.deepEqual(all.children.map(b=>b.textContent),['Save all','Reject all']);
 const cards=list.slice(1),title=c=>c.children[0].children[1].textContent,primary=c=>c.children.at(-1).children[0].textContent;
 assert.equal(title(cards[0]),'old.txt → archive/new.txt');assert.equal(primary(cards[0]),'Move');assert.equal(cards[0].children.length,2,'a move shows no text comparison');
 assert.equal(primary(cards[1]),'Delete');assert.equal(cards[1].children[1].children.length,1,'a delete shows only the current text');
 assert.equal(primary(cards[2]),'Save');assert.equal(cards[2].children[1].children.length,2);
 assert.match(cards[0].children[0].children[2].textContent,/Nothing is replaced/);assert.match(cards[1].children[0].children[2].textContent,/cannot be undone/);
 all.children[0].dispatch('click');await p.settle();
 assert.deepEqual(p.calls.filter(c=>c.args?.payload?.action==='web_approve').map(c=>[c.args.payload.id,c.args.payload.allow]),[['m1',true],['d1',true],['w1',true]]);
 p.renderWeb({folder:'/fixtures/Main',workspace_binding:'b1',pending:[{...base,id:'w2',path:'one.md',before:'',after:'x'}]});
 assert.equal(p.byId.get('web-proposals').children.length,1,'one proposal needs no Save all');
});

test('a Code project shows its project rules under Advanced and reads them from Mistral',async()=>{
 const p=panel();await p.settle();
 p.renderWeb({project:{id:'code-'+ID,name:'Code fixture',kind:'project'},folder:'/fixtures/Main',workspace_binding:'b1'});await p.settle();
 assert.equal(p.byId.get('project-rules').hidden,false);
 assert.ok(p.calls.some(c=>c.name==='project_rules_edit'&&c.args.projectId==='code-'+ID&&c.args.action==='api-read'));
 p.renderWeb({project:{id:'chat-'+ID,name:'Chat',kind:'conversation'},folder:null});
 assert.equal(p.byId.get('project-rules').hidden,true,'a conversation has no project rules');
});

// A fake clock: timers run as soon as the test advances time past them.
function fakeClock(){
 let now=Date.now();const timers=[];
 class FakeDate extends Date{constructor(...a){super(...(a.length?a:[now]));}static now(){return now;}}
 return {Date:FakeDate,setTimeout:(fn,ms)=>{timers.push({at:now+(ms||0),fn});return timers.length;},
  advance(ms){now+=ms;for(const t of timers.splice(0).sort((a,b)=>a.at-b.at)){if(t.at<=now)t.fn();else timers.push(t);}}};
}

test('a failed first read of Code project rules is retried on a timer until Mistral answers',async()=>{
 const clock=fakeClock();let reads=0;
 const p=panel({clock,answers:{project_rules_edit:args=>{if(args.action!=='api-read')return undefined;reads++;if(reads===1)throw new Error('The project has switched; try again');return {project_id:args.projectId,value:'Answer briefly.'};}}});
 p.renderWeb({project:{id:'code-'+ID,name:'Code fixture',kind:'project'},folder:'/fixtures/Main',workspace_binding:'b1'});await p.settle();
 assert.equal(reads,1);assert.equal(p.byId.get('project-rules-text').textContent,messages.en.projectRulesUnavailable);
 clock.advance(8200);await p.settle();
 assert.equal(reads,2,'the panel asks again by itself, without another redraw');
 assert.equal(p.byId.get('project-rules-text').textContent,'Answer briefly.');
 clock.advance(60000);await p.settle();assert.equal(reads,2,'a successful read is not repeated');
});

test('a Code project whose rules keep failing is retried only a few times by the timer',async()=>{
 const clock=fakeClock();let reads=0;
 const p=panel({clock,answers:{project_rules_edit:args=>{if(args.action==='api-read'){reads++;throw new Error('unavailable');}return undefined;}}});
 p.renderWeb({project:{id:'code-'+ID,name:'Code fixture',kind:'project'},folder:'/fixtures/Main',workspace_binding:'b1'});await p.settle();
 for(let i=0;i<8;i++){clock.advance(8200);await p.settle();}
 assert.equal(reads,4,'three timed retries after the first read');
 assert.equal(p.byId.get('project-rules-text').textContent,messages.en.projectRulesUnavailable);
});

test('after an update the panel opens once with every missed version, and Settings shows all versions again',async()=>{
 const missed={current:'4.0.0-beta.5',versions:[{version:'4.0.0-beta.5',date:'2026-11-20',changes:['Five.']},{version:'4.0.0-beta.4',date:'2026-11-18',changes:['Four a.','Four b.']}]};
 const all={current:'4.0.0-beta.5',versions:[...missed.versions,{version:'4.0.0-beta.3',changes:['Three.']}]};
 const p=panel({answers:{whats_new_get:args=>args.all?all:missed}});await p.settle();await new Promise(r=>setTimeout(r,1600));
 const dialog=p.byId.get('whats-new-dialog');
 assert.equal(dialog.open,true);assert.ok(p.calls.some(c=>c.name==='chrome_panel'&&c.args.mode==='files'),'the panel opens to show it');
 assert.match(p.byId.get('whats-new-intro').textContent,/updated to V4 Beta 5/);
 const sections=p.byId.get('whats-new-list').children;
 assert.deepEqual(sections.map(s=>s.children[0].textContent),['V4 Beta 5 \u00b7 2026-11-20','V4 Beta 4 \u00b7 2026-11-18']);
 assert.deepEqual(sections[1].children[1].children.map(li=>li.textContent),['Four a.','Four b.']);
 assert.equal(p.byId.get('whats-new-english').hidden,true,'no English note in English');
 p.byId.get('whats-new-done').dispatch('click');dialog.dispatch('close');await p.settle();
 assert.ok(p.calls.some(c=>c.name==='whats_new_seen'),'closing records the version as shown');
 p.byId.get('settings-whats-new').dispatch('click');await p.settle();
 assert.equal(p.byId.get('whats-new-list').children.length,3);assert.equal(p.byId.get('whats-new-intro').textContent,'The changes in each version of VibeZ V4.');
 const quiet=panel({answers:{whats_new_get:()=>({current:'4.0.0-beta.5',versions:[]})}});await quiet.settle();await new Promise(r=>setTimeout(r,1600));
 assert.equal(quiet.byId.get('whats-new-dialog').open,false);assert.ok(!quiet.calls.some(c=>c.name==='chrome_panel'),'nothing new: the panel stays as it is');
});

test('closing Settings returns to the project panel when it was open, and closes the panel otherwise',async()=>{
 const p=panel();await p.settle();
 const closeTo=()=>{p.calls.length=0;p.byId.get('close-settings-panel').dispatch('click');return p.calls.find(c=>c.name==='chrome_panel')?.args.mode;};
 p.emit('chrome-panel','files');p.emit('chrome-panel','settings');
 assert.equal(closeTo(),'files');
 p.emit('chrome-panel','closed');p.emit('chrome-panel','settings');
 assert.equal(closeTo(),'closed');
 p.emit('chrome-panel','files');p.emit('chrome-panel','language');
 assert.equal(closeTo(),'files','the language shortcut opens Settings too');
 const html=fs.readFileSync(path.join(root,'standalone-ui/panel.html'),'utf8'),settings=html.slice(html.indexOf('id="panel-settings"'),html.indexOf('<dialog'));
 for(const key of ['accountNote','languageHelp','autoConnectHelp','tabOrderHelp','diagnosticsHelp','whatsNewHelp'])assert.ok(!settings.includes('data-v4="'+key+'"'),key+' is no longer a paragraph in Settings');
 for(const key of ['autoConnectHelp','tabOrderHelp','diagnosticsHelp','whatsNewHelp'])assert.ok(settings.includes('data-help-key="'+key+'"'),key+' remains as a tooltip');
 assert.ok(!settings.includes('id="language"'),'the language is chosen in the toolbar');
 for(const id of ['panel-auto-connect','settings-diagnostics','settings-whats-new','panel-tabs-reset'])assert.ok(settings.slice(settings.indexOf('settings-menu')).includes('id="'+id+'"'),id+' is in the menu');
});

test('Settings offers Report a problem, Share feedback and About, and links only name fixed pages',async()=>{
 const p=panel();await p.settle();
 p.byId.get('settings-about').dispatch('click');
 assert.equal(p.byId.get('about-dialog').open,true);
 const thanks=p.byId.get('about-thanks');assert.match(thanks.textContent,/ActiveUser435/);
 thanks.children.find(c=>c.tagName==='BUTTON').dispatch('click');await p.settle();
 assert.deepEqual(JSON.parse(JSON.stringify(p.calls.filter(c=>c.name==='app_open_link').map(c=>c.args))),[{link:'tester'}]);
 p.byId.get('about-close').dispatch('click');assert.equal(p.byId.get('about-dialog').open,false);
 const html=fs.readFileSync(path.join(root,'standalone-ui/panel.html'),'utf8'),rust=fs.readFileSync(path.join(root,'desktop/src-tauri/src/app_links.rs'),'utf8');
 assert.match(html,/© 2026 Le Computeur/,'the maker is named as in the licence');
 const links=[...html.matchAll(/data-link="([^"]+)"/g)].map(m=>m[1]);
 assert.deepEqual(links.sort(),['feedback','license','report','source','website']);
 for(const link of links)assert.ok(rust.includes('"'+link+'"=>"https://'),link+' is a fixed address in the app');
 for(const key of ['menuReport','menuFeedback','aboutTitle','aboutThanks'])for(const [code,d]of Object.entries(messages))assert.ok(d[key],code+':'+key);
});

test('a failed read of the project rules is tried again later instead of being kept',async()=>{
 let fail=true;const p=panel({answers:{project_rules_edit:async args=>{if(fail)throw new Error('not yet');return {project_id:args.projectId,value:'Rule'};}}});await p.settle();
 p.renderWeb({project:{id:'code-'+ID,name:'Code',kind:'project'},folder:'/f',workspace_binding:'b1'});await p.settle();
 assert.equal(p.run("apiRules.failed"),true);const reads=()=>p.calls.filter(c=>c.name==='project_rules_edit').length;const first=reads();
 p.renderWeb({project:{id:'code-'+ID,name:'Code',kind:'project'},folder:'/f',workspace_binding:'b1'});await p.settle();
 assert.equal(reads(),first,'no new read straight away');
 fail=false;p.run('apiRules.at=Date.now()-9000');
 p.renderWeb({project:{id:'code-'+ID,name:'Code',kind:'project'},folder:'/f',workspace_binding:'b1'});await p.settle();
 assert.equal(reads(),first+1);assert.equal(p.run('apiRules.value'),'Rule');assert.equal(p.byId.get('project-rules-edit').hidden,false,'the edit button appears after the retry');
});
