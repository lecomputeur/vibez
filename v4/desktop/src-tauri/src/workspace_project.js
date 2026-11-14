// An explicit breadcrumb or a verified nested sidebar entry identifies a
// project inside a chat. The exact project URL supplies overview identity;
// other sidebar projects never select its workspace or supply its name.
(() => {
  const visible = e => !!e && e.getClientRects().length > 0;
  const name = e => (e?.innerText || e?.textContent || '').replace(/\s+/g, ' ').trim().slice(0,120);
  // Since 13 Nov 2026 the Work/Code switch inside a project is a tab that
  // links to the project itself; its label ("Work") is not the project's name.
  const modeTab = e => e?.getAttribute?.('role') === 'tab' || !!e?.closest?.('[role="tablist"]');
  const projectURL = value => {
    try {
      const url = new URL(value, location.href);
      if (url.protocol !== 'https:' || !['chat.mistral.ai','vibe.mistral.ai'].includes(url.hostname) || url.port || url.username || url.password) return null;
      const work = url.pathname.match(/^\/work\/projects\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:\/|$)/i);
      if (work) return {url,id:work[1].toLowerCase(),kind:'work',overview:/^\/work\/projects\/[0-9a-f-]{36}\/?$/i.test(url.pathname)};
      const code = url.pathname.match(/^\/code\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:\/((?:draft(?::|%3a)session(?::|%3a))?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}))?\/?$/i);
      return code ? {url,id:'code-'+code[1].toLowerCase(),kind:'code',overview:!code[2]} : null;
    } catch (_) { return null; }
  };
  const conversationURL = value => {
    try{
      const url=new URL(value,location.href);
      if(url.protocol!=='https:'||!['chat.mistral.ai','vibe.mistral.ai'].includes(url.hostname)||url.port||url.username||url.password)return null;
      const match=url.pathname.match(/^\/work\/(?:(?:chat|chats|c)\/)?([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\/?$/i);
      return match?{url,id:match[1].toLowerCase()}:null;
    }catch(_){return null;}
  };
  const draftURL=value=>{
    try{const url=new URL(value,location.href);return url.protocol==='https:'&&['chat.mistral.ai','vibe.mistral.ai'].includes(url.hostname)&&!url.port&&!url.username&&!url.password&&!url.search&&!url.hash&&/^\/work(?:\/new)?\/?$/.test(url.pathname);}catch(_){return false;}
  };
  // The editor/row/send-button relation was verified on the real empty Work
  // composer. No message text is returned; only a local user-submit signal.
  const composer=()=>{
    const editors=[...document.querySelectorAll('div.ProseMirror[contenteditable="true"]')].filter(visible);
    if(editors.length!==1)return null;
    const editor=editors[0];
    // Current Mistral puts the action/send bar outside the text row. A single
    // visible editor and its own enclosing form still define one composer.
    const form=editor.closest('form');
    if(visible(form)){
      const buttons=[...form.querySelectorAll('button[type="submit"]')].filter(button=>visible(button)&&!button.disabled&&button.getAttribute('aria-disabled')!=='true');
      return {editor,row:form,send:buttons.length===1?buttons[0]:null};
    }
    let row=editor;
    for(let depth=0;depth<5&&row;depth++,row=row.parentElement){
      if(!row.classList?.contains('@container/chat-input-row'))continue;
      if(!visible(row))return null;
      const buttons=[...row.querySelectorAll('button[type="submit"]')].filter(button=>visible(button)&&!button.disabled&&button.getAttribute('aria-disabled')!=='true');
      return {editor,row,send:buttons.length===1?buttons[0]:null};
    }
    return null;
  };
  if(!window.__vibezLooseConversations&&typeof crypto!=='undefined'&&typeof crypto.randomUUID==='function'){
    const state=window.__vibezLooseConversations={marker:'vibez-loose-v1',document:crypto.randomUUID(),draft:null,submitted:null,sequence:0,
      reset(){this.draft=null;this.submitted=null;this.sequence++;}};
    const submit=event=>{
      if(event.isTrusted!==true||!draftURL(location.href)||!state.draft)return;
      const current=composer();
      if(!current||!current.send||current.editor!==state.draft.editor||!(current.editor.textContent||'').trim())return;
      state.submitted={document:state.document,nonce:state.draft.nonce,sequence:++state.sequence,at:Date.now(),from:location.href};
    };
    document.addEventListener('click',event=>{
      if(event.isTrusted!==true)return;
      const anchor=event.target.closest?.('a[href]');
      if(anchor){state.reset();return;}
      const button=event.target.closest?.('button[type="submit"]');
      if(button&&button===composer()?.send)submit(event);
    },true);
    document.addEventListener('keydown',event=>{
      if(event.isTrusted!==true||!draftURL(location.href)||event.key!=='Enter'||event.shiftKey||event.ctrlKey||event.metaKey||event.altKey||event.isComposing)return;
      const current=composer();
      if(current&&(event.target===current.editor||current.editor.contains?.(event.target)))submit(event);
    },true);
    window.addEventListener('popstate',()=>state.reset(),true);
  }
  let loose=null;
  const looseState=window.__vibezLooseConversations;
  if(looseState?.marker==='vibez-loose-v1'){
    if(draftURL(location.href)){
      const current=composer();
      if(current){
        if(!looseState.draft){
          const known=new Set();
          for(const anchor of document.querySelectorAll('a[href*="/work/"]')){
            const target=visible(anchor)&&conversationURL(anchor.href);if(target)known.add(target.id);if(known.size>=512)break;
          }
          looseState.draft={nonce:crypto.randomUUID(),editor:current.editor,known:[...known]};looseState.submitted=null;
        }else{looseState.draft.editor=current.editor;}
        loose={document:looseState.document,nonce:looseState.draft.nonce,ready:true,known:looseState.draft.known,submitted:looseState.submitted};
      }
    }else if(conversationURL(location.href)&&looseState.draft){
      // The successful first send remounts the composer. Its captured proof
      // belongs to the previous draft and must survive that normal SPA change.
      loose={document:looseState.document,nonce:looseState.draft.nonce,ready:false,known:looseState.draft.known,submitted:looseState.submitted};
    }else{looseState.reset();}
  }
  // This is only a request to show the local panel. Project identity still
  // comes from the confirmed page URL and visible breadcrumb below.
  if (!window.__vibezProjectClicks) {
    window.__vibezProjectClicks = {sequence:0,last:null};
    document.addEventListener('click',event=>{
      const anchor=event.target.closest?.('a[href]');
      const target=anchor&&projectURL(anchor.href),conversation=anchor&&conversationURL(anchor.href);
      if(target?.overview||conversation)window.__vibezProjectClicks.last={id:conversation?'chat-'+conversation.id:target.id,
        stamp:Date.now()+':'+(++window.__vibezProjectClicks.sequence)};
    },true);
  }
  // A first send on an exact Work project overview changes to /work/<chat>
  // before Mistral renders its breadcrumb/sidebar row. Capture that one trusted
  // submit, not message text, so native recognition keeps the same project.
  let projectStart=null;
  if(typeof crypto!=='undefined'&&typeof crypto.randomUUID==='function'&&typeof window.addEventListener==='function'){
    if(!window.__vibezProjectStart){
      const state=window.__vibezProjectStart={document:crypto.randomUUID(),current:null,submitted:null,pressed:null,sequence:0,
        reset(){this.current=null;this.submitted=null;this.pressed=null;}};
      const submit=event=>{
        const scope=state.current,current=composer(),route=projectURL(location.href);
        if(event.isTrusted!==true||!scope||!route?.overview||route.kind!=='work'||route.id!==scope.project||
            location.href!==scope.from||!current?.send||!(current.editor.textContent||'').trim())return;
        // Mistral remounts the editor when a connector mention is inserted.
        // The trusted current send plus this exact project URL retain the same
        // native-issued document/nonce proof even before the next poll.
        scope.editor=current.editor;
        state.submitted={document:state.document,nonce:scope.nonce,project:scope.project,from:scope.from,sequence:++state.sequence,at:Date.now()};
      };
      // Some Mistral buttons submit/disable/remount on pointer-down, before
      // the later click. Capture only the trusted current project Send press.
      document.addEventListener('pointerdown',event=>{
        if(event.isTrusted!==true||event.button!==0)return;
        const button=event.target.closest?.('button[type="submit"]');
        if(!button||button!==composer()?.send)return;
        const sequence=state.sequence;submit(event);
        if(state.sequence!==sequence)state.pressed={button,at:Date.now(),sequence:state.sequence};
      },true);
      document.addEventListener('click',event=>{
        if(event.isTrusted!==true)return;
        if(event.target.closest?.('a[href]')){state.reset();return;}
        const button=event.target.closest?.('button[type="submit"]');
        if(state.pressed&&button===state.pressed.button&&state.submitted?.sequence===state.pressed.sequence&&Date.now()-state.pressed.at<=1500){state.pressed=null;return;}
        if(button&&button===composer()?.send)submit(event);
        else if(!composer()?.row.contains(event.target))state.reset();
      },true);
      document.addEventListener('keydown',event=>{
        if(event.isTrusted!==true)return;
        if(event.key==='Escape'||event.altKey||event.metaKey){state.reset();return;}
        if(event.key!=='Enter'||event.shiftKey||event.ctrlKey||event.isComposing)return;
        const current=composer();
        if(current&&(event.target===current.editor||current.editor.contains?.(event.target)))submit(event);
      },true);
      window.addEventListener('popstate',()=>state.reset(),true);
    }
    const state=window.__vibezProjectStart,route=projectURL(location.href),current=composer();
    if(route?.kind==='work'&&route.overview&&current){
      if(!state.current||state.current.from!==location.href){
        const known=new Set();
        for(const link of document.querySelectorAll('a[href*="/work/"]')){
          const chat=visible(link)&&conversationURL(link.href);if(chat)known.add(chat.id);if(known.size>=512)break;
        }
        state.current={project:route.id,from:location.href,nonce:crypto.randomUUID(),editor:current.editor,known:[...known]};state.submitted=null;
      }else{state.current.editor=current.editor;}
      projectStart={document:state.document,nonce:state.current.nonce,project:state.current.project,from:state.current.from,ready:true,known:state.current.known,submitted:state.submitted};
    }else if(conversationURL(location.href)&&state.current&&state.submitted){
      projectStart={document:state.document,nonce:state.current.nonce,project:state.current.project,from:state.current.from,ready:false,submitted:state.submitted};
    }else{state.reset();}
  }
  const breadcrumbs = new Map();
  for (const anchor of document.querySelectorAll('main header a[href],main nav[aria-label] a[href],main [aria-label*="readcrumb"] a[href],[role="main"] header a[href],a[aria-current="page"][href*="/work/projects/"],a[aria-current="true"][href*="/work/projects/"],a[aria-current="page"][href*="/code/"],a[aria-current="true"][href*="/code/"]')) {
    const project = visible(anchor) && !modeTab(anchor) && projectURL(anchor.href);
    if (project) breadcrumbs.set(project.id,{href:anchor.href,name:name(anchor)});
  }
  const current = projectURL(location.href);
  const conversation=conversationURL(location.href);
  const projectAnchors=[...document.querySelectorAll('a[href*="/work/projects/"],a[href*="/code/"]')];
  const sidebarProjects=[];
  const sidebarOverview=anchor=>{
    const project=projectURL(anchor.href),item=anchor.parentElement;
    return visible(anchor)&&project?.kind==='work'&&project.overview&&anchor.getAttribute?.('data-sidebar')==='menu-button'&&
      item?.tagName==='LI'&&item.getAttribute?.('data-sidebar')==='menu-item'&&item.classList?.contains('group/menu-item')&&
      item.closest?.('ul[data-sidebar="menu"]')?project:null;
  };
  // The official project row owns exactly one menu button and one collapsible
  // subtree. Its nested conversations remain available after the duplicate
  // central list is hidden. Nearby menu entries cannot establish ownership.
  for(const anchor of projectAnchors){
    const project=sidebarOverview(anchor),item=anchor.parentElement;
    if(!project)continue;
    const children=[...item.children];
    if(children.length!==2||children[0]!==anchor||children[1].tagName!=='DIV'||
        !children[1].classList?.contains('group-data-[collapsible=icon]:hidden'))continue;
    const nested=[...children[1].querySelectorAll('a[href]')];
    if(nested.some(link=>projectURL(link.href)))continue;
    const chats=nested.filter(link=>{
      // Conversation rows reuse menu-item/menu-button, rather than the
      // menu-sub-item names. Their exact nested-list chain proves ownership.
      const row=link.parentElement,list=row?.parentElement,sub=list?.parentElement,inner=sub?.parentElement;
      const cells=row?[...row.children]:[];
      return visible(link)&&link.getAttribute?.('data-sidebar')==='menu-button'&&row?.tagName==='LI'&&
        row.getAttribute?.('data-sidebar')==='menu-item'&&row.classList?.contains('group/menu-item')&&
        cells[0]===link&&(cells.length===1||(cells.length===2&&cells[1].tagName==='DIV'))&&
        list?.tagName==='UL'&&list.getAttribute?.('data-sidebar')==='menu'&&
        sub?.tagName==='UL'&&sub.getAttribute?.('data-sidebar')==='menu-sub'&&
        inner?.tagName==='DIV'&&inner.parentElement===children[1];
    })
      .map(link=>({anchor:link,chat:conversationURL(link.href)})).filter(entry=>entry.chat).slice(0,64);
    sidebarProjects.push({anchor,project,chats});
  }
  if(conversation){
    for(const group of sidebarProjects){
      if(group.chats.some(entry=>entry.chat.id===conversation.id)){
        breadcrumbs.set(group.project.id,{href:group.anchor.href,name:name(group.anchor)});
      }
    }
  }
  const links = [...breadcrumbs.values()];
  let conversationName='';
  if(conversation){
    for(const anchor of document.querySelectorAll('a[href*="/work/"]')){
      if(visible(anchor)&&!anchor.closest?.('main,[role="main"]')&&conversationURL(anchor.href)?.id===conversation.id){conversationName=name(anchor);if(conversationName)break;}
    }
  }
  let currentName = '';
  if (current) {
    // Match the UUID first: never substitute the first project in the sidebar.
    for (const anchor of projectAnchors) {
      const target = projectURL(anchor.href);
      if (visible(anchor) && !modeTab(anchor) && target?.id === current.id && target.overview) {
        currentName = name(anchor);
        if (currentName) break;
      }
    }
    // A generic heading can still belong to the previous SPA page. Only an
    // exact project-URL link supplies its name; native code caches it by ID.
  }
  const chats = new Set();
  // Only the current overview and its verified sidebar subtree may identify
  // its chats. A broad main element can also wrap the whole sidebar, so those
  // links must be excluded before reading the central overview list.
  if (current?.kind === 'work' && current.overview) {
    for (const anchor of document.querySelectorAll('main a[href],[role="main"] a[href]')) {
      if (!visible(anchor)||anchor.closest?.('ul[data-sidebar="menu"]')) continue;
      try {
        const url = new URL(anchor.href,location.href);
        if (url.protocol!=='https:' || !['chat.mistral.ai','vibe.mistral.ai'].includes(url.hostname) || url.port || url.username || url.password) continue;
        const match=url.pathname.match(/^\/work\/(?:(chat|chats|c)\/)?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/?$/i);
        if (!match) continue;
        chats.add(url.origin+'/work/'+(match[1]?match[1].toLowerCase()+'/':'')+match[2].toLowerCase());
        if (chats.size>=64) break;
      } catch (_) {}
    }
    const groups=sidebarProjects.filter(group=>group.project.id===current.id);
    if(groups.length===1){
      for(const entry of groups[0].chats){
        if(chats.size>=64)break;
        chats.add(entry.chat.url.origin+entry.chat.url.pathname.replace(/\/$/,'').toLowerCase());
      }
    }
  }
  // Remember only an explicit menu action on a verified project chat. A later
  // home redirect may request a return to that project's existing overview;
  // it never grants a project folder to the home composer or an unrelated chat.
  let projectReturn=null;
  if(typeof window.addEventListener==='function'&&!window.__vibezProjectReturn){
    const state=window.__vibezProjectReturn={current:null,pending:null,reset(){this.current=null;this.pending=null;this.missing=null;}};
    document.addEventListener('click',event=>{
      if(event.isTrusted!==true)return;
      const target=event.target;
      const button=target.closest?.('button,[role="button"]'),context=state.current;
      // The official message action is a direct button, not a menu item. Its
      // accessible name is "Delete question" even in the Dutch Work interface
      // (verified live). Only that action in a visible message region can arm
      // this return. Deleting a later turn stays in the existing conversation;
      // only Mistral's subsequent empty home composer requests a project return.
      const messageRegion=button?.closest?.('[role="region"]');
      const deleteQuestion=button&&[button.getAttribute('aria-label'),button.getAttribute('title'),name(button)].some(label=>label==='Delete question');
      if(context?.active&&visible(button)&&deleteQuestion&&messageRegion&&button.closest?.('main,[role="main"]')&&
          !button.closest?.('[data-sidebar],aside,nav,header,form,[role="dialog"],[role="alertdialog"],[role="menu"]')&&!composer()?.row.contains(button)){
        state.pending={project:context.project,from:location.href,chat:context.active,at:Date.now(),chosen:true,confirmed:true};return;
      }
      if(button&&['menu','true'].includes(button.getAttribute('aria-haspopup'))){
        const group=state.groups?.find(group=>group.chats.some(entry=>(entry.anchor.contains?.(button)||entry.anchor.parentElement?.children[1]?.contains?.(button))));
        const row=group?.chats.find(entry=>(entry.anchor.contains?.(button)||entry.anchor.parentElement?.children[1]?.contains?.(button)));
        const inMain=button.closest?.('main,[role="main"]');
        const header=context?.active&&button.getAttribute('aria-haspopup')==='menu'&&inMain&&!button.closest?.('[data-sidebar],aside,nav')&&!composer()?.row.contains(button);
        const chat=row?.chat.id||(header?context.active:null);
        if(chat){state.pending={project:row?group.project.id:context.project,from:location.href,chat,at:Date.now()};return;}
      }
      const pending=state.pending;
      const item=target.closest?.('[role="menuitem"]');
      if(pending&&item&&target.closest?.('[role="menu"]')){
        pending.chosen=true;
        if(item.getAttribute('data-variant')==='destructive'||item.classList?.contains('text-destructive'))pending.confirmed=true;
        return;
      }
      if(target.closest?.('a[href]')){state.reset();return;}
      if(pending?.chosen&&button&&target.closest?.('[role="dialog"],[role="alertdialog"]'))pending.confirmed=true;
      // Menu choices and their confirmation dialog may complete asynchronously.
      // Any other explicit action abandons the return, including a new-chat button.
      if(!target.closest?.('[role="menu"],[role="dialog"],[role="alertdialog"]'))state.pending=null;
    },true);
    document.addEventListener('contextmenu',event=>{
      if(event.isTrusted!==true)return;
      const anchor=event.target.closest?.('a[href]');
      const group=state.groups?.find(group=>group.chats.some(entry=>entry.anchor===anchor));
      const entry=group?.chats.find(entry=>entry.anchor===anchor);
      if(entry)state.pending={project:group.project.id,from:location.href,chat:entry.chat.id,at:Date.now()};
    },true);
    document.addEventListener('keydown',event=>{
      if(event.isTrusted!==true)return;
      if(event.altKey||event.ctrlKey||event.metaKey||event.key==='Escape')state.reset();
    },true);
    window.addEventListener('popstate',()=>{const p=state.pending;if(!p?.chosen||!(draftURL(location.href)||location.href===p.from))state.reset();},true);
  }
  const returnState=window.__vibezProjectReturn;
  if(returnState){
    returnState.groups=sidebarProjects;
    let owner=null;
    if(current?.kind==='work'&&current.overview)owner=current.id;
    else if(conversation&&breadcrumbs.size===1)owner=[...breadcrumbs.keys()][0];
    const owners=sidebarProjects.filter(group=>group.project.id===owner);
    if(owner&&owners.length===1){
      if(returnState.current&&returnState.current.from!==location.href)returnState.pending=null;
      returnState.current={project:owner,from:location.href,active:conversation?.id||null,rows:owners[0].chats};
    }else if(draftURL(location.href)){
      const pending=returnState.pending,editor=composer()?.editor;
      if(pending&&Date.now()-pending.at<=30_000&&pending.at<=Date.now()+1000){
        // Mistral removes the collapsible conversation subtree when its final
        // chat disappears. The verified project row itself still exists. This
        // is return-navigation evidence only; native code separately requires
        // a recently confirmed project/chat pair captured before deletion.
        const present=projectAnchors.filter(anchor=>sidebarOverview(anchor)?.id===pending.project).length===1;
        const stillListed=sidebarProjects.some(group=>group.chats.some(entry=>entry.chat.id===pending.chat));
        const movedElsewhere=sidebarProjects.some(group=>group.project.id!==pending.project&&group.chats.some(entry=>entry.chat.id===pending.chat));
        if(present&&!movedElsewhere&&(!stillListed||pending.chosen)&&editor&&!(editor.textContent||'').trim())projectReturn={...pending,reason:'removed_project_chat'};
      }else{returnState.reset();}
    }else{
      const p=returnState.pending;
      // Removing the active sidebar row removes its ownership breadcrumb before
      // Mistral redirects. Keep only this short, already observed user action.
      if(!p||location.href!==p.from||Date.now()-p.at>30_000)returnState.reset();
    }
    const pending=returnState.pending;
    // Deleting through the opened chat may leave both its URL and its sidebar
    // row behind. Recognize the stable recovery pane by its structure, after
    // a trusted menu choice and confirmation; never match translated wording.
    if(!projectReturn&&pending?.chosen&&conversation?.id===pending.chat&&location.href===pending.from&&
        Date.now()-pending.at<=30_000&&pending.at<=Date.now()+1000&&breadcrumbs.size<=1&&(!breadcrumbs.size||breadcrumbs.has(pending.project))&&!composer()){
      const candidates=[];
      for(const button of document.querySelectorAll('main button,[role="main"] button')){
        if(!visible(button)||button.closest('[data-sidebar],aside,nav,header,form,[role="dialog"],[role="alertdialog"],[role="menu"]'))continue;
        let container=button.parentElement;
        for(let depth=0;depth<4&&container;depth++,container=container.parentElement){
          const text=(container.innerText||container.textContent||'').replace(/\s+/g,' ').trim();
          const controls=[...container.querySelectorAll('button,a[href]')].filter(visible);
          if(text.length>500)break;
          if(text.length>name(button).length&&controls.length===1&&controls[0]===button&&
              !container.querySelector('[role="progressbar"],[aria-busy="true"],.animate-spin,[contenteditable="true"],textarea')){
            candidates.push(button);break;
          }
        }
      }
      const button=candidates.length===1?candidates[0]:null;
      if(button){
        if(returnState.missing?.button===button&&Date.now()-returnState.missing.at>=500)projectReturn={project:pending.project,from:pending.from,chat:pending.chat,at:pending.at,reason:'missing_project_chat'};
        else if(returnState.missing?.button!==button)returnState.missing={button,at:Date.now()};
      }else{returnState.missing=null;}
    }else{returnState.missing=null;}
  }
  const contextProject=current?.kind==='work'?current.id:breadcrumbs.size===1?[...breadcrumbs.keys()][0]:null;
  const contextGroups=sidebarProjects.filter(group=>group.project.id===contextProject);
  const projectChats=contextGroups.length===1?contextGroups[0].chats.map(entry=>entry.chat.url.origin+entry.chat.url.pathname.replace(/\/$/,'').toLowerCase()):[];
  const navigationTrace={armed:Boolean(returnState?.pending),chosen:Boolean(returnState?.pending?.chosen),confirmed:Boolean(returnState?.pending?.confirmed),home:draftURL(location.href),owner_known:contextGroups.length===1,return_ready:Boolean(projectReturn)};
  return JSON.stringify({links:links.slice(0,6),ambiguous:breadcrumbs.size>1,name:currentName,conversation_name:conversationName,loose,project_start:projectStart,project_return:projectReturn,project_chats:projectChats,sidebar_return_projects:sidebarProjects.slice(0,64).map(group=>({id:group.project.id,name:name(group.anchor),url:group.project.url.origin+'/work/projects/'+group.project.id,chats:group.chats.map(entry=>entry.chat.url.origin+entry.chat.url.pathname.replace(/\/$/,'').toLowerCase())})),navigation_trace:navigationTrace,chats:[...chats],clicked:window.__vibezProjectClicks.last});
})()
