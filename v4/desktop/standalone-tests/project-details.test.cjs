'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../src-tauri/src/project_details.js'),'utf8');
const ID='229ee257-4177-4f98-969c-3055311c7cae';
class Style {
 constructor(){this.properties=new Map();}
 getPropertyValue(k){return this.properties.get(k)?.value||'';}
 getPropertyPriority(k){return this.properties.get(k)?.priority||'';}
 setProperty(k,value,priority=''){this.properties.set(k,{value,priority});}
 removeProperty(k){this.properties.delete(k);}
}
class Node {
 constructor(tag,text='',classes='',attributes={}){this.tagName=tag.toUpperCase();this.valueText=text;this.classes=new Set(classes.split(' ').filter(Boolean));this.classList={contains:name=>this.classes.has(name)};this.attributes=attributes;this.children=[];this.style=new Style();this.disabled=false;this.clicked=0;this.checked=false;this.id='';}
 append(...children){for(const node of children){node.parentElement=this;this.children.push(node);}return this;}
 get textContent(){return this.valueText+this.children.map(n=>n.textContent).join('');}
 getAttribute(k){return this.attributes[k]??null;}
 getClientRects(){return this.style.getPropertyValue('display')==='none'?[]:[{}];}
 querySelectorAll(selector){const all=[];function walk(node){for(const child of node.children){all.push(child);walk(child);}}walk(this);if(selector==='input[type="checkbox"][role="checkbox"]')return all.filter(n=>n.tagName==='INPUT'&&n.attributes.type==='checkbox'&&n.attributes.role==='checkbox');if(selector==='label')return all.filter(n=>n.tagName==='LABEL');throw Error('Unexpected broad selector: '+selector);}
 click(){this.clicked++;if(this.tagName==='INPUT')this.checked=!this.checked;}
}
function fixture(english=false){
 const p=t=>new Node('p',t),button=new Node('button',english?'Customize':'Aanpassen','',{type:'button'});
 const first=new Node('div').append(p(english?'Tone':'Toon'),p(english?'Default (Global)':'Standaard (Globaal)'),p(english?'Instructions':'Instructies'),p('User project instructions.'),button);
 const checkbox=new Node('input','','',{type:'checkbox',role:'checkbox'});checkbox.checked=true;checkbox.id='context-control';
 const label=new Node('label',english?'Include chats from other projects as context':'Voeg chats van andere projecten toe als context');label.control=checkbox;label.htmlFor=checkbox.id;
 const context=new Node('div').append(p(english?'Additional context':'Aanvullende context'),new Node('div').append(checkbox,label));
 const sidebar=new Node('div','','col-start-2 overflow-y-auto row-start-1 row-end-4').append(first,context,new Node('hr'),new Node('div','Upload-only controls are outside the snapshot.'));
 const grid=new Node('div','','grid grid-cols-[1fr_400px] grid-rows-[auto_1fr_auto]').append(new Node('main','Never read chat or file content.'),sidebar);
 const nodes=[sidebar],dialogs=[];let queries=0;
 const document={querySelectorAll(selector){queries++;if(selector==='div.col-start-2')return nodes;if(selector==='button[role="tab"][id$="-trigger-settings"]')return [];if(selector==='[role="dialog"]')return dialogs;throw Error('Unexpected selector: '+selector);}};
 const location={protocol:'https:',hostname:'chat.mistral.ai',port:'',pathname:'/work/projects/'+ID};
 const window={};const sandbox={document,location,window};vm.createContext(sandbox);
 const run=(action=null,enabled=null,expected=ID)=>JSON.parse(vm.runInContext(source.replace('__VIBEZ_PROJECT_ID__',JSON.stringify(expected)).replace('__VIBEZ_PROJECT_ACTION__',JSON.stringify(action)).replace('__VIBEZ_PROJECT_ENABLED__',JSON.stringify(enabled)),sandbox));
 return {run,sidebar,grid,first,context,checkbox,label,button,nodes,dialogs,location,window,get queries(){return queries;}};
}
test('verified overview mirrors only the three allowed sections and stays readable while hidden',()=>{
 const f=fixture();const r=f.run();assert.equal(r.available,true);assert.equal(r.instructions,'User project instructions.');assert.equal(r.tone,'Standaard (Globaal)');assert.equal(r.context_checked,true);assert.deepEqual(r.settings.map(x=>x.kind),['tone','instructions','context']);
 assert.equal(f.sidebar.style.getPropertyValue('display'),'none');assert.equal(f.grid.style.getPropertyValue('grid-template-columns'),'minmax(0, 1fr)');assert.deepEqual(f.run(),r);
 assert.ok(!JSON.stringify(r).includes('Upload-only'));assert.ok(!JSON.stringify(r).includes('Never read'));
 assert.equal(r.settings[0].action,undefined);assert.equal(r.settings[1].action,'instructions');assert.equal(r.settings[2].action,'context');
});
test('English labels share the same proved structural boundary',()=>{const f=fixture(true);const r=f.run();assert.equal(r.available,true);assert.equal(r.settings[0].label,'Tone');assert.equal(r.settings[1].label,'Instructions');});
test('German and Arabic headings use the same structure without guessing their translations',()=>{
 for(const headings of [['Ton','Anweisungen','Zusätzlicher Kontext'],['النبرة','التعليمات','سياق إضافي']]){
  const f=fixture();f.first.children[0].valueText=headings[0];f.first.children[2].valueText=headings[1];f.context.children[0].valueText=headings[2];
  const r=f.run();assert.equal(r.available,true);assert.deepEqual(r.settings.map(x=>x.label),headings);
 }
});
test('navigation away or a different project restores exact prior style properties',()=>{
 const f=fixture();f.sidebar.style.setProperty('display','flex');f.grid.style.setProperty('column-gap','3rem','important');f.run();
 f.location.pathname='/work/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';assert.equal(f.run().available,false);assert.equal(f.sidebar.style.getPropertyValue('display'),'flex');assert.equal(f.grid.style.getPropertyValue('column-gap'),'3rem');assert.equal(f.grid.style.getPropertyPriority('column-gap'),'important');assert.equal(f.grid.style.getPropertyValue('grid-template-columns'),'');
 const g=fixture();assert.equal(g.run(null,null,'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa').available,false);assert.equal(g.queries,0);assert.equal(g.button.clicked,0);
});
test('ambiguous or changed layout fails closed and restores the original sidebar',()=>{
 const f=fixture();f.run();f.first.children.push(new Node('button','Unrelated action'));assert.equal(f.run().available,false);assert.equal(f.sidebar.style.getPropertyValue('display'),'');
 const g=fixture();const extra=fixture();g.nodes.push(extra.sidebar);assert.equal(g.run().available,false);assert.equal(g.button.clicked,0);
});
test('only the verified instructions button is invoked and visible dialogs block repeated actions',()=>{
 const f=fixture();assert.equal(f.run('instructions').acted,true);assert.equal(f.button.clicked,1);assert.equal(f.checkbox.clicked,0);
 f.dialogs.push(new Node('div'));assert.equal(f.run('instructions').reason,'dialog_open');assert.equal(f.button.clicked,1);
 const g=fixture();assert.equal(g.run('tone').acted,false);assert.equal(g.button.clicked,0);g.button.disabled=true;assert.equal(g.run('instructions').acted,false);
});
test('context requests are desired-state idempotent and use only the associated checkbox',()=>{
 const f=fixture();assert.equal(f.run('context',true).unchanged,true);assert.equal(f.checkbox.clicked,0);
 assert.equal(f.run('context',false).acted,true);assert.equal(f.checkbox.checked,false);assert.equal(f.checkbox.clicked,1);assert.equal(f.button.clicked,0);
 assert.equal(f.run('context',false).unchanged,true);assert.equal(f.checkbox.clicked,1);
 const g=fixture();g.label.control=null;g.label.htmlFor='different';assert.equal(g.run('context',false).available,false);assert.equal(g.checkbox.clicked,0);
});
test('decorative empty checkbox labels do not hide the current official overview',()=>{
 const f=fixture(),decoration=new Node('label','');decoration.control=f.checkbox;decoration.htmlFor=f.checkbox.id;
 f.context.children[1].append(decoration);assert.equal(f.run().available,true);assert.equal(f.run().context_label,f.label.textContent);
 f.context.children[1].append(new Node('label','Another nonempty label'));assert.equal(f.run().available,false);
});
test('snapshots bound instruction text and reject unknown origins before DOM access',()=>{
 const f=fixture();f.first.children[3].valueText='x'.repeat(12000);assert.equal(f.run().instructions.length,8000);
 const g=fixture();g.location.hostname='example.org';assert.equal(g.run().available,false);assert.equal(g.queries,0);
});

// Form boundary recorded from the official instructions dialog in test.50.
// This fixture never loads Mistral or accesses an actual account/project.
const rulesSource=fs.readFileSync(path.join(__dirname,'../src-tauri/src/project_rules_form.js'),'utf8');
const NONCE='a'.repeat(32);
class RulesNode extends Node {
 constructor(tag,text='',classes='',attributes={}){super(tag,text,classes,attributes);this.isConnected=true;this._value='';this.events=[];}
 get value(){return this._value;}
 set value(value){this._value=value;}
 dispatchEvent(event){this.events.push(event.type);return true;}
 querySelectorAll(selector){
  const nodes=[];const walk=node=>{for(const child of node.children){nodes.push(child);walk(child);}};walk(this);
  if(selector==='form')return nodes.filter(node=>node.tagName==='FORM');
  if(selector==='h2')return nodes.filter(node=>node.tagName==='H2');
  if(selector==='textarea')return nodes.filter(node=>node.tagName==='TEXTAREA');
  if(selector==='select[name="preset"]')return nodes.filter(node=>node.tagName==='SELECT'&&node.attributes.name==='preset');
  if(selector==='input[type="checkbox"][role="checkbox"]')return nodes.filter(node=>node.tagName==='INPUT'&&node.attributes.type==='checkbox'&&node.attributes.role==='checkbox');
  throw Error('Unexpected rules selector: '+selector);
 }
}
function rulesFixture(){
 const dialog=new RulesNode('div','','',{role:'dialog','aria-labelledby':'instructions-heading'});
 const heading=new RulesNode('h2','Instructies');heading.id='instructions-heading';
 const form=new RulesNode('form');form.id='instructions-form';
 const field=new RulesNode('textarea','','',{name:'custom'});field.value='Original project rules.';
 const preset=new RulesNode('select','','',{name:'preset'}),checkbox=new RulesNode('input','','',{type:'checkbox',role:'checkbox'});
 const submit=new RulesNode('button','Opslaan','',{type:'submit'});
 const close=new RulesNode('button','','absolute top-4 right-4',{type:'button'}).append(new RulesNode('svg'),new RulesNode('span','Close','sr-only'));
 for(const node of [field,preset,checkbox,submit])node.form=form;
 form.append(new RulesNode('div').append(preset),new RulesNode('div').append(field),checkbox,submit);
 dialog.append(heading,form,close);
 const dialogs=[dialog];let queries=0;
 const document={querySelectorAll(selector){queries++;assert.equal(selector,'[role="dialog"]');return dialogs.filter(node=>node.isConnected);}};
 close.click=()=>{close.clicked++;dialog.isConnected=false;};
 submit.click=()=>{submit.clicked++;dialog.isConnected=false;};
 const location={protocol:'https:',hostname:'chat.mistral.ai',port:'',pathname:'/work/projects/'+ID};
 const window={},sandbox={window,document,location,HTMLTextAreaElement:RulesNode,Event:class{constructor(type,options){this.type=type;this.bubbles=options.bubbles;}}};vm.createContext(sandbox);
 const run=(action,{project=ID,nonce=NONCE,expected=null,value=null}={})=>{
  const boundary=rulesSource.lastIndexOf(')(__VIBEZ_RULES_PROJECT__');
  return JSON.parse(vm.runInContext(rulesSource.slice(0,boundary)+')('+[project,action,nonce,expected,value].map(JSON.stringify).join(', ')+')',sandbox));
 };
 return {run,dialog,form,field,preset,checkbox,submit,close,heading,dialogs,location,window,get queries(){return queries;}};
}
test('reading project rules closes only the proved form without submitting or changing any field',()=>{
 const f=rulesFixture();f.field.value='  Exact whitespace\n';const result=f.run('read');
 assert.equal(result.ready,true);assert.equal(result.value,'  Exact whitespace\n');assert.equal(f.close.clicked,1);assert.equal(f.submit.clicked,0);assert.equal(f.field.events.length,0);
 assert.equal(f.preset.events.length,0);assert.equal(f.checkbox.clicked,0);
});
test('only explicit submit after nonce-bound fill changes the native instructions; cancelling never submits',()=>{
 const f=rulesFixture();assert.equal(f.run('submit').reason,'context_changed');assert.equal(f.submit.clicked,0);
 assert.equal(f.run('fill',{expected:f.field.value,value:'Updated rules.'}).filled,true);assert.equal(f.submit.clicked,0);
 assert.equal(f.field.value,'Updated rules.');assert.deepEqual(f.field.events,['input','change']);
 assert.equal(f.run('submit',{nonce:'b'.repeat(32)}).reason,'context_changed');assert.equal(f.submit.clicked,0);
 assert.equal(f.run('submit').submitted,true);assert.equal(f.submit.clicked,1);assert.equal(f.run('status').closed,true);
 const g=rulesFixture();g.run('fill',{expected:g.field.value,value:'Local draft'});assert.equal(g.run('abort').cancelled,true);assert.equal(g.submit.clicked,0);assert.equal(g.close.clicked,1);
});
test('changed original text, project route, or textarea identity cannot submit to another context',()=>{
 const f=rulesFixture();assert.equal(f.run('fill',{expected:'Stale original',value:'Change'}).reason,'stale');assert.equal(f.field.value,'Original project rules.');assert.equal(f.submit.clicked,0);
 const g=rulesFixture();g.run('fill',{expected:g.field.value,value:'Change'});g.location.pathname='/work/projects/cace260d-d95d-4859-b45b-f56f185f15da';
 const before=g.queries;assert.equal(g.run('submit').reason,'context_changed');assert.equal(g.queries,before);assert.equal(g.submit.clicked,0);
 const h=rulesFixture();h.run('fill',{expected:h.field.value,value:'Change'});const replacement=new RulesNode('textarea','','',{name:'custom'});replacement.form=h.form;replacement.value='Change';h.form.children[1].children=[replacement];
 assert.equal(h.run('submit').reason,'context_changed');assert.equal(h.submit.clicked,0);
});
test('ambiguous dialogs and changed form boundaries fail closed before reading or writing values',()=>{
 for(const mutate of [f=>f.dialogs.push(new RulesNode('div')),f=>f.form.id='other-form',f=>f.field.attributes.name='message',f=>f.form.children[1].append(new RulesNode('textarea')),f=>f.heading.id='wrong',f=>f.close.classes.delete('top-4')]){
  const f=rulesFixture();mutate(f);assert.equal(f.run('read').ready,false);assert.equal(f.submit.clicked,0);assert.equal(f.close.clicked,0);
 }
});
test('rules values are bounded, markup stays plain text, and untrusted origins do not access the DOM',()=>{
 const f=rulesFixture();f.field.value='x'.repeat(8001);assert.equal(f.run('read').reason,'too_long');assert.equal(f.submit.clicked,0);
 const g=rulesFixture();const payload='<img onerror="steal()">\n__VIBEZ_RULES_VALUE__';assert.equal(g.run('fill',{expected:g.field.value,value:payload}).filled,true);assert.equal(g.field.value,payload);assert.equal(g.submit.clicked,0);
 const h=rulesFixture();h.location.hostname='evil.invalid';assert.equal(h.run('read').reason,'context_changed');assert.equal(h.queries,0);
});
test('asynchronous close and temporarily disabled save are confirmed without duplicate submit',()=>{
 const f=rulesFixture();f.close.click=()=>{f.close.clicked++;};assert.equal(f.run('read').ready,true);assert.notEqual(f.run('status').closed,true);
 f.dialog.isConnected=false;assert.equal(f.run('status').closed,true);
 const g=rulesFixture();g.submit.disabled=true;assert.equal(g.run('fill',{expected:g.field.value,value:'Changed'}).filled,true);
 assert.equal(g.run('submit').reason,'submit_pending');assert.equal(g.submit.clicked,0);
 g.submit.disabled=false;assert.equal(g.run('submit').submitted,true);assert.equal(g.submit.clicked,1);assert.equal(g.run('status').closed,true);
 const h=rulesFixture();h.run('fill',{expected:h.field.value,value:'Changed'});h.checkbox.checked=!h.checkbox.checked;
 assert.equal(h.run('submit').reason,'form_changed');assert.equal(h.submit.clicked,0);assert.equal(h.run('abort').cancelled,true);
});
