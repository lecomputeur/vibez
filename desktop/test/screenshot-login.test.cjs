'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const rows=require('../screenshot-login-i18n.json');
const raw=fs.readFileSync(path.join(__dirname,'../src-tauri/src/screenshot_login.js'),'utf8');
const source=raw.replace('__VIBEZ_LOGIN_LABELS__',JSON.stringify(Object.values(rows).flatMap(r=>r[0].split('|')))).replace('__VIBEZ_SIGNUP_LABELS__',JSON.stringify(Object.values(rows).flatMap(r=>r[1].split('|'))));
function run(words,options={}){
 const doc={defaultView:{getComputedStyle:e=>({display:options.hidden?'none':'block',visibility:'visible',opacity:'1'})}};
 const parent={tagName:'HEADER',parentElement:null,contains:e=>elements.includes(e),getBoundingClientRect:()=>({height:60})};
 const elements=words.map(text=>({tagName:'BUTTON',isConnected:true,parentElement:parent,ownerDocument:doc,textContent:text,getAttribute:()=>null,closest:()=>options.article?{}:null,getBoundingClientRect:()=>({width:80,height:30,top:options.low?400:15,bottom:options.low?430:45})}));
 doc.querySelectorAll=()=>elements;
 return vm.runInNewContext(source,{document:doc,Set,Array,Math,String});
}
test('only a visible adjacent guest pair triggers the notice in every supported language',()=>{
 for(const [lang,row] of Object.entries(rows))assert.equal(run([row[0].split('|')[0],row[1].split('|').find(s=>s!==row[0].split('|')[0])]),true,lang);
 assert.equal(run(['Inloggen','Aanmelden']),true);
 assert.equal(run(['Sign in','Sign up']),true);
});
test('signed-in, unavailable, one action, hidden actions or quoted login instructions never trigger',()=>{
 for(const words of [[],['Account'],['Sign in'],['Sign up'],['Log out','Account']])assert.equal(run(words),false);
 for(const option of ['article','low','hidden'])assert.equal(run(['Sign in','Sign up'],{[option]:true}),false,option);
 assert.equal(run(['Aanmelden']),false,'one ambiguous Dutch control is insufficient');
});
test('guest inspection cannot operate the page or inspect credentials',()=>{
 new vm.Script(source);assert.doesNotMatch(raw,/\.click\(|\.focus\(|\.value|\.cookie|localStorage|sessionStorage|fetch\(|__TAURI__|invoke\(/i);
});
