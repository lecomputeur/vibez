'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const helper = new vm.Script(fs.readFileSync(
  path.join(__dirname, '../src-tauri/src/rich_render.js'), 'utf8'),
  {filename: 'rich_render.js'});

// These cases must stop before rendering starts. Deliberately provide no usable
// DOM, observers or scheduler: a gated page must retain its original rendering.
function runGatedPage({url, fixture = false, subframe = false,
  css = true, unsupported = [], resizeObserver = true, mutationObserver = true}) {
  const calls = {attributeReads: 0, observers: 0, writes: 0};
  const forbidden = action => {
    throw new Error(`Gated helper attempted ${action}`);
  };
  const readOnly = (object, label) => new Proxy(object, {
    get(target, property) {
      if (Object.hasOwn(target, property)) return target[property];
      return forbidden(`${label}.${String(property)}`);
    },
    set() { calls.writes++; return forbidden(`${label} assignment`); },
    defineProperty() { calls.writes++; return forbidden(`${label} definition`); },
    deleteProperty() { calls.writes++; return forbidden(`${label} deletion`); },
  });
  const element = readOnly({getAttribute(name) {
    calls.attributeReads++;
    return fixture && name === 'data-vibez-offline-fixture' ? 'rich40' : null;
  }}, 'documentElement');
  const document = readOnly({documentElement: element}, 'document');
  const CSS = css ? Object.freeze({supports: property => !unsupported.includes(property)}) : undefined;
  class Observer {
    constructor() { calls.observers++; forbidden('observer construction'); }
  }
  const location = new URL(url);
  const windowProperties = {
    __vibezRichRender: undefined, CSS,
    ResizeObserver: resizeObserver ? Observer : undefined,
    MutationObserver: mutationObserver ? Observer : undefined,
  };
  const window = readOnly(windowProperties, 'window');
  windowProperties.top = subframe ? Object.freeze({}) : window;
  const context = {
    window, document, CSS, location,
    ResizeObserver: windowProperties.ResizeObserver,
    MutationObserver: windowProperties.MutationObserver,
    setTimeout: () => forbidden('timer scheduling'),
    requestAnimationFrame: () => forbidden('animation scheduling'),
    getComputedStyle: () => forbidden('style inspection'),
  };
  assert.doesNotThrow(() => helper.runInNewContext(context, {timeout: 1000}));
  assert.equal(calls.observers, 0);
  assert.equal(calls.writes, 0);
  assert.equal(windowProperties.__vibezRichRender, undefined);
  return calls;
}

for (const url of [
  'https://example.org/chat',
  'https://vibe.mistral.ai.example.org/chat',
  'https://chat.mistral.ai.example.org/chat',
  'https://vibe.mistral.ai@example.org/chat',
  'http://vibe.mistral.ai/chat',
]) {
  test(`rich rendering leaves an untrusted origin untouched: ${url}`, () => {
    // A copied fixture marker cannot grant a remote host rendering access.
    runGatedPage({url, fixture: true});
  });
}

for (const url of [
  'file:///tmp/synthetic-chat.html',
  'tauri://localhost/offline.html',
  'https://tauri.localhost/offline.html',
  'http://localhost:8765/chat',
  'http://127.0.0.1:8765/chat',
]) {
  test(`rich rendering leaves an unmarked local page untouched: ${url}`, () => {
    runGatedPage({url});
  });
}

test('rich rendering ignores subframes without inspecting their document', () => {
  const calls = runGatedPage({url: 'https://vibe.mistral.ai/', subframe: true});
  assert.equal(calls.attributeReads, 0);
});

for (const [name, capabilities] of [
  ['no CSS API', {css: false}],
  ['no content visibility', {unsupported: ['content-visibility']}],
  ['no intrinsic block size', {unsupported: ['contain-intrinsic-block-size']}],
  ['no ResizeObserver', {resizeObserver: false}],
  ['no MutationObserver', {mutationObserver: false}],
]) {
  test(`rich rendering leaves unsupported WebKit capabilities untouched: ${name}`, () => {
    runGatedPage({url: 'https://vibe.mistral.ai/', ...capabilities});
  });
}
