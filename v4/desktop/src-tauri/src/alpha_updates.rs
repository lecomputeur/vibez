//! Independent Alpha updates: never consult the stable V3 release channel.
use super::*;
use semver::Version;
use std::{path::{Path,PathBuf},sync::{OnceLock,atomic::{AtomicBool,Ordering}},time::Duration};
use tauri_plugin_updater::UpdaterExt;

const ENDPOINT:&str="https://github.com/lecomputeur/vibez/releases/download/v4-alpha-channel/alpha.json";
const MAX_PACKAGE:u64=512*1024*1024;
static BUSY:AtomicBool=AtomicBool::new(false);
static STARTED:AtomicBool=AtomicBool::new(false);
fn stored()->&'static Mutex<Value>{static S:OnceLock<Mutex<Value>>=OnceLock::new();S.get_or_init(||Mutex::new(json!({"status":"idle","automatic":true,"channel":"v4-alpha"})))}
// V4 Alpha, Beta, release candidate and final 4.x releases share this channel,
// so an Alpha installation moves on to the Beta without being reinstalled.
pub fn alpha_version(value:&Version)->bool {
    let pre=value.pre.as_str();
    let numbered=|n:&str|!n.is_empty()&&n.len()<=6&&!n.starts_with('0')&&n.bytes().all(|c|c.is_ascii_digit());
    value.major==4&&value.build.is_empty()&&(pre.is_empty()||["alpha.","beta.","rc."].iter().any(|stage|pre.strip_prefix(stage).is_some_and(numbered)))
}
#[cfg(test)]
#[path = "alpha_update_client_tests.rs"]
mod client_tests;
fn newer(current:&Version,next:&Version)->bool{alpha_version(next)&&next>current}
fn system_mode()->bool {
    cfg!(target_os="linux")&&!is_flatpak()&&std::env::var_os("APPIMAGE").is_none()&&
        Path::new("/usr/lib/vibez4-alpha-updater/update.py").is_file()
}
/// A Microsoft Store (MSIX) install: the Store delivers updates, VibeZ never installs one itself.
#[cfg(target_os="windows")]
pub fn store_packaged()->bool{
    #[link(name="kernel32")]extern "system"{fn GetCurrentPackageFullName(length:*mut u32,name:*mut u16)->i32;}
    // ERROR_INSUFFICIENT_BUFFER (122) with a length means the process has a package identity.
    let mut length=0u32;unsafe{GetCurrentPackageFullName(&mut length,std::ptr::null_mut())==122&&length>0}
}
#[cfg(not(target_os="windows"))]pub fn store_packaged()->bool{false}
fn native_mode()->bool {
    #[cfg(target_os="linux")]{return !is_flatpak()&&std::env::var_os("APPIMAGE").is_some();}
    #[cfg(not(target_os="linux"))]{true}
}
fn update_state(app:&tauri::AppHandle,value:Value){
    if let Ok(mut state)=stored().lock(){*state=value.clone();}
    for label in ["main","connector-panel"]{let _=app.emit_to(EventTarget::Webview{label:label.into()},"alpha-update",value.clone());}
}
pub fn state()->Value {
    #[cfg(target_os="linux")] if is_flatpak(){return alpha_flatpak_update::state();}
    if store_packaged(){return json!({"status":"automatic","automatic":true,"kind":"store","channel":"store","current":env!("CARGO_PKG_VERSION")});}
    let mut value=stored().lock().map(|v|v.clone()).unwrap_or_else(|_|json!({"status":"error"}));
    if system_mode(){
        value=json!({"status":"automatic","automatic":true,"kind":"system","channel":"v4-alpha"});
        if let Ok(bytes)=std::fs::read("/var/lib/vibez4-alpha-updater/status.json"){
            if bytes.len()<=8192{if let Ok(status)=serde_json::from_slice::<Value>(&bytes){if status["channel"]=="v4-alpha"{
                value["status"]=status["status"].clone();value["available"]=status["available"].clone();value["error"]=status["error"].clone();
            }}}
        }
    }
    value["current"]=json!(env!("CARGO_PKG_VERSION"));value
}
fn directory(app:&tauri::AppHandle)->Result<PathBuf,String>{Ok(app.path().app_cache_dir().map_err(err)?.join("alpha-update"))}
fn updater(app:&tauri::AppHandle)->Result<tauri_plugin_updater::Updater,String>{
    app.updater_builder().endpoints(vec![ENDPOINT.parse().map_err(err)?]).map_err(err)?
        .pubkey(include_str!("../alpha-updater.pub").trim())
        .version_comparator(|current,release|newer(&current,&release.version))
        .timeout(Duration::from_secs(120)).build().map_err(err)
}
fn validate_update(update:&tauri_plugin_updater::Update)->Result<(),String>{
    let version=Version::parse(&update.version).map_err(err)?;
    if !alpha_version(&version){return Err("This is not a V4 update".into());}
    let url=&update.download_url;
    let prefix=format!("/lecomputeur/vibez/releases/download/v{}/VibeZ-{}-",update.version,update.version);
    if url.scheme()!="https"||url.host_str()!=Some("github.com")||url.port_or_known_default()!=Some(443)||
        !url.username().is_empty()||url.password().is_some()||url.query().is_some()||url.fragment().is_some()||!url.path().starts_with(&prefix){
        return Err("The Alpha update has an unknown download address".into());
    }
    Ok(())
}
fn private_write(path:&Path,bytes:&[u8])->Result<(),String>{
    let tmp=path.with_extension("tmp");let _=std::fs::remove_file(&tmp);
    let mut opts=std::fs::OpenOptions::new();opts.write(true).create_new(true);
    #[cfg(unix)]{use std::os::unix::fs::OpenOptionsExt;opts.mode(0o600);}
    let mut file=opts.open(&tmp).map_err(err)?;file.write_all(bytes).map_err(err)?;file.sync_all().map_err(err)?;
    std::fs::rename(tmp,path).map_err(err)
}
async fn check_inner(app:&tauri::AppHandle)->Result<(),String>{
    if store_packaged(){update_state(app,state());return Ok(());}
    if system_mode(){update_state(app,state());return Ok(());}
    if !native_mode(){return Err("The Alpha update service is missing. Install the full V4 Alpha package.".into());}
    update_state(app,json!({"status":"checking","automatic":true,"channel":"v4-alpha"}));
    let Some(update)=updater(app)?.check().await.map_err(err)? else{
        update_state(app,json!({"status":"current","automatic":true,"channel":"v4-alpha"}));return Ok(());
    };
    validate_update(&update)?;
    update_state(app,json!({"status":"downloading","automatic":true,"available":update.version,"channel":"v4-alpha"}));
    let bytes=update.download(|_,_|{},||{}).await.map_err(err)?;
    if bytes.len()as u64>MAX_PACKAGE{return Err("De Alpha-update is te groot".into());}
    update.verify(&bytes).map_err(err)?;
    let root=directory(app)?;std::fs::create_dir_all(&root).map_err(err)?;
    #[cfg(unix)]{use std::os::unix::fs::PermissionsExt;std::fs::set_permissions(&root,std::fs::Permissions::from_mode(0o700)).map_err(err)?;}
    private_write(&root.join("package"),&bytes)?;
    private_write(&root.join("release.json"),&serde_json::to_vec(&update.raw_json).map_err(err)?)?;
    update_state(app,json!({"status":"ready","automatic":true,"restart_required":true,"available":update.version,"channel":"v4-alpha"}));
    Ok(())
}
pub fn check(app:&tauri::AppHandle){
    #[cfg(target_os="linux")] if is_flatpak(){alpha_flatpak_update::start(app);return;}
    if BUSY.swap(true,Ordering::SeqCst){return;}
    let app=app.clone();tauri::async_runtime::spawn(async move{
        if let Err(error)=check_inner(&app).await{update_state(&app,json!({"status":"error","automatic":true,"channel":"v4-alpha","error":error}));}
        BUSY.store(false,Ordering::SeqCst);
    });
}
/// Called before the first chat window is created, never while someone types.
pub fn apply_staged(app:&tauri::AppHandle)->Result<bool,String>{
    // A DEB/RPM installation must never fall back to a graphical root prompt.
    // Its signed package manager service is the only installation path.
    if store_packaged()||system_mode()||is_flatpak()||!native_mode(){return Ok(false);}
    let root=directory(app)?;let meta=root.join("release.json");let package=root.join("package");
    if !meta.exists(){return Ok(false);}
    for (path,max) in [(&meta,1024*1024),(&package,MAX_PACKAGE)]{
        let info=std::fs::symlink_metadata(path).map_err(err)?;
        if !info.file_type().is_file()||info.len()>max{return Err("The saved Alpha update has changed".into());}
    }
    let raw:Value=serde_json::from_slice(&std::fs::read(&meta).map_err(err)?).map_err(err)?;
    let Some(update)=updater(app)?.restore_update(raw).map_err(err)? else{
        let _=std::fs::remove_file(meta);let _=std::fs::remove_file(package);return Ok(false);
    };
    validate_update(&update)?;let bytes=std::fs::read(&package).map_err(err)?;update.verify(&bytes).map_err(err)?;
    update.install(&bytes).map_err(err)?;
    let _=std::fs::remove_file(meta);let _=std::fs::remove_file(package);Ok(true)
}
pub fn startup(app:&tauri::AppHandle){
    match apply_staged(app){Ok(true)=>app.restart(),Ok(false)=>{},Err(error)=>update_state(app,json!({"status":"error","automatic":true,"channel":"v4-alpha","error":error}))}
}
pub fn start(app:&tauri::AppHandle){
    if STARTED.swap(true,Ordering::SeqCst){return;}
    #[cfg(target_os="linux")] if is_flatpak(){alpha_flatpak_update::start(app);return;}
    if store_packaged(){return;}
    if system_mode(){
        // The root service checks every five minutes and writes its status file;
        // show what it found without waiting for someone to press Check now.
        let app=app.clone();tauri::async_runtime::spawn(async move{
            let mut last=Value::Null;
            loop{let now=state();if now!=last{update_state(&app,now.clone());last=now;}tokio::time::sleep(Duration::from_secs(60)).await;}
        });
        return;
    }
    let app=app.clone();tauri::async_runtime::spawn(async move{
        tokio::time::sleep(Duration::from_secs(15)).await;
        loop{check(&app);tokio::time::sleep(Duration::from_secs(6*60*60)).await;}
    });
}
/// Shares a lock with the root updater, closing the launch/install race.
#[cfg(target_os="linux")]
pub fn system_startup_lock()->Result<(),String>{
    use std::os::unix::{fs::MetadataExt,process::CommandExt};
    if std::env::current_exe().map_err(err)?.to_string_lossy().trim_end_matches(" (deleted)")!="/usr/bin/vibez4-alpha"{return Ok(());}
    let path=Path::new("/var/lib/vibez4-alpha-updater/running.lock");if !path.exists(){return Ok(());}
    let info=std::fs::symlink_metadata(path).map_err(err)?;
    if !info.file_type().is_file()||info.uid()!=0||info.mode()&0o022!=0{return Err("The Alpha update lock is not trusted".into());}
    let file=std::fs::File::open(path).map_err(err)?;file.lock_shared().map_err(err)?;
    let running=std::fs::metadata("/proc/self/exe").map_err(err)?;let installed=std::fs::metadata("/usr/bin/vibez4-alpha").map_err(err)?;
    if (running.dev(),running.ino())!=(installed.dev(),installed.ino()){
        return Err(Command::new("/usr/bin/vibez4-alpha").args(std::env::args_os().skip(1)).exec().to_string());
    }
    static LOCK:OnceLock<std::fs::File>=OnceLock::new();let _=LOCK.set(file);Ok(())
}
#[cfg(not(target_os="linux"))]pub fn system_startup_lock()->Result<(),String>{Ok(())}

#[tauri::command]
pub fn alpha_update_state(webview:Webview)->Result<Value,String>{require_local(&webview)?;Ok(state())}
#[tauri::command]
pub fn alpha_update_check(webview:Webview,app:tauri::AppHandle)->Result<Value,String>{require_local(&webview)?;check(&app);Ok(state())}
#[tauri::command]
pub fn alpha_update_allow(webview:Webview,app:tauri::AppHandle)->Result<Value,String>{
    require_local(&webview)?;
    #[cfg(target_os="linux")] if is_flatpak(){return alpha_flatpak_update::request_update(&app);}
    Ok(state())
}
#[cfg(test)]mod tests{
    use super::*;
    #[test]fn alpha_channel_never_adopts_v3_other_majors_or_private_tests(){
        let current=Version::parse("4.0.0-alpha.4").unwrap();
        for wrong in ["3.0.10","3.1.0","4.0.0-test.99","5.0.0-alpha.1","5.0.0","4.0.0-alpha.04","4.0.0-alpha.9+other","4.0.0-beta.0","4.0.0-beta","4.0.0-rc.1.1"]{
            if let Ok(next)=Version::parse(wrong){assert!(!newer(&current,&next),"{wrong}");}
        }
        assert!(newer(&current,&Version::parse("4.0.0-alpha.5").unwrap()));
        assert!(!newer(&current,&current));assert!(!newer(&current,&Version::parse("4.0.0-alpha.3").unwrap()));
    }
    #[test]fn an_alpha_moves_on_to_beta_rc_and_final_but_never_back(){
        let order=["4.0.0-alpha.30","4.0.0-alpha.31","4.0.0-beta.1","4.0.0-beta.2","4.0.0-beta.10","4.0.0-rc.1","4.0.0","4.0.1-beta.1","4.1.0"];
        for pair in order.windows(2){
            let (old,new)=(Version::parse(pair[0]).unwrap(),Version::parse(pair[1]).unwrap());
            assert!(newer(&old,&new),"{} -> {}",pair[0],pair[1]);assert!(!newer(&new,&old),"{} -> {}",pair[1],pair[0]);
        }
    }
}
