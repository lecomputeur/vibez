const west = require('./locales/west');
const asia = require('./locales/asia');
const east = require('./locales/east');
const rtl = require('./locales/rtl');
const southasia = require('./locales/southasia');
const globalLanguages = require('./locales/global');

const GROUP_KEYS = Object.freeze({
  menu: ['paste','copy','cut','selectAll','searchGoogle','searchDuck','open','screenshot','settings','updates','about','quit'],
  shot: ['shotStartError','noSource','noDisplays','shotFailed','shotFailedMessage','selectShot','selectHint'],
  dialog: ['desktopClient','copySystem','reportProblem','close','latest','updateFailed','updateReady','readyInstall','restartUpdate','later','installedOnly','flatpakBuild','openReleases'],
  settings: ['settingsTitle','desktopIntegration','globalShot','shotShortcut','showShot','startLogin','minTray','closeTray','display','hardware','backend','zoom','language','updatesBrowser','autoUpdates','installOnQuit','externalLinks','browserData','resetData','save','automatic','enabled','disabled','system','saving','saved','restartNeeded','shortcutBusy','checking','updateStarted','clearConfirm','clearing','cleared','notCleared'],
});

const RAW = Object.freeze({ ...west, ...asia, ...east, ...rtl, ...southasia, ...globalLanguages });
const RTL_LANGUAGES = new Set(['ar','he','fa','ur']);

const LANGUAGE_OPTIONS = Object.freeze([
  { code: 'system', name: 'System' },
  { code: 'en', name: 'English' },
  { code: 'nl', name: 'Nederlands' },
  { code: 'de', name: 'Deutsch' },
  { code: 'fr', name: 'Français' },
  { code: 'es', name: 'Español' },
  { code: 'it', name: 'Italiano' },
  { code: 'pt', name: 'Português' },
  { code: 'pl', name: 'Polski' },
  { code: 'ru', name: 'Русский' },
  { code: 'uk', name: 'Українська' },
  { code: 'tr', name: 'Türkçe' },
  { code: 'zh-CN', name: '简体中文' },
  { code: 'zh-TW', name: '繁體中文' },
  { code: 'ja', name: '日本語' },
  { code: 'ko', name: '한국어' },
  { code: 'hi', name: 'हिन्दी' },
  { code: 'bn', name: 'বাংলা' },
  { code: 'pa', name: 'ਪੰਜਾਬੀ' },
  { code: 'mr', name: 'मराठी' },
  { code: 'te', name: 'తెలుగు' },
  { code: 'ta', name: 'தமிழ்' },
  { code: 'gu', name: 'ગુજરાતી' },
  { code: 'id', name: 'Bahasa Indonesia' },
  { code: 'vi', name: 'Tiếng Việt' },
  { code: 'th', name: 'ไทย' },
  { code: 'fil', name: 'Filipino' },
  { code: 'jv', name: 'Basa Jawa' },
  { code: 'sw', name: 'Kiswahili' },
  { code: 'ha', name: 'Hausa' },
  { code: 'am', name: 'አማርኛ' },
  { code: 'ar', name: 'العربية' },
  { code: 'he', name: 'עברית' },
  { code: 'fa', name: 'فارسی' },
  { code: 'ur', name: 'اردو' },
]);

function buildTranslations() {
  const out = {};
  for (const [code, groups] of Object.entries(RAW)) {
    const strings = {};
    for (const [group, keys] of Object.entries(GROUP_KEYS)) {
      const values = groups[group];
      if (!Array.isArray(values) || values.length !== keys.length) {
        throw new Error(`Invalid ${group} translation count for ${code}: expected ${keys.length}, got ${values?.length ?? 'none'}`);
      }
      keys.forEach((key, index) => { strings[key] = values[index]; });
    }
    out[code] = Object.freeze(strings);
  }
  return Object.freeze(out);
}

const TRANSLATIONS = buildTranslations();
const SUPPORTED = new Set(Object.keys(TRANSLATIONS));

function normalizeLocale(value) {
  const raw = String(value || 'en').trim().replace(/_/g, '-');
  const lower = raw.toLowerCase();
  if (lower.startsWith('zh')) {
    if (lower.includes('tw') || lower.includes('hk') || lower.includes('mo') || lower.includes('hant')) return 'zh-TW';
    return 'zh-CN';
  }
  const base = lower.split('-')[0];
  return SUPPORTED.has(base) ? base : 'en';
}

function resolveLanguage(setting, osLocale) {
  if (setting && setting !== 'system') return normalizeLocale(setting);
  return normalizeLocale(osLocale);
}

function isRtl(language) {
  return RTL_LANGUAGES.has(normalizeLocale(language));
}

function getStrings(language) {
  return TRANSLATIONS[normalizeLocale(language)] || TRANSLATIONS.en;
}

function formatText(text, values = {}) {
  return String(text).replace(/\{([a-zA-Z0-9_]+)\}/g, (match, key) => Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match);
}

function t(language, key, values) {
  const strings = getStrings(language);
  return formatText(strings[key] ?? TRANSLATIONS.en[key] ?? key, values);
}

function uiBundle(language) {
  const resolved = normalizeLocale(language);
  return {
    language: resolved,
    dir: isRtl(resolved) ? 'rtl' : 'ltr',
    strings: getStrings(resolved),
    languageOptions: LANGUAGE_OPTIONS,
  };
}

module.exports = {
  GROUP_KEYS,
  LANGUAGE_OPTIONS,
  TRANSLATIONS,
  normalizeLocale,
  resolveLanguage,
  isRtl,
  getStrings,
  t,
  uiBundle,
};
