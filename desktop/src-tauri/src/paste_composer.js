/* Focus and observe a normal native paste. No image bytes, file access or native IPC. */
(() => {
  'use strict';
  window.__vibezPasteReceipt?.cleanup?.();
  const visible = el => {
    if (!el?.isConnected || el.disabled || el.readOnly || el.getAttribute('aria-disabled') === 'true') return false;
    const r = el.getBoundingClientRect(), s = el.ownerDocument.defaultView.getComputedStyle(el);
    return r.width >= 80 && r.height >= 12 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const editable = el => visible(el) && (el.tagName === 'TEXTAREA' || el.isContentEditable) &&
    !el.closest('[role="search"],.monaco-editor,.cm-editor,.CodeMirror,[data-vibez-no-paste]');
  // Code's terminal/editor is not an image composer. Match its route, not a
  // conversation title which can legitimately contain the word "code".
  if (/(^|\/)code(?:\/|$)/i.test(location.pathname)) return JSON.stringify({ready:false,reason:'code'});
  const candidates = [];
  function visit(root, depth = 0) {
    if (depth > 4) return;
    for (const el of root.querySelectorAll('textarea,[contenteditable="true"],[contenteditable="plaintext-only"],[role="textbox"],iframe')) {
      if (editable(el)) candidates.push(el);
      if (el.tagName === 'IFRAME' && visible(el)) {
        try { if (el.contentDocument) visit(el.contentDocument, depth + 1); } catch (_) { /* cross-origin frames stay isolated */ }
      }
    }
    for (const el of root.querySelectorAll('*')) if (el.shadowRoot) visit(el.shadowRoot, depth + 1);
  }
  visit(document);
  candidates.sort((a,b) => {
    const active = el => el.getRootNode().activeElement === el ? 1 : 0;
    return active(b)-active(a) || b.getBoundingClientRect().bottom-a.getBoundingClientRect().bottom;
  });
  const editor = candidates[0];
  if (!editor) return JSON.stringify({ready:false,reason:'no-editor'});
  editor.focus({preventScroll:true});
  if (editor.getRootNode().activeElement !== editor) return JSON.stringify({ready:false,reason:'no-focus'});
  const receipt = {received:false,images:0,trusted:false,cleanup:null};
  const doc = editor.ownerDocument;
  const listener = event => {
    const path = event.composedPath();
    if (!path.includes(editor) && !editor.contains(event.target)) return;
    // Capture metadata only; do not intercept/defaultPrevent or read other clipboard data.
    receipt.received = true;
    receipt.trusted = event.isTrusted;
    receipt.images = [...(event.clipboardData?.items || [])].filter(i => i.kind === 'file' && i.type.startsWith('image/')).length;
  };
  receipt.cleanup = () => doc.removeEventListener('paste',listener,true);
  doc.addEventListener('paste',listener,true);
  window.__vibezPasteReceipt = receipt;
  return JSON.stringify({ready:true});
})();
