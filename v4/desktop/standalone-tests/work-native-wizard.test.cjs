const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');

const source = readFileSync(require('node:path').resolve(__dirname, '../src-tauri/src/work_native_wizard.js'), 'utf8');
const id = 'e2e933ff-6268-4985-bd6f-ef66d046ffba';
const input = {
  origin: 'https://chat.mistral.ai', title: 'VibeZ Work 124', slugPrefix: 'vibez_work_124',
  description: 'VibeZ private test 124',
  endpoint: 'https://test-124.trycloudflare.com/mcp/' + id + '/' + 'S3cr3t_-'.repeat(6),
};
const detailPath = '/connections/vibez_work_124_d2a1';

class Node {
  constructor(innerText = '', attributes = {}) {
    this.innerText = innerText;
    this.value = '';
    this.attributes = attributes;
    this.children = {};
    this.clicks = 0;
  }
  getAttribute(key) { return this.attributes[key]; }
  setAttribute(key, value) { this.attributes[key] = value; }
  hasAttribute(key) { return Object.hasOwn(this.attributes, key); }
  querySelectorAll(selector) { return this.children[selector] || []; }
  getClientRects() { return this.hidden ? [] : [{}]; }
  click() { this.clicks += 1; }
  dispatchEvent() { this.setAttribute('aria-expanded', 'true'); }
  closest() { return this.main; }
  focus() { focused = this; }
  select() {}
  blur() { focused = null; }
}
let focused = null;

function fixture() {
  const document = new Node();
  document.execCommand = (command, _, value) => {
    assert.equal(command, 'insertText');
    focused.value = value;
    return true;
  };
  const window = {};
  window.top = window;
  const url = new URL(input.origin + '/connections');
  const clock = { now: 1_000_000 };
  const scope = { window, document, URLSearchParams, PointerEvent: class {}, location: url,
    FocusEvent: class { constructor(type) { this.type = type; } }, Event: class { constructor(type) { this.type = type; } },
    Date: { now: () => clock.now } };
  const step = vm.runInNewContext(source, scope);
  const run = (stage, extra = {}) => JSON.parse(JSON.stringify(step({ ...input, stage, ...extra })));

  const menuButton = new Node('Nieuwe connector');
  const formEntry = new Node('Aangepaste connector toevoegen');
  const formHeading = new Node('Aangepaste connector toevoegen');
  const dialog = new Node();
  const form = new Node();
  const fields = {
    title: new Node(), endpoint: new Node(), description: new Node(),
  };
  const submit = new Node('Connector toevoegen');
  const auth = new Node('Automatisch detecteren');
  const heading = new Node(input.title);
  const main = new Node(input.description);
  const tryNow = new Node('Probeer nu');
  const share = new Node('Share');
  heading.main = main;
  main.children = { button: [tryNow, share] };
  document.children = {
    'button[aria-haspopup=menu]': [menuButton], '[role=menuitem]': [formEntry],
    '[role=dialog]': [dialog], 'h1': [heading],
  };
  dialog.children = { 'h1,h2,h3,[role=heading]': [formHeading], form: [form] };
  form.children = {
    'input[name=title][type=text]': [fields.title], 'input#server[name=server]': [fields.endpoint],
    'input#description[name=description]': [fields.description], 'input[type=password]': [],
    'button[type=submit]': [submit], button: [submit, auth], 'button,[role=combobox]': [submit, auth],
  };
  return { run, scope, url, clock, form, dialog, fields, menuButton, formEntry, submit, auth, tryNow, share };
}

test('handles the no-key wizard and returns only the exact Work identity', () => {
  const f = fixture();
  for (const stage of ['open-menu', 'open-form', 'title', 'endpoint', 'description']) assert.equal(f.run(stage).state, 'advanced');
  assert.equal(f.formEntry.clicks, 1);
  assert.equal(f.fields.endpoint.value, input.endpoint);
  // Mistral is still detecting: nudge the address once, wait, and never
  // submit early. The nudge repeats at most every 3 s.
  assert.deepEqual(f.run('auth'), { state: 'wait', reason: 'detect-kick' });
  assert.deepEqual(f.run('submit'), { state: 'wait', reason: 'detecting' });
  f.clock.now += 3_100;
  assert.deepEqual(f.run('auth'), { state: 'wait', reason: 'detect-kick' });
  assert.deepEqual(f.run('auth'), { state: 'wait', reason: 'detecting' });
  assert.equal(f.submit.clicks, 0);
  f.auth.innerText = 'Geen authenticatie';
  assert.deepEqual(f.run('auth'), { state: 'advanced' });
  assert.deepEqual(f.run('submit'), { state: 'submitted' });
  assert.deepEqual(f.run('submit'), { state: 'submitted' });
  assert.equal(f.submit.clicks, 1);
  f.url.pathname = detailPath;
  assert.deepEqual(f.run('detail'), { state: 'detail', path: detailPath });
  assert.equal(f.tryNow.clicks, 0);
  assert.equal(f.share.clicks, 0);
  f.url.pathname = '/work';
  assert.deepEqual(f.run('detail'), { state: 'wrong-page' });
});

test('a key, OAuth or API-token form is reported and never filled in or submitted', () => {
  for (const label of ['API-token authenticatie', 'OAuth2.1']) {
    const f = fixture();
    for (const stage of ['open-menu', 'open-form', 'title', 'endpoint', 'description']) f.run(stage);
    f.auth.innerText = label;
    assert.deepEqual(f.run('auth'), { state: 'auth-required' }, label);
    assert.deepEqual(f.run('submit'), { state: 'auth-required' }, label);
    assert.equal(f.submit.clicks, 0);
  }
  const f = fixture();
  for (const stage of ['open-menu', 'open-form', 'title', 'endpoint', 'description']) f.run(stage);
  f.auth.innerText = 'Geen authenticatie';
  const key = new Node();
  key.type = 'password';
  f.form.children['input[type=password]'] = [key];
  assert.deepEqual(f.run('submit'), { state: 'auth-required' });
  assert.equal(key.value, '');
  assert.equal(f.submit.clicks, 0);
});

test('wrong origin, other forms and other connectors cannot be submitted', () => {
  const f = fixture();
  f.scope.location = new URL('https://example.com/connections');
  assert.deepEqual(f.run('auth'), { state: 'wrong-origin' });
  f.scope.location = f.url;
  for (const stage of ['title', 'endpoint', 'description']) assert.equal(f.run(stage).state, 'advanced');
  f.auth.innerText = 'Geen authenticatie';
  f.fields.endpoint.value = 'https://unrelated.trycloudflare.com/mcp/' + id;
  assert.deepEqual(f.run('auth'), { state: 'unexpected-form' });
  assert.deepEqual(f.run('submit'), { state: 'unexpected-form' });
  assert.equal(f.submit.clicks, 0);
  f.url.pathname = '/connections/another_project_aaaa';
  assert.deepEqual(f.run('detail'), { state: 'wrong-page' });
  assert.equal(f.tryNow.clicks, 0);
});

test('an address outside the Cloudflare test tunnel is refused before any step', () => {
  const f = fixture();
  assert.deepEqual(f.run('open-menu', { endpoint: 'https://example.com/mcp/' + id }), { state: 'invalid-input' });
  assert.equal(f.menuButton.clicks, 0);
});

test('a Polish site language is recognised by structure and connector words', () => {
  const f = fixture();
  f.menuButton.innerText = 'Nowy konektor';
  f.formEntry.innerText = 'Dodaj niestandardowy konektor';
  f.submit.innerText = 'Dodaj konektor';
  f.auth.innerText = 'Wykryj automatycznie';
  // The dialog heading is translated: its own address field identifies it.
  f.dialog.children['h1,h2,h3,[role=heading]'][0].innerText = 'Dodaj niestandardowy konektor';
  f.dialog.children['input#server[name=server]'] = [f.fields.endpoint];
  for (const stage of ['open-menu', 'open-form', 'title', 'endpoint', 'description']) assert.equal(f.run(stage).state, 'advanced', stage);
  assert.equal(f.formEntry.clicks, 1);
  assert.deepEqual(f.run('submit'), { state: 'wait', reason: 'detect-kick' });
  assert.deepEqual(f.run('submit'), { state: 'wait', reason: 'detecting' });
  f.auth.innerText = 'Brak uwierzytelniania';
  assert.deepEqual(f.run('auth'), { state: 'advanced' });
  assert.deepEqual(f.run('submit'), { state: 'submitted' });
  assert.equal(f.submit.clicks, 1);
});

test('a translated key form is still refused', () => {
  const f = fixture();
  for (const stage of ['open-menu', 'open-form', 'title', 'endpoint', 'description']) f.run(stage);
  f.auth.innerText = 'Uwierzytelnianie tokenem API';
  assert.deepEqual(f.run('submit'), { state: 'auth-required' });
  assert.equal(f.submit.clicks, 0);
});

test('two candidate menus or entries are never guessed between', () => {
  const f = fixture();
  f.menuButton.innerText = 'Nowy konektor';
  const other = new Node('Filtruj konektory');
  f.scope.document.children['button[aria-haspopup=menu]'] = [f.menuButton, other];
  assert.deepEqual(f.run('open-menu'), { state: 'wait' });
  f.scope.document.children['button[aria-haspopup=menu]'] = [f.menuButton];
  assert.equal(f.run('open-menu').state, 'advanced');
  f.formEntry.innerText = 'Dodaj niestandardowy konektor';
  f.scope.document.children['[role=menuitem]'] = [f.formEntry, new Node('Własny serwer MCP')];
  assert.deepEqual(f.run('open-form'), { state: 'wait' });
  assert.equal(f.formEntry.clicks, 0);
});
