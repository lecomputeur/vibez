'use strict';
// This local settings view only observes native update state. Permission is an explicit action.
(()=>{
const phases=new Set(['idle','automatic','current','checking','downloading','installing','ready','available','consent_required','restart_required','waiting_for_close','installed','updated','disabled','error','screen_restricted','not_flatpak']);
function accepted(value){return value&&typeof value==='object'&&!Array.isArray(value)&&phases.has(value.status||value.phase)?value:null;}
function presentation(value,pending=false){
 const state=accepted(value)||{status:'idle'},phase=state.status||state.phase;
 const kind=state.kind||'native',busy=Boolean(pending||state.busy||['checking','downloading','installing'].includes(phase));
 const restricted=['screen_restricted','not_flatpak'].includes(phase),disabled=state.automatic===false||phase==='disabled';
 let key='updateAutomatic';
 if(phase==='screen_restricted')key='updateScreenRestricted';
 else if(phase==='error'||phase==='not_flatpak')key='updateError';
 else if(phase==='checking')key='updateChecking';
 else if(['downloading','installing'].includes(phase))key='updateDownloading';
 else if(state.restart_required||phase==='restart_required'||(phase==='ready'&&kind!=='flatpak'))key='updateReady';
 else if(phase==='waiting_for_close')key='updateWaiting';
 else if(disabled)key='updateDisabled';
 else if(kind==='flatpak'&&state.consent_required)key='updatePermission';
 else if(['current','installed','updated'].includes(phase)||(phase==='ready'&&kind==='flatpak'))key='updateCurrent';
 // A Microsoft Store install is updated by the Store; there is nothing to check here.
 return {key,busy,store:kind==='store',allow:kind==='flatpak'&&state.consent_required===true&&!restricted&&!disabled,
  error:state.error||''};
}
async function attach({document,tauri,language}){
 const status=document.getElementById('alpha-update-status'),check=document.getElementById('alpha-update-check'),allow=document.getElementById('alpha-update-allow');
 if(!status||!check||!allow)return;
 let state={status:'idle'},pending=false,revision=0;
 function render(){
  const view=presentation(state,pending);
  status.textContent=language.t(view.key);status.title=view.error?(language.errorText?language.errorText(view.error,'updateError'):language.t('updateError')).slice(0,2048):'';
  status.setAttribute('aria-busy',String(view.busy));
  check.textContent=language.t('updateCheck');check.disabled=view.busy;check.hidden=view.store;
  allow.textContent=language.t('updateAllow');allow.hidden=!view.allow;allow.disabled=view.busy;
 }
 function receive(value){if(!accepted(value))return;state=value;revision++;render();}
 async function request(command){
  if(presentation(state,pending).busy)return;
  if(command==='alpha_update_allow'&&!presentation(state).allow)return;
  const before=++revision;pending=true;render();
  try{const result=await tauri.core.invoke(command);if(before===revision&&accepted(result))state=result;}
  catch(error){if(before===revision)state={...state,status:'error',error};}
  finally{pending=false;render();}
 }
 check.addEventListener('click',()=>request('alpha_update_check'));
 allow.addEventListener('click',()=>request('alpha_update_allow'));
 language.onChange(render);
 for(const event of ['alpha-update','alpha-flatpak-update'])await tauri.event.listen(event,e=>receive(e.payload));
 await language.ready();render();
 const before=revision;
 try{const initial=await tauri.core.invoke('alpha_update_state');if(before===revision)receive(initial);}
 catch(error){if(before===revision)receive({status:'error',error});}
}
if(typeof module==='object'&&module.exports)module.exports={presentation,attach};
if(typeof window!=='undefined'&&window.__TAURI__&&window.vibezLanguage)attach({document:window.document,tauri:window.__TAURI__,language:window.vibezLanguage});
})();
