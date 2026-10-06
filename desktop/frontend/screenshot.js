'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const strings={
    en:{question:'What would you like to capture?',scope:'Choose a part of the page open in VibeZ.',visibleHelp:'Only what you can see now, without the toolbar.',fullHelp:'The loaded page, including content below the screen.',selectionHelp:'Drag a rectangle on the page. Escape cancels.',loadedOnly:'Full page captures content already loaded, not unloaded chat history.',ready:'Your screenshot',copy:'Copy',save:'Save PNG…',again:'Take another screenshot',private:'No automatic uploads or messages.',close:'Close',initializing:'Loading screenshot tools…',choose:'Choose one of the three options above.',copied:'Copied. Paste into Vibe or another app with Ctrl+V.',saved:'Saved:',cancelled:'Cancelled. Choose an option to try again.',failed:'Screenshot failed.',copyFailed:'Screenshot created, but copying failed. Use Save PNG.',selectionBusy:'Drag on the VibeZ page. Press Escape to cancel.',working:'Creating screenshot…',preview:'Screenshot preview',copying:'Copying…',saving:'Choose where to save the PNG.'},
    nl:{question:'Wat wil je vastleggen?',scope:'Kies een deel van de pagina die in VibeZ openstaat.',visibleHelp:'Alleen wat je nu ziet, zonder de werkbalk.',fullHelp:'De geladen pagina, ook de inhoud onder het scherm.',selectionHelp:'Sleep een rechthoek op de pagina. Escape annuleert.',loadedOnly:'Hele pagina neemt geladen inhoud mee, niet de nog niet geladen chatgeschiedenis.',ready:'Jouw screenshot',copy:'Kopiëren',save:'PNG opslaan…',again:'Nieuwe screenshot maken',private:'Geen automatische uploads of berichten.',close:'Sluiten',initializing:'Screenshotfuncties laden…',choose:'Klik hierboven op een van de drie opties.',copied:'Gekopieerd. Plak met Ctrl+V in Vibe of een andere app.',saved:'Opgeslagen:',cancelled:'Geannuleerd. Kies een optie om opnieuw te beginnen.',failed:'Screenshot maken is mislukt.',copyFailed:'Screenshot gemaakt, maar kopiëren is mislukt. Gebruik PNG opslaan.',selectionBusy:'Sleep op de VibeZ-pagina. Druk op Escape om te annuleren.',working:'Screenshot maken…',preview:'Voorbeeld van je screenshot',copying:'Kopiëren…',saving:'Kies waar je de PNG wilt opslaan.'}
  };
  let lang='en',busy=false,platform='linux';
  const t=key=>(strings[lang]||strings.en)[key]||strings.en[key]||key;
  function feedback(text,kind='info'){$('feedback').dataset.kind=kind;$('feedback-text').textContent=text;}
  function lock(value){busy=value;for(const b of document.querySelectorAll('button'))b.disabled=value;}
  function choose(){ $('choose').hidden=false;$('result').hidden=true;$('image').removeAttribute('src'); }
  function localize(state){preview.localize(state);lang=preview.currentLanguage();for(const el of document.querySelectorAll('[data-shot]'))el.textContent=t(el.dataset.shot);$('close').setAttribute('aria-label',t('close'));$('image').alt=t('preview');platform=state.platform;$('save').hidden=platform!=='linux';}
  async function capture(mode){
    if(busy)return;lock(true);feedback(t(mode==='selection'?'selectionBusy':'working'),'busy');
    try{
      const result=await preview.invoke('capture_screenshot',{mode});
      if(result.cancelled){choose();feedback(t('cancelled'));return;}
      if(typeof result.dataUrl!=='string'||!result.dataUrl.startsWith('data:image/png;base64,'))throw new Error('No PNG returned');
      $('image').src=result.dataUrl;$('dimensions').textContent=`${result.width} × ${result.height} px · PNG`;
      $('choose').hidden=true;$('result').hidden=false;
      feedback(t(result.copied?'copied':'copyFailed'),result.copied?'success':'error');
    }catch(error){choose();feedback(`${t('failed')} ${preview.errorText(error)}`,'error');}
    finally{lock(false);($('result').hidden?document.querySelector('[data-mode="visible"]'):$('copy')).focus();}
  }
  for(const button of document.querySelectorAll('[data-mode]'))button.addEventListener('click',()=>capture(button.dataset.mode));
  for(const action of ['copy','save'])$(action).addEventListener('click',async()=>{
    if(busy)return;lock(true);feedback(t(action==='save'?'saving':'copying'),'busy');
    try{const result=await preview.invoke('screenshot_action',{action});if(result.cancelled)feedback(t('cancelled'));else feedback(action==='save'?`${t('saved')} ${result.path}`:t('copied'),'success');}
    catch(error){feedback(preview.errorText(error),'error');}finally{lock(false);}
  });
  $('again').addEventListener('click',async()=>{if(busy)return;try{await preview.invoke('screenshot_action',{action:'new'});choose();feedback(t('choose'));document.querySelector('[data-mode="visible"]').focus();}catch(error){feedback(preview.errorText(error),'error');}});
  const close=()=>{if(!busy)preview.invoke('screenshot_action',{action:'close'}).catch(error=>feedback(preview.errorText(error),'error'));};
  $('close').addEventListener('click',close);$('done').addEventListener('click',close);
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!busy){event.preventDefault();close();}});
  preview.invoke('get_state').then(state=>{localize(state);lock(false);feedback(t('choose'));document.querySelector('[data-mode="visible"]').focus();})
    .catch(error=>feedback(preview.errorText(error),'error'));
})();
