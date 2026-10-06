'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let polling = false, epoch = 0, captureBusy = false, languageBusy = false, state = null, languagesReady = false;
  function status(text) { $('status').textContent = text; $('status').title = text; }
  function prepareLanguages() {
    if (languagesReady) return;
    for (const option of preview.data.options) {
      const el = document.createElement('option'); el.value = option.code; el.textContent = option.name; $('quick-language').appendChild(el);
    }
    languagesReady = true;
  }
  function showLanguageState() {
    if (!state) return;
    prepareLanguages(); $('quick-language').value = state.settings.language;
    const resolved = preview.resolve(state.settings.language, state.os_locale);
    const code = resolved.toUpperCase().replace('-', '·');
    $('language-code').textContent = state.settings.language === 'system' ? `AUTO·${code}` : code;
    preview.localize(state);
  }
  async function refresh() {
    if (polling || languageBusy) return;
    polling = true; const started = epoch;
    try {
      const incoming = await preview.invoke('get_state');
      if (started !== epoch || languageBusy || (state && incoming.revision < state.revision)) return;
      state = incoming; preview.localize(state); $('version').textContent = state.version;
      $('back').disabled = !state.can_go_back; $('forward').disabled = !state.can_go_forward;
      $('loading').classList.toggle('active', state.loading); $('screenshot').hidden = !state.settings.show_screenshot;
      showLanguageState(); status(state.status);
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
    const panel = $('language-panel'); panel.hidden = !panel.hidden;
    $('language-button').setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) {
      prepareLanguages(); showLanguageState(); $('quick-language').focus();
      try { $('quick-language').showPicker?.(); } catch (_) {}
    }
  });
  $('quick-language').addEventListener('change', async () => {
    if (!state || languageBusy) return;
    languageBusy = true; ++epoch; $('quick-language').disabled = true;
    try {
      const patch = { language: $('quick-language').value };
      const expected = { language: state.settings.language };
      const saved = await preview.invoke('save_settings', { patch, expected });
      state = { ...state, ...saved }; preview.localize(state); showLanguageState(); status(preview.extra('saved'));
      $('language-panel').hidden = true; $('language-button').setAttribute('aria-expanded', 'false');
    } catch (error) { status(preview.errorText(error)); }
    finally { languageBusy = false; $('quick-language').disabled = false; }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !$('language-panel').hidden) {
      $('language-panel').hidden = true; $('language-button').setAttribute('aria-expanded', 'false'); $('language-button').focus();
    }
  });
  document.addEventListener('pointerdown', event => {
    const control = document.querySelector('.language-control');
    if (control && !control.contains(event.target)) {
      $('language-panel').hidden = true; $('language-button').setAttribute('aria-expanded', 'false');
    }
  });
  $('settings').addEventListener('click', () => preview.invoke('show_settings').catch(e => status(preview.errorText(e))));

  function closeScreenshotPanel() {
    const panel = $('screenshot-panel');
    panel.hidden = true;
    $('screenshot').setAttribute('aria-expanded', 'false');
  }
  $('screenshot').addEventListener('click', () => {
    if (captureBusy) return;
    const panel = $('screenshot-panel');
    panel.hidden = !panel.hidden;
    $('screenshot').setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) panel.querySelector('button')?.focus();
  });
  for (const item of document.querySelectorAll('[data-screenshot-mode]')) {
    item.addEventListener('click', async () => {
      if (captureBusy) return;
      const mode = item.dataset.screenshotMode;
      closeScreenshotPanel();
      captureBusy = true;
      $('screenshot').disabled = true;
      for (const button of document.querySelectorAll('[data-screenshot-mode]')) button.disabled = true;
      try { await preview.invoke('capture_screenshot', { mode }); }
      catch (error) { status(preview.errorText(error)); }
      finally {
        captureBusy = false;
        $('screenshot').disabled = false;
        for (const button of document.querySelectorAll('[data-screenshot-mode]')) button.disabled = false;
        await refresh();
      }
    });
  }
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !$('screenshot-panel').hidden) {
      closeScreenshotPanel();
      $('screenshot').focus();
    }
  });
  document.addEventListener('pointerdown', event => {
    const control = document.querySelector('.screenshot-control');
    if (control && !control.contains(event.target)) closeScreenshotPanel();
  });

  refresh(); setInterval(refresh, 1500);
})();
