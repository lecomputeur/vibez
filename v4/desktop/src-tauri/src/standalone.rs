#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
//! Local UI plus an unprivileged official Mistral web surface.
#[path="official_web.rs"]
mod official_web;
#[path="screenshot_v4.rs"]
mod screenshot_v4;
use screenshot_v4::{desktop_ui,policy,rich_render,PreviewState,message,title,PAGE_VIEW};
mod screenshots;
mod screenshot_dialog;
mod work_native;
mod chat_downloads;
mod composer_connector;
#[path="classic_layout.rs"]
mod classic_layout;
#[path="classic_language.rs"]
mod classic_language;
#[path="panel_prefs.rs"]
mod panel_prefs;
#[path="project_import.rs"]
mod project_import;
#[path="project_details.rs"]
mod project_details;
#[path="project_overview.rs"]
mod project_overview;
#[path="display_policy.rs"]
mod display_policy;
#[path="alpha_updates.rs"]
mod alpha_updates;
#[cfg(all(feature = "native-smoke", target_os = "linux"))]
mod login_window_smoke;
#[cfg(target_os = "linux")]
mod alpha_flatpak_update;
#[cfg(any(not(target_os = "linux"), test))]
#[path="platform_desktop.rs"]
mod platform_desktop;
#[cfg(target_os = "linux")]
use gtk::prelude::*;
use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, Read, Write},
    process::{Child, ChildStdin, Command, Stdio},
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    },
};
use tauri::{
    Emitter, EventTarget, Manager, PhysicalPosition, PhysicalSize, Webview, WebviewUrl,
    WebviewWindowBuilder,
};
use tauri_plugin_clipboard_manager::ClipboardExt;
const APP_ID: &str = "nl.lecomputeur.vibez4.alpha";
const MAX_EVENT: u64 = 2_000_000;
struct Process {
    child: Child,
    input: ChildStdin,
    #[cfg(target_os="windows")]
    _job:platform_desktop::BackendJob,
}
#[derive(Clone)]
struct Choice {
    path: String,
    chat: Option<String>,
}
#[derive(Default)]
struct Bridge {
    process: Mutex<Option<Process>>,
    chat: Mutex<Option<String>>,
    choice: Mutex<Option<Choice>>,
    login_url: Mutex<Option<String>>,
    login_gate: tokio::sync::Mutex<()>,
    login_labels: Mutex<Vec<String>>,
    serial: AtomicU64,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Screen {
    x: i32,
    y: i32,
    width: u32,
    height: u32,
}
fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}
fn local_url(url: &url::Url) -> bool {
    ((url.scheme() == "tauri" && url.host_str() == Some("localhost"))
        || (url.scheme() == "http" && url.host_str() == Some("tauri.localhost")))
        && matches!(url.path(), "" | "/" | "/index.html")
        && url.query().is_none()
}
#[tauri::command]
async fn get_state(webview: Webview, app: tauri::AppHandle) -> Result<Value, String> {
    screenshot_v4::require_dialog(&webview)?;
    Ok(screenshot_v4::dialog_state(&app).await)
}
#[tauri::command]
async fn capture_screenshot(webview: Webview, app: tauri::AppHandle, mode: String, paste: Option<bool>) -> Result<Value, String> {
    screenshot_v4::require_dialog(&webview)?;
    screenshot_dialog::capture(&app, &mode, paste.unwrap_or(false)).await
}
#[tauri::command]
async fn screenshot_action(webview: Webview, app: tauri::AppHandle, action: String) -> Result<Value, String> {
    screenshot_v4::require_dialog(&webview)?;
    screenshot_dialog::action(&app, &action).await
}
fn require_local(view: &Webview) -> Result<(), String> {
    let u=view.url().map_err(err)?;
    let mut panel=u.clone();panel.set_path("/index.html");
    if (view.label() == "main" && local_url(&u)) || (view.label()=="connector-panel" && u.path()=="/panel.html" && local_url(&panel)) {
        Ok(())
    } else {
        Err("Only the local VibeZ window can do this".into())
    }
}
fn safe_https(url: &url::Url) -> bool {
    url.scheme() == "https"
        && url.host_str().is_some()
        && url.port_or_known_default() == Some(443)
        && url.username().is_empty()
        && url.password().is_none()
}
fn validate_login(raw: &str) -> Result<url::Url, String> {
    let u = url::Url::parse(raw).map_err(|_| "Invalid Mistral address")?;
    if raw.len() > 8192
        || raw.chars().any(|c| c.is_whitespace() || c.is_control())
        || !safe_https(&u)
        || u.host_str() != Some("console.mistral.ai")
    {
        return Err("Only Mistral's own authorization page can be opened".into());
    }
    Ok(u)
}
fn intersects(a: Screen, b: Screen) -> bool {
    (a.x as i64) < b.x as i64 + b.width as i64
        && (b.x as i64) < a.x as i64 + a.width as i64
        && (a.y as i64) < b.y as i64 + b.height as i64
        && (b.y as i64) < a.y as i64 + a.height as i64
}
#[cfg(target_os = "linux")]
fn guard_game(safe: Screen) -> Result<(), String> {
    let output = Command::new("/usr/bin/xprop")
        .args(["-root", "_NET_CLIENT_LIST"])
        .output()
        .map_err(|_| "Cannot check the WoT screen")?;
    if !output.status.success() {
        return Err("Cannot check the WoT screen".into());
    }
    let text = String::from_utf8_lossy(&output.stdout);
    for id in text
        .split('#')
        .nth(1)
        .unwrap_or("")
        .split(|c: char| c == ',' || c.is_whitespace())
        .filter(|v| {
            v.starts_with("0x") && v.len() < 20 && v[2..].chars().all(|c| c.is_ascii_hexdigit())
        })
    {
        let props = Command::new("/usr/bin/xprop")
            .args(["-id", id, "_NET_WM_NAME"])
            .output()
            .map_err(err)?;
        let title = String::from_utf8_lossy(&props.stdout).to_lowercase();
        if !(title.contains("wot client") || title.contains("world of tanks")) {
            continue;
        }
        let geometry = Command::new("/usr/bin/xwininfo")
            .args(["-id", id])
            .output()
            .map_err(err)?;
        let geometry = String::from_utf8_lossy(&geometry.stdout);
        let value = |key: &str| -> Result<i32, String> {
            geometry
                .lines()
                .find(|l| l.trim_start().starts_with(key))
                .and_then(|l| l.split(':').nth(1))
                .and_then(|s| s.trim().parse::<i32>().ok())
                .ok_or_else(|| "The WoT screen is unclear. VibeZ does not open.".into())
        };
        let game = Screen {
            x: value("Absolute upper-left X")?,
            y: value("Absolute upper-left Y")?,
            width: value("Width")? as u32,
            height: value("Height")? as u32,
        };
        if intersects(safe, game) {
            return Err(
                "WoT is now on the configured VibeZ screen. VibeZ does not open on that screen."
                    .into(),
            );
        }
    }
    Ok(())
}
static SAVED_SAFE_OUTPUT:std::sync::OnceLock<Option<String>>=std::sync::OnceLock::new();
fn safe_output() -> Result<Option<String>,String> {
    let raw=std::env::var("VIBEZ_SAFE_OUTPUT").ok();
    let explicit=display_policy::requested_output(raw.as_deref())?.map(str::to_owned);
    Ok(explicit.or_else(||SAVED_SAFE_OUTPUT.get().cloned().flatten()))
}
fn native_screen(monitor:&tauri::Monitor)->Screen {
    Screen{x:monitor.position().x,y:monitor.position().y,width:monitor.size().width,height:monitor.size().height}
}
fn screen(app: &tauri::AppHandle) -> Result<Screen, String> {
    let monitors = app.available_monitors().map_err(err)?;
    let screens:Vec<_>=monitors.iter().map(native_screen).collect();
    let primary=app.primary_monitor().map_err(err)?.as_ref().map(native_screen);
    #[cfg(target_os = "linux")]
    if let Some(output_name)=safe_output()? {
        // Explicit personal safety mode resolves the real output connector and
        // verifies it against native geometry. It must never silently fall back.
        let output=Command::new("/usr/bin/xrandr").arg("--listmonitors").output()
            .map_err(|_|"Cannot check the configured safe screen")?;
        if !output.status.success(){return Err("Cannot check the configured safe screen".into());}
        let requested=String::from_utf8_lossy(&output.stdout).lines()
            .find_map(|line|display_policy::parse_monitor(line,&output_name))
            .ok_or("The configured safe screen is not available")?;
        let selected=display_policy::select(&screens,primary,Some(requested))?;
        guard_game(selected)?;
        return Ok(selected);
    }
    #[cfg(not(target_os = "linux"))]
    if safe_output()?.is_some() {
        return Err("The configured Linux screen protection is not available on this system".into());
    }
    // Ordinary Linux, including a one-screen Wayland laptop, needs no XRandR
    // connector names or X11 utilities to open on its native primary monitor.
    display_policy::select(&screens,primary,None)
}
fn monitor_scale(app:&tauri::AppHandle,screen:Screen)->Result<f64,String> {
    app.available_monitors().map_err(err)?.iter().find(|m|native_screen(m)==screen)
        .map(|m|m.scale_factor()).ok_or_else(||"The screen has changed".into())
}
#[cfg(target_os = "linux")]
fn position_dialog(app:&tauri::AppHandle,dialog:&gtk::FileChooserDialog,screen:Screen)->Result<(),String> {
    let scale=monitor_scale(app,screen)?;let(x,y,width,height)=display_policy::dialog_bounds(screen,scale)?;
    dialog.set_default_size(width,height);
    if safe_output()?.is_some() {
        dialog.set_position(gtk::WindowPosition::None);dialog.move_(x,y);
    } else {
        dialog.set_position(gtk::WindowPosition::CenterOnParent);
    }
    Ok(())
}
fn is_flatpak()->bool {
    std::env::var_os("FLATPAK_ID").is_some()||std::path::Path::new("/.flatpak-info").is_file()
}
#[cfg(target_os = "linux")]
fn portal_pick(parent:&impl gtk::glib::IsA<gtk::Window>,title:&str,action:gtk::FileChooserAction,accept:&str,cancel:&str,multiple:bool)->Result<Option<Vec<std::path::PathBuf>>,String> {
    if safe_output()?.is_some() {
        // Portal windows belong to the desktop compositor. Unlike our own GTK
        // windows their monitor cannot be verified before they are shown.
        return Err("A system dialog cannot be placed safely with the configured screen protection".into());
    }
    let chooser=gtk::FileChooserNative::new(Some(title),Some(parent),action,Some(accept),Some(cancel));
    chooser.set_modal(true);chooser.set_select_multiple(multiple);
    let response=chooser.run();
    let result=if response==gtk::ResponseType::Accept {Some(chooser.filenames())}else{None};
    chooser.destroy();Ok(result)
}
fn created_child(parent:&std::path::Path,chosen:&std::path::Path)->Result<std::path::PathBuf,String> {
    let canonical=chosen.canonicalize().map_err(err)?;
    if canonical.parent()!=Some(parent)||!canonical.is_dir(){return Err("Create the new workspace directly in the chosen location".into());}
    Ok(canonical)
}
fn place(window: &tauri::Window) -> Result<(), String> {
    let s = screen(window.app_handle())?;
    let scale=monitor_scale(window.app_handle(),s)?;
    let placed=display_policy::window_bounds(s,scale,(1280,860))?;
    let min_width=((760.*scale).round() as u32).min(placed.width);
    let min_height=((520.*scale).round() as u32).min(placed.height);
    window.set_min_size(Some(PhysicalSize::new(min_width,min_height))).map_err(err)?;
    window
        .set_size(PhysicalSize::new(placed.width,placed.height))
        .map_err(err)?;
    window
        .set_position(PhysicalPosition::new(placed.x,placed.y))
        .map_err(err)
}
fn send(app:&tauri::AppHandle,event:Value) {
    if work_native::handle_event(app,&event) {return;}
    if !official_web::observe(app,&event) {return;}
    chat_downloads::observe(app,&event);
    composer_connector::observe(app,&event);
    project_import::observe(app,&event);
    project_overview::observe(app,&event);
    for label in ["main","connector-panel"] {
        let _=app.emit_to(EventTarget::Webview{label:label.into()},"app-engine",event.clone());
    }
}

fn write_engine(app: &tauri::AppHandle, payload: &Value) -> Result<(), String> {
    let text = serde_json::to_string(payload).map_err(err)?;
    if text.len() > 1_200_000 {
        return Err("Bericht is te groot".into());
    }
    let state = app.state::<Bridge>();
    let mut guard = state.process.lock().map_err(err)?;
    let process = guard
        .as_mut()
        .ok_or("The conversation connection has not started")?;
    writeln!(process.input, "{text}")
        .and_then(|_| process.input.flush())
        .map_err(|_| "The conversation connection stopped. Open VibeZ again.".into())
}
fn close_login(app: &tauri::AppHandle) {
    let labels = app
        .state::<Bridge>()
        .login_labels
        .lock()
        .map(|mut p| std::mem::take(&mut *p))
        .unwrap_or_default();
    for label in labels {
        if let Some(w) = app.get_webview_window(&label) {
            let _ = w.destroy();
        }
    }
}
fn engine_interpreter(app:&tauri::AppHandle)->Result<std::path::PathBuf,String> {
    #[cfg(target_os="linux")]
    {let _=app;Ok("/usr/bin/python3".into())}
    #[cfg(not(target_os="linux"))]
    {
        let root=app.path().resource_dir().map_err(err)?.join("python-runtime");
        #[cfg(target_os="windows")]
        let selected=root.join("python.exe");
        #[cfg(target_os="macos")]
        let selected=root.join("bin/python3");
        let folder=root.canonicalize().map_err(|_|"The bundled Python runtime is missing. Reinstall VibeZ.".to_owned())?;
        let interpreter=selected.canonicalize().map_err(|_|"The bundled Python runtime is missing. Reinstall VibeZ.".to_owned())?;
        if !interpreter.starts_with(folder)||!interpreter.is_file(){return Err("The bundled Python runtime is not valid".into());}
        Ok(interpreter)
    }
}
fn engine_environment(command:&mut Command,app:&tauri::AppHandle,interpreter:&std::path::Path)->Result<(),String> {
    command.env_clear().env("LANG","C.UTF-8");
    #[cfg(target_os="linux")]
    {let _=(app,interpreter);command.env("PATH","/usr/bin:/bin");}
    #[cfg(not(target_os="linux"))]
    {
        let home=app.path().app_data_dir().map_err(err)?.join("runtime-home");
        let temp=app.path().app_cache_dir().map_err(err)?.join("runtime-temp");
        for folder in [&home,&temp]{std::fs::create_dir_all(folder).map_err(err)?;}
        command.env("HOME",&home).env("TMPDIR",&temp).env("TEMP",&temp).env("TMP",&temp);
        let runtime=app.path().resource_dir().map_err(err)?.join("python-runtime").canonicalize().map_err(err)?;
        let certificates=runtime.join("certificates/cacert.pem").canonicalize()
            .map_err(|_|"The bundled security certificates are missing. Reinstall VibeZ.".to_owned())?;
        if !certificates.starts_with(&runtime)||!certificates.is_file(){return Err("The bundled security certificates are not valid".into());}
        command.env("SSL_CERT_FILE",certificates);
        let python=interpreter.parent().ok_or("The Python runtime has no location")?;
        #[cfg(target_os="macos")]
        command.env("PATH",std::env::join_paths([python,std::path::Path::new("/usr/bin"),std::path::Path::new("/bin"),std::path::Path::new("/usr/sbin"),std::path::Path::new("/sbin")]).map_err(err)?);
        #[cfg(target_os="windows")]
        {
            let windows=std::env::var_os("SystemRoot").or_else(||std::env::var_os("WINDIR")).map(std::path::PathBuf::from).filter(|p|p.is_absolute()&&p.join("System32").is_dir()).ok_or("The Windows system folder is not available")?;
            command.env("SystemRoot",&windows).env("WINDIR",&windows).env("USERPROFILE",&home).env("APPDATA",&home).env("LOCALAPPDATA",&home)
                .env("PATH",std::env::join_paths([python.to_path_buf(),windows.join("System32")]).map_err(err)?);
        }
    }
    Ok(())
}
fn start_engine(app: &tauri::AppHandle) -> Result<(), String> {
    let root = app.path().resource_dir().map_err(err)?.join("backend");
    let script = root.join("standalone_engine.py");
    if !script.is_file() {
        return Err("De meegeleverde gespreksengine ontbreekt".into());
    }
    #[cfg(all(feature = "native-smoke", target_os = "linux"))]
    let original_script = script.clone();
    #[cfg(all(feature = "native-smoke", target_os = "linux"))]
    let script = smoke::engine_script(&script)?;
    let data = app.path().app_data_dir().map_err(err)?.join("standalone");
    #[cfg(all(feature = "native-smoke", target_os = "linux"))]
    let data = smoke::engine_data(&data)?;
    let legacy = app
        .path()
        .app_config_dir()
        .map_err(err)?
        .join("project-folders.json");
    #[cfg(all(feature = "native-smoke", target_os = "linux"))]
    let legacy = smoke::legacy_path(&legacy)?;
    let interpreter=engine_interpreter(app)?;
    let mut command = Command::new(&interpreter);
    command
        .args(["-I", "-B", "-X", "utf8", "-u"])
        .arg(&script)
        .arg("--data-dir")
        .arg(data)
        .arg("--legacy-projects")
        .arg(legacy)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    engine_environment(&mut command,app,&interpreter)?;
    #[cfg(target_os="windows")]
    {use std::os::windows::process::CommandExt;command.creation_flags(0x08000000);}
    #[cfg(all(feature = "native-smoke", target_os = "linux"))]
    smoke::configure_engine(&mut command, &original_script);
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    let mut child = command.spawn().map_err(err)?;
    #[cfg(target_os="windows")]
    let job=match platform_desktop::BackendJob::attach(&child) {
        Ok(job)=>job,Err(error)=>{let _=child.kill();let _=child.wait();return Err(error);}
    };
    let input = child.stdin.take().ok_or("Geen gespreksverbinding")?;
    let output = child.stdout.take().ok_or("Geen gespreksuitvoer")?;
    *app.state::<Bridge>().process.lock().map_err(err)? = Some(Process { child, input, #[cfg(target_os="windows")] _job:job });
    let handle = app.clone();
    std::thread::spawn(move || {
        let mut reader = BufReader::new(output);
        loop {
            let mut line = Vec::new();
            match reader
                .by_ref()
                .take(MAX_EVENT + 1)
                .read_until(b'\n', &mut line)
            {
                Ok(0) | Err(_) => break,
                _ if line.len() as u64 > MAX_EVENT => break,
                _ => (),
            };
            let Ok(event) = serde_json::from_slice::<Value>(&line) else {
                break;
            };
            let state = handle.state::<Bridge>();
            if event["type"] == "state" {
                if let Ok(mut chat) = state.chat.lock() {
                    *chat = event["conversation_id"].as_str().map(str::to_owned);
                }
            }
            if event["type"] == "auth" {
                if let Ok(mut url) = state.login_url.lock() {
                    *url = event["url"]
                        .as_str()
                        .filter(|u| validate_login(u).is_ok())
                        .map(str::to_owned);
                }
                if matches!(
                    event["status"].as_str(),
                    Some("starting" | "connected" | "cancelled" | "error" | "disconnected")
                ) {
                    close_login(&handle);
                }
            }
            send(&handle, event);
        }
        send(
            &handle,
            json!({"type":"error","code":"engine_stopped","message":"The conversation connection stopped. Your history stays saved locally. Open VibeZ again."}),
        );
    });
    Ok(())
}
fn stop_engine(app: &tauri::AppHandle) {
    close_login(app);
    let process = app
        .state::<Bridge>()
        .process
        .lock()
        .ok()
        .and_then(|mut p| p.take());
    if let Some(mut p) = process {
        let _ = writeln!(p.input, "{{\"action\":\"shutdown\"}}");
        let _ = p.input.flush();
        #[cfg(unix)]
        unsafe {
            unix_kill(-(p.child.id() as i32), 15);
        }
        std::thread::spawn(move || {
            for _ in 0..20 {
                if matches!(p.child.try_wait(), Ok(Some(_))) {
                    return;
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            let _ = p.child.kill();
            let _ = p.child.wait();
        });
    }
}
#[cfg(unix)]
extern "C" {
    #[link_name = "kill"]
    fn unix_kill(pid: i32, sig: i32) -> i32;
}
#[tauri::command]
async fn app_command(
    webview: Webview,
    app: tauri::AppHandle,
    payload: Value,
) -> Result<(), String> {
    require_local(&webview)?;
    #[cfg(all(feature = "native-smoke", target_os = "linux"))]
    if smoke::observed(&app, &payload)? {
        return Ok(());
    }
    let action = payload["action"].as_str().ok_or("Invalid action")?;
    if !matches!(
        action,
        "hello"
            | "chat"
            | "approve"
            | "cancel"
            | "login"
            | "cancel_login"
            | "disconnect"
            | "model"
            | "new_project"
            | "rename_project"
            | "select_project"
            | "select_chat"
            | "new_chat"
            | "workspace"
            | "clear_workspace"
            | "export"
    ) {
        return Err("Onbekende handeling".into());
    }
    let state = app.state::<Bridge>();
    if matches!(
        action,
        "chat" | "approve" | "workspace" | "clear_workspace" | "export"
    ) {
        let current = state.chat.lock().map_err(err)?;
        if payload["conversation_id"].as_str() != current.as_deref() {
            return Err("The conversation changed. Try again in the current conversation.".into());
        }
    }
    if action == "workspace" {
        let chosen = state.choice.lock().map_err(err)?;
        let chat = state.chat.lock().map_err(err)?;
        if !chosen
            .as_ref()
            .is_some_and(|c| Some(c.path.as_str()) == payload["path"].as_str() && &c.chat == &*chat)
        {
            return Err("Choose the workspace with the folder picker".into());
        }
    }
    write_engine(&app, &payload)
}
#[tauri::command]
fn app_info(webview: Webview) -> Result<Value, String> {
    require_local(&webview)?;
    Ok(
        json!({"version":env!("CARGO_PKG_VERSION"),"sync_available":false,"standalone":true}),
    )
}
#[tauri::command]
async fn app_choose_folder(
    webview: Webview,
    app: tauri::AppHandle,
) -> Result<Option<String>, String> {
    app_choose_folder_mode(webview, app, false).await
}
async fn app_choose_folder_mode(
    webview: Webview,
    app: tauri::AppHandle,
    create: bool,
) -> Result<Option<String>, String> {
    require_local(&webview)?;
    let before = app.state::<Bridge>().chat.lock().map_err(err)?.clone();
    #[cfg(target_os = "linux")]
    let result: Result<Option<std::path::PathBuf>, String> = {
    let handle = app.clone();
    let (tx, rx) = tokio::sync::oneshot::channel();
    app.run_on_main_thread(move || {
        let result = (|| {
            let s = screen(&handle)?;
            let parent = handle
                .get_window("main")
                .ok_or("Het VibeZ-venster ontbreekt")?
                .gtk_window()
                .map_err(err)?;
            let title = classic_language::text(&handle,if create {"createWorkspace"} else {"chooseWorkspace"});
            let cancel = classic_language::text(&handle,"cancel");
            let accept = classic_language::text(&handle,if create {"createWorkspace"} else {"chooseFolderConfirm"});
            let granted_parent=if is_flatpak() {
                let pick_title=classic_language::text(&handle,if create {"chooseWorkspaceLocation"}else{"chooseWorkspace"});
                let pick_accept=classic_language::text(&handle,"chooseFolderConfirm");
                let Some(paths)=portal_pick(&parent,&pick_title,gtk::FileChooserAction::SelectFolder,&pick_accept,&cancel,false)? else{return Ok(None);};
                let path=paths.into_iter().next().ok_or("No folder was chosen")?;
                if !create{return Ok(Some(path));}
                Some(path.canonicalize().map_err(err)?)
            }else{None};
            let dialog = gtk::FileChooserDialog::with_buttons(
                Some(&title),
                Some(&parent),
                if create {gtk::FileChooserAction::CreateFolder} else {gtk::FileChooserAction::SelectFolder},
                &[
                    (cancel.as_str(), gtk::ResponseType::Cancel),
                    (accept.as_str(), gtk::ResponseType::Accept),
                ],
            );
            // CreateFolder offers a name field and creates the confirmed directory.
            dialog.set_create_folders(true);
            if let Some(ref location)=granted_parent {
                if !dialog.set_current_folder(location){return Err("The chosen location is not available".into());}
            }
            position_dialog(&handle,&dialog,s)?;
            #[cfg(all(feature = "native-smoke", target_os = "linux"))]
            smoke::observe_dialog(
                &dialog,
                s,
                if dialog.action() == gtk::FileChooserAction::Save {
                    "export"
                } else {
                    "folder"
                },
            );
            let response = dialog.run();
            let value = if response == gtk::ResponseType::Accept {
                dialog.filename()
            } else {
                None
            };
            dialog.close();
            match (granted_parent,value) {
                (Some(parent),Some(path))=>created_child(&parent,&path).map(Some),
                (_,value)=>Ok(value),
            }
        })();
        let _ = tx.send(result);
    })
    .map_err(err)?;
    rx.await.map_err(err)?

    };
    #[cfg(not(target_os = "linux"))]
    let result = platform_desktop::workspace(&app,create).await;
    let Some(path) = result? else { return Ok(None) };
    let value = std::fs::canonicalize(path)
        .map_err(err)?
        .to_string_lossy()
        .into_owned();
    let state = app.state::<Bridge>();
    if *state.chat.lock().map_err(err)? != before {
        return Err("The conversation changed while choosing the folder. Choose again.".into());
    }
    *state.choice.lock().map_err(err)? = Some(Choice {
        path: value.clone(),
        chat: before,
    });
    Ok(Some(value))
}
fn make_login(
    app: &tauri::AppHandle,
    url: url::Url,
    features: Option<tauri::webview::NewWindowFeatures>,
) -> Result<tauri::WebviewWindow, String> {
    let s = screen(app)?;
    let scale=monitor_scale(app,s)?;
    let placement=display_policy::window_bounds(s,scale,(620,760))?;
    let(lx,ly,lw,lh)=display_policy::logical_bounds(placement,scale)?;
    let state = app.state::<Bridge>();
    if state.login_labels.lock().map_err(err)?.len() >= 4 {
        return Err("Close a Mistral sign-in window first".into());
    }
    let label = format!(
        "mistral-login-{}",
        state.serial.fetch_add(1, Ordering::SeqCst)
    );
    let nested = app.clone();
    let data = app.path().app_data_dir().map_err(err)?.join("webview");
    let mut builder = WebviewWindowBuilder::new(app, &label, WebviewUrl::External(url))
        .data_directory(data)
        .title(format!("VibeZ V4 Beta · {}",classic_language::text(app,"autoConnect")))
        .inner_size(lw as f64,lh as f64)
        .min_inner_size(420_f64.min(lw as f64),480_f64.min(lh as f64))
        .position(lx as f64,ly as f64)
        .visible(false)
        .focused(false)
        .on_navigation(|u| u.as_str() == "about:blank" || safe_https(u))
        .on_permission_request(|_, _| tauri::webview::PermissionResponse::Deny)
        .on_new_window(move |url, features| {
            if !(url.as_str() == "about:blank" || safe_https(&url)) {
                return tauri::webview::NewWindowResponse::Deny;
            }
            match make_login(&nested, url, Some(features)) {
                Ok(window) => tauri::webview::NewWindowResponse::Create { window },
                Err(_) => tauri::webview::NewWindowResponse::Deny,
            }
        });
    #[cfg(not(target_os="linux"))]
    {builder=builder.on_download(chat_downloads::handle);}
    if let Some(features) = features {
        builder = builder.window_features(features);
    }
    // Once the project panel and Mistral surface are attached, main contains
    // multiple webviews and Tauri no longer exposes it as a WebviewWindow.
    // Parent the permission popup to the native Window instead.
    let parent = app.get_window("main").ok_or("Het hoofdvenster ontbreekt")?;
    #[cfg(target_os = "linux")]
    { builder = builder.transient_for_raw(&parent.gtk_window().map_err(err)?); }
    #[cfg(target_os = "windows")]
    { builder = builder.owner_raw(parent.hwnd().map_err(err)?); }
    #[cfg(target_os = "macos")]
    { builder = builder.parent_raw(parent.ns_window().map_err(err)?); }
    let window = builder.build().map_err(err)?;
    window.set_min_size(Some(PhysicalSize::new(((420.*scale).round() as u32).min(placement.width),((480.*scale).round() as u32).min(placement.height)))).map_err(err)?;
    window.set_size(PhysicalSize::new(placement.width,placement.height)).map_err(err)?;
    window
        .set_position(PhysicalPosition::new(placement.x,placement.y))
        .map_err(err)?;
    state.login_labels.lock().map_err(err)?.push(label);
    window.show().map_err(err)?;
    Ok(window)
}
#[tauri::command]
async fn app_open_login(
    webview: Webview,
    app: tauri::AppHandle,
    url: String,
) -> Result<(), String> {
    require_local(&webview)?;
    let state=app.state::<Bridge>();
    let _login_gate=state.login_gate.lock().await;
    let parsed = validate_login(&url)?;
    if app
        .state::<Bridge>()
        .login_url
        .lock()
        .map_err(err)?
        .as_deref()
        != Some(&url)
    {
        return Err("This sign-in attempt has expired. Try again.".into());
    }
    let label = app
        .state::<Bridge>()
        .login_labels
        .lock()
        .map_err(err)?
        .first()
        .cloned();
    if let Some(label) = label {
        if let Some(w) = app.get_webview_window(&label) {
            return w.set_focus().map_err(err);
        }
    }
    make_login(&app, parsed, None)?;
    Ok(())
}
#[tauri::command]
async fn app_save_export(
    webview: Webview,
    app: tauri::AppHandle,
    text: String,
) -> Result<bool, String> {
    require_local(&webview)?;
    if text.len() > 4_000_000 {
        return Err("This conversation is too large to export".into());
    }
    #[cfg(not(target_os = "linux"))]
    { platform_desktop::save_export(&app,text).await }
    #[cfg(target_os = "linux")]
    {
    let handle = app.clone();
    let (tx, rx) = tokio::sync::oneshot::channel();
    app.run_on_main_thread(move || {
        let result = (|| {
            let s = screen(&handle)?;
            let parent = handle
                .get_window("main")
                .ok_or("Geen VibeZ-venster")?
                .gtk_window()
                .map_err(err)?;
            let title=classic_language::text(&handle,"exportConversation");
            let cancel=classic_language::text(&handle,"cancel");
            let save=classic_language::text(&handle,"filesSave");
            let dialog = gtk::FileChooserDialog::with_buttons(
                Some(&title),
                Some(&parent),
                gtk::FileChooserAction::Save,
                &[
                    (&cancel, gtk::ResponseType::Cancel),
                    (&save, gtk::ResponseType::Accept),
                ],
            );
            dialog.set_current_name("VibeZ-chat.md");
            dialog.set_do_overwrite_confirmation(true);
            position_dialog(&handle,&dialog,s)?;
            #[cfg(all(feature = "native-smoke", target_os = "linux"))]
            smoke::observe_dialog(
                &dialog,
                s,
                if dialog.action() == gtk::FileChooserAction::Save {
                    "export"
                } else {
                    "folder"
                },
            );
            let response = dialog.run();
            let path = if response == gtk::ResponseType::Accept {
                dialog.filename()
            } else {
                None
            };
            dialog.close();
            if let Some(path) = path {
                std::fs::write(path, text).map_err(err)?;
                Ok(true)
            } else {
                Ok(false)
            }
        })();
        let _ = tx.send(result);
    })
    .map_err(err)?;
    rx.await.map_err(err)?
    }
}
#[tauri::command]
fn app_copy(webview: Webview, app: tauri::AppHandle, text: String) -> Result<(), String> {
    require_local(&webview)?;
    if text.len() > 2_000_000 {
        return Err("Tekst is te groot".into());
    }
    app.clipboard().write_text(text).map_err(err)
}
#[cfg(all(feature = "native-smoke", target_os = "linux"))]
#[path = "standalone_smoke.rs"]
mod smoke;
fn desktop_dialogs(builder:tauri::Builder<tauri::Wry>)->tauri::Builder<tauri::Wry> {
    #[cfg(not(target_os = "linux"))]
    { builder.plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::Builder::new().open_js_links_on_click(false).build()) }
    #[cfg(target_os = "linux")]
    { builder }
}
fn main() {
    if std::env::args().any(|a| a == "--version") {
        println!(
            "VibeZ V4 Beta · {} · standalone app",
            env!("CARGO_PKG_VERSION")
        );
        return;
    }
    #[cfg(all(feature = "native-smoke", target_os = "linux"))]
    if login_window_smoke::requested() {
        login_window_smoke::run();
        return;
    }
    if let Err(error)=alpha_updates::system_startup_lock(){eprintln!("{error}");std::process::exit(1);}
    let app = desktop_dialogs(tauri::Builder::default()
        .manage(Bridge::default())
        .manage(chat_downloads::SaveState::default())
        .manage(official_web::WebState::default())
        .manage(work_native::SetupState::default())
        .manage(composer_connector::ComposerState::default())
        .manage(project_import::ImportState::default())
        .manage(project_overview::OverviewState::default())
        .plugin(
            tauri_plugin_single_instance::Builder::new()
                .dbus_id("nl.lecomputeur.vibez4.alpha.Standalone")
                .callback(|app, _, _| {
                    if let Some(w) = app.get_window("main") {
                        if place(&w).is_ok() {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                })
                .build(),
        )
        .plugin(tauri_plugin_clipboard_manager::init()))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            app_command,
            app_info,
            alpha_updates::alpha_update_state,
            alpha_updates::alpha_update_check,
            alpha_updates::alpha_update_allow,
            app_choose_folder,
            app_open_login,
            app_save_export,
            app_copy,
            official_web::web_surface,
            official_web::web_navigate,
            official_web::chrome_panel,
            official_web::chrome_snapshot,
            get_state,
            capture_screenshot,
            screenshot_action,
            classic_language::language_get,
            classic_language::language_set,
            panel_prefs::panel_prefs_get,
            panel_prefs::panel_prefs_set,
            official_web::web_command,
            official_web::web_choose_folder,
            project_import::project_import_choose,
            project_import::project_import_commit,
            project_import::project_import_resolve,
            project_details::project_details_action,
            project_details::project_rules_edit,
            project_overview::project_open_folder
        ])
        .setup(|app| {
            #[cfg(all(feature="native-smoke",target_os="linux"))]
            let skip_updates=std::env::args().any(|v|matches!(v.as_str(),"--standalone-smoke-test"|"--live-code-probe"|"--live-connector-self-test"|"--live-work-self-test"));
            #[cfg(not(all(feature="native-smoke",target_os="linux")))]
            let skip_updates=false;
            if !skip_updates{alpha_updates::startup(app.handle());}
            let config = app.path().app_config_dir()?;
            let data = app.path().app_data_dir()?;
            std::fs::create_dir_all(&config)?;
            std::fs::create_dir_all(&data)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                for p in [&config, &data] {
                    std::fs::set_permissions(p, std::fs::Permissions::from_mode(0o700))?;
                }
            }
            #[cfg(target_os="linux")]
            {
                let raw=std::env::var("VIBEZ_SAFE_OUTPUT").ok();
                let selected=display_policy::load_safe_output(&config,raw.as_deref()).map_err(std::io::Error::other)?;
                let _=SAVED_SAFE_OUTPUT.set(selected);
            }
            app.manage(classic_language::Language::load(&config).map_err(std::io::Error::other)?);
            app.manage(panel_prefs::PanelPrefs::load(&config));
            screenshot_v4::manage(app.handle());
            #[cfg(target_os = "linux")]
            {
                gtk::glib::set_prgname(Some(APP_ID));
                gtk::glib::set_application_name("VibeZ V4 Beta");
                gtk::gdk::set_program_class(APP_ID);
            }
            let window =
                WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                    .title(format!("VibeZ V4 Beta · {}", env!("CARGO_PKG_VERSION")))
                    .data_directory(data.join("standalone-ui"))
                    .inner_size(1280., 860.)
                    .min_inner_size(760., 520.)
                    .visible(false)
                    .on_navigation(local_url)
                    .on_permission_request(|_, _| tauri::webview::PermissionResponse::Deny)
                    .on_new_window(|_, _| tauri::webview::NewWindowResponse::Deny)
                    .build()?;
            let panel_builder=tauri::webview::WebviewBuilder::new("connector-panel",WebviewUrl::App("panel.html".into()));
            #[cfg(target_os="linux")]
            let panel_builder=panel_builder.disable_drag_drop_handler();
            app.get_window("main").ok_or("Geen hoofdvenster")?.add_child(
                panel_builder
                    .data_directory(data.join("connector-ui"))
                    .on_navigation(|u|{let mut v=u.clone();v.set_path("/index.html");u.path()=="/panel.html"&&local_url(&v)})
                    .on_permission_request(|_,_|tauri::webview::PermissionResponse::Deny)
                    .on_new_window(|_,_|tauri::webview::NewWindowResponse::Deny),
                tauri::LogicalPosition::new(880.,54.),tauri::LogicalSize::new(400.,806.))?;
            classic_layout::layout(app.handle()).map_err(std::io::Error::other)?;
            project_import::attach(app.handle(),&app.get_webview("connector-panel").unwrap());
            // The local webview is named main; authorization is still checked by
            // document URL in addition to label. The remote web surface has no native capability.
            place(&app.get_window("main").ok_or("Geen hoofdvenster")?).map_err(std::io::Error::other)?;
            start_engine(app.handle()).map_err(std::io::Error::other)?;
            #[cfg(target_os = "linux")]
            window.gtk_window()?.set_focus_on_map(false);
            window.show()?;
            official_web::monitor(app.handle());
            if !skip_updates{alpha_updates::start(app.handle());}
            #[cfg(all(feature = "native-smoke", target_os = "linux"))]
            smoke::start(app.handle());
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label()=="main" && matches!(event,tauri::WindowEvent::Resized(_)|tauri::WindowEvent::ScaleFactorChanged{..}) {official_web::resize(window.app_handle());}
            if window.label().starts_with("mistral-login-")
                && matches!(event, tauri::WindowEvent::CloseRequested { .. })
            {
                let _ = write_engine(window.app_handle(), &json!({"action":"cancel_login"}));
            }
            if window.label() == "main"
                && matches!(event, tauri::WindowEvent::CloseRequested { .. })
            {
                stop_engine(window.app_handle());
            }
        })
        .build(tauri::generate_context!())
        .expect("VibeZ could not open on the configured display");
    app.run(|app, event| {
        if matches!(
            event,
            tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }
        ) {
            stop_engine(app);
            chat_downloads::cancel_all();
        }
    });
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn connector_geometry_accepts_positive_and_negative_coordinates() {
        let left = display_policy::parse_monitor(" 1: +DisplayPort-1 2560/597x1440/336+0+0 DisplayPort-1","DisplayPort-1").unwrap();
        assert_eq!(
            (left.x, left.y, left.width, left.height),
            (0, 0, 2560, 1440)
        );
        let negative =
            display_policy::parse_monitor(" 1: +DisplayPort-1 2560/597x1440/336-2560+0 DisplayPort-1","DisplayPort-1").unwrap();
        assert_eq!(negative.x, -2560);
        assert!(
            display_policy::parse_monitor(" 0: +*DisplayPort-0 2560/597x1440/336+2560+0 DisplayPort-0","DisplayPort-1").is_none()
        );
    }
    #[test]
    fn portal_created_workspace_is_a_real_direct_child_of_the_granted_parent() {
        let path=std::env::temp_dir().join(format!("vibez-alpha-created-child-{}",std::process::id()));
        std::fs::create_dir(&path).unwrap();let parent=path.canonicalize().unwrap();
        let child=parent.join("new-root");std::fs::create_dir(&child).unwrap();
        assert_eq!(created_child(&parent,&child).unwrap(),child);
        assert!(created_child(&parent,&parent).is_err());
        let file=parent.join("ordinary-file");std::fs::write(&file,"fixture").unwrap();assert!(created_child(&parent,&file).is_err());
        let nested=child.join("nested");std::fs::create_dir(&nested).unwrap();assert!(created_child(&parent,&nested).is_err());
        #[cfg(unix)] {let escaped=parent.join("escaped");std::os::unix::fs::symlink(&std::env::temp_dir(),&escaped).unwrap();assert!(created_child(&parent,&escaped).is_err());}
        std::fs::remove_dir_all(parent).unwrap();
    }
    #[test]
    fn adjacent_monitors_are_not_overlap() {
        let left = Screen {
            x: 0,
            y: 0,
            width: 2560,
            height: 1440,
        };
        let right = Screen {
            x: 2560,
            y: 0,
            width: 2560,
            height: 1440,
        };
        assert!(!intersects(left, right));
        assert!(intersects(left, Screen { x: 2000, ..right }));
    }
    #[test]
    fn only_bundled_main_document_is_local() {
        for raw in [
            "tauri://localhost/",
            "tauri://localhost/index.html",
            "http://tauri.localhost/index.html",
        ] {
            assert!(local_url(&raw.parse().unwrap()));
        }
        for raw in [
            "https://chat.mistral.ai/",
            "tauri://localhost/settings.html",
            "tauri://localhost/index.html?command=approve",
            "file:///tmp/index.html",
        ] {
            assert!(!local_url(&raw.parse().unwrap()));
        }
    }
    #[test]
    fn login_start_is_only_the_official_console() {
        assert!(validate_login("https://console.mistral.ai/codestral?process_id=test").is_ok());
        for raw in [
            "https://evil.test/",
            "https://console.mistral.ai:444/",
            "https://user:secret@console.mistral.ai/",
            "http://console.mistral.ai/",
            "https://console.mistral.ai/\n",
        ] {
            assert!(validate_login(raw).is_err());
        }
    }
}
