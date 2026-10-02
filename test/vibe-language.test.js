const test = require('node:test');
const assert = require('node:assert/strict');
const {
  VIBE_LOCALE_COOKIE_URLS,
  resolveVibeLocale,
} = require('../vibe-language');

test('Vibe page locale follows supported VibeZ/system languages', () => {
  assert.equal(resolveVibeLocale('nl-NL'), 'nl');
  assert.equal(resolveVibeLocale('en-GB'), 'en');
  assert.equal(resolveVibeLocale('de-DE'), 'de');
  assert.equal(resolveVibeLocale('pt-BR'), 'pt');
  assert.equal(resolveVibeLocale('uk-UA'), 'uk');
});

test('unsupported Vibe page languages fall back to English', () => {
  assert.equal(resolveVibeLocale('ja-JP'), 'en');
  assert.equal(resolveVibeLocale('zh-TW'), 'en');
  assert.equal(resolveVibeLocale(''), 'en');
});

test('locale cookie is applied to both current Mistral Vibe hosts', () => {
  assert.deepEqual(VIBE_LOCALE_COOKIE_URLS, [
    'https://vibe.mistral.ai/',
    'https://chat.mistral.ai/',
  ]);
});
