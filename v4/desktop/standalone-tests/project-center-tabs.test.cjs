'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../src-tauri/src/project_details.js'),'utf8');
const ID='229ee257-4177-4f98-969c-3055311c7cae',CHAT='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
class Style {
 constructor(){this.values=new Map();}
 getPropertyValue(k){return this.values.get(k)?.value||'';}
 getPropertyPriority(k){return this.values.get(k)?.priority||'';}
 setProperty(k,value,priority=''){this.values.set(k,{value,priority});}
 removeProperty(k){this.values.delete(k);}
}
function matches(node,selector){
 if(selector.includes(','))return selector.split(',').some(part=>matches(node,part.trim()));
 const attributes=[...selector.matchAll(/\[([\w-]+)(\$?=)?(?:"([^"]*)")?\]/g)];
 const base=selector.replace(/\[[^\]]+\]/g,'');
 const tag=base.match(/^([\w-]+)/)?.[1];if(tag&&node.tagName!==tag.toUpperCase())return false;
 for(const cls of [...base.matchAll(/\.([\w-]+)/g)].map(m=>m[1]))if(!node.classes.has(cls))return false;
 for(const [,name,op,value]of attributes){const actual=name==='id'?node.id:node.getAttribute(name);if(op==='='?actual!==value:op==='$='?!actual?.endsWith(value):actual===null)return false;}
 return Boolean(tag||attributes.length||base.startsWith('.'));
}
class Node {
 constructor(tag,text='',classes='',attrs={}){this.tagName=tag.toUpperCase();this.text=text;this.attrs=attrs;this.classes=new Set(classes.split(' ').filter(Boolean));this.classList={contains:k=>this.classes.has(k)};this.children=[];this.style=new Style();this.id='';this.hidden=false;this.disabled=false;this.checked=false;this.clicked=0;this.events=[];this.listeners={};}
 append(...children){for(const child of children){child.parentElement=this;this.children.push(child);}return this;}
 replace(...children){for(const old of this.children)old.parentElement=null;this.children=[];return this.append(...children);}
 get textContent(){return this.text+this.children.map(e=>e.textContent).join('');}
 set textContent(value){this.replace();this.text=String(value);}
 get innerText(){return this.textContent;}
 get firstElementChild(){return this.children[0]||null;}
 get childElementCount(){return this.children.length;}
 get isConnected(){let node=this;while(node.parentElement)node=node.parentElement;return node.connectedRoot===true;}
 getAttribute(k){return k==='id'?this.id||null:this.attrs[k]??null;}
 setAttribute(k,value){if(k==='id')this.id=value;else this.attrs[k]=String(value);}
 getClientRects(){if(!this.isConnected)return[];for(let n=this;n;n=n.parentElement)if(n.hidden||n.style.getPropertyValue('display')==='none')return[];return[{}];}
 contains(node){for(let n=node;n;n=n.parentElement)if(n===this)return true;return false;}
 closest(selector){for(let n=this;n;n=n.parentElement)if(matches(n,selector))return n;return null;}
 querySelectorAll(selector){const found=[];const walk=node=>{for(const child of node.children){if(matches(child,selector))found.push(child);walk(child);}};walk(this);return found;}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 addEventListener(type,handler){(this.listeners[type]??=[]).push(handler);}
 removeEventListener(type,handler){this.listeners[type]=(this.listeners[type]||[]).filter(h=>h!==handler);}
 click(){this.clicked++;if(this.tagName==='INPUT')this.checked=!this.checked;this.onClick?.();}
 dispatchEvent(event){this.events.push(event);this.onEvent?.(event);for(const handler of this.listeners[event.type]||[])handler(event);return true;}
}
function fixture({english=false,active='conversations',draft='',focused=false,attachment=false}={}){
 const p=t=>new Node('p',t),button=new Node('button',english?'Customize':'Aanpassen','',{type:'button'});
 const first=new Node('div').append(p(english?'Tone':'Toon'),p(english?'Default':'Standaard'),p(english?'Instructions':'Instructies'),p('Project rules.'),button);
 const checkbox=new Node('input','','',{type:'checkbox',role:'checkbox'});checkbox.id='context';checkbox.checked=true;
 const label=new Node('label',english?'Include project chats':'Projectgesprekken toevoegen');label.control=checkbox;
 const context=new Node('div').append(p(english?'Additional context':'Aanvullende context'),new Node('div').append(checkbox,label));
 let sidebar=new Node('div','','col-start-2 overflow-y-auto row-start-1 row-end-4').append(first,context,new Node('hr'),new Node('div','Private uploaded files must not be read.'));
 const tabs=new Node('div','','grid grid-cols-2',{role:'tablist'});
 const convTab=new Node('button',english?'Conversations':'Gesprekken','',{type:'button',role:'tab','aria-selected':'true'});convTab.id='radix-fixture-trigger-conversations';
 const settingsTab=new Node('button',english?'Settings':'Instellingen','',{type:'button',role:'tab','aria-selected':'false'});settingsTab.id='radix-fixture-trigger-settings';tabs.append(convTab,settingsTab);
 const conversations=new Node('div','','w-full flex h-full min-h-0 flex-col',{role:'tabpanel','aria-labelledby':convTab.id});conversations.id='radix-fixture-content-conversations';
 const settingsPanel=new Node('div','','w-full h-full min-h-0',{role:'tabpanel','aria-labelledby':settingsTab.id});settingsPanel.id='radix-fixture-content-settings';
 convTab.attrs['aria-controls']=conversations.id;settingsTab.attrs['aria-controls']=settingsPanel.id;
 const root=new Node('div','','w-full flex h-full min-h-0 flex-col').append(tabs,conversations,settingsPanel);
 const heading=new Node('div','Project name'),grid=new Node('div','','grid grid-cols-1 grid-rows-[auto_1fr]').append(heading,root);
 const navigation=new Node('nav','Left project navigation'),main=new Node('main').append(navigation,grid);main.connectedRoot=true;
 const dialogs=[];let editor,composer,list,row,send,fileInput,allowSelection=true,queries=0,revision=0,documentFocused=true;
 const listeners={};
 const document={activeElement:null,hasFocus:()=>documentFocused,addEventListener(type,handler){(listeners[type]??=[]).push(handler);},removeEventListener(type,handler){listeners[type]=(listeners[type]||[]).filter(h=>h!==handler);},querySelectorAll(selector){queries++;return main.querySelectorAll(selector).concat(dialogs.filter(e=>matches(e,selector)));}};
 const fire=(type,target=editor,extra={})=>{for(const handler of listeners[type]||[])handler({type,target,isTrusted:true,...extra});};
 const mountComposer=(text='',hasAttachment=false)=>{
  const paragraph=new Node('p',text);if(!text)paragraph.append(new Node('br','','ProseMirror-trailingBreak'));
  editor=new Node('div','','ProseMirror',{contenteditable:'true'}).append(paragraph);
  send=new Node('button','','',{type:'submit'});send.disabled=!text&&!hasAttachment;send.style.setProperty('display','none');
  const middle=new Node('div','','scrollbar-subtle min-h-0 min-w-0 grow overflow-y-auto').append(send,new Node('div','','caret-brand-500 break-words').append(editor));
  row=new Node('div','','@container/chat-input-row min-h-0 min-w-0 flex items-center gap-1').append(
   new Node('div').append(new Node('button','','',{type:'button'})),middle,new Node('div').append(new Node('button','','',{type:'button'}),new Node('button','','',{type:'button'})));
  const grid=new Node('div','','grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_0px]').append(row);
  const focus=new Node('div','','flex min-h-0 flex-1 flex-col gap-3 overflow-hidden shadow click-focus-input').append(grid);
  const card=new Node('div','','bg-card flex min-h-0 flex-col overflow-hidden max-h-100').append(focus);
  const bar=new Node('div','','relative flex min-h-0 cursor-text flex-col',{'data-chat-input-bar':'true'}).append(card);
  const content=new Node('div','','flex w-full max-w-full min-w-0 flex-col gap-4').append(bar);
  const form=new Node('form','','w-full max-w-full min-w-0').append(content);
  composer=new Node('div','','col-start-1 col-end-1 mx-auto w-full max-w-(--breakpoint-md) pb-4 md:pb-8').append(form);
  fileInput=null;
  if(hasAttachment){fileInput=new Node('input','','',{type:'file'});fileInput.files=[{name:'selected-fixture.txt'}];composer.append(fileInput);}
  const chat=new Node('a','Private chat title');chat.href='https://chat.mistral.ai/work/'+CHAT;
  list=new Node('div','','col-start-1 col-end-1 h-full transition-all flex flex-col gap-3 overflow-auto').append(chat);
  conversations.append(list,composer);revision++;
 };
 const select=(value,initial=false)=>{
  const settings=value==='settings';convTab.attrs['aria-selected']=String(!settings);settingsTab.attrs['aria-selected']=String(settings);
  conversations.hidden=settings;settingsPanel.hidden=!settings;conversations.replace();settingsPanel.replace();document.activeElement=null;
  if(settings)settingsPanel.append(sidebar);else mountComposer(initial?draft:'',initial?attachment:false);
 };
 convTab.onEvent=event=>{if(event.type==='mousedown'&&allowSelection)select('conversations');};
 settingsTab.onEvent=event=>{if(event.type==='mousedown'&&allowSelection)select('settings');};
 select(active,true);if(focused)document.activeElement=editor;
 const location={protocol:'https:',hostname:'chat.mistral.ai',port:'',pathname:'/work/projects/'+ID,href:'https://chat.mistral.ai/work/projects/'+ID};
 const window={},sandbox={document,location,window,URL,Date,MouseEvent:class{constructor(type,options){this.type=type;Object.assign(this,options);}}};vm.createContext(sandbox);
 const run=(action=null,enabled=null,expected=ID)=>JSON.parse(vm.runInContext(source.replace('__VIBEZ_PROJECT_ID__',JSON.stringify(expected)).replace('__VIBEZ_PROJECT_ACTION__',JSON.stringify(action)).replace('__VIBEZ_PROJECT_ENABLED__',JSON.stringify(enabled)),sandbox));
 const settle=(action=null,enabled=null)=>{let result;for(let i=0;i<12;i++){result=run(action,enabled);if(!result.pending)return result;}assert.fail('Project presentation did not settle');};
 return{run,settle,select,tabs,root,grid,main,heading,navigation,first,checkbox,label,button,convTab,settingsTab,conversations,settingsPanel,dialogs,window,location,document,
  get editor(){return editor;},get composer(){return composer;},get list(){return list;},get row(){return row;},get send(){return send;},get fileInput(){return fileInput;},get sidebar(){return sidebar;},set sidebar(value){sidebar=value;},get revision(){return revision;},get queries(){return queries;},fire,set documentFocused(value){documentFocused=value;},set allowSelection(value){allowSelection=value;}};
}
function assertComposerOnly(f){
 assert.equal(f.root.getClientRects().length,1,'project root remains visible');
 assert.notEqual(f.root.style.getPropertyValue('visibility'),'hidden','project root must not remain visually hidden');
 assert.equal(f.conversations.getClientRects().length,1,'native conversation panel remains visible');
 assert.equal(f.editor.getClientRects().length,1,'original native editor is visible');
 assert.equal(f.composer.getClientRects().length,1,'native composer wrapper is visible');
 assert.equal(f.tabs.getClientRects().length,0,'duplicate tabs stay hidden');
 assert.equal(f.list.getClientRects().length,0,'duplicate conversation list stays hidden');
 assert.equal(f.heading.getClientRects().length,1);assert.equal(f.navigation.getClientRects().length,1);
}

test('project overview keeps a native composer while hiding only duplicate tabs and conversation list',()=>{
 const f=fixture();const result=f.settle();assert.equal(result.available,true);assert.equal(result.instructions,'Project rules.');assertComposerOnly(f);
 const editor=f.editor,composer=f.composer,revision=f.revision,tabEvents=f.settingsTab.events.length;
 for(let i=0;i<5;i++){assert.equal(f.run().available,true);assertComposerOnly(f);}
 assert.equal(f.editor,editor);assert.equal(f.composer,composer);assert.equal(f.revision,revision);assert.equal(f.settingsTab.events.length,tabEvents);
 assert.ok(!JSON.stringify(result).includes('Private'));
});
test('initial active settings and translated labels return to a visible original composer',()=>{
 for(const english of [false,true]){const f=fixture({english,active:'settings'});const result=f.settle();assert.equal(result.available,true);assertComposerOnly(f);assert.equal(result.settings[0].label,english?'Tone':'Toon');}
});
test('nonempty drafts and focused editors are never automatically unmounted to capture settings',()=>{
 for(const options of [{draft:'Unsent private text'},{focused:true}]){
  const f=fixture(options),editor=f.editor;const result=f.run();assert.equal(f.settingsTab.events.length,0);assert.equal(f.editor,editor);assert.equal(f.editor.getClientRects().length,1);
  assert.ok(!JSON.stringify(result).includes('Unsent private text'));
 }
});
test('a selected attachment with no message text prevents automatic tab switching',()=>{
 const f=fixture({attachment:true}),editor=f.editor;f.run();assert.equal(f.settingsTab.events.length,0);assert.equal(f.editor,editor);assert.equal(f.fileInput.files.length,1);assert.equal(f.editor.getClientRects().length,1);
});
test('a draft typed after bootstrap survives repeated idle synchronization and rejected right actions',()=>{
 const f=fixture();assert.equal(f.settle().available,true);const editor=f.editor;editor.textContent='A private unsent draft';f.document.activeElement=editor;
 const tabEvents=f.settingsTab.events.length;for(let i=0;i<4;i++)f.run();
 const result=f.run('instructions');assert.notEqual(result.acted,true);assert.notEqual(result.pending,true);assert.equal(f.settingsTab.events.length,tabEvents);assert.equal(f.editor,editor);assert.equal(editor.textContent,'A private unsent draft');assertComposerOnly(f);
});
test('explicit right-side instructions and context actions complete then restore the project composer',()=>{
 const f=fixture();assert.equal(f.settle().available,true);
 const opened=f.settle('instructions');assert.equal(opened.acted,true);assert.equal(f.button.clicked,1);assert.equal(f.checkbox.clicked,0);
 assert.equal(f.settle('finish').available,true);assertComposerOnly(f);
 const changed=f.settle('context',false);assert.equal(changed.acted,true);assert.equal(f.checkbox.checked,false);assert.equal(f.checkbox.clicked,1);
 assert.equal(f.settle('finish').available,true);assertComposerOnly(f);assert.equal(f.run().context_checked,false);
});
test('context requests remain desired-state idempotent and never submit a message',()=>{
 const f=fixture();f.settle();assert.equal(f.settle('context',true).unchanged,true);assert.equal(f.checkbox.clicked,0);f.settle('finish');assertComposerOnly(f);assert.equal(f.send.clicked,0);
});
test('an open native dialog prevents automatic tab switching and repeated right actions',()=>{
 const f=fixture();const dialog=new Node('div','','',{role:'dialog'});dialog.connectedRoot=true;f.dialogs.push(dialog);
 f.run();assert.equal(f.settingsTab.events.length,0);assert.equal(f.editor.getClientRects().length,1);
 const g=fixture();g.settle();g.dialogs.push(dialog);assert.notEqual(g.run('instructions').acted,true);assert.equal(g.button.clicked,0);
});
test('chat navigation restores exact original styles without hiding actual chat content',()=>{
 const f=fixture();f.tabs.style.setProperty('display','grid','important');f.settle();const list=f.list;list.style.setProperty('color','blue');
 f.location.pathname='/work/'+CHAT;assert.equal(f.run().available,false);assert.equal(f.tabs.style.getPropertyValue('display'),'grid');assert.equal(f.tabs.style.getPropertyPriority('display'),'important');assert.equal(list.style.getPropertyValue('display'),'');assert.equal(list.style.getPropertyValue('color'),'blue');assert.equal(f.root.style.getPropertyValue('display'),'');assert.equal(f.window.__vibezProjectSidebar,undefined);
});
test('untrusted routes and nonproject pages never manipulate project tabs',()=>{
 for(const mutate of [f=>f.location.hostname='example.org',f=>f.location.pathname='/code/'+ID,f=>f.location.pathname='/work/projects/'+ID+'/settings',f=>f.location.port='444']){
  const f=fixture();mutate(f);assert.equal(f.run().available,false);assert.equal(f.queries,0);assert.equal(f.settingsTab.events.length,0);assert.equal(f.convTab.events.length,0);
 }
});
test('unknown tab or composer structures restore official controls instead of hiding an input',()=>{
 for(const mutate of [f=>f.settingsPanel.attrs['aria-labelledby']='other',f=>f.convTab.attrs['aria-controls']='other',f=>f.settingsTab.tagName='A',f=>f.grid.classes.delete('grid-cols-1'),f=>f.root.append(new Node('div')),f=>f.composer.classes.delete('mx-auto'),f=>f.conversations.append(new Node('div'))]){
  const f=fixture();mutate(f);assert.equal(f.run().available,false);assert.equal(f.root.style.getPropertyValue('display'),'');assert.equal(f.tabs.style.getPropertyValue('display'),'');assert.equal(f.editor.getClientRects().length,1);assert.equal(f.settingsTab.events.length,0);
 }
});
test('website declining selection does not cause endless tab switching or leave the composer hidden',()=>{
 const f=fixture();f.allowSelection=false;f.run();for(let i=0;i<4;i++)f.run();assert.ok(f.settingsTab.events.length<=1);assert.equal(f.editor.getClientRects().length,1);assert.equal(f.root.style.getPropertyValue('display'),'');assert.notEqual(f.root.style.getPropertyValue('visibility'),'hidden');
});
test('a layout change after presentation restores original list, tabs and composer styles',()=>{
 const f=fixture();f.tabs.style.setProperty('display','grid','important');assert.equal(f.settle().available,true);const composer=f.composer,list=f.list;
 f.root.append(new Node('div','Unrecognized new section'));const result=f.run();assert.equal(result.available,false);
 assert.equal(f.tabs.style.getPropertyValue('display'),'grid');assert.equal(f.tabs.style.getPropertyPriority('display'),'important');assert.equal(list.style.getPropertyValue('display'),'');assert.equal(composer.style.getPropertyValue('margin-top'),'');assert.equal(f.editor.getClientRects().length,1);assert.equal(f.root.style.getPropertyValue('visibility'),'');
});
test('temporary native dialogs can close and bootstrap then completes without sending a chat',()=>{
 const f=fixture(),dialog=new Node('div','','',{role:'dialog'});dialog.connectedRoot=true;f.dialogs.push(dialog);f.run();assert.equal(f.settingsTab.events.length,0);
 f.dialogs.length=0;assert.equal(f.settle().available,true);assertComposerOnly(f);assert.equal(f.send.clicked,0);
});
test('explicit context refresh reads newly mounted original project settings after the round trip',()=>{
 const f=fixture();f.settle();const fresh=fixture({active:'settings'});fresh.first.children[3].text='New project rules from Mistral.';f.sidebar=fresh.sidebar;
 const action=f.settle('context',false);assert.equal(action.acted,true);assert.equal(fresh.checkbox.clicked,1);assert.equal(f.checkbox.clicked,0);
 assert.equal(f.settle('finish').available,true);assert.equal(f.run().instructions,'New project rules from Mistral.');assertComposerOnly(f);
});
test('even whitespace text beside an empty-editor trailing break is preserved before bootstrap',()=>{
 const f=fixture();const editor=f.editor;editor.children[0].text=' ';
 const result=f.run();assert.equal(f.settingsTab.events.length,0);assert.equal(f.editor,editor);assert.equal(editor.textContent,' ');assert.equal(editor.getClientRects().length,1);assert.ok(!JSON.stringify(result).includes('Private chat title'));
});
test('stale editor focus in an inactive webview does not block an explicit right-side action',()=>{
 const f=fixture();f.settle();const editor=f.editor;f.document.activeElement=editor;f.fire('input');f.documentFocused=false;
 const result=f.settle('instructions');assert.equal(result.acted,true);assert.equal(f.button.clicked,1);assert.equal(f.settle('finish').finished,true);assertComposerOnly(f);
});
test('an actually focused empty editor remains mounted when a right-side action is requested',()=>{
 const f=fixture();f.settle();const editor=f.editor;f.document.activeElement=editor;f.documentFocused=true;
 const events=f.settingsTab.events.length,result=f.run('instructions');assert.equal(result.reason,'composer_busy');assert.equal(f.settingsTab.events.length,events);assert.equal(f.editor,editor);assert.equal(f.editor.getClientRects().length,1);
});
test('trusted upload-control pointer interaction prevents a later automatic empty-composer probe',()=>{
 for(const kind of ['pointerdown','mousedown']){
  const f=fixture(),dialog=new Node('div','','',{role:'dialog'});dialog.connectedRoot=true;f.dialogs.push(dialog);f.run();
  const editor=f.editor,upload=f.row.children[0].children[0];f.fire(kind,upload);f.dialogs.length=0;
  const result=f.run();assert.equal(result.reason,'composer_busy');assert.equal(f.settingsTab.events.length,0);assert.equal(f.editor,editor);assert.equal(f.editor.getClientRects().length,1);
 }
});

test('returning to a project after deletion presents its empty native project composer, never a loose chat',()=>{
 const f=fixture();assert.equal(f.location.pathname,'/work/projects/'+ID);
 const result=f.settle();assert.equal(result.available,true);assertComposerOnly(f);
 assert.equal(f.editor.textContent,'');assert.equal(f.send.clicked,0,'no message or chat is created automatically');
 assert.equal(f.location.pathname,'/work/projects/'+ID,'new conversation starts from the same project route');
 assert.equal(f.run().instructions,'Project rules.','the native project context remains available');
});
