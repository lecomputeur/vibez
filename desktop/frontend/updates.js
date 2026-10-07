'use strict';
(()=>{
  const $=id=>document.getElementById(id);let last=null,reading=false,actionBusy=false,closed=false,base={};
  const baseKeys={checking:'checking',latest:'latest',idle:'checking',ready:'readyInstall',error:'updateFailed'};
  const extraKeys={available:'updateAvailable',downloading:'updateDownloading',store:'updateStoreManaged'};
  const text=s=>extraKeys[s.phase]?preview.extra(extraKeys[s.phase]):(base[baseKeys[s.phase]]||s.phase).replace('{version}',s.release?.version||'');
  function render(s){
    const old=$('package').value;
    if(JSON.stringify(last?.release)!==JSON.stringify(s.release)){
      $('package').replaceChildren();for(const a of s.release?.assets||[]){const o=document.createElement('option');o.value=a.name;o.textContent=`${a.kind} · ${(a.size/1e6).toFixed(1)} MB`;$('package').append(o);}
      if((s.release?.assets||[]).some(a=>a.name===old))$('package').value=old;
    }
    last=s;$('version').textContent=s.release?.version||s.current;$('status').textContent=text(s);
    for(const id of ['download','open','reveal','store','cancel','retry'])$(id).hidden=true;
    $('package').hidden=!(s.phase==='available'||(s.phase==='error'&&s.release));$('package').disabled=s.busy||actionBusy;
    if(s.phase==='available'||(s.phase==='error'&&s.release))$('download').hidden=false;
    if(s.phase==='ready'){$('open').hidden=false;$('reveal').hidden=false;}
    if(s.phase==='store')$('store').hidden=false;
    if(s.phase==='downloading')$('cancel').hidden=false;
    if(s.phase==='error'&&!s.release)$('retry').hidden=false;
    $('progress').hidden=s.phase!=='downloading';$('progress').value=s.total?100*s.received/s.total:0;
    $('size').textContent=s.phase==='downloading'?`${(s.received/1e6).toFixed(1)} / ${(s.total/1e6).toFixed(1)} MB`:s.phase==='ready'?'SHA-256 ✓':'';
    $('filename').textContent=s.fileName||'';$('error').textContent=s.error||'';$('error').hidden=!s.error;
    for(const id of ['download','open','reveal','store','retry'])$(id).disabled=actionBusy||s.busy;
    $('help').hidden=!['available','ready','downloading'].includes(s.phase);
  }
  async function refresh(){if(reading||closed||actionBusy)return;reading=true;try{base=preview.localize(await preview.invoke('get_state'));render(await preview.invoke('update_state'));}catch(e){$('error').hidden=false;$('error').textContent=preview.errorText(e);}finally{reading=false;}}
  async function action(name){if(actionBusy)return;actionBusy=true;try{const result=await preview.invoke('update_action',{action:name,name:$('package').value||null});if(name==='close'){closed=true;return;}render(result);}catch(e){$('error').hidden=false;$('error').textContent=preview.errorText(e);}finally{actionBusy=false;await refresh();}}
  for(const id of ['download','open','reveal','store','cancel','close'])$(id).addEventListener('click',()=>action(id));
  $('retry').addEventListener('click',()=>action('check'));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();action('close');}});
  refresh();const timer=setInterval(refresh,400);window.addEventListener('pagehide',()=>{closed=true;clearInterval(timer);});
})();
