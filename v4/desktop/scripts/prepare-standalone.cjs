'use strict';
const fs=require('node:fs'),path=require('node:path');
const project=path.resolve(__dirname,'..'),root=path.resolve(project,'..'),dist=path.join(project,'dist');
fs.rmSync(dist,{recursive:true,force:true});fs.mkdirSync(dist,{recursive:true});
for(const name of ['index.html','chrome.js','connection-status.js','connection-feedback.js','panel.html','panel-tabs.js','panel.js','alpha-updates.js','panel.css','style.css','language.js','toolbar.css'])fs.copyFileSync(path.join(root,'standalone-ui',name),path.join(dist,name));
fs.copyFileSync(path.join(root,'shell.css'),path.join(dist,'shell.css'));
fs.copyFileSync(path.join(project,'frontend/preview.css'),path.join(dist,'preview.css'));
fs.copyFileSync(path.join(root,'icon.png'),path.join(dist,'icon.png'));
// The V3 screenshot dialog (visible page, full page, selection; paste, copy, save).
for(const name of ['screenshot.html','screenshot.js','screenshot.css','common.js','screenshot-file-translations.js','screenshot-login-translations.js'])fs.copyFileSync(path.join(project,'frontend',name),path.join(dist,name));
console.log('Prepared familiar VibeZ toolbar and optional local-files panel.');

const base=require(path.join(root,'i18n.js')),extra=require(path.join(project,'preview-i18n.json')),add=require(path.join(root,'standalone-ui/language-extra.json'));
// V4's language choice is independent of the preserved V3 dictionaries.
const options=base.LANGUAGE_OPTIONS.filter(option=>option.code!=='ru');
const withoutRussian=dictionary=>Object.fromEntries(Object.entries(dictionary).filter(([code])=>code!=='ru'));
const translations=withoutRussian(base.TRANSLATIONS),preview=withoutRussian(extra.translations),added=withoutRussian(add);
fs.writeFileSync(path.join(dist,'translations.js'),'window.VIBEZ_TRANSLATIONS='+JSON.stringify({options,translations,extra:preview,new:added})+';\n');
fs.writeFileSync(path.join(dist,'preview-translations.js'),'window.VIBEZ_PREVIEW_TRANSLATIONS='+JSON.stringify({translations:preview})+';\n');
fs.writeFileSync(path.join(project,'src-tauri/src/language_options.json'),JSON.stringify(options,null,2)+'\n');
fs.writeFileSync(path.join(project,'src-tauri/src/language_extra.json'),JSON.stringify(added)+'\n');
