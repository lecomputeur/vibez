'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'../src-tauri/src/workspace_project.js'),'utf8');
const A='cace260d-d95d-4859-b45b-f56f185f15da',B='229ee257-1234-4567-890a-123456789abc';
const overview='https://chat.mistral.ai/work/projects/'+A,chat='https://chat.mistral.ai/work/11111111-2222-4333-8444-555555555555';
function node(tag,attributes={},visible=true){
 const value={tagName:tag.toUpperCase(),attributes,children:[],parentElement:null,shown:visible,
  classList:{contains:name=>(attributes.class||'').split(' ').includes(name)},getAttribute:name=>attributes[name]??null,
  getClientRects(){for(let current=this;current;current=current.parentElement)if(current.shown===false)return[];return[{}];},
  closest(selector){for(let current=this;current;current=current.parentElement){
   if(selector==='ul[data-sidebar="menu"]'&&current.tagName==='UL'&&current.getAttribute('data-sidebar')==='menu')return current;
   if(selector==='li[data-sidebar="menu-item"]'&&current.tagName==='LI'&&current.getAttribute('data-sidebar')==='menu-item')return current;
  }return null;},
  append(...children){for(const child of children){child.parentElement=this;this.children.push(child);}return this;},
  querySelectorAll(selector){assert.equal(selector,'a[href]');const matches=[];const visit=value=>{for(const child of value.children){if(child.tagName==='A'&&child.href)matches.push(child);visit(child);}};visit(this);return matches;}
 };return value;
}
const anchor=(href,text='',visible=true)=>Object.assign(node('a',{},visible),{href,innerText:text,textContent:text});
function projectGroup(href,text,chats=[]){
 const project=anchor(href,text);project.attributes['data-sidebar']='menu-button';
 const root=node('li',{'data-sidebar':'menu-item',class:'group/menu-item'}),menu=node('ul',{'data-sidebar':'menu'});
 const collapse=node('div',{class:'group-data-[collapsible=icon]:hidden'}),list=node('ul',{'data-sidebar':'menu'}),sub=node('ul',{'data-sidebar':'menu-sub'}),inner=node('div');
 for(const link of chats){link.attributes['data-sidebar']='menu-button';list.append(node('li',{'data-sidebar':'menu-item',class:'group/menu-item'}).append(link,node('div')));}
 collapse.append(inner.append(sub.append(list)));root.append(project,collapse);menu.append(root);
 return{project,root,collapse,list,sub,inner,menu,chats};
}
function inspect({url=chat,breadcrumbs=[],main=[],sidebar=[],heading=null,clickedHref=null}={}){
 let click;
 const document={addEventListener:(type,handler)=>{assert.equal(type,'click');click=handler;},querySelectorAll:selector=>{
  if(selector.startsWith('main header'))return breadcrumbs;
  if(selector==='main a[href],[role="main"] a[href]')return main;
  if(selector==='a[href*="/work/projects/"],a[href*="/code/"]')return sidebar;
  if(selector==='a[href*="/work/"]')return sidebar;
  if(selector==='main h1,[role="main"] h1,h1')return heading?[anchor('',heading)]:[];
  throw Error('Unexpected selector '+selector);
 }};
 const context=vm.createContext({document,location:{href:url},URL,window:{}});
 const first=vm.runInContext(script,context);
 if(!clickedHref)return JSON.parse(first);
 click({target:{closest:()=>anchor(clickedHref)}});
 return JSON.parse(vm.runInContext(script,context));
}
test('a project click requests its panel without changing detected project identity',()=>{
 const result=inspect({url:overview,sidebar:[anchor(overview,'Alpha')],clickedHref:overview});
 assert.equal(result.clicked.id,A);assert.match(result.clicked.stamp,/^\d+:1$/);assert.equal(result.name,'Alpha');
 assert.equal(inspect({url:overview,clickedHref:chat}).clicked.id,'chat-11111111-2222-4333-8444-555555555555');
 for(const href of ['https://evil.test/work/projects/'+A,'https://chat.mistral.ai/code/'+A+'/'+B]){
  assert.equal(inspect({url:overview,clickedHref:href}).clicked,null);
 }
 assert.equal(inspect({url:overview,clickedHref:'https://chat.mistral.ai/code/'+A}).clicked.id,'code-'+A);
});
test('loose conversation titles come only from its exact visible chat link',()=>{
 const sidebar=[anchor('https://chat.mistral.ai/work/'+B,'Other chat'),anchor(chat,'  Loose\nconversation '),anchor(overview,'Other project')];
 const result=inspect({url:chat,sidebar});assert.equal(result.conversation_name,'Loose conversation');assert.deepEqual(result.links,[]);
 for(const bad of [anchor(chat,'Hidden',false),anchor('https://evil.test/work/11111111-2222-4333-8444-555555555555','Wrong host')])assert.equal(inspect({url:chat,sidebar:[bad]}).conversation_name,'');
});
test('chat breadcrumbs are deduplicated before reporting distinct projects and ambiguity',()=>{
 const result=inspect({breadcrumbs:[...Array.from({length:8},()=>anchor(overview,'CityTripXL')),anchor('https://chat.mistral.ai/work/projects/'+B,'Other')]});
 assert.equal(result.links.length,2);assert.equal(result.ambiguous,true);assert.deepEqual(result.chats,[]);
});
test('only visible main chat links on a direct project overview are collected',()=>{
 const result=inspect({url:overview,sidebar:[anchor(overview,'CityTripXL')],main:[anchor(chat+'?tab=files#modal'),anchor(chat),anchor('https://chat.mistral.ai/work/chat/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/'),anchor('https://chat.mistral.ai/work/chats/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'),anchor('https://chat.mistral.ai/work/c/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'),anchor(overview),anchor('https://evil.test/work/11111111-2222-4333-8444-555555555555'),anchor('https://chat.mistral.ai/work/settings'),anchor('https://chat.mistral.ai/work/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee','',false)]});
 assert.equal(result.name,'CityTripXL');assert.equal(result.chats.length,4);assert.equal(result.chats[0],chat);
 assert.ok(result.chats.every(url=>url.startsWith('https://chat.mistral.ai/work/')&&!url.includes('?')&&!url.includes('#')));
});
test('chat messages and sidebar links cannot create associations for another chat',()=>{
 const result=inspect({main:[anchor(chat)],sidebar:[anchor(overview,'CityTripXL')]});
 assert.deepEqual(result.chats,[]);assert.deepEqual(result.links,[]);assert.equal(result.ambiguous,false);
 const nested=inspect({url:overview+'/chat/11111111-2222-4333-8444-555555555555',main:[anchor(chat)]});
 assert.deepEqual(nested.chats,[]);
});
test('overview chat collection is bounded and ignores external or credential-bearing links',()=>{
 const main=[anchor('https://user:secret@chat.mistral.ai/work/11111111-2222-4333-8444-555555555555'),anchor('https://chat.mistral.ai:444/work/11111111-2222-4333-8444-555555555555'),...Array.from({length:90},(_,n)=>anchor('https://chat.mistral.ai/work/'+n.toString(16).padStart(8,'0')+'-2222-4333-8444-555555555555'))];
 const result=inspect({url:overview,main});assert.equal(result.chats.length,64);assert.ok(result.chats.every(url=>!url.includes('secret')&&!url.includes(':444')));
});
test('the current project keeps only its own nested sidebar chats when the central list is hidden',()=>{
 const otherChat='https://chat.mistral.ai/work/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
 const own=projectGroup(overview,'CityTripXL',[anchor(chat)]),other=projectGroup('https://chat.mistral.ai/work/projects/'+B,'Other',[anchor(otherChat)]);
 // The official main element includes both sidebar groups; neither group may
 // be mistaken for the central overview list or leak into another project.
 const result=inspect({url:overview,sidebar:[own.project,other.project,...own.chats,...other.chats],main:[...own.chats,...other.chats,anchor(chat,'Hidden central item',false)]});
 assert.equal(result.name,'CityTripXL');assert.deepEqual(result.chats,[chat]);assert.deepEqual(result.links,[]);
 const switched=inspect({url:'https://chat.mistral.ai/work/projects/'+B,sidebar:[own.project,other.project],main:[...own.chats,...other.chats]});
 assert.deepEqual(switched.chats,[otherChat]);
});
test('opening a nested sidebar chat supplies only its explicit owning project',()=>{
 const own=projectGroup(overview,'CityTripXL',[anchor(chat,'Trip planning')]),other=projectGroup('https://chat.mistral.ai/work/projects/'+B,'Other',[anchor('https://chat.mistral.ai/work/'+B)]);
 const sidebar=[own.project,other.project,...own.chats,...other.chats];
 const result=inspect({url:chat,sidebar});assert.deepEqual(result.links,[{href:overview,name:'CityTripXL'}]);assert.equal(result.ambiguous,false);assert.deepEqual(result.chats,[]);
 const standalone=inspect({url:'https://chat.mistral.ai/work/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',sidebar});assert.deepEqual(standalone.links,[]);
});
test('hidden, altered or neighboring sidebar entries cannot assert chat ownership',()=>{
 for(const mutate of [
  group=>{group.project.attributes['data-sidebar']='menu-sub-button';},
  group=>{group.root.attributes['data-sidebar']='menu-sub-item';},
  group=>{group.root.attributes.class='unrelated';},
  group=>{group.root.children.reverse();},
  group=>{group.collapse.attributes.class='unrelated';},
  group=>{group.menu.attributes['data-sidebar']='unrelated';},
  group=>{group.chats[0].shown=false;},
  group=>{group.root.shown=false;},
  group=>{group.list.append(anchor('https://chat.mistral.ai/work/projects/'+B,'Nested other project'));},
  group=>{group.chats[0].attributes['data-sidebar']='menu-sub-button';},
  group=>{group.chats[0].parentElement.attributes['data-sidebar']='menu-sub-item';},
  group=>{group.chats[0].parentElement.attributes.class='unrelated';},
  group=>{group.chats[0].parentElement.children.reverse();},
  group=>{group.chats[0].parentElement.append(node('div'));},
  group=>{group.list.attributes['data-sidebar']='menu-sub';},
  group=>{group.sub.attributes['data-sidebar']='menu';},
  group=>{group.inner.tagName='SECTION';},
  group=>{group.collapse.children=[group.sub];group.sub.parentElement=group.collapse;}
 ]){
  const group=projectGroup(overview,'Project',[anchor(chat)]);mutate(group);
  const sidebar=[group.project,...group.chats];assert.deepEqual(inspect({url:chat,sidebar}).links,[]);
  assert.deepEqual(inspect({url:overview,sidebar,main:[]}).chats,[]);
 }
 const group=projectGroup(overview,'Project',[]),neighbor=anchor(chat,'Unrelated sidebar chat');group.menu.append(node('li',{'data-sidebar':'menu-item'}).append(neighbor));
 assert.deepEqual(inspect({url:chat,sidebar:[group.project,neighbor]}).links,[]);
});
test('multiple explicit sidebar owners remain ambiguous and duplicate overview rows do not supply chats',()=>{
 const first=projectGroup(overview,'One',[anchor(chat)]),second=projectGroup('https://chat.mistral.ai/work/projects/'+B,'Two',[anchor(chat)]);
 const result=inspect({url:chat,sidebar:[first.project,second.project]});assert.equal(result.ambiguous,true);assert.equal(result.links.length,2);
 const duplicate=projectGroup(overview,'Duplicate',[anchor(chat)]);
 assert.deepEqual(inspect({url:overview,sidebar:[first.project,duplicate.project]}).chats,[]);
});
test('verified sidebar chat evidence is canonical, bounded and rejects external credentials and Code groups',()=>{
 const links=[anchor(chat+'?tab=files#modal'),anchor('https://evil.test/work/'+B),anchor('https://user:secret@chat.mistral.ai/work/'+B),anchor('https://chat.mistral.ai:444/work/'+B),
  ...Array.from({length:90},(_,n)=>anchor('https://chat.mistral.ai/work/'+n.toString(16).padStart(8,'0')+'-2222-4333-8444-555555555555'))];
 const own=projectGroup(overview,'Project',links),result=inspect({url:overview,sidebar:[own.project]});
 assert.equal(result.chats.length,64);assert.equal(result.chats[0],chat);assert.ok(result.chats.every(url=>!/[?#@]/.test(url)&&!url.includes(':444')&&!url.includes('evil')));
 const code=projectGroup('https://chat.mistral.ai/code/'+A,'Code',[anchor(chat)]);
 assert.deepEqual(inspect({url:chat,sidebar:[code.project]}).links,[]);
});
test('Code overview and session names come only from their exact Code project link',()=>{
 const code='https://chat.mistral.ai/code/'+A,session=code+'/'+B;
 const sidebar=[anchor(overview,'Work with same UUID'),anchor('https://chat.mistral.ai/code/'+B,'Other Code project'),anchor(session,'Session title'),anchor(code,'  Vibez\n ')];
 assert.equal(inspect({url:code,sidebar,heading:'Wrong generic heading'}).name,'Vibez');
 const current=inspect({url:session,sidebar,heading:'Session heading'});assert.equal(current.name,'Vibez');assert.deepEqual(current.chats,[]);
 const work=inspect({url:overview,sidebar});assert.equal(work.name,'Work with same UUID');
});
test('a stale generic heading never supplies a project name',()=>{
 const code='https://chat.mistral.ai/code/'+A;
 assert.equal(inspect({url:code,heading:'Vibez'}).name,'');
 assert.equal(inspect({url:code+'/'+B,heading:'Session title'}).name,'');
});
test('switching Work and Code cannot copy the previous page heading into the new project',()=>{
 const code='https://chat.mistral.ai/code/'+B;
 assert.equal(inspect({url:overview,sidebar:[anchor(code,'Code Beta')],heading:'Code Beta'}).name,'');
 assert.equal(inspect({url:code,sidebar:[anchor(overview,'Work Alpha')],heading:'Work Alpha'}).name,'');
 assert.equal(inspect({url:overview,sidebar:[anchor(overview,'Work Alpha')],heading:'Code Beta'}).name,'Work Alpha');
});
test('Code draft-session routes retain their explicit parent project until the real session arrives',()=>{
 const code='https://chat.mistral.ai/code/'+A,sidebar=[anchor(overview,'Work with same UUID'),anchor(code,'Vibez')];
 for(const suffix of ['draft%3Asession%3A'+B,'draft%3asession%3a'+B,'draft:session:'+B,'draft%3Asession:'+B,B]){
  const result=inspect({url:code+'/'+suffix,sidebar,heading:'Session title'});
  assert.equal(result.name,'Vibez',suffix);assert.deepEqual(result.chats,[]);
 }
 for(const suffix of ['draft%3Asession%3Anew','draft:other:'+B,'draft%3Asession%3A'+B+'/other','draft%3Asession%3A'+B+'%2Fother','draft%253Asession%253A'+B]){
  assert.equal(inspect({url:code+'/'+suffix,sidebar,heading:'Not a project'}).name,'',suffix);
 }
});
test('Code route validation rejects non-project pages and unsafe project name sources',()=>{
 const code='https://chat.mistral.ai/code/'+A;
 const sidebar=[anchor(code,'Hidden',false),anchor('https://evil.test/code/'+A,'External'),anchor('https://user:secret@chat.mistral.ai/code/'+A,'Credentials'),anchor('https://chat.mistral.ai:444/code/'+A,'Port'),anchor(overview,'Same UUID but Work')];
 assert.equal(inspect({url:code+'/'+B,sidebar}).name,'');
 for(const route of ['/code','/code/extensions','/code/settings','/code/new','/code/'+A+'/new','/code/'+A+'/'+B+'/other']){
  assert.equal(inspect({url:'https://chat.mistral.ai'+route,sidebar:[anchor(code,'Vibez')],heading:'Not a project'}).name,'',route);
 }
});
test('Work and Code breadcrumbs with identical raw UUIDs remain distinct',()=>{
 const code='https://chat.mistral.ai/code/'+A;
 const result=inspect({breadcrumbs:[anchor(overview,'Work'),anchor(code,'Code')]});
 assert.equal(result.ambiguous,true);assert.equal(result.links.length,2);
});
function draftPage({history=[],url='https://chat.mistral.ai/work'}={}){
 let serial=0,editorText='',editorVisible=true,sendVisible=false;
 const listeners={click:[],pointerdown:[],keydown:[],contextmenu:[],popstate:[]},events=[];
 const hiddenSubmit={getClientRects:()=>[],disabled:false,getAttribute:()=>null};
 const send={getClientRects:()=>sendVisible?[{}]:[],disabled:false,getAttribute:()=>null};
 const row={classList:{contains:value=>value==='@container/chat-input-row'},getClientRects:()=>[{}],querySelectorAll:selector=>{assert.equal(selector,'button[type="submit"]');return[hiddenSubmit,send];}};
 const editor={closest:()=>null,classList:{contains:()=>false},getClientRects:()=>editorVisible?[{}]:[],parentElement:{classList:{contains:()=>false},parentElement:row},get textContent(){return editorText;},contains:node=>node===editor};
 const location={href:url};
 const document={addEventListener:(type,handler)=>listeners[type].push(handler),querySelectorAll:selector=>{
  if(selector==='div.ProseMirror[contenteditable="true"]')return[editor];
  if(selector==='a[href*="/work/"]')return history;
  if(selector.startsWith('main header')||selector==='a[href*="/work/projects/"],a[href*="/code/"]'||selector==='main a[href],[role="main"] a[href]'||selector==='main h1,[role="main"] h1,h1')return[];
  throw Error('Unexpected selector '+selector);
 }};
 const window={addEventListener:(type,handler)=>listeners[type].push(handler)};
 const context=vm.createContext({document,location,URL,window,crypto:{randomUUID:()=> (++serial).toString(16).padStart(8,'0')+'-1234-4234-8234-123456789abc'}});
 const run=()=>JSON.parse(vm.runInContext(script,context));
 const fire=(type,event={})=>{events.push(type);for(const fn of listeners[type])fn({isTrusted:true,target:editor,...event});};
 return{run,fire,location,window,editor,send,listeners,set text(value){editorText=value;sendVisible=Boolean(value.trim());},set sendVisible(value){sendVisible=value;},set editorVisible(value){editorVisible=value;}};
}
test('an empty verified home composer gets one per-document draft without reading text into snapshots',()=>{
 const f=draftPage({history:[anchor(chat,'Old chat')]});const first=f.run(),next=f.run();
 assert.equal(first.loose.ready,true);assert.equal(first.loose.nonce,next.loose.nonce);assert.equal(first.loose.document,next.loose.document);assert.deepEqual(first.loose.known,['11111111-2222-4333-8444-555555555555']);assert.equal(first.loose.submitted,null);
 f.text='Private draft text that must never enter the snapshot';assert.ok(!JSON.stringify(f.run()).includes('Private draft text'));
 f.editorVisible=false;assert.equal(f.run().loose,null);
});
test('only trusted plain Enter or the same visible enabled submit records first-send proof',()=>{
 for(const bad of [{isTrusted:false},{shiftKey:true},{ctrlKey:true},{metaKey:true},{altKey:true},{isComposing:true}]){
  const f=draftPage();f.run();f.text='message';f.fire('keydown',{key:'Enter',...bad});assert.equal(f.run().loose.submitted,null);
 }
 const f=draftPage();f.run();f.fire('keydown',{key:'Enter'});assert.equal(f.run().loose.submitted,null);
 f.text='message';f.sendVisible=false;f.fire('keydown',{key:'Enter'});assert.equal(f.run().loose.submitted,null);
 f.sendVisible=true;f.send.disabled=true;f.fire('keydown',{key:'Enter'});assert.equal(f.run().loose.submitted,null);
 f.send.disabled=false;f.fire('keydown',{key:'Enter'});const proof=f.run().loose.submitted;assert.equal(proof.nonce,f.run().loose.nonce);assert.ok(proof.at>0);assert.equal(proof.from,'https://chat.mistral.ai/work');
 const click=draftPage();click.run();click.text='click message';click.fire('click',{target:{closest:s=>s==='button[type="submit"]'?click.send:null}});assert.ok(click.run().loose.submitted);
});
test('a real first-send proof survives the SPA switch and changed saved-chat composer',()=>{
 const f=draftPage();const before=f.run().loose;f.text='message';f.fire('keydown',{key:'Enter'});f.location.href=chat;
 const after=f.run().loose;assert.equal(after.ready,false);assert.equal(after.document,before.document);assert.equal(after.nonce,before.nonce);assert.equal(after.submitted.nonce,before.nonce);
 assert.equal(draftPage({url:chat}).run().loose,null);
});
test('history navigation, popstate, explicit new-home clicks and document replacement invalidate promotion',()=>{
 for(const navigation of ['history','popstate','new-home']){
  const f=draftPage();const before=f.run().loose;f.text='message';f.fire('keydown',{key:'Enter'});
  if(navigation==='popstate')f.fire('popstate');else f.fire('click',{target:{closest:s=>s==='a[href]'?anchor(navigation==='history'?chat:'https://chat.mistral.ai/work'):null}});
  if(navigation==='new-home'){
   const next=f.run().loose;assert.notEqual(next.nonce,before.nonce);assert.equal(next.submitted,null);
  }else{f.location.href=chat;assert.equal(f.run().loose,null);}
 }
 const f=draftPage();f.run();f.text='message';f.fire('keydown',{key:'Enter'});const reloaded=draftPage();assert.equal(reloaded.run().loose.submitted,null);
});

function removalPage({url=chat}={}){
 let now=10000,editorText='';const listeners={click:[],pointerdown:[],keydown:[],contextmenu:[],popstate:[]};
 const own=projectGroup(overview,'Fixture project',[anchor(chat)]),other=projectGroup('https://chat.mistral.ai/work/projects/'+B,'Other',[anchor('https://chat.mistral.ai/work/'+B)]);
 const groups=[own,other],location={href:url};
 for(const g of groups)for(const link of g.chats){const box=link.parentElement.children[1];box.contains=button=>box.children.includes(button);box.append(node('button',{'aria-haspopup':'menu'}));}
 const row={classList:{contains:x=>x==='@container/chat-input-row'},getClientRects:()=>[{}],querySelectorAll:()=>[]};
 const editor={closest:()=>null,getClientRects:()=>[{}],classList:{contains:()=>false},parentElement:row,get textContent(){return editorText;}};
 const sidebar=()=>groups.flatMap(g=>[g.project,...g.chats]);
 const document={addEventListener:(type,fn)=>listeners[type].push(fn),querySelectorAll:selector=>{
  if(selector==='div.ProseMirror[contenteditable="true"]')return[editor];
  if(selector.startsWith('main header')||selector==='main h1,[role="main"] h1,h1'||selector==='main a[href],[role="main"] a[href]')return[];
  if(selector==='a[href*="/work/"]'||selector==='a[href*="/work/projects/"],a[href*="/code/"]')return sidebar();
  throw Error('Unexpected selector '+selector);
 }};
 const window={addEventListener:(type,fn)=>listeners[type].push(fn)};
 const context=vm.createContext({window,document,location,URL,Date:{now:()=>now}});
 const run=()=>JSON.parse(vm.runInContext(script,context));
 const fire=(type,event)=>{for(const fn of listeners[type])fn({isTrusted:true,...event});};
 const menu=(group=own,trusted=true)=>{const button=group.chats[0].parentElement.children[1].children[0];fire('click',{isTrusted:trusted,target:{closest:s=>s==='button,[role="button"]'?button:null}});};
 const remove=(group=own)=>{group.list.children=[];group.chats=[];};
 return{run,fire,location,window,own,other,menu,remove,set text(v){editorText=v;},advance(ms){now+=ms;}};
}
test('removing the current project chat and redirecting home requests its existing project overview',()=>{
 for(const url of [chat,overview]){
  const f=removalPage({url});f.run();f.menu();f.remove();f.location.href='https://chat.mistral.ai/work';
  const result=f.run();assert.equal(result.project_return.project,A);assert.equal(result.project_return.from,url);assert.equal(result.project_return.chat,'11111111-2222-4333-8444-555555555555');assert.equal(result.project_return.reason,'removed_project_chat');
  assert.deepEqual(result.links,[],'home is not misidentified as project context');
 }
});
test('return waits for removal evidence and does not run when a chat is moved to another project',()=>{
 const f=removalPage();f.run();f.menu();f.location.href='https://chat.mistral.ai/work';assert.equal(f.run().project_return,null);
 const moved=f.own.chats[0];f.remove();f.other.list.append(moved.parentElement);f.other.chats.push(moved);assert.equal(f.run().project_return,null);
});
test('normal new-chat navigation, toolbar reset, back navigation, typing and cancellation stay outside the project',()=>{
 for(const mode of ['new-chat-link','new-chat-button','native-reset','popstate','escape','shortcut','typed','expired']){
  const f=removalPage();f.run();f.menu();
  if(mode==='new-chat-link')f.fire('click',{target:{closest:s=>s==='a[href]'?anchor('https://chat.mistral.ai/work'):null}});
  if(mode==='new-chat-button')f.fire('click',{target:{closest:()=>null}});
  if(mode==='native-reset')f.window.__vibezProjectReturn.reset();
  if(mode==='popstate')f.fire('popstate',{});
  if(mode==='escape')f.fire('keydown',{key:'Escape'});
  if(mode==='shortcut')f.fire('keydown',{key:'o',ctrlKey:true});
  if(mode==='typed')f.text='Do not redirect a user writing a different chat';
  if(mode==='expired')f.advance(31000);
  f.remove();f.location.href='https://chat.mistral.ai/work';assert.equal(f.run().project_return,null,mode);
 }
});
test('synthetic menu clicks, unrelated project chats and missing project evidence never request a return',()=>{
 for(const mode of ['untrusted','other-project','missing-project','wrong-route']){
  const f=removalPage();f.run();f.menu(mode==='other-project'?f.other:f.own,mode!=='untrusted');f.remove();
  if(mode==='missing-project')f.own.root.shown=false;
  f.location.href=mode==='wrong-route'?'https://chat.mistral.ai/work/'+B:'https://chat.mistral.ai/work';assert.equal(f.run().project_return,null,mode);
 }
});
test('the Work/Code mode tab that links to the open project never supplies the project name',()=>{
 // Measured on 13 Nov 2026: inside a project the "Work" tab (role=tab) links to
 // the project itself and comes before the real project link, so every project
 // was named "Work".
 const tab=anchor(overview,'Work');tab.attributes.role='tab';
 const result=inspect({url:overview,sidebar:[tab,anchor(overview,'Alpha')],breadcrumbs:[tab]});
 assert.equal(result.name,'Alpha');assert.equal(result.ambiguous,false);
 assert.equal(inspect({url:overview,sidebar:[tab]}).name,'','with only the mode tab there is no name rather than a wrong one');
});
