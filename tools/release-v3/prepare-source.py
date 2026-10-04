#!/usr/bin/env python3
"""Apply reviewed first-build corrections once; source job commits before tests."""
from pathlib import Path
r=Path(__file__).resolve().parents[2]/'desktop'
marker=r/'.v3-integration-revision'
if marker.exists() and marker.read_text().strip()=='1': raise SystemExit(0)
def edit(path, old, new):
 p=r/path;s=p.read_text()
 if old not in s: raise SystemExit(f'Missing reviewed patch anchor: {path}')
 p.write_text(s.replace(old,new,1))
# WKWebView URL can exist before absoluteString exists; Wry 0.57 unwraps it.
# Inspect the native optional URI without passing through that unsafe getter.
edit('src-tauri/src/site_language.rs', '''            if let Ok(uri) = view.url() {
                if uri.as_str() != "about:blank" { return Err("Language probe navigated remotely".into()); }
            }''', '''            let (tx, rx) = tokio::sync::oneshot::channel();
            view.with_webview(move |platform| {
                #[cfg(target_os = "linux")]
                let uri = platform.inner().uri().map(|s| s.to_string());
                #[cfg(target_os = "windows")]
                let uri: Option<String> = None; // Cookie probe performs no navigation.
                #[cfg(target_os = "macos")]
                let uri = unsafe {
                    let native = &*platform.inner().cast::<objc2_web_kit::WKWebView>();
                    native.URL().and_then(|url| url.absoluteString()).map(|s| s.to_string())
                };
                let _ = tx.send(uri);
            }).map_err(err)?;
            let uri = tokio::time::timeout(std::time::Duration::from_secs(3), rx).await.map_err(err)?.map_err(err)?;
            if uri.as_deref().is_some_and(|s| !s.is_empty() && s != "about:blank") {
                return Err("Language probe navigated remotely".into());
            }''')
# WindowCloseRequested belongs to the owning popup, never the main app.
edit('src-tauri/src/auth.rs', '''#[cfg(any(target_os = "windows", target_os = "macos"))]
pub fn attach_errors(_app: &AppHandle, _view: &Webview) -> Result<(), String> { Ok(()) }''', '''#[cfg(target_os = "windows")]
pub fn attach_errors(app: &AppHandle, view: &Webview) -> Result<(), String> {
    if !view.label().starts_with(PREFIX) { return Ok(()); }
    let app = app.clone(); let label = view.label().to_owned();
    view.with_webview(move |platform| {
        let callback_app = app.clone();
        let callback = webview2_com::WindowCloseRequestedEventHandler::create(Box::new(move |_, _| {
            let app = callback_app.clone(); let label = label.clone();
            tauri::async_runtime::spawn(async move {
                if let Some(window) = app.get_webview_window(&label) { let _ = window.destroy(); }
                if !app.webview_windows().keys().any(|key| key.starts_with(PREFIX)) {
                    if let Some(main) = app.get_webview("vibe") {
                        if main.url().is_ok_and(|url| policy::auth_return_url(&url)) { end(&app); }
                    }
                }
            });
            Ok(())
        }));
        let result = unsafe {
            platform.controller().CoreWebView2().and_then(|view| {
                let mut token = 0; view.add_WindowCloseRequested(&callback, &mut token)
            })
        };
        if result.is_err() { crate::message(&app, "Could not attach sign-in window close handler."); }
    }).map_err(crate::err)
}
#[cfg(target_os = "macos")]
pub fn attach_errors(_app: &AppHandle, _view: &Webview) -> Result<(), String> { Ok(()) }''')
p=r/'src-tauri/src/auth.rs';p.write_text(p.read_text().replace('VibeZ Preview ·','VibeZ 3 ·'))
# Test SPA history as the live application uses it, and wait for native state.
p=r/'src-tauri/src/smoke.rs';s=p.read_text();a=s.index('fn history_check(app: &AppHandle)')
s=s[:a]+'''fn history_check(app: &AppHandle) -> Result<(), String> {
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
''';p.write_text(s)
marker.write_text('1\n')
print('First-build native integration corrections applied; commit before building.')
