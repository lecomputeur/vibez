//! VibeZ language preference and Mistral locale preparation, independent of chat data.
use super::*;
use std::sync::atomic::AtomicBool;
#[cfg(target_os="linux")]
use webkit2gtk::{WebContextExt,WebViewExt};
#[path="language_retry.rs"] mod retry;
#[derive(serde::Serialize,serde::Deserialize)]
struct Preference {language:String}
pub struct Language {
    selected:Mutex<String>,file:std::path::PathBuf,
    generation:AtomicU64,completed:AtomicU64,loading:AtomicBool,
    gate:tokio::sync::Mutex<()>,applying:AtomicBool,
    // While VibeZ runs Mistral's own connector pages, the site is English so
    // the automation recognises the same labels for every app language.
    work_english:AtomicBool,
}
fn valid(value:&str)->bool {
    let options:Value=serde_json::from_str(include_str!("language_options.json")).expect("bundled language options");
    options.as_array().is_some_and(|a|a.iter().any(|v|v["code"]==value))
}
fn normalize(raw:&str)->String {
    let raw=raw.replace('_',"-").to_ascii_lowercase();
    if raw.starts_with("zh") {return if ["tw","hk","mo","hant"].iter().any(|v|raw.contains(v)){"zh-TW"}else{"zh-CN"}.into();}
    let code=raw.split(['-','.']).next().unwrap_or("en");
    if code!="system" && valid(code){code.into()}else{"en".into()}
}
fn site_locale(code:&str)->String {
    let code=normalize(code);
    match code.as_str(){"en"|"nl"|"fr"|"de"|"es"|"pl"|"it"|"pt"|"ar"|"uk"=>code,_=>"en".into()}
}
fn os_locale()->String {sys_locale::get_locale().unwrap_or_else(||"en".into())}
fn translated(locale:&str,key:&str)->String {
    static CATALOG:std::sync::OnceLock<Value>=std::sync::OnceLock::new();
    let catalog=CATALOG.get_or_init(||serde_json::from_str(include_str!("language_extra.json")).expect("bundled UI translations"));
    catalog[locale][key].as_str().or_else(||catalog["en"][key].as_str()).unwrap_or(key).to_owned()
}
pub fn text(app:&tauri::AppHandle,key:&str)->String {translated(&app.state::<Language>().resolved(),key)}
impl Language {
    pub fn load(config:&std::path::Path)->Result<Self,String> {
        let file=config.join("language.json");
        let source=if file.exists(){file.clone()}else{config.join("settings.json")};
        let selected=if source.exists(){
            let raw=std::fs::read(source).map_err(err)?;
            if raw.len()>1_000_000{return Err("The language settings are too large".into());}
            serde_json::from_slice::<Value>(&raw).ok().and_then(|v|v["language"].as_str().filter(|v|valid(v)).map(str::to_owned)).unwrap_or_else(||"system".into())
        }else{"system".into()};
        Ok(Self{selected:Mutex::new(selected),file,generation:AtomicU64::new(1),completed:AtomicU64::new(0),loading:AtomicBool::new(false),gate:tokio::sync::Mutex::new(()),applying:AtomicBool::new(false),work_english:AtomicBool::new(false)})
    }
    fn resolved(&self)->String {let s=self.selected.lock().unwrap();normalize(if s.as_str()=="system"{return normalize(&os_locale());}else{&s})}
    fn save(&self,selected:&str)->Result<(),String> {
        static SERIAL:AtomicU64=AtomicU64::new(1);
        let temp=self.file.with_extension(format!("tmp-{}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::SeqCst)));
        let mut options=std::fs::OpenOptions::new();options.create_new(true).write(true);
        #[cfg(unix)] {use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
        let mut f=options.open(&temp).map_err(err)?;
        f.write_all(serde_json::to_string(&Preference{language:selected.into()}).map_err(err)?.as_bytes()).map_err(err)?;f.sync_all().map_err(err)?;
        std::fs::rename(temp,&self.file).map_err(err)
    }
}
pub fn info(app:&tauri::AppHandle)->Value {
    let l=app.state::<Language>();let selected=l.selected.lock().unwrap();let language=selected.clone();
    let os=os_locale();let resolved=normalize(if language=="system"{&os}else{&language});
    let revision=l.generation.load(Ordering::SeqCst);let pending=revision!=l.completed.load(Ordering::SeqCst);drop(selected);
    json!({"language":language,"resolved":resolved,"os_locale":os,"site_locale":site_locale(&resolved),"pending":pending,"revision":revision})
}

fn announce(app:&tauri::AppHandle) {
    let info=info(app);
    for label in ["main","connector-panel"]{let _=app.emit_to(EventTarget::Webview{label:label.into()},"language-state",info.clone());}
}
#[cfg(target_os="linux")]
async fn preferred(view:&Webview,locale:&str)->Result<(),String> {
    let locale=locale.to_owned();let(tx,rx)=tokio::sync::oneshot::channel();
    view.with_webview(move |p|{let ok=if let Some(c)=p.inner().context(){c.set_preferred_languages(&[&locale]);true}else{false};let _=tx.send(ok);}).map_err(err)?;
    if tokio::time::timeout(std::time::Duration::from_secs(3),rx).await.map_err(err)?.map_err(err)?{Ok(())}else{Err("The browser language could not be set".into())}
}
// WebView2/WKWebView keep their system browser-language preferences. The same
// Mistral NEXT_LOCALE cookie below still applies the selected site language.
#[cfg(not(target_os="linux"))]
async fn preferred(_view:&Webview,_locale:&str)->Result<(),String> {Ok(())}
async fn prepare(view:&Webview,locale:&str)->Result<(),String> {
    preferred(view,locale).await?;
    // Only the locale cookie is changed; authentication cookies are preserved.
    for host in ["https://chat.mistral.ai/","https://vibe.mistral.ai/"]{
        for c in view.cookies_for_url(host.parse().map_err(err)?).map_err(err)?{if c.name()=="NEXT_LOCALE"{view.delete_cookie(c).map_err(err)?;}}
    }
    for domain in ["chat.mistral.ai",".chat.mistral.ai","vibe.mistral.ai",".vibe.mistral.ai","mistral.ai",".mistral.ai"] {
        let c=tauri::webview::Cookie::build(("NEXT_LOCALE","")).domain(domain).path("/").secure(true).build();let _=view.delete_cookie(c);
    }
    for domain in ["chat.mistral.ai","vibe.mistral.ai",".mistral.ai"]{
        let c=tauri::webview::Cookie::build(("NEXT_LOCALE",locale.to_owned())).domain(domain).path("/").secure(true).same_site(tauri::webview::cookie::SameSite::Lax).build();view.set_cookie(c).map_err(err)?;
    }
    for _ in 0..30 {
        let cookies=view.cookies_for_url("https://chat.mistral.ai/".parse().unwrap()).map_err(err)?;
        let values:Vec<_>=cookies.iter().filter(|c|c.name()=="NEXT_LOCALE").collect();
        if !values.is_empty()&&values.iter().all(|c|c.value()==locale){return Ok(());}
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    }
    Err("The browser language could not be confirmed yet".into())
}
fn eligible(url:&url::Url)->bool {
    safe_https(url)&&matches!(url.host_str(),Some("chat.mistral.ai"|"vibe.mistral.ai")) && !["/auth","/login","/oauth","/signin","/sign-in"].iter().any(|p|url.path().starts_with(p))
}
fn popup_active(app:&tauri::AppHandle)->bool {
    app.state::<Bridge>().login_labels.lock().map(|labels|labels.iter().any(|l|app.get_webview_window(l).is_some())).unwrap_or(true)
}
async fn prepare_current(app:&tauri::AppHandle,view:&Webview,generation:u64)->Result<bool,String> {
    let l=app.state::<Language>();let locale=current_site_locale(&l);
    let outcome=retry::prepare(||prepare(view,&locale),||l.generation.load(Ordering::SeqCst)==generation,|_,_|{},std::time::Duration::from_millis(200)).await?;
    Ok(outcome==retry::Outcome::Ready)
}
fn current_site_locale(l:&Language)->String {
    if l.work_english.load(Ordering::SeqCst){"en".into()}else{site_locale(&l.resolved())}
}
/// Switch only the Mistral locale cookie for the Work connector automation:
/// English while it runs, the user's site language afterwards. Open pages are
/// never reloaded here; the next page load uses the restored language.
pub async fn work_english(app:&tauri::AppHandle,view:&Webview,on:bool)->Result<(),String> {
    let l=app.state::<Language>();let _gate=l.gate.lock().await;
    l.work_english.store(on,Ordering::SeqCst);
    let locale=current_site_locale(&l);
    retry::prepare(||prepare(view,&locale),||true,|_,_|{},std::time::Duration::from_millis(200)).await.map(|_|())
}
pub async fn bootstrap(app:&tauri::AppHandle,view:&Webview,target:url::Url)->Result<(),String> {
    let l=app.state::<Language>();let _gate=l.gate.lock().await;
    let mut prepared=false;
    for _ in 0..3 {
        let generation=l.generation.load(Ordering::SeqCst);
        match prepare_current(app,view,generation).await {
            Ok(true)=>{l.completed.store(generation,Ordering::SeqCst);prepared=true;break;},
            Ok(false)=>continue,
            Err(_)=>break,
        }
    }
    if !prepared {for label in ["main","connector-panel"]{let _=app.emit_to(EventTarget::Webview{label:label.into()},"language-warning",true);}}
    #[cfg(all(feature="native-smoke",target_os="linux"))]
    if super::smoke::enabled(){announce(app);return Ok(());}
    view.navigate(target).map_err(err)?;announce(app);Ok(())
}
async fn apply(app:tauri::AppHandle) {
    let l=app.state::<Language>();let _gate=l.gate.lock().await;
    let generation=l.generation.load(Ordering::SeqCst);
    if generation==l.completed.load(Ordering::SeqCst)||l.loading.load(Ordering::SeqCst)||popup_active(&app){return;}
    let Some(view)=app.get_webview("mistral-web")else{return;};
    let Ok(url)=view.url()else{return;};if !eligible(&url){return;}
    let result=prepare_current(&app,&view,generation).await;
    if matches!(result,Ok(true)) && l.generation.load(Ordering::SeqCst)==generation && !l.loading.load(Ordering::SeqCst) && !popup_active(&app) && view.url().ok()==Some(url.clone()) {
        #[cfg(all(feature="native-smoke",target_os="linux"))]
        if super::smoke::enabled(){let locale=site_locale(&l.resolved());let _=view.eval(format!("document.documentElement.lang={}",serde_json::to_string(&locale).unwrap()));l.completed.store(generation,Ordering::SeqCst);announce(&app);return;}
        if view.navigate(url).is_ok(){l.completed.store(generation,Ordering::SeqCst);announce(&app);}
    }else if result.is_err(){for label in ["main","connector-panel"]{let _=app.emit_to(EventTarget::Webview{label:label.into()},"language-warning",true);}}
}
pub fn loaded(app:&tauri::AppHandle,finished:bool) {app.state::<Language>().loading.store(!finished,Ordering::SeqCst);if finished{retry_pending(app);}}
pub fn retry_pending(app:&tauri::AppHandle) {let l=app.state::<Language>();if l.generation.load(Ordering::SeqCst)!=l.completed.load(Ordering::SeqCst) && !l.applying.swap(true,Ordering::SeqCst){let app=app.clone();tauri::async_runtime::spawn(async move{apply(app.clone()).await;app.state::<Language>().applying.store(false,Ordering::SeqCst);});}}
#[tauri::command]
pub fn language_get(webview:Webview,app:tauri::AppHandle)->Result<Value,String>{require_local(&webview)?;Ok(info(&app))}
#[tauri::command]
pub async fn language_set(webview:Webview,app:tauri::AppHandle,language:String)->Result<Value,String>{
    require_local(&webview)?;if !valid(&language){return Err("Onbekende taal".into());}
    let l=app.state::<Language>();
    {let mut selected=l.selected.lock().map_err(err)?;l.save(&language)?;*selected=language;l.generation.fetch_add(1,Ordering::SeqCst);}
    announce(&app);retry_pending(&app);Ok(info(&app))
}
#[cfg(test)]mod tests{
 use super::*;
 #[test]fn locales_preserve_chinese_and_system_variants(){assert_eq!(normalize("nl_NL.UTF-8"),"nl");assert_eq!(normalize("zh-Hant-TW"),"zh-TW");assert_eq!(normalize("zh_CN"),"zh-CN");assert_eq!(normalize("unknown"),"en");assert!(!valid("../nl"));assert!(valid("system"));}
 #[test]fn native_dialog_labels_use_the_selected_locale(){assert_eq!(translated("de","chooseWorkspace"),"Ordner auswählen");assert_eq!(translated("fr","cancel"),"Annuler");assert_eq!(translated("unknown","cancel"),"Cancel");assert_eq!(translated("en","exportConversation"),"Export conversation");assert_eq!(translated("nl","exportConversation"),"Gesprek exporteren");assert_eq!(translated("unknown","exportConversation"),"Export conversation");}
 #[test]fn removed_russian_is_not_selectable_and_its_system_locale_falls_back_to_english(){assert!(!valid("ru"));assert_eq!(normalize("ru_RU.UTF-8"),"en");assert_eq!(translated("ru","chooseWorkspace"),"Choose folder");}
 #[test]fn a_previous_russian_preference_falls_back_without_rewriting_user_settings(){let root=std::env::temp_dir().join(format!("vibez-removed-language-{}",std::process::id()));std::fs::create_dir_all(&root).unwrap();let file=root.join("language.json");let original=r#"{"language":"ru"}"#;std::fs::write(&file,original).unwrap();let l=Language::load(&root).unwrap();assert_eq!(*l.selected.lock().unwrap(),"system");assert_eq!(std::fs::read_to_string(&file).unwrap(),original);std::fs::remove_dir_all(root).unwrap();}
 #[test]fn mistral_mapping_retains_the_v3_fallback(){assert_eq!(site_locale("nl-NL"),"nl");assert_eq!(site_locale("de_DE"),"de");assert_eq!(site_locale("ar"),"ar");assert_eq!(site_locale("ja"),"en");}
 #[test]fn auth_and_external_pages_never_reload(){for u in ["https://auth.mistral.ai/","https://accounts.google.com/","https://chat.mistral.ai/auth/callback","about:blank","https://example.org/"]{assert!(!eligible(&u.parse().unwrap()));}assert!(eligible(&"https://chat.mistral.ai/work/projects/123".parse().unwrap()));}
 #[test]fn preference_survives_and_leaves_legacy_settings_untouched(){let root=std::env::temp_dir().join(format!("vibez-language-{}",std::process::id()));std::fs::create_dir_all(&root).unwrap();let file=root.join("settings.json");std::fs::write(&file,r#"{"language":"nl","zoom_factor":1.2}"#).unwrap();let l=Language::load(&root).unwrap();assert_eq!(*l.selected.lock().unwrap(),"nl");l.save("de").unwrap();assert_eq!(*Language::load(&root).unwrap().selected.lock().unwrap(),"de");assert_eq!(std::fs::read_to_string(file).unwrap(),r#"{"language":"nl","zoom_factor":1.2}"#);std::fs::remove_dir_all(root).unwrap();}
}
