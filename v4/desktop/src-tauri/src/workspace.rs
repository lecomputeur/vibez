
use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, Read, Write},
    process::{Child, ChildStdin, Command, Stdio},
    sync::{atomic::{AtomicU64, AtomicBool, Ordering}, Mutex},
};
use tauri::{Emitter, EventTarget, Manager, Webview, WebviewUrl, LogicalPosition, LogicalSize};

#[path="workspace_projects.rs"]
mod projects;
#[cfg(target_os="linux")]
#[path="workspace_login.rs"]
mod login;
#[derive(Default)]
struct Context {
    project: Option<projects::Project>,
    chosen_project: Option<String>,
    initialized: bool,
}
const MAX_EVENT: u64 = 2_000_000;
#[cfg(feature = "native-smoke")]
#[path = "workspace_smoke.rs"]
mod native_smoke;
struct Process { child: Child, input: ChildStdin }
#[derive(Default)]
pub(crate) struct Bridge {
    process: Mutex<Option<Process>>,
    generation: AtomicU64,
    pub visible: AtomicBool,
    context: Mutex<Context>,
    gate: tokio::sync::Mutex<()>,
    chosen_folder: Mutex<Option<String>>,
    login_url: Mutex<Option<String>>,
    login_children: Mutex<Vec<String>>,
}
fn local_document(url: &url::Url) -> bool {
    ((url.scheme() == "tauri" && url.host_str() == Some("localhost"))
        || (url.scheme() == "http" && url.host_str() == Some("tauri.localhost")))
        && url.path() == "/workspace.html"
        && url.query().is_none()
}
fn require_local(webview: &Webview) -> Result<(), String> {
    if webview.label() == "workspace" && local_document(&webview.url().map_err(|_| "Window not available")?) {
        Ok(())
    } else { Err("Only the local VibeZ window can perform this action".into()) }
}
fn validate_login(url: &str) -> Result<(), String> {
    let parsed = url::Url::parse(url).map_err(|_| "Invalid sign-in address")?;
    if url.len() > 8192 || url.chars().any(|c| c.is_control() || c.is_whitespace())
        || parsed.scheme() != "https" || parsed.host_str() != Some("console.mistral.ai")
        || parsed.port_or_known_default() != Some(443) || !parsed.username().is_empty()
        || parsed.password().is_some()
    { return Err("Only Mistral's own sign-in page can be opened".into()); }
    Ok(())
}
fn send(app: &tauri::AppHandle, event: Value) {
    // File contents and sign-in URLs are never broadcast to other windows.
    let _ = app.emit_to(EventTarget::Webview { label: "workspace".into() }, "workspace-engine", event);
}
fn spawn_engine(app: &tauri::AppHandle) -> Result<(), String> {
    let script = app.path().resource_dir().map_err(|_| "Program files not available")?
        .join("backend/workspace_engine.py");
    if !script.is_file() { return Err("De meegeleverde gespreksengine ontbreekt".into()); }
    let mut command = Command::new("/usr/bin/python3");
    command.args(["-I", "-u"]).arg(script)
        .env_clear().env("PATH", "/usr/bin:/bin").env("LANG", "C.UTF-8")
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
    #[cfg(target_os = "linux")]
    { use std::os::unix::process::CommandExt; command.process_group(0); }
    let mut child = command.spawn().map_err(|_| "Cannot start the conversation engine. Install the DEB with the package installer.")?;
    let input = child.stdin.take().ok_or("Gespreksverbinding ontbreekt")?;
    let output = child.stdout.take().ok_or("Gespreksantwoord ontbreekt")?;
    let bridge = app.state::<Bridge>();
    let generation = bridge.generation.fetch_add(1, Ordering::SeqCst) + 1;
    *bridge.process.lock().map_err(|_| "Conversation engine not available")? = Some(Process { child, input });
    let handle = app.clone();
    std::thread::spawn(move || {
        let mut reader = BufReader::new(output);
        loop {
            let mut line = Vec::new();
            match reader.by_ref().take(MAX_EVENT + 1).read_until(b'\n', &mut line) {
                Ok(0) | Err(_) => break,
                _ if line.len() as u64 > MAX_EVENT => break,
                _ => (),
            }
            let Ok(event) = serde_json::from_slice::<Value>(&line) else { break; };
            let state = handle.state::<Bridge>();
            if state.generation.load(Ordering::SeqCst) != generation { break; }
            if event["type"] == "auth" {
                #[cfg(target_os="linux")]
                if matches!(event["status"].as_str(),Some("starting"|"connected"|"cancelled"|"disconnected"|"error")) { login::close(&handle); }
                if let Ok(mut url) = state.login_url.lock() {
                    *url = event.get("url").and_then(Value::as_str)
                        .filter(|value| validate_login(value).is_ok()).map(str::to_owned);
                }
            }
            send(&handle, event);
        }
        if handle.state::<Bridge>().generation.load(Ordering::SeqCst) == generation {
            send(&handle, json!({"type":"state","connected":false,"workspace":null,"mcp":false,"busy":false,"authenticating":false}));
            send(&handle, json!({"type":"error","message":"The connection stopped. Close VibeZ 4 Test and open it again."}));
        }
    });
    Ok(())
}

fn write_engine(app: &tauri::AppHandle, payload: &Value) -> Result<(), String> {
    let text = serde_json::to_string(payload).map_err(|_| "Invalid message")?;
    if text.len() > 1_200_000 { return Err("Bericht is te groot".into()); }
    let state=app.state::<Bridge>();
    let mut guard = state.process.lock().map_err(|_| "Conversation engine not available")?;
    let process = guard.as_mut().ok_or("Open VibeZ 4 Test again")?;
    if process.child.try_wait().map_err(|_| "Conversation engine not available")?.is_some() {
        return Err("The conversation engine stopped. Open VibeZ 4 Test again.".into());
    }
    writeln!(process.input, "{text}").and_then(|_| process.input.flush())
        .map_err(|_| "The conversation engine stopped. Open VibeZ 4 Test again.".into())
}
fn bindings_path(app: &tauri::AppHandle) -> Result<std::path::PathBuf,String> {
    Ok(app.path().app_config_dir().map_err(crate::err)?.join("project-folders.json"))
}
async fn detect_project(app: &tauri::AppHandle) -> Result<Option<projects::Project>,String> {
    #[cfg(feature="native-smoke")]
    if let Some(project)=native_smoke::detected() { return Ok(project); }
    let view = app.get_webview("vibe").ok_or("Mistral is not available yet")?;
    let url = view.url().map_err(crate::err)?;
    if !projects::origin(&url) { return Ok(None); }
    let mut project = projects::parse(&url);
    // A direct project URL is authoritative. Within a chat, only an explicit
    // visible project breadcrumb is eligible, never the full sidebar list.
    let raw = crate::screenshots::eval_value(&view, include_str!("workspace_project.js")).await.unwrap_or_default();
    if view.url().map_err(crate::err)? != url { return Err("Mistral is changing pages; try again".into()); }
    if let Ok(info)=serde_json::from_str::<Value>(&raw) {
        if project.is_none() && url.path().starts_with("/work/") {
            let mut candidates = std::collections::BTreeMap::new();
            if let Some(links)=info["links"].as_array() {
                for link in links.iter().take(6) {
                    if let Some(mut p)=link["href"].as_str().and_then(|u|u.parse().ok()).and_then(|u|projects::parse(&u)) {
                        if let Some(name)=link["name"].as_str().filter(|v|!v.trim().is_empty()) { p.name=name.chars().take(120).collect(); }
                        candidates.insert(p.id.clone(),p);
                    }
                }
            }
            if candidates.len()==1 { project=candidates.into_values().next(); }
        } else if let Some(p)=project.as_mut() {
            if let Some(name)=info["name"].as_str().filter(|v|!v.trim().is_empty()) { p.name=name.chars().take(120).collect(); }
        }
    }
    // Avoid briefly replacing a known name with the UUID fallback while
    // Mistral rerenders the same project. Names never determine file scope.
    if let Some(p)=project.as_mut() {
        if p.name==format!("Project {}",&p.id[..8]) {
            if let Some(previous)=app.state::<Bridge>().context.lock().map_err(crate::err)?.project.as_ref().filter(|old|old.id==p.id) {
                p.name=previous.name.clone();
            }
        }
    }
    Ok(project)
}
async fn sync_locked(app: &tauri::AppHandle) -> Result<(),String> {
    let project = detect_project(app).await?;
    let state=app.state::<Bridge>();
    let (changed, renamed) = {
        let c=state.context.lock().map_err(crate::err)?;
        (!c.initialized || c.project.as_ref().map(|p|&p.id)!=project.as_ref().map(|p|&p.id), c.project!=project)
    };
    if changed {
        let binding = projects::read(&bindings_path(app)?);
        let path=binding.as_ref().ok().and_then(|b|project.as_ref().and_then(|p|b.folders.get(&p.id).cloned()));
        // Revocation must also happen if a saved binding is corrupt/unavailable.
        write_engine(app, &json!({"action":"project","project":project,"path":path}))?;
        let mut c=state.context.lock().map_err(crate::err)?;
        c.chosen_project=None; *state.chosen_folder.lock().map_err(crate::err)?=None;
        c.project=project; c.initialized=true;
        if let Err(e)=binding { send(app,json!({"type":"project_error","message":e})); }
    } else if renamed {
        write_engine(app, &json!({"action":"project_meta","project":project}))?;
        state.context.lock().map_err(crate::err)?.project=project;
    }
    Ok(())
}
pub fn monitor(app: &tauri::AppHandle) {
    let handle=app.clone();
    tauri::async_runtime::spawn(async move {
        loop {
            tokio::time::sleep(std::time::Duration::from_millis(800)).await;
            if handle.get_window("main").is_none() { break; }
            let state=handle.state::<Bridge>();
            if state.process.lock().map(|p|p.is_none()).unwrap_or(true) { continue; }
            let _gate=state.gate.lock().await;
            if let Err(e)=sync_locked(&handle).await { send(&handle,json!({"type":"project_error","message":e})); }
        }
    });
}
#[tauri::command]
pub async fn workspace_command(webview: Webview, app: tauri::AppHandle, payload: Value) -> Result<(), String> {
    require_local(&webview)?;
    let action = payload.get("action").and_then(Value::as_str).ok_or("Invalid action")?;
    #[cfg(feature = "native-smoke")]
    if native_smoke::observed(&app, &payload)? { return Ok(()); }
    if !matches!(action, "hello" | "login" | "cancel_login" | "workspace" | "clear_workspace" | "chat" | "approve" | "cancel" | "model" | "reset" | "disconnect") {
        return Err("Onbekende handeling".into());
    }
    let state = app.state::<Bridge>();
    let _gate=state.gate.lock().await;
    sync_locked(&app).await?;
    let project=state.context.lock().map_err(crate::err)?.project.clone();
    if !matches!(action,"hello" | "cancel" | "login" | "cancel_login" | "disconnect")
        && payload.get("project_key").and_then(Value::as_str)!=project.as_ref().map(|p|p.id.as_str()) {
        return Err("You moved to another project. Wait until the right workspace appears.".into());
    }
    if action == "workspace" {
        let chosen = state.chosen_folder.lock().map_err(|_| "Folder picker not available")?;
        let context=state.context.lock().map_err(crate::err)?;
        if context.chosen_project!=project.as_ref().map(|p|p.id.clone())
            || payload.get("path").and_then(Value::as_str) != chosen.as_deref() || chosen.is_none() {
            return Err("Choose the workspace with the ‘Choose a workspace’ button".into());
        }
    }
    if matches!(action,"workspace" | "clear_workspace") {
        if let Some(project)=&project {
            let path=bindings_path(&app)?;
            let mut bindings=projects::read(&path)?;
            if action=="workspace" { bindings.folders.insert(project.id.clone(),payload["path"].as_str().ok_or("No workspace")?.into()); }
            else { bindings.folders.remove(&project.id); }
            projects::write(&path,&bindings)?;
        }
    }
    write_engine(&app, &payload)
}

#[tauri::command]
pub async fn workspace_choose_folder(webview: Webview, app: tauri::AppHandle) -> Result<Option<String>, String> {
    require_local(&webview)?;
    let state=app.state::<Bridge>();
    let before={ let _gate=state.gate.lock().await; sync_locked(&app).await?; state.context.lock().map_err(crate::err)?.project.as_ref().map(|p|p.id.clone()) };
    let result = tauri::async_runtime::spawn_blocking(|| {
        Command::new("/usr/bin/zenity").args(["--file-selection", "--directory", "--title=Choose a workspace for VibeZ 4 Test"])
            .stdin(Stdio::null()).stderr(Stdio::null()).output()
    }).await.map_err(|_| "Folder picker could not be opened")?
        .map_err(|_| "Folder picker is missing. Install the DEB with the package installer.")?;
    if !result.status.success() { return Ok(None); }
    let value = String::from_utf8(result.stdout).map_err(|_| "This folder name cannot be used")?
        .trim_end_matches('\n').to_owned();
    if value.is_empty() { return Ok(None); }
    let _gate=state.gate.lock().await;
    sync_locked(&app).await?;
    let mut context=state.context.lock().map_err(crate::err)?;
    if context.project.as_ref().map(|p|p.id.clone())!=before { return Err("The project changed while choosing the folder. Choose the folder again for the right project.".into()); }
    context.chosen_project=before;
    let value=std::fs::canonicalize(&value).map_err(|_|"This folder is not available")?.to_string_lossy().into_owned();
    *state.chosen_folder.lock().map_err(|_| "Folder picker not available")? = Some(value.clone());
    Ok(Some(value))
}

#[tauri::command]
pub async fn workspace_open_login(webview: Webview, app: tauri::AppHandle, url: String) -> Result<(), String> {
    require_local(&webview)?;
    validate_login(&url)?;
    if app.state::<Bridge>().login_url.lock().map_err(|_| "Sign-in not available")?.as_deref() != Some(&url) {
        return Err("This sign-in attempt has expired. Try again.".into());
    }
    #[cfg(target_os="linux")]
    { login::open(&app,url).await }
    #[cfg(not(target_os="linux"))]
    { Err("Shared Mistral sign-in is available in the local Linux test version".into()) }
}

pub fn login_closed(app: &tauri::AppHandle) {
    let _=write_engine(app,&json!({"action":"cancel_login"}));
}
pub fn stop_engine(app: &tauri::AppHandle) {
    #[cfg(target_os="linux")]
    login::close(app);
    let state = app.state::<Bridge>();
    state.generation.fetch_add(1, Ordering::SeqCst);
    let process = state.process.lock().ok().and_then(|mut p| p.take());
    if let Some(mut process) = process {
        let _ = writeln!(process.input, "{{\"action\":\"shutdown\"}}");
        let _ = process.input.flush();
        // One process group for the conversation engine and its MCP child.
        // Signal before returning: app exit must never leave a tool running.
        #[cfg(target_os = "linux")]
        unsafe { linux_kill(-(process.child.id() as i32), 15); }
        std::thread::spawn(move || {
            for _ in 0..30 {
                if matches!(process.child.try_wait(), Ok(Some(_))) { return; }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            #[cfg(target_os = "linux")]
            unsafe { linux_kill(-(process.child.id() as i32), 9); }
            let _ = process.child.kill();
            let _ = process.child.wait();
        });
    }
}
#[cfg(target_os = "linux")]
extern "C" { #[link_name = "kill"] fn linux_kill(pid: i32, sig: i32) -> i32; }


#[tauri::command]
pub async fn show_workspace(webview: Webview, app: tauri::AppHandle) -> Result<(), String> {
    crate::require_local(&webview)?;
    open(&app)
}
pub fn open(app: &tauri::AppHandle) -> Result<(), String> {
    let state = app.state::<Bridge>();
    let show = !state.visible.load(Ordering::SeqCst);
    if app.get_webview("workspace").is_none() {
        let data = app.path().app_data_dir().map_err(crate::err)?.join("local-files");
        let window = app.get_window("main").ok_or("VibeZ-venster ontbreekt")?;
        let builder = tauri::webview::WebviewBuilder::new("workspace", WebviewUrl::App("workspace.html".into()))
            .data_directory(data).on_navigation(local_document)
            .on_new_window(|_, _| tauri::webview::NewWindowResponse::Deny)
            .on_permission_request(|_, _| tauri::webview::PermissionResponse::Deny);
        window.add_child(builder, LogicalPosition::new(760., crate::policy::TOOLBAR_HEIGHT), LogicalSize::new(520., 760.)).map_err(crate::err)?;
        spawn_engine(app)?;
        monitor(app);
        #[cfg(feature = "native-smoke")]
        native_smoke::start(app);
    }
    state.visible.store(show, Ordering::SeqCst);
    crate::layout(app)?;
    if show { if let Some(view) = app.get_webview("workspace") { view.set_focus().map_err(crate::err)?; } }
    Ok(())
}
#[tauri::command]
pub fn workspace_hide(webview: Webview, app: tauri::AppHandle) -> Result<(), String> {
    require_local(&webview)?;
    app.state::<Bridge>().visible.store(false, Ordering::SeqCst);
    crate::layout(&app)
}
#[cfg(feature = "native-smoke")]
pub fn smoke_from_toolbar(app: &tauri::AppHandle) {
    let handle=app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_millis(1400));
        if let Some(view)=handle.get_webview("shell") {
            let _=view.eval_with_callback("JSON.stringify({ready:document.readyState,button:!!document.getElementById('local-files'),url:location.href})", |r|eprintln!("Toolbar before test: {r}"));
            let _=view.eval("(async()=>{for(let i=0;i<40;i++){const b=document.getElementById('local-files');if(b){b.click();return;}await new Promise(r=>setTimeout(r,200));}})()");
            std::thread::sleep(std::time::Duration::from_secs(3));
            let _=view.eval_with_callback("document.body.innerText", |r|eprintln!("Toolbar after test: {r}"));
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn local_commands_are_only_for_the_bundled_document() {
        for url in ["tauri://localhost/workspace.html", "http://tauri.localhost/workspace.html"] {
            assert!(local_document(&url.parse().unwrap()));
        }
        for url in ["https://vibe.mistral.ai/", "https://localhost/workspace.html", "tauri://localhost/other.html", "file:///etc/passwd", "tauri://localhost/?action=approve"] {
            assert!(!local_document(&url.parse().unwrap()));
        }
    }
    #[test]
    fn login_links_stay_on_the_official_console() {
        assert!(validate_login("https://console.mistral.ai/codestral?process=test").is_ok());
        for url in ["http://console.mistral.ai/", "https://console.mistral.ai.evil.test/", "https://console.mistral.ai:444/", "https://user:secret@console.mistral.ai/", "javascript:alert(1)", "https://console.mistral.ai/\n"] {
            assert!(validate_login(url).is_err());
        }
    }
}
