'use strict';
const $=id=>document.getElementById(id),invoke=(name,args)=>window.__TAURI__.core.invoke(name,args);
let panel='closed',statusId=null,statusDetail='',screenshotHighlight=null,currentProject=null,pendingProjectOpen=null,lastPanelDismissAt=0;
const t=key=>window.vibezLanguage.t(key);
const connection=window.vibezConnectionStatus.createConnectionStatus();
function renderConnection(){
 const current=connection.view(),button=$('connection-indicator'),label=t(current.state==='no_project'?'openProjectOrConversation':current.key),projectName=current.kind==='conversation'&&current.draft?t('newConversation'):current.projectName;
 button.dataset.state=current.state;
 $('connection-label').textContent=label;
 for(const [id,value]of [['connection-project-name',projectName],['connection-folder-name',current.folderName]]){
  const node=$(id);node.textContent=value;node.title=value;node.hidden=!value;
 }
 button.title=[...new Set([projectName,current.folderName].filter(Boolean))].join(' · ');
 button.setAttribute('aria-label',[label,projectName,current.folderName,t('connectionOpenFiles')].filter(Boolean).join(' · '));
}
function status(text,key=null,detail=''){statusId=key;statusDetail=detail;$('status').textContent=text||'';$('status').title=window.vibezLanguage.errorText(detail,key||'operationFailed');}
function showError(error){const key=error?.code==='engine_stopped'?'engineStopped':'operationFailed';status(t(key),key,error);}
function setPanel(mode){panel=mode;if(mode!=='files'){pendingProjectOpen=null;lastPanelDismissAt=Date.now();}for(const [id,value]of [['settings','settings'],['connection-indicator','files']])$(id).setAttribute('aria-expanded',String(mode===value));}
function openPanel(mode){const previous=panel;setPanel(mode);invoke('chrome_panel',{mode}).catch(error=>{if(panel===mode)setPanel(previous);showError(error);});}
for(const action of ['back','forward','reload','home'])$(action).addEventListener('click',()=>invoke('web_navigate',{destination:action}).catch(showError));
$('connection-indicator').addEventListener('click',()=>openPanel('files'));
$('settings').addEventListener('click',()=>openPanel(panel==='settings'?'closed':'settings'));
$('screenshot').addEventListener('click',async()=>{const button=$('screenshot');clearTimeout(screenshotHighlight);button.dataset.active='true';button.disabled=true;try{await invoke('chrome_snapshot');}catch(e){showError(e);}finally{button.disabled=false;screenshotHighlight=setTimeout(()=>delete button.dataset.active,1600);}});
$('quick-language').addEventListener('change',async()=>{const menu=$('quick-language');menu.disabled=true;try{await window.vibezLanguage.set(menu.value);}catch(e){menu.value=window.vibezLanguage.state().language;showError(e);}finally{menu.disabled=false;}});
async function boot(){
 await window.vibezLanguage.ready();
 const menu=$('quick-language');for(const option of window.VIBEZ_TRANSLATIONS.options){const node=document.createElement('option');node.value=option.code;node.textContent=option.code==='system'?t('system'):option.name;menu.append(node);}
 function badge(){const s=window.vibezLanguage.state();$('language-code').textContent=s.resolved.toUpperCase();menu.value=s.language;menu.querySelector('option[value=system]').textContent=t('system');}
 window.vibezLanguage.onChange(()=>{badge();renderConnection();if(statusId)status(t(statusId),statusId,statusDetail);});badge();renderConnection();
 await window.__TAURI__.event.listen('language-warning',()=>status(t('languageWarning'),'languageWarning'));
 await window.__TAURI__.event.listen('chrome-panel',e=>setPanel(e.payload));
 await window.__TAURI__.event.listen('project-panel-open',e=>{
  if(typeof e.payload?.clicked_at==='number'&&e.payload.clicked_at<=lastPanelDismissAt)return;
  pendingProjectOpen=e.payload?.project_id||null;
  if(pendingProjectOpen&&pendingProjectOpen===currentProject){pendingProjectOpen=null;openPanel('files');}
 });
 await window.__TAURI__.event.listen('app-engine',e=>{
  connection.receive(e.payload);renderConnection();
  if(e.payload.type==='error')showError(e.payload);
  if(e.payload.type==='web_connector'){
   currentProject=e.payload.project?.id||null;
   if(pendingProjectOpen&&pendingProjectOpen===currentProject){pendingProjectOpen=null;openPanel('files');}
   if(e.payload.pending?.length)status(t('reviewChanges'),'reviewChanges');
   else if(statusId==='reviewChanges')status('');
  }
 });
 const info=await invoke('app_info');$('version').textContent=info.version;
 await invoke('web_surface',{show:true,route:null});
}boot().catch(showError);
