#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod policy;
mod smoke;
mod native_layout;

use policy::{APP_ID, APP_NAME, HOME, TOOLBAR_HEIGHT, Settings};
use serde_json::{json, Value};
use std::{fs, io::Write, path::PathBuf, sync::{Mutex, atomic::{AtomicBool, Ordering}}};
use tauri::{AppHandle, Manager, Webview, WebviewUrl, WebviewWindowBuilder, LogicalPosition, LogicalSize};
use tauri::webview::{WebviewBuilder, NewWindowResponse, PermissionResponse};
use tauri_plugin_autostart::ManagerExt as AutostartExt;
use tauri_plugin_clipboard_manager::ClipboardExt;
use tauri_plugin_opener::OpenerExt;
use webkit2gtk::WebViewExt;

struct PreviewState {
    settings: Mutex<Settings>,
    file: PathBuf,
    status: Mutex<String>,
    capture_busy: AtomicBool,
    tray_ready: AtomicBool,
    shell_ready: AtomicBool,
    smoke: bool,
}

fn err(e: impl std::fmt::Display) -> String { e.to_string() }
fn title() -> String { format!("{APP_NAME} v{}", env!("CARGO_PKG_VERSION")) }
fn require_local(webview: &Webview) -> Result<(), String> {
    if policy::trusted_caller(webview.label(), &webview.url().map_err(err)?) { Ok(()) }
    else { Err("Native commands are restricted to the bundled preview controls".into()) }
}
fn message(app: &AppHandle, text: impl Into<String>) {
    if let Ok(mut status) = app.state::<PreviewState>().status.lock() { *status = text.into(); }
}
fn read_settings(file: &PathBuf) -> Settings {
    match fs::read(file).ok().and_then(|v| serde_json::from_slice::<Settings>(&v).ok()) {
        Some(s) if s.validate().is_ok() => s,
        _ => Settings::default(),
    }
}
fn write_settings(file: &PathBuf, settings: &Settings) -> Result<(), String> {
    use std::os::unix::fs::OpenOptionsExt;
    let temp = file.with_extension("tmp");
    let mut output = fs::OpenOptions::new().create(true).truncate(true).write(true).mode(0o600)
        .open(&temp).map_err(err)?;
    output.write_all(&serde_json::to_vec_pretty(settings).map_err(err)?).map_err(err)?;
    output.sync_all().map_err(err)?;
    fs::rename(temp, file).map_err(err)
}
fn os_locale() -> String {
    ["LC_ALL", "LC_MESSAGES", "LANG"].iter().find_map(|k| std::env::var(k).ok().filter(|s| !s.is_empty()))
        .unwrap_or_else(|| "en".into()).split('.').next().unwrap_or("en").replace('_', "-")
}
fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_window("main") {
        let _ = window.unminimize(); let _ = window.show(); let _ = window.set_focus();
        let _ = layout(app);
    }
}
fn layout(app: &AppHandle) -> Result<(), String> {
    native_layout::layout(app)
}

#[tauri::command]
async fn get_state(webview: Webview, app: AppHandle) -> Result<Value, String> {
    require_local(&webview)?;
    let settings = app.state::<PreviewState>().settings.lock().map_err(err)?.clone();
    let view = app.get_webview("vibe").ok_or("Vibe view is not ready")?;
    let (tx, rx) = tokio::sync::oneshot::channel();
    view.with_webview(move |platform| {
        let native = platform.inner();
        let _ = tx.send((native.can_go_back(), native.can_go_forward(), native.is_loading()));
    }).map_err(err)?;
    let (back, forward, loading) = rx.await.map_err(err)?;
    let state = app.state::<PreviewState>();
    if webview.label() == "shell" { state.shell_ready.store(true, Ordering::Relaxed); }
    let status = state.status.lock().map_err(err)?.clone();
    Ok(json!({"settings": settings, "version": env!("CARGO_PKG_VERSION"), "os_locale": os_locale(),
        "can_go_back": back, "can_go_forward": forward, "loading": loading,
        "tray_ready": state.tray_ready.load(Ordering::Relaxed), "status": status}))
}

#[tauri::command]
async fn navigate(webview: Webview, app: AppHandle, action: String) -> Result<(), String> {
    require_local(&webview)?;
    let view = app.get_webview("vibe").ok_or("Vibe view is not ready")?;
    match action.as_str() {
        "back" => view.with_webview(|p| p.inner().go_back()).map_err(err),
        "forward" => view.with_webview(|p| p.inner().go_forward()).map_err(err),
        "reload" => view.reload().map_err(err),
        "home" => view.navigate(HOME.parse().map_err(err)?).map_err(err),
        _ => Err("Unsupported navigation action".into()),
    }
}

async fn open_settings(app: &AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("settings") {
        window.show().map_err(err)?; return window.set_focus().map_err(err);
    }
    WebviewWindowBuilder::new(app, "settings", WebviewUrl::App("settings.html".into()))
        .title(format!("{} · Settings", title())).inner_size(760., 760.).min_inner_size(600., 500.)
        .data_directory(app.path().app_data_dir().map_err(err)?.join("controls"))
        .on_navigation(policy::local_url)
        .on_new_window(|_, _| NewWindowResponse::Deny)
        .build().map_err(err)?;
    Ok(())
}

#[tauri::command]
async fn show_settings(webview: Webview, app: AppHandle) -> Result<(), String> {
    require_local(&webview)?; open_settings(&app).await
}

#[tauri::command]
async fn save_settings(webview: Webview, app: AppHandle, settings: Settings) -> Result<Settings, String> {
    require_local(&webview)?;
    settings.validate()?;
    let state = app.state::<PreviewState>();
    if settings.close_to_tray && !state.tray_ready.load(Ordering::Relaxed) {
        return Err("The tray could not be initialized. Close-to-tray stays disabled.".into());
    }
    let mut current = state.settings.lock().map_err(err)?;
    let previous = current.clone();
    // Each autostart entry uses the preview's own name and executable, never vibez.desktop.
    if settings.start_at_login != previous.start_at_login {
        if settings.start_at_login { app.autolaunch().enable().map_err(err)?; }
        else { app.autolaunch().disable().map_err(err)?; }
    }
    if let Err(error) = write_settings(&state.file, &settings) {
        if settings.start_at_login != previous.start_at_login {
            if previous.start_at_login { let _ = app.autolaunch().enable(); }
            else { let _ = app.autolaunch().disable(); }
        }
        return Err(error);
    }
    *current = settings.clone();
    drop(current);
    if let Some(view) = app.get_webview("vibe") { view.set_zoom(settings.zoom_factor).map_err(err)?; }
    Ok(settings)
}

#[tauri::command]
async fn close_settings(webview: Webview) -> Result<(), String> {
    require_local(&webview)?;
    if webview.label() != "settings" { return Err("Only settings can close itself".into()); }
    webview.window().close().map_err(err)
}

async fn take_screenshot(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<PreviewState>();
    if state.capture_busy.swap(true, Ordering::SeqCst) { return Err("A screenshot is already in progress".into()); }
    message(app, "Choose a screenshot in the desktop dialog…");
    let result: Result<(), String> = async {
        let response = ashpd::desktop::screenshot::Screenshot::request().interactive(true).modal(true)
            .send().await.map_err(err)?.response().map_err(err)?;
        let uri = url::Url::parse(response.uri().as_str()).map_err(err)?;
        let file = uri.to_file_path().map_err(|_| "The portal did not return a local image".to_string())?;
        if fs::metadata(&file).map_err(err)?.len() > 64 * 1024 * 1024 {
            return Err("Screenshot is larger than the 64 MiB preview limit".into());
        }
        let image = tauri::image::Image::from_bytes(&fs::read(file).map_err(err)?).map_err(err)?;
        app.clipboard().write_image(&image).map_err(err)?;
        Ok(())
    }.await;
    state.capture_busy.store(false, Ordering::SeqCst);
    match &result {
        Ok(()) => { message(app, "Screenshot copied — paste it into Vibe with Ctrl+V."); show_main(app); },
        Err(error) => message(app, format!("Screenshot cancelled or unavailable: {error}")),
    }
    result
}

#[tauri::command]
async fn capture_screenshot(webview: Webview, app: AppHandle) -> Result<(), String> {
    require_local(&webview)?; take_screenshot(&app).await
}

#[tauri::command]
async fn get_diagnostics(webview: Webview, app: AppHandle) -> Result<String, String> {
    require_local(&webview)?;
    Ok(format!("{}\nApplication ID: {}\nEngine: Tauri 2 / system WebKitGTK\nOS: Linux {}\nSession: {}\nDesktop: {}\nConfig: {}\nData: {}\nAutomatic updates: disabled in preview\nMicrophone/camera: not enabled in this preview\nGlobal shortcut: not registered (does not conflict with Electron)",
        title(), APP_ID, std::env::consts::ARCH,
        std::env::var("XDG_SESSION_TYPE").unwrap_or_default(),
        std::env::var("XDG_CURRENT_DESKTOP").unwrap_or_default(),
        app.path().app_config_dir().map_err(err)?.display(), app.path().app_data_dir().map_err(err)?.display()))
}

fn create_tray(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    use tauri::{menu::{Menu, MenuItem}, tray::TrayIconBuilder};
    let open = MenuItem::with_id(app, "open", "Open VibeZ Tauri Preview", true, None::<&str>)?;
    let screenshot = MenuItem::with_id(app, "capture", "Screenshot", true, None::<&str>)?;
    let settings = MenuItem::with_id(app, "settings", "Settings", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit preview", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &screenshot, &settings, &quit])?;
    let mut builder = TrayIconBuilder::with_id("vibez-tauri-preview")
        .tooltip(title()).menu(&menu).show_menu_on_left_click(true)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => show_main(app),
            "quit" => app.exit(0),
            "settings" => { let app = app.clone(); tauri::async_runtime::spawn(async move { if let Err(e) = open_settings(&app).await { message(&app, e); } }); },
            "capture" => { let app = app.clone(); tauri::async_runtime::spawn(async move { let _ = take_screenshot(&app).await; }); },
            _ => (),
        });
    if let Some(icon) = app.default_window_icon() { builder = builder.icon(icon.clone()); }
    builder.build(app)?;
    Ok(())
}

fn main() {
    if std::env::args().any(|a| a == "--version") { println!("{}", title()); return; }
    let smoke = std::env::args().any(|a| a == "--smoke-test");
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| show_main(app)))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_autostart::Builder::new().app_name(APP_NAME).arg("--hidden").build())
        .invoke_handler(tauri::generate_handler![get_state, navigate, show_settings, save_settings, close_settings, capture_screenshot, get_diagnostics])
        .setup(move |app| {
            use std::os::unix::fs::PermissionsExt;
            let config = app.path().app_config_dir()?;
            let data = app.path().app_data_dir()?;
            for dir in [&config, &data] { fs::create_dir_all(dir)?; fs::set_permissions(dir, fs::Permissions::from_mode(0o700))?; }
            let file = config.join("settings.json");
            let settings = read_settings(&file);
            app.manage(PreviewState { settings: Mutex::new(settings.clone()), file,
                status: Mutex::new("Rust / WebKitGTK · isolated preview".into()),
                capture_busy: AtomicBool::new(false), tray_ready: AtomicBool::new(false), shell_ready: AtomicBool::new(false), smoke });
            let window = tauri::window::WindowBuilder::new(app, "main")
                .title(title()).inner_size(1280., 840.).min_inner_size(760., 560.).build()?;
            let controls = WebviewBuilder::new("shell", WebviewUrl::App("index.html".into()))
                .data_directory(data.join("controls")).on_navigation(policy::local_url)
                .on_new_window(|_, _| NewWindowResponse::Deny);
            window.add_child(controls, LogicalPosition::new(0., 0.), LogicalSize::new(1280., TOOLBAR_HEIGHT))?;
            let handle = app.handle().clone();
            let popup_handle = app.handle().clone();
            let content_url = if smoke { WebviewUrl::App("offline.html".into()) } else { WebviewUrl::External(HOME.parse()?) };
            let content = WebviewBuilder::new("vibe", content_url)
                .data_directory(data.join("webview")).disable_drag_drop_handler()
                .on_permission_request(|_, _| PermissionResponse::Deny)
                .on_navigation(move |url| {
                    if (smoke && policy::local_url(url)) || policy::embedded_url(url) { return true; }
                    if policy::external_url(url) {
                        if let Err(error) = handle.opener().open_url(url.as_str(), None::<&str>) { message(&handle, err(error)); }
                    }
                    false
                })
                .on_new_window(move |url, _| {
                    // First Linux prototype uses same-view auth. Popup/opener-based SSO needs separate validation.
                    if policy::embedded_url(&url) {
                        if let Some(view) = popup_handle.get_webview("vibe") { let _ = view.navigate(url); }
                    } else if policy::external_url(&url) {
                        let _ = popup_handle.opener().open_url(url.as_str(), None::<&str>);
                    }
                    NewWindowResponse::Deny
                });
            let vibe = window.add_child(content, LogicalPosition::new(0., TOOLBAR_HEIGHT), LogicalSize::new(1280., 840. - TOOLBAR_HEIGHT))?;
            vibe.set_zoom(settings.zoom_factor)?;
            layout(app.handle()).map_err(std::io::Error::other)?;
            if !smoke {
                match create_tray(app.handle()) {
                    Ok(()) => app.state::<PreviewState>().tray_ready.store(true, Ordering::Relaxed),
                    Err(error) => message(app.handle(), format!("Tray unavailable: {error}")),
                }
                if std::env::args().any(|a| a == "--hidden") && app.state::<PreviewState>().tray_ready.load(Ordering::Relaxed) { window.hide()?; }
            } else { smoke::start(app.handle().clone()); }
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() != "main" { return; }
            let app = window.app_handle();
            match event {
                tauri::WindowEvent::Resized(_) | tauri::WindowEvent::ScaleFactorChanged { .. } => { if let Err(e) = layout(app) { message(app, e); } },
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    let state = app.state::<PreviewState>();
                    let hide = state.settings.lock().map(|s| s.close_to_tray).unwrap_or(false)
                        && state.tray_ready.load(Ordering::Relaxed) && !state.smoke;
                    if hide { api.prevent_close(); let _ = window.hide(); }
                    else { app.exit(0); }
                },
                _ => (),
            }
        })
        .run(tauri::generate_context!())
        .expect("VibeZ Tauri Preview could not start");
}
