'use strict';
window.preview = (() => {
  const data = window.VIBEZ_TRANSLATIONS;
  const extras = {
    en: {
      previewTitle: 'VibeZ Tauri Preview',
      intro: 'Experimental Linux edition. Your current Electron VibeZ, account profile and installed packages are left untouched.',
      limits: 'This is not yet a feature-complete replacement. Screenshot selection uses your Linux desktop portal; paste with Ctrl+V. Global shortcuts, automatic updates and microphone/camera permissions are not enabled. Popup-based sign-in and the live Vibe website still need testing on your desktop.',
      diagnostics: 'Diagnostic information', copy: 'Select and copy this information for testing. It contains no chat messages or account tokens.',
      trayHint: 'Enable only when you can see the preview tray icon. GNOME may need tray support. Reopening the preview restores its window.',
      screenshotHint: 'The portal may offer an area, window or whole-screen capture, depending on your desktop. Cancelling never falls back to a silent capture.',
      saved: 'Saved for the preview only.', back: 'Back', forward: 'Forward', reload: 'Reload'
    },
    nl: {
      previewTitle: 'VibeZ Tauri Preview',
      intro: 'Experimentele Linux-versie. Je huidige Electron-VibeZ, accountprofiel en geïnstalleerde pakketten blijven ongemoeid.',
      limits: 'Dit is nog geen volledige vervanger. Screenshots gaan via het schermdialoogvenster van Linux; plakken met Ctrl+V. Globale sneltoetsen, automatische updates en microfoon/camera zijn nog niet ingeschakeld. Inloggen via pop-ups en de live Vibe-website moeten nog op jouw computer worden getest.',
      diagnostics: 'Diagnostische informatie', copy: 'Selecteer en kopieer dit voor het testen. Er staan geen chatberichten of accounttokens in.',
      trayHint: 'Alleen inschakelen als je het preview-traypictogram ziet. GNOME kan extra trayondersteuning nodig hebben. De preview opnieuw openen toont het venster weer.',
      screenshotHint: 'Afhankelijk van je desktop kun je een gebied, venster of volledig scherm kiezen. Na annuleren wordt nooit alsnog stilzwijgend een screenshot gemaakt.',
      saved: 'Alleen voor de proefversie opgeslagen.', back: 'Terug', forward: 'Vooruit', reload: 'Herladen'
    }
  };
  let language = 'en';
  function resolve(setting, locale) {
    const raw = String(setting && setting !== 'system' ? setting : locale || 'en').replace(/_/g, '-').toLowerCase();
    const candidate = raw.startsWith('zh') ? (/tw|hk|mo|hant/.test(raw) ? 'zh-TW' : 'zh-CN') : raw.split(/[.-]/)[0];
    return data.translations[candidate] ? candidate : 'en';
  }
  function localize(state) {
    language = resolve(state.settings.language, state.os_locale);
    document.documentElement.lang = language;
    document.documentElement.dir = ['ar','he','fa','ur'].includes(language) ? 'rtl' : 'ltr';
    const strings = data.translations[language];
    for (const el of document.querySelectorAll('[data-i18n]')) el.textContent = strings[el.dataset.i18n] || el.dataset.i18n;
    for (const el of document.querySelectorAll('[data-extra]')) el.textContent = extra(el.dataset.extra);
    for (const key of ['back','forward','reload']) {
      const button = document.getElementById(key);
      if (button) { button.title = extra(key); button.setAttribute('aria-label', extra(key)); }
    }
    return strings;
  }
  function extra(key) { return (extras[language] || extras.en)[key] || key; }
  function invoke(command, args = {}) {
    if (!window.__TAURI__?.core?.invoke) return Promise.reject(new Error('Native preview bridge is unavailable'));
    return window.__TAURI__.core.invoke(command, args);
  }
  function errorText(error) { return typeof error === 'string' ? error : error?.message || String(error); }
  return { data, resolve, localize, extra, invoke, errorText };
})();
