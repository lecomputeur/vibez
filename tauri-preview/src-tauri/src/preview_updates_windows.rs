//! Manual update discovery for the separate Windows preview build.
use std::{sync::atomic::{AtomicBool, Ordering}, time::Duration};
use semver::Version;
use serde_json::Value;
use tauri::AppHandle;
use tauri_plugin_opener::OpenerExt;

const REPO: &str = "lecomputeur/vibez";
const BRANCH: &str = "vibe/tauri-linux-preview-7c4e90";
const WORKFLOW: &str = ".github/workflows/tauri-preview-windows.yml";
const RUNS: &str = "https://api.github.com/repos/lecomputeur/vibez/actions/runs?branch=vibe%2Ftauri-linux-preview-7c4e90&status=success&event=push&per_page=10";
static BUSY: AtomicBool = AtomicBool::new(false);
struct Guard;
impl Drop for Guard { fn drop(&mut self) { BUSY.store(false, Ordering::SeqCst); } }

async fn get_json(client: &reqwest::Client, url: &str) -> Result<Value, ()> {
    let response = client.get(url).send().await.map_err(|_| ())?;
    if !response.status().is_success() { return Err(()); }
    let bytes = response.bytes().await.map_err(|_| ())?;
    if bytes.len() > 1024 * 1024 { return Err(()); }
    serde_json::from_slice(&bytes).map_err(|_| ())
}
async fn discover() -> Result<Option<(Version,String)>, ()> {
    let client = reqwest::Client::builder().https_only(true).timeout(Duration::from_secs(8))
        .user_agent(concat!("VibeZ-Tauri-Preview/", env!("CARGO_PKG_VERSION"))).build().map_err(|_| ())?;
    let data = get_json(&client, RUNS).await?;
    for run in data["workflow_runs"].as_array().ok_or(())?.iter().take(10) {
        if run["status"] != "completed" || run["conclusion"] != "success" || run["path"] != WORKFLOW
            || run["head_branch"] != BRANCH || run["head_repository"]["full_name"] != REPO { continue; }
        let id = run["id"].as_u64().ok_or(())?;
        let artifacts = get_json(&client, &format!("https://api.github.com/repos/{REPO}/actions/runs/{id}/artifacts?per_page=100")).await?;
        for entry in artifacts["artifacts"].as_array().ok_or(())? {
            if entry["expired"] != false { continue; }
            let Some(name) = entry["name"].as_str() else { continue; };
            let Some(raw) = name.strip_prefix("VibeZ-Tauri-Preview-").and_then(|v| v.strip_suffix("-Windows-x64-Store-Preview")) else { continue; };
            let Ok(version) = Version::parse(raw) else { continue; };
            let artifact_id = entry["id"].as_u64().ok_or(())?;
            return Ok(Some((version, format!("https://github.com/{REPO}/actions/runs/{id}/artifacts/{artifact_id}"))));
        }
    }
    Ok(None)
}
pub fn start(app: AppHandle) {
    if BUSY.swap(true, Ordering::SeqCst) { return; }
    crate::message(&app, "Checking for preview updates…");
    tauri::async_runtime::spawn(async move {
        let _guard = Guard;
        match tokio::time::timeout(Duration::from_secs(25), discover()).await {
            Ok(Ok(Some((version,url)))) if Version::parse(env!("CARGO_PKG_VERSION")).map(|v| version > v).unwrap_or(false) => {
                crate::message(&app, "Preview update available.");
                let _ = app.opener().open_url(url, None::<&str>);
            }
            Ok(Ok(_)) => crate::message(&app, "No newer tested preview is available."),
            _ => crate::message(&app, "Could not check preview updates. Please try again later."),
        }
    });
}
