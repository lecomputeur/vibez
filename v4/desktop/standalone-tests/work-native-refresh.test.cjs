const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');

const source = readFileSync(require('node:path').resolve(__dirname, '../src-tauri/src/work_native_refresh.js'), 'utf8');
const name = 'vibezwork3c41fa29b80b42df_9228';
const STALE = 'We kunnen de connector niet bereiken. Controleer de status van uw server en verbind opnieuw.\n' +
  'Verbindingen\nGeen authenticatie nodig\nTools\nOpnieuw verbinden om tools te gebruiken';
const FRESH = 'Verbindingen\nGeen authenticatie nodig\nTools\nInteractief\nWrite File\nRead File\nCreate Document';

class Node {
  constructor(innerText = '', attributes = {}) {
    this.innerText = innerText;
    this.attributes = attributes;
    this.children = {};
    this.clicks = 0;
    this.pointerdowns = 0;
    this.type = attributes.type || '';
    this.value = attributes.value || '';
    this.disabled = false;
  }
  getAttribute(key) { return this.attributes[key] ?? null; }
  querySelectorAll(selector) { return this.children[selector] || []; }
  querySelector(selector) { return (this.children[selector] || [])[0] || null; }
  getClientRects() { return this.hidden ? [] : [{}]; }
  click() { this.clicks += 1; }
  dispatchEvent(event) { if (event.type === 'pointerdown') this.pointerdowns += 1; }
}

function fixture(text) {
  const document = new Node();
  const main = new Node(text);
  const heading = new Node('vibezwork3c41fa29b80b42df');
  const moreTop = new Node('', { 'aria-label': 'Meer acties' });
  const moreRow = new Node('', { 'aria-label': 'Meer acties' });
  main.children.button = [moreTop, moreRow];
  document.children.h1 = [heading];
  document.children.main = [main];
  const clock = { now: 1_000_000 };
  const window = {};
  window.top = window;
  const context = {
    document, window, location: { pathname: '/connections/' + name, search: '', hash: '' },
    Date: { now: () => clock.now }, PointerEvent: class { constructor(type) { this.type = type; } },
  };
  const run = vm.runInNewContext('(' + source.trim() + ')', context);
  return { document, main, moreRow, clock, step: () => JSON.parse(JSON.stringify(run({ name }))) };
}

test('reachable connector page with tool titles is accepted at once', () => {
  const f = fixture(FRESH);
  assert.equal(f.step().state, 'ok');
});

test('stale connector is reconnected through the row menu and its save button', () => {
  const f = fixture(STALE);
  assert.deepEqual(f.step(), { state: 'wait', reason: 'opening' });
  assert.equal(f.moreRow.pointerdowns, 1);
  const item = new Node('Opnieuw verbinden');
  f.document.children['[role=menuitem]'] = [item];
  f.clock.now += 500;
  assert.deepEqual(f.step(), { state: 'wait', reason: 'menu' });
  assert.equal(item.clicks, 1);
  f.document.children['[role=menuitem]'] = [];
  const dialog = new Node('Voeg een andere verbinding toe');
  const save = new Node('Opslaan');
  dialog.children.button = [new Node('Annuleren'), save];
  dialog.children.input = [new Node('', { type: 'text', value: 'default' })];
  f.document.children['[role=dialog],[role=alertdialog]'] = [dialog];
  assert.deepEqual(f.step(), { state: 'wait', reason: 'saving' });
  assert.equal(save.clicks, 1);
  f.document.children['[role=dialog],[role=alertdialog]'] = [];
  f.main.innerText = FRESH;
  // The caller is told a reconnect happened: it loads the chat page afresh.
  assert.deepEqual(f.step(), { state: 'ok', reason: 'reconnected' });
});

test('a key field means the connector is not the open kind and nothing is filled in', () => {
  const f = fixture(STALE);
  f.document.children['input[type=password]'] = [new Node('', { type: 'password' })];
  assert.equal(f.step().state, 'auth-required');
});

test('page without stale notice and without tool titles is accepted only after 4 s', () => {
  const f = fixture('Verbindingen\nGeen authenticatie nodig\nTools');
  assert.deepEqual(f.step(), { state: 'wait', reason: 'checking' });
  f.clock.now += 3000;
  assert.deepEqual(f.step(), { state: 'wait', reason: 'checking' });
  f.clock.now += 1500;
  assert.deepEqual(f.step(), { state: 'ok', reason: 'not-stale' });
});

test('late stale notice restarts the wait and leads to a reconnect', () => {
  const f = fixture('Verbindingen\nGeen authenticatie nodig\nTools');
  f.step();
  f.clock.now += 3000;
  f.main.innerText = STALE;
  assert.deepEqual(f.step(), { state: 'wait', reason: 'opening' });
});

test('other pages and names are refused', () => {
  const f = fixture(FRESH);
  assert.equal(vm.runInNewContext('(' + source.trim() + ')', {})({ name: 'github_1234' }).state, 'invalid-input');
});

test('half-loaded stale page waits for its connection section instead of giving up', () => {
  const f = fixture('We kunnen de connector niet bereiken. Controleer de status van uw server en verbind opnieuw.');
  assert.deepEqual(f.step(), { state: 'wait', reason: 'checking' });
  f.clock.now += 2000;
  assert.deepEqual(f.step(), { state: 'wait', reason: 'checking' });
  f.main.innerText = STALE;
  assert.deepEqual(f.step(), { state: 'wait', reason: 'opening' });
  assert.equal(f.moreRow.pointerdowns, 1);
});

test('stale page that never shows the open connection kind is reported after 8 s', () => {
  const f = fixture('We kunnen de connector niet bereiken. Controleer de status van uw server en verbind opnieuw.');
  f.step();
  f.clock.now += 8500;
  assert.deepEqual(f.step(), { state: 'auth-required', reason: 'not-open-connector' });
});

test('stale connector page in English (as Mistral shows it in the hidden view) is recognised and reconnected', () => {
  // Wording measured live: the English page says "No auth needed".
  const f = fixture('We cannot reach the connector. Please check the status of your server and reconnect.\n' +
    'Connections\nNo auth needed\nTools\nReconnect to use tools\nReconnect this connector to view and manage the tools you can use.');
  f.main.children.button.forEach(b => { b.attributes['aria-label'] = 'More actions'; });
  assert.deepEqual(f.step(), { state: 'wait', reason: 'opening' });
  assert.equal(f.moreRow.pointerdowns, 1);
});

test('a reconnect form that stays open after Save is given up after 8 s, so the connector is replaced', () => {
  // Measured live after five minutes of downtime: the form stayed open for 90 s.
  const f = fixture(STALE);
  f.step();
  f.document.children['[role=menuitem]'] = [new Node('Opnieuw verbinden')];
  f.clock.now += 500;
  f.step();
  f.document.children['[role=menuitem]'] = [];
  const dialog = new Node('Voeg een andere verbinding toe');
  dialog.children.button = [new Node('Annuleren'), new Node('Opslaan')];
  dialog.children.input = [new Node('', { type: 'text', value: 'default' })];
  f.document.children['[role=dialog],[role=alertdialog]'] = [dialog];
  assert.deepEqual(f.step(), { state: 'wait', reason: 'saving' });
  f.clock.now += 7000;
  assert.deepEqual(f.step(), { state: 'wait', reason: 'connecting' });
  f.clock.now += 1500;
  assert.deepEqual(f.step(), { state: 'reconnect-failed', reason: 'save-stuck' });
});
