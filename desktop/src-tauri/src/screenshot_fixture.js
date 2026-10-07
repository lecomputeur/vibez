/* Offline synthetic UI-test content only; never injected during ordinary use. */
(() => {
  document.body.style.cssText='margin:0;background:white;color:#222;font:16px system-ui';
  document.body.innerHTML='<div id="shot-host" style="position:fixed;inset:0;display:flex;overflow:hidden"><aside style="width:80px;flex-shrink:0;background:rgb(0,200,180)">Sidebar</aside><main id="shot-scroll" style="height:100%;flex:1;overflow-y:auto;padding:0;max-width:none"><div style="height:1800px;position:relative;background:white"><div style="position:absolute;left:24px;top:24px;width:120px;height:100px;background:rgb(230,30,40)"></div><p style="position:absolute;left:24px;top:160px">Native screenshot — offline test</p><canvas id="shot-canvas" width="100" height="80" style="position:absolute;left:24px;top:230px"></canvas><div style="position:absolute;left:24px;top:1400px;width:120px;height:100px;background:rgb(30,60,230)"></div></div></main></div>';
  // Apply via CSSOM, not inline attributes blocked by the real local CSP.
  for(const el of document.body.querySelectorAll('[style]')){const style=el.getAttribute('style');el.removeAttribute('style');el.style.cssText=style;}
  const canvas=document.getElementById('shot-canvas'),c=canvas.getContext('2d');c.fillStyle='rgb(160,40,190)';c.fillRect(0,0,100,80);
  const meta=document.createElement('meta');meta.httpEquiv='Content-Security-Policy';meta.content="default-src 'none'; style-src 'self'; img-src 'self'; script-src 'self'";document.head.append(meta);
})();

// Offline consumer of actual native or clearly identified compatibility image events.
(() => {
  window.__shotPasteEvents=[];
  const form=document.createElement('form');
  form.style.cssText='position:fixed;left:280px;bottom:20px;width:400px;height:70px;z-index:10';
  const editor=document.createElement('textarea');editor.id='shot-composer';editor.value='Bestaande concepttekst';
  editor.style.cssText='width:100%;height:70px;box-sizing:border-box;background:white;color:black';
  let submits=0;
  form.addEventListener('submit',e=>{e.preventDefault();submits++;});
  editor.addEventListener('paste',e=>{
    const files=Array.from(e.clipboardData?.files||[]);
    if(!files.length) return;
    e.preventDefault();
    for(const f of files) {
      const record={trusted:e.isTrusted,bridge:e.vibezScreenshotBridge===true,type:f.type,size:f.size,draft:editor.value,submits,dataUrl:null};
      window.__shotPasteEvents.push(record);
      const reader=new FileReader();reader.onload=()=>{record.dataUrl=reader.result;};reader.readAsDataURL(f);
    }
  });
  form.append(editor);document.body.append(form);
  const toggle=document.createElement('button');toggle.id='shot-block-editor';toggle.textContent='Composer on/off';
  toggle.style.cssText='position:fixed;left:700px;bottom:25px;width:160px;height:40px;z-index:11';
  toggle.addEventListener('click',()=>{editor.readOnly=!editor.readOnly;toggle.textContent=editor.readOnly?'Composer disabled':'Composer on/off';});
  document.body.append(toggle);
})();
