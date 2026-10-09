/* Read only the selected public mode controls. Return an enum, never page text,
   input contents, URLs, account data or storage. Unknown is NOT proof of Chat.
   No click, focus, navigation, clipboard operation or attachment is performed. */
(() => {
  'use strict';
  const controls='button,a,[role="tab"],[role="radio"],[role="combobox"],select';
  const forbidden='[contenteditable="true"],[contenteditable="plaintext-only"],article,[role="log"],.monaco-editor,.cm-editor,.CodeMirror,.xterm';
  const mode=value=>{
    const s=String(value||'').trim().toLowerCase();
    return ['code','chat','work'].includes(s)?s:null;
  };
  function shown(el){
    if(!el?.isConnected||el.closest('[hidden],[inert],'+forbidden))return false;
    const r=el.getBoundingClientRect(),style=el.ownerDocument.defaultView.getComputedStyle(el);
    return r.width>0&&r.height>0&&style.display!=='none'&&style.visibility==='visible';
  }
  function label(el){
    for(const attr of ['data-mode','data-value','aria-label']){
      const found=mode(el.getAttribute(attr));if(found)return found;
    }
    return mode(el.textContent);
  }
  const picked=[];
  for(const el of Array.from(document.querySelectorAll(controls)).slice(0,160)){
    if(!shown(el))continue;
    if(el.tagName==='SELECT'){
      const options=Array.from(el.options);
      if(options.some(o=>mode(o.value)==='code'||mode(o.textContent)==='code')){
        const selected=options.find(o=>o.selected);
        const value=selected&&(mode(selected.value)||mode(selected.textContent));
        if(value)picked.push(value);
      }
      continue;
    }
    const value=label(el);if(!value)continue;
    // An exact Code combo label is useful even when its options are closed.
    // A generic Chat button alone is NOT evidence that Code is inactive.
    if(value==='code'&&el.getAttribute('role')==='combobox')picked.push(value);
    const current=el.getAttribute('aria-current');
    const selected=['aria-selected','aria-pressed','aria-checked'].some(a=>el.getAttribute(a)==='true')||
      (current!==null&&current!=='false')||['active','checked'].includes(el.getAttribute('data-state'));
    if(!selected)continue;
    const group=el.closest('[role="tablist"],[role="radiogroup"],[data-mode-selector],nav')||el.parentElement;
    if(!group||['BODY','HTML'].includes(group.tagName))continue;
    const siblings=Array.from(group.querySelectorAll(controls)).slice(0,24).filter(shown).map(label);
    if(siblings.includes('code')&&(siblings.includes('chat')||siblings.includes('work')))picked.push(value);
  }
  if(picked.includes('code'))return 'code';
  if(picked.includes('chat'))return 'chat';
  if(picked.includes('work'))return 'work';
  return 'unknown';
})();
