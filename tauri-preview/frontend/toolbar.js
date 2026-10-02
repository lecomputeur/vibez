'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let polling = false;
  let captureBusy = false;
  let languageBusy = false;
  let state = null;
  let languagesReady = false;

  function status(text) { $('status').textContent = text; $('status').title = text; }

  function prepareLanguages() {
    if (languagesReady) return;
    for (const option of preview.data.options) {
      const el = document.createElement('option');
      el.value = option.code; el.textContent = option.name;
      $('quick-language').appendChild(el);
    }
    languagesReady = true;
  }

  function showLanguageState() {
    if (!state) return;
    prepareLanguages();
    $('quick-language').value = state.settings.language;
    const resolved = preview.resolve(state.settings.language, state.os_locale);
    $('language-code').textContent = state.settings.language === 'system' ? 'AUTO' : resolved.toUpperCase().replace('-', '·');
    preview.localize(state);
  }

  async function refresh() {
    if (polling || languageBusy) return;
    polling = true;
    try {
      state = await preview.invoke('get_state');
      preview.localize(state);
      $('version').textContent = state.version;
      $('back').disabled = !state.can_go_back;
      $('forward').disabled = !state.can_go_forward;
      $('loading').classList.toggle('active', state.loading);
      $('screenshot').hidden = !state.settings.show_screenshot;
      showLanguageState();
      status(state.status);
    } catch (error) { status(preview.errorText(error)); }
    finally { polling = false; }
  }

  for (const action of ['back', 'forward', 'reload', 'home']) {
    $(action).addEventListener('click', async () => {
      try { await preview.invoke('navigate', { action }); await refresh(); }
      catch (error) { status(preview.errorText(error)); }
    });
  }

  $('language-button').addEventListener('click', () => {
    const panel = $('language-panel');
    panel.hidden = !panel.hidden;
    $('language-button').setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) {
      prepareLanguages(); showLanguageState(); $('quick-language').focus();
      try { $('quick-language').showPicker?.(); } catch (_) {}
    }
  });

  $('quick-language').addEventListener('change', async () => {
    if (!state || languageBusy) return;
    languageBusy = true;
    $('quick-language').disabled = true;
    try {
      const settings = { ...state.settings, language: $('quick-language').value };
      state.settings = await preview.invoke('save_settings', { settings });
      preview.localize(state);
      showLanguageState();
      status(preview.extra('saved'));
      $('language-panel').hidden = true;
      $('language-button').setAttribute('aria-expanded', 'false');
    } catch (error) { status(preview.errorText(error)); }
    finally { languageBusy = false; $('quick-language').disabled = false; }
  });

  document.addEventListener('pointerdown', event => {
    const control = document.querySelector('.language-control');
    if (control && !control.contains(event.target)) {
      $('language-panel').hidden = true;
      $('language-button').setAttribute('aria-expanded', 'false');
    }
  });

  $('settings').addEventListener('click', () => preview.invoke('show_settings').catch(e => status(preview.errorText(e))));
  $('screenshot').addEventListener('click', async () => {
    if (captureBusy) return;
    captureBusy = true; $('screenshot').disabled = true;
    try { await preview.invoke('capture_screenshot'); }
    catch (error) { status(preview.errorText(error)); }
    finally { captureBusy = false; $('screenshot').disabled = false; await refresh(); }
  });

  refresh(); setInterval(refresh, 1500);
})();
