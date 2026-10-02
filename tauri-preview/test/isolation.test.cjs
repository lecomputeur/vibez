'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');
const dir = path.resolve(__dirname, '..');
const read = name => fs.readFileSync(path.join(dir, name), 'utf8');
const config = JSON.parse(read('src-tauri/tauri.conf.json'));
const cap = JSON.parse(read('src-tauri/capabilities/local-shell.json'));

test('preview has an independent identity, executable and version', () => {
  assert.equal(config.identifier, 'nl.lecomputeur.vibez.tauri.preview');
  assert.equal(config.mainBinaryName, 'vibez-tauri-preview');
  assert.equal(config.version, '0.1.10');
  assert.equal(config.productName, 'VibeZ Tauri Preview');
  assert.equal(JSON.parse(read('package.json')).version, config.version);
  assert.match(read('src-tauri/Cargo.toml'), /version = "0\.1\.10"/);
});
test('remote website and auth popups have no native capabilities or iframe bridge', () => {
  assert.deepEqual(cap.webviews, ['shell', 'settings']);
  assert.equal(cap.local, true);
  assert.equal(cap.remote, undefined);
  assert.equal(cap.windows, undefined);
  assert.ok(cap.permissions.every(p => p.startsWith('allow-')));
  assert.match(config.app.security.csp, /frame-src 'none'/);
  assert.doesNotMatch(read('frontend/index.html'), /<iframe|https:\/\/vibe/);
});
test('no production updater, protocol registration or store target is enabled', () => {
  assert.equal(config.plugins, undefined);
  assert.deepEqual(config.bundle.targets, ['deb']);
  const cargo = read('src-tauri/Cargo.toml');
  assert.doesNotMatch(cargo, /electron|tauri-plugin-updater|tauri-plugin-deep-link/);
  assert.doesNotMatch(read('src-tauri/src/main.rs'), /["']com\.vibez\.app|["']vibez\.desktop|LeComputeur\.VibeZDesktop/);
});
test('all frontend scripts parse without requiring an Electron runtime', () => {
  for (const filename of ['common.js','toolbar.js','settings.js']) new vm.Script(read(`frontend/${filename}`));
});
test('prepared assets reuse the existing logo and toolbar without modifying them', () => {
  execFileSync(process.execPath, [path.join(dir, 'scripts/prepare.cjs')]);
  assert.deepEqual(fs.readFileSync(path.join(dir,'dist/icon.png')), fs.readFileSync(path.join(dir,'../icon.png')));
  assert.equal(read('dist/shell.css'), fs.readFileSync(path.join(dir,'../shell.css'),'utf8'));
  const data = JSON.parse(read('dist/translations.json'));
  assert.equal(Object.keys(data.translations).length, 34);
  const previewData = JSON.parse(read('dist/preview-translations.json'));
  assert.deepEqual(Object.keys(previewData.translations).sort(), Object.keys(data.translations).sort());
  const keys = Object.keys(previewData.translations.en).sort();
  assert.ok(keys.length >= 30);
  for (const [code, strings] of Object.entries(previewData.translations)) {
    assert.deepEqual(Object.keys(strings).sort(), keys, `preview keys for ${code}`);
    assert.ok(keys.every(key => typeof strings[key] === 'string' && strings[key].trim()), `preview text for ${code}`);
  }
});
test('OS language resolving supports Dutch and Chinese and falls back safely', () => {
  const data = JSON.parse(read('dist/translations.json'));
  const context = { window: { VIBEZ_TRANSLATIONS: data } };
  vm.createContext(context); vm.runInContext(read('frontend/common.js'), context);
  const resolve = context.window.preview.resolve;
  assert.equal(resolve('system', 'nl_NL.UTF-8'), 'nl');
  assert.equal(resolve('system', 'zh-Hant-TW'), 'zh-TW');
  assert.equal(resolve('fr','nl_NL'), 'fr');
  assert.equal(resolve('system','xx_YY'), 'en');
});
test('toolbar language picker saves the choice through native settings', () => {
  const html = read('frontend/index.html');
  const toolbar = read('frontend/toolbar.js');
  const main = read('src-tauri/src/main.rs');
  assert.match(html, /id="language-button"/);
  assert.match(html, /id="quick-language"/);
  assert.match(toolbar, /save_settings/);
  assert.match(toolbar, /language: \$\('quick-language'\)\.value/);
  assert.match(main, /write_settings\(&state\.file, &settings\)/);
  assert.match(main, /desktop_ui::refresh\(&app\)/);
});
test('popup implementation preserves related views without spoofing or intercepting credentials', () => {
  const auth = read('src-tauri/src/auth.rs');
  assert.match(auth, /\.window_features\(features\)/);
  assert.match(auth, /NewWindowResponse::Create/);
  assert.doesNotMatch(auth, /\.user_agent\(|\.initialization_script\(|\.cookies\(|\.set_cookie\(|ignore_certificate/);
  assert.doesNotMatch(auth, /get_webview\("vibe"\).*navigate/);
  assert.match(read('src-tauri/src/smoke.rs'), /window\.opener\.postMessage/);
  assert.match(read('frontend/index.html'), /id="home"/);
});
test('tray update check is native-only, manual and separated from stable releases', () => {
  const updates = read('src-tauri/src/preview_updates.rs');
  const desktop = read('src-tauri/src/desktop_ui.rs');
  assert.match(desktop, /"updates" => crate::preview_updates::start/);
  assert.match(desktop, /menu_label/);
  const generated = JSON.parse(read('dist/translations.json'));
  assert.match(generated.translations.nl.updates, /Controleren op updates/);
  assert.match(read('src-tauri/src/main.rs'), /desktop_ui::refresh\(&app\)/);
  assert.match(updates, /const BRANCH: &str = "vibe\/tauri-linux-preview-7c4e90"/);
  assert.match(updates, /run\["conclusion"\] != "success"/);
  assert.match(updates, /entry\["expired"\] != false/);
  assert.doesNotMatch(updates, /Command::new|reqwest::blocking|danger_accept_invalid_certs|\.bearer_auth\(/);
  assert.doesNotMatch(read('src-tauri/build.rs'), /preview_updates|check_updates/);
});
test('Windows Store preview stays separate from the production Store identity', () => {
  const ps = read('scripts/build-windows-store-preview.ps1');
  assert.match(ps, /LeComputeur\.VibeZTauriPreview/);
  assert.doesNotMatch(ps, /Identity Name="LeComputeur\.VibeZDesktop"/);
  assert.doesNotMatch(ps, /9NR7L2G4MS08/);
  const workflow = fs.readFileSync(path.join(dir, '..', '.github', 'workflows', 'tauri-preview-windows.yml'), 'utf8');
  assert.match(workflow, /windows-latest/);
  assert.match(workflow, /Store-Preview/);
});
test('first-login nested OAuth popups are preserved and still isolated', () => {
  const auth = read('src-tauri/src/auth.rs');
  const smoke = read('src-tauri/src/smoke.rs');
  assert.match(auth, /create_auth_window\(&nested_app, next, nested_features, true\)/);
  assert.doesNotMatch(auth, /additional nested sign-in window was blocked/i);
  assert.match(smoke, /Nested OAuth popup/);
  assert.match(smoke, /Nested popup was granted native command access/);
  assert.match(smoke, /Nested popup callback did not reach its opener/);
});
test('trusted auth popup keeps the complete HTTPS redirect chain inside the isolated webview', () => {
  const auth = read('src-tauri/src/auth.rs');
  const policy = read('src-tauri/src/policy.rs');
  assert.match(auth, /fn auth_chain_allowed/);
  assert.match(auth, /policy::auth_chain_url\(url\)/);
  assert.match(policy, /url\.scheme\(\) == "https"/);
  assert.match(auth, /if auth_chain_allowed\(next, smoke\) \{ return true; \}/);
  assert.match(auth, /create_auth_window\(app, url, features, trusted_chain\)/);
  assert.doesNotMatch(auth, /\.user_agent\(|\.cookies\(|\.set_cookie\(|ignore_certificate/);
});
test('automatic injected opener is disabled; explicit native routes are traced', () => {
  const main = read('src-tauri/src/main.rs');
  assert.match(main, /open_js_links_on_click\(false\)/);
  assert.doesNotMatch(main, /\.plugin\(tauri_plugin_opener::init\(\)\)/);
  assert.match(main, /link_trace::record\("main-open-external", url\)/);
  assert.match(main, /link_trace::record\("main-popup-request", &url\)/);
  assert.match(main, /link_probe::start/);
  assert.match(read('src-tauri/src/link_probe.rs'), /native,native,native/);
});

test('main authentication routing is stateful across providers instead of domain-by-domain patching', () => {
  const main = read('src-tauri/src/main.rs');
  const policy = read('src-tauri/src/policy.rs');
  assert.match(main, /auth_active: AtomicBool/);
  assert.match(main, /policy::auth_entry_url\(url\)/);
  assert.match(main, /auth_active\.load\(Ordering::SeqCst\) && policy::auth_chain_url\(url\)/);
  assert.match(main, /policy::auth_return_url\(url\)/);
  assert.match(main, /"main-auth-allow"/);
  assert.match(policy, /pub fn auth_chain_url/);
  assert.match(policy, /pub fn auth_return_url/);
  assert.doesNotMatch(policy, /accounts\.youtube\.com.*embedded_url/s);
});

test('saved VibeZ language also drives Mistral NEXT_LOCALE and reloads the site', () => {
  const main = read('src-tauri/src/main.rs');
  const policy = read('src-tauri/src/policy.rs');
  assert.match(main, /Cookie::build\(\("NEXT_LOCALE", locale\.clone\(\)\)\)/);
  assert.match(main, /"chat\.mistral\.ai", "vibe\.mistral\.ai"/);
  assert.match(main, /view\.set_cookie\(cookie\)/);
  assert.match(main, /if reload \{ view\.reload\(\)/);
  assert.match(main, /language_changed/);
  assert.match(main, /apply_site_language\(&app, &settings\.language, true\)/);
  assert.match(policy, /pub fn mistral_site_locale/);
});
