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
console.log(`Prepared preview assets and ${Object.keys(TRANSLATIONS).length} existing language bundles.`);
