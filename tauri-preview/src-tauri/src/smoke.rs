//! Offline integration checks against real GTK/WebKit windows; no Mistral account or network required.
use std::{sync::{mpsc, atomic::Ordering}, thread, time::{Duration, Instant}};
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
fn popup_checks(app: &AppHandle) -> Result<(), String> {
    let view = app.get_webview("vibe").ok_or("Missing Vibe view")?;
    let initial = view.url().map_err(crate::err)?;
    // Test both direct window.open and a blank window followed by navigation.
    // These are offline test pages, never a real OAuth or Google session.
    for blank in [false, true] {
        view.eval("window.__reply='pending'; window.onmessage=e=>{if(e.source===window.__popup && e.data==='preview-popup-reply')window.__reply='ok';};").map_err(crate::err)?;
        view.eval(if blank { "window.__popup=window.open('about:blank','_blank');" }
            else { "window.__popup=window.open('tauri://localhost/offline.html','_blank');" }).map_err(crate::err)?;
        let deadline = Instant::now() + Duration::from_secs(5);
        let popup = loop {
            if let Some((_, window)) = app.webview_windows().into_iter().find(|(label,_)| label.starts_with("auth-popup-")) { break window; }
            if Instant::now() > deadline { return Err("window.open did not create a separate popup".into()); }
            thread::sleep(Duration::from_millis(100));
        };
        if blank {
            let popup_view = app.get_webview(popup.label()).ok_or("Missing blank popup")?;
            popup_view.eval("location.href='tauri://localhost/offline.html';").map_err(crate::err)?;
        }
        thread::sleep(Duration::from_millis(600));
        let popup_view = app.get_webview(popup.label()).ok_or("Missing popup view")?;
        if view.url().map_err(crate::err)? != initial { return Err("Popup replaced the main page".into()); }
        if crate::require_local(&popup_view).is_ok() { return Err("Popup was granted native command access".into()); }
        if !evaluate(&popup_view, "Boolean(window.opener)")?.contains("true") { return Err("Popup lost window.opener".into()); }
        popup_view.eval("window.__probe='pending'; if(window.__TAURI__){window.__TAURI__.core.invoke('get_state').then(()=>window.__probe='UNSAFE',()=>window.__probe='denied');}else{window.__probe='denied';}").map_err(crate::err)?;
        thread::sleep(Duration::from_millis(300));
        if !evaluate(&popup_view, "window.__probe")?.contains("denied") { return Err("Popup native IPC was not denied".into()); }
        popup_view.eval("window.opener.postMessage('preview-popup-reply','*'); window.close();").map_err(crate::err)?;
        let deadline = Instant::now() + Duration::from_secs(5);
        while app.get_webview_window(popup.label()).is_some() {
            if Instant::now() > deadline { return Err("Popup did not close after window.close".into()); }
            thread::sleep(Duration::from_millis(100));
        }
        if !evaluate(&view, "window.__reply")?.contains("ok") { return Err("Popup did not deliver its callback to the opener".into()); }
        if view.url().map_err(crate::err)? != initial { return Err("Closing the popup changed the main URL".into()); }
        println!("POPUP_OK: blank-bootstrap={blank}, opener preserved, callback received, native IPC denied, popup closed, main unchanged");
    }
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
    popup_checks(app)?;
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
            Ok(()) => { println!("SMOKE_OK: popup/opener callbacks, denied popup/content IPC, toolbar, title, resize/maximize/restore and hide/show"); app.exit(0); },
            Err(error) => { eprintln!("SMOKE_FAILED: {error}\n{}", crate::auth::diagnostics()); app.exit(1); },
        }
    });
}
