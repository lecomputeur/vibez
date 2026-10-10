'use strict';
(async () => {
  const $ = id => document.getElementById(id);
  const fields = { language: ['language', 'value'], zoom_factor: ['zoom', 'value'], show_screenshot: ['show-screenshot', 'checked'], close_to_tray: ['close-to-tray', 'checked'], start_at_login: ['start-at-login', 'checked'], auto_updates: ['auto-updates', 'checked'] };
  let state = null, baseline = {}, saving = false, polling = false, epoch = 0;
  function values() {
    const result = {};
    for (const [key, [id, prop]] of Object.entries(fields)) result[key] = $(id)[prop];
    result.zoom_factor = Number(result.zoom_factor); return result;
  }
  function accept(incoming, force = false, reconcile = false) {
    if (state && incoming.revision < state.revision) return;
    const edited = state ? values() : {};
    for (const [key, [id, prop]] of Object.entries(fields)) {
      const conflict = reconcile && incoming.settings[key] !== baseline[key] && incoming.settings[key] !== edited[key];
      if (force || !state || edited[key] === baseline[key] || conflict) {
        $(id)[prop] = prop === 'value' ? String(incoming.settings[key]) : incoming.settings[key];
        baseline[key] = incoming.settings[key];
      }
      if (reconcile) baseline[key] = incoming.settings[key];
    }
    state = incoming; preview.localize(state);
    $('version').textContent = `v${state.version} · Rust / Tauri`;
    $('close-to-tray').disabled = saving || !state.tray_ready;
    $('save').disabled = saving;
  }
  async function refresh(force = false) {
    if (polling || saving) return;
    polling = true; const started = epoch;
    try {
      const incoming = await preview.invoke('get_state');
      if (started === epoch && !saving) accept(incoming, force);
    } catch (error) { $('result').textContent = preview.errorText(error); }
    finally { polling = false; }
  }
  async function diagnostics() {
    $('diagnostics-refresh').disabled = true;
    try { $('diagnostics').value = await preview.invoke('get_diagnostics'); }
    catch (error) { $('diagnostics').value = preview.errorText(error); }
    finally { $('diagnostics-refresh').disabled = false; }
  }
  try {
    for (const option of preview.data.options) {
      const el = document.createElement('option'); el.value = option.code; el.textContent = option.name; $('language').appendChild(el);
    }
    accept(await preview.invoke('get_state'), true); $('save').disabled = false;
  } catch (error) { $('result').textContent = preview.errorText(error); $('save').disabled = true; }
  // Diagnostics never controls whether independent preferences can be saved.
  diagnostics();
  $('diagnostics-refresh').addEventListener('click', diagnostics);
  $('diagnostics-copy').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($('diagnostics').value); }
    catch (_) { $('diagnostics').focus(); $('diagnostics').select(); }
  });
  $('language').addEventListener('change', () => {
    if (state) preview.localize({ ...state, settings: { ...state.settings, language: $('language').value } });
  });
  $('preferences').addEventListener('submit', async event => {
    event.preventDefault(); if (!state || saving) return;
    const edited = values(), patch = {}, expected = {};
    for (const key of Object.keys(fields)) {
      if (edited[key] !== baseline[key]) { patch[key] = edited[key]; expected[key] = baseline[key]; }
    }
    if (!Object.keys(patch).length) { $('result').textContent = preview.extra('saved'); return; }
    saving = true; ++epoch; $('save').disabled = true;
    for (const [id] of Object.values(fields)) $(id).disabled = true;
    let conflict = false;
    try {
      const saved = await preview.invoke('save_settings', { patch, expected });
      accept({ ...state, ...saved }, true); $('result').textContent = preview.extra('saved');
    } catch (error) {
      conflict = String(error) === 'settings_conflict'; $('result').textContent = preview.errorText(error);
    } finally {
      saving = false; $('save').disabled = false;
      for (const [id] of Object.values(fields)) $(id).disabled = false;
      $('close-to-tray').disabled = !state.tray_ready;
    }
    if (conflict) {
      try { accept(await preview.invoke('get_state'), false, true); }
      catch (error) { $('result').textContent = preview.errorText(error); }
    }
  });
  $('check-updates').addEventListener('click', async () => {
    const button = $('check-updates'); button.disabled = true;
    try {
      await preview.invoke('check_for_updates');
      const strings = preview.data.translations[preview.currentLanguage()] || preview.data.translations.en;
      $('result').textContent = strings.updateStarted || 'Update check started.';
    } catch (error) { $('result').textContent = preview.errorText(error); }
    finally { button.disabled = false; }
  });
  $('close').addEventListener('click', () => preview.invoke('close_settings').catch(e => $('result').textContent = preview.errorText(e)));
  setInterval(refresh, 1500);
})();
