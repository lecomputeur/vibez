'use strict';
window.preview = (() => {
  const data = window.VIBEZ_TRANSLATIONS;
  const extras = {
    en: {
      previewTitle: 'VibeZ Tauri Preview',
      intro: 'Experimental Linux edition. Your current Electron VibeZ, account profile and installed packages are left untouched.',
      limits: 'This is not yet a feature-complete replacement. Screenshots use your Linux desktop portal; paste with Ctrl+V. Check for preview updates through the tray menu and install the .deb manually. Global shortcuts, automatic installation and microphone/camera permissions are not enabled.',
      diagnostics: 'Diagnostic information', copy: 'Select and copy this information for testing. Technical diagnostic fields are in English; no chat messages or account tokens are included.',
      trayHint: 'Enable only when you can see the preview tray icon. GNOME may need tray support. Reopening the preview restores its window.',
      screenshotHint: 'The portal may offer an area, window or whole-screen capture, depending on your desktop. Cancelling never falls back to a silent capture.',
      disclaimer: 'Independent project. Not affiliated with or supported by Mistral AI. A Mistral account and internet connection may be required.',
      saved: 'Saved for the preview only.', back: 'Back', forward: 'Forward', reload: 'Reload', home: 'Home', bridgeError: 'Native preview bridge is unavailable'
    },
    nl: {
      previewTitle: 'VibeZ Tauri Preview',
      intro: 'Experimentele Linux-versie. Je huidige Electron-VibeZ, accountprofiel en geïnstalleerde pakketten blijven ongemoeid.',
      limits: 'Dit is nog geen volledige vervanger. Screenshots gaan via het schermdialoogvenster van Linux; plakken met Ctrl+V. Controleer updates voor de proefversie via het systeemvakmenu en installeer het .deb-bestand handmatig. Globale sneltoetsen, automatisch installeren en microfoon/camera zijn nog niet ingeschakeld.',
      diagnostics: 'Diagnostische informatie', copy: 'Selecteer en kopieer dit voor het testen. Technische diagnosevelden zijn Engelstalig; er staan geen chatberichten of accounttokens in.',
      trayHint: 'Alleen inschakelen als je het pictogram van de proefversie in het systeemvak ziet. GNOME kan extra ondersteuning nodig hebben. De proefversie opnieuw openen toont het venster weer.',
      screenshotHint: 'Afhankelijk van je desktop kun je een gebied, venster of volledig scherm kiezen. Na annuleren wordt nooit alsnog stilzwijgend een screenshot gemaakt.',
      disclaimer: 'Onafhankelijk project. Niet verbonden aan of ondersteund door Mistral AI. Een Mistral-account en internetverbinding kunnen nodig zijn.',
      saved: 'Alleen voor de proefversie opgeslagen.', back: 'Terug', forward: 'Vooruit', reload: 'Herladen', home: 'Startpagina', bridgeError: 'De verbinding met de proefversie is niet beschikbaar'
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
    for (const key of ['back','forward','reload','home','screenshot','settings']) {
      const button = document.getElementById(key);
      const label = ['screenshot','settings'].includes(key) ? strings[key] : extra(key);
      if (button) { button.title = label; button.setAttribute('aria-label', label); }
    }
    const system = document.querySelector('#language option[value="system"]');
    if (system) system.textContent = strings.system || 'System';
    return strings;
  }
  function extra(key) { return (extras[language] || extras.en)[key] || key; }
  function invoke(command, args = {}) {
    if (!window.__TAURI__?.core?.invoke) return Promise.reject(new Error(extra('bridgeError')));
    return window.__TAURI__.core.invoke(command, args);
  }
  function errorText(error) { return typeof error === 'string' ? error : error?.message || String(error); }
  return { data, resolve, localize, extra, invoke, errorText };
})();
