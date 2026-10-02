const SUPPORTED_VIBE_LOCALES = new Set([
  'en',
  'nl',
  'de',
  'fr',
  'es',
  'it',
  'pt',
  'pl',
  'ar',
  'uk',
]);

const VIBE_LOCALE_COOKIE_URLS = Object.freeze([
  'https://vibe.mistral.ai/',
  'https://chat.mistral.ai/',
]);

function resolveVibeLocale(language) {
  const normalized = String(language || 'en').trim().replace(/_/g, '-').toLowerCase();
  const base = normalized.split('-')[0];
  return SUPPORTED_VIBE_LOCALES.has(base) ? base : 'en';
}

module.exports = {
  SUPPORTED_VIBE_LOCALES,
  VIBE_LOCALE_COOKIE_URLS,
  resolveVibeLocale,
};
