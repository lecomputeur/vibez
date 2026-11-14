/* Read only visible guest controls, not cookies, storage, account data, or
   conversation contents. A missing/unknown control is not proof of logout. */
(() => {
  'use strict';
  const excluded='[hidden],[inert],[aria-hidden="true"],article,[role="log"],[contenteditable],.monaco-editor,.cm-editor,.CodeMirror,.xterm,[data-testid*="message"]';
  const normalize=s=>String(s||'').normalize('NFKC').trim().toLowerCase().replace(/[\s\u200e\u200f]+/g,' ');
  const login=new Set(__VIBEZ_LOGIN_LABELS__.map(normalize));
  const signup=new Set(__VIBEZ_SIGNUP_LABELS__.map(normalize));
  const controls='button,a,[role="button"]';
  function visible(el) {
    if(!el?.isConnected||el.closest(excluded))return false;
    const r=el.getBoundingClientRect(),s=el.ownerDocument.defaultView.getComputedStyle(el);
    // The guest actions are in the page header, not a message or example.
    return r.width>0&&r.height>0&&r.top>=0&&r.top<160&&r.bottom<=200&&
      s.display!=='none'&&s.visibility==='visible'&&s.opacity!=='0';
  }
  const found=[];
  for(const el of Array.from(document.querySelectorAll(controls)).slice(0,200)) {
    if(!visible(el))continue;
    const labels=[el.getAttribute('aria-label'),el.textContent].map(normalize);
    for(const [kind,words] of [['login',login],['signup',signup]])
      if(labels.some(s=>words.has(s)))found.push({el,kind,rect:el.getBoundingClientRect()});
  }
  // Both adjacent guest actions must be present. Do not display a login
  // warning because a signed-in conversation merely mentions "sign in".
  for(const a of found.filter(x=>x.kind==='login'))for(const b of found.filter(x=>x.kind==='signup')) {
    if(a.el===b.el||Math.abs(a.rect.top-b.rect.top)>48)continue;
    let parent=a.el.parentElement;
    for(let depth=0;depth<5&&parent&&!['BODY','HTML'].includes(parent.tagName);depth++,parent=parent.parentElement) {
      if(parent.contains(b.el)&&parent.getBoundingClientRect().height<=200)return true;
    }
  }
  return false;
})();
