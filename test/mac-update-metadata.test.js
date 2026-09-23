const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { generateMacUpdateMetadata } = require('../build/generate-mac-update-metadata');

const hash = (contents) => crypto.createHash('sha512').update(contents).digest('base64');

test('macOS update metadata contains signed release archives for both architectures', (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'vibez-mac-update-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));

  const x64 = Buffer.from('signed Intel archive');
  const arm64 = Buffer.from('signed Apple silicon archive');
  fs.writeFileSync(path.join(directory, 'VibeZ-2.0.1-macOS-x64.zip'), x64);
  fs.writeFileSync(path.join(directory, 'VibeZ-2.0.1-macOS-arm64.zip'), arm64);

  const metadataPath = generateMacUpdateMetadata(directory, '2.0.1', '2026-09-23T12:00:00.000Z');
  const metadata = fs.readFileSync(metadataPath, 'utf8');

  assert.match(metadata, /^version: 2\.0\.1$/m);
  assert.match(metadata, /url: VibeZ-2\.0\.1-macOS-x64\.zip/);
  assert.match(metadata, /url: VibeZ-2\.0\.1-macOS-arm64\.zip/);
  assert.ok(metadata.includes(`sha512: ${hash(x64)}`));
  assert.ok(metadata.includes(`sha512: ${hash(arm64)}`));
  assert.ok(metadata.includes(`size: ${x64.length}`));
  assert.ok(metadata.includes(`size: ${arm64.length}`));
  assert.match(metadata, /path: VibeZ-2\.0\.1-macOS-x64\.zip/);
  assert.match(metadata, /releaseDate: '2026-09-23T12:00:00\.000Z'/);
});

test('macOS update metadata fails when either architecture is missing', (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'vibez-mac-update-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  fs.writeFileSync(path.join(directory, 'VibeZ-2.0.1-macOS-x64.zip'), 'signed Intel archive');

  assert.throws(
    () => generateMacUpdateMetadata(directory, '2.0.1'),
    /Missing macOS update archive.*arm64/,
  );
});
