'use strict';
(async () => {
  const $ = id => document.getElementById(id);
  let state;
  try {
    state = await preview.invoke('get_state');
    preview.localize(state); $('version').textContent = `v${state.version} · Rust / WebKitGTK`;
    for (const option of preview.data.options) {
      const el = document.createElement('option'); el.value = option.code; el.textContent = option.name; $('language').appendChild(el);
    }
    $('language').value = state.settings.language;
    $('zoom').value = String(state.settings.zoom_factor);
    $('show-screenshot').checked = state.settings.show_screenshot;
    $('close-to-tray').checked = state.settings.close_to_tray && state.tray_ready;
    $('close-to-tray').disabled = !state.tray_ready;
    $('start-at-login').checked = state.settings.start_at_login;
    $('diagnostics').value = await preview.invoke('get_diagnostics');
  } catch (error) { $('result').textContent = preview.errorText(error); $('save').disabled = true; }
  $('language').addEventListener('change', () => {
    if (state) preview.localize({ ...state, settings: { ...state.settings, language: $('language').value } });
  });
  $('preferences').addEventListener('submit', async event => {
    event.preventDefault(); $('save').disabled = true;
    try {
      const settings = { language: $('language').value, zoom_factor: Number($('zoom').value),
        show_screenshot: $('show-screenshot').checked, close_to_tray: $('close-to-tray').checked,
        start_at_login: $('start-at-login').checked };
      const saved = await preview.invoke('save_settings', { settings });
      state.settings = saved; preview.localize(state); $('result').textContent = preview.extra('saved');
    } catch (error) { $('result').textContent = preview.errorText(error); }
    finally { $('save').disabled = false; }
  });
  $('close').addEventListener('click', () => preview.invoke('close_settings').catch(e => $('result').textContent = preview.errorText(e)));
})();
