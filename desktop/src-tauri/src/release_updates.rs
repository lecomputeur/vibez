//! Visible, local update dialog; verified download followed by an explicit OS handoff.
use std::{sync::{Mutex,OnceLock,atomic::{AtomicBool,Ordering}},time::Duration,path::PathBuf};
use tauri::{AppHandle,Manager,WebviewUrl,WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;
use serde_json::{json,Value};
use crate::{desktop_ui,err,policy,update_download::{self,Release,Asset}};
static BUSY:AtomicBool=AtomicBool::new(false);
static CANCEL:AtomicBool=AtomicBool::new(false);
#[derive(Default)]
struct State {phase:&'static str,release:Option<Release>,received:u64,total:u64,error:String,ready:Option<(PathBuf,Asset)>}
impl State {
    fn begin_check(&mut self) {
        *self = Self { phase: "checking", ..Default::default() };
    }
}
fn state()->&'static Mutex<State>{static S:OnceLock<Mutex<State>>=OnceLock::new();S.get_or_init(||Mutex::new(State{phase:"idle",..Default::default()}))}
struct Guard;impl Drop for Guard{fn drop(&mut self){BUSY.store(false,Ordering::SeqCst);}}
#[cfg(target_os="windows")]
fn store_packaged()->bool{
    #[link(name="kernel32")]extern "system"{fn GetCurrentPackageFullName(length:*mut u32,name:*mut u16)->i32;}
    let mut length=0u32;unsafe{GetCurrentPackageFullName(&mut length,std::ptr::null_mut())==122&&length>0}
}
#[cfg(not(target_os="windows"))]fn store_packaged()->bool{false}
pub fn snapshot()->Result<Value,String>{
    let s=state().lock().map_err(err)?;
    Ok(json!({"phase":s.phase,"release":s.release,"received":s.received,"total":s.total,"error":s.error,
        "fileName":s.ready.as_ref().map(|(_,a)|&a.name),"current":env!("CARGO_PKG_VERSION"),"busy":BUSY.load(Ordering::SeqCst)}))
}
fn set_phase(phase:&'static str){if let Ok(mut s)=state().lock(){s.phase=phase;s.error.clear();}}
#[cfg(test)] mod state_tests {
    use super::*;
    #[test] fn new_check_discards_old_release_and_download_state() {
        let mut s=State {phase:"error",release:Some(Release {version:"3.0.4".into(),assets:vec![]}),
            received:100,total:200,error:"Old download error".into(),ready:None};
        s.begin_check();
        assert_eq!(s.phase,"checking");assert!(s.release.is_none());assert!(s.ready.is_none());
        assert_eq!((s.received,s.total),(0,0));assert!(s.error.is_empty());
        // Discovery errors retain no stale assets, so the UI offers a new check.
        s.phase="error";s.error="Metadata failed".into();assert!(s.release.is_none());
    }
}
pub async fn show(app:&AppHandle)->Result<(),String>{
    if let Some(w)=app.get_webview_window("updates"){w.show().map_err(err)?;return w.set_focus().map_err(err);}
    let window=WebviewWindowBuilder::new(app,"updates",WebviewUrl::App("updates.html".into()))
        .title(format!("VibeZ · {}",desktop_ui::text(app,"updates")))
        .inner_size(400.,300.).min_inner_size(340.,260.).visible(false).resizable(true)
        .data_directory(app.path().app_data_dir().map_err(err)?.join("controls"))
        .data_store_identifier([118,105,98,101,122,51,0,0,0,0,0,0,0,0,0,1])
        .on_navigation(policy::local_url).on_new_window(|_,_|tauri::webview::NewWindowResponse::Deny).build().map_err(err)?;
    if let Some(main)=app.get_window("main"){
        if let (Ok(p),Ok(size))=(main.outer_position(),main.outer_size()){
            let ws=window.outer_size().map_err(err)?;
            let(mut x,mut y)=(p.x as i64+(size.width as i64-ws.width as i64)/2,p.y as i64+(size.height as i64-ws.height as i64)/2);
            if let Some(m)=main.current_monitor().map_err(err)?{let left=m.position().x as i64;let top=m.position().y as i64;x=x.clamp(left,(left+m.size().width as i64-ws.width as i64).max(left));y=y.clamp(top,(top+m.size().height as i64-ws.height as i64).max(top));}
            window.set_position(tauri::PhysicalPosition::new(x as i32,y as i32)).map_err(err)?;
        }
    }
    window.show().map_err(err)?;window.set_focus().map_err(err)
}
pub fn check(app:AppHandle,manual:bool){
    if BUSY.swap(true,Ordering::SeqCst){
        if manual{tauri::async_runtime::spawn(async move{let _=show(&app).await;});}return;
    }
    tauri::async_runtime::spawn(async move{
        let _guard=Guard;
        let already_ready=state().lock().map(|s|s.phase=="ready").unwrap_or(false);
        if already_ready{if manual{let _=show(&app).await;}return;}
        if store_packaged(){set_phase("store");if manual{let _=show(&app).await;}return;}
        if let Ok(mut s)=state().lock(){s.begin_check();}if manual{let _=show(&app).await;}
        match update_download::discover().await{
            Ok(Some(release)) if semver::Version::parse(&release.version).ok()>semver::Version::parse(env!("CARGO_PKG_VERSION")).ok()=>{
                if let Ok(mut s)=state().lock(){s.phase="available";s.release=Some(release);s.received=0;s.total=0;}
                crate::message(&app,desktop_ui::preview(&app,"updateAvailable"));let _=show(&app).await;
            },
            Ok(_)=>set_phase("latest"),
            Err(error)=>{if let Ok(mut s)=state().lock(){s.phase="error";s.error=error;}},
        }
    });
}
pub async fn action(app:&AppHandle,action:&str,name:Option<String>)->Result<Value,String>{
    match action{
        "close"=>{if let Some(w)=app.get_webview_window("updates"){w.close().map_err(err)?;}},
        "cancel"=>{CANCEL.store(true,Ordering::SeqCst);},
        "check"=>check(app.clone(),true),
        "store"=>{if !store_packaged(){return Err("This is not a Store installation".into());}app.opener().open_url("ms-windows-store://pdp/?ProductId=9NR7L2G4MS08",None::<&str>).map_err(err)?;},
        "download"=>{
            if store_packaged(){return Err("Microsoft Store manages this installation".into());}
            if BUSY.swap(true,Ordering::SeqCst){return Err("An update operation is already running".into());}
            let selected=state().lock().ok().and_then(|s|s.release.as_ref().and_then(|r|r.assets.iter().find(|a|Some(&a.name)==name.as_ref())).cloned());
            let Some(asset)=selected else{BUSY.store(false,Ordering::SeqCst);return Err("Choose an offered update package".into());};
            CANCEL.store(false,Ordering::SeqCst);
            {let mut s=state().lock().map_err(err)?;s.phase="downloading";s.received=0;s.total=asset.size;s.error.clear();s.ready=None;}
            let app=app.clone();
            tauri::async_runtime::spawn(async move{
                let _guard=Guard;
                let result=async{
                    let root=app.path().app_cache_dir().map_err(err)?.join("updates");
                    update_download::download(&root,&asset,&CANCEL,|n|{if let Ok(mut s)=state().lock(){s.received=n;}}).await
                }.await;
                if let Ok(mut s)=state().lock(){match result{Ok(path)=>{s.ready=Some((path,asset));s.phase="ready";},Err(e)=>{s.phase=if e=="cancelled"{"available"}else{"error"};s.error=if e=="cancelled"{String::new()}else{e};}}}
            });
        },
        "reveal"|"open"=>{
            if store_packaged()||BUSY.load(Ordering::SeqCst){return Err("Update cannot be opened now".into());}
            let(path,asset)=state().lock().map_err(err)?.ready.clone().ok_or("No verified download")?;
            let p=path.clone();let checked=asset.clone();tauri::async_runtime::spawn_blocking(move||update_download::verify_file(&p,&checked)).await.map_err(err)??;
            // No command arguments, elevation, silent flags, profile deletion, or restart.
            if action=="open"{
                #[cfg(target_os="linux")]
                if asset.kind=="AppImage" {
                    update_download::prepare_appimage(&path)?;
                    std::process::Command::new(&path).spawn().map_err(err)?;
                    return snapshot();
                }
                app.opener().open_path(path.to_string_lossy().into_owned(),None::<&str>).map_err(err)?;
            }
            else{app.opener().reveal_item_in_dir(&path).map_err(err)?;}
        },
        _=>return Err("Unsupported update action".into()),
    }
    snapshot()
}
pub fn schedule(app:AppHandle){tauri::async_runtime::spawn(async move{
    tokio::time::sleep(Duration::from_secs(6)).await;
    if app.state::<crate::PreviewState>().settings.lock().map(|s|s.auto_updates).unwrap_or(false){check(app.clone(),false);}
});}
// Test helper: retry pure observations during WKWebView document startup, never
// replay a button click or treat a pending/failed permission result as success.
async fn await_probe_value(view:&tauri::Webview,script:&str,wanted:&str,context:&str)->Result<(),String>{
    let deadline=std::time::Instant::now()+Duration::from_secs(12);
    loop{
        let observed=match crate::screenshots::eval_value(view,script).await{
            Ok(value) if value==wanted=>return Ok(()),
            Ok(value)=>value,
            Err(error)=>format!("read error: {error}"),
        };
        if std::time::Instant::now()>deadline{return Err(format!("{context}: expected {wanted}, observed {observed}"));}
        tokio::time::sleep(Duration::from_millis(80)).await;
    }
}
/// Explicit CI test exercises the real local button and downloads a published
/// package. It never opens, installs or announces a fake public release.
pub async fn smoke_check(app:&AppHandle)->Result<(),String>{
    if !app.state::<crate::PreviewState>().smoke{return Err("Update probe requires offline smoke mode".into());}
    show(app).await.map_err(|e|format!("Open update window: {e}"))?;
    let window=app.get_webview("updates").ok_or("Update window missing")?;
    // A nonempty status is written only after the production frontend has read
    // get_state AND update_state and rendered the result. Arbitrary sleeps are
    // insufficient when a new WKWebView process starts on a busy test runner.
    await_probe_value(&window,"String(document.readyState==='complete' && !!document.getElementById('status')?.textContent && typeof window.__TAURI__?.core?.invoke==='function')","true","Update frontend readiness").await?;
    window.eval("window.__updateAcl='pending';window.__TAURI__.core.invoke('update_state').then(()=>window.__updateAcl='allowed').catch(()=>window.__updateAcl='denied');true").map_err(err)?;
    await_probe_value(&window,"window.__updateAcl","allowed","Local update dialog ACL").await?;
    let remote=app.get_webview("vibe").ok_or("Missing webview")?;
    remote.eval("(() => {window.__updateAcl='pending';if(typeof window.__TAURI__?.core?.invoke!=='function'){window.__updateAcl='no-bridge';return true;}window.__TAURI__.core.invoke('update_state').then(()=>window.__updateAcl='allowed').catch(()=>window.__updateAcl='denied');return true;})()").map_err(err)?;
    await_probe_value(&remote,"String(['denied','no-bridge'].includes(window.__updateAcl))","true","Remote update isolation").await?;
    println!("UPDATE_ACL_OK: local dialog allowed, remote page denied");
    if std::env::args().any(|a|a=="--update-download-probe"){
        let release=update_download::discover().await?.ok_or("No published package for probe")?;
        let asset=release.assets.first().ok_or("No download")?.clone();
        {let mut s=state().lock().map_err(err)?;s.release=Some(release);s.phase="available";s.ready=None;s.error.clear();}
        await_probe_value(&window,"String(!document.getElementById('download').hidden && !document.getElementById('download').disabled && !!document.getElementById('package').value)","true","Download button readiness").await?;
        window.eval("document.getElementById('download').click();").map_err(err)?;
        let mut ready=None;
        for _ in 0..600{
            tokio::time::sleep(Duration::from_millis(100)).await;
            let s=snapshot()?;
            if s["phase"]=="error"{return Err(format!("Update button download failed: {}",s["error"]));}
            if s["phase"]=="ready"&&!BUSY.load(Ordering::SeqCst){ready=state().lock().map_err(err)?.ready.clone();break;}
        }
        let(path,downloaded)=ready.ok_or("Update button did not produce a verified download")?;
        update_download::verify_file(&path,&downloaded)?;
        if downloaded.name!=asset.name{return Err("Update button selected the wrong artifact".into());}
        await_probe_value(&window,"String(!document.getElementById('open').hidden && !document.getElementById('reveal').hidden)","true","Verified download actions").await?;
        println!("UPDATE_DOWNLOAD_OK: button -> native ACL -> HTTPS -> {} bytes -> SHA-256 -> explicit Open, {} (never executed)",asset.size,asset.name);
        {let mut s=state().lock().map_err(err)?;s.ready=None;s.release=None;s.phase="latest";}
        let _=std::fs::remove_dir_all(path.parent().unwrap());
    }
    action(app,"close",None).await?;Ok(())
}
