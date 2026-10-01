'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let polling = false;
  let captureBusy = false;
  function status(text) { $('status').textContent = text; $('status').title = text; }
  async function refresh() {
    if (polling) return;
    polling = true;
    try {
      const state = await preview.invoke('get_state');
      preview.localize(state);
      $('version').textContent = state.version;
      $('back').disabled = !state.can_go_back;
      $('forward').disabled = !state.can_go_forward;
      $('loading').classList.toggle('active', state.loading);
      $('screenshot').hidden = !state.settings.show_screenshot;
      const homeLabel = preview.resolve(state.settings.language, state.os_locale) === 'nl' ? 'Startpagina — terug naar Vibe' : 'Home — back to Vibe';
      $('home').title = homeLabel; $('home').setAttribute('aria-label', homeLabel);
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
