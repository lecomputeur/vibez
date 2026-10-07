/* Focus and observe native delivery and the application's visible attachment UI. */
(() => {
  'use strict';
  const requireFocused=__VIBEZ_PASTE_FOCUSED__;
  window.__vibezPasteReceipt?.cleanup?.();
  const visible = el => {
    if (!el?.isConnected || el.disabled || el.readOnly || el.matches(':disabled') || el.closest('[aria-disabled="true"],[inert]')) return false;
    const r=el.getBoundingClientRect(),s=el.ownerDocument.defaultView.getComputedStyle(el);
    return r.width>=80&&r.height>=12&&s.display!=='none'&&s.visibility!=='hidden';
  };
  const editable=el=>visible(el)&&(el.tagName==='TEXTAREA'||el.isContentEditable)&&!el.closest('[role="search"],.monaco-editor,.cm-editor,.CodeMirror,[data-vibez-no-paste]');
  if(/(^|\/)code(?:\/|$)/i.test(location.pathname))return JSON.stringify({ready:false,reason:'code'});
  const candidates=[];
  function visit(root,depth=0){
    if(depth>4)return;
    for(const el of root.querySelectorAll('textarea,[contenteditable="true"],[contenteditable="plaintext-only"],[role="textbox"],iframe')){
      if(editable(el))candidates.push(el);
      if(el.tagName==='IFRAME'&&visible(el)){try{if(el.contentDocument)visit(el.contentDocument,depth+1);}catch(_){}}
    }
    for(const el of root.querySelectorAll('*'))if(el.shadowRoot)visit(el.shadowRoot,depth+1);
  }
  visit(document);
  candidates.sort((a,b)=>{const active=el=>el.getRootNode().activeElement===el?1:0;return active(b)-active(a)||b.getBoundingClientRect().bottom-a.getBoundingClientRect().bottom;});
  const editor=requireFocused?candidates.find(el=>el.getRootNode().activeElement===el):candidates[0];
  if(!editor)return JSON.stringify({ready:false,reason:'no-editor'});
  editor.focus({preventScroll:true});
  if(editor.getRootNode().activeElement!==editor)return JSON.stringify({ready:false,reason:'no-focus'});
  // Never count receipt of a paste event as application acceptance.
  let scope=editor.closest('form');
  if(!scope||scope.getBoundingClientRect().height>innerHeight*.8){
    scope=editor.parentElement;
    for(let i=0;i<4&&scope?.parentElement&&!['BODY','MAIN','HTML'].includes(scope.parentElement.tagName);i++){
      const next=scope.parentElement,r=next.getBoundingClientRect();if(r.height>innerHeight*.65)break;scope=next;
    }
  }
  if(!scope)scope=editor;
  const receipt={received:false,images:0,trusted:false,bridge:false,editor,scope,cleanup:null,fileNames:[],upload:null};
  const usableUpload=e=>e?.isConnected&&!e.matches(':disabled')&&!e.closest('[aria-disabled="true"],[inert]')&&
    (!e.accept||e.accept.toLowerCase().split(',').some(t=>['image/*','image/png','.png','*','*/*'].includes(t.trim())))&&!e.files?.length;
  const inputs=[...scope.querySelectorAll('input[type="file"]')].filter(usableUpload);
  if(inputs.length===1)receipt.upload=inputs[0];
  const markers='img,[data-testid*="attachment"],[data-testid*="file-card"],[data-testid*="upload-preview"],[data-file-name],[title],[aria-label]';
  function signature(el){return [el.getAttribute('src'),el.getAttribute('title'),el.getAttribute('data-file-name'),el.getAttribute('aria-label'),el.textContent?.slice(0,180)].join('|');}
  const shown=el=>{const r=el.getBoundingClientRect(),s=el.ownerDocument.defaultView.getComputedStyle(el);return r.width>=8&&r.height>=8&&s.display!=='none'&&s.visibility!=='hidden';};
  const initial=new Map([...scope.querySelectorAll(markers)].map(el=>[el,signature(el)]));
  const initialAlerts=new Map([...document.querySelectorAll('[role="alert"]')].filter(shown).map(e=>[e,e.textContent]));
  let firstSeen=0;
  receipt.status=()=>{
    if(!editor.isConnected||!scope.isConnected)return {attached:false,reason:'composer-changed'};
    const alerts=[...document.querySelectorAll('[role="alert"]')].filter(el=>shown(el)&&initialAlerts.get(el)!==el.textContent);
    if(alerts.length)return {attached:false,rejected:true,reason:'site-alert'};
    let found=false;
    for(const el of scope.querySelectorAll(markers)){
      if(el===editor||editor.contains(el)||!shown(el)||initial.get(el)===signature(el))continue;
      const src=el.getAttribute('src')||'';
      const name=[el.getAttribute('title'),el.getAttribute('data-file-name'),el.getAttribute('aria-label'),el.textContent].filter(Boolean).join(' ');
      const named=receipt.fileNames.some(n=>n&&name.includes(n));
      const picture=el.tagName==='IMG'&&/^(blob:|data:image\/)/.test(src)&&el.complete&&el.naturalWidth>8;
      if(named||picture){found=true;break;}
    }
    const pending=[...scope.querySelectorAll('[role="progressbar"],[aria-busy="true"]')].some(shown);
    if(!found||pending)firstSeen=0;else if(!firstSeen)firstSeen=Date.now();
    return {attached:found&&!pending&&Date.now()-firstSeen>=700,pending,received:receipt.received,images:receipt.images,trusted:receipt.trusted,bridge:receipt.bridge};
  };
  const doc=editor.ownerDocument;
  const listener=event=>{
    if(!event.composedPath().includes(editor)&&!editor.contains(event.target))return;
    receipt.received=true;receipt.trusted=event.isTrusted;
    const files=Array.from(event.clipboardData?.files||[]).filter(f=>f.type.startsWith('image/'));
    receipt.images=files.length;receipt.fileNames=files.map(f=>f.name);receipt.bridge=event.vibezScreenshotBridge===true;
  };
  receipt.cleanup=()=>doc.removeEventListener('paste',listener,true);
  doc.addEventListener('paste',listener,true);window.__vibezPasteReceipt=receipt;
  return JSON.stringify({ready:true,canUpload:!!receipt.upload});
})();
