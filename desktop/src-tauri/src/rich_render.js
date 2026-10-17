/* Linux rich-chat rendering containment. No IPC or telemetry. */
(() => {
  'use strict';
  if (window.top !== window || window.__vibezRichRender) return;
  const fixture = document.documentElement?.getAttribute('data-vibez-offline-fixture') === 'rich40'
    || document.documentElement?.getAttribute('data-vibez-offline-rich-test') === '1';
  const local = ['tauri:', 'file:'].includes(location.protocol)
    || ['localhost', 'tauri.localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  if (!['https://chat.mistral.ai', 'https://vibe.mistral.ai'].includes(location.origin)
    && !(fixture && local)) return;
  if (!window.CSS?.supports('content-visibility', 'auto')
    || !CSS.supports('contain-intrinsic-block-size', 'auto 1px')
    || !window.ResizeObserver || !window.MutationObserver) return;

  // Live selectors are deliberately narrow and still require validation against
  // the current hosted app. Unknown markup remains completely untouched.
  const selector = fixture ? '[data-vibez-message="assistant"]' : [
    'main [data-message-author-role="assistant"]',
    'main [data-role="assistant"][data-message-id]',
    'main [data-testid="assistant-message"]',
    'main [data-testid="message-assistant"]'
  ].join(',');
  const streamingSelector = '[aria-busy="true"],[data-vibez-streaming="true"],'
    + '[data-streaming="true"],[data-is-streaming="true"]';
  const editableSelector = 'input,textarea,select,[contenteditable]:not([contenteditable="false"]),iframe,video';
  const changedAttributes = ['class', 'style', 'aria-busy', 'data-vibez-message',
    'data-message-author-role', 'data-role', 'data-message-id', 'data-testid',
    'data-vibez-streaming', 'data-streaming', 'data-is-streaming',
    'href', 'rel', 'media', 'disabled', 'type', 'hidden', 'open', 'aria-hidden'];
  const propertyNames = ['content-visibility', 'contain-intrinsic-block-size'];
  const records = new Map();
  const ownStyles = new WeakMap();
  const pauses = new Set();
  const counters = { scans: 0, passes: 0, measurements: 0, mutations: 0,
    resizeInvalidations: 0, anchorCorrections: 0, streamingExemptions: 0,
    completedBatches: 0, batchedMeasurements: 0, maxBatchMs: 0, maxSynchronousMeasureMs: 0 };
  let disposed = false, running = false, timer = 0, unstableTimer = 0;
  let needScan = true, invalidateAll = true, forceNext = false, rerun = false;
  let waiters = [], anchor = null, userEpoch = 0, globalWidth = 0;
  const stableAfterMs = 700;
  const cachedBatchLimit = 2;
  const raf = () => new Promise(resolve => requestAnimationFrame(resolve));
  const rememberStyle = element => ownStyles.set(element, element.getAttribute('style') || '');
  const readProperty = (element, name) => ({
    value: element.style.getPropertyValue(name), priority: element.style.getPropertyPriority(name)
  });
  const sameProperty = (a, b) => a.value === b.value && a.priority === b.priority;
  const setProperty = (record, name, value) => {
    const { element } = record;
    const current = readProperty(element, name);
    if (!record.owned[name] || !sameProperty(current, record.owned[name])) record.original[name] = current;
    if (value) element.style.setProperty(name, value, 'important');
    else element.style.removeProperty(name);
    record.owned[name] = readProperty(element, name);
    rememberStyle(element);
  };
  const restoreProperty = (record, name) => {
    const current = readProperty(record.element, name);
    const owned = record.owned[name];
    if (owned && sameProperty(current, owned)) {
      const saved = record.original[name];
      if (saved.value) record.element.style.setProperty(name, saved.value, saved.priority);
      else record.element.style.removeProperty(name);
    } else {
      // The host may update or hide an answer after attachment. Such a write
      // replaces our restoration baseline and must never be undone on cleanup.
      record.original[name] = current;
    }
    delete record.owned[name];
    rememberStyle(record.element);
  };
  const expose = record => {
    restoreProperty(record, 'content-visibility');
    restoreProperty(record, 'contain-intrinsic-block-size');
    record.optimized = false;
  };
  const isStreaming = element => element.matches(streamingSelector)
    || !!element.querySelector(streamingSelector);
  function owner(node) {
    let element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    while (element) {
      if (records.has(element)) return records.get(element);
      element = element.parentElement;
    }
    return null;
  }
  function scrollContainer(element) {
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      const overflow = getComputedStyle(parent).overflowY;
      if (/auto|scroll/.test(overflow) && parent.scrollHeight > parent.clientHeight + 2) return parent;
    }
    return document.scrollingElement;
  }
  function saveAnchor() {
    if (anchor || !records.size || disposed) return;
    for (const y of [0.32, 0.55, 0.75]) {
      const hit = document.elementFromPoint(Math.floor(innerWidth * 0.62), Math.floor(innerHeight * y));
      if (!hit || !owner(hit)) continue;
      const parent = scrollContainer(hit);
      if (!parent) continue;
      anchor = { element: hit, parent, top: hit.getBoundingClientRect().top, scrollTop: parent.scrollTop, epoch: userEpoch };
      return;
    }
  }
  function restoreAnchor() {
    const previous = anchor;
    anchor = null;
    // Native wheel animation and hosted-page autoscroll can continue after
    // their initiating input event. Never undo movement that occurred while
    // this batch yielded to WebKit.
    if (!previous || previous.epoch !== userEpoch || !previous.element.isConnected
      || !previous.parent.isConnected
      || Math.abs(previous.parent.scrollTop - previous.scrollTop) > 0.5) return;
    const delta = previous.element.getBoundingClientRect().top - previous.top;
    if (Number.isFinite(delta) && Math.abs(delta) > 0.5) {
      previous.parent.scrollTop += delta;
      counters.anchorCorrections++;
    }
  }
  function schedule(delay = 0, force = false) {
    if (disposed) return;
    forceNext ||= force;
    if (running) { rerun = true; return; }
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { timer = 0; void pass(); }, delay);
  }
  function dirty(record, timestamp = performance.now()) {
    // Streaming into the already exposed tail must not force a layout read for
    // every token. Only exposing a previously skipped answer needs an anchor.
    if (record.optimized) saveAnchor();
    record.version++;
    record.dirty = true;
    record.changedAt = timestamp;
    expose(record);
  }
  function scan() {
    counters.scans++;
    needScan = false;
    for (const [element, record] of records) {
      if (!element.isConnected || !element.matches(selector)) {
        resizeObserver.unobserve(element);
        propertyNames.forEach(name => restoreProperty(record, name));
        records.delete(element);
      }
    }
    // Prefer outer role wrappers when the hosted app nests two known markers.
    const candidates = Array.from(document.querySelectorAll(selector));
    const candidateSet = new Set(candidates);
    for (const element of candidates) {
      if (records.has(element)) continue;
      let nested = false;
      for (let parent = element.parentElement; parent; parent = parent.parentElement) {
        if (candidateSet.has(parent)) { nested = true; break; }
      }
      if (nested || element.matches(editableSelector) || element.querySelector(editableSelector)) continue;
      const display = getComputedStyle(element).display;
      // Require a formatting context already provided by the page. Creating
      // display:flow-root ourselves could override host display:none/hidden CSS.
      // Plain blocks with potentially collapsing margins remain untouched.
      if (!['flow-root', 'flex', 'grid'].includes(display)) continue;
      const original = {};
      for (const name of propertyNames) original[name] = {
        value: element.style.getPropertyValue(name), priority: element.style.getPropertyPriority(name)
      };
      const record = { element, original, owned: {}, dirty: true, changedAt: 0,
        optimized: false, width: 0, observedWidth: 0, measuredHeight: 0, version: 0, exempt: false };
      records.set(element, record);
      resizeObserver.observe(element);
    }
  }
  function pendingMeasurements() {
    return Array.from(records.values()).filter(record => record.dirty && !record.exempt).length;
  }
  async function pass() {
    if (disposed || running) return;
    running = true;
    const batchStarted = performance.now();
    const force = forceNext;
    rerun = false;
    counters.passes++;
    let nextWork = Infinity;
    try {
      if (needScan) scan();
      if (invalidateAll) {
        // A resize invalidates the entire cache, but must not expose the entire
        // transcript in one frame. Only the chosen batch is expanded below.
        for (const record of records.values()) {
          record.version++;
          record.dirty = true;
          record.changedAt = 0;
        }
        invalidateAll = false;
      }
      const ordered = Array.from(records.values()).filter(record => record.element.isConnected)
        .sort((a, b) => a.element.compareDocumentPosition(b.element) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1);
      const last = ordered.at(-1);
      const now = performance.now();
      const ready = [];
      for (const record of ordered) {
        const streaming = isStreaming(record.element);
        record.exempt = record === last || streaming || !!record.element.querySelector(editableSelector);
        if (record.exempt) {
          if (record.optimized) { saveAnchor(); expose(record); }
          if (streaming) counters.streamingExemptions++;
          record.dirty = true;
          continue;
        }
        if (pauses.size) continue;
        if (!record.dirty) continue;
        const remaining = stableAfterMs - (now - record.changedAt);
        if (!force && remaining > 0) { nextWork = Math.min(nextWork, remaining); continue; }
        ready.push(record);
      }
      // At initial attachment, or after an intentional Find/capture expansion,
      // reading already rendered boxes together removes no containment. Every
      // ordinary cache invalidation expands at most two historical answers.
      const alreadyExpanded = ordered.every(record => !record.optimized);
      const chosen = alreadyExpanded ? ready : ready.slice(0, cachedBatchLimit);
      const measuring = [];
      for (const record of chosen) {
        saveAnchor();
        expose(record);
        measuring.push({ record, version: record.version });
      }
      if (measuring.length) {
        // Separate all style writes from all geometry reads. No scroll callback
        // performs layout or rescans the message list.
        await raf();
        const sizes = measuring.map(({ record, version }) => {
          const measureStarted = performance.now();
          const element = record.element;
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          const contentHeight = rect.height - (parseFloat(style.paddingTop) || 0)
            - (parseFloat(style.paddingBottom) || 0) - (parseFloat(style.borderTopWidth) || 0)
            - (parseFloat(style.borderBottomWidth) || 0);
          counters.measurements++;
          counters.maxSynchronousMeasureMs = Math.max(counters.maxSynchronousMeasureMs, performance.now() - measureStarted);
          return { record, version, height: Math.max(0, contentHeight), width: rect.width,
            eligible: ['flow-root', 'flex', 'grid'].includes(style.display)
              && style.contentVisibility === 'visible' && rect.width > 0
              && rect.height >= Math.max(1200, innerHeight * 2) };
        });
        for (const size of sizes) {
          const { record } = size;
          if (disposed || pauses.size || !record.element.isConnected || record.version !== size.version
            || isStreaming(record.element)) continue;
          record.width = size.width;
          record.measuredHeight = size.height;
          record.dirty = false;
          if (!size.eligible) continue;
          setProperty(record, 'contain-intrinsic-block-size', 'auto ' + size.height + 'px');
          setProperty(record, 'content-visibility', 'auto');
          record.optimized = true;
        }
        counters.completedBatches++;
        counters.batchedMeasurements += measuring.length;
      }
      // Give WebKit a paint opportunity with this batch contained again before
      // another historical batch is expanded. Anchor restoration is local to
      // each batch and is skipped if the user scrolled meanwhile.
      if (anchor) { await raf(); restoreAnchor(); }
      if (ready.length > chosen.length) nextWork = Math.min(nextWork, 16);
    } finally {
      running = false;
      counters.maxBatchMs = Math.max(counters.maxBatchMs, performance.now() - batchStarted);
      const state = status();
      if ((!pendingMeasurements() && !invalidateAll && !needScan) || pauses.size || disposed) {
        forceNext = false;
        waiters.splice(0).forEach(resolve => resolve(state));
      }
      if (rerun) schedule(0);
      else if (Number.isFinite(nextWork)) schedule(Math.max(16, Math.ceil(nextWork)));
    }
  }
  function status() {
    const values = Array.from(records.values());
    const pending = values.filter(record => record.dirty && !record.exempt).length;
    return { version: 3, experimental: true, fixture, disposed, running,
      messages: values.length, optimized: values.filter(record => record.optimized).length,
      dirty: values.filter(record => record.dirty).length, paused: Array.from(pauses),
      pendingMeasurements: pending, working: running || pending > 0 || invalidateAll || needScan,
      cachedBatchLimit,
      ...counters };
  }
  function refresh() {
    if (disposed) return Promise.resolve(status());
    needScan = true;
    invalidateAll = true;
    const promise = new Promise(resolve => waiters.push(resolve));
    schedule(0, true);
    return promise;
  }
  function pause(reason = 'manual') {
    if (disposed) return status();
    if (pauses.has(String(reason))) return status();
    saveAnchor();
    pauses.add(String(reason));
    for (const record of records.values()) expose(record);
    restoreAnchor();
    return status();
  }
  function resume(reason = 'manual') {
    pauses.delete(String(reason));
    return refresh();
  }
  function invalidate() {
    if (disposed) return;
    invalidateAll = true;
    counters.resizeInvalidations++;
    schedule(100);
  }
  const resizeObserver = new ResizeObserver(entries => {
    let changed = false;
    for (const entry of entries) {
      if (entry.target === document.documentElement) {
        const width = entry.contentRect.width;
        if (globalWidth && Math.abs(width - globalWidth) > 0.5) changed = true;
        globalWidth = width;
      } else {
        const record = records.get(entry.target);
        if (!record) continue;
        const width = entry.contentRect.width;
        if (record.observedWidth && Math.abs(width - record.observedWidth) > 0.5) changed = true;
        record.observedWidth = width;
      }
    }
    if (changed) invalidate();
  });
  function stylesheetNode(node) {
    if (node.nodeType !== Node.ELEMENT_NODE) return node.parentElement?.tagName === 'STYLE';
    return node.matches('style,link[rel~="stylesheet"]')
      || !!node.querySelector('style,link[rel~="stylesheet"]');
  }
  function stylesheetMutation(mutation) {
    const element = mutation.target.nodeType === Node.ELEMENT_NODE
      ? mutation.target : mutation.target.parentElement;
    if (element?.closest('style') || element?.tagName === 'LINK') return true;
    return mutation.type === 'childList'
      && [...mutation.addedNodes, ...mutation.removedNodes].some(stylesheetNode);
  }
  const mutationObserver = new MutationObserver(mutations => {
    let relevant = false;
    for (const mutation of mutations) {
      if (mutation.type === 'attributes' && mutation.attributeName === 'style'
        && ownStyles.get(mutation.target) === (mutation.target.getAttribute('style') || '')) continue;
      if (stylesheetMutation(mutation)) {
        invalidateAll = true;
        relevant = true;
      }
      const record = owner(mutation.target);
      if (record) { dirty(record); relevant = true; }
      if (mutation.type === 'childList' && (mutation.addedNodes.length || mutation.removedNodes.length)) {
        // New descendants of an existing answer cannot create a new outer
        // answer. Avoid rescanning a huge transcript on every streamed token.
        if (!record) needScan = true;
        relevant = true;
      }
      if (!record && mutation.type === 'attributes') {
        if (!['style', 'class'].includes(mutation.attributeName)) needScan = true;
        // Ancestor class/style changes can change fonts, width, or line height.
        if (mutation.target === document.documentElement || mutation.target === document.body
          || Array.from(records.keys()).some(element => mutation.target.contains(element))) {
          invalidateAll = true;
          relevant = true;
        }
        relevant ||= needScan;
      }
    }
    if (relevant) { counters.mutations++; schedule(90); }
  });
  function onInteraction() { userEpoch++; }
  function onKey(event) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') pause('find');
    else if (event.key === 'Escape' && pauses.has('find')) void resume('find');
    onInteraction();
  }
  function onSelection() {
    // WebKit's native Find selects its match and can keep that selection after
    // the dialog closes. Find already exposes every answer, so those events
    // must not create a second, persistent manual-selection pause. Preserve
    // any selection pause that was present before Find opened.
    if (pauses.has('find')) return;
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed) pause('selection');
    else if (pauses.has('selection')) void resume('selection');
  }
  // A cached page keeps this document and its JS global. Disposing on a
  // persisted pagehide would leave an inert API that blocks later injection.
  function onPageHide(event) { if (!event.persisted) dispose(); }
  function onPageShow(event) {
    if (!event.persisted) return;
    // A native capture/search belongs to the document active at the time.
    // Its cleanup can run on a different page while this document is cached.
    pauses.delete('capture');
    pauses.delete('find');
    void refresh();
  }
  function beforePrint() { pause('print'); }
  function afterPrint() { void resume('print'); }
  function onResourceLoad(event) {
    if (event.target?.matches?.('link[rel~="stylesheet"]')) invalidate();
    else {
      const record = event.target ? owner(event.target) : null;
      if (record) { dirty(record); schedule(stableAfterMs); }
    }
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    clearTimeout(timer);
    clearTimeout(unstableTimer);
    mutationObserver.disconnect();
    resizeObserver.disconnect();
    for (const record of records.values()) propertyNames.forEach(name => restoreProperty(record, name));
    records.clear();
    document.removeEventListener('keydown', onKey, true);
    document.removeEventListener('wheel', onInteraction, true);
    document.removeEventListener('pointerdown', onInteraction, true);
    document.removeEventListener('selectionchange', onSelection);
    document.removeEventListener('load', onResourceLoad, true);
    document.removeEventListener('error', onResourceLoad, true);
    window.removeEventListener('resize', invalidate);
    window.removeEventListener('beforeprint', beforePrint);
    window.removeEventListener('afterprint', afterPrint);
    window.removeEventListener('pagehide', onPageHide);
    window.removeEventListener('pageshow', onPageShow);
    document.fonts?.removeEventListener('loadingdone', invalidate);
    waiters.splice(0).forEach(resolve => resolve(status()));
  }
  Object.defineProperty(window, '__vibezRichRender', {
    configurable: true, value: Object.freeze({ status, pause, resume, refresh, dispose })
  });
  document.addEventListener('keydown', onKey, true);
  document.addEventListener('wheel', onInteraction, { passive: true, capture: true });
  document.addEventListener('pointerdown', onInteraction, { passive: true, capture: true });
  document.addEventListener('selectionchange', onSelection);
  document.addEventListener('load', onResourceLoad, true);
  document.addEventListener('error', onResourceLoad, true);
  window.addEventListener('resize', invalidate, { passive: true });
  window.addEventListener('beforeprint', beforePrint);
  window.addEventListener('afterprint', afterPrint);
  window.addEventListener('pagehide', onPageHide);
  window.addEventListener('pageshow', onPageShow);
  document.fonts?.addEventListener('loadingdone', invalidate);
  mutationObserver.observe(document.documentElement, { childList: true, subtree: true,
    characterData: true, attributes: true, attributeFilter: changedAttributes });
  resizeObserver.observe(document.documentElement);
  schedule(0, true);
})();
