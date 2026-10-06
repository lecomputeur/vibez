//! Trusted local chooser + result preview. No screenshot file writes until Save.
use crate::{desktop_ui,err,policy,screenshots,PreviewState};
use serde_json::{json,Value};
use std::sync::{Mutex,atomic::Ordering};
use tauri::{AppHandle,Manager,WebviewUrl,WebviewWindowBuilder};
#[cfg(target_os="linux")]
#[path="screenshot_screen_linux.rs"] mod screen_linux;
static LAST:Mutex<Option<Vec<u8>>>=Mutex::new(None);
pub fn clear() {if let Ok(mut last)=LAST.lock(){*last=None;}}
pub fn remember(bytes:Vec<u8>)->Result<(),String>{*LAST.lock().map_err(err)?=Some(bytes);Ok(())}
fn last()->Result<Vec<u8>,String>{LAST.lock().map_err(err)?.clone().ok_or("Make a screenshot first".into())}
pub async fn open(app:&AppHandle)->Result<(),String> {
    if app.state::<PreviewState>().capture_busy.load(Ordering::SeqCst) {return Err(desktop_ui::status(app,"screenshot_busy"));}
    if let Some(window)=app.get_webview_window("screenshot") {window.show().map_err(err)?;return window.set_focus().map_err(err);}
    let builder=WebviewWindowBuilder::new(app,"screenshot",WebviewUrl::App("screenshot.html".into()))
        .title(format!("VibeZ · {} · test 3",desktop_ui::text(app,"screenshot")))
        .inner_size(580.,620.).min_inner_size(480.,520.).center().resizable(true)
        .data_directory(app.path().app_data_dir().map_err(err)?.join("controls"))
        .data_store_identifier([118,105,98,101,122,51,0,0,0,0,0,0,0,0,0,1])
        .on_navigation(policy::local_url).on_new_window(|_,_|tauri::webview::NewWindowResponse::Deny);
    #[cfg(target_os="linux")]
    let builder=if let Some(main)=app.get_window("main") {builder.transient_for_raw(&main.gtk_window().map_err(err)?)} else {builder};
    let window=builder.build().map_err(err)?;
    window.set_focus().map_err(err)
}
pub async fn capture(app:&AppHandle,mode:&str)->Result<Value,String> {
    if !matches!(mode,"full"|"visible"|"selection") {return Err("Unsupported screenshot mode".into());}
    if app.state::<PreviewState>().capture_busy.load(Ordering::SeqCst) {return Err(desktop_ui::status(app,"screenshot_busy"));}
    if let Some(window)=app.get_webview_window("screenshot") {window.hide().map_err(err)?;}
    crate::show_main(app);
    #[cfg(target_os="linux")]
    let result=if mode=="selection" {capture_desktop(app).await} else {screenshots::capture_preview(app,mode).await};
    #[cfg(not(target_os="linux"))]
    let result=screenshots::capture_preview(app,mode).await;
    // Restore the chooser even after Escape, timeout, clipboard failure or errors.
    if let Some(window)=app.get_webview_window("screenshot") {let _=window.show();let _=window.set_focus();}
    result
}
#[cfg(target_os="linux")]
async fn capture_desktop(app:&AppHandle)->Result<Value,String> {
    use base64::{engine::general_purpose::STANDARD,Engine as _};
    let state=app.state::<PreviewState>();
    if state.capture_busy.swap(true,Ordering::SeqCst){return Err(desktop_ui::status(app,"screenshot_busy"));}
    struct Busy<'a>(&'a std::sync::atomic::AtomicBool);
    impl Drop for Busy<'_>{fn drop(&mut self){self.0.store(false,Ordering::SeqCst);}}
    let _busy=Busy(&state.capture_busy);clear();
    let Some(bytes)=screen_linux::capture(app,desktop_ui::language(app)=="nl").await? else{return Ok(json!({"cancelled":true}));};
    let image=tauri::image::Image::from_bytes(&bytes).map_err(err)?;
    let copied=screenshots::copy_last(app,&bytes).is_ok();
    let result=json!({"cancelled":false,"dataUrl":format!("data:image/png;base64,{}",STANDARD.encode(&bytes)),"width":image.width(),"height":image.height(),"copied":copied});
    remember(bytes)?;Ok(result)
}
pub async fn action(app:&AppHandle,action:&str)->Result<Value,String> {
    match action {
        "copy"=>{screenshots::copy_last(app,&last()?)?;Ok(json!({"copied":true}))},
        "save"=>save(app,last()?).await,
        "new"=>{clear();Ok(json!({}))},
        "close"=>{
            #[cfg(target_os="linux")] screen_linux::cancel(app);
            screenshots::cancel_active(app);clear();if let Some(w)=app.get_webview_window("screenshot"){w.close().map_err(err)?;}crate::show_main(app);Ok(json!({}))},
        _=>Err("Unsupported screenshot action".into())
    }
}
#[cfg(target_os="linux")]
async fn save(app:&AppHandle,bytes:Vec<u8>)->Result<Value,String> {
    use gtk::prelude::*;
    let window=app.get_webview_window("screenshot").ok_or("Screenshot window closed")?;
    let (tx,rx)=tokio::sync::oneshot::channel();
    let app2=app.clone();
    app.run_on_main_thread(move || {
        let parent=window.gtk_window().ok();
        let dutch=desktop_ui::language(&app2)=="nl";
        let dialog=gtk::FileChooserNative::new(
            Some(if dutch {"Screenshot opslaan"} else {"Save screenshot"}),parent.as_ref(),gtk::FileChooserAction::Save,
            Some(if dutch {"Opslaan"} else {"Save"}),Some(if dutch {"Annuleren"} else {"Cancel"}));
        dialog.set_current_name("VibeZ-screenshot.png");dialog.set_do_overwrite_confirmation(true);
        let filter=gtk::FileFilter::new();filter.set_name(Some("PNG image"));filter.add_pattern("*.png");dialog.add_filter(filter);
        let sender=std::cell::RefCell::new(Some(tx));
        let keeper=std::rc::Rc::new(std::cell::RefCell::new(Some(dialog.clone())));
        dialog.connect_response(move |dialog,response| {
            let result:Result<Option<std::path::PathBuf>,String>=if response==gtk::ResponseType::Accept {
                dialog.filename().ok_or("No local file selected".into()).map(Some)
            } else {Ok(None)};
            if let Some(tx)=sender.borrow_mut().take(){let _=tx.send(result);}
            dialog.destroy();keeper.borrow_mut().take();
        });
        dialog.show();
    }).map_err(err)?;
    let path=rx.await.map_err(err)??;
    let Some(path)=path else {return Ok(json!({"cancelled":true}));};
    // The native dialog owns filename choice and overwrite confirmation. Never
    // silently change the selected path after that confirmation.
    tauri::async_runtime::spawn_blocking(move || {
        use std::io::Write;
        let mut options=std::fs::OpenOptions::new();options.create(true).truncate(true).write(true);
        #[cfg(unix)] {use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
        let mut file=options.open(&path).map_err(err)?;file.write_all(&bytes).map_err(err)?;file.sync_all().map_err(err)?;
        Ok(json!({"saved":true,"path":path.display().to_string()}))
    }).await.map_err(err)?
}
#[cfg(not(target_os="linux"))]
async fn save(_app:&AppHandle,_bytes:Vec<u8>)->Result<Value,String>{Err("Save is not enabled in this Linux test candidate. Use Copy.".into())}
