'use strict';
window.preview = (() => {
  const data = window.VIBEZ_TRANSLATIONS;
  const previewData = window.VIBEZ_PREVIEW_TRANSLATIONS;
  let language = 'en';
  function resolve(setting, locale) {
    const raw = String(setting && setting !== 'system' ? setting : locale || 'en').replace(/_/g, '-').toLowerCase();
    const candidate = raw.startsWith('zh') ? (/tw|hk|mo|hant/.test(raw) ? 'zh-TW' : 'zh-CN') : raw.split(/[.-]/)[0];
    return data.translations[candidate] ? candidate : 'en';
  }
  function extra(key) {
    const strings = previewData?.translations?.[language] || {};
    const fallback = previewData?.translations?.en || {};
    return strings[key] || fallback[key] || key;
  }
  function localize(state) {
    language = resolve(state.settings.language, state.os_locale);
    document.documentElement.lang = language;
    document.documentElement.dir = ['ar','he','fa','ur'].includes(language) ? 'rtl' : 'ltr';
    const strings = data.translations[language];
    for (const el of document.querySelectorAll('[data-i18n]')) el.textContent = strings[el.dataset.i18n] || el.dataset.i18n;
    for (const el of document.querySelectorAll('[data-extra]')) el.textContent = extra(el.dataset.extra);
    for (const key of ['back','forward','reload','home','screenshot','settings']) {
      const button = document.getElementById(key);
      const label = ['screenshot','settings'].includes(key) ? strings[key] : extra(key);
      if (button) { button.title = label; button.setAttribute('aria-label', label); }
    }
    const languageButton = document.getElementById('language-button');
    if (languageButton) { const label = extra('languageButton'); languageButton.title = label; languageButton.setAttribute('aria-label', label); }
    const languageHeading = document.getElementById('language-heading');
    if (languageHeading) languageHeading.textContent = extra('chooseLanguage');
    for (const system of document.querySelectorAll('option[value="system"]')) system.textContent = strings.system || 'System';
    return strings;
  }
  function invoke(command, args = {}) {
    if (!window.__TAURI__?.core?.invoke) return Promise.reject(new Error(extra('bridgeError')));
    return window.__TAURI__.core.invoke(command, args);
  }
  function errorText(error) {
    const raw = typeof error === 'string' ? error : error?.message || String(error);
    const key = { settings_conflict: 'settingsConflict', tray_unavailable: 'trayUnavailable' }[raw];
    return key ? extra(key) : raw;
  }
  function currentLanguage() { return language; }
  return { data, previewData, resolve, localize, extra, invoke, errorText, currentLanguage };
})();
