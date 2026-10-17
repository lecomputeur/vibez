(() => {
  'use strict';
  // Offline acceptance checks. This file never loads a URL or account data.
  // A real WebKit window runs these checks; Node is only used for syntax checks.
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
  const frames = async (count = 2) => { while (count-- > 0) await frame(); };
  const result = window.__richLifecycle = {done: false, running: false, checks: [], phases: [], errors: [], started: null, ended: null};
  let active = false;
  let oracleSerial = 0;
  const chat = () => document.querySelector('#chat');
  const renderer = () => window.__vibezRichRender;
  const check = (name, pass, details = {}) => {
    const row = {name, pass: !!pass, ...details};
    result.checks.push(row);
    result.passed = result.checks.filter(item => item.pass).length;
    result.failed = result.checks.filter(item => !item.pass).length;
    return row;
  };
  const phase = name => { result.phase = name; result.phases.push({name, at: performance.now()}); };
  const update = async () => { if (renderer()?.refresh) await renderer().refresh(); await frames(); };

  async function settle(maxMs = 12000) {
    const started = performance.now();
    let previous = '', steady = 0;
    while (performance.now() - started < maxMs) {
      await sleep(100);
      const value = `${chat().scrollHeight}:${chat().clientWidth}:${chat().clientHeight}`;
      steady = value === previous ? steady + 1 : 0;
      previous = value;
      if (steady >= 5) return {settled: true, elapsedMs: performance.now() - started};
    }
    return {settled: false, elapsedMs: performance.now() - started};
  }

  // Let mutation and ResizeObserver handling run naturally. Calling refresh()
  // here would conceal bugs in automatic invalidation after hosted-app updates.
  async function autoSettle() {
    await sleep(950);
    await frames(2);
    return settle();
  }

  // Full rendering is an independent height oracle. No expected size is copied
  // from helper internals, and the same DOM and viewport are used on both sides.
  async function geometry(label = 'geometry', {restore = true} = {}) {
    const pane = chat(), api = renderer();
    if (!pane || !api) throw new Error('Missing offline fixture or rendering helper');
    const reason = `lifecycle-oracle-${++oracleSerial}`;
    const initialY = pane.scrollTop;
    await settle();
    const optimizedBefore = pane.scrollHeight;
    let full;
    await api.pause(reason);
    try {
      await frames(3);
      await sleep(120);
      full = pane.scrollHeight;
    } finally {
      await api.resume(reason);
    }
    await update();
    const settled = await settle();
    const optimized = pane.scrollHeight;
    if (restore) pane.scrollTop = initialY;
    const delta = optimized - full;
    const row = check(label, Math.abs(delta) <= 8 && Math.abs(optimizedBefore - full) <= 8 && settled.settled, {
      optimizedBefore, optimized, full, delta, viewportWidth: pane.clientWidth,
      viewportHeight: pane.clientHeight, settled, beforeY: initialY, afterY: pane.scrollTop,
    });
    return row;
  }
  window.__richCheckGeometry = geometry;

  function visibleAnchor() {
    const pane = chat(), bounds = pane.getBoundingClientRect();
    const target = [...pane.querySelectorAll('article.assistant, article.user')].find(element => {
      const rect = element.getBoundingClientRect();
      return rect.bottom > bounds.top + 30 && rect.top < bounds.bottom - 20;
    });
    if (!target) throw new Error('No visible message anchor');
    return {element: target, top: target.getBoundingClientRect().top};
  }

  function selectionText(node) {
    const selection = window.getSelection(), range = document.createRange();
    range.selectNodeContents(node);
    selection.removeAllRanges();
    selection.addRange(range);
    const text = selection.toString();
    selection.removeAllRanges();
    return text;
  }

  async function scenario(name, callback) {
    phase(name);
    try { await callback(); }
    catch (error) {
      result.errors.push({phase: name, message: String(error), stack: String(error.stack || '')});
      check(`${name}: completed`, false, {error: String(error)});
    }
  }

  window.__richLifecycleStart = () => {
    if (active) return {started: false, reason: 'Already running'};
    active = true;
    result.running = true;
    result.started = performance.now();
    (async () => {
      const pane = chat();
      const api = renderer();
      if (!pane || !api) throw new Error('Install fixture and helper before starting lifecycle checks');
      if (document.documentElement.dataset.vibezOfflineFixture !== 'rich40' && document.documentElement.dataset.vibezOfflineRichTest !== '1') throw new Error('Explicit offline marker missing');
      const messages = pane.querySelector('.messages');
      const originalAssistants = [...messages.querySelectorAll('article.assistant')];
      const originalCount = originalAssistants.length;
      const originalChars = messages.textContent.length;
      const originalY = pane.scrollTop;
      result.fixture = {assistantReplies: originalCount, characters: originalChars, nodes: messages.querySelectorAll('*').length};
      check('Forty rich synthetic answers are present', originalCount === 40, result.fixture);
      check('WebKit supports content-visibility', CSS.supports('content-visibility', 'auto'));
      result.initialHelperStatus = api.status?.() || null;

      await scenario('Initial height and stationary viewport', async () => {
        await update();
        await settle();
        await geometry('Initial optimized height matches fully rendered height');
        pane.scrollTop = Math.round((pane.scrollHeight - pane.clientHeight) * 0.55);
        await frames(4);
        await settle();
        const anchor = visibleAnchor(), startY = pane.scrollTop, started = performance.now();
        await sleep(2000);
        const move = anchor.element.getBoundingClientRect().top - anchor.top;
        check('Stationary viewport stays put for two seconds', Math.abs(move) <= 3 && Math.abs(pane.scrollTop - startY) <= 3,
          {movePixels: move, scrollDelta: pane.scrollTop - startY, elapsedMs: performance.now() - started});
      });

      let streamed;
      await scenario('Streaming append and in-place updates', async () => {
        streamed = document.createElement('article');
        streamed.className = 'assistant';
        streamed.dataset.vibezMessage = 'assistant';
        streamed.dataset.vibezReplyId = 'lifecycle-streamed';
        streamed.dataset.vibezStreaming = 'true';
        streamed.setAttribute('aria-busy', 'true');
        streamed.innerHTML = '<div class="role">Synthetic streaming answer</div><div class="answer-body"><section class="rich-section markdown"><h2>Streaming lifecycle</h2><div class="stream-parts"></div></section></div>';
        messages.append(streamed);
        await update();
        pane.scrollTop = pane.scrollHeight;
        await frames(3);
        const parts = streamed.querySelector('.stream-parts');
        const samples = [];
        for (let i = 0; i < 18; i++) {
          const section = document.createElement('section');
          section.className = 'rich-section markdown';
          section.innerHTML = `<p>STREAM_CHUNK_${i}_END ${'Synthetic streaming prose with formatting and emoji 🧪. '.repeat(25)}</p><pre><code>const streamed_${i} = ${i};\n${'// local generated source\n'.repeat(12)}</code></pre><table><tbody><tr><td>Chunk ${i}</td><td>Complete</td></tr></tbody></table>`;
          parts.append(section);
          await sleep(45);
          // Follow the active response as the hosted page would while streaming.
          pane.scrollTop = pane.scrollHeight;
          await frames();
          samples.push({index: i, height: pane.scrollHeight, responseHeight: streamed.getBoundingClientRect().height});
        }
        const lastParagraph = parts.lastElementChild.querySelector('p');
        const initialText = lastParagraph.textContent;
        // React-like rendering often replaces a text node repeatedly.
        for (let i = 0; i < 8; i++) {
          lastParagraph.textContent = `${initialText} STREAM_REPLACEMENT_${i} ${'More text. '.repeat(i * 4)}`;
          await sleep(45);
          pane.scrollTop = pane.scrollHeight;
        }
        await autoSettle();
        const finalText = parts.textContent;
        const monotonic = samples.every((item, index) => !index || item.height >= samples[index - 1].height - 3);
        check('Streaming retains every appended rich chunk', Array.from({length: 18}, (_, i) => `STREAM_CHUNK_${i}_END`).every(token => finalText.includes(token)) && parts.querySelectorAll('table').length === 18 && parts.querySelectorAll('pre').length === 18,
          {chunks: parts.children.length, tables: parts.querySelectorAll('table').length, codeBlocks: parts.querySelectorAll('pre').length});
        check('Streaming text-node replacement keeps final response', finalText.includes('STREAM_REPLACEMENT_7') && !finalText.includes('STREAM_REPLACEMENT_6'));
        check('Streaming grows monotonically without collapsing', monotonic && samples[samples.length - 1].height > samples[0].height + 500,
          {first: samples[0], last: samples[samples.length - 1]});
        const activeSkipped = [streamed, ...streamed.querySelectorAll('.rich-section')].filter(element => getComputedStyle(element).contentVisibility !== 'visible').length;
        check('Busy streaming answer stays fully renderable', activeSkipped === 0 && streamed.getBoundingClientRect().height > 500, {containedSections: activeSkipped});
        await geometry('Active streaming height matches full rendering');
        const rangeText = selectionText(lastParagraph);
        // Native Selection follows rendered whitespace rules. In a normal
        // paragraph two spaces collapse and a trailing space may disappear;
        // textContent is therefore not a valid selection oracle. Compare the
        // same paragraph with containment fully paused instead.
        const selectionReason = 'lifecycle-selection-oracle';
        let controlSelection;
        await api.pause(selectionReason);
        try {
          await frames(3);
          controlSelection = selectionText(lastParagraph);
        } finally {
          await api.resume(selectionReason);
        }
        let firstDifference = -1;
        for (let i = 0; i < Math.max(rangeText.length, controlSelection.length); i++) {
          if (rangeText[i] !== controlSelection[i]) { firstDifference = i; break; }
        }
        const finalMarkersRetained = ['STREAM_CHUNK_17_END', 'STREAM_REPLACEMENT_7'].every(marker => rangeText.includes(marker) && controlSelection.includes(marker));
        check('Streamed text remains selectable', rangeText.length > 0 && rangeText === controlSelection && finalMarkersRetained, {
          selectedCharacters: rangeText.length, fullyRenderedSelectedCharacters: controlSelection.length,
          sourceCharacters: lastParagraph.textContent.length, finalMarkersRetained, firstDifference,
          optimizedNearDifference: firstDifference < 0 ? null : rangeText.slice(Math.max(0, firstDifference - 20), firstDifference + 40),
          fullyRenderedNearDifference: firstDifference < 0 ? null : controlSelection.slice(Math.max(0, firstDifference - 20), firstDifference + 40),
        });
        streamed.dataset.vibezStreaming = 'false';
        streamed.setAttribute('aria-busy', 'false');
        await autoSettle();
        await geometry('Completed streaming height matches full rendering');
      });

      await scenario('Historical offscreen message expansion', async () => {
        pane.scrollTop = Math.round((pane.scrollHeight - pane.clientHeight) * 0.57);
        await update();
        await settle();
        const target = originalAssistants[0], anchor = visibleAnchor();
        check('History edit target begins above viewport', target.getBoundingClientRect().bottom < pane.getBoundingClientRect().top);
        const previousHeight = pane.scrollHeight;
        const expansion = document.createElement('section');
        expansion.className = 'rich-section markdown';
        expansion.dataset.lifecycleExpansion = 'true';
        expansion.innerHTML = `<h2>HISTORY_EXPANSION_SENTINEL</h2><p>${'A historical response has expanded with entirely synthetic text. '.repeat(150)}</p><pre><code>${'const expanded = true;\n'.repeat(80)}</code></pre>`;
        target.querySelector('.answer-body').append(expansion);
        await autoSettle();
        const anchorMove = anchor.element.getBoundingClientRect().top - anchor.top;
        check('Historical expansion updates scroll extent', pane.scrollHeight > previousHeight + 500,
          {beforeHeight: previousHeight, afterHeight: pane.scrollHeight, growth: pane.scrollHeight - previousHeight});
        check('Historical expansion preserves stationary visible content', Math.abs(anchorMove) <= 8,
          {anchorMovePixels: anchorMove});
        await geometry('Expanded offscreen history matches full rendering');
        pane.scrollTop = 0;
        await update();
        await settle();
        check('Expanded historical content remains present and reachable', expansion.textContent.includes('HISTORY_EXPANSION_SENTINEL') && expansion.getBoundingClientRect().height > 500);
      });

      await scenario('Narrow and wide responsive layout', async () => {
        const app = document.querySelector('.app'), savedWidth = app.style.width, savedRight = app.style.right;
        const widths = [];
        try {
          for (const width of [980, 1440]) {
            app.style.width = `${width}px`;
            app.style.right = 'auto';
            await frames(4);
            await autoSettle();
            const row = await geometry(`Container resize to ${width}px keeps correct scroll height`);
            widths.push({requested: width, actual: app.getBoundingClientRect().width, pane: pane.clientWidth, height: row.full});
            pane.scrollTop = pane.scrollHeight;
            await frames(3);
            check(`Bottom remains reachable at ${width}px`, Math.abs(pane.scrollHeight - pane.clientHeight - pane.scrollTop) <= 3,
              {scrollTop: pane.scrollTop, extent: pane.scrollHeight - pane.clientHeight});
            pane.scrollTop = 0;
            await frames(3);
            check(`Top remains reachable at ${width}px`, pane.scrollTop === 0);
          }
          check('Responsive width test changes the actual content layout', widths[0].actual === 980 && widths[1].actual === 1440 && widths[0].pane < widths[1].pane && widths[0].height > widths[1].height,
            {widths});
        } finally {
          app.style.width = savedWidth;
          app.style.right = savedRight;
          await update();
          await settle();
        }
      });

      await scenario('Detached, removed and replaced messages', async () => {
        pane.scrollTop = Math.round((pane.scrollHeight - pane.clientHeight) * 0.60);
        await update();
        await settle();
        const beforeHeight = pane.scrollHeight;
        const detached = originalAssistants[2], sibling = detached.nextSibling;
        detached.remove();
        await autoSettle();
        check('Removing an offscreen message shrinks scroll extent', pane.scrollHeight < beforeHeight - 1000,
          {beforeHeight, removedHeight: pane.scrollHeight});
        await geometry('Removed message leaves no stale reserved height');
        messages.insertBefore(detached, sibling);
        await autoSettle();
        check('Reattaching a message restores its text', detached.isConnected && detached.querySelectorAll('.rich-section').length === 16);
        await geometry('Reattached message reserves its full height');
        const replacement = document.createElement('article');
        replacement.className = 'assistant';
        replacement.dataset.vibezMessage = 'assistant';
        replacement.dataset.vibezReplyId = 'lifecycle-replacement';
        replacement.innerHTML = '<div class="role">Synthetic replacement</div><div class="answer-body"><section class="rich-section markdown"><p>REPLACED_MESSAGE_SENTINEL</p></section></div>';
        const replaced = originalAssistants[3];
        replaced.replaceWith(replacement);
        await autoSettle();
        check('Replacing a historical message keeps the new content', replacement.isConnected && !replaced.isConnected && replacement.textContent.includes('REPLACED_MESSAGE_SENTINEL'));
        await geometry('Replacement does not retain the old large height');
        replacement.replaceWith(replaced);
        await update();
        await settle();
      });

      await scenario('Hosted-page style ownership', async () => {
        // A hosted renderer may legitimately hide an already managed answer.
        // Its new style must survive helper pause, remeasurement and release.
        const candidate = originalAssistants[5].cloneNode(true);
        candidate.dataset.vibezReplyId = 'lifecycle-host-style-ownership';
        candidate.dataset.vibezMessage = 'assistant';
        candidate.style.removeProperty('content-visibility');
        candidate.style.removeProperty('contain-intrinsic-block-size');
        messages.insertBefore(candidate, streamed || null);
        try {
          await autoSettle();
          const optimized = getComputedStyle(candidate).contentVisibility;
          check('Style ownership fixture begins as a managed large answer', optimized === 'auto',
            {contentVisibility: optimized, height: candidate.getBoundingClientRect().height});
          candidate.style.setProperty('display', 'none');
          candidate.style.setProperty('content-visibility', 'hidden');
          await autoSettle();
          check('Hosted-page visibility changes are retained during automatic updates', candidate.style.display === 'none' && getComputedStyle(candidate).display === 'none' && candidate.style.contentVisibility === 'hidden');
          const reason = 'lifecycle-host-style-ownership';
          await api.pause(reason);
          try {
            await frames(2);
            check('Hosted-page visibility changes survive helper pause', candidate.style.display === 'none' && getComputedStyle(candidate).display === 'none' && candidate.style.contentVisibility === 'hidden');
          } finally {
            await api.resume(reason);
          }
          await autoSettle();
          check('Hosted-page visibility changes survive helper resume', candidate.style.display === 'none' && getComputedStyle(candidate).display === 'none' && candidate.style.contentVisibility === 'hidden');
          candidate.remove();
          await autoSettle();
          check('Releasing a removed answer preserves newer hosted-page styles', candidate.style.display === 'none' && candidate.style.contentVisibility === 'hidden',
            {releasedInlineDisplay: candidate.style.display, releasedContentVisibility: candidate.style.contentVisibility});
        } finally {
          candidate.remove();
          await autoSettle();
        }
      });

      await scenario('Loaded stylesheet changes paragraph heights', async () => {
        // The test asset is bundled beside the offline page. Unlike a new
        // inline <style>, this exercises a genuine load allowed by style-src
        // 'self'. The helper must notice it without a manual refresh().
        await autoSettle();
        const beforeHeight = pane.scrollHeight;
        const paragraph = originalAssistants[0].querySelector('p');
        const beforeLineHeight = parseFloat(getComputedStyle(paragraph).lineHeight);
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'rich-height-test.css';
        try {
          await new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
              link.onload = link.onerror = null;
              reject(new Error('Same-origin height stylesheet did not load within five seconds'));
            }, 5000);
            link.onload = () => {
              clearTimeout(timer);
              link.onload = link.onerror = null;
              resolve();
            };
            link.onerror = () => {
              clearTimeout(timer);
              link.onload = link.onerror = null;
              reject(new Error('Same-origin height stylesheet failed to load'));
            };
            document.head.append(link);
          });
          await autoSettle();
          const afterLineHeight = parseFloat(getComputedStyle(paragraph).lineHeight);
          const changedHeight = pane.scrollHeight;
          check('Loaded stylesheet actually increases paragraph line height', Number.isFinite(afterLineHeight) && afterLineHeight > beforeLineHeight + 1,
            {beforeLineHeight, afterLineHeight});
          check('Loaded stylesheet automatically updates rich-history extent', changedHeight > beforeHeight + 1000,
            {beforeHeight, changedHeight, growth: changedHeight - beforeHeight});
          await geometry('Loaded stylesheet preserves full rendered history height');
        } finally {
          link.remove();
          await autoSettle();
          const restoredLineHeight = parseFloat(getComputedStyle(paragraph).lineHeight);
          check('Removing stylesheet restores paragraph line height', Math.abs(restoredLineHeight - beforeLineHeight) <= 0.1,
            {beforeLineHeight, restoredLineHeight});
          const restoredHeight = pane.scrollHeight;
          check('Removing stylesheet automatically restores rich-history extent', Math.abs(restoredHeight - beforeHeight) <= 8,
            {beforeHeight, restoredHeight, delta: restoredHeight - beforeHeight});
          await geometry('Removed stylesheet leaves no stale reserved height');
        }
      });

      await scenario('Overlapping exact cache refreshes', async () => {
        await update();
        await settle();
        let firstResolved = false;
        const first = api.refresh().then(value => { firstResolved = true; return value; });
        const started = performance.now();
        let overlapState = null;
        while (performance.now() - started < 15000) {
          await frame();
          const status = api.status();
          const limit = status.cachedBatchLimit || 2;
          if (status.running && status.pendingMeasurements > 0 && status.pendingMeasurements <= limit) {
            overlapState = status;
            break;
          }
          if (firstResolved) break;
        }
        check('A second refresh overlaps the final in-flight cache batch', overlapState !== null,
          {overlapState, observationMs: performance.now() - started, firstAlreadyResolved: firstResolved});
        if (!overlapState) {
          await first;
          return;
        }
        // Queue new invalidation while the last current batch is still in
        // flight. Its completion must not resolve either promise while that
        // newly queued exact refresh remains unfinished.
        const second = api.refresh();
        let timer;
        let states;
        try {
          states = await Promise.race([
            Promise.all([first, second]),
            new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Overlapping refreshes did not drain within thirty seconds')), 30000); }),
          ]);
        } finally {
          clearTimeout(timer);
        }
        const finalStatus = api.status();
        check('Overlapping refresh promises resolve only after all exact work drains',
          states.every(status => status.pendingMeasurements === 0 && status.working === false && status.running === false)
          && finalStatus.pendingMeasurements === 0 && finalStatus.working === false && finalStatus.running === false,
          {resolvedStates: states, finalStatus});
        await geometry('Overlapping refreshes retain full-rendered page height');
      });

      await scenario('Programmatic scroll during a cache batch', async () => {
        await update();
        await settle();
        pane.scrollTop = Math.round((pane.scrollHeight - pane.clientHeight) * 0.50);
        await frames(4);
        const initialHeight = pane.scrollHeight;
        let resolved = false;
        const refreshing = api.refresh().then(value => { resolved = true; return value; });
        const started = performance.now();
        let inFlight = null;
        while (performance.now() - started < 15000) {
          await frame();
          const status = api.status();
          if (status.running && status.pendingMeasurements > 0 && status.pendingMeasurements <= (status.cachedBatchLimit || 2)) {
            inFlight = status;
            break;
          }
          if (resolved) break;
        }
        check('Programmatic scroll occurs during the final active cache batch', inFlight !== null,
          {inFlight, observationMs: performance.now() - started});
        if (!inFlight) {
          await refreshing;
          return;
        }
        const beforeY = pane.scrollTop;
        pane.scrollTop = Math.min(pane.scrollHeight - pane.clientHeight - 20, beforeY + 170);
        const requestedY = pane.scrollTop;
        let timer;
        try {
          await Promise.race([
            refreshing,
            new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('In-flight scroll refresh did not finish within thirty seconds')), 30000); }),
          ]);
        } finally {
          clearTimeout(timer);
        }
        await frames(3);
        await sleep(150);
        const actualY = pane.scrollTop;
        check('Cache completion preserves an explicit programmatic scroll', Math.abs(requestedY - beforeY) > 100 && Math.abs(actualY - requestedY) <= 3 && Math.abs(pane.scrollHeight - initialHeight) <= 8,
          {beforeY, requestedY, actualY, errorPixels: actualY - requestedY, beforeHeight: initialHeight, afterHeight: pane.scrollHeight, helper: api.status()});
        await geometry('Programmatic scroll preserves the exact full-rendered height');
      });

      await scenario('Simulated BFCache lifecycle', async () => {
        // Synthetic persisted events verify the helper lifecycle contract;
        // they do not constitute an actual browser back-forward cache hit.
        api.pause('capture');
        api.pause('find');
        dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
        await frames(2);
        dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
        await update();
        await settle();
        const status = api.status();
        check('Simulated persisted page lifecycle keeps the helper active',
          status.optimized > 0 && status.running === false && status.working !== true &&
          (status.pendingMeasurements || 0) === 0 && !status.disposed
          && !status.paused.includes('capture') && !status.paused.includes('find'),
          {simulatedEvents: true, actualBFCacheHit: false, helper: status});
        await geometry('Simulated persisted page lifecycle preserves full-rendered geometry');
      });

      await scenario('Final content and idle quiescence', async () => {
        pane.scrollTop = 0;
        await update();
        await settle();
        const firstParagraph = originalAssistants[0].querySelector('p');
        check('Original rich text remains selectable', selectionText(firstParagraph) === firstParagraph.textContent);
        check('Original answers are still connected after lifecycle changes', originalAssistants.every(element => element.isConnected) && messages.querySelectorAll('article.assistant').length === originalCount + (streamed?.isConnected ? 1 : 0));
        check('Fixture keeps all original text plus intentional additions', messages.textContent.length >= originalChars, {initialCharacters: originalChars, finalCharacters: messages.textContent.length});
        await geometry('Final complete page matches full-rendered height');
        pane.scrollTop = Math.min(originalY, pane.scrollHeight - pane.clientHeight);
        await update();
        await settle();
        const countersBefore = api.status?.() || null;
        const idleAnchor = visibleAnchor(), idleY = pane.scrollTop;
        let mutations = 0;
        const observer = new MutationObserver(records => { mutations += records.length; });
        observer.observe(messages, {subtree: true, attributes: true, childList: true, characterData: true});
        await sleep(2500);
        observer.disconnect();
        const idleMove = idleAnchor.element.getBoundingClientRect().top - idleAnchor.top;
        check('No uncontrolled DOM mutation loop after settling', mutations <= 2, {mutations, observationMs: 2500, statusBefore: countersBefore, statusAfter: api.status?.() || null});
        check('No uncontrolled scroll jumps after settling', Math.abs(idleMove) <= 3 && Math.abs(pane.scrollTop - idleY) <= 3, {anchorMovePixels: idleMove, scrollDelta: pane.scrollTop - idleY});
        result.finalHelperStatus = api.status?.() || null;
      });
    })().catch(error => {
      result.errors.push({phase: result.phase, message: String(error), stack: String(error.stack || '')});
      check('Lifecycle runner completed without fatal error', false, {error: String(error)});
    }).finally(() => {
      result.running = false;
      result.done = true;
      result.ended = performance.now();
      result.elapsedMs = result.ended - result.started;
      result.ok = result.failed === 0;
      result.phase = 'done';
    });
    return {started: true};
  };
  return {installed: true, entry: '__richLifecycleStart', geometryEntry: '__richCheckGeometry'};
})()
