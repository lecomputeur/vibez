#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod policy;
mod browser;
#[cfg(target_os = "linux")]
mod linux_identity;
mod settings_store;
mod site_language;
mod status;
mod smoke;
mod link_trace;
mod link_probe;
#[cfg(target_os = "linux")]
#[path = "native_layout.rs"]
mod native_layout;
#[cfg(any(target_os = "windows", target_os = "macos"))]
#[path = "native_layout_windows.rs"]
mod native_layout;
mod auth;
mod desktop_ui;
mod screenshots;
#[path = "release_updates.rs"]
mod preview_updates;

use policy::{APP_ID, APP_NAME, HOME, TOOLBAR_HEIGHT, Settings};
use serde_json::{json, Value};
use std::{fs, path::PathBuf, sync::{Mutex, atomic::{AtomicBool, AtomicU64, Ordering}}};
use tauri::{AppHandle, Manager, Webview, WebviewUrl, WebviewWindowBuilder, LogicalPosition, LogicalSize};
use tauri::webview::{WebviewBuilder, NewWindowResponse, PermissionResponse};
use tauri_plugin_autostart::ManagerExt as AutostartExt;
use tauri_plugin_clipboard_manager::ClipboardExt;
use tauri_plugin_opener::OpenerExt;
#[cfg(target_os = "linux")]
use webkit2gtk::WebViewExt;

struct PreviewState {
    settings: Mutex<Settings>,
    file: PathBuf,
    status: Mutex<status::Status>,
    revision: AtomicU64,
    save_gate: tokio::sync::Mutex<()>,
    site_language: site_language::LanguageState,
    auth_started: Mutex<Option<std::time::Instant>>,
    capture_busy: AtomicBool,
    tray_ready: AtomicBool,
    shell_ready: AtomicBool,
    smoke: bool,
    auth_active: AtomicBool,
}
fn err(e: impl std::fmt::Display) -> String { e.to_string() }
fn title() -> String { format!("{APP_NAME} v{}", env!("CARGO_PKG_VERSION")) }
fn require_local(webview: &Webview) -> Result<(), String> {
    if policy::trusted_caller(webview.label(), &webview.url().map_err(err)?) { Ok(()) }
    else { Err("Native commands are restricted to the bundled preview controls".into()) }
}
fn message(app: &AppHandle, text: impl Into<String>) {
    if let Ok(mut status) = app.state::<PreviewState>().status.lock() { *status = status::Status::persistent(text); }
}
fn saved_message(app: &AppHandle) {
    if let Ok(mut status) = app.state::<PreviewState>().status.lock() { *status = status::Status::transient("settings_saved"); }
}
#[cfg(target_os = "windows")]
fn os_locale() -> String {
    use windows::Win32::Globalization::{GetUserDefaultUILanguage, LCIDToLocaleName, LOCALE_ALLOW_NEUTRAL_NAMES, MAX_LOCALE_NAME};
    unsafe {
        let lcid = GetUserDefaultUILanguage();
        let mut buffer = [0u16; MAX_LOCALE_NAME as usize];
        let len = LCIDToLocaleName(lcid as u32, Some(&mut buffer), LOCALE_ALLOW_NEUTRAL_NAMES);
        if len > 1 { return String::from_utf16_lossy(&buffer[..len as usize - 1]).replace('_', "-"); }
    }
    sys_locale::get_locale().unwrap_or_else(|| "en".into()).replace('_', "-")
}
#[cfg(not(target_os = "windows"))]
fn os_locale() -> String {
    sys_locale::get_locale()
        .or_else(|| ["LC_ALL", "LC_MESSAGES", "LANG"].iter().find_map(|k| std::env::var(k).ok().filter(|s| !s.is_empty())))
        .unwrap_or_else(|| "en".into()).split('.').next().unwrap_or("en").replace('_', "-")
}
fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_window("main") {
        let _ = window.unminimize(); let _ = window.show(); let _ = window.set_focus(); let _ = layout(app);
    }
}
fn layout(app: &AppHandle) -> Result<(), String> { native_layout::layout(app) }

#[tauri::command]
async fn get_state(webview: Webview, app: AppHandle) -> Result<Value, String> {
    require_local(&webview)?;
    let (settings, revision) = {
        let state = app.state::<PreviewState>();
        let settings = state.settings.lock().map_err(err)?;
        (settings.clone(), state.revision.load(Ordering::SeqCst))
    };
    let view = app.get_webview("vibe").ok_or("Vibe view is not ready")?;
    let (back, forward, loading) = browser::state(&view, &app).await?;
    let state = app.state::<PreviewState>();
    if webview.label() == "shell" && !state.shell_ready.swap(true, Ordering::SeqCst) {
        #[cfg(target_os = "linux")]
        native_layout::repair(&app)?;
    }
    let raw_status = state.status.lock().map_err(err)?.text().to_owned();
    let status = desktop_ui::status(&app, &raw_status);
    Ok(json!({"settings": settings, "revision": revision, "version": env!("CARGO_PKG_VERSION"), "os_locale": os_locale(), "platform": std::env::consts::OS,
        "can_go_back": back, "can_go_forward": forward, "loading": loading,
        "tray_ready": state.tray_ready.load(Ordering::Relaxed), "status": status}))
}
#[tauri::command]
async fn navigate(webview: Webview, app: AppHandle, action: String) -> Result<(), String> {
    require_local(&webview)?;
    let view = app.get_webview("vibe").ok_or("Vibe view is not ready")?;
    match action.as_str() {
        "back" => browser::history(&view, false).await,
        "forward" => browser::history(&view, true).await,
        "reload" => view.reload().map_err(err),
        "home" => {
            auth::close_popups(&app); auth::end(&app);
            link_trace::record("auth-mode-reset-home", &HOME.parse().map_err(err)?);
            message(&app, "Returning to Vibe. Your preview profile has not been cleared.");
            view.navigate(HOME.parse().map_err(err)?).map_err(err)
        },
        _ => Err("Unsupported navigation action".into()),
    }
}
async fn open_settings(app: &AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("settings") {
        window.show().map_err(err)?; return window.set_focus().map_err(err);
    }
    WebviewWindowBuilder::new(app, "settings", WebviewUrl::App("settings.html".into()))
        .title(format!("{} · {}", title(), desktop_ui::text(app, "settings"))).inner_size(760., 760.).min_inner_size(600., 500.)
        .data_directory(app.path().app_data_dir().map_err(err)?.join("controls")).data_store_identifier([118,105,98,101,122,51,0,0,0,0,0,0,0,0,0,1])
        .on_navigation(policy::local_url).on_new_window(|_, _| NewWindowResponse::Deny).build().map_err(err)?;
    Ok(())
}
#[tauri::command]
async fn show_settings(webview: Webview, app: AppHandle) -> Result<(), String> { require_local(&webview)?; open_settings(&app).await }
#[tauri::command]
async fn save_settings(webview: Webview, app: AppHandle, patch: settings_store::Patch, expected: settings_store::Patch) -> Result<Value, String> {
    require_local(&webview)?;
    let state = app.state::<PreviewState>();
    // Serializes the entire read/compare/side-effect/write/commit transaction.
    let gate = state.save_gate.lock().await;
    let previous = state.settings.lock().map_err(err)?.clone();
    let settings = patch.apply(&expected, &previous)?;
    if settings.close_to_tray && !state.tray_ready.load(Ordering::Relaxed) { return Err("tray_unavailable".into()); }
    let autostart_changed = settings.start_at_login != previous.start_at_login;
    let zoom_changed = settings.zoom_factor != previous.zoom_factor;
    if autostart_changed {
        if settings.start_at_login { app.autolaunch().enable().map_err(err)?; }
        else { app.autolaunch().disable().map_err(err)?; }
    }
    let result = (|| {
        if zoom_changed { app.get_webview("vibe").ok_or("Vibe view is not ready")?.set_zoom(settings.zoom_factor).map_err(err)?; }
        settings_store::write(&state.file, &settings)
    })();
    if let Err(error) = result {
        if autostart_changed {
            if previous.start_at_login { let _ = app.autolaunch().enable(); } else { let _ = app.autolaunch().disable(); }
        }
        if zoom_changed { if let Some(v) = app.get_webview("vibe") { let _ = v.set_zoom(previous.zoom_factor); } }
        return Err(error);
    }
    let revision = {
        let mut current = state.settings.lock().map_err(err)?;
        *current = settings.clone(); state.revision.fetch_add(1, Ordering::SeqCst) + 1
    };
    let language_changed = settings.language != previous.language;
    drop(gate);
    saved_message(&app);
    if language_changed { site_language::request(&app); }
    if let Err(error) = desktop_ui::refresh(&app) { message(&app, format!("Menu update failed: {error}")); }
    Ok(json!({"settings": settings, "revision": revision}))
}
#[tauri::command]
async fn close_settings(webview: Webview) -> Result<(), String> {
    require_local(&webview)?;
    if webview.label() != "settings" { return Err("Only settings can close itself".into()); }
    webview.window().close().map_err(err)
}
async fn take_screenshot(app: &AppHandle) -> Result<(), String> {
    screenshots::capture(app, "selection").await
}
#[tauri::command]
async fn capture_screenshot(webview: Webview, app: AppHandle, mode: String) -> Result<(), String> {
    require_local(&webview)?;
    screenshots::capture(&app, &mode).await
}
#[tauri::command]
async fn check_for_updates(webview: Webview, app: AppHandle) -> Result<(), String> {
    require_local(&webview)?;
    preview_updates::check(app, true);
    Ok(())
}
#[tauri::command]
async fn get_diagnostics(webview: Webview, app: AppHandle) -> Result<String, String> {
    require_local(&webview)?;
    let (engine, os_name, session, desktop, update_text) = if cfg!(target_os = "windows") {
        ("Tauri 2 / Microsoft WebView2", "Windows", String::new(), String::new(),
         "Updates: automatic startup checks; Microsoft Store delivery is used for Store installs")
    } else if cfg!(target_os = "macos") {
        ("Tauri 2 / Apple WKWebView", "macOS", String::new(), String::new(), "Updates: automatic startup checks; installation remains user-confirmed")
    } else {
        ("Tauri 2 / system WebKitGTK", "Linux", std::env::var("XDG_SESSION_TYPE").unwrap_or_default(),
         std::env::var("XDG_CURRENT_DESKTOP").unwrap_or_default(),
         "Updates: automatic startup checks; installation remains user-confirmed")
    };
    let auth_mode = auth::active(&app);
    let auto_updates = app.state::<PreviewState>().settings.lock().map(|s| s.auto_updates).unwrap_or(false);
    let site_language = site_language::inspect(&app).await;
    Ok(format!("{}\nApplication ID: {}\nEngine: {}\nOS: {} {}\nSystem/UI locale: {}\nSession: {}\nDesktop: {}\nConfig: {}\nData: {}\n{}\nAutomatic update checks: {}; automatic installation: disabled\nMicrophone/camera: not enabled in this version\nGlobal shortcut: not registered (does not conflict with Electron)\nSign-in popups: related webview; provider restrictions still apply\nAuthentication routing mode: {}\nMistral site language: {}\nAutomatic JS link interception: disabled\nRecent navigation (origins only, no credentials or tokens):\n{}\nLink routing (current process, origins only):\n{}",
        title(), APP_ID, engine, os_name, std::env::consts::ARCH, os_locale(), session, desktop,
        app.path().app_config_dir().map_err(err)?.display(), app.path().app_data_dir().map_err(err)?.display(),
        update_text, if auto_updates { "enabled" } else { "disabled" }, if auth_mode { "active" } else { "inactive" }, site_language, auth::diagnostics(), link_trace::diagnostics()))
}
fn create_tray(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> { desktop_ui::create_tray(app) }
fn main() {
    if std::env::args().any(|a| a == "--version") { println!("{}", title()); return; }
    let link_probe_only = std::env::args().any(|a| a == "--link-probe-only");
    let icon_probe = std::env::args().any(|a| a == "--icon-smoke-test");
    let smoke = icon_probe || link_probe_only || std::env::args().any(|a| a == "--smoke-test");
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| show_main(app)))
        .plugin(tauri_plugin_opener::Builder::new().open_js_links_on_click(false).build())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_autostart::Builder::new().app_name(APP_NAME).arg("--hidden").build())
        .invoke_handler(tauri::generate_handler![get_state, navigate, show_settings, save_settings, close_settings, capture_screenshot, check_for_updates, get_diagnostics])
        .setup(move |app| {
            #[cfg(target_os = "linux")]
            linux_identity::initialize().map_err(std::io::Error::other)?;
            let config = app.path().app_config_dir()?; let data = app.path().app_data_dir()?;
            for dir in [&config, &data] {
                fs::create_dir_all(dir)?;
                #[cfg(unix)] { use std::os::unix::fs::PermissionsExt; fs::set_permissions(dir, fs::Permissions::from_mode(0o700))?; }
            }
            let file = config.join("settings.json");
            let loaded = settings_store::read(&file).map_err(std::io::Error::other)?;
            let settings = loaded.settings;
            app.manage(PreviewState { settings: Mutex::new(settings.clone()), file,
                status: Mutex::new(status::Status::persistent(if loaded.recovered { "settings_recovered" } else { "" })),
                revision: AtomicU64::new(0), save_gate: tokio::sync::Mutex::new(()),
                site_language: site_language::LanguageState::default(), auth_started: Mutex::new(None),
                capture_busy: AtomicBool::new(false), tray_ready: AtomicBool::new(false), shell_ready: AtomicBool::new(false),
                auth_active: AtomicBool::new(false), smoke });
            let window = tauri::window::WindowBuilder::new(app, "main")
                .title(title()).inner_size(1280., 840.).min_inner_size(760., 560.).visible(false)
                .icon(tauri::image::Image::from_bytes(include_bytes!("../icons/128x128.png"))?)?.build()?;
            #[cfg(target_os = "linux")]
            linux_identity::prepare_window(&window).map_err(std::io::Error::other)?;
            let controls = WebviewBuilder::new("shell", WebviewUrl::App("index.html".into()))
                .data_directory(data.join("controls")).data_store_identifier([118,105,98,101,122,51,0,0,0,0,0,0,0,0,0,1]).on_navigation(policy::local_url).on_new_window(|_, _| NewWindowResponse::Deny);
            window.add_child(controls, LogicalPosition::new(0., 0.), LogicalSize::new(1280., TOOLBAR_HEIGHT))?;
            let handle = app.handle().clone(); let popup_handle = app.handle().clone();
            let content_url = if smoke { WebviewUrl::App("offline.html".into()) } else { WebviewUrl::External("about:blank".parse()?) };
            let content = WebviewBuilder::new("vibe", content_url)
                .data_directory(data.join("webview")).data_store_identifier([118,105,98,101,122,51,0,0,0,0,0,0,0,0,0,2]).disable_drag_drop_handler()
                .on_permission_request(|_, _| PermissionResponse::Deny)
                .on_navigation(move |url| {
                    if url.as_str() == "about:blank" && handle.state::<PreviewState>().site_language.bootstrap.load(Ordering::SeqCst) { return true; }
                    if smoke && policy::local_url(url) { link_trace::record("main-allow-local-test", url); return true; }
                    if policy::auth_entry_url(url) { auth::begin(&handle); }
                    if auth::active(&handle) && policy::auth_chain_url(url) {
                        if policy::auth_return_url(url) { auth::end(&handle); link_trace::record("auth-mode-end", url); }
                        link_trace::record("main-auth-allow", url); return true;
                    }
                    if policy::embedded_url(url) { link_trace::record("main-allow", url); return true; }
                    if policy::external_url(url) {
                        link_trace::record("main-open-external", url);
                        if handle.opener().open_url(url.as_str(), None::<&str>).is_err() {
                            link_trace::record("main-external-failed", url);
                            message(&handle, "Could not open the external link in your browser.");
                        }
                    } else { link_trace::record("main-block", url); }
                    false
                })
                .on_page_load(|view, payload| {
                    let finished = matches!(payload.event(), tauri::webview::PageLoadEvent::Finished);
                    link_trace::record(if finished { "main-load-finished" } else { "main-load-started" }, payload.url());
                    auth::page(payload.url(), finished);
                    site_language::loaded(view.app_handle(), payload.url(), finished);
                })
                .on_new_window(move |url, features| {
                    link_trace::record("main-popup-request", &url);
                    let target = url.clone(); let response = auth::new_window(&popup_handle, url, features);
                    let created = matches!(&response, NewWindowResponse::Create { .. });
                    link_trace::record(if created { "main-popup-created" } else { "main-popup-not-created" }, &target); response
                });
            let vibe = window.add_child(content, LogicalPosition::new(0., TOOLBAR_HEIGHT), LogicalSize::new(1280., 840. - TOOLBAR_HEIGHT))?;
            auth::attach_errors(app.handle(), &vibe).map_err(std::io::Error::other)?;
            vibe.set_zoom(settings.zoom_factor)?;
            // Prepare language on a neutral page; no delayed redirect during OAuth.
            if !smoke { site_language::request(app.handle()); }
            layout(app.handle()).map_err(std::io::Error::other)?;
            if !smoke || icon_probe {
                match create_tray(app.handle()) {
                    Ok(()) => app.state::<PreviewState>().tray_ready.store(true, Ordering::Relaxed),
                    Err(error) => message(app.handle(), format!("Tray unavailable: {error}")),
                }
            }
            // Visibility is an explicit startup decision, never a layout side effect.
            let start_hidden = !smoke && std::env::args().any(|a| a == "--hidden")
                && app.state::<PreviewState>().tray_ready.load(Ordering::Relaxed);
            if !start_hidden { window.show()?; }
            if !smoke { preview_updates::schedule(app.handle().clone()); }
            // The external icon probe inspects a real, offline running app.
            if smoke && !icon_probe { link_probe::start(app.handle().clone(), link_probe_only); }
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() != "main" { return; }
            let app = window.app_handle();
            match event {
                tauri::WindowEvent::Resized(_) | tauri::WindowEvent::ScaleFactorChanged { .. } => { if let Err(e) = layout(app) { message(app, e); } },
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    let state = app.state::<PreviewState>();
                    let hide = state.settings.lock().map(|s| s.close_to_tray).unwrap_or(false) && state.tray_ready.load(Ordering::Relaxed) && !state.smoke;
                    if hide { api.prevent_close(); let _ = window.hide(); } else { app.exit(0); }
                },
                _ => (),
            }
        })
        .run(tauri::generate_context!()).expect("VibeZ 3 could not start");
}
