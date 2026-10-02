//! Manual, read-only update discovery for this preview, never Electron's release feed.
//! Downloads open in the user's browser; no package installation or credential handling.
use std::{sync::atomic::{AtomicBool, Ordering}, time::Duration};
use serde_json::Value;
use semver::Version;
use tauri::{AppHandle, Manager};
use tauri_plugin_opener::OpenerExt;
use gtk::prelude::*;

const REPO: &str = "lecomputeur/vibez";
const BRANCH: &str = "vibe/tauri-linux-preview-7c4e90";
const WORKFLOW: &str = ".github/workflows/tauri-preview-linux.yml";
const RUNS: &str = "https://api.github.com/repos/lecomputeur/vibez/actions/runs?branch=vibe%2Ftauri-linux-preview-7c4e90&status=success&event=push&per_page=10";
static BUSY: AtomicBool = AtomicBool::new(false);
struct BusyGuard;
impl Drop for BusyGuard { fn drop(&mut self) { BUSY.store(false, Ordering::SeqCst); } }

#[derive(Clone, Debug)]
struct Download { version: Version, url: String }
fn valid_run(run: &Value) -> Option<u64> {
    if run["status"] != "completed" || run["conclusion"] != "success"
        || run["event"] != "push" || run["head_branch"] != BRANCH
        || run["path"] != WORKFLOW || run["head_repository"]["full_name"] != REPO { return None; }
    run["id"].as_u64().filter(|id| *id > 0)
}
fn artifact(run: &Value, entry: &Value) -> Option<Download> {
    let run_id = valid_run(run)?;
    if entry["expired"] != false || entry["size_in_bytes"].as_u64()? == 0 { return None; }
    let id = entry["id"].as_u64().filter(|id| *id > 0)?;
    if entry["workflow_run"]["id"].as_u64()? != run_id
        || entry["workflow_run"]["head_branch"] != BRANCH
        || entry["workflow_run"]["head_sha"] != run["head_sha"] { return None; }
    let raw = entry["name"].as_str()?.strip_prefix("VibeZ-Tauri-Preview-")?.strip_suffix("-Linux-x64")?;
    let version = Version::parse(raw).ok()?;
    if !version.pre.is_empty() || !version.build.is_empty() { return None; }
    Some(Download { version, url: format!("https://github.com/{REPO}/actions/runs/{run_id}/artifacts/{id}") })
}
async fn get_json(client: &reqwest::Client, url: &str) -> Result<Value, &'static str> {
    let mut response = client.get(url).send().await.map_err(|_| "network")?;
    if matches!(response.status().as_u16(), 403 | 429) { return Err("rate-limit"); }
    if !response.status().is_success() { return Err("http"); }
    const LIMIT: usize = 1024 * 1024;
    if response.content_length().is_some_and(|n| n > LIMIT as u64) { return Err("size"); }
    let mut body = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "network")? {
        if body.len() + chunk.len() > LIMIT { return Err("size"); }
        body.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&body).map_err(|_| "json")
}
async fn discover() -> Result<Option<Download>, &'static str> {
    let client = reqwest::Client::builder().https_only(true)
        .redirect(reqwest::redirect::Policy::none()).timeout(Duration::from_secs(8))
        .user_agent(concat!("VibeZ-Tauri-Preview/", env!("CARGO_PKG_VERSION")))
        .default_headers({ let mut h = reqwest::header::HeaderMap::new();
            h.insert(reqwest::header::ACCEPT, reqwest::header::HeaderValue::from_static("application/vnd.github+json")); h })
        .build().map_err(|_| "client")?;
    let response = get_json(&client, RUNS).await?;
    let runs = response["workflow_runs"].as_array().ok_or("json")?;
    for run in runs.iter().take(10) {
        let Some(id) = valid_run(run) else { continue; };
        let entries = get_json(&client, &format!("https://api.github.com/repos/{REPO}/actions/runs/{id}/artifacts?per_page=100")).await?;
        let entries = entries["artifacts"].as_array().ok_or("json")?;
        if let Some(download) = entries.iter().filter_map(|entry| artifact(run, entry)).max_by(|a,b| a.version.cmp(&b.version)) {
            return Ok(Some(download));
        }
    }
    Ok(None)
}
fn newer(download: &Download, installed: &str) -> bool {
    Version::parse(installed).map(|current| download.version > current).unwrap_or(false)
}
fn report(app: &AppHandle, result: Result<Option<Download>, &'static str>) -> (String, String, Option<String>) {
    let tr = |en: &str, nl: &str| crate::desktop_ui::pair(app, en, nl);
    let installed = env!("CARGO_PKG_VERSION");
    let current = tr(&format!("Installed preview: {installed}"), &format!("Geïnstalleerde proefversie: {installed}"));
    match result {
        Ok(Some(download)) if newer(&download, installed) => {
            crate::message(app, "Preview update available.");
            (tr("Preview update available", "Update voor de proefversie beschikbaar"),
             format!("{current}\n{}\n\n{}", tr(&format!("New tested preview: {}", download.version), &format!("Nieuwe geteste proefversie: {}", download.version)),
                tr("Download opens the preview build on GitHub. A GitHub sign-in is required. Unpack the ZIP and install its .deb manually. Your regular VibeZ is not changed.",
                   "De download opent de proefversie op GitHub. Je moet daar zijn ingelogd. Pak de ZIP uit en installeer het .deb-bestand handmatig. Je gewone VibeZ blijft ongemoeid.")), Some(download.url))
        },
        Ok(Some(_)) => {
            crate::message(app, "No newer tested preview is available.");
            (tr("No preview update", "Geen update voor de proefversie"), format!("{current}\n\n{}", tr("No newer tested preview is available. The regular Electron edition is a separate product and is not compared.", "Er is geen nieuwere geteste proefversie beschikbaar. De gewone Electron-versie wordt niet met deze proefversie vergeleken.")), None)
        },
        Ok(None) => {
            crate::message(app, "No downloadable tested preview was found.");
            (tr("No preview download found", "Geen download voor de proefversie gevonden"), format!("{current}\n\n{}", tr("No completed preview build with a valid Linux download was found. Build artifacts may have expired. This does not mean your preview is up to date.", "Er is geen afgeronde proefversie met een geldige Linux-download gevonden. De downloads kunnen verlopen zijn. Dit betekent niet dat jouw proefversie bijgewerkt is.")), None)
        },
        Err(error) => {
            crate::message(app, "Could not check preview updates. Please try again later.");
            let detail = if error == "rate-limit" { tr("GitHub's request limit was reached. Please try again later.", "De aanvraaglimiet van GitHub is bereikt. Probeer het later opnieuw.") }
                else { tr("The update service could not be reached or returned an invalid response. Check your connection and try again later.", "De updatedienst kon niet worden bereikt of gaf een ongeldig antwoord. Controleer je verbinding en probeer het later opnieuw.") };
            (tr("Update check failed", "Updates controleren is niet gelukt"), format!("{current}\n\n{detail}"), None)
        },
    }
}
pub fn start(app: AppHandle) {
    if BUSY.swap(true, Ordering::SeqCst) { return; }
    crate::message(&app, "Checking for preview updates…");
    tauri::async_runtime::spawn(async move {
        let _guard = BusyGuard;
        let result = tokio::time::timeout(Duration::from_secs(25), discover()).await.unwrap_or(Err("timeout"));
        let (heading, body, download) = report(&app, result);
        let close = crate::desktop_ui::text(&app, "close");
        let open = crate::desktop_ui::pair(&app, "Open download", "Download openen");
        let handle = app.clone();
        if app.run_on_main_thread(move || {
            crate::show_main(&handle);
            let parent = handle.get_window("main").and_then(|w| w.gtk_window().ok());
            let dialog = gtk::MessageDialog::new(parent.as_ref(), gtk::DialogFlags::MODAL,
                gtk::MessageType::Info, gtk::ButtonsType::None, &heading);
            dialog.set_property("secondary-text", &body);
            dialog.add_button(&close, gtk::ResponseType::Close);
            if download.is_some() { dialog.add_button(&open, gtk::ResponseType::Accept); }
            dialog.connect_response(move |dialog, response| {
                dialog.close();
                if response == gtk::ResponseType::Accept {
                    if let Some(url) = &download {
                        if handle.opener().open_url(url, None::<&str>).is_err() {
                            crate::message(&handle, "Could not open the external link in your browser.");
                        }
                    }
                }
            });
            dialog.show_all();
        }).is_err() { crate::message(&app, "Could not check preview updates. Please try again later."); }
    });
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn fixtures() -> (Value, Value) {
        (json!({"id":10,"status":"completed","conclusion":"success","event":"push","head_branch":BRANCH,"path":WORKFLOW,"head_repository":{"full_name":REPO},"head_sha":"testsha"}),
         json!({"id":20,"name":"VibeZ-Tauri-Preview-0.1.12-Linux-x64","expired":false,"size_in_bytes":100,"workflow_run":{"id":10,"head_branch":BRANCH,"head_sha":"testsha"}}))
    }
    #[test] fn only_tested_matching_preview_artifacts_are_updates() {
        let (run, entry) = fixtures(); let d = artifact(&run, &entry).unwrap();
        assert_eq!(d.url, "https://github.com/lecomputeur/vibez/actions/runs/10/artifacts/20");
        assert!(newer(&d, "0.1.9")); assert!(!newer(&d, "0.1.12")); assert!(!newer(&d, "0.2.0"));
        for (key, value) in [("head_branch", json!("main")), ("conclusion", json!("failure")), ("status", json!("in_progress")), ("event", json!("pull_request")), ("path", json!(".github/workflows/release.yml"))] {
            let mut wrong = run.clone(); wrong[key] = value; assert!(artifact(&wrong, &entry).is_none());
        }
    }
    #[test] fn ignore_expired_foreign_and_malformed_packages() {
        let (run, entry) = fixtures();
        for name in ["VibeZ-2.0.2-Linux-x64", "VibeZ-Tauri-Preview-validation", "VibeZ-Tauri-Preview-0.1.99-Windows-x64", "VibeZ-Tauri-Preview-../danger-Linux-x64", "VibeZ-Tauri-Preview-0.1.99+rebuild-Linux-x64"] {
            let mut wrong = entry.clone(); wrong["name"] = json!(name); assert!(artifact(&run, &wrong).is_none());
        }
        let mut expired = entry.clone(); expired["expired"] = json!(true); assert!(artifact(&run, &expired).is_none());
        let mut other = entry.clone(); other["workflow_run"]["head_sha"] = json!("other"); assert!(artifact(&run, &other).is_none());
        let mut fork = run.clone(); fork["head_repository"]["full_name"] = json!("other/vibez"); assert!(artifact(&fork, &entry).is_none());
    }
    #[test] fn update_request_is_manual_and_never_an_electron_feed() {
        assert!(RUNS.starts_with("https://api.github.com/repos/lecomputeur/vibez/actions/runs?"));
        assert!(!RUNS.contains("/releases")); assert!(!BUSY.load(Ordering::SeqCst));
    }
}
