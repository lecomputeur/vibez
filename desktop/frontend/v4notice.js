'use strict';
(()=>{
  const $=id=>document.getElementById(id);let busy=false;
  async function action(name){
    if(busy)return;busy=true;$('error').hidden=true;
    try{await preview.invoke('v4_notice_action',{action:name});}
    catch(e){$('error').textContent=preview.errorText(e);$('error').hidden=false;}
    finally{busy=false;}
  }
  for(const id of ['official','discussions','issue','repo','close'])$(id).addEventListener('click',()=>action(id));
  // Linux keeps VibeZ until Mistral's Linux app exists; Windows and macOS get no further updates.
  const agent=typeof navigator==='object'&&navigator?String(navigator.userAgent||''):'';
  const linux=/Linux/.test(agent)&&!/Android/.test(agent);
  $('stable').hidden=linux;$('linux').hidden=!linux;
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();action('close');}});
  preview.invoke('get_state').then(state=>{preview.localize(state);document.title=preview.extra('v4NoticeTitle');})
    .catch(e=>{$('error').textContent=preview.errorText(e);$('error').hidden=false;});
})();
