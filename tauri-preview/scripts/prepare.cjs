'use strict';
const fs = require('node:fs');
const path = require('node:path');
const project = path.resolve(__dirname, '..');
const root = path.resolve(project, '..');
const out = path.join(project, 'dist');
fs.mkdirSync(out, { recursive: true });
for (const name of fs.readdirSync(path.join(project, 'frontend'))) fs.copyFileSync(path.join(project, 'frontend', name), path.join(out, name));
// Stable Electron assets are read-only inputs.
fs.copyFileSync(path.join(root, 'shell.css'), path.join(out, 'shell.css'));
fs.copyFileSync(path.join(root, 'icon.png'), path.join(out, 'icon.png'));
fs.mkdirSync(path.join(project, 'src-tauri/icons'), { recursive: true });
// Generate platform-sized icons with the already installed Tauri tool (no network).
// A single 512px icon exceeds GTK/X11's _NET_WM_ICON payload limit.
require('node:child_process').execFileSync(process.execPath, [
  path.join(project, 'node_modules/@tauri-apps/cli/tauri.js'), 'icon',
  path.join(root, 'icon.png'), '--output', path.join(project, 'src-tauri/icons'),
], { stdio: 'pipe' });
// The generator also emits icon.png. Keep the original 512px launcher/tray
// artwork byte-for-byte while retaining its generated 128px native variant.
fs.copyFileSync(path.join(root, 'icon.png'), path.join(project, 'src-tauri/icons/icon.png'));
const { LANGUAGE_OPTIONS, TRANSLATIONS } = require(path.join(root, 'i18n.js'));
const data = { options: LANGUAGE_OPTIONS, translations: TRANSLATIONS };
fs.writeFileSync(path.join(out, 'translations.json'), JSON.stringify(data));
fs.writeFileSync(path.join(out, 'translations.js'), 'window.VIBEZ_TRANSLATIONS = ' + JSON.stringify(data) + ';\n');
const previewData = JSON.parse(fs.readFileSync(path.join(project, 'preview-i18n.json'), 'utf8'));
const stability = JSON.parse(fs.readFileSync(path.join(project, 'stability-i18n.json'), 'utf8'));
const stabilityKeys = ['settingsConflict','settingsRecovered','siteLanguageFailed','trayUnavailable'];
for (const code of Object.keys(TRANSLATIONS)) {
  if (!Array.isArray(stability[code]) || stability[code].length !== stabilityKeys.length) throw new Error(`Missing stability translations: ${code}`);
  Object.assign(previewData.translations[code], Object.fromEntries(stabilityKeys.map((key,i)=>[key,stability[code][i]])));
}
const baseLanguages = Object.keys(TRANSLATIONS).sort();
if (JSON.stringify(baseLanguages) !== JSON.stringify(Object.keys(previewData.translations).sort())) throw new Error('Preview language codes differ');
const keys = Object.keys(previewData.translations.en).sort();
for (const [code, strings] of Object.entries(previewData.translations)) {
  if (JSON.stringify(Object.keys(strings).sort()) !== JSON.stringify(keys)) throw new Error(`Preview translation keys differ: ${code}`);
}
fs.writeFileSync(path.join(out, 'preview-translations.json'), JSON.stringify(previewData));
fs.writeFileSync(path.join(out, 'preview-translations.js'), 'window.VIBEZ_PREVIEW_TRANSLATIONS = ' + JSON.stringify(previewData) + ';\n');
console.log(`Prepared preview assets and ${baseLanguages.length} complete language bundles.`);
