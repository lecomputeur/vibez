// Keep unusable rich-text clipboard artifacts out of the message model.
// Never rewrite literal []() text, inspect the system clipboard or send a message.
(() => {
  'use strict';
  if(location.protocol!=='https:'||!['chat.mistral.ai','vibe.mistral.ai'].includes(location.hostname))return;
  const message=__VIBEZ_EMPTY_ATTACHMENT_MESSAGE__;
  if(window.__vibezAttachmentGuard){
    window.__vibezAttachmentGuard.message=message;
    document.querySelectorAll("[data-vibez-empty-attachment]").forEach(n=>{n.textContent=message;});return;
  }
  const state=window.__vibezAttachmentGuard={message,cleaned:0,removedImages:0,removedLinks:0};
  const editorFor=target=>{
    const editor=target?.closest?.('.ProseMirror[contenteditable="true"]');
    return editor?.closest('form')&&!editor.closest('[role="dialog"],[role="menu"],[role="search"],dialog')?editor:null;
  };
  const meaningfulAttributes=node=>[...node.attributes].some(a=>
    !['src','srcset','alt','title','href','class','style','width','height'].includes(a.name)&&a.value.trim());
  function warn(editor){
    let notice=editor.closest('form').querySelector('[data-vibez-empty-attachment]');
    if(!notice){
      notice=document.createElement('div');notice.setAttribute('data-vibez-empty-attachment','');
      notice.setAttribute('role','status');notice.setAttribute('aria-live','polite');
      notice.style.cssText='font:inherit;font-size:13px;padding:8px 12px;color:inherit;border:1px solid #ff663b;border-radius:8px;margin-top:8px';
      editor.insertAdjacentElement('afterend',notice);
    }
    notice.textContent=state.message;
  }
  document.addEventListener('paste',event=>{
    const editor=editorFor(event.target),data=event.clipboardData;
    if(!editor||!data||event.defaultPrevented||event.vibezCleanPaste)return;
    // A real file transfer belongs to Mistral's upload handler, including VibeZ
    // screenshots. A preview without a URL may be an upload still in progress.
    if(data.files?.length||[...data.items||[]].some(item=>item.kind==='file'))return;
    const html=data.getData('text/html');
    if(!html||html.length>2*1024*1024||!/<(?:img|a)\b/i.test(html))return;
    // Template content is inert: clipboard images are never loaded here.
    const template=document.createElement('template');template.innerHTML=html;
    let images=0,links=0;
    for(const image of template.content.querySelectorAll('img')){
      if(['src','srcset','alt','title'].some(a=>(image.getAttribute(a)||'').trim())||meaningfulAttributes(image))continue;
      image.remove();images++;
    }
    for(const link of template.content.querySelectorAll('a')){
      // Preserve text, named anchors, images, SVG icons and any other children.
      if((link.getAttribute('href')||'').trim()||link.textContent.trim()||link.children.length||meaningfulAttributes(link))continue;
      if(link.textContent)link.replaceWith(document.createTextNode(link.textContent));else link.remove();
      links++;
    }
    if(!images&&!links)return;
    if(typeof DataTransfer!=='function'||typeof ClipboardEvent!=='function')return;
    const transfer=new DataTransfer();
    transfer.setData('text/html',template.innerHTML);
    // Plain clipboard text can deliberately contain Markdown. Keep it verbatim.
    transfer.setData('text/plain',data.getData('text/plain'));
    // Formatting wrappers left behind by an empty image must not replace a
    // selected draft with an empty paragraph. Keep unknown or annotated nodes.
    const emptyMarkup=!template.content.textContent.trim()&&[...template.content.querySelectorAll('*')].every(node=>
      ['P','DIV','SPAN','BR'].includes(node.tagName)&&![...node.attributes].some(a=>a.value.trim()));
    if(emptyMarkup&&!data.getData('text/plain')){
      event.preventDefault();event.stopImmediatePropagation();
      state.cleaned++;state.removedImages+=images;state.removedLinks+=links;warn(editor);return;
    }
    const clean=new ClipboardEvent('paste',{clipboardData:transfer,bubbles:true,cancelable:true,composed:true});
    Object.defineProperty(clean,'vibezCleanPaste',{value:true});
    // Reuse the editor's own parser and sanitization, rather than insertHTML or
    // replacing the draft. Selection, marks and the connector are kept by it.
    const accepted=!editor.dispatchEvent(clean);
    // If the editor refuses the replacement, let the ORIGINAL trusted event
    // continue normally, including the browser's native default paste action.
    if(accepted){
      event.preventDefault();event.stopImmediatePropagation();
      state.cleaned++;state.removedImages+=images;state.removedLinks+=links;
    }
    warn(editor);
  },true);
})();
