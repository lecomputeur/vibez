'use strict';
window.vibezLanguage=(()=>{
const catalog=window.VIBEZ_TRANSLATIONS,listeners=[];let selected={language:'system',resolved:'en',site_locale:'en',pending:false},started;
function lookup(locale,key){for(const dictionary of [catalog.translations,catalog.extra,catalog.new]){const value=dictionary?.[locale]?.[key];if(typeof value==='string'&&value.trim())return value;}return null;}
function t(key){return lookup(selected.resolved,key)||lookup('en',key)||key;}
function format(key,args={}){return t(key).replace(/\{([A-Za-z][A-Za-z0-9_]*)\}/g,(token,name)=>Object.hasOwn(args,name)&&['string','number'].includes(typeof args[name])?String(args[name]).slice(0,4096):token);}
function errorText(error,fallbackKey='operationFailed'){
 if(error===null||error===undefined||error==='')return '';
 let value=error;
 // Native IPC can return an encoded object. Keep its translation key intact so
 // a language change also re-renders an error which is already on screen.
 if(typeof value==='string'&&value.length<=32768&&value.trim().startsWith('{')){try{value=JSON.parse(value);}catch(_){}}
 if(value&&typeof value==='object'){
  const key=value.message_key||(value.code==='engine_stopped'?'engineStopped':null);
  if(typeof key==='string'&&(lookup(selected.resolved,key)||lookup('en',key)))return format(key,value.message_args&&typeof value.message_args==='object'?value.message_args:{});
  if(typeof value.message_en==='string'&&value.message_en.trim())return value.message_en.slice(0,8192);
  if(['en',selected.resolved].includes(value.message_language)&&typeof value.message==='string'&&value.message.trim())return value.message.slice(0,8192);
  value=value.message||value.error||'';
 }
 // Older backends returned Dutch diagnostics as an unmarked string. Those
 // strings may be shown only in Dutch; elsewhere use the current UI language
 // (or its English catalogue fallback) instead of leaking Dutch into the UI.
 if(selected.resolved==='nl'&&typeof value==='string'&&value.trim())return value.slice(0,8192);
 return t(fallbackKey);
}
function apply(next){if(next.revision!==undefined&&selected.revision!==undefined&&(next.revision<selected.revision||(next.revision===selected.revision&&!selected.pending&&next.pending)))return;selected=next;document.documentElement.lang=next.resolved;document.documentElement.dir=['ar','he','fa','ur'].includes(next.resolved)?'rtl':'ltr';for(const selector of ['[data-i18n]','[data-extra]','[data-v4]'])for(const node of document.querySelectorAll(selector)){node.textContent=t(node.getAttribute(selector.slice(1,-1)));}for(const node of document.querySelectorAll('[data-title-key]')){const text=t(node.dataset.titleKey);node.title=text;node.setAttribute('aria-label',text);}for(const node of document.querySelectorAll('[data-placeholder-key]'))node.placeholder=t(node.dataset.placeholderKey);const globe=document.getElementById('language-button');if(globe){globe.title=t('languageButton');globe.setAttribute('aria-label',t('languageButton'));}for(const fn of listeners)fn(next);}
async function ready(){if(started)return started;started=(async()=>{await window.__TAURI__.event.listen('language-state',e=>apply(e.payload));await window.__TAURI__.event.listen('language-warning',()=>{const target=document.getElementById('language-status')||document.getElementById('status');if(target)target.textContent=t('languageWarning');});apply(await window.__TAURI__.core.invoke('language_get'));})();return started;}
async function set(language){const state=await window.__TAURI__.core.invoke('language_set',{language});apply(state);return state;}
return {ready,set,t,format,errorText,state:()=>selected,onChange:fn=>listeners.push(fn),apply};
})();
