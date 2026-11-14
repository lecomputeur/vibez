(function workChatAuthorization(input) {
  const { url, job, project, connectorId, connectorName, marker, stage, token } = input || {};
  const uuid = '[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}';
  const idPattern = new RegExp('^' + uuid + '$');
  const projectPattern = new RegExp('^(?:chat-)?' + uuid + '$');
  const connector = /^((?:vibezwork)[a-f0-9]{16})_[a-z0-9]{4,12}$/.exec(connectorName || '');
  if (!/^[a-f0-9]{32}$/.test(job || '') || !projectPattern.test(project || '') ||
      !idPattern.test(connectorId || '') || !connector || typeof marker !== 'string' ||
      !/^\[VibeZ-work:[a-f0-9]{32}:/.test(marker) ||
      !marker.endsWith(':' + project + ':' + connector[1] + ']') ||
      marker.length !== '[VibeZ-work:'.length + 32 + 1 + project.length + 1 + connector[1].length + 1) {
    return { state: 'invalid-input' };
  }
  if (typeof url !== 'string' || location.href !== url || location.protocol !== 'https:' ||
      !['chat.mistral.ai', 'vibe.mistral.ai'].includes(location.hostname) ||
      location.port || location.username || location.password || window.top !== window) {
    return { state: 'wrong-scope' };
  }
  const chatPath = new RegExp('^/work/(?:(?:chat|chats|c)/)?' + uuid + '/?$');
  const projectPath = new RegExp('^/work/projects/(' + uuid + ')(?:/(?:chat|chats|c)/' + uuid + ')?/?$');
  const projectRoute = projectPath.exec(location.pathname);
  const homeDraft = /^\/work(?:\/new)?\/?$/.test(location.pathname) &&
    project.startsWith('chat-') && !location.search && !location.hash;
  if (!chatPath.test(location.pathname) && projectRoute?.[1] !== project && !homeDraft) {
    return { state: 'wrong-scope' };
  }

  const title = connector[1];
  const draftKey = 'vibez-work-draft';
  const visible = node => !!node?.getClientRects().length;
  const controls = (root, selector) => [...root.querySelectorAll(selector)].filter(visible);
  const one = (nodes, predicate = () => true) => {
    const matches = nodes.filter(predicate);
    return matches.length === 1 ? matches[0] : null;
  };
  const isLabel = (node, pattern) => pattern.test((node.getAttribute('aria-label') || '').trim()) ||
    pattern.test((node.innerText || '').trim());
  const enabled = button => button && !button.disabled && button.getAttribute('aria-disabled') !== 'true';
  // In a wide window Mistral opens the Connectors list from the pointer moving
  // over and pressing the item; a bare click() leaves it closed (13 Nov 2026).
  // Send the events a mouse would send, then the click, so both layouts open it.
  const press = node => {
    if (typeof node.dispatchEvent !== 'function' || typeof MouseEvent !== 'function') return node.click();
    const box = node.getBoundingClientRect?.() || { x: 0, y: 0, width: 0, height: 0 };
    const base = { bubbles: true, cancelable: true, composed: true, view: window, button: 0,
      clientX: box.x + box.width / 2, clientY: box.y + box.height / 2, pointerId: 1, pointerType: 'mouse', isPrimary: true };
    const fire = (type, buttons) => node.dispatchEvent(new (type.startsWith('pointer') && typeof PointerEvent === 'function' ? PointerEvent : MouseEvent)(type, { ...base, buttons }));
    for (const type of ['pointerover', 'pointerenter', 'mouseover', 'mouseenter', 'pointermove', 'mousemove', 'pointerdown', 'mousedown']) fire(type, 1);
    for (const type of ['pointerup', 'mouseup']) fire(type, 0);
    node.click();
  };
  const connectLabel = /^(Verbinden|Connect|Connecter|Se connecter|Conectar|Connetti|Collega|Połącz|Підключити|اتصال)$/i;
  const popups = '[role="dialog"],[role="alertdialog"],[role="menu"]';
  const dialogs = controls(document, popups);
  const buttons = [...new Set(dialogs.flatMap(dialog => controls(dialog, 'button')))];
  // Labels in every Mistral site language VibeZ can select (en, nl, fr, de,
  // es, it, pt, pl, uk, ar).
  const connectorMenu = one(buttons, button => isLabel(button,
    /^(Connectors|Connecteurs|Konnektoren|Conectores|Connettori|Konektory|Łączniki|Конектори|الموصلات)$/i));
  // Most accounts get the picker as a dialog with button rows. Newer variants
  // render it in a portal beside <main> without those roles, and the row's
  // visible text can be empty (its label hidden on screen). The row is
  // therefore matched by its text content as well, in any visible overlay.
  const rowText = node => (node.textContent || '').replace(/\s+/g, ' ').trim();
  const mainElement = document.querySelector?.('main') || null;
  const overlayRoots = [...(document.body?.children || [])].filter(node => node !== mainElement &&
    !/^(SCRIPT|STYLE|LINK|IFRAME|NEXT-ROUTE-ANNOUNCER)$/.test(node.tagName || '') && visible(node));
  const rowSelector = 'button,[role="option"],[role="menuitem"],[role="menuitemradio"],[role="menuitemcheckbox"],[cmdk-item],li';
  const innermost = nodes => nodes.filter(node => !nodes.some(other => other !== node && node.contains(other)));
  const overlayRows = innermost([...new Set(overlayRoots.flatMap(root => controls(root, rowSelector)))]
    .filter(node => rowText(node) === title && !node.closest('form')));
  const pickerRow = one(buttons, button => (button.innerText || '').trim() === title || rowText(button) === title) ||
    one(overlayRows);
  const searchLabel = /^(zoek\w*|search\w*|recherch\w*|such\w*|busca\w*|cerca\w*|pesquis\w*|szukaj|wyszukaj|filter\w*|filtr\w*|пошук|шукати|بحث)(?:\s+\w+)?(?:\s*[.…]*)?$/i;
  const fieldLabel = field => (field.getAttribute('aria-label') || field.placeholder || '').trim();
  const searches = [...new Set(dialogs.flatMap(dialog => controls(dialog, 'input')))];
  const overlayInputs = [...new Set(overlayRoots.flatMap(root => controls(root, 'input,[cmdk-input],[role="combobox"]')))]
    .filter(field => !field.closest('form'));
  const pickerSearch = one(searches, field => searchLabel.test(fieldLabel(field))) ||
    one(overlayInputs, field => field.type === 'search' || field.hasAttribute?.('cmdk-input') || searchLabel.test(fieldLabel(field)));
  const passwords = controls(document, 'input[type="password"]');
  const password = one(passwords, field => field.id === 'header:authorization');
  const auth = password?.closest('[role="dialog"],[role="alertdialog"]');
  const authText = auth?.innerText || '';
  const authDialog = passwords.length === 1 && visible(auth) && authText.includes(marker) &&
    authText.includes(connectorName) && authText.includes(title) &&
    one(controls(auth, 'button'), button => isLabel(button, /^Bearer$/)) ? auth : null;
  // Diagnostic name of the first failed dialog check. Never page text or values.
  const authReason = authDialog ? '' : passwords.length !== 1 ? 'password-count' : !password ? 'password-field' :
    !visible(auth) ? 'auth-dialog' : !authText.includes(marker) ? 'auth-marker' :
    !authText.includes(connectorName) ? 'auth-name' : !authText.includes(title) ? 'auth-title' : 'auth-bearer';
  // The connector overview VibeZ confirmed (see 'authorize') counts as known.
  const allKnown = (...known) => dialogs.every(dialog => [...known, state?.overview].some(node =>
    node && (dialog === node || dialog.contains(node) || node.contains(dialog))));
  const menu = connectorMenu?.closest(popups);
  const anchor = pickerRow || pickerSearch;
  const picker = anchor ? (anchor.closest(popups) || overlayRoots.find(root => root.contains(anchor)) || null) : null;

  let state = window.__vibezWorkChatAuthorization;
  const matchesJob = candidate => candidate?.job === job && candidate.url === url &&
    candidate.project === project && candidate.connectorId === connectorId &&
    candidate.connectorName === connectorName && candidate.marker === marker;
  if (stage === 'cancel') {
    if (!matchesJob(state)) return { state: 'wrong-scope' };
    if (state.password?.isConnected && state.password.value) {
      if (!authDialog || password !== state.password ||
          !/^[A-Za-z0-9_-]{50,85}$/.test(token || '') || password.value !== token ||
          !allKnown(state.menu, menu, state.picker, picker, authDialog)) {
        return { state: 'unexpected-dialog' };
      }
      password.focus();
      if (document.activeElement !== password) return { state: 'wait' };
      password.select();
      document.execCommand('delete');
      password.blur();
      if (password.value) return { state: 'wait' };
    }
    delete window.__vibezWorkChatAuthorization;
    // VibeZ reloads this page after 'cancel'. Keep the person's typed text in
    // this tab's session storage, so it is put back in the new document.
    const draftEditor = one(controls(document, 'div.ProseMirror[contenteditable="true"]'));
    const draftNode = draftEditor?.pmViewDesc?.node;
    const draftText = typeof draftNode?.textBetween === 'function'
      ? draftNode.textBetween(0, draftNode.content.size, '\n', '') : '';
    try {
      if (draftText.trim()) sessionStorage.setItem(draftKey, JSON.stringify({ job, url, text: draftText, at: Date.now() }));
      else sessionStorage.removeItem(draftKey);
    } catch (_) { /* storage blocked: the draft cannot be kept */ }
    return { state: 'cancelled' };
  }

  const editor = one(controls(document, 'div.ProseMirror[contenteditable="true"]'));
  const doc = editor?.pmViewDesc?.node;
  const form = editor?.closest('form');
  if (!form || typeof doc?.descendants !== 'function') return { state: 'wait', reason: 'no-editor' };
  // Put back the text kept before VibeZ reloaded this page (see 'cancel').
  let kept = null;
  try { kept = JSON.parse(sessionStorage.getItem(draftKey) || 'null'); } catch (_) { kept = null; }
  if (kept) {
    try { sessionStorage.removeItem(draftKey); } catch (_) { /* ignore */ }
    const fresh = kept.job === job && kept.url === url && typeof kept.text === 'string' &&
      Date.now() - Number(kept.at || 0) < 180000;
    if (fresh && !String(doc.textContent || '').trim() && typeof document.execCommand === 'function') {
      editor.focus?.();
      kept.text.split('\n').forEach((line, index) => {
        if (index) document.execCommand('insertParagraph');
        if (line) document.execCommand('insertText', false, line);
      });
      return { state: 'wait', reason: 'restoring-draft' };
    }
  }
  let exact = 0;
  let other = false;
  let otherAtoms = false;
  const oldNodes = [];
  doc.descendants(node => {
    if (node.isText) return;
    if (!node.isInline || !node.isAtom) return;
    // A newer picker may store the connector by name or another handle rather
    // than its UUID; only a chip for a *different* connector UUID (a replaced
    // connector) is a stale reference.
    const chipValue = String(node.attrs?.selectedValue || '');
    if (node.type.name === 'slash' && node.attrs?.slashType === 'text-tag' &&
        node.attrs.subType === 'connection' && node.attrs.selectedLabel === title &&
        (chipValue === connectorId || chipValue === connectorName || !idPattern.test(chipValue))) exact++;
    // Only another VibeZ folder connector (for example from the previous
    // folder, or the connector replaced after a restart) would make Mistral
    // use the wrong folder. Text the user typed, files and other connectors
    // stay as they are; the reference is added.
    else if (node.type.name === 'slash' && node.attrs?.subType === 'connection' &&
        /^vibezwork[a-f0-9]{16}$/.test(node.attrs.selectedLabel || '')) {
      other = true;
      oldNodes.push(node);
    } else otherAtoms = true;
  });
  // The DOM element ProseMirror renders for a document node, through its view
  // descriptors; the label itself may be hidden on screen.
  const nodeDOM = node => {
    const pending = [editor.pmViewDesc];
    while (pending.length) {
      const desc = pending.pop();
      if (!desc) continue;
      if (desc.node === node && desc.dom?.isConnected && desc.dom !== editor && editor.contains(desc.dom)) return desc.dom;
      pending.push(...(desc.children || []));
    }
    return null;
  };
  // The same connector referenced twice (for example after a page reload) is
  // harmless: Mistral uses it once. Only another VibeZ folder reference blocks.
  const hasDraft = other;
  const same = candidate => matchesJob(candidate) && candidate.editor === editor && candidate.form === form;

  if (stage === 'open-menu') {
    if (same(state) && state.step === 'menu') return { state: 'advanced' };
    // The composer already references exactly this connector and nothing else.
    if (exact >= 1 && !other && !dialogs.length) return { state: 'selected' };
    if (hasDraft) {
      // Remove VibeZ's own earlier folder reference. Its chip is hidden on
      // screen, so a DOM selection cannot reach it; removing the rendered
      // element is what ProseMirror's observer turns into a deletion (the
      // same way the composer integration revokes a reference). A few tries.
      const tries = window.__vibezWorkOldReference = (window.__vibezWorkOldReference || 0) + 1;
      if (tries <= 4) {
        const doms = oldNodes.map(nodeDOM).filter(Boolean);
        if (doms.length === oldNodes.length) {
          for (const dom of doms) dom.remove();
          return { state: 'wait', reason: 'removing-old-reference' };
        }
      }
      // Still there: when the draft holds nothing but stale references and
      // their separator whitespace, clear it as a person does with Select
      // All and Backspace; the new reference is added afterwards.
      if (tries <= 6 && !otherAtoms && !String(doc.textContent || '').trim() && typeof document.execCommand === 'function') {
        editor.focus?.();
        document.execCommand('selectAll');
        document.execCommand('delete');
        return { state: 'wait', reason: 'clearing-stale-draft' };
      }
      return { state: 'blocked-draft', reason: 'other-folder-reference' };
    }
    delete window.__vibezWorkOldReference;
    if (dialogs.length) {
      // Work's own + menu or connector picker left open by an earlier attempt:
      // close them first. Anything else is still unexpected.
      const ownMenus = !passwords.length && dialogs.every(dialog => dialog === menu || dialog === picker ||
        (menu && dialog.contains(menu)) || (picker && dialog.contains(picker)));
      if (!ownMenus) {
        // Something Mistral opened by itself (often right after a reload, such as
        // a notice). Never touch a key field; otherwise close it with Escape a
        // few times before giving up, and name it in the diagnostics.
        const tries = window.__vibezWorkForeignDialog = (window.__vibezWorkForeignDialog || 0) + 1;
        if (!passwords.length && tries <= 4) {
          (document.activeElement || document.body)?.dispatchEvent?.(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
          return { state: 'wait', reason: 'closing-foreign-dialog' };
        }
        const names = dialogs.filter(dialog => dialog !== menu && dialog !== picker)
          .map(dialog => (dialog.getAttribute?.('role') || '') + ' ' + (dialog.getAttribute?.('aria-label') ||
            dialog.querySelector?.('h1,h2,h3,[role=heading]')?.innerText || ''))
          .join(' ').toLowerCase().match(/[a-z]{2,20}/g) || [];
        return { state: 'unexpected-dialog', reason: 'open-dialog', detail: names.slice(0, 8) };
      }
      const plus = one(controls(form, 'button[data-coachmark-target="chat-input-settings"][aria-haspopup="dialog"]'));
      if (plus && plus.getAttribute('aria-expanded') === 'true') plus.click();
      else (document.activeElement || document.body).dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
      return { state: 'wait', reason: 'closing-old-menu' };
    }
    delete window.__vibezWorkForeignDialog;
    const plus = one(controls(form, 'button[data-coachmark-target="chat-input-settings"][aria-haspopup="dialog"]'));
    if (!enabled(plus) || plus.getAttribute('aria-expanded') === 'true') return { state: 'wait' };
    state = { job, url, project, connectorId, connectorName, marker, editor, form, step: 'menu' };
    window.__vibezWorkChatAuthorization = state;
    plus.click();
    return { state: 'advanced' };
  }

  if (!same(state)) return { state: 'wrong-scope', reason: matchesJob(state) ? 'editor-replaced' : 'no-job' };
  if (hasDraft) {
    // The row chosen moments ago inserted another VibeZ connector for this
    // folder: the loaded page's picker still listed the connector this attempt
    // replaced (for example after a restart). Report a stale picker, so the
    // page is reloaded and the choice repeated; the old chip is removed then.
    if (!exact && ['chosen', 'token'].includes(state.step)) return { state: 'wait', reason: 'stale-row-reference' };
    return { state: 'blocked-draft', reason: 'draft' };
  }
  if (['chosen', 'token', 'submitted', 'reselected'].includes(state.step) &&
      exact >= 1 && !dialogs.length) return { state: 'selected' };
  // Work can select an already authorized connector without a Bearer dialog
  // and leave its own menus open. Close only those known menus, then report.
  if (['chosen', 'token', 'submitted', 'reselected'].includes(state.step) &&
      exact >= 1 && !passwords.length) {
    if (!allKnown(state.menu, menu, state.picker, picker)) return { state: 'unexpected-dialog', reason: 'other-dialog' };
    const plus = one(controls(form, 'button[data-coachmark-target="chat-input-settings"][aria-haspopup="dialog"]'));
    state.closing = (state.closing || 0) + 1;
    if (state.closing === 1 && enabled(plus) && plus.getAttribute('aria-expanded') === 'true') plus.click();
    else if (state.closing <= 4) (document.activeElement || document.body).dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
    return { state: 'wait', reason: 'closing-menu' };
  }

  if (stage === 'open-picker' && state.step === 'menu') {
    if (!menu) return { state: 'wait', reason: dialogs.length ? 'menu-unrecognized' : 'no-menu' };
    if (!allKnown(menu)) return { state: 'unexpected-dialog', reason: 'other-dialog' };
    if (!enabled(connectorMenu)) return { state: 'wait', reason: 'menu-disabled' };
    state.menu = menu;
    state.step = 'picker';
    press(connectorMenu);
    return { state: 'advanced' };
  }

  if (stage === 'choose' && state.step === 'picker') {
    if (!picker) {
      // Diagnostics only: the shapes of the overlays on screen, never their text.
      const shapes = overlayRoots.slice(0, 6).map(root => (root.tagName || '').toLowerCase() +
        (root.getAttribute?.('role') ? '[' + root.getAttribute('role') + ']' : ''));
      return { state: 'wait', reason: dialogs.length ? 'no-picker' : 'no-dialog', detail: shapes };
    }
    if (!allKnown(state.menu, menu, picker) || passwords.length) {
      return { state: 'unexpected-dialog', reason: passwords.length ? 'auth-before-choose' : 'other-dialog' };
    }
    state.picker = picker;
    if (enabled(pickerRow)) {
      state.step = 'chosen';
      pickerRow.click();
      return { state: 'advanced' };
    }
    if (pickerSearch && !pickerSearch.disabled && !pickerSearch.readOnly && !pickerSearch.value) {
      pickerSearch.focus();
      document.execCommand('insertText', false, title);
    }
    return { state: 'wait', reason: pickerRow ? 'row-disabled' : 'no-row' };
  }

  if (stage === 'authorize' && ['chosen', 'token'].includes(state.step)) {
    if (!passwords.length) {
      // Work shows this connector's own overview with a "Connect" button when
      // the account has not connected it yet. Only that exact dialog (it
      // carries this project's and folder's VibeZ marker) is confirmed, once.
      const overview = one(dialogs.filter(dialog => dialog !== menu && dialog !== picker &&
        (dialog.innerText || dialog.textContent || '').includes(marker)));
      if (overview && !state.overviewConnected) {
        const connect = one(controls(overview, 'button'), button => isLabel(button, connectLabel));
        if (!enabled(connect)) return { state: 'wait', reason: connect ? 'connect-disabled' : 'no-connect-button' };
        state.overviewConnected = true;
        state.overview = overview;
        state.connectedAt = Date.now();
        connect.click();
        return { state: 'wait', reason: 'connecting-connector' };
      }
      if (state.overviewConnected && Date.now() - (state.connectedAt || 0) < 3000) return { state: 'wait', reason: 'connecting-connector' };
      // Work may select the row without a Bearer dialog, or show nothing at all.
      // Report visible notice words (not page content) to see what Work said.
      const notices = controls(document, '[role="alert"],[role="status"],[data-sonner-toast],[aria-live="polite"],[aria-live="assertive"]')
        .map(node => node.innerText || '').join(' ').toLowerCase().normalize('NFKD').replace(/[^a-z ]+/g, ' ')
        .split(/\s+/).filter(Boolean).slice(0, 18);
      const detail = [];
      let chunk = 'notice';
      for (const word of notices) {
        if ((chunk + '-' + word).length > 32) { detail.push(chunk); chunk = word.slice(0, 32); } else chunk += '-' + word;
      }
      if (notices.length) detail.push(chunk);
      if (pickerRow) {
        const icons = [...pickerRow.querySelectorAll('svg path')].map(path => path.getAttribute('d') || '');
        const plus = icons.some(d => d.startsWith('M12 3V21'));
        detail.push(plus ? 'row-plus' : 'row-no-plus');
        // Measured live: the first click on a connector made moments ago only
        // connects it (Mistral says "Succesvol verbonden") and inserts nothing;
        // the row keeps its plus. Choose it once more instead of reloading.
        const said = notices.join(' ');
        if (plus && !exact && !dialogs.some(dialog => dialog !== menu && dialog !== picker) && !state.chosenAgain &&
            enabled(pickerRow) && /\b(verbonden|connected)\b/.test(said) && !/mislukt|failed|fout|error/.test(said)) {
          state.chosenAgain = true;
          pickerRow.click();
          return { state: 'wait', reason: 'choose-again' };
        }
      } else detail.push(picker ? 'row-missing' : 'picker-closed');
      return { state: 'wait', reason: exact ? 'reference-with-dialog' : dialogs.length ? 'no-password-dialog-open' : 'no-password-no-dialog', detail };
    }
    if (!authDialog || !allKnown(state.menu, menu, state.picker, picker, authDialog)) {
      return { state: 'unexpected-dialog', reason: authReason || 'other-dialog' };
    }
    if (!/^[A-Za-z0-9_-]{50,85}$/.test(token || '')) return { state: 'invalid-input' };
    if (state.step === 'token') return password.value === token ? { state: 'advanced' } : { state: 'unexpected-dialog', reason: 'token-field-changed' };
    if (password.disabled || password.readOnly || password.value) return { state: 'unexpected-dialog', reason: 'token-field-busy' };
    password.focus();
    document.execCommand('insertText', false, token);
    password.blur();
    if (password.value !== token) return { state: 'wait', reason: 'token-not-accepted' };
    state.password = password;
    // Shape only (length and last characters) to diagnose a rejected form later.
    state.tokenShape = { length: token.length, tail: token.slice(-6) };
    state.step = 'token';
    return { state: 'advanced' };
  }

  if (stage === 'confirm' && ['token', 'submitted'].includes(state.step)) {
    if (state.step === 'submitted') return { state: 'submitted' };
    if (!/^[A-Za-z0-9_-]{50,85}$/.test(token || '')) return { state: 'invalid-input' };
    if (!authDialog || !allKnown(state.menu, menu, state.picker, picker, authDialog) ||
        password.value !== token) {
      return { state: 'unexpected-dialog', reason: authReason || (password.value !== token ? 'token-field-changed' : 'other-dialog') };
    }
    const connect = one(controls(authDialog, 'button'), button => isLabel(button, connectLabel));
    if (!enabled(connect)) return { state: 'wait', reason: connect ? 'connect-disabled' : 'no-connect-button' };
    state.step = 'submitted';
    state.submittedAt = Date.now();
    state.schemeBefore = controls(authDialog, 'button').map(b => (b.getAttribute('aria-label') || b.innerText || '').trim()).filter(t => /bearer|schema|scheme/i.test(t)).join('|').slice(0, 40);
    connect.click();
    return { state: 'submitted' };
  }

  if (stage === 'reselect' && ['submitted', 'reselected'].includes(state.step)) {
    if (state.step === 'reselected') return { state: 'advanced' };
    if (passwords.length && !authDialog) return { state: 'unexpected-dialog', reason: authReason };
    if (passwords.length) {
      // The Bearer dialog stayed open after Verbinden. Report its visible
      // control names only, then do what a person does: close it once and
      // choose the same connector again.
      const name = text => (text || '').trim().toLowerCase().normalize('NFKD').replace(/[^a-z]+/g, '-').replace(/^-|-$/g, '').slice(0, 32);
      const detail = [];
      const value = password.value || '', shape = state.tokenShape || { length: 0, tail: '' };
      detail.push(!value ? 'token-cleared' : value.length === shape.length && value.endsWith(shape.tail) ? 'token-kept' :
        value.length > shape.length && value.endsWith(shape.tail) ? 'token-prefixed' : /^[•*]+$/.test(value) ? 'token-masked' :
        value.length > shape.length ? 'token-longer' : 'token-shorter');
      // Visible error text of the dialog, as lowercase words in short chunks.
      const alerts = controls(authDialog, '[role="alert"],[aria-live],[aria-invalid="true"],.text-destructive,.text-red-500,.text-error');
      const words = [...new Set(alerts.map(a => a.innerText || ''))].join(' ').toLowerCase().normalize('NFKD').replace(/[^a-z ]+/g, ' ').split(/\s+/).filter(Boolean).slice(0, 24);
      let chunk = 'alert';
      for (const word of words) {
        if ((chunk + '-' + word).length > 32) { detail.push(chunk); chunk = word.slice(0, 32); } else chunk += '-' + word;
      }
      detail.push(chunk);
      if (!state.closedAuth && Date.now() - (state.submittedAt || 0) >= 8000) {
        const close = one(controls(authDialog, 'button'), b => isLabel(b,
          /^(Close|Sluiten|Annuleren|Cancel|Fermer|Annuler|Schließen|Abbrechen|Cerrar|Cancelar|Chiudi|Annulla|Fechar|Zamknij|Anuluj|Закрити|Скасувати|إغلاق|إلغاء)$/i));
        if (close) {
          if (password.value) { password.focus(); password.select(); document.execCommand('delete'); password.blur(); }
          state.closedAuth = true;
          close.click();
          return { state: 'wait', reason: 'closed-auth-dialog', detail };
        }
      }
      return { state: 'wait', reason: state.closedAuth ? 'auth-dialog-reopened' : 'auth-dialog-still-open', detail };
    }
    // Work may still be inserting the reference after Verbinden. Clicking the
    // row again too early can toggle the connector off again.
    if (Date.now() - (state.submittedAt || 0) < 3000) return { state: 'wait', reason: 'settling' };
    if (picker && enabled(pickerRow)) {
      if (!allKnown(state.menu, menu, state.picker, picker)) return { state: 'unexpected-dialog', reason: 'other-dialog' };
      state.step = 'reselected';
      pickerRow.click();
      return { state: 'advanced' };
    }
    // Work can close its menus after the Bearer dialog. Without a selected
    // reference, reopen the same official + > Connectors route, at most twice.
    if (!dialogs.length) {
      if (state.reopen === 'plus') return { state: 'wait', reason: 'reopening-menu' };
      if ((state.reopened || 0) >= 2) return { state: 'wait', reason: 'reopen-exhausted' };
      const plus = one(controls(form, 'button[data-coachmark-target="chat-input-settings"][aria-haspopup="dialog"]'));
      if (!enabled(plus) || plus.getAttribute('aria-expanded') === 'true') return { state: 'wait', reason: 'plus-unavailable' };
      state.reopened = (state.reopened || 0) + 1;
      state.reopen = 'plus';
      state.menu = null;
      state.picker = null;
      plus.click();
      return { state: 'wait', reason: 'reopening-menu' };
    }
    if (state.reopen && menu && !picker) {
      if (!allKnown(menu)) return { state: 'unexpected-dialog', reason: 'other-dialog' };
      state.menu = menu;
      if (state.reopen !== 'plus' || !enabled(connectorMenu)) return { state: 'wait', reason: 'reopening-picker' };
      state.reopen = 'picker';
      press(connectorMenu);
      return { state: 'wait', reason: 'reopening-picker' };
    }
    if (state.reopen && picker) {
      if (!allKnown(state.menu, menu, picker)) return { state: 'unexpected-dialog', reason: 'other-dialog' };
      state.picker = picker;
      state.reopen = 'row';
      if (pickerSearch && !pickerRow && !pickerSearch.disabled && !pickerSearch.readOnly && !pickerSearch.value) {
        pickerSearch.focus();
        document.execCommand('insertText', false, title);
      }
    }
    return { state: 'wait', reason: !dialogs.length ? 'no-dialog' : picker ? (pickerRow ? 'row-disabled' : 'no-row') : 'no-picker' };
  }

  if (stage === 'selected' && ['chosen', 'submitted', 'reselected'].includes(state.step)) {
    return { state: 'wait', reason: exact < 1 ? 'no-reference' : 'dialog-open' };
  }
  return { state: 'invalid-stage' };
})
