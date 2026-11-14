//! Explicit, local-only live-service diagnostic; excluded from public builds.
//! The Python driver keeps account credentials inside its own process.
use super::*;
use std::path::{Path, PathBuf};

pub fn requested() -> bool {
    std::env::args().any(|arg| arg == "--live-alpha7-fixture")
}

fn artifact_root() -> Result<PathBuf, String> {
    if !requested() { return Err("Live fixture was not requested".into()); }
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).parent().and_then(Path::parent)
        .ok_or("No diagnostic source root")?.join("artifacts").canonicalize().map_err(err)?;
    let raw = PathBuf::from(std::env::var_os("VIBEZ_ALPHA7_FIXTURE_ROOT").ok_or("No fixture directory")?);
    if !raw.is_absolute() || raw == base { return Err("Invalid fixture directory".into()); }
    let root = raw.canonicalize().map_err(err)?;
    if root != raw || !root.starts_with(&base) || !root.is_dir() {
        return Err("The live fixture must use its own artifact directory".into());
    }
    Ok(root)
}

pub fn enabled() -> bool { requested() && artifact_root().is_ok() }

pub fn engine_script(original: &Path) -> Result<PathBuf, String> {
    if !requested() { return Ok(original.into()); }
    artifact_root()?;
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).parent().and_then(Path::parent)
        .ok_or("No diagnostic source root")?.canonicalize().map_err(err)?;
    let driver = base.join("tools/alpha7-live-connector-driver.py");
    if !driver.is_file() || std::fs::symlink_metadata(&driver).map_err(err)?.file_type().is_symlink() {
        return Err("The live fixture driver is missing".into());
    }
    Ok(driver)
}

pub fn engine_data(original: &Path) -> Result<PathBuf, String> {
    if !requested() { return Ok(original.into()); }
    let data = artifact_root()?.join("backend-state");
    std::fs::create_dir_all(&data).map_err(err)?;
    if std::fs::symlink_metadata(&data).map_err(err)?.file_type().is_symlink() {
        return Err("The fixture backend directory is redirected".into());
    }
    Ok(data)
}

pub fn legacy_path(original: &Path) -> Result<PathBuf, String> {
    if !requested() { return Ok(original.into()); }
    Ok(artifact_root()?.join("no-legacy-projects.json"))
}

pub fn configure_engine(command: &mut Command, original: &Path) {
    if let Ok(root) = artifact_root() {
        command.arg("--engine-source").arg(original).arg("--fixture-root").arg(root);
    }
}

fn report(value: Value) -> Result<(), String> {
    let bytes = serde_json::to_vec_pretty(&value).map_err(err)?;
    if bytes.len() > 65536 { return Err("The fixture report is too large".into()); }
    let root = artifact_root()?;
    let temporary = root.join(format!(".live-report-{}.tmp", std::process::id()));
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)] { use std::os::unix::fs::OpenOptionsExt; options.mode(0o600); }
    let mut file = options.open(&temporary).map_err(err)?;
    file.write_all(&bytes).and_then(|_| file.sync_all()).map_err(err)?;
    drop(file);
    std::fs::rename(temporary, root.join("native-result.json")).map_err(err)
}

pub fn observed(app: &tauri::AppHandle, payload: &Value) -> Result<bool, String> {
    if !enabled() { return Ok(false); }
    if payload["action"] == "fixture_alpha7_run" {
        write_engine(app, &json!({"action":"fixture_live_run"}))?;
        return Ok(true);
    }
    if payload["action"] != "fixture_alpha7_done" { return Ok(false); }
    // Reports contain only boolean conclusions and a fixed short phase. Full
    // provider data, file content, addresses and credentials never cross here.
    let phase = payload["phase"].as_str().filter(|value| matches!(*value,
        "starting" | "needs_user_sign_in" | "complete" | "failed" | "timeout"))
        .ok_or("Invalid live fixture phase")?;
    let mut result = json!({"version":env!("CARGO_PKG_VERSION"),"phase":phase,
        "passed":payload["passed"].as_bool().unwrap_or(false),
        "live_mistral":true,"fixture_only_files":true,"credentials_exported":false});
    for key in ["on_screen_1", "authorization_clicked", "needs_user_sign_in", "completed"] {
        if let Some(value) = payload[key].as_bool() { result[key] = json!(value); }
    }
    report(result)?;
    Ok(true)
}

pub fn start(app: &tauri::AppHandle) {
    if !enabled() { return; }
    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        let safe = screen(&handle).ok();
        let on_safe = match (safe, handle.get_window("main")) {
            (Some(s), Some(w)) => match (w.outer_position(), w.outer_size()) {
                (Ok(p), Ok(size)) => p.x >= s.x && p.y >= s.y
                    && p.x as i64 + size.width as i64 <= s.x as i64 + s.width as i64
                    && p.y as i64 + size.height as i64 <= s.y as i64 + s.height as i64,
                _ => false,
            }, _ => false,
        };
        if !on_safe { let _ = report(json!({"phase":"failed","on_screen_1":false,"passed":false})); return; }
        tokio::time::sleep(std::time::Duration::from_millis(1700)).await;
        let script = r#"(async()=>{
const core=window.__TAURI__.core,event=window.__TAURI__.event;
const report=(phase,extra={})=>core.invoke('app_command',{payload:{action:'fixture_alpha7_done',phase,on_screen_1:true,...extra}});
window.__alpha7FixtureFinished=false;
await event.listen('app-engine',e=>{
 const d=e.payload;
 if(d.type==='auth'&&d.status==='waiting'&&d.url)core.invoke('app_open_login',{url:d.url}).catch(()=>report('failed'));
 if(d.type==='alpha7_fixture_result'){
  window.__alpha7FixtureFinished=true;
  report(d.report?.passed===true?'complete':'failed',{passed:d.report?.passed===true,completed:true});
 }
});
await report('starting');
await core.invoke('app_command',{payload:{action:'fixture_alpha7_run'}});
})().catch(()=>window.__TAURI__.core.invoke('app_command',{payload:{action:'fixture_alpha7_done',phase:'failed',passed:false}}));"#;
        if handle.get_webview("main").is_none_or(|view| view.eval(script).is_err()) {
            let _ = report(json!({"phase":"failed","on_screen_1":true,"passed":false}));
            return;
        }
        let mut clicked = std::collections::BTreeSet::new();
        for _ in 0..1200 {
            if let Some(main) = handle.get_webview("main") {
                if official_web::eval(&main,"String(window.__alpha7FixtureFinished===true)").await.ok().as_deref()==Some("true") { return; }
            }
            let labels = handle.state::<Bridge>().login_labels.lock().map(|v|v.clone()).unwrap_or_default();
            for label in labels {
                let Some(view) = handle.get_webview(&label) else { continue; };
                let Ok(url) = view.url() else { continue; };
                if !safe_https(&url) || url.host_str()!=Some("console.mistral.ai") || clicked.contains(&label) { continue; }
                let check = r#"(()=>{const visible=e=>e.getClientRects().length>0&&!e.disabled;if([...document.querySelectorAll('input[type=password],input[type=email],input[autocomplete=username],input[autocomplete=current-password]')].some(visible))return 'needs_sign_in';const buttons=[...document.querySelectorAll('button,[role=button]')].filter(e=>visible(e)&&['authorize','autoriseren','toestaan','allow'].includes((e.innerText||e.textContent||'').replace(/\s+/g,' ').trim().toLowerCase()));if(buttons.length!==1)return 'waiting';buttons[0].click();return 'clicked';})()"#;
                match official_web::eval(&view,check).await.unwrap_or_default().as_str() {
                    "clicked" => { clicked.insert(label); },
                    "needs_sign_in" => {
                        let _ = report(json!({"version":env!("CARGO_PKG_VERSION"),"phase":"needs_user_sign_in","needs_user_sign_in":true,"on_screen_1":true,"passed":false}));
                        // Leave the legitimate sign-in window for the user;
                        // never inspect credentials or external identity pages.
                    }, _ => {},
                }
            }
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        }
        let _ = report(json!({"phase":"timeout","on_screen_1":true,"passed":false}));
    });
}
