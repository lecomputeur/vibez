'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const dir = path.resolve(__dirname, '..');
const read = f => fs.readFileSync(path.join(dir, f), 'utf8');
const toolbar = read('frontend/toolbar.js'), settings = read('frontend/settings.js');
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(r => resolve = r); return { promise, resolve }; }
function backend() { return { revision: 0, settings: { language: 'nl', zoom_factor: 1, show_screenshot: true, close_to_tray: false, start_at_login: false, auto_updates: true } }; }
function snapshot(b) { return structuredClone({ ...b, os_locale: 'nl-NL', version: '0.1.15', tray_ready: true, status: '', can_go_back: false, can_go_forward: false, loading: false }); }
function environment(b, opts = {}) {
  const elements = new Map(), intervals = [], calls = [];
  const get = id => {
    if (!elements.has(id)) elements.set(id, { value: '', textContent: '', disabled: false, hidden: false, checked: false, children: [], listeners: {}, classList: { toggle(){} }, appendChild(e){this.children.push(e);}, setAttribute(){}, focus(){}, select(){}, addEventListener(name, f){this.listeners[name] = f;} });
    return elements.get(id);
  };
  const screenshotModes = ['full_page','visible','selection'].map(mode => ({
    dataset: { screenshotMode: mode }, disabled: false, listeners: {},
    addEventListener(name, fn){ this.listeners[name] = fn; }, focus(){}
  }));
  let held;
  const context = {
    navigator: { clipboard: { writeText: async () => {} } },
    document: {
      getElementById: get, createElement: () => ({}), addEventListener(){},
      querySelector: selector => selector === '.screenshot-control' ? ({ contains: () => true }) : null,
      querySelectorAll: selector => selector === '[data-screenshot-mode]' ? screenshotModes : []
    },
    setInterval: f => intervals.push(f),
    preview: { data: { options: [{code:'system',name:'System'},{code:'nl',name:'Nederlands'},{code:'en',name:'English'}],
      translations: { nl: { updateStarted: 'Updatecontrole gestart.' }, en: { updateStarted: 'Update check started.' } } },
      localize(){}, resolve: (s, os) => s === 'system' ? os.split('-')[0] : s, extra: k => k, errorText: e => String(e), currentLanguage: () => 'nl',
      invoke: async (command, args) => {
        if (command === 'get_state') { if (held) { const h = held; held = null; return h.promise; } return snapshot(b); }
        if (command === 'get_diagnostics') { if (opts.diagnosticsError) throw Error('diagnostics offline'); return 'diagnostics'; }
        if (command === 'capture_screenshot') { calls.push({ command, args: structuredClone(args) }); return true; }
        if (command === 'save_settings') {
          calls.push(structuredClone(args)); assert.equal(args.settings, undefined, 'must send patches, never a whole stale form');
          for (const [key, value] of Object.entries(args.patch)) {
            if (b.settings[key] !== value && args.expected[key] !== b.settings[key]) throw 'settings_conflict';
          }
          Object.assign(b.settings, args.patch); ++b.revision;
          return structuredClone({ settings: b.settings, revision: b.revision });
        }
        return true;
      }
    }
  };
  return { get, intervals, calls, run: s => vm.runInNewContext(s, context), hold: () => { held = deferred(); return held; } };
}
test('diagnostic parser reads the actual cookie in any pair position', () => {
  const script = read('src-tauri/src/site_diagnostics.js');
  for (const cookie of ['NEXT_LOCALE=en', 'theme=light; NEXT_LOCALE=en', 'a=1;NEXT_LOCALE=en;b=2', 'NEXT_LOCALE=%65n']) {
    const result = vm.runInNewContext(script, {document: {cookie,documentElement:{lang:'en'}}, navigator:{language:'en'},location:{hostname:'chat.mistral.ai'}});
    assert.match(result, /document-cookie=en;/);
  }
});
test('old settings window changing only zoom preserves a newer toolbar language', async () => {
  const b = backend(), panel = environment(b), bar = environment(b);
  await panel.run(settings); bar.run(toolbar); await flush();
  bar.get('quick-language').value = 'en'; await bar.get('quick-language').listeners.change();
  panel.get('zoom').value = '1.25'; await panel.get('preferences').listeners.submit({preventDefault(){}});
  assert.equal(b.settings.language, 'en'); assert.equal(b.settings.zoom_factor, 1.25);
  assert.deepEqual(panel.calls[0].patch, {zoom_factor: 1.25});
});
test('poll started before a successful write cannot roll toolbar back', async () => {
  const b = backend(), bar = environment(b); bar.run(toolbar); await flush();
  const old = snapshot(b), held = bar.hold(); const poll = bar.intervals[0]();
  bar.get('quick-language').value = 'en'; await bar.get('quick-language').listeners.change();
  held.resolve(old); await poll;
  assert.equal(b.settings.language, 'en'); assert.equal(bar.get('language-code').textContent, 'EN');
});
test('failed diagnostics never disables preference editing or saving', async () => {
  const b = backend(), panel = environment(b, {diagnosticsError:true});
  await panel.run(settings); await flush();
  assert.equal(panel.get('save').disabled, false);
  panel.get('zoom').value = '1.5'; await panel.get('preferences').listeners.submit({preventDefault(){}});
  assert.equal(b.settings.zoom_factor, 1.5);
});
test('same-field conflict loads the new value instead of overwriting it', async () => {
  const b = backend(), panel = environment(b); await panel.run(settings);
  panel.get('language').value = 'de'; b.settings.language = 'en'; ++b.revision;
  await panel.get('preferences').listeners.submit({preventDefault(){}});
  assert.equal(b.settings.language, 'en'); assert.equal(panel.get('language').value, 'en');
  assert.match(panel.get('result').textContent, /settings_conflict/);
});
test('settings refresh follows new untouched fields but keeps a dirty field', async () => {
  const b = backend(), panel = environment(b); await panel.run(settings);
  panel.get('zoom').value = '1.25'; b.settings.language = 'en'; ++b.revision;
  await panel.intervals[0]();
  assert.equal(panel.get('language').value, 'en'); assert.equal(panel.get('zoom').value, '1.25');
});

test('automatic update preference is editable and Check now invokes the native checker', async () => {
  const b = backend(), panel = environment(b); await panel.run(settings); await flush();
  assert.equal(panel.get('auto-updates').checked, true);
  panel.get('auto-updates').checked = false;
  await panel.get('preferences').listeners.submit({preventDefault(){}});
  assert.equal(b.settings.auto_updates, false);
  await panel.get('check-updates').listeners.click();
  assert.equal(panel.get('result').textContent, 'Updatecontrole gestart.');
});

test('screenshot menu exposes full page, visible page and selection modes', async () => {
  const b = backend(), bar = environment(b); bar.run(toolbar); await flush();
  const panel = bar.get('screenshot-panel');
  panel.hidden = true;
  bar.get('screenshot').listeners.click();
  assert.equal(panel.hidden, false);
  // Invoke the three menu handlers in the order they are declared by the toolbar.
  const modes = ['full_page','visible','selection'];
  const modeButtons = [];
  // The environment records capture calls when each menu item is clicked.
  // Re-evaluate through the document mock's stable mode elements by exposing their handlers indirectly:
  // use the first/second/third capture calls generated by synthetic menu item clicks.
  const script = `document.querySelectorAll('[data-screenshot-mode]').forEach(b => b.listeners.click())`;
  await bar.run(`Promise.all([...document.querySelectorAll('[data-screenshot-mode]')].map(b => b.listeners.click()))`);
  const captures = bar.calls.filter(c => c.command === 'capture_screenshot');
  assert.deepEqual(captures.map(c => c.args.mode).sort(), modes.sort());
});
