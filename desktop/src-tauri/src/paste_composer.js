/* Locate the real editing host, then observe delivery separately from acceptance.
   No page text, account data, clipboard bytes or native privileges are collected. */
(() => {
  'use strict';
  const requireFocused=__VIBEZ_PASTE_FOCUSED__;
  window.__vibezPasteReceipt?.cleanup?.();
  const selector='textarea,[contenteditable],[role="textbox"],input[type="text"],input:not([type])';
  const excluded='[role="search"],.monaco-editor,.cm-editor,.CodeMirror,.xterm,[data-vibez-no-paste]';
  const stats={scanned:0,editable:0,hidden:0,blocked:0,frames:0,shadows:0,width:innerWidth,height:innerHeight};
  const parent=el=>el.parentElement||el.getRootNode()?.host||null;
  const ancestor=(el,query)=>{for(let p=el;p;p=parent(p))if(p.matches?.(query))return p;return null;};
  function active(root){let el=root.activeElement;while(el?.shadowRoot?.activeElement)el=el.shadowRoot.activeElement;return el;}
  function host(el){
    if(!el)return null;
    if(el.tagName==='TEXTAREA')return el;
    if(el.tagName==='INPUT'&&['text',''].includes(el.type)){
      // A generic search/login input is not an image composer.
      return el.getAttribute('role')==='textbox'||ancestor(el,'[data-testid*="composer"],[data-composer]')?el:null;
    }
    if(!el.isContentEditable)return null;
    while(el.parentElement?.isContentEditable)el=el.parentElement;
    return el;
  }
  function box(el){
    let r=el.getBoundingClientRect();
    if((r.width<=0||r.height<=0)&&el.isContentEditable){
      const range=el.ownerDocument.createRange();range.selectNodeContents(el);r=range.getBoundingClientRect();
    }
    return r;
  }
  function eligible(el){
    if(!el?.isConnected)return false;
    if(el.disabled||el.readOnly||el.getAttribute('aria-disabled')==='true'||el.matches(':disabled')||ancestor(el,'[inert]')||ancestor(el,excluded)){
      stats.blocked++;return false;
    }
    const r=box(el),s=el.ownerDocument.defaultView.getComputedStyle(el);
    // Small/inline rich-text hosts are valid. 80px wide and 12px high were
    // accidental restrictions, not a definition of an editable message field.
    if(r.width<=0||r.height<=0||s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'){
      stats.hidden++;return false;
    }
    return true;
  }
  const fail=reason=>JSON.stringify({ready:false,reason,stats});
  // A /code route may contain an ordinary message composer beside a code
  // editor. Exclude the actual editor/terminal element, never the whole page.
  const candidates=[],seen=new Set();
  function add(el){const h=host(el);if(!h||seen.has(h))return;seen.add(h);stats.editable++;if(eligible(h))candidates.push(h);}
  function visit(root,depth=0){
    if(depth>6)return;
    add(active(root));
    for(const el of root.querySelectorAll(selector)){stats.scanned++;add(el);}
    for(const el of root.querySelectorAll('iframe')){
      try{if(el.contentDocument&&el.getBoundingClientRect().width>0){stats.frames++;visit(el.contentDocument,depth+1);}}catch(_){/* cross-origin stays isolated */}
    }
    for(const el of root.querySelectorAll('*'))if(el.shadowRoot){stats.shadows++;visit(el.shadowRoot,depth+1);}
  }
  visit(document);
  const focused=el=>{const a=active(el.getRootNode());return a===el||el.contains(a);};
  const isComposer=el=>!!ancestor(el,'[data-testid*="composer"],[data-composer],form');
  candidates.sort((a,b)=>Number(focused(b))-Number(focused(a))||Number(isComposer(b))-Number(isComposer(a))||box(b).bottom-box(a).bottom);
  const editor=requireFocused?candidates.find(focused):candidates[0];
  if(!editor)return fail(requireFocused?'no-focused-editor':'no-editor');
  editor.focus({preventScroll:true});
  // Some rich editors focus a descendant; that still targets the same host.
  if(!focused(editor))return fail('focus-not-ready');
  const doc=editor.ownerDocument;
  if(!doc.hasFocus())return fail('window-not-focused');
  let scope=editor.closest('form');
  if(!scope){
    scope=editor.parentElement||editor;
    for(let i=0;i<6&&scope.parentElement&&!['BODY','MAIN','HTML'].includes(scope.parentElement.tagName);i++){
      const next=scope.parentElement;if(box(next).height>doc.defaultView.innerHeight*.8)break;scope=next;
    }
  }
  const receipt={received:false,images:0,trusted:false,bridge:false,editor,scope,cleanup:null,fileNames:[],upload:null};
  const usableUpload=e=>!e.disabled&&!e.matches(':disabled')&&!ancestor(e,'[inert]')&&
    (!e.accept||e.accept.toLowerCase().split(',').some(t=>['image/*','image/png','.png','*','*/*'].includes(t.trim())))&&!e.files?.length;
  const inputs=[...scope.querySelectorAll('input[type="file"]')].filter(usableUpload);
  if(inputs.length===1)receipt.upload=inputs[0];
  const markers='img,[data-testid*="attachment"],[data-testid*="file-card"],[data-testid*="upload-preview"],[data-file-name],[title],[aria-label],a[download],span';
  function signature(el){return [el.getAttribute('src'),el.getAttribute('title'),el.getAttribute('data-file-name'),el.getAttribute('aria-label'),el.textContent?.slice(0,180)].join('|');}
  const shown=el=>{const r=el.getBoundingClientRect(),s=el.ownerDocument.defaultView.getComputedStyle(el);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
  const initial=new Map([...scope.querySelectorAll(markers)].map(el=>[el,signature(el)]));
  const initialAlerts=new Map([...doc.querySelectorAll('[role="alert"]')].filter(shown).map(e=>[e,e.textContent]));
  let firstSeen=0;
  receipt.status=()=>{
    if(!scope.isConnected)return {attached:false,reason:'composer-changed'};
    if([...doc.querySelectorAll('[role="alert"]')].some(el=>shown(el)&&initialAlerts.get(el)!==el.textContent))
      return {attached:false,rejected:true,reason:'site-alert'};
    let found=false;
    for(const el of scope.querySelectorAll(markers)){
      if(el===editor||!shown(el)||initial.get(el)===signature(el))continue;
      // A new IMG inside a rich-text editing host is also a real attachment.
      // Draft text itself is never taken as evidence of an upload.
      const src=el.getAttribute('src')||'';
      const name=[el.getAttribute('title'),el.getAttribute('data-file-name'),el.getAttribute('aria-label'),el.getAttribute('download'),el.textContent].filter(Boolean).join(' ');
      const named=!editor.contains(el)&&receipt.fileNames.some(n=>n&&name.includes(n));
      const picture=el.tagName==='IMG'&&/^(blob:|data:image\/)/.test(src)&&el.complete&&el.naturalWidth>8;
      if(named||picture){found=true;break;}
    }
    const pending=[...scope.querySelectorAll('[role="progressbar"],[aria-busy="true"]')].some(shown);
    if(!found||pending)firstSeen=0;else if(!firstSeen)firstSeen=Date.now();
    return {attached:found&&!pending&&Date.now()-firstSeen>=700,pending,received:receipt.received,images:receipt.images,trusted:receipt.trusted,bridge:receipt.bridge};
  };
  const listener=event=>{
    if(!event.composedPath().includes(editor)&&!editor.contains(event.target))return;
    receipt.received=true;receipt.trusted=event.isTrusted;
    const files=Array.from(event.clipboardData?.files||[]).filter(f=>f.type.startsWith('image/'));
    receipt.images=files.length;receipt.fileNames=files.map(f=>f.name);receipt.bridge=event.vibezScreenshotBridge===true;
  };
  receipt.cleanup=()=>doc.removeEventListener('paste',listener,true);
  doc.addEventListener('paste',listener,true);window.__vibezPasteReceipt=receipt;
  return JSON.stringify({ready:true,canUpload:!!receipt.upload,kind:editor.tagName,stats});
})();
