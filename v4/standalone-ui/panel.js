'use strict';
const $=id=>document.getElementById(id),invoke=(name,args)=>window.__TAURI__.core.invoke(name,args);
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
const t=key=>window.vibezLanguage.t(key),errorText=(error,key='operationFailed')=>window.vibezLanguage.errorText(error,key);
const connectionFeedback=window.vibezConnectionFeedback.connectionFeedback;
const labels={read_image:'readImage',move_file:'moveItem',read_file:'readFile',propose_file:'fileActionProposed',save_file:'fileActionSaved',import_file:'addFiles',import_folder:'addFolder',create_folder:'newFolder'};
let webState={project:null,pending:[],activity:[]},auto={status:'idle'},loginURL='',actionError='',technicalError='',autoBusySince=0;
const BUSY_STATUSES=['starting','authorizing','connecting','registering'],PHASE_KEYS={tunnel:'phaseTunnel',tunnel_retry:'phaseTunnelRetry',reachable:'phaseReachable',permission:'phasePermission',register:'phaseRegister',enroll:'phaseEnroll',attach:'phaseAttach',refresh:'phaseRefresh'};
// While a link runs, the status line names the current part and counts the seconds.
if(typeof setInterval==='function')setInterval(()=>{if(BUSY_STATUSES.includes(auto.status))renderAutomatic();},1000);
let importBusy=false,importCancelling=false,importMessage=null,projectDetails=null;
let importConflict=null,conflictChoices={},conflictApplyAll=false,conflictSubmitting=false,conflictFailure='',projectPanelMode='files';
let openWorkspaceBusy=false,folderPicking=false;
let folderRequest=null,folderNotice=null,folderRequestSerial=0;
let rulesEdit=null,rulesOperation=null,rulesNotice=null,apiRules=null;
const isConversation=()=>webState.project?.kind==='conversation';
function folderMessage(key){const folder=webState.folder?(webState.folder.split(/[\\/]/).filter(Boolean).pop()||webState.folder):'';return t(key).split('{folder}').join(folder);}
function contextLabel(id,key){const node=$(id);node.dataset.v4=key;node.textContent=folderMessage(key);}
function proposalHelp(proposal){const format=proposal.new===true&&['.odt','.docx','.ods','.xlsx','.odp','.pptx'].includes(proposal.document_format)?proposal.document_format.slice(1).toUpperCase():null;return format?t('documentProposalNote').split('{format}').join(format):t('proposalNote');}
function contextName(project){return project?.kind==='conversation'&&project.draft?t('newConversation'):project?.name||t('openProjectOrConversation');}
function webNotice(error){actionError=error;$('web-status').textContent=t('operationFailed');renderAutomatic();}
async function webCommand(action,extra={}){actionError='';renderAutomatic();try{await invoke('web_command',{payload:{action,project_id:webState.project?.id,...extra}});return true;}catch(e){webNotice(e);return false;}}
function renderWeb(data){
 const changed=auto.project_id!==data.project?.id;
 if(changed||webState.import_binding!==data.import_binding){browserPath='.';browserRequest=null;browserMove=null;$('browser-move-form').hidden=true;$('browser-entries').replaceChildren();resetFolderForm();importBusy=false;importCancelling=false;importMessage=null;openWorkspaceBusy=false;clearImportConflict();}
 if(changed){resetRulesEditor();auto={project_id:data.project?.id,status:'idle'};actionError='';delete $('files-options').dataset.requested;openWorkspaceBusy=false;$('files-options').open=false;$('advanced-setup').open=false;$('mistral-project-settings').open=false;}
 const newlyLinked=!changed&&Boolean(webState.project)&&!webState.folder&&Boolean(data.folder);
 webState=data;const p=data.project,linked=Boolean(data.folder),running=data.tunnel_status==='running';
 $('panel-auto-connect').checked=data.auto_connect===true;
 contextLabel('context-panel-label',isConversation()?'conversationPanel':'projectPanel');
 $('web-project-name').removeAttribute('data-v4');$('web-project-name').textContent=contextName(p);
 contextLabel('web-project-note',!p?'openProjectOrConversation':isConversation()?(p.draft?'draftConversationNote':'conversationFolderNote'):'projectFolderNote');$('web-project-note').hidden=Boolean(p&&!isConversation());
 contextLabel('context-scope-note',isConversation()?'conversationScopeNote':'scopeNote');
 contextLabel('context-setup-note',isConversation()?'conversationSetupNote':'setupNote');
 contextLabel('import-conflict-help',isConversation()?'conversationImportConflictHelp':'importConflictHelp');
 renderLinkedFolders();
 // Manual connection options stay out of sight; an error that needs them opens them explicitly.
 $('files-options').hidden=$('files-options').dataset.requested!=='1'||!linked;
 $('web-enable').hidden=data.enabled;$('web-enable').disabled=!linked;$('web-tunnel-choice').hidden=!data.enabled||running||data.tunnel_status==='starting';$('web-stop').hidden=!['running','starting'].includes(data.tunnel_status);$('web-setup').hidden=!linked||!data.url;
 $('web-connector-name').value=p?'VibeZ'+p.name.replace(/[^a-zA-Z0-9]/g,'').slice(0,45)+p.id.slice(0,8):'';$('web-endpoint').value=data.url||'';$('web-token').value=data.token||'';
 $('web-status').textContent=data.tunnel_status==='failed'?t('failed'):data.tunnel_status==='starting'?t('starting'):data.enabled&&running?t('active'):data.enabled?t('allowed'):linked?t('paused'):t(isConversation()?'conversationChooseFirst':'chooseFirst');
$('web-review').hidden=!data.pending?.length;$('web-proposals').replaceChildren();$('web-no-proposals').hidden=Boolean(data.pending?.length);for(const proposal of data.pending||[]){const card=el('article','approval'),head=el('div','approval-head');head.append(el('span','eyebrow',proposal.project_name),el('h3','',proposal.path),el('p','',proposalHelp(proposal)));card.append(head);const comparison=el('div','comparison');for(const [title,text]of [[t('currentText'),proposal.before],[t('proposal'),proposal.after]]){const section=el('section');section.append(el('h4','',title),el('pre','',text));comparison.append(section);}card.append(comparison);const actions=el('div','approval-actions'),yes=el('button','primary',t('filesSave')),no=el('button','secondary',t('reject'));for(const [b,allow]of [[yes,true],[no,false]])b.addEventListener('click',async()=>{yes.disabled=no.disabled=true;const ok=await webCommand('web_approve',{id:proposal.id,allow});if(!ok)yes.disabled=no.disabled=false;});actions.append(yes,no);card.append(actions);$('web-proposals').append(card);}
renderAutomatic();renderProjectFiles();renderProjectDetails();renderAdvanced();
 if(newlyLinked)panelTabsView?.folderLinked();else panelTabsView?.sync();
 if($('diagnostics-dialog').open){requestDiagnostics();renderDiagnostics();}}

function folderName(path){return path.split(/[\\/]/).filter(Boolean).pop()||path;}
function linkedFolders(){return webState.folders||[];}
function sameFolders(project,revision){return webState.project?.id===project&&(webState.workspace_binding||null)===revision;}
function closeFolderMenus(){for(const menu of $('linked-folders').querySelectorAll('details'))menu.open=false;}
function renderLinkedFolders(){
 const p=webState.project,entries=linkedFolders(),multiple=entries.length>1;
 $('workspace-section').hidden=!p;$('folder-summary').hidden=!p||Boolean(webState.folder);
 $('workspace-add').hidden=!p||!webState.folder;$('workspace-add').disabled=folderPicking||entries.length>=16;
 $('workspace-destination').hidden=!multiple;
 const list=$('linked-folders');list.hidden=!entries.length;list.replaceChildren();
 const project=p?.id,revision=webState.workspace_binding||null;
 for(const item of entries){
  const row=el('div','linked-folder'),top=el('div','linked-folder-top');row.dataset.folderId=item.id;
  row.dataset.selected=String(item.id===webState.target_folder_id);
  const label=el('label','linked-folder-label');
  if(multiple){const radio=el('input');radio.type='radio';radio.name='workspace-destination';radio.value=item.id;radio.checked=item.id===webState.target_folder_id;radio.disabled=folderPicking;radio.addEventListener('change',()=>{if(radio.checked&&sameFolders(project,revision))webCommand('web_select_folder',{workspace_binding:revision,folder_id:item.id});});label.append(radio);}
  const text=el('span','linked-folder-text');text.append(el('strong','',folderName(item.path)),el('span','linked-folder-path',item.path));label.append(text);top.append(label);
  const options=el('details','linked-folder-options'),summary=el('summary','', '⋯');summary.setAttribute('aria-label',t('filesOptions')+': '+folderName(item.path));summary.title=t('filesOptions');options.append(summary);
  options.addEventListener('toggle',()=>{if(options.open)for(const other of list.querySelectorAll('details'))if(other!==options)other.open=false;});
  const menu=el('div','linked-folder-menu');
  const replace=el('button','option-action',t('otherWorkspace')),remove=el('button','option-action',t('unlink'));
  replace.type=remove.type='button';replace.disabled=remove.disabled=folderPicking;
  replace.addEventListener('click',()=>{options.open=false;if(sameFolders(project,revision))chooseFolder(false,false,item.id);});
  remove.addEventListener('click',()=>{options.open=false;if(sameFolders(project,revision))webCommand('web_remove_folder',{workspace_binding:revision,folder_id:item.id});});
  menu.append(replace,remove);options.append(menu);top.append(options);row.append(top);
  const actions=el('div','folder-actions'),open=el('button','secondary',t('openWorkspace'));open.type='button';open.disabled=openWorkspaceBusy||folderPicking||!webState.import_binding;
  open.addEventListener('click',()=>{if(sameFolders(project,revision))openFolder(item.id);});actions.append(open);row.append(actions);list.append(row);
 }
}
async function openFolder(folderId){
 const projectId=webState.project?.id,binding=webState.import_binding;
 if(!projectId||!binding||openWorkspaceBusy)return;
 openWorkspaceBusy=true;renderLinkedFolders();
 try{await invoke('project_open_folder',{projectId,binding,folderId});}catch(error){if(webState.project?.id===projectId&&webState.import_binding===binding)webNotice(error);}
 finally{if(webState.project?.id===projectId&&webState.import_binding===binding){openWorkspaceBusy=false;renderLinkedFolders();}}
}
async function chooseFolder(create=false,adding=false,replacingId=null){
 const key=webState.project?.id,revision=webState.workspace_binding||null,folderId=replacingId||webState.target_folder_id||null;if(!key||folderPicking||(create&&webState.folder))return;
 folderPicking=true;renderAutomatic();renderLinkedFolders();
 try{const path=await invoke('web_choose_folder',{create});if(!path||!sameFolders(key,revision))return;
  actionError='';renderAutomatic();await invoke('web_command',{payload:{action:adding?'web_add_folder':'web_link',project_id:key,path,...(revision?{workspace_binding:revision,...(!adding?{folder_id:folderId}:{})}:{})}});
 }catch(e){if(sameFolders(key,revision))webNotice(e);}
 finally{folderPicking=false;renderAutomatic();renderLinkedFolders();}
}
$('workspace-add').addEventListener('click',()=>chooseFolder(false,true));
$('create-workspace').addEventListener('click',()=>chooseFolder(true));
for(const id of ['web-pause','connection-refresh'])$(id).addEventListener('click',()=>{$('files-options').open=false;});
document.addEventListener('click',e=>{if(!$('files-options').contains(e.target))$('files-options').open=false;if(!$('linked-folders').contains(e.target))closeFolderMenus();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){for(const menu of $('linked-folders').querySelectorAll('details[open]')){menu.open=false;menu.querySelector('summary').focus();}if($('files-options').open){$('files-options').open=false;$('files-options').querySelector('summary').focus();}}});
$('web-enable').addEventListener('click',()=>webCommand('web_enable',{allow:true}));$('web-pause').addEventListener('click',()=>webCommand('web_enable',{allow:false}));$('web-start').addEventListener('click',()=>webCommand('web_start'));$('web-stop').addEventListener('click',()=>webCommand('web_stop'));$('web-rotate').addEventListener('click',()=>webCommand('web_rotate'));
for(const [button,input]of [['web-copy-name','web-connector-name'],['web-copy-url','web-endpoint'],['web-copy-token','web-token']])$(button).addEventListener('click',async()=>{try{await invoke('app_copy',{text:$(input).value});$(button).textContent=t('copied');}catch(e){webNotice(e);}});

for(const id of ['close-panel','close-settings-panel'])$(id).addEventListener('click',()=>invoke('chrome_panel',{mode:'closed'}));
$('settings-files').addEventListener('click',()=>invoke('chrome_panel',{mode:'files'}));
async function boot(){
 await window.vibezLanguage.ready();
 window.vibezLanguage.onChange(()=>{if(webState.type==='web_connector')renderWeb(webState);});
 const select=$('language');for(const o of window.VIBEZ_TRANSLATIONS.options){const n=el('option','',o.code==='system'?t('system'):o.name);n.value=o.code;select.append(n);}
 function selected(){const s=window.vibezLanguage.state();select.value=s.language;$('language-fallback').hidden=s.site_locale===s.resolved;document.querySelector('option[value=system]').textContent=t('system');$('language-status').textContent=s.pending?t('languagePending'):'';$('language-status').title='';}
 window.vibezLanguage.onChange(selected);selected();
 select.addEventListener('change',async()=>{select.disabled=true;try{await window.vibezLanguage.set(select.value);}catch(e){selected();$('language-status').textContent=t('operationFailed');$('language-status').title=errorText(e);}finally{select.disabled=false;}});
 await window.__TAURI__.event.listen('app-engine',e=>{if(e.payload.type==='web_connector')renderWeb(e.payload);if(e.payload.type==='error')webNotice(e.payload);});
 await window.__TAURI__.event.listen('chrome-panel',e=>{projectPanelMode=e.payload;const settings=['settings','language'].includes(e.payload);$('web-panel').hidden=settings;$('panel-settings').hidden=!settings;if(e.payload==='files'){document.body.scrollTop=0;document.documentElement.scrollTop=0;renderImportConflict();}else if($('import-conflict-dialog').open){$('import-conflict-dialog').close();}if(e.payload==='language'){$('language').focus();}});
 const info=await invoke('app_info');$('panel-version').textContent=info.version;
 try{panelTabsView?.applyPrefs(await invoke('panel_prefs_get'));}catch(error){}
 await webCommand('web_hello');
}boot().catch(e=>webNotice(e));

function renderAutomatic(){
 const busy=['starting','authorizing','connecting','registering'].includes(auto.status);
 const status=auto.status==='connected'&&(!webState.enabled||webState.tunnel_status!=='running')?'paused':auto.status;
 const linked=Boolean(webState.folder),connected=status==='connected';
 const feedback=connectionFeedback({automatic:{...auto,status},actionError,linked});
 const manuallyPaused=!busy&&!connected&&status!=='error'&&(webState.manually_paused||auto.pause_reason==='manual');
 const signInRequired=!busy&&!connected&&status!=='error'&&!manuallyPaused&&auto.pause_reason==='sign_in';
 $('auto-connect').hidden=!webState.project||feedback.action==='none'||(connected&&!feedback.messageKey);$('auto-connect').disabled=folderPicking;
 $('create-workspace').hidden=!webState.project||linked;$('create-workspace').disabled=folderPicking;
 $('auto-connect').dataset.action=busy?'cancel':!linked?'chooseWorkspace':feedback.buttonKey||'filesConnect';$('auto-connect').textContent=t(busy?'cancel':!linked?'chooseWorkspace':feedback.buttonKey||'filesConnect');
 $('auto-connect').className=(busy?'secondary':'primary')+' files-main-action';
 $('connection-refresh').hidden=!connected;$('web-pause').hidden=!connected;$('web-pause').disabled=folderPicking;
 const key=status==='connected'?'filesConnected':status==='authorizing'?(auto.retry_after?'filesWaiting':'filesAuthorizing'):busy?'filesConnecting':status==='error'?'filesFailed':manuallyPaused?'filesPausedByYou':signInRequired?'filesSignInRequired':status==='paused'||status==='cancelled'?'filesPaused':'filesDisconnected';
 // The play/pause/stop icons already show these states; words only where the user must act.
 $('auto-status').hidden=((!webState.project||!linked)||status==='connected'||manuallyPaused||(['idle','paused'].includes(status)&&!signInRequired))&&!actionError&&status!=='error';$('auto-status').dataset.state=actionError?'error':status;if(busy){if(!autoBusySince)autoBusySince=Date.now();}else autoBusySince=0;
 const phaseKey=busy&&!actionError&&status!=='authorizing'?PHASE_KEYS[auto.phase]:null,elapsed=busy&&autoBusySince?Math.round((Date.now()-autoBusySince)/1000):0;
 $('auto-status').textContent=actionError?t('operationFailed'):(phaseKey?t(phaseKey):t(key))+(busy&&elapsed>=3?' · '+elapsed+' s':'');
 const errorKey=feedback.messageKey||'auto_error';
 $('connection-details').hidden=!feedback.messageKey;$('connection-details').textContent=feedback.messageKey?t(errorKey):'';
 const rawDetail=actionError?errorText(actionError):status==='error'?errorText(auto,errorKey):'';
 const detail=[rawDetail&&rawDetail!==$('connection-details').textContent?rawDetail:'',feedback.errorCode?t('connectionErrorCode')+': '+feedback.errorCode:''].filter(Boolean).join('\n');
 if(detail!==technicalError){$('error-details').open=false;technicalError=detail;}
 $('error-details').hidden=!detail;$('error-details-text').textContent=detail;
 $('error-open-diagnostics').hidden=!detail&&status!=='error'&&!actionError;
 if($('diagnostics-dialog').open)renderDiagnostics();
 $('auto-open-login').hidden=!loginURL||!busy;
 $('api-access').hidden=feedback.errorCode!=='permission';
}
$('auto-connect').addEventListener('click',event=>{
 if(['starting','authorizing','connecting','registering'].includes(auto.status))return webCommand('web_abort');
 if(!webState.folder)return chooseFolder();
 const feedback=connectionFeedback({automatic:auto,actionError,linked:true});
 if(feedback.action==='none')return;
 if(feedback.action==='folder')return chooseFolder();
 if(feedback.action==='settings'){event.stopPropagation?.();$('files-options').dataset.requested='1';$('files-options').hidden=false;$('files-options').open=true;$('advanced-setup').open=true;if(feedback.errorCode==='permission')$('studio-api-key').focus();return;}
 return webCommand('web_connect');
});
$('connection-refresh').addEventListener('click',()=>webCommand('web_connect'));
$('auto-open-login').addEventListener('click',()=>{if(loginURL)invoke('app_open_login',{url:loginURL}).catch(e=>webNotice(e));});
$('studio-save-key').addEventListener('click',async()=>{const key=$('studio-api-key').value.trim();if(await webCommand('web_set_api_key',{api_key:key}))$('studio-api-key').value='';});
window.vibezLanguage.onChange(renderAutomatic);
window.__TAURI__.event.listen('app-engine',e=>{
 const data=e.payload;if(data.type==='web_auto'&&data.project_id===webState.project?.id){auto=data;renderAutomatic();}
 if(data.type==='auth'){if(data.status==='waiting'){loginURL=data.url;invoke('app_open_login',{url:loginURL}).catch(error=>webNotice(error));}else if(['connected','cancelled','error','disconnected'].includes(data.status))loginURL='';renderAutomatic();}
});

function renderProjectFiles(){
 const linked=Boolean(webState.project&&webState.folder&&webState.import_binding);
 $('file-browser').hidden=!linked;
 $('project-files').hidden=!webState.project;
 const heading=$('files-section-heading');heading.removeAttribute('data-v4');heading.textContent=linked?(webState.folder.split(/[\\/]/).filter(Boolean).pop()||webState.folder):t('mainFolderSetup');
 // Linked: the folder card already names the folder, so keep this area short.
 heading.hidden=linked;$('main-folder-setup').hidden=linked;
 $('project-drop-zone').hidden=!linked;
 $('project-drop-zone').removeAttribute('data-title-key');$('project-drop-zone').title=heading.textContent;$('project-drop-zone').setAttribute('aria-label',heading.textContent);
 $('project-add-files').disabled=!linked||importBusy||Boolean(folderRequest);
 $('project-new-folder').disabled=!linked||importBusy||Boolean(folderRequest);
 $('project-drop-zone').setAttribute('aria-disabled',String(!linked||importBusy||Boolean(folderRequest)));
 contextLabel('project-drop-hint',linked?'dropShort':'dropChooseWorkspace');
 const message=$('project-import-status');message.title=errorText(importMessage?.detail,'fileImportFailed');
 message.dataset.error=String(Boolean(importMessage?.error));
 const copied=importMessage?.count?t('filesCopied').replace('{count}',String(importMessage.count)):'';
 const skipped=importMessage?.skipped?t('importSkipped').replace('{count}',String(importMessage.skipped)):'';
 renderFolderForm();
 message.textContent=importCancelling?t('importCancel')+'…':importConflict?t('importConflictTitle'):importBusy?t('copyingFiles'):[copied,skipped,importMessage?.error?t('fileImportFailed'):''].filter(Boolean).join(' ');
 const details=$('project-import-error-details'),detail=[errorText(importMessage?.detail,'fileImportFailed'),...(importMessage?.backups||[])].filter(Boolean).join('\n');
 if($('project-import-error-text').textContent!==detail)details.open=false;
 details.hidden=!importMessage?.error||!detail;$('project-import-error-text').textContent=detail;
}
async function startImport(grant){
 if(importBusy||folderRequest||!webState.project||!webState.folder||!webState.import_binding)return;
 const projectId=webState.project.id,binding=webState.import_binding;
 importBusy=true;importCancelling=false;importMessage=null;renderProjectFiles();
 try{
  const accepted=grant?await invoke('project_import_commit',{grant}):await invoke('project_import_choose',{projectId,binding});
  if(accepted===false&&webState.project?.id===projectId&&webState.import_binding===binding){importBusy=false;renderProjectFiles();}
 }catch(error){
  if(webState.project?.id===projectId&&webState.import_binding===binding){importBusy=false;importMessage={error:true,detail:error};renderProjectFiles();}
 }
}
function resetFolderForm(){
 folderRequest=null;folderNotice=null;$('new-folder-form').hidden=true;$('new-folder-name').value='';
}
function renderFolderForm(){
 contextLabel('subfolder-location','subfolderLocation');
 const busy=Boolean(folderRequest),linked=Boolean(webState.folder&&webState.import_binding);
 for(const id of ['new-folder-name','create-folder','cancel-new-folder'])$(id).disabled=busy||importBusy||!linked;
 const status=$('new-folder-status');status.textContent=folderNotice?folderMessage(folderNotice.error?'folderCreateFailed':'folderCreated')+(folderNotice.error?'':' '+folderNotice.name):'';
 status.title=errorText(folderNotice?.detail,'folderCreateFailed');status.dataset.error=String(Boolean(folderNotice?.error));
}
$('project-new-folder').addEventListener('click',()=>{
 if(importBusy||folderRequest||!webState.folder||!webState.workspace_binding)return;
 folderNotice=null;$('new-folder-form').hidden=false;renderFolderForm();$('new-folder-name').focus();
});
$('cancel-new-folder').addEventListener('click',()=>{if(folderRequest)return;resetFolderForm();renderProjectFiles();$('project-new-folder').focus();});
$('new-folder-form').addEventListener('submit',async event=>{
 event.preventDefault();if(folderRequest||importBusy)return;
 const key=webState.project?.id,revision=webState.workspace_binding,name=$('new-folder-name').value.trim();
 if(!key||!revision||!webState.folder||!name)return;
 $('new-folder-name').value=name;
 const request={project_id:key,workspace_binding:revision,request_id:'create-'+Date.now()+'-'+(++folderRequestSerial),name};folderRequest=request;folderNotice=null;renderProjectFiles();
 try{await invoke('web_command',{payload:{action:'web_create_folder',...request}});}
 catch(error){if(folderRequest===request){folderRequest=null;folderNotice={error:true,detail:error};renderProjectFiles();}}
});
window.__TAURI__.event.listen('app-engine',event=>{
 const d=event.payload,request=folderRequest;
 if(d.type!=='web_create_folder_result'||!request||d.request_id!==request.request_id||d.project_id!==request.project_id||d.workspace_binding!==request.workspace_binding||webState.project?.id!==request.project_id||webState.workspace_binding!==request.workspace_binding)return;
 folderRequest=null;
 if(d.created===true&&!d.error){folderNotice={name:request.name};$('new-folder-form').hidden=true;$('new-folder-name').value='';}
 else folderNotice={error:true,detail:d};
 renderProjectFiles();
});
$('project-add-files').addEventListener('click',()=>startImport());
document.addEventListener('dragover',e=>e.preventDefault());
document.addEventListener('drop',e=>e.preventDefault());
window.__TAURI__.event.listen('project-drop',e=>{
 const zone=$('project-drop-zone'),d=e.payload;
 const target=Number.isFinite(d.x)&&Number.isFinite(d.y)?document.elementFromPoint(d.x,d.y):null;
 const inside=target&&zone.contains(target)&&!$('web-panel').hidden&&zone.getAttribute('aria-disabled')==='false';
 zone.dataset.over=String(Boolean(inside&&d.kind!=='leave'&&d.kind!=='drop'));
 if(d.kind==='drop'&&inside&&typeof d.grant==='string')startImport(d.grant);
});
window.__TAURI__.event.listen('app-engine',e=>{
 const d=e.payload;
 if(d.type==='web_import_conflicts'&&d.project_id===webState.project?.id&&d.binding===webState.import_binding&&typeof d.plan_id==='string'&&Array.isArray(d.items)&&d.items.length<=50){
  if(importConflict?.plan_id!==d.plan_id){conflictChoices={};conflictApplyAll=false;conflictSubmitting=false;conflictFailure='';}
  importConflict=d;importBusy=true;renderProjectFiles();renderImportConflict();
 }
 if(d.type==='web_import_result'&&d.project_id===webState.project?.id&&d.binding===webState.import_binding){
  clearImportConflict();importBusy=false;importCancelling=false;importMessage={count:d.count||0,skipped:d.skipped||0,error:Boolean(d.error),detail:d.error?d:'',backups:d.backups||[]};renderProjectFiles();
 }
});
window.vibezLanguage.onChange(()=>{renderProjectFiles();renderProjectDetails();renderImportConflict();});

function clearImportConflict(){
 if($('import-conflict-dialog').open)$('import-conflict-dialog').close();
 importConflict=null;conflictChoices={};conflictApplyAll=false;conflictSubmitting=false;conflictFailure='';
 $('import-conflict-items').replaceChildren();
}
function setConflictChoice(id,choice){
 if(!importConflict||conflictSubmitting)return;
 const items=conflictApplyAll?importConflict.items:importConflict.items.filter(item=>item.id===id);
 for(const item of items)conflictChoices[item.id]=choice==='replace'&&!item.can_replace?'skip':choice;
 renderImportConflict();
}
function renderImportConflict(){
 if(!importConflict)return;
 const dialog=$('import-conflict-dialog'),container=$('import-conflict-items');container.replaceChildren();
 const kind=value=>t(value==='directory'?'importFolder':'importFile');
 for(const item of importConflict.items){
  const field=el('fieldset'),legend=el('legend','',item.name);field.dataset.itemId=item.id;field.append(legend);
  field.append(el('p','conflict-kind',t('importSource')+': '+kind(item.source_kind)+' · '+t('importExisting')+': '+kind(item.target_kind)));
  const options=el('div','import-conflict-options');
  if(!conflictChoices[item.id])conflictChoices[item.id]='skip';
  for(const [value,key]of [['skip','importSkip'],['replace','importReplace'],['keep_both','importKeepBoth']]){
   const label=el('label'),input=el('input');input.type='radio';input.name='import-choice-'+item.id;input.value=value;
   input.checked=conflictChoices[item.id]===value;input.disabled=conflictSubmitting||(value==='replace'&&!item.can_replace);
   input.addEventListener('change',()=>setConflictChoice(item.id,value));label.append(input,el('span','',t(key)));options.append(label);
  }
  field.append(options);container.append(field);
 }
 $('import-conflict-changed').hidden=importConflict.status!=='changed';
 $('import-conflict-all-label').hidden=importConflict.items.length<2;
 $('import-conflict-all').checked=conflictApplyAll;$('import-conflict-all').disabled=conflictSubmitting;
 $('import-conflict-folder-note').hidden=!importConflict.items.some(item=>conflictChoices[item.id]==='replace'&&(item.source_kind==='directory'||item.target_kind==='directory'));
 $('import-conflict-error').textContent=conflictFailure?t('fileImportFailed'):'';$('import-conflict-error').title=errorText(conflictFailure,'fileImportFailed');
 for(const id of ['import-conflict-continue','import-conflict-cancel'])$(id).disabled=conflictSubmitting;
 if(projectPanelMode==='files'&&!dialog.open)dialog.showModal();
}
async function submitImportConflict(cancel=false){
 if(!importConflict||conflictSubmitting)return;
 const plan=importConflict,choices=cancel?{}:{...conflictChoices};
 const args={projectId:plan.project_id,binding:plan.binding,planId:plan.plan_id,choices,cancel};
 if(cancel){clearImportConflict();importBusy=true;importCancelling=true;importMessage=null;renderProjectFiles();}
 else{conflictSubmitting=true;conflictFailure='';renderImportConflict();}
 try{
  await invoke('project_import_resolve',args);
  if(!cancel&&importConflict?.plan_id===plan.plan_id){clearImportConflict();renderProjectFiles();}
 }catch(error){
  if(cancel&&webState.project?.id===plan.project_id&&webState.import_binding===plan.binding){importBusy=false;importCancelling=false;renderProjectFiles();}
  if(!cancel&&importConflict?.plan_id===plan.plan_id){conflictSubmitting=false;conflictFailure=error;renderImportConflict();}
 }
}
$('import-conflict-continue').addEventListener('click',()=>submitImportConflict());
$('import-conflict-cancel').addEventListener('click',()=>submitImportConflict(true));
$('import-conflict-dialog').addEventListener('cancel',event=>{event.preventDefault();submitImportConflict(true);});
$('import-conflict-all').addEventListener('change',event=>{
 conflictApplyAll=event.target.checked;
 const first=importConflict?.items[0];
 if(first)setConflictChoice(first.id,conflictChoices[first.id]||'skip');
});

function renderProjectDetails(){
 renderProjectRules();
 const wrapper=$('mistral-project-settings'),container=$('mistral-project-settings-body');container.replaceChildren();
 const data=projectDetails?.project_id===webState.project?.id?projectDetails:null;
 wrapper.hidden=isConversation()||!data?.available||data.cached===true;
 if(wrapper.hidden)return;
 // Remaining website-provided settings are rendered as plain text.
 for(const setting of data.settings||[]){
  if(setting.kind==='instructions')continue;
  const section=el('section','project-setting');section.append(el('h3','',t(setting.kind==='tone'?'projectTone':'projectAdditionalContext')));
  if(setting.kind==='context'){
   const label=el('label','project-context'),checkbox=el('input');checkbox.type='checkbox';checkbox.checked=setting.checked===true;checkbox.disabled=!setting.action;
   checkbox.addEventListener('change',()=>projectSettingAction(setting.action,checkbox,data.project_id));
   label.append(checkbox,el('span','',t('projectIncludeOtherChats')));section.append(label);
  }else{
   section.append(el('p','setting-text',/^(?:Standaard|Default|Standard|Par défaut|Défaut)(?:\s*\([^)]+\))?$/i.test(setting.text||'')?t('projectToneDefault'):setting.text));
   if(setting.action){const button=el('button','secondary',t('projectRulesEdit'));button.addEventListener('click',()=>projectSettingAction(setting.action,button,data.project_id));section.append(button);}
  }
  container.append(section);
 }
}
function resetRulesEditor(){
 const draft=rulesEdit;rulesEdit=null;rulesOperation=null;rulesNotice=null;
 $('project-rules-input').value='';
 if(draft&&!draft.api)invoke('project_rules_edit',{projectId:draft.project_id,action:'cancel',nonce:draft.nonce}).catch(()=>{});
}
function currentRulesDetails(){return projectDetails?.project_id===webState.project?.id?projectDetails:null;}
function loadApiRules(projectId){
 apiRules={project_id:projectId,loading:true};
 invoke('project_rules_edit',{projectId,action:'api-read'}).then(result=>{
  if(apiRules?.project_id!==projectId)return;
  apiRules=result?.project_id===projectId&&typeof result.value==='string'?{project_id:projectId,value:result.value}:{project_id:projectId,failed:true};
 }).catch(()=>{if(apiRules?.project_id===projectId)apiRules={project_id:projectId,failed:true};}).finally(()=>{if(webState.project?.id===projectId)renderProjectRules();});
}
function renderProjectRules(){
 const data=currentRulesDetails(),project=webState.project;
 const supported=!isConversation()&&/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(project?.id||'');
 $('project-rules').hidden=!supported;if(!supported)return;
 const editing=rulesEdit?.project_id===project.id,busy=Boolean(rulesOperation);
 const available=data?.available===true,canEdit=available&&data.can_edit===true&&data.cached!==true;
 // Outside the project overview the rules come from Mistral's project request.
 if(!available&&!editing&&apiRules?.project_id!==project.id)loadApiRules(project.id);
 const api=!available&&apiRules?.project_id===project.id&&typeof apiRules.value==='string';
 $('project-rules-text').hidden=editing;
 $('project-rules-text').textContent=available?(data.instructions||t('projectRulesEmpty')):api?(apiRules.value||t('projectRulesEmpty')):t(apiRules?.project_id===project.id&&apiRules.failed?'projectRulesUnavailable':'projectRulesLoading');
 $('project-rules-note').hidden=editing||api||!data?.cached;
 $('project-rules-note').textContent=t('projectRulesCached');
 $('project-rules-form').hidden=!editing;
 $('project-rules-edit').hidden=editing||!(canEdit||api);$('project-rules-edit').disabled=busy;
 $('project-rules-open').hidden=editing||canEdit||api||!data?.can_open_project;$('project-rules-open').disabled=busy;
 $('project-rules-open').title=t('projectRulesOpenProject');
 $('project-rules-input').disabled=busy;
 $('project-rules-save').disabled=busy||!(canEdit||rulesEdit?.api);
 $('project-rules-cancel').disabled=busy;
 const status=$('project-rules-status');status.dataset.error=String(Boolean(rulesNotice?.detail));
 status.textContent=rulesOperation?t(rulesOperation.action==='save'?'projectRulesSaving':'projectRulesLoading'):rulesNotice?t(rulesNotice.key):'';
 status.title=errorText(rulesNotice?.detail,rulesNotice?.key||'projectRulesError');
}
$('project-rules-edit').addEventListener('click',async()=>{
 if(!rulesOperation&&!rulesEdit&&webState.project?.id&&apiRules?.project_id===webState.project.id&&typeof apiRules.value==='string'&&currentRulesDetails()?.available!==true){
  rulesEdit={project_id:webState.project.id,api:true,value:apiRules.value};rulesNotice=null;$('project-rules-input').value=apiRules.value;renderProjectRules();$('project-rules-input').focus();return;
 }
 const data=currentRulesDetails(),projectId=webState.project?.id;
 if(rulesOperation||rulesEdit||!projectId||!data?.available||!data.can_edit||data.cached)return;
 const operation={projectId,action:'open'};rulesOperation=operation;rulesNotice=null;renderProjectRules();
 try{
  const result=await invoke('project_rules_edit',{projectId,action:'open'});
  if(rulesOperation!==operation||webState.project?.id!==projectId){if(result?.nonce)invoke('project_rules_edit',{projectId,action:'cancel',nonce:result.nonce}).catch(()=>{});return;}
  if(result?.project_id!==projectId||typeof result.value!=='string'||typeof result.nonce!=='string')throw {message_key:'projectRulesError'};
  rulesEdit={project_id:projectId,nonce:result.nonce,value:result.value};$('project-rules-input').value=result.value;
 }catch(error){if(rulesOperation===operation)rulesNotice={key:'operationFailed',detail:error};}
 finally{if(rulesOperation===operation){rulesOperation=null;renderProjectRules();if(rulesEdit)$('project-rules-input').focus();}}
});
$('project-rules-input').addEventListener('input',()=>{if(rulesEdit)rulesEdit.value=$('project-rules-input').value;});
$('project-rules-cancel').addEventListener('click',()=>{if(rulesOperation)return;resetRulesEditor();renderProjectRules();$('project-rules-edit').focus();});
$('project-rules-open').addEventListener('click',()=>projectSettingAction('open_project',$('project-rules-open'),webState.project?.id));
$('project-rules-form').addEventListener('submit',async event=>{
 event.preventDefault();const draft=rulesEdit,data=currentRulesDetails();
 if(draft?.api){
  const value=$('project-rules-input').value;if(rulesOperation||draft.project_id!==webState.project?.id||value.length>8000)return;
  const operation={projectId:draft.project_id,action:'save'};rulesOperation=operation;rulesNotice=null;renderProjectRules();
  try{
   const result=await invoke('project_rules_edit',{projectId:draft.project_id,action:'api-save',value});
   if(rulesOperation!==operation||webState.project?.id!==draft.project_id)return;
   if(result?.project_id!==draft.project_id||result.saved!==true)throw {message_key:'projectRulesError'};
   apiRules={project_id:draft.project_id,value:result.value};rulesEdit=null;$('project-rules-input').value='';rulesNotice={key:'projectRulesSaved'};
  }catch(error){if(rulesOperation===operation)rulesNotice={key:'projectRulesError',detail:error};}
  finally{if(rulesOperation===operation){rulesOperation=null;renderProjectRules();}}
  return;
 }
 if(rulesOperation||!draft||draft.project_id!==webState.project?.id||!data?.available||!data.can_edit||data.cached)return;
 const value=$('project-rules-input').value;if(value.length>8000)return;
 const operation={projectId:draft.project_id,action:'save'};rulesOperation=operation;rulesNotice=null;renderProjectRules();
 try{
  const result=await invoke('project_rules_edit',{projectId:draft.project_id,action:'save',value,nonce:draft.nonce});
  if(rulesOperation!==operation||webState.project?.id!==draft.project_id)return;
  if(result?.project_id!==draft.project_id||result.saved!==true)throw {message_key:'projectRulesError'};
  rulesEdit=null;$('project-rules-input').value='';rulesNotice={key:'projectRulesSaved'};
 }catch(error){if(rulesOperation===operation)rulesNotice={key:'projectRulesError',detail:error};}
 finally{if(rulesOperation===operation){rulesOperation=null;renderProjectRules();}}
});
async function projectSettingAction(action,control,expectedProject){
 if(!['instructions','context','open_project'].includes(action))return;
 if(!expectedProject||expectedProject!==webState.project?.id||projectDetails?.project_id!==expectedProject)return;
 if(action==='open_project'?!projectDetails.can_open_project:!projectDetails.available)return;
 control.disabled=true;
 try{await invoke('project_details_action',{projectId:webState.project.id,action,enabled:control.type==='checkbox'?control.checked:null});}
 catch(error){webNotice(error);}
 finally{renderProjectDetails();}
}
window.__TAURI__.event.listen('project-details',e=>{projectDetails=e.payload;renderProjectDetails();});

let browserPath='.',browserRequest=null,browserMove=null,browserDrag=null,browserSerial=0;
function renderBrowserLocation(){$('browser-location').textContent=folderMessage('browserLocation')+' /'+(browserPath==='.'?'':browserPath);}
window.vibezLanguage.onChange(renderBrowserLocation);
async function browse(operation='list',path=browserPath,extra={}){
 const key=webState.project?.id,revision=webState.workspace_binding;if(!key||!revision||browserRequest)return;
 const request={action:'web_local_files',project_id:key,workspace_binding:revision,request_id:'browse-'+Date.now()+'-'+(++browserSerial),operation,path,...extra};browserRequest=request;$('browser-status').textContent=t('loadingFiles');
 try{await invoke('web_command',{payload:request});}catch(error){if(browserRequest===request){browserRequest=null;$('browser-status').textContent=t('fileActionFailed');$('browser-status').title=errorText(error);}}
}
$('file-browser').addEventListener('toggle',()=>{if($('file-browser').open)browse();});
$('browser-refresh').addEventListener('click',()=>browse());
$('browser-up').addEventListener('click',()=>browse('list',browserPath.split('/').slice(0,-1).join('/')||'.'));
$('browser-move-cancel').addEventListener('click',()=>{browserMove=null;$('browser-move-form').hidden=true;});
$('browser-move-form').addEventListener('submit',event=>{event.preventDefault();if(!browserMove)return;const source=browserMove;browserMove=null;$('browser-move-form').hidden=true;browse('move',source,{destination:$('browser-move-target').value.trim()||'.'});});
window.__TAURI__.event.listen('app-engine',event=>{
 const value=event.payload,request=browserRequest;
 if(value.type!=='web_local_files_result'||!request||value.request_id!==request.request_id||value.project_id!==webState.project?.id||value.workspace_binding!==webState.workspace_binding)return;
 browserRequest=null;$('browser-status').textContent=value.error?t('fileActionFailed'):value.truncated?t('fileListTruncated'):'';
 if(value.error)return;
 browserPath=value.path||'.';renderBrowserLocation();$('browser-up').disabled=browserPath==='.';
 const list=$('browser-entries');list.replaceChildren();
 for(const item of value.entries||[]){
  const path=(browserPath==='.'?'':browserPath+'/')+item.name,row=el('li'),button=el(item.type==='directory'?'button':'span','browser-name',(item.type==='directory'?'▱ ':'')+item.name);row.append(button);row.draggable=true;
  row.addEventListener('dragstart',event=>{browserDrag={path,revision:webState.workspace_binding};event.dataTransfer?.setData('text/plain',item.name);});row.addEventListener('dragend',()=>{browserDrag=null;});
  if(item.type==='directory'){
   button.type='button';button.addEventListener('click',()=>browse('list',path));
   row.addEventListener('dragover',event=>{if(browserDrag){event.preventDefault();event.stopPropagation();}});
   row.addEventListener('drop',event=>{if(browserDrag?.revision===webState.workspace_binding){event.preventDefault();event.stopPropagation();const source=browserDrag.path;browserDrag=null;browse('move',source,{destination:path});}});
  }
  const move=el('button','secondary browser-move',t('moveItem'));move.type='button';move.addEventListener('click',()=>{browserMove=path;$('browser-move-source').textContent=item.name;$('browser-move-target').value=browserPath;$('browser-move-form').hidden=false;$('browser-move-target').focus();});row.append(move);list.append(row);
 }
});

// Tabs below the connection status: Files and Advanced (environment, project
// rules, tone and context, changes). Only visibility changes; every section
// keeps its own hidden state and logic. The open tab is remembered for this
// viewer; the tab order is remembered per installation.
let panelTabsView=null,diagnostics=null,diagnosticsAt=0;
(function panelTabs(){
 if(!window.vibezPanelTabs)return;
 const sections={files:['workspace-section','project-files','file-browser'],advanced:['advanced-environment','project-rules','mistral-project-settings','advanced-changes']};
 const panels={files:'tab-files',advanced:'tab-advanced'};
 let saved=null;try{const value=localStorage.getItem('vibez-panel-tab-v2');if(['files','advanced'].includes(value))saved=value;}catch(error){}
 const model=window.vibezPanelTabs.createPanelTabs({savedTab:saved,
  persist:prefs=>{touched=true;invoke('panel_prefs_set',{tabOrder:prefs.tab_order}).catch(error=>webNotice(error));},
  remember:name=>{try{localStorage.setItem('vibez-panel-tab-v2',name);}catch(error){}}});
 let autoOpened=false,dragging=null,touched=false;
 const buttons={files:$('tab-files-button'),advanced:$('tab-advanced-button')};
 function clearDrop(){for(const button of Object.values(buttons))if(button)delete button.dataset.drop;}
 function dropAfter(event,button){
  const box=typeof button.getBoundingClientRect==='function'?button.getBoundingClientRect():null;if(!box)return true;
  const after=event.clientX>box.left+box.width/2;
  const rtl=typeof getComputedStyle==='function'&&getComputedStyle(button).direction==='rtl';
  return rtl?!after:after;
 }
 function bind(name,button){
  button.dataset.tab=name;button.draggable=true;
  button.addEventListener('click',()=>model.select(name));
  button.addEventListener('dragstart',event=>{dragging=name;button.dataset.dragging='true';try{event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',name);}catch(error){}});
  button.addEventListener('dragend',()=>{dragging=null;delete button.dataset.dragging;clearDrop();});
  button.addEventListener('dragover',event=>{if(!dragging||dragging===name)return;event.preventDefault();try{event.dataTransfer.dropEffect='move';}catch(error){}const after=dropAfter(event,button);clearDrop();button.dataset.drop=after?'after':'before';});
  button.addEventListener('dragleave',()=>{delete button.dataset.drop;});
  button.addEventListener('drop',event=>{if(!dragging||dragging===name)return;event.preventDefault();const tab=dragging,after=dropAfter(event,button);dragging=null;clearDrop();model.move(tab,name,after);});
 }
 for(const name of ['files','advanced'])bind(name,buttons[name]);
 function render(){
  const s=model.state(),strip=$('panel-tabs');
  // Buttons are moved only when their order differs: moving a focused button would blur it.
  const wanted=s.order.filter(name=>buttons[name]),present=strip.children?[...strip.children].map(node=>node.dataset.tab):null;
  if(!present||present.join()!==wanted.join())for(const name of wanted)strip.append(buttons[name]);
  for(const name of Object.keys(panels)){
   const on=s.current===name,button=buttons[name];
   button.setAttribute('aria-selected',String(on));button.tabIndex=on?0:-1;
   $(panels[name]).setAttribute('data-active',String(on));
  }
  $('panel-tabs-reset').disabled=s.tab_order.join()===model.TABS.join();
  renderAdvanced();
  sync();
 }
 function sync(){
  const s=model.state(),visible=name=>sections[name].some(id=>!$(id).hidden),any=s.order.some(visible);
  if($('panel-tabs-row').hidden!==!any)$('panel-tabs-row').hidden=!any;
  // An empty tab never hides content that another tab has: show that one instead.
  if(!visible(s.current)){const fallback=s.order.find(visible);if(fallback&&fallback!==s.current){model.select(fallback,true);return;}}
  // The file list is the main content of the Files tab: open it once each time it becomes available.
  if($('file-browser').hidden)autoOpened=false;else if(s.current==='files'&&!autoOpened){autoOpened=true;$('file-browser').open=true;}
 }
 model.onChange(render);
 $('panel-auto-connect').addEventListener('change',async event=>{const box=event.target,on=box.checked===true;if(!await webCommand('web_auto_connect',{enabled:on}))box.checked=!on;});
 $('panel-tabs-reset').addEventListener('click',()=>model.resetOrder());
 // Dragging files over the panel shows the drop area; dragging a tab does not.
 if(typeof document.addEventListener==='function')document.addEventListener('dragenter',()=>{if(dragging)return;const s=model.state();if(s.current!=='files'&&!$('project-files').hidden)model.select('files',true);});
 $('panel-tabs').addEventListener('keydown',event=>{
  if(event.key!=='ArrowLeft'&&event.key!=='ArrowRight')return;event.preventDefault();
  const s=model.state(),index=s.order.indexOf(s.current),next=s.order[(index+(event.key==='ArrowRight'?1:-1)+s.order.length)%s.order.length];
  model.select(next);if(typeof buttons[next]?.focus==='function')buttons[next].focus();
 });
 if(typeof MutationObserver==='function')new MutationObserver(sync).observe($('web-panel'),{attributes:true,attributeFilter:['hidden'],subtree:true});
 window.vibezLanguage.onChange(render);
 panelTabsView={state:()=>model.state(),applyPrefs:prefs=>touched?model.state():model.apply(prefs),folderLinked:()=>model.folderLinked(),sync};
 render();
})();

// Advanced tab: the environment of this project (this computer, the linked
// folder, git branch and repository when the folder is a repository) and the
// recent changes the assistant made.
function activityRows(){
 const id=webState.project?.id;if(!id)return [];
 const seen=new Set(),rows=[];
 for(const row of [...(webState.recent_activity||[]),...(webState.activity||[])]){
  if(!row||row.project_id!==id||!labels[row.action])continue;
  const key=row.action+'\n'+String(row.path||'')+'\n'+Math.round(Number(row.time)*1000);
  if(seen.has(key))continue;seen.add(key);rows.push(row);
 }
 return rows.sort((a,b)=>Number(a.time)-Number(b.time));
}
function formatTime(seconds){
 const when=new Date(Number(seconds)*1000);if(!Number.isFinite(when.getTime())||!(Number(seconds)>0))return null;
 const make=locale=>({short:new Intl.DateTimeFormat(locale,{hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(when),long:new Intl.DateTimeFormat(locale,{dateStyle:'medium',timeStyle:'medium'}).format(when),iso:when.toISOString()});
 try{return make(window.vibezLanguage.state().resolved);}catch(error){return make('en');}
}
function activityItem(row){
 const item=el('li'),main=el('div','file-action-main'),path=String(row.path||'');
 main.append(el('span','file-action-label',t(labels[row.action])),el('span','file-action-name',path));main.title=path;item.append(main);
 if(row.outcome)item.append(el('span','activity-outcome',String(row.outcome)));
 const time=formatTime(row.time);if(time){const node=el('time','file-action-time',time.short);node.dateTime=time.iso;node.title=time.long;item.append(node);}
 return item;
}
function renderAdvanced(){
 const project=webState.project;
 $('advanced-environment').hidden=!project;$('advanced-changes').hidden=!project;
 if(!project)return;
 const facts=$('advanced-environment-facts'),env=webState.environment||{},git=env.git||null;facts.replaceChildren();
 const fact=(key,value)=>facts.append(el('dt','',t(key)),el('dd','',value));
 fact('advancedHost',env.host||t('advancedNone'));
 fact('advancedFolder',webState.folder||t('advancedNone'));
 if(git?.branch)fact('advancedBranch',git.branch);
 if(git?.remote)fact('advancedRepository',git.remote);
 const list=$('advanced-changes-list'),rows=activityRows().reverse();list.replaceChildren();
 for(const row of rows)list.append(activityItem(row));
 contextLabel('advanced-changes-empty',isConversation()?'noRecentConversationActions':'noRecentFileActions');$('advanced-changes-empty').hidden=rows.length>0;
}
window.vibezLanguage.onChange(renderAdvanced);

// Diagnostics: a dialog opened from Settings or from a failed connection. It
// shows the connection facts the engine already keeps (names, counts and
// status codes only; the tunnel address truncated and never a key), the
// technical details of the last error and this project's file activity, and
// copies all of it as one report for a GitHub issue.
function requestDiagnostics(force=false){
 if(!webState.project||!$('diagnostics-dialog').open)return;
 const now=Date.now();if(!force&&now-diagnosticsAt<2000)return;diagnosticsAt=now;
 invoke('web_command',{payload:{action:'web_diagnostics',project_id:webState.project.id}}).catch(()=>{});
}
function diagnosticsFacts(){
 const project=webState.project,d=diagnostics&&project&&diagnostics.project_id===project.id?diagnostics:null,pairs=value=>Object.entries(value||{}).sort().map(([k,v])=>k+' ×'+v);
 const rows=[['advancedTunnel',String(webState.tunnel_status||'unknown')+(d?.tunnel_host?' · '+d.tunnel_host:'')],['advancedConnectorId',webState.local_connector_id||t('advancedNone')]];
 if(d){
  rows.push(['advancedProtocolVersions',d.protocol_versions?.length?d.protocol_versions.join(', '):t('advancedNone')]);
  rows.push(['advancedRequests',[String(d.request_total||0),...pairs(d.request_counts)].join('\n')]);
  rows.push(['advancedRejections',pairs(d.rejections).join(', ')||t('advancedNone')]);
  if(d.timing)rows.push(['advancedTiming',[d.timing.outcome+' ('+d.timing.method+')',...(d.timing.steps||[]).map(([name,s])=>name+' '+s+' s')].join('\n')]);
 }else rows.push(['advancedRequests',t('advancedUnavailable')]);
 // Every rejected request is also a traced request, so it is listed once,
 // with its reason, instead of a second time as a bare rejection.
 const traced=(d?.recent_errors||[]).some(e=>e.rejection);
 const errors=d?[...(d.recent_errors||[]).map(e=>{const time=formatTime(e.time);return (time?time.short+' · ':'')+[e.verb,e.method==='none'?'':e.method,e.tool,e.phase,e.rejection?'rejected: '+e.rejection:'','HTTP '+e.http_status,e.tool_error?'tool error':'',e.session?'session '+e.session:''].filter(Boolean).join(' · ');}),
  ...(traced?[]:(d.recent_rejections||[]).map(r=>'rejected: '+r.reason+' · HTTP '+r.http_status))]:[];
 return {rows,errors};
}
function renderDiagnostics(){
 const project=webState.project;
 $('diagnostics-unavailable').hidden=Boolean(project);$('advanced-connection').hidden=!project;$('advanced-activity').hidden=!project;$('diagnostics-copy').disabled=!project;$('advanced-refresh').disabled=!project;
 if(!project)return;
 const {rows,errors:lines}=diagnosticsFacts(),facts=$('advanced-connection-facts');facts.replaceChildren();
 for(const [key,value]of rows)facts.append(el('dt','',t(key)),el('dd','',value));
 const errors=$('advanced-connection-errors');errors.replaceChildren();
 if(lines.length){errors.append(el('h4','',t('advancedErrors')));const ul=el('ul');for(const line of lines)ul.append(el('li','',line));errors.append(ul);}
 $('diagnostics-details').hidden=!technicalError;$('diagnostics-details-text').textContent=technicalError;
 const list=$('advanced-activity-list'),activity=activityRows();list.replaceChildren();
 for(const row of activity)list.append(activityItem(row));
 contextLabel('advanced-activity-empty',isConversation()?'noRecentConversationActions':'noRecentFileActions');$('advanced-activity-empty').hidden=activity.length>0;
}
function diagnosticsReport(){
 const {rows,errors}=diagnosticsFacts(),env=webState.environment||{},git=env.git||null;
 const out=['VibeZ '+($('panel-version').textContent||''),t('advancedEnvironment')+': '+([env.system,git?.branch?t('advancedBranch')+' '+git.branch:'',git?.remote?t('advancedRepository')+' '+git.remote:''].filter(Boolean).join(', ')||t('advancedNone')),''];
 out.push(t('advancedConnection'));for(const [key,value]of rows)out.push('- '+t(key)+': '+String(value).replace(/\n/g,'; '));
 if(errors.length){out.push('',t('advancedErrors'));for(const line of errors)out.push('- '+line);}
 if(technicalError){out.push('',t('technicalDetails'),technicalError);}
 const activity=activityRows();
 if(activity.length){out.push('',t('advancedActivity'));for(const row of activity)out.push('- '+[formatTime(row.time)?.iso,t(labels[row.action]),row.path,row.outcome].filter(Boolean).join(' · '));}
 return out.join('\n').trim()+'\n';
}
function openDiagnostics(){
 const dialog=$('diagnostics-dialog');$('diagnostics-status').textContent='';
 if(!dialog.open&&typeof dialog.showModal==='function')dialog.showModal();
 renderDiagnostics();requestDiagnostics(true);
}
$('settings-diagnostics').addEventListener('click',openDiagnostics);
$('error-open-diagnostics').addEventListener('click',openDiagnostics);
$('diagnostics-close').addEventListener('click',()=>{const dialog=$('diagnostics-dialog');if(dialog.open&&typeof dialog.close==='function')dialog.close();});
$('advanced-refresh').addEventListener('click',()=>requestDiagnostics(true));
$('diagnostics-copy').addEventListener('click',async()=>{try{await invoke('app_copy',{text:diagnosticsReport()});$('diagnostics-status').textContent=t('diagnosticsCopied');}catch(error){$('diagnostics-status').textContent=t('operationFailed');$('diagnostics-status').title=errorText(error);}});
window.__TAURI__.event.listen('app-engine',e=>{const d=e.payload;if(d.type==='web_diagnostics'&&d.project_id===webState.project?.id){diagnostics=d;if($('diagnostics-dialog').open)renderDiagnostics();}});
window.vibezLanguage.onChange(()=>{if($('diagnostics-dialog').open)renderDiagnostics();});

// Play, pause and stop icons for the file connection. They only forward to the
// existing actions, so every check and message stays the same. Plain "connect"
// moves to the play icon; choosing a folder, cancelling and restoring keep
// their worded button because a beginner needs those words.
(function tunnelControls(){
 const forward=(icon,target)=>$(icon).addEventListener('click',()=>{if(!$(icon).disabled)$(target).click();});
 forward('tunnel-play','auto-connect');forward('tunnel-pause','web-pause');forward('tunnel-stop','web-stop');
 function set(id,on){if($(id).disabled!==!on)$(id).disabled=!on;}
 function sync(){
  const connect=$('auto-connect'),plain=connect.dataset.action==='filesConnect';
  const wanted=plain?'1':'';if((connect.dataset.iconized||'')!==wanted){if(wanted)connect.dataset.iconized='1';else delete connect.dataset.iconized;}
  set('tunnel-play',plain&&!connect.hidden&&!connect.disabled);
  set('tunnel-pause',!$('web-pause').hidden&&!$('web-pause').disabled);
  set('tunnel-stop',!$('web-stop').hidden);
  const show=!connect.hidden||!$('web-pause').hidden||!$('web-stop').hidden;
  if($('tunnel-controls').hidden!==!show)$('tunnel-controls').hidden=!show;
 }
 if(typeof MutationObserver==='function')new MutationObserver(sync).observe($('web-panel'),{attributes:true,attributeFilter:['hidden','disabled','data-action'],subtree:true});
 sync();
})();
