'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const extraKeys={auto:'screenshotAutoPaste',paste:'screenshotPaste',save:'screenshotSavePng',again:'screenshotNew',copied:'screenshotCopied',cancelled:'screenshotCancelled',copyFailed:'screenshotCopyFailed',selectionBusy:'screenshotDrag',working:'screenshotWorking',pasting:'screenshotPaste',fileSaved:'screenshotFileSaved'};
  const baseKeys={copy:'copy',close:'close',failed:'shotFailed',saving:'saving',saved:'saved'};
  let busy=false,baseStrings={},refreshing=false,closed=false,lastFeedback=null,mode='unknown',fileChoice=null,fileResult=false;
  const asFile=()=>mode==='code'||fileChoice===true;
  const fileStrings=()=>window.VIBEZ_SCREENSHOT_FILES?.[preview.currentLanguage()]||window.VIBEZ_SCREENSHOT_FILES?.en||[];
  function t(key){if(key==='fileSaved')return fileStrings()[1]||preview.extra('saved');return extraKeys[key]?preview.extra(extraKeys[key]):baseStrings[baseKeys[key]||key]||key;}
  function render(){
    const file=asFile(),result=!$('result').hidden;
    // Unknown still offers a file option, but must not disable previously
    // working Chat/Work paste simply because the selected mode is unreadable.
    $('file-title').textContent=fileStrings()[0]||'Screenshot as file';
    $('file-option').hidden=['chat','work'].includes(mode)&&!file&&!fileResult;
    $('code-hint').textContent=preview.extra('screenshotCodeHint');
    $('code-hint').hidden=$('file-option').hidden;
    $('as-file').checked=file;$('as-file').disabled=busy||mode==='code';
    $('auto-choice').hidden=file;
    const fileOutput=result&&(fileResult||mode==='code');
    $('save-file').hidden=!fileOutput;$('paste').hidden=fileOutput;
    $('save').hidden=fileOutput;
  }
  function feedback(text='',kind='info'){lastFeedback=null;const e=$('feedback');e.hidden=!text;e.dataset.kind=kind;e.textContent=text;render();}
  function status(key,kind='info'){feedback(t(key),kind);lastFeedback={key,kind};}
  function lock(value){busy=value;for(const b of document.querySelectorAll('button,input'))b.disabled=value;render();}
  function choose(){fileResult=false;$('choose').hidden=false;$('result').hidden=true;$('image').removeAttribute('src');render();}
  async function close(){await preview.invoke('screenshot_action',{action:'close'});closed=true;}
  function localize(state){
    const language=preview.resolve(state.settings.language,state.os_locale);
    if(language!==preview.currentLanguage()||!Object.keys(baseStrings).length){
      baseStrings=preview.localize(state);
      for(const el of document.querySelectorAll('[data-shot]'))el.textContent=t(el.dataset.shot);
      $('close').setAttribute('aria-label',t('close'));
      $('choose').setAttribute('aria-label',t('screenshot'));
      $('result').setAttribute('aria-label',baseStrings.screenshot);
      $('image').alt=baseStrings.screenshot;document.title=baseStrings.screenshot;
      if(lastFeedback){const {key,kind}=lastFeedback;status(key,kind);}
    }
    mode=['code','chat','work'].includes(state.screenshot_mode)?state.screenshot_mode:'unknown';
    render();
  }
  async function refresh(initial=false){
    if(refreshing||closed||(!initial&&busy))return;
    refreshing=true;
    try{localize(await preview.invoke('get_state'));if(initial){lock(false);feedback();document.querySelector('[data-mode="visible"]').focus();}}
    catch(error){if(initial)feedback(preview.errorText(error),'error');}
    finally{refreshing=false;}
  }
  async function saveImage(){
    status('saving');
    const result=await preview.invoke('screenshot_action',{action:'save'});
    if(result.cancelled){status('cancelled');return;}
    if(result.saved!==true)throw new Error(t('failed'));
    status(fileResult?'fileSaved':'saved','success');
    // Keep the preview, allowing another save. Never upload/share automatically
    // and never treat a cancelled dialog as a successfully written PNG.
  }
  async function capture(captureMode){
    if(busy)return;lock(true);let gotPng=false;
    try{
      // Re-read the selected mode when a choice is made, not just on window open.
      localize(await preview.invoke('get_state'));
      const file=asFile();fileResult=file;
      status(captureMode==='selection'?'selectionBusy':'working');
      const result=await preview.invoke('capture_screenshot',{mode:captureMode,paste:!file&&$('auto-paste').checked});
      if(result.cancelled){choose();status('cancelled');return;}
      if(result.pasted&&!file){await close();return;}
      if(typeof result.dataUrl!=='string'||!result.dataUrl.startsWith('data:image/png;base64,'))throw new Error(t('failed'));
      $('image').src=result.dataUrl;$('dimensions').textContent=`${result.width} × ${result.height} px · PNG`;
      $('choose').hidden=true;$('result').hidden=false;gotPng=true;render();
      if(file){await saveImage();}
      else if(result.pasteError)feedback(result.pasteError,'error');
      else status(result.copied?'copied':'copyFailed',result.copied?'success':'error');
    }catch(error){
      // Save failures do not discard a successful capture. Retry uses the same PNG.
      if(!gotPng)choose();
      feedback(`${t('failed')} ${preview.errorText(error)}`,'error');
    }finally{lock(false);($('result').hidden?document.querySelector('[data-mode="visible"]'):fileResult?$('save-file'):$('copy')).focus();}
  }
  for(const button of document.querySelectorAll('[data-mode]'))button.addEventListener('click',()=>capture(button.dataset.mode));
  $('as-file').addEventListener('change',()=>{if(busy||mode==='code')return;fileChoice=$('as-file').checked;render();});
  for(const id of ['copy','save','save-file','paste'])$(id).addEventListener('click',async()=>{
    if(busy)return;
    const action=id==='save-file'?'save':id;
    if(action==='paste'&&(fileResult||mode==='code'))return;
    lock(true);
    try{
      if(action==='save'){await saveImage();return;}
      status(action==='paste'?'pasting':'working');
      const result=await preview.invoke('screenshot_action',{action});
      if(result.pasted){await close();return;}
      status(result.cancelled?'cancelled':'copied',result.cancelled?'info':'success');
    }catch(error){feedback(preview.errorText(error),'error');}finally{lock(false);}
  });
  $('again').addEventListener('click',async()=>{if(busy)return;try{await preview.invoke('screenshot_action',{action:'new'});choose();feedback();document.querySelector('[data-mode="visible"]').focus();}catch(error){feedback(preview.errorText(error),'error');}});
  $('close').addEventListener('click',()=>{if(!busy)close().catch(error=>feedback(preview.errorText(error),'error'));});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!busy){event.preventDefault();close().catch(error=>feedback(preview.errorText(error),'error'));}});
  refresh(true);
  window.addEventListener('focus',()=>refresh());
  const refreshTimer=setInterval(()=>refresh(),1000);
  window.addEventListener('pagehide',()=>{closed=true;clearInterval(refreshTimer);});
})();
