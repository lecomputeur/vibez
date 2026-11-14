const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const src = fs.readFileSync(require('node:path').join(__dirname, '../src-tauri/src/work_chat_authorize.js'), 'utf8');
const project = '2055311c-7cae-499c-b45b-f56f185f15da';
const connectorId = '3055311c-7cae-499c-b45b-f56f185f15da';
const chat = '4055311c-7cae-499c-b45b-f56f185f15da';
const title = 'vibezwork0123456789abcdef';
const connectorName = title + '_abcd';
const marker = '[VibeZ-work:' + 'a'.repeat(32) + ':' + project + ':' + title + ']';
const token = 'a'.repeat(56);
const POPUPS = '[role="dialog"],[role="alertdialog"],[role="menu"]';
const AUTH = '[role="dialog"],[role="alertdialog"]';
const authField = 'input[type="password"]';
const editorSelector = 'div.ProseMirror[contenteditable="true"]';
const plusSelector = 'button[data-coachmark-target="chat-input-settings"][aria-haspopup="dialog"]';
const leaf = (attrs = {}) => ({
  innerText: '', value: '', isConnected: true, nodes: {}, attrs: {},
  getAttribute(k) { return this.attrs[k]; },
  getClientRects() { return this.hidden ? [] : [{}]; },
  closest(s) { return this.nodes[s]; },
  querySelectorAll(s) { return this.nodes[s] ?? []; },
  contains(node) { return Object.values(this.nodes).some(e => Array.isArray(e) && e.includes(node)); },
  click() { this.clicked = (this.clicked ?? 0) + 1; this.onClick?.(); },
  dispatchEvent(event) { (this.events ??= []).push(event.type); this.onEvent?.(event); return true; },
  getBoundingClientRect() { return { x: 10, y: 10, width: 100, height: 20 }; },
  ...attrs,
});
const fixture = ({ alreadyAuthorized = false, closeAfterConnect = false, storage } = {}) => {
  const data = { project, connectorId, connectorName, marker, token, job: 'a'.repeat(32) };
  const loc = new URL('https://chat.mistral.ai/work/' + chat);
  data.url = loc.href;
  const form = leaf();
  const editorDesc = { node: { descendants: fn => atoms.forEach(fn), textContent: '' }, children: [] };
  const editorContains = [];
  const editor = leaf({ pmViewDesc: editorDesc, contains(node) { return editorContains.includes(node); } });
  const atoms = [];
  const plus = leaf(), search = leaf({ placeholder: 'Zoeken' });
  const settings = leaf(), picker = leaf(), auth = leaf({ innerText: title + connectorName + marker });
  const openConnectors = leaf({ innerText: 'Connectors' });
  const pickerRow = leaf({ innerText: title });
  const connect = leaf({ innerText: 'Verbinden' });
  const password = leaf({ id: 'header:authorization' });
  const bearer = leaf({ innerText: 'Bearer' });
  const doc = leaf();
  const unrelated = leaf({ innerText: 'Other dialog' });
  const setDialogs = (...dialogs) => { doc.nodes[POPUPS] = dialogs; doc.nodes[authField] = dialogs.includes(auth) ? [password] : []; };
  editor.nodes.form = form;
  doc.nodes[editorSelector] = [editor];
  form.nodes[plusSelector] = [plus];
  settings.nodes.button = [openConnectors];
  openConnectors.nodes[POPUPS] = settings;
  pickerRow.nodes[POPUPS] = picker;
  search.nodes[POPUPS] = picker;
  picker.nodes.input = [search];
  picker.nodes.button = [pickerRow];
  auth.nodes.button = [bearer, connect];
  password.nodes[AUTH] = auth;
  password.focus = () => { doc.activeElement = password; };
  password.blur = () => { doc.activeElement = null; };
  password.select = () => {};
  search.focus = () => { doc.activeElement = search; };
  doc.execCommand = (method, _, value) => {
    if (method === 'insertText') doc.activeElement.value = value;
    if (method === 'delete') doc.activeElement.value = '';
  };
  plus.onClick = () => setDialogs(settings);
  openConnectors.onClick = () => setDialogs(settings, picker);
  const workTag = { isInline: true, isAtom: true, type: {name:'slash'}, attrs: {
    slashType:'text-tag', subType:'connection', selectedValue:connectorId, selectedLabel:title,
  }};
  pickerRow.onClick = () => {
    if (!alreadyAuthorized) return setDialogs(settings, picker, auth);
    atoms.push(workTag);
    setDialogs();
  };
  connect.onClick = () => { alreadyAuthorized = true; closeAfterConnect ? setDialogs() : setDialogs(settings, picker); };
  const window = {}; window.top = window;
  const clock = { now: 0 };
  class MouseEvent { constructor(type, init) { this.type = type; Object.assign(this, init); } }
  class PointerEvent extends MouseEvent {}
  const fn = vm.runInNewContext(src, { location:loc, document:doc, window, Date: { now: () => clock.now }, MouseEvent, PointerEvent, sessionStorage: storage });
  const stage = (stage, overrides = {}) => { if (stage === 'reselect' && !overrides.noAdvance) clock.now += 5000; return fn({...data, ...overrides, stage}).state; };
  const reason = (stage, overrides = {}) => fn({...data, ...overrides, stage}).reason;
  const choose = () => {
    assert.equal(stage('open-menu'), 'advanced');
    assert.equal(stage('open-picker'), 'advanced');
    assert.equal(stage('choose'), 'advanced');
  };
  return { doc, editor, data, fn, openConnectors, stage, reason, choose, atoms, auth, password, plus, connect, setDialogs, unrelated, workTag, picker, settings, pickerRow, clock, leaf, editorDesc, editorContains, scope: { document: doc } };
};
{
  // Work opens the connector's own overview with "Verbinden" when the account
  // has not connected it yet. VibeZ confirms only that exact overview, once.
  const f = fixture();
  const overview = leaf({ innerText: title + ' Local files for Garden Planner ' + marker });
  const join = leaf({ innerText: 'Verbinden' });
  overview.nodes.button = [join];
  join.onClick = () => { f.atoms.push(f.workTag); f.setDialogs(); };
  f.pickerRow.onClick = () => f.setDialogs(f.settings, f.picker, overview);
  f.choose();
  assert.equal(f.reason('authorize'), 'connecting-connector');
  assert.equal(join.clicked, 1);
  assert.equal(f.stage('authorize'), 'selected');
  assert.equal(join.clicked, 1);
}
{
  // An overview without this folder's marker is never confirmed.
  const f = fixture();
  const other = leaf({ innerText: 'Another connector' });
  const join = leaf({ innerText: 'Verbinden' });
  other.nodes.button = [join];
  f.pickerRow.onClick = () => f.setDialogs(f.settings, f.picker, other);
  f.choose();
  assert.equal(f.reason('authorize'), 'no-password-dialog-open');
  assert.equal(join.clicked, undefined);
}
{
  // An unknown "Connect" label is reported, so VibeZ can retry in English.
  const f = fixture();
  const overview = leaf({ innerText: marker });
  const join = leaf({ innerText: 'Csatlakozás' });
  overview.nodes.button = [join];
  f.pickerRow.onClick = () => f.setDialogs(f.settings, f.picker, overview);
  f.choose();
  assert.equal(f.reason('authorize'), 'no-connect-button');
  assert.equal(join.clicked, undefined);
}
{
  const f = fixture(); f.choose();
  assert.equal(f.stage('authorize'), 'advanced');
  assert.equal(f.stage('confirm'), 'submitted');
  assert.equal(f.stage('confirm'), 'submitted');
  assert.equal(f.connect.clicked, 1);
  assert.equal(f.stage('reselect'), 'advanced');
  assert.equal(f.stage('selected'), 'selected');
}
{
  const f = fixture({alreadyAuthorized:true}); f.choose();
  assert.equal(f.stage('authorize'), 'selected');
  assert.equal(f.password.value, '');
}
{
  // Text the user already typed stays; the folder reference is added to it.
  const f = fixture(); f.atoms.push({isText:true,text:'existing draft'});
  assert.equal(f.stage('open-menu'), 'advanced');
  assert.equal(f.plus.clicked, 1);
}
{
  // A dialog VibeZ did not open is first closed with Escape, then reported.
  const f = fixture(); f.setDialogs(f.unrelated);
  for (let i = 0; i < 4; i++) assert.equal(f.reason('open-menu'), 'closing-foreign-dialog');
  assert.equal(f.stage('open-menu'), 'unexpected-dialog');
  assert.equal(f.plus.clicked, undefined);
}
{
  const f = fixture(); f.choose(); f.auth.innerText = 'another connector';
  assert.equal(f.stage('authorize'), 'unexpected-dialog');
  assert.equal(f.password.value, '');
}
{
  const f = fixture(); f.choose(); assert.equal(f.stage('authorize'), 'advanced');
  f.atoms.push({isText:true,text:'an unrelated draft'});
  assert.equal(f.stage('cancel', { token: 'b'.repeat(56) }), 'unexpected-dialog');
  assert.equal(f.stage('cancel'), 'cancelled');
  assert.equal(f.password.value, '');
  assert.equal(f.atoms[0].text, 'an unrelated draft');
  assert.equal(f.connect.clicked, undefined);
}
{
  const f = fixture();
  assert.equal(f.stage('open-menu', { url: 'https://chat.mistral.ai/work/' + project }), 'wrong-scope');
}
{
  // Work closes every menu after the Bearer dialog: reopen + > Connectors and pick the same row.
  const f = fixture({ closeAfterConnect: true }); f.choose();
  assert.equal(f.stage('authorize'), 'advanced');
  assert.equal(f.stage('confirm'), 'submitted');
  assert.equal(f.stage('reselect'), 'wait');
  assert.equal(f.plus.clicked, 2);
  assert.equal(f.stage('reselect'), 'wait');
  assert.equal(f.stage('reselect'), 'advanced');
  assert.equal(f.pickerRow.clicked, 2);
  assert.equal(f.stage('selected'), 'selected');
  assert.equal(f.atoms.length, 1);
}
{
  // A failed dialog check names the check, never page text or values.
  const f = fixture(); f.choose(); f.auth.innerText = title + connectorName;
  const result = (() => { const r = f.stage('authorize'); return r; })();
  assert.equal(result, 'unexpected-dialog');
  assert.equal(f.reason('authorize'), 'auth-marker');
  assert.equal(f.password.value, '');
}
{
  // This folder's reference next to typed text is already connected.
  const f = fixture(); f.atoms.push(f.workTag);
  f.atoms.push({isText:true,text:'user text'});
  assert.equal(f.stage('open-menu'), 'selected');
}
{
  // A reference to another VibeZ folder (the previous one, or the connector
  // replaced after a restart) is removed by its rendered element, even when
  // VibeZ hides that element on screen. Then the normal route continues.
  const f = fixture();
  const stale = { isInline: true, isAtom: true, type: {name:'slash'}, attrs: {
    slashType:'text-tag', subType:'connection', selectedValue:'6055311c-7cae-499c-b45b-f56f185f15da', selectedLabel:'vibezwork0123456789abcdef' }};
  f.atoms.push(stale);
  const chipDom = { isConnected: true, removed: 0, remove() { this.removed++; f.atoms.splice(f.atoms.indexOf(stale), 1); } };
  f.editorDesc.children = [{ node: stale, dom: chipDom, children: [] }];
  f.editorContains.push(chipDom);
  assert.equal(f.reason('open-menu'), 'removing-old-reference');
  assert.equal(chipDom.removed, 1);
  assert.equal(f.stage('open-menu'), 'advanced');
  assert.equal(f.plus.clicked, 1);
}
{
  // Without a reachable element, a draft holding only stale references is
  // cleared like Select All + Backspace; typed text is never cleared.
  const f = fixture();
  const stale = { isInline: true, isAtom: true, type: {name:'slash'}, attrs: {
    slashType:'text-tag', subType:'connection', selectedValue:'6055311c-7cae-499c-b45b-f56f185f15da', selectedLabel:'vibezwork0123456789abcdef' }};
  f.atoms.push(stale);
  f.editorDesc.node.textContent = '  ';
  const commands = [];
  f.scope.document.execCommand = (name, _, value) => { commands.push(name); if (name === 'delete') f.atoms.length = 0; };
  assert.equal(f.reason('open-menu'), 'clearing-stale-draft');
  assert.deepEqual(commands, ['selectAll', 'delete']);
  assert.equal(f.stage('open-menu'), 'advanced');
  const g = fixture();
  g.atoms.push(stale, { isText: true, text: 'typed' });
  g.editorDesc.node.textContent = 'typed';
  for (let i = 0; i < 6; i++) g.reason('open-menu');
  assert.equal(g.stage('open-menu'), 'blocked-draft');
  assert.equal(g.reason('open-menu'), 'other-folder-reference');
  assert.equal(g.plus.clicked, undefined);
}
{
  // Already authorized: Work inserts the reference but leaves its menus open.
  const f = fixture(); f.choose();
  f.atoms.push(f.workTag); f.setDialogs(f.settings, f.picker);
  f.plus.attrs['aria-expanded'] = 'true';
  f.plus.onClick = () => f.setDialogs();
  assert.equal(f.reason('authorize'), 'closing-menu');
  assert.equal(f.plus.clicked, 2);
  assert.equal(f.stage('authorize'), 'selected');
  assert.equal(f.password.value, '');
}
{
  // A composer holding only this exact reference is already connected.
  const f = fixture(); f.atoms.push(f.workTag);
  assert.equal(f.stage('open-menu'), 'selected');
  assert.equal(f.plus.clicked, undefined);
}
{
  // The same reference twice (after a page reload) is still one connection.
  const f = fixture(); f.atoms.push(f.workTag, f.workTag);
  assert.equal(f.stage('open-menu'), 'selected');
  assert.equal(f.plus.clicked, undefined);
}
{
  // Right after Verbinden the row is not clicked again.
  const f = fixture(); f.choose();
  assert.equal(f.stage('authorize'), 'advanced');
  assert.equal(f.stage('confirm'), 'submitted');
  assert.equal(f.reason('reselect'), 'settling');
  assert.equal(f.pickerRow.clicked, 1);
}
{
  // The Bearer dialog stays open after Verbinden: report names, then close it once.
  const f = fixture(); f.choose();
  const close = { innerText: 'Close', attrs: {}, getAttribute(k){return this.attrs[k];}, getClientRects(){return [{}];}, click(){ this.clicked=(this.clicked??0)+1; f.setDialogs(); } };
  f.auth.nodes.button.push(close);
  f.connect.onClick = () => {};
  assert.equal(f.stage('authorize'), 'advanced');
  assert.equal(f.stage('confirm'), 'submitted');
  assert.equal(f.reason('reselect'), 'auth-dialog-still-open');
  assert.equal(f.stage('reselect'), 'wait');
  assert.equal(close.clicked, undefined);
  assert.equal(f.stage('reselect'), 'wait');
  assert.equal(close.clicked, 1);
  assert.equal(f.password.value, '');
}
{
  // Work's own menus left open by an earlier attempt are closed, not treated as foreign.
  const f = fixture(); f.setDialogs(f.settings, f.picker);
  f.plus.attrs['aria-expanded'] = 'true'; f.plus.onClick = () => f.setDialogs();
  assert.equal(f.reason('open-menu'), 'closing-old-menu');
  assert.equal(f.plus.clicked, 1);
  f.plus.attrs['aria-expanded'] = 'false'; f.plus.onClick = () => f.setDialogs(f.settings);
  assert.equal(f.stage('open-menu'), 'advanced');
}
{
  // The chosen row inserted the connector this attempt replaced: the loaded
  // page's picker was stale (restart). Reported as a stale picker, so the
  // native side reloads and chooses again; never a blocked draft.
  const f = fixture({ alreadyAuthorized: true });
  f.pickerRow.onClick = () => { f.atoms.push({ isInline: true, isAtom: true, type: {name:'slash'}, attrs: {
    slashType:'text-tag', subType:'connection', selectedValue:'6055311c-7cae-499c-b45b-f56f185f15da', selectedLabel:title }}); f.setDialogs(); };
  f.choose();
  assert.equal(f.stage('authorize'), 'wait');
  assert.equal(f.reason('authorize'), 'stale-row-reference');
  assert.equal(f.stage('cancel'), 'cancelled');
}
console.log('Native Work authorization fixtures passed (18 cases)');
{
  // A picker row whose visible text is empty (its label hidden on screen) is still recognized by its text content.
  const f = fixture();
  f.pickerRow.innerText = ''; f.pickerRow.textContent = title;
  f.choose();
  assert.equal(f.pickerRow.clicked, 1);
}
{
  // A chip that names this connector by name or another handle instead of its UUID is ours.
  const f = fixture();
  f.atoms.push({ ...f.workTag, attrs: { ...f.workTag.attrs, selectedValue: connectorName } });
  assert.equal(f.stage('open-menu'), 'selected');
  const g = fixture();
  g.atoms.push({ ...g.workTag, attrs: { ...g.workTag.attrs, selectedValue: 'row-7' } });
  assert.equal(g.stage('open-menu'), 'selected');
}
{
  // The same label with a different connector UUID is a replaced connector: removed before linking.
  const f = fixture();
  const commands = [];
  f.scope.document.execCommand = method => commands.push(method);
  f.atoms.push({ ...f.workTag, attrs: { ...f.workTag.attrs, selectedValue: '5055311c-7cae-499c-b45b-f56f185f15da' } });
  assert.equal(f.reason('open-menu'), 'clearing-stale-draft');
  assert.deepEqual(commands, ['selectAll', 'delete']);
  assert.equal(f.plus.clicked, undefined);
}
{
  // In a wide window Mistral opens the Connectors list from the pointer, not
  // from a bare click: the attach step presses the item like a mouse does.
  const f = fixture();
  const opens = f.openConnectors.onClick;
  let pressed = false;
  f.openConnectors.onEvent = event => { if (event.type === 'pointerdown') pressed = true; };
  f.openConnectors.onClick = () => { if (pressed) opens(); };
  f.choose();
  assert.deepEqual(f.openConnectors.events.slice(-4), ['pointerdown', 'mousedown', 'pointerup', 'mouseup']);
  assert.equal(f.openConnectors.clicked, 1, 'one click after the pointer events, so a narrow window opens it as before');
}
{
  // The page is reloaded after 'cancel' (a connector enrolled moments ago is
  // missing from the loaded picker). The person's typed draft must come back
  // in the new document, once, and only for the same job and page.
  const store = new Map();
  const storage = { getItem: k => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k) };
  const f = fixture({ storage });
  f.editorDesc.node.content = { size: 10 };
  f.editorDesc.node.textBetween = () => 'Hello there\nsecond line';
  f.choose();
  assert.equal(f.stage('cancel'), 'cancelled');
  assert.equal(JSON.parse(store.get('vibez-work-draft')).text, 'Hello there\nsecond line');
  // New document: no menus, empty editor, the draft is typed back in.
  f.setDialogs();
  f.editorDesc.node.textBetween = () => '';
  const typed = [];
  f.doc.execCommand = (method, _, value) => { typed.push(value === undefined ? method : value); };
  assert.equal(f.reason('open-menu'), 'restoring-draft');
  assert.deepEqual(typed, ['Hello there', 'insertParagraph', 'second line']);
  assert.equal(store.has('vibez-work-draft'), false);
  f.editorDesc.node.textContent = 'Hello there second line';
  assert.equal(f.stage('open-menu'), 'advanced');
  assert.equal(typed.length, 3);
}
{
  // A kept draft from another job, or one that is too old, is dropped unused.
  const store = new Map();
  const storage = { getItem: k => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k) };
  const f = fixture({ storage });
  store.set('vibez-work-draft', JSON.stringify({ job: 'b'.repeat(32), url: f.data.url, text: 'other', at: 0 }));
  f.doc.execCommand = () => { throw new Error('must not type'); };
  assert.equal(f.stage('open-menu'), 'advanced');
  assert.equal(store.has('vibez-work-draft'), false);
  const g = fixture({ storage });
  g.clock.now = 200000;
  store.set('vibez-work-draft', JSON.stringify({ job: g.data.job, url: g.data.url, text: 'old', at: 0 }));
  g.doc.execCommand = () => { throw new Error('must not type'); };
  assert.equal(g.stage('open-menu'), 'advanced');
  // An empty composer at cancel removes nothing it did not keep.
  const h = fixture({ storage });
  h.editorDesc.node.content = { size: 0 };
  h.editorDesc.node.textBetween = () => '  ';
  h.choose();
  assert.equal(h.stage('cancel'), 'cancelled');
  assert.equal(store.has('vibez-work-draft'), false);
}
