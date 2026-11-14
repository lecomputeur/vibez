(function workConnectorRefresh(input) {
  // Runs only on this installation's own connector page in Mistral, in the
  // hidden setup view. It reconnects a no-key connector the way a person does
  // (⋮ → Opnieuw verbinden → Opslaan) and never fills in a key.
  const { name, force } = input || {};
  if (!/^vibezwork[a-f0-9]{16}_[a-z0-9]{4,12}$/.test(name || '')) return { state: 'invalid-input' };
  if (location.pathname !== '/connections/' + name || location.search || location.hash || window.top !== window) {
    return { state: 'wait', reason: 'loading' };
  }
  const visible = node => !!node?.getClientRects().length;
  const label = node => (node.getAttribute('aria-label') || node.innerText || '').trim();
  const heading = [...document.querySelectorAll('h1')].find(h => visible(h) && h.innerText.trim() === name.split('_')[0]);
  if (!heading) return { state: 'wait', reason: 'loading' };
  if ([...document.querySelectorAll('input[type=password]')].some(visible)) return { state: 'auth-required' };
  const main = document.querySelector('main') || document.body;
  const text = main.innerText || '';
  const toasts = [...document.querySelectorAll('[data-sonner-toast],[role=status],[role=alert]')].filter(visible).map(t => t.innerText || '').join(' ');
  const state = window.__vibezRefresh || (window.__vibezRefresh = { step: 'idle', tries: 0, at: 0 });
  // `force` exists for the live test only: it reconnects a reachable connector too.
  const forced = force === true && (state.step !== 'saved' || Date.now() - state.at < 2500);
  const stale = forced || /niet bereiken|cannot reach|can't reach|Opnieuw verbinden om tools|Reconnect to use tools/i.test(text);
  // A reachable connector lists its tools by title ("Read File", "Write File").
  // After a reconnect the caller is told so: Mistral needs a moment before the
  // connector can be chosen in a chat.
  if (!stale && /read[_ ]file|workspace[_ ]overview|list[_ ]directory/i.test(text)) {
    return state.tries ? { state: 'ok', reason: 'reconnected' } : { state: 'ok' };
  }
  if (state.step !== 'idle' && /Opnieuw verbinden mislukt|Reconnect failed/i.test(toasts) && Date.now() - state.at > 1500) {
    state.step = 'idle';
    if (state.tries >= 3) return { state: 'reconnect-failed' };
  }
  if (!/Geen authenticatie nodig|No auth(entication)? (needed|required)/i.test(text)) {
    // The "cannot reach" notice is drawn before the connection section below
    // it. Only a page that still lacks that section after 8 s is another kind.
    state.unknownSince = state.unknownSince || Date.now();
    return stale && Date.now() - state.unknownSince >= 8000 ? { state: 'auth-required', reason: 'not-open-connector' } : { state: 'wait', reason: 'checking' };
  }
  state.unknownSince = 0;
  // 3. The reconnect form: only a connection name, no key. Save it.
  const dialogs = [...document.querySelectorAll('[role=dialog],[role=alertdialog]')].filter(visible);
  for (const dialog of dialogs) {
    if (dialog.querySelector('input[type=password]')) return { state: 'auth-required' };
    const save = [...dialog.querySelectorAll('button')].filter(visible)
      .find(b => /^(Opslaan|Save|Verbinden|Connect)$/i.test(label(b)) && !b.disabled);
    const named = [...dialog.querySelectorAll('input')].filter(visible).every(i => i.type !== 'text' || i.value);
    if (save && named && state.step === 'menu') {
      state.step = 'saved';
      state.at = Date.now();
      save.click();
      return { state: 'wait', reason: 'saving' };
    }
    // Measured live after five minutes of downtime: Mistral kept this form open
    // after Save without ever calling the connector, for the full 90 s. A good
    // reconnect closes it within about 3 s, so stop here and let it be replaced.
    if (state.step === 'saved' && Date.now() - state.at > 8000) return { state: 'reconnect-failed', reason: 'save-stuck' };
    return { state: 'wait', reason: state.step === 'saved' ? 'connecting' : 'dialog' };
  }
  if (!stale) {
    // Not marked unreachable and no dialog: accept once that has held for 4 s,
    // so a late "cannot reach" status still gets its chance to appear.
    state.freshSince = state.freshSince || Date.now();
    return Date.now() - state.freshSince >= 4000 ? { state: 'ok', reason: 'not-stale' } : { state: 'wait', reason: 'checking' };
  }
  state.freshSince = 0;
  if (state.step === 'saved' && Date.now() - state.at < 15000) return { state: 'wait', reason: 'connecting' };
  // 2. Choose "Opnieuw verbinden" in the open connection menu.
  const item = [...document.querySelectorAll('[role=menuitem]')].filter(visible)
    .find(i => /^(Opnieuw verbinden|Reconnect)$/i.test(label(i)));
  if (item) {
    state.step = 'menu';
    item.click();
    return { state: 'wait', reason: 'menu' };
  }
  // 1. Open the ⋮ menu of the connection row (the last "Meer acties" on the page).
  if (state.tries >= 3) return { state: 'reconnect-failed' };
  if (Date.now() - state.at < 3000) return { state: 'wait', reason: 'opening' };
  const more = [...main.querySelectorAll('button')].filter(visible).filter(b => /^(Meer acties|More actions)$/i.test(label(b)));
  const row = more[more.length - 1];
  if (!row || more.length < 2) return { state: 'wait', reason: 'no-menu' };
  state.tries++;
  state.at = Date.now();
  state.step = 'opening';
  row.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse', button: 0 }));
  return { state: 'wait', reason: 'opening' };
})
