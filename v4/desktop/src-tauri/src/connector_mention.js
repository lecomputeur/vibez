// Use Mistral's native rich-text paste path. Never open or search a menu.
(() => {
  const config=__VIBEZ_CONNECTOR_CONTEXT__;
  if(location.protocol!=='https:'||!['chat.mistral.ai','vibe.mistral.ai'].includes(location.hostname))return;
  // Work folder connectors are named vibezwork<16 hex>; project and
  // conversation connectors carry the title "VibeZ · <project>". Mistral needs
  // that reference in the message, but people need not see it: hide the label
  // in the composer, sent messages and tool lines. Menus, dialogs and the
  // connector pages keep it, because VibeZ's own setup steps look for it there.
  // A title chip is hidden only for a title VibeZ itself passed in (quiet.titles).
  if(!window.__vibezWorkLabelQuiet){
    const label=/vibezwork[0-9a-f]{16}/,exact=/^vibezwork[0-9a-f]{16}$/,inline=/(\s?)vibezwork[0-9a-f]{16}(\s?)/g;
    const titled=v=>quiet.titles.has((v||'').trim());
    const marked=v=>label.test(v||'')||titled(v);
    const skip='[role="dialog"],[role="alertdialog"],[role="menu"],[role="listbox"],[data-radix-popper-content-wrapper]';
    const block='p,li,h1,h2,h3,h4,blockquote,pre,[contenteditable="true"],.ProseMirror,main,body';
    const quiet=window.__vibezWorkLabelQuiet={hidden:0,titles:new Set()};
    const style=document.createElement('style');style.id='vibez-work-label-quiet';
    style.textContent='[data-vibez-quiet-label]{display:none!important}';
    const text=node=>{
      const parent=node.parentElement;
      if(!parent||!marked(node.nodeValue)||location.pathname.startsWith('/connections'))return;
      if(parent.closest(skip)||parent.closest('style,script,textarea,input'))return;
      // Mistral renders menus, drawers and connector pickers in portals beside
      // <main>, whatever roles they carry; VibeZ's own setup steps read the
      // label there. Only the chat area itself (composer, messages, tool
      // lines) is quieted.
      const main=document.querySelector('main');
      if(main&&!main.contains(parent))return;
      // In the composer a title chip is judged by its connector UUID below, never by its text.
      if(!label.test(node.nodeValue||'')&&parent.closest('[contenteditable="true"]'))return;
      if(exact.test((node.nodeValue||'').trim())||titled(node.nodeValue)){
        // The label is a chip of its own: hide that chip (and its icon).
        let chip=parent;
        for(let i=0;i<4;i++){
          const up=chip.parentElement;
          if(!up||up.matches(block)||(up.textContent||'').trim()!==node.nodeValue.trim())break;
          chip=up;
        }
        if(chip.matches(block))return;
        if(!chip.hasAttribute('data-vibez-quiet-label')){chip.setAttribute('data-vibez-quiet-label','');quiet.hidden++;}
        // Work keeps a separator space next to the chip. It is not typed text;
        // left beside an invisible chip it shows as a gap: in the composer one
        // Backspace cannot remove, in a sent message a word split in two
        // ("T est"). The composer loses one on each side (ProseMirror reads the
        // removal back); a sent message or tool line loses the one after the
        // chip, or else the one before it, so typed spacing stays.
        const after=chip.nextSibling,before=chip.previousSibling;
        const afterSpace=after&&after.nodeType===3&&/^[\s\u00a0\u200b]/.test(after.nodeValue||'');
        const beforeSpace=before&&before.nodeType===3&&/[\s\u00a0\u200b]$/.test(before.nodeValue||'');
        const composer=Boolean(chip.closest('[contenteditable="true"]'));
        if(afterSpace&&(composer||!chip.hasAttribute('data-vibez-quiet-gap'))){after.nodeValue=after.nodeValue.slice(1);chip.setAttribute('data-vibez-quiet-gap','');}
        if(beforeSpace&&(composer||!chip.hasAttribute('data-vibez-quiet-gap'))){before.nodeValue=before.nodeValue.slice(0,-1);chip.setAttribute('data-vibez-quiet-gap','');}
        // A Code project renders a sent message as " <chip> text": a whitespace-only
        // node before the chip is never typed text, so it goes as well.
        if(!composer&&before&&before.nodeType===3&&!/\S/.test(before.nodeValue||''))before.nodeValue='';
        for(const near of [after,before])if(near&&near.nodeType===3&&!near.nodeValue)near.remove();
        // Mistral starts a sent message that carries a reference with a space of
        // its own, and a reference added beside a typed draft brings a second
        // one. With the chip invisible they would show as an indent before the
        // first word, so a sent message never starts with white space.
        if(!composer){
          const line=chip.closest('p,li')||chip.parentElement;
          if(line&&!line.closest('[contenteditable="true"]')){
            const walker=document.createTreeWalker(line,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement?.closest('[data-vibez-quiet-label]')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
            let lead;
            while((lead=walker.nextNode())){
              const trimmed=lead.nodeValue.replace(/^[\s\u00a0\u200b]+/,'');
              if(trimmed!==lead.nodeValue)lead.nodeValue=trimmed;
              if(trimmed)break;
            }
          }
        }
        return;
      }
      // Inside other text (a tool line): drop the name. Never edit typed text.
      if(parent.closest('[contenteditable="true"]')||!label.test(node.nodeValue||''))return;
      // The label and its one separator: the space after it, else the one before.
      const cleaned=node.nodeValue.replace(inline,(_,lead,trail)=>trail?lead:'');
      if(cleaned!==node.nodeValue)node.nodeValue=cleaned;
    };
    const scan=root=>{
      if(!root)return;
      if(root.nodeType===3){text(root);return;}
      if(root.nodeType!==1&&root.nodeType!==9)return;
      const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:n=>marked(n.nodeValue)?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_SKIP});
      const found=[];while(walker.nextNode())found.push(walker.currentNode);
      found.forEach(text);
    };
    quiet.scan=scan;
    const start=()=>{
      if(!document.getElementById('vibez-work-label-quiet'))(document.head||document.documentElement).append(style);
      scan(document.body);
      new MutationObserver(list=>{for(const m of list){if(m.type==='characterData')text(m.target);else m.addedNodes.forEach(scan);}})
        .observe(document.body,{childList:true,subtree:true,characterData:true});
    };
    if(document.body)start();else document.addEventListener('DOMContentLoaded',start,{once:true});
  }
  // The verified project context names this project's connector title; only a
  // title VibeZ passed in is ever hidden in sent messages and tool lines.
  {
    const quiet=window.__vibezWorkLabelQuiet,title=config?.title;
    if(quiet?.titles&&typeof title==='string'&&title.startsWith('VibeZ · ')&&title.length<=200&&!/[\x00-\x1f\x7f]/.test(title)&&!quiet.titles.has(title)){quiet.titles.add(title);if(document.body)quiet.scan?.(document.body);}
  }
  const visible=e=>!!e&&e.getClientRects().length>0;
  const uuid=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
  let state=window.__vibezLocalConnectorMention;
  if(!state||state.version!==24){
    state=window.__vibezLocalConnectorMention={version:24,managed:new WeakMap(),attempts:new WeakMap(),config:null,status:'idle'};
    // Reconcile again at a genuine send, so normal Select All / Replace typing
    // cannot accidentally remove the invisible routing reference.
    const sent=e=>{if(!e.isTrusted)return;state.sending=true;try{state.refresh?.();}finally{state.sending=false;}const form=e.target?.closest?.('form');if(!form)return;const editor=form.querySelector('div.ProseMirror[contenteditable="true"]');const record=state.managed.get(editor);if(record)record.sent=true;};
    const editorEvent=e=>e.isTrusted&&e.target?.closest?.('div.ProseMirror[contenteditable="true"]');
    document.addEventListener('input',e=>{if(editorEvent(e))setTimeout(()=>state.refresh?.(),0);},true);
    document.addEventListener('compositionstart',e=>{if(editorEvent(e))state.composing=true;},true);
    document.addEventListener('compositionend',e=>{if(editorEvent(e)){state.composing=false;setTimeout(()=>state.refresh?.(),0);}},true);
    document.addEventListener('submit',sent,true);
    document.addEventListener('pointerdown',e=>{if(e.target?.closest?.('button[type="submit"]'))sent(e);},true);
    document.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&e.target?.closest?.('div.ProseMirror[contenteditable="true"]'))sent(e);},true);
    // The hidden reference is an atom: beside it, the first Backspace or Delete
    // would silently remove the chip and nothing else. Step the caret over the
    // hidden chip first, so the key removes the character a person sees.
    const stepOver=e=>{
      if(!e.isTrusted||e.isComposing||(e.key!=='Backspace'&&e.key!=='Delete')||e.altKey||e.ctrlKey||e.metaKey)return;
      const editor=e.target?.closest?.('div.ProseMirror[contenteditable="true"]');if(!editor)return;
      const record=state.managed.get(editor);if(!record)return;
      const selection=document.getSelection();if(!selection||!selection.isCollapsed||selection.rangeCount!==1)return;
      const node=selection.anchorNode,offset=selection.anchorOffset;if(!node||!editor.contains(node))return;
      const back=e.key==='Backspace';
      const hidden=el=>!!el&&el.nodeType===1&&el.getAttribute('contenteditable')==='false'&&el.getAttribute('aria-hidden')==='true'&&editor.contains(el)&&(record.presentation?.has(el)||el.style.display==='none');
      // The element right before (Backspace) or after (Delete) the caret.
      let beside=null;
      if(node.nodeType===3){if(back?offset===0:offset===node.nodeValue.length)beside=back?node.previousSibling:node.nextSibling;}
      else beside=back?node.childNodes[offset-1]||null:node.childNodes[offset]||null;
      if(!hidden(beside))return;
      const text=back?beside.previousSibling:beside.nextSibling;
      if(!text||text.nodeType!==3||!text.nodeValue.length){e.preventDefault();return;}
      const range=document.createRange();range.setStart(text,back?text.nodeValue.length:0);range.collapse(true);
      selection.removeAllRanges();selection.addRange(range);
      // ProseMirror reads the selection back on this event; it must do so now,
      // before its own key handling, or it would still delete the atom itself.
      document.dispatchEvent(new Event('selectionchange'));
    };
    document.addEventListener('keydown',stepOver,true);
  }
  state.config=config;
  state.refresh=()=>{
    const config=state.config;
    const title=config?.title;
    const project=config?.project;
    const workLabel=typeof project==='string'&&!project.startsWith('code-')&&typeof title==='string'&&/^vibezwork[a-f0-9]{16}$/.test(title);
    const legacyLabel=typeof title==='string'&&title.startsWith('VibeZ · ')&&title.length<=200&&!/[\x00-\x1f\x7f]/.test(title);
    const valid=config&&config.url===location.href&&(workLabel||legacyLabel)&&typeof project==='string'&&uuid.test(project.replace(/^(code-|chat-)/,''))&&uuid.test(config.connector_id)&&typeof config.attach==='boolean';
    const attach=valid&&config.attach;
    const editors=[...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(visible);
    if(editors.length!==1){state.status='waiting_editor';return;}
    const editor=editors[0],root=editor.pmViewDesc,doc=root?.node,schema=doc?.type?.schema,slash=schema?.nodes?.slash;
    if(!doc||typeof doc.descendants!=='function'||!slash?.isInline||!slash.isAtom||!slash.spec.parseDOM?.some(p=>p.tag==='span.slash-node')||!['slashType','subType','selectedValue','selectedLabel'].every(k=>slash.spec.attrs?.[k])){state.status='unsupported_editor';return;}
    if([...document.querySelectorAll('[role="dialog"],[role="menu"]')].some(visible)){state.status='user_menu';return;}
    const referenceDOM=node=>{
      const pending=[editor.pmViewDesc];
      while(pending.length){const desc=pending.pop();if(!desc)continue;if(desc.node===node&&desc.dom?.isConnected&&editor.contains(desc.dom)&&desc.dom!==editor)return desc.dom;pending.push(...(desc.children||[]));}
      return null;
    };
    // Exact connector UUID comes from the verified native project context.
    // Mistral may restore this same reference from a draft after a page reload;
    // its presentation must not depend on who created the current DOM node.
    const matchingReferences=(record,current)=>{
      const nodes=[];
      current?.descendants(n=>{if(n.type.name==='slash'&&n.attrs?.slashType==='text-tag'&&n.attrs?.subType==='connection'&&n.attrs.selectedValue===record.id)nodes.push(n);});
      return nodes;
    };
    const quietReference=record=>{
      for(const node of matchingReferences(record,editor.pmViewDesc?.node)){
        const dom=referenceDOM(node);if(!dom)continue;
        if(!record.presentation)record.presentation=new Map();
        if(!record.presentation.has(dom))record.presentation.set(dom,{display:dom.style.getPropertyValue('display'),priority:dom.style.getPropertyPriority('display'),aria:dom.getAttribute('aria-hidden')});
        if(dom.style.getPropertyValue('display')!=='none'||dom.style.getPropertyPriority('display')!=='important')dom.style.setProperty('display','none','important');
        if(dom.getAttribute('aria-hidden')!=='true')dom.setAttribute('aria-hidden','true');
      }
    };
    const record=state.managed.get(editor),refs=[];let otherAtoms=false;
    doc.descendants(n=>{if(n.type.name==='slash'&&n.attrs?.slashType==='text-tag'&&n.attrs?.subType==='connection')refs.push(n);else if(n.isAtom&&!n.isText)otherAtoms=true;});
    const own=record&&matchingReferences(record,doc);
    // Revoke only a reference inserted by this integration in this very editor.
    // ProseMirror's DOM observer processes this single node removal;
    // text, other connectors, attachments, focus and selection are not replaced.
    if(own?.length&&(!valid||record.project!==config.project||record.id!==config.connector_id||(record.active&&!attach))){
      if(!record.active){
        for(const [dom,original]of record.presentation||[]){
          if(!dom.isConnected)continue;
          if(original.display)dom.style.setProperty('display',original.display,original.priority);else dom.style.removeProperty('display');
          if(original.aria===null)dom.removeAttribute('aria-hidden');else dom.setAttribute('aria-hidden',original.aria);
        }
        state.managed.delete(editor);state.status='released';return;
      }
      const doms=own.map(referenceDOM).filter(Boolean);
      if(doms.length===own.length){for(const dom of doms)dom.remove();state.managed.delete(editor);state.attempts.delete(editor);state.status='revoking';return;}
      state.status='waiting_editor';return;
    }
    if(!valid){state.status='inactive';return;}
    if(refs.some(n=>n.attrs.selectedValue===config.connector_id)){
      const current=record&&record.project===config.project&&record.id===config.connector_id?record:{id:config.connector_id,project:config.project,url:location.href,sent:false};
      current.active=attach;state.managed.set(editor,current);quietReference(current);state.status=attach?'attached':'presentation_only';return;
    }
    if(!attach){state.status='presentation_only';return;}
    if(state.composing){state.status='composing';return;}
    const missing=record&&!own?.length&&record.project===config.project&&record.url===location.href;
    const selection=document.getSelection();
    const caret=!state.composing&&selection?.isCollapsed&&editor.contains(selection.anchorNode)&&editor.contains(document.activeElement);
    const repair=missing&&doc.textContent.trim()&&caret;
    // A draft typed before VibeZ was connected, or restored by Mistral, has no
    // reference yet. It is left alone while it is being edited. At a genuine
    // send, with the caret in the editor, the reference joins it: otherwise the
    // message would leave without the project tools. A leftover chip with this
    // project's own label but another connector's UUID (a connector that was
    // replaced) stays as it is and does not hold the current reference back.
    const late=state.sending&&caret&&doc.textContent.trim()&&!otherAtoms&&refs.every(n=>n.attrs.selectedLabel===title);
    if(missing&&!record.sent&&!doc.textContent.trim()){state.status='user_removed';return;}
    if(!late&&(refs.length||otherAtoms||doc.textContent.trim()&&!repair)){state.status='preserved_draft';return;}
    if(repair&&!record.repairAttempted){record.repairAttempted=true;state.attempts.delete(editor);}
    // A failed/unsupported paste is tried only once per editor and conversation.
    if(record?.sent&&!own?.length)state.attempts.delete(editor);
    const key=config.project+':'+config.connector_id+':'+location.href;
    if(state.attempts.get(editor)===key){state.status='unavailable';return;}
    if(typeof DataTransfer!=='function'||typeof ClipboardEvent!=='function'){state.status='unsupported_editor';return;}
    state.attempts.set(editor,key);
    const node=document.createElement('span');node.className='slash-node';
    for(const[k,v]of Object.entries({slashType:'text-tag',subType:'connection',selectedValue:config.connector_id,selectedLabel:config.title}))node.setAttribute(k,v);
    const transfer=new DataTransfer();transfer.setData('text/html',node.outerHTML);transfer.setData('text/plain','');
    // Beside typed text the reference goes to the very start of the draft, where
    // an empty composer has it too: Mistral then sends and shows the message the
    // same way in both orders. The caret returns to where the person left it.
    let back=null;
    const first=editor.firstElementChild;
    if(caret&&doc.textContent.trim()&&doc.firstChild?.type?.name==='paragraph'&&first?.tagName==='P'){
      back={node:selection.anchorNode,offset:selection.anchorOffset,children:first.childNodes.length};
      // Right after the editor gained focus ProseMirror takes a caret at the
      // start for a browser reset and puts its own back, once: ask again then.
      const atStart=()=>selection.isCollapsed&&selection.anchorOffset===0&&(selection.anchorNode===first||selection.anchorNode===first.firstChild);
      for(let n=0;n<2;n++){
        const range=document.createRange();range.setStart(first,0);range.collapse(true);
        selection.removeAllRanges();selection.addRange(range);
        document.dispatchEvent(new Event('selectionchange'));
        if(atStart())break;
      }
    }
    const accepted=!editor.dispatchEvent(new ClipboardEvent('paste',{clipboardData:transfer,bubbles:true,cancelable:true}));
    if(back?.node?.isConnected&&editor.contains(back.node)){
      const offset=back.node===first?back.offset+Math.max(0,first.childNodes.length-back.children):back.offset;
      const limit=back.node.nodeType===3?back.node.nodeValue.length:back.node.childNodes.length;
      if(offset<=limit){
        const range=document.createRange();range.setStart(back.node,offset);range.collapse(true);
        selection.removeAllRanges();selection.addRange(range);
        document.dispatchEvent(new Event('selectionchange'));
      }
    }
    if(accepted){const record={id:config.connector_id,project:config.project,url:location.href,sent:false,active:true};state.managed.set(editor,record);quietReference(record);state.status='attached';}
    else state.status='unavailable';
  };
  state.refresh();
})();
