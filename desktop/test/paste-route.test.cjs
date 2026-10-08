'use strict';
// Small selector-level regression. Real-engine capture/paste/acknowledgement on
// these SPA paths is additionally exercised in screenshot_release_probe.rs.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../src-tauri/src/paste_composer.js'),'utf8');
function probe(pathname,excluded=false,requireFocused=false){
 const doc={activeElement:null,hasFocus:()=>true,addEventListener(){},removeEventListener(){},querySelectorAll:()=>[]};
 doc.defaultView={innerHeight:840,getComputedStyle:()=>({display:'block',visibility:'visible'})};
 const form={tagName:'FORM',isConnected:true,parentElement:null,querySelectorAll:()=>[],getBoundingClientRect:()=>({width:400,height:120,bottom:600})};
 const editor={tagName:'TEXTAREA',id:'message',isConnected:true,parentElement:form,ownerDocument:doc,disabled:false,readOnly:false,
  getAttribute:()=>null,getRootNode:()=>doc,getBoundingClientRect:()=>({width:400,height:60,bottom:580}),
  matches:q=>excluded&&q.includes('.monaco-editor'),closest:q=>q==='form'?form:null,focus(){doc.activeElement=this;},contains:e=>e===editor};
 form.matches=q=>q.split(',').includes('form');form.getRootNode=()=>doc;
 doc.activeElement=editor;
 doc.querySelectorAll=q=>q.startsWith('textarea,')?[editor]:[];
 const window={};
 const raw=vm.runInNewContext(source.replace('__VIBEZ_PASTE_FOCUSED__',String(requireFocused)),{
  document:doc,window,location:{pathname},innerWidth:1280,innerHeight:840,Date,Set,Map,JSON
 });
 return {result:JSON.parse(raw),receipt:window.__vibezPasteReceipt};
}
for(const route of ['/','/code','/code/task','/work','/chat/code/thread','/CODE/task']){
 test(`a message field is eligible on ${route}`,()=>{
  for(const focused of [false,true]){const value=probe(route,false,focused);assert.equal(value.result.ready,true);assert.equal(value.receipt.editor.id,'message');}
 });
 test(`a real code field remains excluded on ${route}`,()=>{
  const value=probe(route,true);assert.equal(value.result.ready,false);assert.equal(value.receipt,undefined);
 });
}
