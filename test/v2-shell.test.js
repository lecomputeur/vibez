const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

test('VibeZ 2.0 uses its own desktop shell around Mistral Vibe', () => {
  const main = read('main-v2.js');
  assert.match(main, /WebContentsView/);
  assert.match(main, /contentView\.addChildView\(vibeView\)/);
  assert.match(main, /loadFile\(path\.join\(__dirname, 'shell\.html'\)\)/);
  assert.match(main, /vibeView\.webContents/);
});

test('VibeZ 2.0 no longer creates the floating screenshot window', () => {
  const main = read('main-v2.js');
  const screenshot = read('screenshot-v2.js');
  assert.doesNotMatch(main, /screenshotButtonWindow/);
  assert.doesNotMatch(screenshot, /vibez-screenshot-button/);
  assert.match(main, /vibez:shell:action/);
  assert.match(main, /triggerScreenshot/);
});

test('VibeZ 2.0 toolbar does not expose a browser-style service or hostname pill', () => {
  const shell = read('shell.html');
  assert.doesNotMatch(shell, /location-pill/);
  assert.doesNotMatch(shell, /vibe\.mistral\.ai/);
  assert.match(shell, /id="screenshot"/);
  assert.match(shell, /id="settings"/);
});

test('VibeZ 2.0 uses the stable production identity', () => {
  const pkg = JSON.parse(read('package.json'));
  assert.equal(pkg.main, 'main-v2.js');
  assert.equal(pkg.version, '2.0.0');
  assert.equal(pkg.desktopName, 'com.vibez.app');
  assert.equal(pkg.build.appId, 'com.vibez.app');
  assert.equal(pkg.build.productName, 'VibeZ');
  assert.equal(pkg.build.executableName, 'vibez');
  assert.deepEqual(pkg.build.protocols[0].schemes, ['vibez']);
  assert.equal(pkg.build.publish.releaseType, 'release');
});

test('VibeZ 2.0 production UI and updater contain no beta or test branding', () => {
  const main = read('main-v2.js');
  const shell = read('shell.html');
  assert.doesNotMatch(main, /test shell|VibeZ 2\.0 Test|VIBEZ_V2_TEST/i);
  assert.doesNotMatch(shell, /2\.0 TEST|class="beta"/i);
  assert.match(main, /autoUpdater\.checkForUpdates/);
  assert.match(main, /checkMacUpdates/);
  assert.match(main, /process\.windowsStore/);
});

test('macOS 2.0 packaging is ready for Developer ID entitlements', () => {
  const pkg = JSON.parse(read('package.json'));
  assert.equal(pkg.build.mac.hardenedRuntime, true);
  assert.equal(pkg.build.mac.entitlements, 'build/entitlements.mac.plist');
  assert.equal(pkg.build.mac.entitlementsInherit, 'build/entitlements.mac.inherit.plist');
  assert.match(read('build/entitlements.mac.plist'), /com\.apple\.security\.cs\.allow-jit/);
});
