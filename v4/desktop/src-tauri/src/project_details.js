// Only verified official Work project controls are mirrored. Chat text and
// uploads are not returned, moved, cloned or recreated.
((expected, action, enabled) => {
  const owner = '__vibezProjectSidebar';
  const marker = 'vibez-work-project-v3';
  const text = (node, limit = 240) => (node?.textContent || '').trim().slice(0, limit);
  const visible = node => !!node && node.getClientRects().length > 0;
  const has = (node, names) => !!node && names.every(name => node.classList.contains(name));
  const reply = value => JSON.stringify(value);
  const restore = () => {
    const old = window[owner];
    if (!old || !['vibez-work-project-v1','vibez-work-project-v2',marker].includes(old.marker)) return;
    for (const item of old.styles) {
      if (!item.node?.style) continue;
      if (item.value) item.node.style.setProperty(item.property,item.value,item.priority);
      else item.node.style.removeProperty(item.property);
    }
    for (const [kind,handler] of old.listeners || []) document.removeEventListener(kind,handler,true);
    delete window[owner];
  };
  const unavailable = reason => {restore();return reply({available:false,settings:[],...(reason?{reason}:{})});};
  const route = location.pathname.match(/^\/work\/projects\/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\/?$/i);
  if (location.protocol !== 'https:' || !['chat.mistral.ai','vibe.mistral.ai'].includes(location.hostname) ||
      location.port || !route || route[1].toLowerCase() !== expected) return unavailable('context_changed');
  if (window[owner] && (window[owner].project !== expected || window[owner].marker === 'vibez-work-project-v2')) restore();
  const dialogs = () => [...document.querySelectorAll('[role="dialog"]')].some(visible);
  const styles = pairs => pairs.map(([node,property]) => ({node,property,value:node.style.getPropertyValue(property),priority:node.style.getPropertyPriority(property)}));
  const rememberStyles = (state,pairs) => {
    // Disconnected previous tab contents are no longer part of this document.
    state.styles = state.styles.filter(item => item.node.isConnected !== false);
    for (const [node,property] of pairs) if (!state.styles.some(item => item.node === node && item.property === property))
      state.styles.push(...styles([[node,property]]));
  };
  const controls = sidebar => {
    const sections = [...sidebar.children];
    if (sections.length !== 4 || sections[2].tagName !== 'HR') return null;
    const first = [...sections[0].children];
    if (first.length !== 5 || first.slice(0,4).some(n => n.tagName !== 'P') || first[4].tagName !== 'BUTTON' || first[4].getAttribute('type') !== 'button') return null;
    const context = [...sections[1].children];
    if (context.length !== 2 || context[0].tagName !== 'P') return null;
    const headings = [first[0],first[2],context[0]].map(n => text(n));
    if (headings.some(v => !v) || new Set(headings).size !== 3) return null;
    const inputs = [...context[1].querySelectorAll('input[type="checkbox"][role="checkbox"]')];
    const labels = [...context[1].querySelectorAll('label')].filter(n => text(n,500));
    if (inputs.length !== 1 || labels.length !== 1) return null;
    const checkbox=inputs[0],label=labels[0];
    if (label.control !== checkbox && (!checkbox.id || label.htmlFor !== checkbox.id)) return null;
    if (!text(label,500) || !text(first[4])) return null;
    return {sidebar,first,context,checkbox,label};
  };
  const snapshot = ({first,context,checkbox,label}) => {
    const tone=text(first[1]),instructions=text(first[3],8000),contextLabel=text(label,500);
    const canEdit=!first[4].disabled && first[4].getAttribute('aria-disabled') !== 'true';
    const canContext=!checkbox.disabled && checkbox.getAttribute('aria-disabled') !== 'true';
    return {available:true,tone,instructions,context_label:contextLabel,context_checked:checkbox.checked,can_edit:canEdit,can_context:canContext,settings:[
      {kind:'tone',label:text(first[0]),text:tone},
      {kind:'instructions',label:text(first[2]),text:instructions,...(canEdit?{action:'instructions',action_label:text(first[4])}:{})},
      {kind:'context',label:text(context[0]),text:contextLabel,checked:checkbox.checked,...(canContext?{action:'context'}:{})}
    ]};
  };
  const perform = found => {
    if (dialogs()) return {acted:false,reason:'dialog_open'};
    const {first,checkbox}=found;
    if (action === 'instructions' && !first[4].disabled && first[4].getAttribute('aria-disabled') !== 'true') {first[4].click();return {acted:true,action};}
    if (action === 'context' && typeof enabled === 'boolean' && !checkbox.disabled && checkbox.getAttribute('aria-disabled') !== 'true') {
      if (checkbox.checked === enabled) return {acted:false,action,unchanged:true};
      checkbox.click();return {acted:true,action};
    }
    return {acted:false,reason:'unavailable'};
  };
  // Older official layout: its independent sidebar can stay mounted while the
  // original conversation composer remains visible.
  const oldLayouts=[];
  for (const sidebar of document.querySelectorAll('div.col-start-2')) {
    if (!has(sidebar,['overflow-y-auto','row-start-1','row-end-4'])) continue;
    const grid=sidebar.parentElement;
    if (!has(grid,['grid','grid-cols-[1fr_400px]','grid-rows-[auto_1fr_auto]']) || !visible(grid)) continue;
    if (!visible(sidebar) && window[owner]?.sidebar !== sidebar) continue;
    const found=controls(sidebar);if (found) oldLayouts.push({...found,grid});
  }
  if (oldLayouts.length > 1) return unavailable('layout_changed');
  if (oldLayouts.length === 1) {
    const found=oldLayouts[0],{sidebar,grid}=found;
    if (window[owner] && (window[owner].marker !== 'vibez-work-project-v1' || window[owner].sidebar !== sidebar || window[owner].grid !== grid)) restore();
    if (!window[owner]) window[owner]={marker:'vibez-work-project-v1',project:expected,sidebar,grid,styles:styles([[sidebar,'display'],[grid,'grid-template-columns'],[grid,'column-gap']])};
    sidebar.style.setProperty('display','none','important');grid.style.setProperty('grid-template-columns','minmax(0, 1fr)','important');grid.style.setProperty('column-gap','0','important');
    if (action === 'finish') return reply({...snapshot(found),finished:true});
    return reply(action?perform(found):snapshot(found));
  }
  // Newer official layout: validate both Radix tab/panel identities. Neither
  // the sidebar's Work/Code anchors nor actual chat pages can match this scope.
  const layouts=[];
  for (const settingsTab of document.querySelectorAll('button[role="tab"][id$="-trigger-settings"]')) {
    const tabs=settingsTab.parentElement,root=tabs?.parentElement,grid=root?.parentElement;
    if (!tabs || tabs.tagName !== 'DIV' || tabs.getAttribute('role') !== 'tablist' || !has(tabs,['grid','grid-cols-2']) ||
        !has(root,['w-full','flex','h-full','min-h-0','flex-col']) || !root.closest('main,[role="main"]') ||
        !has(grid,['grid','grid-cols-1','grid-rows-[auto_1fr]']) || !visible(grid)) continue;
    const buttons=[...tabs.children],children=[...root.children];
    if (buttons.length !== 2 || buttons[1] !== settingsTab || children.length !== 3 || children[0] !== tabs) continue;
    const prefix=settingsTab.id.slice(0,-'-trigger-settings'.length);
    if (!prefix || buttons.some((b,i) => b.tagName !== 'BUTTON' || b.getAttribute('type') !== 'button' || b.getAttribute('role') !== 'tab' ||
        b.id !== prefix+'-trigger-'+['conversations','settings'][i] || b.disabled || b.getAttribute('aria-disabled') === 'true')) continue;
    const panels=children.slice(1);
    if (panels.some((p,i) => p.tagName !== 'DIV' || p.getAttribute('role') !== 'tabpanel' || p.id !== prefix+'-content-'+['conversations','settings'][i] ||
        p.getAttribute('aria-labelledby') !== buttons[i].id || buttons[i].getAttribute('aria-controls') !== p.id)) continue;
    const selected=buttons.map(b => b.getAttribute('aria-selected'));
    if (!((selected[0] === 'true' && selected[1] === 'false') || (selected[0] === 'false' && selected[1] === 'true')) ||
        panels.some((p,i) => p.hidden !== (selected[i] !== 'true'))) continue;
    layouts.push({root,grid,tabs,conversationTab:buttons[0],settingsTab,conversations:panels[0],settingsPanel:panels[1],settingsActive:selected[1] === 'true'});
  }
  if (layouts.length !== 1) return unavailable('layout_changed');
  const layout=layouts[0];
  if (window[owner] && (window[owner].marker !== marker || ['root','grid','tabs','conversations','settingsPanel'].some(k => window[owner][k] !== layout[k]))) restore();
  if (!window[owner]) {
    const state=window[owner]={marker,project:expected,...layout,styles:styles([[layout.tabs,'display'],[layout.settingsPanel,'visibility']]),snapshot:null,phase:'idle',touched:false,failed:false,listeners:[]};
    const handler=event => {if(event.isTrusted === true && state.composer?.contains(event.target)) state.touched=true;};
    for (const kind of ['input','change','drop','paste','compositionstart','pointerdown','mousedown']) {document.addEventListener(kind,handler,true);state.listeners.push([kind,handler]);}
  }
  const state=window[owner];
  const parts=() => {
    const children=[...layout.conversations.children];
    if (children.length !== 2 || children.some(n => n.tagName !== 'DIV')) return null;
    const [list,composer]=children;
    if (!has(list,['col-start-1','col-end-1','h-full','flex','flex-col','overflow-auto']) || !has(composer,['col-start-1','col-end-1','mx-auto','w-full'])) return null;
    const editors=[...composer.querySelectorAll('div.ProseMirror[contenteditable="true"]')];
    if (editors.length !== 1) return null;
    return {list,composer,editor:editors[0]};
  };
  const present=found => {
    rememberStyles(state,[[found.list,'display'],[found.composer,'margin-top']]);
    layout.tabs.style.setProperty('display','none','important');found.list.style.setProperty('display','none','important');
    found.composer.style.setProperty('margin-top','auto','important');state.composer=found.composer;
  };
  // This is the exact empty composer chain observed on the official project
  // page. Extra attachment rows, selected files, media, typed/pasted content or
  // focused controls stop a tab visit before React could unmount the editor.
  const safeToVisit=(found,explicit) => {
    const {composer,editor}=found;
    const focused=typeof document.hasFocus === 'function'?document.hasFocus():true;
    if ((!explicit && state.touched) || (focused && composer.contains(document.activeElement)) || (editor.textContent || '').length > 0) return false;
    if (composer.querySelectorAll('input').length || composer.querySelectorAll('img,video,audio').length) return false;
    let node=composer;
    const chain=[['FORM',['w-full','max-w-full','min-w-0']],['DIV',['flex','w-full','max-w-full','min-w-0','flex-col','gap-4']],
      ['DIV',['relative','flex','min-h-0','cursor-text','flex-col']],['DIV',['bg-card','flex','min-h-0','flex-col','overflow-hidden']],
      ['DIV',['flex','min-h-0','flex-1','flex-col','gap-3','overflow-hidden','click-focus-input']],
      ['DIV',['grid','min-h-0','flex-1','grid-rows-[minmax(0,1fr)_0px]']],['DIV',['@container/chat-input-row','min-h-0','min-w-0','flex','items-center','gap-1']]];
    for (const [tag,classes] of chain) {if(node.children.length !== 1) return false;node=node.children[0];if(node.tagName !== tag || !has(node,classes)) return false;}
    if (chain.length && composer.children[0].children[0].children[0].getAttribute('data-chat-input-bar') !== 'true') return false;
    if (node.children.length !== 3 || [...node.children].some(n => n.tagName !== 'DIV')) return false;
    const middle=node.children[1];
    if (!has(middle,['scrollbar-subtle','min-h-0','min-w-0','grow','overflow-y-auto']) || middle.children.length !== 2) return false;
    const [submit,wrapper]=middle.children;
    if (submit.tagName !== 'BUTTON' || submit.getAttribute('type') !== 'submit' || visible(submit) || wrapper.tagName !== 'DIV' ||
        !has(wrapper,['caret-brand-500','break-words']) || wrapper.children.length !== 1 || wrapper.children[0] !== editor || editor.children.length !== 1) return false;
    const paragraph=editor.children[0];
    return paragraph.tagName === 'P' && paragraph.children.length === 1 && paragraph.children[0].tagName === 'BR' && has(paragraph.children[0],['ProseMirror-trailingBreak']);
  };
  const pending=() => reply({available:false,pending:true,settings:[]});
  const transition=tab => {layout.settingsPanel.style.setProperty('visibility','hidden','important');tab.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0,ctrlKey:false}));};
  const beginReturn=() => {state.phase='to_conversations';transition(layout.conversationTab);return pending();};
  const currentSnapshot=extra => ({...(state.snapshot || {available:false,settings:[]}),...extra});
  const settingsControls=() => {
    if (layout.settingsPanel.children.length !== 1) return null;
    const sidebar=layout.settingsPanel.children[0];
    return has(sidebar,['col-start-2','overflow-y-auto','row-start-1','row-end-4'])?controls(sidebar):null;
  };
  if (action === 'finish') {
    if (dialogs()) {restore();return reply({available:false,finished:false,reason:'dialog_open',settings:[]});}
    if (layout.settingsActive) {
      if (state.phase === 'to_conversations') return pending();
      const found=settingsControls();if(!found) return unavailable('layout_changed');
      if (typeof state.expectedContext === 'boolean' && found.checkbox.checked !== state.expectedContext) return pending();
      state.expectedContext=null;state.snapshot=snapshot(found);return beginReturn();
    }
    const found=parts();if(!found) return unavailable('layout_changed');
    if (state.phase === 'to_settings') state.failed=true;
    present(found);state.phase='idle';state.requested=null;return reply(currentSnapshot({finished:true}));
  }
  if (state.phase === 'to_conversations') {
    if (layout.settingsActive) return pending();
    const found=parts();if(!found) return unavailable('layout_changed');
    present(found);state.phase='idle';state.requested=null;
    if (!action) return reply(currentSnapshot({}));
  }
  if (!layout.settingsActive) {
    const found=parts();if(!found) return unavailable('layout_changed');
    present(found);
    if (state.phase === 'to_settings') return pending();
    if (!action && (state.snapshot || state.failed)) return reply(currentSnapshot(state.failed?{reason:'unavailable'}:{}));
    if (action && !['instructions','context'].includes(action)) return reply({acted:false,reason:'unavailable'});
    if (dialogs()) return reply(action?{acted:false,reason:'dialog_open'}:currentSnapshot({reason:'dialog_open'}));
    if (!safeToVisit(found,Boolean(action))) return reply(action?{acted:false,reason:'composer_busy'}:currentSnapshot({reason:'composer_busy'}));
    if (layout.settingsPanel.children.length) return unavailable('layout_changed');
    state.failed=false;state.phase='to_settings';state.requested=action || null;state.requestedEnabled=enabled;
    transition(layout.settingsTab);return pending();
  }
  const found=settingsControls();if(!found) return unavailable('layout_changed');
  state.snapshot=snapshot(found);
  if (state.phase === 'to_settings') {
    if (state.requested !== (action || null) || (action === 'context' && state.requestedEnabled !== enabled)) return unavailable('context_changed');
    if (!action) return beginReturn();
    state.phase='holding';const result=perform(found);if(action === 'context' && (result.acted || result.unchanged)) state.expectedContext=enabled;return reply(result);
  }
  if (state.phase === 'holding') {
    const result=action?perform(found):currentSnapshot({});
    if(action === 'context' && (result.acted || result.unchanged)) state.expectedContext=enabled;
    return reply(result);
  }
  // A newly opened project may already have Settings selected. Snapshot it and
  // return to the native conversation composer without creating an editor.
  if (dialogs()) return unavailable('dialog_open');
  if (action) {state.phase='holding';const result=perform(found);if(action === 'context' && (result.acted || result.unchanged)) state.expectedContext=enabled;return reply(result);}
  return beginReturn();
})(__VIBEZ_PROJECT_ID__, __VIBEZ_PROJECT_ACTION__, __VIBEZ_PROJECT_ENABLED__)
