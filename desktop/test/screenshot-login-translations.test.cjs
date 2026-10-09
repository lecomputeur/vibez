'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const rows=require('../screenshot-login-i18n.json');
test('guest note has exactly the existing 34 languages',()=>{
 const sandbox={window:{}};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../frontend/screenshot-login-translations.js'),'utf8'),sandbox);
 const translations=sandbox.window.VIBEZ_SCREENSHOT_LOGIN,languages=require('../../i18n.js').TRANSLATIONS;
 assert.deepEqual(Object.keys(rows).sort(),Object.keys(languages).sort());
 assert.deepEqual(Object.keys(translations).sort(),Object.keys(languages).sort());
 for(const [language,row]of Object.entries(rows)){assert.equal(translations[language],row[2]);assert.ok(row.every(s=>s.trim()));}
});
