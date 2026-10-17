(() => {
  'use strict';
  if (document.documentElement.dataset.vibezOfflineFixture !== 'rich40') throw new Error('Resize latency test requires explicit synthetic fixture');
  window.__resizeLatency?.stop();
  const pane = document.querySelector('#chat');
  if (!pane) throw new Error('Resize latency test has no chat pane');
  const state = {startedWallMs: Date.now(), startedPerfMs: performance.now(), frames: [], heartbeats: [], resizes: [], wheels: [], scrolls: [], stopped: false};
  const limit = 12000;
  const push = (list, item) => { if (list.length < limit) list.push(item); };
  const probe = document.createElement('canvas');
  probe.width = 24;
  probe.height = 16;
  probe.id = 'vibez-resize-latency-pixel-probe';
  probe.setAttribute('aria-hidden', 'true');
  Object.assign(probe.style, {position: 'fixed', right: '8px', top: '8px', width: '24px', height: '16px', zIndex: '2147483647', pointerEvents: 'none'});
  const brush = probe.getContext('2d');
  if (!brush) throw new Error('Resize latency pixel probe has no canvas context');
  brush.fillStyle = 'rgb(40,40,170)';
  brush.fillRect(0, 0, 24, 16);
  document.body.append(probe);
  let sequence = 0, rafId = 0, timerId = 0, previousFrame = performance.now(), previousBeat = performance.now();
  function draw(now) {
    if (state.stopped) return;
    const id = ++sequence;
    // The saved native WebKit PNG must contain a newly painted patch, not only
    // a stale screenshot from before resizing. The patch lies outside chat ROI.
    const r = 40 + id % 200, g = 40 + Math.floor(id / 200) % 200;
    // Canvas pixel writes create no DOM/attribute MutationObserver records.
    // Updating a style every frame can keep a debounced application observer
    // from ever running, which would conceal the very resize work under test.
    brush.fillStyle = `rgb(${r},${g},170)`;
    brush.fillRect(0, 0, 24, 16);
    push(state.frames, {id, wallMs: Date.now(), perfMs: now, gapMs: now - previousFrame, width: innerWidth, height: innerHeight, dpr: devicePixelRatio, r, g});
    previousFrame = now;
    rafId = requestAnimationFrame(draw);
  }
  function beat() {
    if (state.stopped) return;
    const now = performance.now();
    push(state.heartbeats, {wallMs: Date.now(), perfMs: now, gapMs: now - previousBeat, width: innerWidth, height: innerHeight});
    previousBeat = now;
    timerId = setTimeout(beat, 100);
  }
  function onResize() { push(state.resizes, {wallMs: Date.now(), width: innerWidth, height: innerHeight}); }
  function onWheel(event) { push(state.wheels, {wallMs: Date.now(), trusted: event.isTrusted, deltaY: event.deltaY, beforeY: pane.scrollTop}); }
  function onScroll() { push(state.scrolls, {wallMs: Date.now(), y: pane.scrollTop}); }
  window.addEventListener('resize', onResize);
  pane.addEventListener('wheel', onWheel, {passive: true});
  pane.addEventListener('scroll', onScroll, {passive: true});
  rafId = requestAnimationFrame(draw);
  timerId = setTimeout(beat, 100);
  const report = () => ({...state, currentWallMs: Date.now(), currentPerfMs: performance.now(), width: innerWidth, height: innerHeight, visibility: document.visibilityState, scrollTop: pane.scrollTop, scrollHeight: pane.scrollHeight, clientHeight: pane.clientHeight, probeConnected: probe.isConnected, helper: window.__vibezRichRender?.status() || null});
  const stop = () => {
    if (!state.stopped) {
      state.stopped = true;
      cancelAnimationFrame(rafId);
      clearTimeout(timerId);
      window.removeEventListener('resize', onResize);
      pane.removeEventListener('wheel', onWheel);
      pane.removeEventListener('scroll', onScroll);
      probe.remove();
    }
    return report();
  };
  window.__resizeLatency = {report, stop};
  return {installed: true, startedWallMs: state.startedWallMs};
})()
