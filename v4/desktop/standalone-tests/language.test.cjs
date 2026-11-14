'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'../..'),base=require(path.join(root,'i18n.js'));
function environment(){const nodes=['back','settings','local-files'].map(id=>({dataset:{titleKey:id==='local-files'?'localFiles':id},title:'',setAttribute(k,v){this[k]=v;}}));const text={textContent:'',getAttribute:()=> 'settings'};const globe={setAttribute(k,v){this[k]=v;}};const document={documentElement:{},getElementById:id=>id==='language-button'?globe:null,querySelectorAll:s=>s==='[data-i18n]'?[text]:s==='[data-title-key]'?nodes:[]};const c={window:{},document};vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(root,'desktop/dist/translations.js'),'utf8'),c);vm.runInContext(fs.readFileSync(path.join(root,'standalone-ui/language.js'),'utf8'),c);return {c,nodes,text,globe,document};}
test('V4 omits Russian while preserving every other language and the V3 source catalog',()=>{const {c}=environment(),d=c.window.VIBEZ_TRANSLATIONS;assert.equal(Object.keys(d.translations).length,33);assert.equal(d.options.length,34);assert.equal(JSON.stringify(d.translations),JSON.stringify(Object.fromEntries(Object.entries(base.TRANSLATIONS).filter(([code])=>code!=='ru'))));assert.equal(JSON.stringify(d.options),JSON.stringify(base.LANGUAGE_OPTIONS.filter(o=>o.code!=='ru')));for(const dictionary of [d.translations,d.extra,d.new])assert.equal(Object.hasOwn(dictionary,'ru'),false);assert.ok(base.TRANSLATIONS.ru);assert.ok(base.LANGUAGE_OPTIONS.some(o=>o.code==='ru'));});
test('live translation updates labels, accessible titles and RTL direction',()=>{const {c,nodes,text,globe,document}=environment();for(const [resolved,dir]of [['nl','ltr'],['en','ltr'],['de','ltr'],['ar','rtl']]){c.window.vibezLanguage.apply({language:resolved,resolved,site_locale:resolved,pending:false});assert.equal(document.documentElement.lang,resolved);assert.equal(document.documentElement.dir,dir);assert.equal(text.textContent,base.TRANSLATIONS[resolved].settings);assert.equal(nodes[1].title,base.TRANSLATIONS[resolved].settings);assert.equal(globe['aria-label'],c.window.VIBEZ_TRANSLATIONS.extra[resolved].languageButton);assert.notEqual(nodes[2].title,'localFiles');}});
test('every advertised language has all added interface and native-dialog translations',()=>{const {c}=environment(),catalog=c.window.VIBEZ_TRANSLATIONS;const keys=Object.keys(catalog.new.en).sort();for(const option of catalog.options.filter(o=>o.code!=='system')){const dictionary=catalog.new[option.code];assert.ok(dictionary,option.code);assert.deepEqual(Object.keys(dictionary).sort(),keys,option.code);for(const key of keys)assert.ok(typeof dictionary[key]==='string'&&dictionary[key].trim(),option.code+':'+key);c.window.vibezLanguage.apply({language:option.code,resolved:option.code,site_locale:'en'});for(const key of ['connectionConnected','connectionDisconnected','connectionOpenFiles','filesConnect','filesSave','chooseFolderConfirm'])assert.equal(c.window.vibezLanguage.t(key),dictionary[key]);}});
test('German, French, Japanese and Arabic use their own new status labels',()=>{const {c}=environment();for(const [resolved,word]of [['de','Verbunden'],['fr','Connecté'],['ja','接続済み'],['ar','متصل']]){c.window.vibezLanguage.apply({language:resolved,resolved,site_locale:'en'});assert.equal(c.window.vibezLanguage.t('connectionConnected'),word,resolved);assert.equal(c.window.vibezLanguage.t('settings'),base.TRANSLATIONS[resolved].settings);}c.window.vibezLanguage.apply({language:'unknown',resolved:'unknown',site_locale:'en'});assert.equal(c.window.vibezLanguage.t('chooseWorkspace'),'Choose folder');});
test('native dialogs and browser UI are bundled from the same translation catalog',()=>{const {c}=environment();assert.equal(fs.readFileSync(path.join(root,'desktop/src-tauri/src/language_extra.json'),'utf8').trim(),JSON.stringify(c.window.VIBEZ_TRANSLATIONS.new));});
test('language actions keep the same local-only IPC boundary',()=>{const c=JSON.parse(fs.readFileSync(path.join(root,'desktop/src-tauri/capabilities/standalone.json'),'utf8'));assert.deepEqual(c.webviews,['main','connector-panel']);assert.ok(c.permissions.includes('allow-language-get'));assert.ok(c.permissions.includes('allow-language-set'));assert.equal(c.remote,undefined);});

test('late responses cannot undo a newer language or a completed browser update',()=>{const {c}=environment();const l=c.window.vibezLanguage;l.apply({language:'de',resolved:'de',site_locale:'de',revision:3,pending:false});l.apply({language:'nl',resolved:'nl',site_locale:'nl',revision:2,pending:false});assert.equal(l.state().language,'de');l.apply({language:'de',resolved:'de',site_locale:'de',revision:3,pending:true});assert.equal(l.state().pending,false);});

test('existing dynamic errors follow Dutch, English and German without leaking a legacy Dutch message',()=>{
 const {c}=environment(),l=c.window.vibezLanguage;
 const raw='Kopiëren is niet gelukt. Controleer of de map en bestanden beschikbaar zijn.';
 for(const [locale,key]of [['en','fileImportFailed'],['de','fileImportFailed'],['nl','fileImportFailed'],['fr','projectRulesError'],['missing-locale','folderCreateFailed']]){
  l.apply({language:locale,resolved:locale,site_locale:'en'});
  const value=l.errorText(raw,key);
  assert.equal(value,locale==='nl'?raw:l.t(key),locale);
  if(locale!=='nl')assert.ok(!value.includes('Kopiëren'),locale);
 }
 l.apply({language:'de',resolved:'de',site_locale:'de'});
 assert.equal(l.errorText({code:'engine_stopped',message:'De verbinding is gestopt.'}),l.t('engineStopped'));
 assert.equal(l.errorText({message_key:'not-a-real-key',message:raw}),l.t('operationFailed'));
 assert.equal(l.errorText({message_en:'The selected folder is no longer available.',message:raw}),'The selected folder is no longer available.');
 assert.equal(l.errorText(null),'');
});

test('structured and encoded errors retain keys and arguments across live locale changes',()=>{
 const {c}=environment(),l=c.window.vibezLanguage;
 const key='folderCreated',args={folder:'User map <script>'},encoded=JSON.stringify({message_key:key,message_args:args,message:'Nederlandse oude tekst'});
 for(const locale of ['nl','en','de','missing-locale']){
  l.apply({language:locale,resolved:locale,site_locale:'en'});
  assert.equal(l.errorText(encoded),l.t(key).replace('{folder}',args.folder));
  assert.ok(!l.errorText(encoded).includes('Nederlandse oude tekst'));
 }
 // User-chosen names stay literal text and are never translated or inserted as HTML.
 assert.ok(l.errorText(encoded).includes(args.folder));
});

test('every active static HTML or JavaScript translation key has an English fallback',()=>{
 const {c}=environment(),catalog=c.window.VIBEZ_TRANSLATIONS;
 const english=key=>[catalog.translations,catalog.extra,catalog.new].some(d=>typeof d.en?.[key]==='string'&&d.en[key].trim());
 const files=['index.html','panel.html','chrome.js','panel.js','panel-tabs.js','alpha-updates.js','connection-status.js','language.js'];
 const keys=new Set();
 for(const file of files){
  const source=fs.readFileSync(path.join(root,'standalone-ui',file),'utf8');
  for(const match of source.matchAll(/data-(?:i18n|extra|v4|title-key|placeholder-key)="([^"]+)"/g))keys.add(match[1]);
  for(const match of source.matchAll(/\bt\('([A-Za-z][A-Za-z0-9_]*)'\)/g))keys.add(match[1]);
 }
 for(const key of keys)assert.ok(english(key),'Missing English UI fallback: '+key);
 assert.ok(english('exportConversation'));
});

test('the initial bundled documents use English until the saved language is ready',()=>{
 for(const file of ['index.html','panel.html']){
  const source=fs.readFileSync(path.join(root,'standalone-ui',file),'utf8');
  assert.match(source,/<html lang="en">/);
  assert.doesNotMatch(source,/Instellingen|Lokale bestanden|Hoofdmap|Annuleren|Sluiten|Open een project|Taalkeuze|Werkmap kiezen/);
 }
});
test('the file browser folder label follows a language change and is translated',()=>{const panel=fs.readFileSync(path.join(root,'standalone-ui/panel.js'),'utf8');assert.match(panel,/vibezLanguage\.onChange\(renderBrowserLocation\)/);const extra=JSON.parse(fs.readFileSync(path.join(root,'standalone-ui/language-extra.json'),'utf8'));for(const [code,dictionary]of Object.entries(extra))if(code!=='en')assert.notEqual(dictionary.browserLocation,extra.en.browserLocation,code);});
