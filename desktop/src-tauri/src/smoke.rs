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
        return Err(format!("Viewport mismatch: window={size:?}, content=({x},{y},{width},{height}), toolbar=({sx},{sy},{sw},{sh})"));
    }
    if window.title().map_err(crate::err)? != crate::title() { return Err("Title does not match preview version".into()); }
    println!("LAYOUT_OK: {}x{} content {}x{} at {},{}", size.width,size.height,width,height,x,y);
    Ok(())
}
fn wait_size(app: &AppHandle, width: f64, height: f64) -> Result<(), String> {
    let window = app.get_window("main").ok_or("Missing main window")?;
    let deadline = Instant::now() + Duration::from_secs(4);
    loop {
        let scale = window.scale_factor().map_err(crate::err)?;
        let actual = window.inner_size().map_err(crate::err)?.to_logical::<f64>(scale);
        if (actual.width - width).abs() <= 2. && (actual.height - height).abs() <= 2. {
            thread::sleep(Duration::from_millis(100)); check_layout(app)?;
            println!("RESIZE_OK: requested={width}x{height}, actual={}x{}", actual.width, actual.height);
            return Ok(());
        }
        if Instant::now() >= deadline { return Err(format!("Requested {width}x{height}, actual {actual:?}; a green layout alone is insufficient")); }
        thread::sleep(Duration::from_millis(50));
    }
}
fn popup_checks(app: &AppHandle) -> Result<(), String> {
    let view = app.get_webview("vibe").ok_or("Missing Vibe view")?;
    let initial = view.url().map_err(crate::err)?;
    for blank in [false, true] {
        view.eval("window.__reply='pending'; window.onmessage=e=>{if(e.source===window.__popup && e.data==='preview-popup-reply')window.__reply='ok';};").map_err(crate::err)?;
        let direct = if cfg!(target_os = "windows") { "window.__popup=window.open('http://tauri.localhost/offline.html','_blank');" }
            else { "window.__popup=window.open('tauri://localhost/offline.html','_blank');" };
        view.eval(if blank { "window.__popup=window.open('about:blank','_blank');" } else { direct }).map_err(crate::err)?;
        let deadline = Instant::now() + Duration::from_secs(5);
        let popup = loop {
            if let Some((_, window)) = app.webview_windows().into_iter().find(|(label,_)| label.starts_with("auth-popup-")) { break window; }
            if Instant::now() > deadline { return Err("window.open did not create a separate popup".into()); }
            thread::sleep(Duration::from_millis(100));
        };
        if blank {
            let popup_view = app.get_webview(popup.label()).ok_or("Missing blank popup")?;
            let target = if cfg!(target_os = "windows") { "location.href='http://tauri.localhost/offline.html';" }
                else { "location.href='tauri://localhost/offline.html';" };
            popup_view.eval(target).map_err(crate::err)?;
        }
        thread::sleep(Duration::from_millis(600));
        let popup_view = app.get_webview(popup.label()).ok_or("Missing popup view")?;
        if view.url().map_err(crate::err)? != initial { return Err("Popup replaced the main page".into()); }
        if crate::require_local(&popup_view).is_ok() { return Err("Popup was granted native command access".into()); }
        if !evaluate(&popup_view, "Boolean(window.opener)")?.contains("true") { return Err("Popup lost window.opener".into()); }
        popup_view.eval("window.__probe='pending'; if(window.__TAURI__){window.__TAURI__.core.invoke('get_state').then(()=>window.__probe='UNSAFE',()=>window.__probe='denied');}else{window.__probe='denied';}").map_err(crate::err)?;
        thread::sleep(Duration::from_millis(300));
        if !evaluate(&popup_view, "window.__probe")?.contains("denied") { return Err("Popup native IPC was not denied".into()); }
        // Nested OAuth popup checks retain opener/state and native isolation.
        popup_view.eval("window.__nestedReply='pending'; window.onmessage=e=>{if(e.source===window.__nested && e.data==='nested-reply')window.__nestedReply='ok';};").map_err(crate::err)?;
        let nested_direct = if cfg!(target_os = "windows") { "window.__nested=window.open('http://tauri.localhost/offline.html','_blank');" }
            else { "window.__nested=window.open('tauri://localhost/offline.html','_blank');" };
        popup_view.eval(nested_direct).map_err(crate::err)?;
        let nested_deadline = Instant::now() + Duration::from_secs(5);
        let nested = loop {
            if let Some((_, window)) = app.webview_windows().into_iter().find(|(label,_)| label.starts_with("auth-popup-") && label != popup.label()) { break window; }
            if Instant::now() > nested_deadline { return Err("Nested OAuth popup did not open".into()); }
            thread::sleep(Duration::from_millis(100));
        };
        thread::sleep(Duration::from_millis(400));
        let nested_view = app.get_webview(nested.label()).ok_or("Missing nested popup view")?;
        if !evaluate(&nested_view, "Boolean(window.opener)")?.contains("true") { return Err("Nested popup lost window.opener".into()); }
        if crate::require_local(&nested_view).is_ok() { return Err("Nested popup was granted native command access".into()); }
        nested_view.eval("window.__probe='pending'; if(window.__TAURI__){window.__TAURI__.core.invoke('get_state').then(()=>window.__probe='UNSAFE',()=>window.__probe='denied');}else{window.__probe='denied';}").map_err(crate::err)?;
        thread::sleep(Duration::from_millis(250));
        if !evaluate(&nested_view, "window.__probe")?.contains("denied") { return Err("Nested popup native IPC was not denied".into()); }
        nested_view.eval("window.opener.postMessage('nested-reply','*'); window.close();").map_err(crate::err)?;
        let nested_close = Instant::now() + Duration::from_secs(5);
        while app.get_webview_window(nested.label()).is_some() {
            if Instant::now() > nested_close { return Err("Nested popup did not close".into()); }
            thread::sleep(Duration::from_millis(100));
        }
        if !evaluate(&popup_view, "window.__nestedReply")?.contains("ok") { return Err("Nested popup callback did not reach its opener".into()); }
        popup_view.eval("window.opener.postMessage('preview-popup-reply','*'); window.close();").map_err(crate::err)?;
        let deadline = Instant::now() + Duration::from_secs(5);
        while app.get_webview_window(popup.label()).is_some() {
            if Instant::now() > deadline { return Err("Popup did not close after window.close".into()); }
            thread::sleep(Duration::from_millis(100));
        }
        if !evaluate(&view, "window.__reply")?.contains("ok") { return Err("Popup did not deliver its callback to the opener".into()); }
        if view.url().map_err(crate::err)? != initial { return Err("Closing the popup changed the main URL".into()); }
        println!("POPUP_OK: blank-bootstrap={blank}, nested popup preserved, opener callbacks received, native IPC denied, popups closed, main unchanged");
    }
    Ok(())
}
fn checks(app: &AppHandle) -> Result<(), String> {
    thread::sleep(Duration::from_secs(4));
    if !app.state::<PreviewState>().shell_ready.load(Ordering::Relaxed) { return Err("Bundled toolbar did not complete native IPC handshake".into()); }
    crate::desktop_ui::smoke_check(app)?;
    tauri::async_runtime::block_on(crate::site_language::smoke_check(app))?;
    check_layout(app)?;
    let window = app.get_window("main").ok_or("Missing main window")?;
    let view = app.get_webview("vibe").ok_or("Missing Vibe webview")?;
    view.eval("window.__probe='pending'; window.__TAURI__.core.invoke('get_state').then(()=>window.__probe='UNSAFE',()=>window.__probe='denied');").map_err(crate::err)?;
    thread::sleep(Duration::from_millis(600));
    let probe = evaluate(&view, "window.__probe")?;
    if !probe.contains("denied") { return Err(format!("Untrusted content IPC was not rejected: {probe}")); }
    history_check(app)?;
    popup_checks(app)?;
    // No test-only layout repair: test the actual production popup cleanup.
    thread::sleep(Duration::from_millis(250)); check_layout(app)?;
    let sizes = if cfg!(target_os="linux") { [(1100.,720.),(760.,560.),(1450.,950.),(1280.,840.)] } else { [(900.,600.),(760.,560.),(1000.,650.),(850.,600.)] };
    for (width,height) in sizes {
        window.set_size(LogicalSize::new(width,height)).map_err(crate::err)?;
        wait_size(app, width, height)?;
        window.maximize().map_err(crate::err)?;
        thread::sleep(Duration::from_millis(500)); check_layout(app)?;
        if !window.is_maximized().map_err(crate::err)? { return Err("Window did not enter maximized state".into()); }
        window.unmaximize().map_err(crate::err)?;
        wait_size(app, width, height)?;
        if window.is_maximized().map_err(crate::err)? { return Err("Window did not leave maximized state".into()); }
    }
    window.hide().map_err(crate::err)?;
    thread::sleep(Duration::from_millis(250));
    crate::layout(app)?;
    thread::sleep(Duration::from_millis(250));
    if window.is_visible().map_err(crate::err)? { return Err("Layout unexpectedly showed a hidden window".into()); }
    println!("HIDDEN_OK: layout preserves hidden state");
    window.show().map_err(crate::err)?;
    thread::sleep(Duration::from_millis(500)); check_layout(app)?;
    Ok(())
}
pub fn start(app: AppHandle) {
    thread::spawn(move || match checks(&app) {
        Ok(()) => { println!("SMOKE_OK: translated tray, related popup callbacks, denied remote IPC, exact shrink/grow/maximize/restore sizes and hidden-state preservation"); app.exit(0); },
        Err(error) => { eprintln!("SMOKE_FAILED: {error}\n{}", crate::auth::diagnostics()); app.exit(1); },
    });
}

fn history_check(app: &AppHandle) -> Result<(), String> {
    let view = app.get_webview("vibe").ok_or("Missing browser")?;
    let original = view.url().map_err(crate::err)?;
    for fragment in ["v3-history-one", "v3-history-two"] {
        let js = format!("history.pushState(null, '', '#{fragment}'); location.hash");
        if !evaluate(&view, &js)?.contains(fragment) { return Err("SPA history entry was not created".into()); }
    }
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if tauri::async_runtime::block_on(crate::browser::state(&view, app))?.0 { break; }
        if Instant::now() > deadline { return Err("Native browser did not expose back history".into()); }
        thread::sleep(Duration::from_millis(50));
    }
    tauri::async_runtime::block_on(crate::browser::history(&view, false))?;
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if evaluate(&view, "location.hash")?.contains("v3-history-one")
            && tauri::async_runtime::block_on(crate::browser::state(&view, app))?.1 { break; }
        if Instant::now() > deadline { return Err("Native Back or Forward availability is wrong".into()); }
        thread::sleep(Duration::from_millis(50));
    }
    tauri::async_runtime::block_on(crate::browser::history(&view, true))?;
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if evaluate(&view, "location.hash")?.contains("v3-history-two") { break; }
        if Instant::now() > deadline { return Err("Native Forward did not reach the next entry".into()); }
        thread::sleep(Duration::from_millis(50));
    }
    view.navigate(original).map_err(crate::err)?;
    thread::sleep(Duration::from_millis(500));
    println!("HISTORY_OK: native Back and Forward navigation and availability verified");
    Ok(())
}
