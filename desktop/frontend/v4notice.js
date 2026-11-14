'use strict';
(()=>{
  const $=id=>document.getElementById(id);let busy=false;
  async function action(name){
    if(busy)return;busy=true;$('error').hidden=true;
    try{await preview.invoke('v4_notice_action',{action:name});}
    catch(e){$('error').textContent=preview.errorText(e);$('error').hidden=false;}
    finally{busy=false;}
  }
  for(const id of ['v4beta','discussions','issue','repo','close'])$(id).addEventListener('click',()=>action(id));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();action('close');}});
  preview.invoke('get_state').then(state=>{preview.localize(state);document.title=preview.extra('v4NoticeTitle');})
    .catch(e=>{$('error').textContent=preview.errorText(e);$('error').hidden=false;});
})();
