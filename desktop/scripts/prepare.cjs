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
const screenshotKeys = ['screenshotFull','screenshotVisible','screenshotSelection','screenshotDrag','screenshotWorking','screenshotCancelled','screenshotHint'];
const screenshotText = {
  en:['Full page','Visible page','Selection','Drag to select • Esc to cancel','Creating screenshot…','Screenshot cancelled.','Choose full page, visible page, or a selection.'],
  nl:['Hele pagina','Zichtbare pagina','Selectie','Sleep om te selecteren • Esc om te annuleren','Schermafbeelding maken…','Schermafbeelding geannuleerd.','Kies hele pagina, zichtbare pagina of een selectie.'],
  de:['Ganze Seite','Sichtbarer Bereich','Auswahl','Zum Auswählen ziehen • Esc zum Abbrechen','Screenshot wird erstellt…','Screenshot abgebrochen.','Wähle ganze Seite, sichtbaren Bereich oder eine Auswahl.'],
  fr:['Page entière','Zone visible','Sélection','Faites glisser pour sélectionner • Échap pour annuler','Capture d’écran en cours…','Capture annulée.','Choisissez la page entière, la zone visible ou une sélection.'],
  es:['Página completa','Área visible','Selección','Arrastra para seleccionar • Esc para cancelar','Creando captura…','Captura cancelada.','Elige página completa, área visible o una selección.'],
  it:['Pagina intera','Area visibile','Selezione','Trascina per selezionare • Esc per annullare','Creazione screenshot…','Screenshot annullato.','Scegli pagina intera, area visibile o una selezione.'],
  pt:['Página inteira','Área visível','Seleção','Arraste para selecionar • Esc para cancelar','A criar captura…','Captura cancelada.','Escolha página inteira, área visível ou uma seleção.'],
  pl:['Cała strona','Widoczny obszar','Zaznaczenie','Przeciągnij, aby zaznaczyć • Esc, aby anulować','Tworzenie zrzutu…','Anulowano zrzut.','Wybierz całą stronę, widoczny obszar lub zaznaczenie.'],
  ru:['Вся страница','Видимая область','Выделение','Перетащите для выбора • Esc для отмены','Создание снимка…','Снимок отменён.','Выберите всю страницу, видимую область или выделение.'],
  uk:['Вся сторінка','Видима область','Виділення','Перетягніть для вибору • Esc для скасування','Створення знімка…','Знімок скасовано.','Виберіть всю сторінку, видиму область або виділення.'],
  tr:['Tam sayfa','Görünen alan','Seçim','Seçmek için sürükleyin • İptal için Esc','Ekran görüntüsü oluşturuluyor…','Ekran görüntüsü iptal edildi.','Tam sayfa, görünen alan veya seçim seçin.'],
  'zh-CN':['整个页面','可见区域','选择区域','拖动以选择 • 按 Esc 取消','正在创建截图…','已取消截图。','选择整个页面、可见区域或自选区域。'],
  'zh-TW':['整個頁面','可見區域','選取區域','拖曳以選取 • 按 Esc 取消','正在建立截圖…','已取消截圖。','選擇整個頁面、可見區域或自選區域。'],
  ja:['ページ全体','表示中の範囲','範囲選択','ドラッグして選択 • Escでキャンセル','スクリーンショットを作成中…','スクリーンショットをキャンセルしました。','ページ全体、表示中の範囲、または範囲選択から選べます。'],
  ko:['전체 페이지','보이는 영역','영역 선택','드래그하여 선택 • Esc로 취소','스크린샷 생성 중…','스크린샷이 취소되었습니다.','전체 페이지, 보이는 영역 또는 영역 선택을 선택하세요.'],
  hi:['पूरा पेज','दिखाई देने वाला भाग','चयन','चुनने के लिए खींचें • रद्द करने के लिए Esc','स्क्रीनशॉट बनाया जा रहा है…','स्क्रीनशॉट रद्द किया गया।','पूरा पेज, दिखाई देने वाला भाग या चयन चुनें।'],
  bn:['পুরো পৃষ্ঠা','দৃশ্যমান অংশ','নির্বাচন','নির্বাচন করতে টেনে নিন • বাতিল করতে Esc','স্ক্রিনশট তৈরি হচ্ছে…','স্ক্রিনশট বাতিল করা হয়েছে।','পুরো পৃষ্ঠা, দৃশ্যমান অংশ বা নির্বাচন বেছে নিন।'],
  pa:['ਪੂਰਾ ਸਫ਼ਾ','ਦਿਖਾਈ ਦੇਣ ਵਾਲਾ ਹਿੱਸਾ','ਚੋਣ','ਚੁਣਨ ਲਈ ਖਿੱਚੋ • ਰੱਦ ਕਰਨ ਲਈ Esc','ਸਕ੍ਰੀਨਸ਼ਾਟ ਬਣਾਇਆ ਜਾ ਰਿਹਾ ਹੈ…','ਸਕ੍ਰੀਨਸ਼ਾਟ ਰੱਦ ਕੀਤਾ ਗਿਆ।','ਪੂਰਾ ਸਫ਼ਾ, ਦਿਖਾਈ ਦੇਣ ਵਾਲਾ ਹਿੱਸਾ ਜਾਂ ਚੋਣ ਚੁਣੋ।'],
  mr:['संपूर्ण पृष्ठ','दिसणारा भाग','निवड','निवडण्यासाठी ड्रॅग करा • रद्द करण्यासाठी Esc','स्क्रीनशॉट तयार होत आहे…','स्क्रीनशॉट रद्द केला.','संपूर्ण पृष्ठ, दिसणारा भाग किंवा निवड निवडा.'],
  te:['మొత్తం పేజీ','కనిపించే భాగం','ఎంపిక','ఎంచుకోవడానికి డ్రాగ్ చేయండి • రద్దు చేయడానికి Esc','స్క్రీన్‌షాట్ రూపొందుతోంది…','స్క్రీన్‌షాట్ రద్దయింది.','మొత్తం పేజీ, కనిపించే భాగం లేదా ఎంపికను ఎంచుకోండి.'],
  ta:['முழுப் பக்கம்','காணும் பகுதி','தேர்வு','தேர்ந்தெடுக்க இழுக்கவும் • ரத்து செய்ய Esc','திரைப்பிடிப்பு உருவாக்கப்படுகிறது…','திரைப்பிடிப்பு ரத்து செய்யப்பட்டது.','முழுப் பக்கம், காணும் பகுதி அல்லது தேர்வைத் தேர்ந்தெடுக்கவும்.'],
  gu:['આખું પાનું','દેખાતો ભાગ','પસંદગી','પસંદ કરવા ખેંચો • રદ કરવા Esc','સ્ક્રીનશોટ બની રહ્યો છે…','સ્ક્રીનશોટ રદ થયો.','આખું પાનું, દેખાતો ભાગ અથવા પસંદગી પસંદ કરો.'],
  id:['Seluruh halaman','Area terlihat','Pilihan','Seret untuk memilih • Esc untuk batal','Membuat tangkapan layar…','Tangkapan layar dibatalkan.','Pilih seluruh halaman, area terlihat, atau pilihan.'],
  vi:['Toàn bộ trang','Vùng hiển thị','Vùng chọn','Kéo để chọn • Esc để hủy','Đang tạo ảnh chụp…','Đã hủy ảnh chụp.','Chọn toàn bộ trang, vùng hiển thị hoặc vùng chọn.'],
  th:['ทั้งหน้า','พื้นที่ที่มองเห็น','เลือกพื้นที่','ลากเพื่อเลือก • Esc เพื่อยกเลิก','กำลังสร้างภาพหน้าจอ…','ยกเลิกภาพหน้าจอแล้ว','เลือกทั้งหน้า พื้นที่ที่มองเห็น หรือเลือกพื้นที่'],
  fil:['Buong pahina','Nakikitang bahagi','Pili','I-drag para pumili • Esc para kanselahin','Gumagawa ng screenshot…','Kinansela ang screenshot.','Piliin ang buong pahina, nakikitang bahagi, o isang seleksyon.'],
  jv:['Kaca lengkap','Area sing katon','Pilihan','Seret kanggo milih • Esc kanggo mbatalake','Nggawe screenshot…','Screenshot dibatalake.','Pilih kaca lengkap, area sing katon, utawa pilihan.'],
  sw:['Ukurasa mzima','Sehemu inayoonekana','Uteuzi','Buruta ili kuchagua • Esc kughairi','Inatengeneza picha ya skrini…','Picha ya skrini imeghairiwa.','Chagua ukurasa mzima, sehemu inayoonekana au uteuzi.'],
  ha:['Dukkan shafi','Yankin da ake gani','Zaɓi','Ja don zaɓa • Esc don sokewa','Ana ƙirƙirar hoton allo…','An soke hoton allo.','Zaɓi dukkan shafi, yankin da ake gani ko zaɓi.'],
  am:['ሙሉ ገጽ','የሚታይ ክፍል','ምርጫ','ለመምረጥ ይጎትቱ • ለመሰረዝ Esc','ቅጽበታዊ ገጽ እይታ በመፍጠር ላይ…','ቅጽበታዊ ገጽ እይታ ተሰርዟል።','ሙሉ ገጽ፣ የሚታይ ክፍል ወይም ምርጫ ይምረጡ።'],
  ar:['الصفحة كاملة','الجزء المرئي','تحديد','اسحب للتحديد • Esc للإلغاء','جارٍ إنشاء لقطة الشاشة…','تم إلغاء لقطة الشاشة.','اختر الصفحة كاملة أو الجزء المرئي أو تحديدًا.'],
  he:['עמוד מלא','האזור הנראה','בחירה','גרור כדי לבחור • Esc לביטול','יוצר צילום מסך…','צילום המסך בוטל.','בחר עמוד מלא, אזור נראה או בחירה.'],
  fa:['کل صفحه','بخش قابل مشاهده','انتخاب','برای انتخاب بکشید • Esc برای لغو','در حال ساخت تصویر…','تصویر لغو شد.','کل صفحه، بخش قابل مشاهده یا انتخاب را انتخاب کنید.'],
  ur:['مکمل صفحہ','نظر آنے والا حصہ','انتخاب','منتخب کرنے کے لیے کھینچیں • منسوخ کرنے کے لیے Esc','اسکرین شاٹ بنایا جا رہا ہے…','اسکرین شاٹ منسوخ کر دیا گیا۔','مکمل صفحہ، نظر آنے والا حصہ یا انتخاب چنیں۔']
};
for (const code of Object.keys(TRANSLATIONS)) {
  if (!Array.isArray(stability[code]) || stability[code].length !== stabilityKeys.length) throw new Error(`Missing stability translations: ${code}`);
  Object.assign(previewData.translations[code], Object.fromEntries(stabilityKeys.map((key,i)=>[key,stability[code][i]])));
}
for (const [code, strings] of Object.entries(previewData.translations)) {
  strings.previewTitle='VibeZ 3'; strings.intro='VibeZ 3 · Rust / Tauri'; strings.isolatedStatus='VibeZ 3 · Rust / Tauri';
  const base=TRANSLATIONS[code]; strings.saved=base.saved||strings.saved;
  strings.updateManualHelp=base.openReleases||strings.updateManualHelp; strings.noDownloadHelp=base.updateFailed||strings.noDownloadHelp;
  const shot=screenshotText[code]||screenshotText.en;
  Object.assign(strings,Object.fromEntries(screenshotKeys.map((key,i)=>[key,shot[i]])));
}
Object.assign(previewData.translations.en,{saved:'Saved.',limits:'Screenshots use your operating system tools. Updates are installed manually. Global shortcuts and microphone/camera access are not enabled.',trayHint:'Enable only when the system tray icon is available.',updateManualHelp:'Open the published VibeZ 3 release and install the package for your system.',bridgeError:'The application connection is unavailable',returningVibe:'Back to Vibe. Your profile is preserved.',noDownloadHelp:'No published VibeZ 3 download was found for this platform.'});
Object.assign(previewData.translations.nl,{saved:'Opgeslagen.',limits:'Schermafbeeldingen gebruiken de hulpmiddelen van je besturingssysteem. Updates installeer je handmatig. Globale sneltoetsen en microfoon/camera zijn niet ingeschakeld.',trayHint:'Alleen inschakelen wanneer het systeemvakpictogram beschikbaar is.',updateManualHelp:'Open de gepubliceerde VibeZ 3-release en installeer het pakket voor je systeem.',bridgeError:'De verbinding met de toepassing is niet beschikbaar',returningVibe:'Terug naar Vibe. Je profiel blijft behouden.',noDownloadHelp:'Geen gepubliceerde VibeZ 3-download gevonden voor dit platform.'});
const screenshotMenu = JSON.parse(fs.readFileSync(path.join(project, 'screenshot-i18n.json'), 'utf8'));
const screenshotMenuKeys = ['screenshotAutoPaste','screenshotPaste','screenshotSavePng','screenshotNew','screenshotCopyFailed','screenshotCancel'];
if (JSON.stringify(Object.keys(screenshotMenu).sort()) !== JSON.stringify(Object.keys(TRANSLATIONS).sort())) throw new Error('Screenshot menu language codes differ');
for (const [code, strings] of Object.entries(previewData.translations)) {
  const values = screenshotMenu[code];
  if (!Array.isArray(values) || values.length !== screenshotMenuKeys.length || values.some(value => typeof value !== 'string' || !value.trim())) throw new Error(`Incomplete screenshot menu translation: ${code}`);
  Object.assign(strings, Object.fromEntries(screenshotMenuKeys.map((key,i) => [key,values[i]])));
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
