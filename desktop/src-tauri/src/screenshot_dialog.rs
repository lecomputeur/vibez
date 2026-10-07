//! Trusted local chooser + result preview. Screenshots stay in memory until Save.
use crate::{desktop_ui,err,policy,screenshots,PreviewState};
use serde_json::{json,Value};
use std::sync::{Mutex,atomic::Ordering};
use tauri::{AppHandle,Manager,WebviewUrl,WebviewWindowBuilder};
#[cfg(target_os="linux")]
#[path="screenshot_screen_linux.rs"] mod screen_linux;
#[path="screenshot_paste.rs"] mod paste_composer;
static OPERATION:std::sync::atomic::AtomicBool=std::sync::atomic::AtomicBool::new(false);
struct Operation;
impl Operation {fn start()->Result<Self,String>{if OPERATION.swap(true,Ordering::SeqCst){Err("Screenshot busy".into())}else{Ok(Self)}}}
impl Drop for Operation {fn drop(&mut self){OPERATION.store(false,Ordering::SeqCst);}}
static LAST:Mutex<Option<Vec<u8>>>=Mutex::new(None);
pub fn clear() {if let Ok(mut last)=LAST.lock(){*last=None;}}
pub fn remember(bytes:Vec<u8>)->Result<(),String>{*LAST.lock().map_err(err)?=Some(bytes);Ok(())}
fn last()->Result<Vec<u8>,String>{LAST.lock().map_err(err)?.clone().ok_or("Make a screenshot first".into())}
pub async fn open(app:&AppHandle)->Result<(),String> {
    if OPERATION.load(Ordering::SeqCst) || app.state::<PreviewState>().capture_busy.load(Ordering::SeqCst) {return Err(desktop_ui::status(app,"screenshot_busy"));}
    if let Some(window)=app.get_webview_window("screenshot") {window.show().map_err(err)?;return window.set_focus().map_err(err);}
    #[cfg(target_os="linux")] install_clipboard_bridge(app)?;
    let builder=WebviewWindowBuilder::new(app,"screenshot",WebviewUrl::App("screenshot.html".into()))
        .title(format!("VibeZ · {} · test 4",desktop_ui::text(app,"screenshot")))
        .inner_size(340.,290.).min_inner_size(340.,290.).center().resizable(false).maximizable(false)
        .data_directory(app.path().app_data_dir().map_err(err)?.join("controls"))
        .data_store_identifier([118,105,98,101,122,51,0,0,0,0,0,0,0,0,0,1])
        .on_navigation(policy::local_url).on_new_window(|_,_|tauri::webview::NewWindowResponse::Deny);
    #[cfg(target_os="linux")]
    let builder=if let Some(main)=app.get_window("main") {builder.transient_for_raw(&main.gtk_window().map_err(err)?)} else {builder};
    let window=builder.build().map_err(err)?;
    window.set_focus().map_err(err)
}
pub async fn capture(app:&AppHandle,mode:&str,auto_paste:bool)->Result<Value,String> {
    if !matches!(mode,"full"|"visible"|"selection") {return Err("Unsupported screenshot mode".into());}
    if app.state::<PreviewState>().capture_busy.load(Ordering::SeqCst) {return Err(desktop_ui::status(app,"screenshot_busy"));}
    let _operation=Operation::start()?;
    let original=app.get_webview("vibe").and_then(|v|v.url().ok());
    if let Some(window)=app.get_webview_window("screenshot") {window.hide().map_err(err)?;}
    // Do not run the layout repair on an already visible window here: GTK
    // reallocates its webviews asynchronously and can expose a transient 1x1.
    if let Some(main)=app.get_window("main") {
        if main.is_minimized().unwrap_or(false) {let _=main.unminimize();}
        if !main.is_visible().unwrap_or(true) {let _=main.show();}
        let _=main.set_focus();
    }
    tokio::time::sleep(std::time::Duration::from_millis(150)).await;
    #[cfg(target_os="linux")]
    let mut result=if mode=="selection" {capture_desktop(app).await} else {screenshots::capture_preview(app,mode).await};
    #[cfg(not(target_os="linux"))]
    let mut result=screenshots::capture_preview(app,mode).await;
    if let Ok(value)=&mut result {
        if auto_paste && value["cancelled"]!=true && value["copied"]==true {
            let current=app.get_webview("vibe").and_then(|v|v.url().ok());
            let pasted=if original.is_some() && current==original {paste_composer::paste(app,&last()?,false).await}
                else {Err("De pagina is gewijzigd. De opname is niet geplakt.".into())};
            match pasted {Ok(method)=>{value["pasted"]=json!(true);value["pasteMethod"]=json!(method);},Err(error)=>{value["pasteError"]=json!(error);}}
        }
        if value["pasted"]==true {return result;}
    }
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
    let copied=screenshots::copy_last(app,&bytes).await.is_ok();
    let result=json!({"cancelled":false,"dataUrl":format!("data:image/png;base64,{}",STANDARD.encode(&bytes)),"width":image.width(),"height":image.height(),"copied":copied});
    remember(bytes)?;Ok(result)
}
pub async fn action(app:&AppHandle,action:&str)->Result<Value,String> {
    match action {
        "copy"=>{screenshots::copy_last(app,&last()?).await?;Ok(json!({"copied":true}))},
        "paste"=>{
            let _operation=Operation::start()?;
            screenshots::copy_last(app,&last()?).await?;
            if let Some(w)=app.get_webview_window("screenshot"){w.hide().map_err(err)?;}
            focus_main(app);
            let result=paste_composer::paste(app,&last()?,false).await;
            if result.is_err(){if let Some(w)=app.get_webview_window("screenshot"){let _=w.show();let _=w.set_focus();}}
            let method=result?;Ok(json!({"pasted":true,"pasteMethod":method}))
        },
        "save"=>save(app,last()?).await,
        "new"=>{clear();Ok(json!({}))},
        "close"=>{
            #[cfg(target_os="linux")] screen_linux::cancel(app);
            screenshots::cancel_active(app);clear();if let Some(w)=app.get_webview_window("screenshot"){w.close().map_err(err)?;}focus_main(app);Ok(json!({}))},
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

fn focus_main(app:&AppHandle) {
    if let Some(w)=app.get_window("main"){if w.is_minimized().unwrap_or(false){let _=w.unminimize();}if !w.is_visible().unwrap_or(true){let _=w.show();}let _=w.set_focus();}
    if let Some(view)=app.get_webview("vibe"){let _=view.set_focus();}
}

#[cfg(target_os="linux")]
fn install_clipboard_bridge(app:&AppHandle)->Result<(),String> {
    use gtk::{gdk,prelude::*};
    use webkit2gtk::WebViewExt;
    static INSTALLED:std::sync::atomic::AtomicBool=std::sync::atomic::AtomicBool::new(false);
    if INSTALLED.swap(true,Ordering::SeqCst){return Ok(());}
    let view=app.get_webview("vibe").ok_or("Vibe is not ready")?;
    let handle=app.clone();
    let result=view.with_webview(move |platform| {
        platform.inner().connect_key_press_event(move |widget,event| {
            let state=event.state();let key=event.keyval();
            let control=state.contains(gdk::ModifierType::CONTROL_MASK);
            let shift=state.contains(gdk::ModifierType::SHIFT_MASK);
            let other=state.intersects(gdk::ModifierType::MOD1_MASK|gdk::ModifierType::SUPER_MASK);
            let paste=!other&&((control&&!shift&&(key==gdk::keys::constants::v||key==gdk::keys::constants::V))
                ||(!control&&shift&&key==gdk::keys::constants::Insert));
            if !paste{return false.into();}
            let allowed=widget.uri().and_then(|uri|uri.parse::<url::Url>().ok()).map(|url|
                policy::auth_return_url(&url)||(handle.state::<PreviewState>().smoke&&policy::local_url(&url))).unwrap_or(false);
            if !allowed{return false.into();}
            let Some(bytes)=screenshots::owned_clipboard_png() else {return false.into();};
            if OPERATION.load(Ordering::SeqCst){return true.into();}
            let app=handle.clone();
            // The real key event authorizes ONLY our currently owned PNG.
            // Other clipboard contents retain normal browser paste behaviour.
            tauri::async_runtime::spawn(async move {
                let Ok(_operation)=Operation::start() else{return;};
                if let Err(error)=paste_composer::paste(&app,&bytes,true).await {crate::message(&app,error);}
            });
            true.into()
        });
    }).map_err(err);
    if result.is_err(){INSTALLED.store(false,Ordering::SeqCst);}
    result
}
