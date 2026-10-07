//! User-initiated screenshots of the loaded Vibe page; no remote native IPC.
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::{json, Value};
use std::{sync::{atomic::{AtomicBool, AtomicU64, Ordering}, Arc, Mutex}, time::{Duration, Instant}};
use tauri::{AppHandle, Manager, Webview};
use tauri_plugin_clipboard_manager::ClipboardExt;
use crate::{desktop_ui, err, message, PreviewState};

const SNAPDOM: &str = include_str!("../../node_modules/@zumer/snapdom/dist/snapdom.js");
#[cfg(target_os = "linux")]
#[path="screenshot_native_linux.rs"] mod native_linux;
#[cfg(target_os="linux")]
#[path="screenshot_clipboard.rs"] mod native_clipboard;
const SCRIPT: &str = include_str!("capture_page.js");
const MAX_DATA: usize = 34 * 1024 * 1024;
static SERIAL: AtomicU64 = AtomicU64::new(1);
struct Busy<'a>(&'a AtomicBool);
impl Drop for Busy<'_> { fn drop(&mut self) { self.0.store(false,Ordering::SeqCst); } }

pub(super) async fn eval_value(view: &Webview, script: impl Into<String>) -> Result<String,String> {
    let (tx,rx)=tokio::sync::oneshot::channel();
    let tx=Arc::new(Mutex::new(Some(tx)));
    view.eval_with_callback(script,move |result| {
        if let Ok(mut slot)=tx.lock() { if let Some(tx)=slot.take() { let _=tx.send(result); } }
    }).map_err(err)?;
    let raw=tokio::time::timeout(Duration::from_secs(5),rx).await.map_err(err)?.map_err(err)?;
    Ok(serde_json::from_str::<String>(&raw).unwrap_or(raw))
}
fn capture_script(mode:&str, drag:&str, id:u64)->Result<String,String> {
    if !matches!(mode,"full"|"visible"|"selection") { return Err("Unsupported screenshot mode".into()); }
    let timeout=if mode=="selection" {120000} else {45000};
    let config=json!({"id":id,"mode":mode,"dragHint":drag,"timeoutMs":timeout,"native":cfg!(target_os="linux")}).to_string();
    let library=if cfg!(target_os="linux") { "" } else { SNAPDOM };
    Ok(format!("{library}\n;\n{}",SCRIPT.replace("__VIBEZ_CAPTURE_CONFIG__",&config)))
}
async fn cancel(view:&Webview,id:u64)->Result<(),String> {
    eval_value(view,format!("(() => {{if(window.__vibezCapture?.id==={id}){{window.__vibezCapture.cancel?.();window.__vibezCapture=null;}}return true;}})()")).await?;
    Ok(())
}
async fn begin(view:&Webview,mode:&str,drag:&str)->Result<u64,String> {
    let id=SERIAL.fetch_add(1,Ordering::SeqCst);
    if mode=="selection" { view.set_focus().map_err(err)?; }
    // Opening/closing a native transient window can briefly leave WebKit at
    // its 1x1 minimum allocation. Wait for a stable, usable viewport instead
    // of returning a formally valid but empty 1x1 PNG.
    let mut previous = String::new();
    let mut ready = false;
    for _ in 0..40 {
        let measured=eval_value(view,"JSON.stringify([innerWidth,innerHeight])").await?;
        let size:Value=serde_json::from_str(&measured).map_err(err)?;
        if size[0].as_f64().unwrap_or(0.)>=64. && size[1].as_f64().unwrap_or(0.)>=64. && measured==previous {
            ready=true;break;
        }
        previous=measured;
        tokio::time::sleep(Duration::from_millis(75)).await;
    }
    if !ready {return Err("The page is still resizing. Wait a moment and try again.".into());}
    view.eval(capture_script(mode,drag,id)?).map_err(err)?;
    Ok(id)
}
async fn wait_result(view:&Webview,mode:&str,id:u64)->Result<Value,String> {
    let deadline=Instant::now()+Duration::from_secs(if mode=="selection" {125} else {50});
    let result=async {
        loop {
            if Instant::now()>deadline { return Err("Screenshot timed out".into()); }
            tokio::time::sleep(Duration::from_millis(180)).await;
            let js=format!("(() => {{const s=window.__vibezCapture;if(!s||s.id!=={id})return '';return s.result?.length>{MAX_DATA}?'{{\"status\":\"error\",\"message\":\"Screenshot too large\"}}':s.result||'';}})()");
            let raw=eval_value(view,js).await?;
            if raw.len()>MAX_DATA { return Err("Screenshot result is too large".into()); }
            if !raw.is_empty() {
                let payload:Value=serde_json::from_str(&raw).map_err(err)?;
                #[cfg(target_os="linux")]
                if payload["status"]=="ready" {
                    let bytes=native_linux::snapshot(view,mode,&payload).await?;
                    let image=tauri::image::Image::from_bytes(&bytes).map_err(err)?;
                    return Ok(json!({"status":"ok","dataUrl":format!("data:image/png;base64,{}",STANDARD.encode(&bytes)),
                        "width":image.width(),"height":image.height(),"geometry":payload["geometry"],"meta":{"engine":"WebKitGTK native snapshot"}}));
                }
                return Ok(payload);
            }
        }
    }.await;
    // Do not reopen the chooser or release the capture lock until the page
    // has acknowledged cleanup, including restoring full-page scroll containers.
    let cleanup=cancel(view,id).await;
    match (result,cleanup) {
        (Ok(value),Ok(()))=>Ok(value),
        (Err(error),_)=>Err(error),
        (_,Err(error))=>Err(format!("Cannot restore screenshot page: {error}")),
    }
}
fn png_bytes(data:&str)->Result<Vec<u8>,String> {
    if data.len()>MAX_DATA { return Err("Screenshot result is too large".into()); }
    let encoded=data.strip_prefix("data:image/png;base64,").ok_or("Not a PNG screenshot")?;
    let bytes=STANDARD.decode(encoded).map_err(err)?;
    // Reject oversized dimensions before decoding an image supplied by a web page.
    if bytes.len()<33 || bytes.len()>26*1024*1024 || &bytes[..8]!=b"\x89PNG\r\n\x1a\n" || &bytes[8..16]!=b"\0\0\0\rIHDR" {
        return Err("Invalid PNG screenshot".into());
    }
    let w=u32::from_be_bytes(bytes[16..20].try_into().map_err(err)?);
    let h=u32::from_be_bytes(bytes[20..24].try_into().map_err(err)?);
    if w==0 || h==0 || w>32760 || h>32760 || u64::from(w)*u64::from(h)>36_000_000 {
        return Err("Screenshot dimensions exceed safe limits".into());
    }
    Ok(bytes)
}
async fn copy_png(app:&AppHandle,bytes:&[u8])->Result<(),String> {
    #[cfg(target_os="linux")]
    { native_clipboard::write(app,bytes).await }
    #[cfg(not(target_os="linux"))]
    { let image=tauri::image::Image::from_bytes(bytes).map_err(err)?;app.clipboard().write_image(&image).map_err(err) }
}
pub async fn capture_preview(app:&AppHandle,mode:&str)->Result<Value,String> {
    if !matches!(mode,"full"|"visible"|"selection") { return Err("Unsupported screenshot mode".into()); }
    let state=app.state::<PreviewState>();
    if state.capture_busy.swap(true,Ordering::SeqCst) { return Err(desktop_ui::status(app,"screenshot_busy")); }
    let _busy=Busy(&state.capture_busy);
    crate::screenshot_dialog::clear();
    message(app,"screenshot_working");
    let result:Result<Value,String>=async {
        let view=app.get_webview("vibe").ok_or("Vibe view is not ready")?;
        let url=view.url().map_err(err)?;
        let id=begin(&view,mode,&desktop_ui::preview(app,"screenshotDrag")).await?;
        let payload=wait_result(&view,mode,id).await?;
        match payload["status"].as_str() {
            Some("cancelled")=>Ok(json!({"cancelled":true})),
            Some("ok")=> {
                if view.url().map_err(err)?!=url { return Err("The page changed during capture; please try again".into()); }
                let bytes=png_bytes(payload["dataUrl"].as_str().ok_or("Missing screenshot data")?)?;
                let copy_error=copy_png(app,&bytes).await.err();
                crate::screenshot_dialog::remember(bytes)?;
                Ok(json!({"cancelled":false,"dataUrl":payload["dataUrl"],"width":payload["width"],"height":payload["height"],
                    "copied":copy_error.is_none(),"copyError":copy_error}))
            },
            _=>Err(payload["message"].as_str().unwrap_or("Screenshot failed").into())
        }
    }.await;
    match &result {
        Ok(value) if value["cancelled"]==true=>message(app,"screenshot_cancelled"),
        Ok(value) if value["copied"]==true=>message(app,"screenshot_copied"),
        Ok(_)=>message(app,"Screenshot ready — see preview"),
        Err(error)=>message(app,format!("Screenshot failed: {error}")),
    }
    result
}
pub fn cancel_active(app:&AppHandle) {
    if let Some(view)=app.get_webview("vibe") { let _=view.eval("window.__vibezCapture?.cancel?.();"); }
}
pub async fn copy_last(app:&AppHandle,bytes:&[u8])->Result<(),String> { copy_png(app,bytes).await }
#[cfg(target_os="linux")]
pub fn owned_clipboard_png()->Option<Arc<Vec<u8>>> { native_clipboard::current_png() }
#[path="screenshot_probe.rs"] mod probe;
pub async fn smoke_check(app:&AppHandle)->Result<(),String> { probe::run(app).await }
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn modes_are_explicit() {
        for mode in ["full","visible","selection"] { assert!(capture_script(mode,"drag",1).is_ok()); }
        assert!(capture_script("unknown","drag",1).is_err());
    }
    #[test] fn no_remote_privileges() { assert!(!SCRIPT.contains("__TAURI__"));assert!(!SCRIPT.contains("invoke(")); }
    #[test] fn rejects_invalid_png_before_decode() {
        assert!(png_bytes("data:text/plain;base64,AAAA").is_err());
        assert!(png_bytes("data:image/png;base64,AAAA").is_err());
        let mut png=vec![0u8;33];png[..16].copy_from_slice(b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR");
        png[16..20].copy_from_slice(&u32::MAX.to_be_bytes());png[20..24].copy_from_slice(&100u32.to_be_bytes());
        assert!(png_bytes(&format!("data:image/png;base64,{}",STANDARD.encode(png))).is_err());
    }
    #[test] fn busy_guard_always_releases() { let busy=AtomicBool::new(true);{let _g=Busy(&busy);}assert!(!busy.load(Ordering::SeqCst)); }
}
