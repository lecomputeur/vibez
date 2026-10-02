'use strict';
const fs = require('node:fs');
const path = require('node:path');
const project = path.resolve(__dirname, '..');
const root = path.resolve(project, '..');
const out = path.join(project, 'dist');
fs.mkdirSync(out, { recursive: true });
for (const name of fs.readdirSync(path.join(project, 'frontend'))) {
  fs.copyFileSync(path.join(project, 'frontend', name), path.join(out, name));
}
// Read existing VibeZ assets without changing any Electron source or settings.
fs.copyFileSync(path.join(root, 'shell.css'), path.join(out, 'shell.css'));
fs.copyFileSync(path.join(root, 'icon.png'), path.join(out, 'icon.png'));
fs.mkdirSync(path.join(project, 'src-tauri/icons'), { recursive: true });
fs.copyFileSync(path.join(root, 'icon.png'), path.join(project, 'src-tauri/icons/icon.png'));
const { LANGUAGE_OPTIONS, TRANSLATIONS } = require(path.join(root, 'i18n.js'));
const data = { options: LANGUAGE_OPTIONS, translations: TRANSLATIONS };
fs.writeFileSync(path.join(out, 'translations.json'), JSON.stringify(data));
fs.writeFileSync(path.join(out, 'translations.js'), 'window.VIBEZ_TRANSLATIONS = ' + JSON.stringify(data) + ';\n');
const previewData = JSON.parse(fs.readFileSync(path.join(project, 'preview-i18n.json'), 'utf8'));
const baseLanguages = Object.keys(TRANSLATIONS).sort();
const previewLanguages = Object.keys(previewData.translations || {}).sort();
if (JSON.stringify(baseLanguages) !== JSON.stringify(previewLanguages)) {
  throw new Error('Preview translations must contain exactly the same 34 languages as VibeZ.');
}
const previewKeys = Object.keys(previewData.translations.en || {});
for (const [code, strings] of Object.entries(previewData.translations)) {
  if (JSON.stringify(Object.keys(strings)) !== JSON.stringify(previewKeys)) {
    throw new Error(`Preview translation keys do not match English for ${code}.`);
  }
}
fs.writeFileSync(path.join(out, 'preview-translations.json'), JSON.stringify(previewData));
fs.writeFileSync(path.join(out, 'preview-translations.js'), 'window.VIBEZ_PREVIEW_TRANSLATIONS = ' + JSON.stringify(previewData) + ';\n');
console.log(`Prepared preview assets and ${baseLanguages.length} complete language bundles.`);
