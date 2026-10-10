'use strict';
// Only adapt legacy update metadata. Never replace, rename or execute an installer.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const yaml = require('js-yaml');
const { GitHubProvider } = require('electron-updater/out/providers/GitHubProvider');
const LEGACY = 'v2.0.2';
const CURRENT = `v${process.env.VIBEZ_RELEASE_VERSION || '3.0.3'}`;
assert.match(CURRENT, /^v3\.\d+\.\d+$/);
const REPO = 'lecomputeur/vibez';
const names = ['latest.yml', 'latest-linux.yml', 'latest-mac.yml'];
const directory = process.argv[2];
if (!directory) throw new Error('Usage: node legacy-feed.cjs DIRECTORY');
const release = JSON.parse(fs.readFileSync(path.join(directory, 'release.json'), 'utf8'));
assert.equal(release.tag_name, LEGACY);
assert.equal(release.draft, false);
const assets = new Map(release.assets.map(a => [a.name, a]));
const provider = new GitHubProvider(
  { owner: 'lecomputeur', repo: 'vibez', provider: 'github' },
  { channel: null, allowPrerelease: false },
  { executor: {}, platform: process.platform }
);
function target(value) {
  assert.equal(typeof value, 'string');
  let name = value;
  if (value.startsWith('https://')) {
    const prefix = `https://github.com/${REPO}/releases/download/${LEGACY}/`;
    assert.ok(value.startsWith(prefix), 'Reject foreign legacy URL');
    name = decodeURIComponent(value.slice(prefix.length));
  }
  assert.match(name, /^VibeZ-2\.[0-9]+\.[0-9]+-[A-Za-z0-9_.-]+$/);
  assert.ok(assets.has(name), `Legacy asset is absent: ${name}`);
  const asset = assets.get(name);
  assert.ok(asset.size > 0);
  assert.equal(asset.browser_download_url, `https://github.com/${REPO}/releases/download/${LEGACY}/${name}`);
  return { name, original: asset.browser_download_url, relative: `../${LEGACY}/${name}` };
}
for (const name of names) {
  const file = path.join(directory, name);
  const old = yaml.load(fs.readFileSync(file, 'utf8'));
  assert.match(old.version, /^2\.[0-9]+\.[0-9]+$/);
  assert.ok(Array.isArray(old.files) && old.files.length > 0);
  const data = structuredClone(old);
  const expected = [];
  for (const entry of data.files) {
    const asset = target(entry.url);
    assert.equal(typeof entry.sha512, 'string');
    assert.ok(entry.sha512.length > 40);
    entry.url = asset.relative;
    expected.push(asset.original);
    if (entry.blockMapUrl) entry.blockMapUrl = target(entry.blockMapUrl).relative;
  }
  if (data.path) data.path = target(data.path).relative;
  if (data.packages) {
    for (const entry of Object.values(data.packages)) entry.path = target(entry.path).relative;
  }
  // Test the actual locked electron-updater resolver, not an assumed URL formula.
  const resolved = provider.resolveFiles({ ...data, tag: CURRENT });
  assert.deepEqual(resolved.map(entry => entry.url.href), expected);
  for (let i = 0; i < data.files.length; i++) {
    assert.equal(data.files[i].sha512, old.files[i].sha512);
    assert.equal(data.files[i].size, old.files[i].size);
  }
  assert.equal(data.version, old.version);
  const serialized = yaml.dump(data, { lineWidth: -1, noRefs: true });
  const roundtrip = yaml.load(serialized);
  assert.deepEqual(provider.resolveFiles({ ...roundtrip, tag: CURRENT }).map(entry => entry.url.href), expected);
  fs.writeFileSync(file, serialized);
  console.log(`LEGACY_UPDATE_OK: ${name} preserves ${data.version} and resolves only to original ${LEGACY} assets`);
}
