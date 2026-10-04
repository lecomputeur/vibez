'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const dir = path.resolve(__dirname, '..');
const read = f => fs.readFileSync(path.join(dir,f),'utf8');
const config = JSON.parse(read('src-tauri/tauri.conf.json'));
const cap = JSON.parse(read('src-tauri/capabilities/local-shell.json'));
test('preview identity and versions stay separate from Electron', () => {
  assert.equal(config.identifier,'nl.lecomputeur.vibez.tauri.preview');
  assert.equal(config.productName,'VibeZ Tauri Preview'); assert.equal(config.mainBinaryName,'vibez-tauri-preview');
  assert.equal(config.version,'0.1.17'); assert.equal(JSON.parse(read('package.json')).version,config.version);
  assert.match(read('src-tauri/Cargo.toml'),/version = "0\.1\.17"/);
});
test('native capabilities belong only to bundled controls, not remote content', () => {
  assert.deepEqual(cap.webviews,['shell','settings']); assert.equal(cap.local,true);
  assert.equal(cap.remote,undefined); assert.equal(cap.windows,undefined);
  assert.ok(cap.permissions.every(p=>p.startsWith('allow-')));
  assert.match(config.app.security.csp,/frame-src 'none'/);
  assert.doesNotMatch(read('frontend/index.html'),/<iframe|https:\/\/vibe/);
});
test('no production updater, URL protocol or Store identity is introduced', () => {
  assert.equal(config.plugins,undefined); assert.deepEqual(config.bundle.targets,['deb']);
  assert.doesNotMatch(read('src-tauri/Cargo.toml'),/electron|tauri-plugin-updater|tauri-plugin-deep-link/);
  assert.doesNotMatch(read('src-tauri/src/main.rs'),/["']com\.vibez\.app|["']vibez\.desktop|LeComputeur\.VibeZDesktop/);
  assert.match(read('scripts/build-windows-store-preview.ps1'),/LeComputeur\.VibeZTauriPreview/);
  assert.doesNotMatch(read('scripts/build-windows-store-preview.ps1'),/9NR7L2G4MS08/);
});
test('all frontend scripts parse without Electron', () => {
  for(const f of ['common.js','toolbar.js','settings.js']) new vm.Script(read(`frontend/${f}`));
});
test('prepared assets retain the logo and all 34 complete translation bundles', () => {
  execFileSync(process.execPath,[path.join(dir,'scripts/prepare.cjs')]);
  assert.deepEqual(fs.readFileSync(path.join(dir,'dist/icon.png')),fs.readFileSync(path.join(dir,'../icon.png')));
  assert.equal(read('dist/shell.css'),fs.readFileSync(path.join(dir,'../shell.css'),'utf8'));
  const base=JSON.parse(read('dist/translations.json')).translations;
  const extra=JSON.parse(read('dist/preview-translations.json')).translations;
  assert.equal(Object.keys(base).length,34); assert.deepEqual(Object.keys(base).sort(),Object.keys(extra).sort());
  const keys=Object.keys(extra.en).sort();
  for(const [code,strings] of Object.entries(extra)) {
    assert.deepEqual(Object.keys(strings).sort(),keys,code);
    assert.ok(keys.every(k=>typeof strings[k]==='string'&&strings[k].trim()),code);
  }
});
test('system language resolution retains Dutch and Chinese behavior', () => {
  const context={window:{VIBEZ_TRANSLATIONS:JSON.parse(read('dist/translations.json'))}};
  vm.createContext(context); vm.runInContext(read('frontend/common.js'),context);
  const resolve=context.window.preview.resolve;
  assert.equal(resolve('system','nl_NL.UTF-8'),'nl'); assert.equal(resolve('system','zh-Hant-TW'),'zh-TW');
  assert.equal(resolve('fr','nl_NL'),'fr'); assert.equal(resolve('system','xx_YY'),'en');
});
test('related OAuth popups keep opener callbacks without credential interception', () => {
  const auth=read('src-tauri/src/auth.rs'), smoke=read('src-tauri/src/smoke.rs');
  assert.match(auth,/\.window_features\(features\)/); assert.match(auth,/NewWindowResponse::Create/);
  assert.match(auth,/create_auth_window\(&nested_app, next, nested_features, true\)/);
  assert.doesNotMatch(auth,/\.user_agent\(|\.initialization_script\(|\.cookies\(|\.set_cookie\(|ignore_certificate/);
  assert.match(smoke,/window\.opener\.postMessage/); assert.match(smoke,/Nested popup was granted native command access/);
  assert.match(auth,/if auth_chain_allowed\(next, smoke\) \{ return true; \}/);
});
test('manual update feed validates successful independent preview artifacts', () => {
  const source=read('src-tauri/src/preview_updates.rs');
  assert.match(source,/run\["conclusion"\] != "success"/); assert.match(source,/entry\["expired"\] != false/);
  assert.match(source,/const BRANCH: &str = "vibe\/tauri-linux-preview-7c4e90"/);
  assert.doesNotMatch(source,/Command::new|reqwest::blocking|danger_accept_invalid_certs|\.bearer_auth\(/);
  assert.doesNotMatch(read('src-tauri/build.rs'),/preview_updates|check_updates/);
});
test('native routing does not reintroduce injected opener interception', () => {
  const main=read('src-tauri/src/main.rs');
  assert.match(main,/open_js_links_on_click\(false\)/); assert.match(main,/"main-open-external"/);
  assert.match(main,/auth::active\(&handle\) && policy::auth_chain_url\(url\)/);
  assert.match(main,/policy::auth_return_url\(url\)/); assert.match(main,/link_probe::start/);
  assert.match(read('src-tauri/src/link_probe.rs'),/native,native,native/);
});
test('language transactions are revisioned and deferred outside content', () => {
  const main=read('src-tauri/src/main.rs'), lang=read('src-tauri/src/site_language.rs');
  assert.match(lang,/gate: tokio::sync::Mutex/); assert.match(lang,/completed: AtomicU64/);
  assert.match(lang,/set_preferred_languages/); assert.match(lang,/cookies_for_url/);
  assert.match(lang,/policy::auth_return_url/); assert.match(main,/site_language::request/);
  assert.doesNotMatch(main,/from_millis\(350\)|Language saved; Mistral/);
});
test('Windows system locale still means the Windows display language', () => {
  assert.match(read('src-tauri/src/main.rs'),/GetUserDefaultUILanguage/);
  assert.match(read('src-tauri/Cargo.toml'),/Win32_Globalization/);
  assert.match(read('frontend/toolbar.js'),/AUTO·/);
});
test('Linux layout never raises the parent minimum or shows hidden windows', () => {
  const source=read('src-tauri/src/native_layout.rs');
  assert.match(source,/gtk::Layout/); assert.doesNotMatch(source,/window\.show\(|surface\.set_size_request\(/);
  assert.match(read('src-tauri/src/smoke.rs'),/RESIZE_OK: requested=/);
  assert.match(read('src-tauri/src/smoke.rs'),/HIDDEN_OK:/);
});
test('launcher identity, icon and package compatibility remain explicit', () => {
  assert.equal(config.app.enableGTKAppId,true);
  assert.equal(config.bundle.linux.deb.files['/usr/share/applications/nl.lecomputeur.vibez.tauri.preview.desktop'],'linux/nl.lecomputeur.vibez.tauri.preview.desktop');
  assert.equal(config.bundle.linux.deb.files['/usr/share/icons/hicolor/512x512/apps/nl.lecomputeur.vibez.tauri.preview.png'],'icons/icon.png');
  assert.match(read('src-tauri/linux/nl.lecomputeur.vibez.tauri.preview.desktop'),/^StartupWMClass=nl\.lecomputeur\.vibez\.tauri\.preview$/m);
  assert.match(read('src-tauri/linux/hidden-generated.desktop.hbs'),/^NoDisplay=true$/m);
  assert.ok(config.bundle.linux.deb.depends.includes('libc6 (>= 2.39)'));
});
