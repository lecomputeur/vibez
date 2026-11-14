'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {createConnectionStatus}=require('../../standalone-ui/connection-status.js');

const WORK='cace260d-d95d-4859-b45b-f56f185f15da';
const CODE='code-'+WORK;
const OTHER='229ee257-1234-4567-890a-123456789abc';
function snapshot(extra={}){
 return {type:'web_connector',project:{id:WORK,name:'Work Alpha'},folder:'/fixtures/Alpha',
  enabled:false,tunnel_status:'stopped',auto_approved:true,manually_paused:false,
  url:'https://fixture.invalid/mcp/'+WORK,...extra};
}
function automatic(project_id,status,extra={}){return {type:'web_auto',project_id,status,...extra};}
function state(s,expected){
 const view=s.view();assert.equal(view.state,expected);
 assert.equal(typeof view.key,'string');assert.ok(view.key.length>0);
 assert.equal(typeof view.projectName,'string');assert.equal(typeof view.folderName,'string');return view;
}
function connected(s,extra={}){
 s.receive(snapshot({enabled:true,tunnel_status:'running',...extra}));
 s.receive(automatic(extra.project?.id||WORK,'connected'));
 state(s,'connected');
}

test('startup and a project without a folder never imply a live file connection',()=>{
 const s=createConnectionStatus();state(s,'no_project');
 s.receive(snapshot({project:null,folder:null,enabled:true,tunnel_status:'running'}));
 s.receive(automatic(WORK,'connected'));state(s,'no_project');
 s.receive(snapshot({folder:null,enabled:true,tunnel_status:'running'}));
 s.receive(automatic(WORK,'connected'));state(s,'no_folder');
});

test('saved approval, a running transport and account sign-in are not connection proof',()=>{
 const s=createConnectionStatus();s.receive(snapshot({enabled:true,tunnel_status:'running'}));
 state(s,'disconnected');
 for(const status of ['starting','waiting','connected','error','disconnected']){
  s.receive({type:'auth',status});state(s,'disconnected');
 }
 s.receive(automatic(WORK,'connected'));state(s,'connected');
 s.receive({type:'auth',status:'error'});state(s,'connected');
});

test('snapshot-first header boot replay restores only the current verified connection',()=>{
 const s=createConnectionStatus();
 s.receive(automatic(WORK,'connected'));state(s,'no_project');
 s.receive(snapshot({enabled:true,tunnel_status:'running'}));state(s,'disconnected');
 s.receive(automatic(WORK,'connected'));state(s,'connected');
 s.receive(snapshot({enabled:true,tunnel_status:'running',project:{id:WORK,name:'Work Alpha renamed'}}));
 assert.equal(state(s,'connected').projectName,'Work Alpha renamed');
});

test('Work and Code with the same raw UUID cannot reuse each other’s proof',()=>{
 const s=createConnectionStatus();connected(s);
 const code={id:CODE,name:'Code Alpha'};
 s.receive(snapshot({project:code,enabled:true,tunnel_status:'running'}));
 assert.notEqual(s.view().state,'connected');assert.equal(s.view().projectName,'Code Alpha');
 for(const status of ['connected','error','paused']){
  s.receive(automatic(WORK,status,{pause_reason:'manual'}));assert.notEqual(s.view().state,'connected');
 }
 s.receive(automatic(CODE,'connected'));state(s,'connected');
 s.receive(automatic(WORK,'error'));state(s,'connected');
 s.receive(snapshot({enabled:true,tunnel_status:'running'}));assert.notEqual(s.view().state,'connected');
 s.receive(automatic(CODE,'connected'));assert.notEqual(s.view().state,'connected');
 s.receive(automatic(WORK,'connected'));state(s,'connected');
});

test('folder relinking invalidates proof even when project and transport remain the same',()=>{
 const s=createConnectionStatus();connected(s);
 s.receive(snapshot({folder:'/fixtures/Replacement',enabled:true,tunnel_status:'running'}));
 assert.notEqual(s.view().state,'connected');
 s.receive(automatic(WORK,'registering',{automatic:false}));state(s,'connecting');
 s.receive(automatic(WORK,'connected'));state(s,'connected');
});

test('disable and re-enable at the same path require fresh verified proof',()=>{
 const s=createConnectionStatus();connected(s);
 s.receive(snapshot({enabled:false,tunnel_status:'running'}));assert.notEqual(s.view().state,'connected');
 s.receive(snapshot({enabled:true,tunnel_status:'running'}));assert.notEqual(s.view().state,'connected');
 s.receive(automatic(WORK,'connected'));state(s,'connected');
});

test('a connected message received while disabled cannot unlock a future enable',()=>{
 const s=createConnectionStatus();s.receive(snapshot());
 s.receive(automatic(WORK,'connected'));assert.notEqual(s.view().state,'connected');
 s.receive(snapshot({enabled:true,tunnel_status:'running'}));assert.notEqual(s.view().state,'connected');
 s.receive(automatic(WORK,'connected'));state(s,'connected');
});

test('stopped or failed transport invalidates proof until a newly verified connection',()=>{
 for(const tunnel_status of ['stopped','starting','failed']){
  const s=createConnectionStatus();connected(s);
  s.receive(snapshot({enabled:true,tunnel_status}));assert.notEqual(s.view().state,'connected');
  s.receive(snapshot({enabled:true,tunnel_status:'running'}));assert.notEqual(s.view().state,'connected');
  s.receive(automatic(WORK,'connected'));state(s,'connected');
 }
});

test('manual pause suppresses old connected proof while explicit resume can show progress',()=>{
 const s=createConnectionStatus();connected(s);
 s.receive(snapshot({manually_paused:true}));state(s,'manual');
 s.receive(automatic(WORK,'connected'));state(s,'manual');
 s.receive(automatic(WORK,'starting',{automatic:false}));state(s,'connecting');
 s.receive(snapshot({manually_paused:true,enabled:true,tunnel_status:'running'}));state(s,'connecting');
 s.receive(snapshot({manually_paused:false,enabled:true,tunnel_status:'running'}));state(s,'connecting');
 s.receive(automatic(WORK,'connected'));state(s,'connected');
});

test('all actual setup phases remain progress rather than confirmed connection',()=>{
 const s=createConnectionStatus();s.receive(snapshot());
 for(const status of ['starting','authorizing','connecting','registering']){
  s.receive(automatic(WORK,status,{automatic:false}));state(s,'connecting');
 }
});

test('scoped errors remain visible after runtime cleanup and an explicit retry can proceed',()=>{
 const s=createConnectionStatus();connected(s);
 s.receive(automatic(WORK,'error',{error_code:'connector_auth'}));state(s,'error');
 s.receive(snapshot({enabled:false,tunnel_status:'running'}));state(s,'error');
 s.receive(automatic(OTHER,'connected'));state(s,'error');
 s.receive(automatic(WORK,'starting',{automatic:false}));state(s,'connecting');
 s.receive(snapshot({enabled:true,tunnel_status:'running'}));state(s,'connecting');
 s.receive(automatic(WORK,'connected'));state(s,'connected');
});

test('manual and sign-in holds have separate states from generic paused connections',()=>{
 const s=createConnectionStatus();s.receive(snapshot());
 s.receive(automatic(WORK,'paused',{pause_reason:'sign_in'}));state(s,'sign_in');
 s.receive(automatic(WORK,'paused',{pause_reason:'manual'}));state(s,'manual');
 s.receive(automatic(WORK,'paused',{pause_reason:'approval'}));state(s,'paused');
});

test('a project exit clears the former project’s displayed connection and ignores late events',()=>{
 const s=createConnectionStatus();connected(s);
 s.receive(snapshot({project:null,folder:null,enabled:false,tunnel_status:'running'}));state(s,'no_project');
 s.receive(automatic(WORK,'connected'));state(s,'no_project');
 s.receive(snapshot({project:{id:OTHER,name:'Work Beta'},folder:'/fixtures/Beta',enabled:true,tunnel_status:'running'}));
 assert.notEqual(s.view().state,'connected');
 s.receive(automatic(OTHER,'connected'));assert.equal(state(s,'connected').projectName,'Work Beta');
});

test('returned toolbar state contains only safe presentation fields, never connection tokens',()=>{
 const s=createConnectionStatus(),token='fixture-sensitive-token-never-render';
 connected(s,{token});
 const view=state(s,'connected');
 assert.deepEqual(Object.keys(view).sort(),['draft','folderName','key','kind','projectName','state']);
 assert.ok(!JSON.stringify(view).includes(token));assert.equal(view.projectName,'Work Alpha');
 assert.equal(view.folderName,'Alpha');assert.ok(!JSON.stringify(view).includes('/fixtures/'));
});

test('toolbar names follow the current project and folder without exposing the full path',()=>{
 const s=createConnectionStatus();
 assert.equal(s.view().projectName,'');assert.equal(s.view().folderName,'');
 connected(s,{folder:'/fixtures/Alpha/'});assert.equal(s.view().folderName,'Alpha');
 s.receive(snapshot({project:{id:OTHER,name:'Project Beta'},folder:'C:\\fixtures\\Beta\\'}));
 assert.equal(s.view().projectName,'Project Beta');assert.equal(s.view().folderName,'Beta');
 s.receive(snapshot({folder:'/'}));assert.equal(s.view().folderName,'/');
 s.receive(snapshot({folder:null}));assert.equal(s.view().folderName,'');
 s.receive(snapshot({project:null,folder:'/fixtures/Old'}));
 assert.equal(s.view().projectName,'');assert.equal(s.view().folderName,'');
});

test('fatal engine shutdown stops the connection until reload while ordinary action errors do not',()=>{
 const s=createConnectionStatus();connected(s);
 s.receive({type:'error',message:'A screenshot could not be copied.'});state(s,'connected');
 s.receive({type:'error',code:'engine_stopped',message:'Open VibeZ opnieuw.'});state(s,'error');
 s.receive(snapshot({enabled:true,tunnel_status:'running'}));
 s.receive(automatic(WORK,'connected'));state(s,'error');
});


test('draft promotion keeps live proof only for the same local conversation and folder',()=>{
 const id='chat-'+WORK,s=createConnectionStatus();
 const draft={id,name:'New conversation',kind:'conversation',draft:true};
 connected(s,{project:draft});
 assert.equal(s.view().draft,true);assert.equal(s.view().kind,'conversation');
 s.receive(snapshot({project:{...draft,name:'A saved conversation',draft:false,conversation_id:OTHER},enabled:true,tunnel_status:'running'}));
 assert.equal(state(s,'connected').projectName,'A saved conversation');assert.equal(s.view().draft,false);
 for(const other of [WORK,CODE,'chat-'+OTHER]){
  s.receive(snapshot({project:{id:other,name:'Other'},enabled:true,tunnel_status:'running'}));
  assert.notEqual(s.view().state,'connected');s.receive(automatic(id,'connected'));assert.notEqual(s.view().state,'connected');
 }
});
