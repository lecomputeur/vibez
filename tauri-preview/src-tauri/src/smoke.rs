//! Offline integration checks against real GTK/WebKit windows; no Mistral account or network required.
use std::{sync::{mpsc, atomic::Ordering}, thread, time::Duration};
use tauri::{AppHandle, Manager, LogicalSize};
use crate::{PreviewState, policy::TOOLBAR_HEIGHT};

fn evaluate(view: &tauri::Webview, js: &str) -> Result<String, String> {
    let (tx,rx) = mpsc::channel();
    view.eval_with_callback(js, move |result| { let _ = tx.send(result); }).map_err(crate::err)?;
    rx.recv_timeout(Duration::from_secs(5)).map_err(crate::err)
}
fn check_layout(app: &AppHandle) -> Result<(), String> {
    let window = app.get_window("main").ok_or("Missing main window")?;
    let view = app.get_webview("vibe").ok_or("Missing Vibe webview")?;
    let shell = app.get_webview("shell").ok_or("Missing toolbar webview")?;
    let scale = window.scale_factor().map_err(crate::err)?;
    let size = window.inner_size().map_err(crate::err)?.to_logical::<f64>(scale);
    let (x,y,width,height) = crate::native_layout::geometry(&view)?;
    let (sx,sy,sw,sh) = crate::native_layout::geometry(&shell)?;
    if x.abs()>2. || (y-TOOLBAR_HEIGHT).abs()>2. || (width-size.width).abs()>2.
        || (height+TOOLBAR_HEIGHT-size.height).abs()>2. || sx.abs()>2. || sy.abs()>2.
        || (sw-size.width).abs()>2. || (sh-TOOLBAR_HEIGHT).abs()>2. {
        return Err(format!("GTK viewport mismatch: window={size:?}, content=({x},{y},{width},{height}), toolbar=({sx},{sy},{sw},{sh})"));
    }
    if window.title().map_err(crate::err)? != crate::title() { return Err("Title does not match preview version".into()); }
    println!("LAYOUT_OK: {}x{} content {}x{} at {},{}", size.width,size.height,width,height,x,y);
    Ok(())
}
fn checks(app: &AppHandle) -> Result<(), String> {
    thread::sleep(Duration::from_secs(4));
    if !app.state::<PreviewState>().shell_ready.load(Ordering::Relaxed) { return Err("Bundled toolbar did not complete native IPC handshake".into()); }
    let window = app.get_window("main").ok_or("Missing main window")?;
    let view = app.get_webview("vibe").ok_or("Missing Vibe webview")?;
    view.eval("window.__probe='pending'; window.__TAURI__.core.invoke('get_state').then(()=>window.__probe='UNSAFE',()=>window.__probe='denied');").map_err(crate::err)?;
    thread::sleep(Duration::from_millis(600));
    let probe = evaluate(&view, "window.__probe")?;
    if !probe.contains("denied") { return Err(format!("Untrusted content IPC was not rejected: {probe}")); }
    for (width,height) in [(1100.,720.),(760.,560.),(1450.,950.),(1280.,840.)] {
        window.set_size(LogicalSize::new(width,height)).map_err(crate::err)?;
        thread::sleep(Duration::from_millis(500)); check_layout(app)?;
        window.maximize().map_err(crate::err)?;
        thread::sleep(Duration::from_millis(500)); check_layout(app)?;
        window.unmaximize().map_err(crate::err)?;
        thread::sleep(Duration::from_millis(500)); check_layout(app)?;
    }
    window.hide().map_err(crate::err)?;
    thread::sleep(Duration::from_millis(250));
    window.show().map_err(crate::err)?;
    thread::sleep(Duration::from_millis(500)); check_layout(app)?;
    Ok(())
}
pub fn start(app: AppHandle) {
    thread::spawn(move || {
        match checks(&app) {
            Ok(()) => { println!("SMOKE_OK: toolbar IPC, denied content IPC, title, resize/maximize/restore and hide/show"); app.exit(0); },
            Err(error) => { eprintln!("SMOKE_FAILED: {error}"); app.exit(1); },
        }
    });
}
