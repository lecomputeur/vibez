'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const strings={
    en:{visibleHelp:'What you see in VibeZ',fullHelp:'Including loaded content below',selectionHelp:'Drag on your screen',auto:'Paste directly in Vibe',note:'Pastes into your draft; does not send a message.',paste:'Paste in Vibe',copy:'Copy',save:'Save PNG…',again:'New',copied:'Copied. Paste with Ctrl+V.',cancelled:'Cancelled.',failed:'Screenshot failed.',copyFailed:'Copying failed. Use Save PNG.',selectionBusy:'Drag an area. Escape cancels.',working:'Creating screenshot…',pasting:'Pasting in Vibe…',saving:'Choose where to save the PNG.',saved:'Saved.',close:'Close'},
    nl:{visibleHelp:'Wat je nu in VibeZ ziet',fullHelp:'Ook de geladen inhoud onderaan',selectionHelp:'Sleep een gebied op je scherm',auto:'Meteen in Vibe plakken',note:'Plakt in je concept; verstuurt geen bericht.',paste:'In Vibe plakken',copy:'Kopiëren',save:'PNG opslaan…',again:'Nieuw',copied:'Gekopieerd. Plak met Ctrl+V.',cancelled:'Geannuleerd.',failed:'Screenshot mislukt.',copyFailed:'Kopiëren mislukt. Gebruik PNG opslaan.',selectionBusy:'Sleep een gebied. Escape annuleert.',working:'Screenshot maken…',pasting:'In Vibe plakken…',saving:'Kies waar je de PNG wilt opslaan.',saved:'Opgeslagen.',close:'Sluiten'}
  };
  let lang='en',busy=false;
  const t=key=>(strings[lang]||strings.en)[key]||strings.en[key]||key;
  function feedback(text='',kind='info'){const e=$('feedback');e.hidden=!text;e.dataset.kind=kind;e.textContent=text;}
  function lock(value){busy=value;for(const b of document.querySelectorAll('button,input'))b.disabled=value;}
  function choose(){ $('choose').hidden=false;$('result').hidden=true;$('image').removeAttribute('src'); }
  async function close(){await preview.invoke('screenshot_action',{action:'close'});}
  function localize(state){preview.localize(state);lang=preview.currentLanguage();for(const el of document.querySelectorAll('[data-shot]'))el.textContent=t(el.dataset.shot);$('close').setAttribute('aria-label',t('close'));$('save').hidden=state.platform!=='linux';}
  async function capture(mode){
    if(busy)return;lock(true);feedback(t(mode==='selection'?'selectionBusy':'working'));
    try{
      const result=await preview.invoke('capture_screenshot',{mode,paste:$('auto-paste').checked});
      if(result.cancelled){choose();feedback(t('cancelled'));return;}
      if(result.pasted){await close();return;}
      if(typeof result.dataUrl!=='string'||!result.dataUrl.startsWith('data:image/png;base64,'))throw new Error('No PNG returned');
      $('image').src=result.dataUrl;$('dimensions').textContent=`${result.width} × ${result.height} px · PNG`;
      $('choose').hidden=true;$('result').hidden=false;
      feedback(result.pasteError || t(result.copied?'copied':'copyFailed'),result.pasteError||!result.copied?'error':'success');
    }catch(error){choose();feedback(`${t('failed')} ${preview.errorText(error)}`,'error');}
    finally{lock(false);($('result').hidden?document.querySelector('[data-mode="visible"]'):$('copy')).focus();}
  }
  for(const button of document.querySelectorAll('[data-mode]'))button.addEventListener('click',()=>capture(button.dataset.mode));
  for(const action of ['copy','save','paste'])$(action).addEventListener('click',async()=>{
    if(busy)return;lock(true);feedback(t(action==='save'?'saving':action==='paste'?'pasting':'working'));
    try{const result=await preview.invoke('screenshot_action',{action});if(result.pasted){await close();return;}feedback(t(result.cancelled?'cancelled':action==='save'?'saved':'copied'),'success');}
    catch(error){feedback(preview.errorText(error),'error');}finally{lock(false);}
  });
  $('again').addEventListener('click',async()=>{if(busy)return;try{await preview.invoke('screenshot_action',{action:'new'});choose();feedback();document.querySelector('[data-mode="visible"]').focus();}catch(error){feedback(preview.errorText(error),'error');}});
  $('close').addEventListener('click',()=>{if(!busy)close().catch(error=>feedback(preview.errorText(error),'error'));});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!busy){event.preventDefault();close().catch(error=>feedback(preview.errorText(error),'error'));}});
  preview.invoke('get_state').then(state=>{localize(state);lock(false);feedback();document.querySelector('[data-mode="visible"]').focus();})
    .catch(error=>feedback(preview.errorText(error),'error'));
})();
