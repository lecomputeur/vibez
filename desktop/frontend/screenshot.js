'use strict';
(() => {
  const $=id=>document.getElementById(id);
  // All UI text comes from the same 34 language bundles as the toolbar.
  const extraKeys={auto:'screenshotAutoPaste',paste:'screenshotPaste',save:'screenshotSavePng',again:'screenshotNew',copied:'screenshotCopied',cancelled:'screenshotCancelled',copyFailed:'screenshotCopyFailed',selectionBusy:'screenshotDrag',working:'screenshotWorking',pasting:'screenshotPaste'};
  const baseKeys={copy:'copy',close:'close',failed:'shotFailed',saving:'saving',saved:'saved'};
  let busy=false,baseStrings={},refreshing=false,closed=false,lastFeedback=null;
  function t(key){return extraKeys[key]?preview.extra(extraKeys[key]):baseStrings[baseKeys[key]||key]||key;}
  function feedback(text='',kind='info'){lastFeedback=null;const e=$('feedback');e.hidden=!text;e.dataset.kind=kind;e.textContent=text;}
  function status(key,kind='info'){feedback(t(key),kind);lastFeedback={key,kind};}
  function lock(value){busy=value;for(const b of document.querySelectorAll('button,input'))b.disabled=value;}
  function choose(){ $('choose').hidden=false;$('result').hidden=true;$('image').removeAttribute('src'); }
  async function close(){await preview.invoke('screenshot_action',{action:'close'});closed=true;}
  function localize(state){
    const language=preview.resolve(state.settings.language,state.os_locale);
    if(language!==preview.currentLanguage()||!Object.keys(baseStrings).length){
      baseStrings=preview.localize(state);
      for(const el of document.querySelectorAll('[data-shot]'))el.textContent=t(el.dataset.shot);
      $('close').setAttribute('aria-label',t('close'));
      $('choose').setAttribute('aria-label',baseStrings.screenshot);
      $('result').setAttribute('aria-label',baseStrings.screenshot);
      $('image').alt=baseStrings.screenshot;document.title=baseStrings.screenshot;
      if(lastFeedback){const {key,kind}=lastFeedback;status(key,kind);}
    }
    $('save').hidden=false;
    const hint=$('code-hint');
    hint.textContent=preview.extra('screenshotCodeHint');
    hint.hidden=state.screenshot_code_context!==true;

  }
  async function refresh(initial=false){
    if(refreshing||closed||(!initial&&busy))return;
    refreshing=true;
    try{localize(await preview.invoke('get_state'));if(initial){lock(false);feedback();document.querySelector('[data-mode="visible"]').focus();}}
    catch(error){if(initial)feedback(preview.errorText(error),'error');}
    finally{refreshing=false;}
  }
  async function capture(mode){
    if(busy)return;lock(true);status(mode==='selection'?'selectionBusy':'working');
    try{
      const result=await preview.invoke('capture_screenshot',{mode,paste:$('auto-paste').checked});
      if(result.cancelled){choose();status('cancelled');return;}
      if(result.pasted){await close();return;}
      if(typeof result.dataUrl!=='string'||!result.dataUrl.startsWith('data:image/png;base64,'))throw new Error('No PNG returned');
      $('image').src=result.dataUrl;$('dimensions').textContent=`${result.width} × ${result.height} px · PNG`;
      $('choose').hidden=true;$('result').hidden=false;
      if(result.pasteError)feedback(result.pasteError,'error');else status(result.copied?'copied':'copyFailed',result.copied?'success':'error');
    }catch(error){choose();feedback(`${t('failed')} ${preview.errorText(error)}`,'error');}
    finally{lock(false);($('result').hidden?document.querySelector('[data-mode="visible"]'):$('copy')).focus();}
  }
  for(const button of document.querySelectorAll('[data-mode]'))button.addEventListener('click',()=>capture(button.dataset.mode));
  for(const action of ['copy','save','paste'])$(action).addEventListener('click',async()=>{
    if(busy)return;lock(true);status(action==='save'?'saving':action==='paste'?'pasting':'working');
    try{const result=await preview.invoke('screenshot_action',{action});if(result.pasted){await close();return;}status(result.cancelled?'cancelled':action==='save'?'saved':'copied','success');}
    catch(error){feedback(preview.errorText(error),'error');}finally{lock(false);}
  });
  $('again').addEventListener('click',async()=>{if(busy)return;try{await preview.invoke('screenshot_action',{action:'new'});choose();feedback();document.querySelector('[data-mode="visible"]').focus();}catch(error){feedback(preview.errorText(error),'error');}});
  $('close').addEventListener('click',()=>{if(!busy)close().catch(error=>feedback(preview.errorText(error),'error'));});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!busy){event.preventDefault();close().catch(error=>feedback(preview.errorText(error),'error'));}});
  refresh(true);
  // Reuse the existing read-only state command: no new native permissions.
  window.addEventListener('focus',()=>refresh());
  const refreshTimer=setInterval(()=>refresh(),1000);
  window.addEventListener('pagehide',()=>{closed=true;clearInterval(refreshTimer);});
})();
