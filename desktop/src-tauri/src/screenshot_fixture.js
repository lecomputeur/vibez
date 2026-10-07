/* Offline synthetic test content only; never injected during ordinary use. */
(() => {
  document.body.style.cssText='margin:0;background:white;color:#222;font:16px system-ui';
  document.body.innerHTML='<div id="shot-host" style="position:fixed;inset:0;display:flex;overflow:hidden"><aside style="width:80px;flex-shrink:0;background:rgb(0,200,180)">Sidebar</aside><main id="shot-scroll" style="height:100%;flex:1;overflow-y:auto;padding:0;max-width:none"><div style="height:1800px;position:relative;background:white"><div style="position:absolute;left:24px;top:24px;width:120px;height:100px;background:rgb(230,30,40)"></div><p style="position:absolute;left:24px;top:160px">Native screenshot — offline test</p><canvas id="shot-canvas" width="100" height="80" style="position:absolute;left:24px;top:230px"></canvas><div style="position:absolute;left:24px;top:1400px;width:120px;height:100px;background:rgb(30,60,230)"></div></div></main></div>';
  for(const el of document.body.querySelectorAll('[style]')){const style=el.getAttribute('style');el.removeAttribute('style');el.style.cssText=style;}
  const canvas=document.getElementById('shot-canvas'),c=canvas.getContext('2d');c.fillStyle='rgb(160,40,190)';c.fillRect(0,0,100,80);
  const meta=document.createElement('meta');meta.setAttribute('data-vibez-test-csp','');meta.httpEquiv='Content-Security-Policy';meta.content="default-src 'none'; style-src 'self'; img-src 'self'; script-src 'self'";document.head.append(meta);
})();
(() => {
  window.__shotPasteEvents=[];
  const form=document.createElement('form');form.style.cssText='position:fixed;left:280px;bottom:20px;width:400px;height:70px;z-index:10';
  const editor=document.createElement('textarea');editor.id='shot-composer';editor.value='Bestaande concepttekst';editor.style.cssText='width:100%;height:70px;box-sizing:border-box;background:white;color:black';
  let submits=0;form.addEventListener('submit',e=>{e.preventDefault();submits++;});
  const attachments=document.createElement('div');attachments.style.cssText='position:absolute;bottom:78px;left:0;width:400px;min-height:30px;background:white';
  const upload=document.createElement('input');upload.type='file';upload.accept='image/png';upload.hidden=true;
  function receive(files,trusted,bridge){
    if(window.__shotPasteMode==='ignore')return;
    for(const f of files){
      const record={trusted,bridge,type:f.type,size:f.size,draft:editor.value,submits,dataUrl:null};window.__shotPasteEvents.push(record);
      const reader=new FileReader();reader.onload=()=>{
        record.dataUrl=reader.result;
        if(window.__shotPasteMode==='reject'){const error=document.createElement('div');error.setAttribute('role','alert');error.textContent='Upload rejected';attachments.append(error);return;}
        const show=()=>{const chip=document.createElement('span');chip.setAttribute('data-file-name',f.name);chip.textContent=f.name;chip.style.cssText='display:block;width:380px;height:30px';attachments.append(chip);};
        if(window.__shotPasteMode==='delay')setTimeout(show,800);else show();
      };reader.readAsDataURL(f);
    }
  }
  editor.addEventListener('paste',e=>{const files=Array.from(e.clipboardData?.files||[]);if(files.length){e.preventDefault();receive(files,e.isTrusted,e.vibezScreenshotBridge===true);}});
  upload.addEventListener('change',()=>{receive(Array.from(upload.files),false,true);upload.value='';});
  form.append(attachments,upload,editor);document.body.append(form);
  const toggle=document.createElement('button');toggle.id='shot-block-editor';toggle.textContent='Composer on/off';toggle.style.cssText='position:fixed;left:700px;bottom:25px;width:160px;height:40px;z-index:11';
  toggle.addEventListener('click',()=>{editor.readOnly=!editor.readOnly;toggle.textContent=editor.readOnly?'Composer disabled':'Composer on/off';});document.body.append(toggle);
})();
