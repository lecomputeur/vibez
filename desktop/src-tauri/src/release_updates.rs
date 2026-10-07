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
        set_phase("checking");if manual{let _=show(&app).await;}
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
            let p=path.clone();tauri::async_runtime::spawn_blocking(move||update_download::verify_file(&p,&asset)).await.map_err(err)??;
            // No command arguments, elevation, silent flags, profile deletion, or restart.
            if action=="open"{app.opener().open_path(path.to_string_lossy().into_owned(),None::<&str>).map_err(err)?;}
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
/// Explicit CI test downloads an existing package but NEVER opens or installs it.
pub async fn smoke_check(app:&AppHandle)->Result<(),String>{
    if !app.state::<crate::PreviewState>().smoke{return Err("Update probe requires offline smoke mode".into());}
    show(app).await?;
    let window=app.get_webview("updates").ok_or("Update window missing")?;
    tokio::time::sleep(Duration::from_millis(400)).await;
    let js="window.__updateAcl='pending';window.__TAURI__.core.invoke('update_state').then(()=>window.__updateAcl='allowed').catch(()=>window.__updateAcl='denied');true";
    window.eval(js).map_err(err)?;
    for _ in 0..40{tokio::time::sleep(Duration::from_millis(50)).await;if crate::screenshots::eval_value(&window,"window.__updateAcl").await?=="allowed"{break;}}
    if crate::screenshots::eval_value(&window,"window.__updateAcl").await?!="allowed"{return Err("Local update dialog ACL denied".into());}
    let remote=app.get_webview("vibe").ok_or("Missing webview")?;
    remote.eval("window.__updateAcl='pending';window.__TAURI__.core.invoke('update_state').then(()=>window.__updateAcl='allowed').catch(()=>window.__updateAcl='denied');true").map_err(err)?;
    tokio::time::sleep(Duration::from_millis(300)).await;
    if crate::screenshots::eval_value(&remote,"window.__updateAcl").await?!="denied"{return Err("Remote update command was not denied".into());}
    action(app,"close",None).await?;
    println!("UPDATE_ACL_OK: local dialog allowed, remote page denied");
    if std::env::args().any(|a|a=="--update-download-probe"){
        let release=update_download::discover().await?.ok_or("No published package for probe")?;
        let asset=release.assets.first().ok_or("No download")?;
        let root=app.path().app_cache_dir().map_err(err)?.join("probe-downloads");
        let cancel=AtomicBool::new(false);
        let path=update_download::download(&root,asset,&cancel,|_|{}).await?;
        update_download::verify_file(&path,asset)?;
        println!("UPDATE_DOWNLOAD_OK: {} bytes verified; {} (never executed)",asset.size,asset.name);
        let _=std::fs::remove_dir_all(path.parent().unwrap());
    }
    Ok(())
}
