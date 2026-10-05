//! Automatic and manual update checks against published VibeZ 3 releases.
use std::{sync::atomic::{AtomicBool, Ordering}, time::Duration};
use serde_json::Value;
use semver::Version;
use tauri::AppHandle;
use tauri_plugin_opener::OpenerExt;

const API: &str = "https://api.github.com/repos/lecomputeur/vibez/releases?per_page=100";
const STORE_URI: &str = "ms-windows-store://pdp/?ProductId=9NR7L2G4MS08";
const STORE_WEB: &str = "https://apps.microsoft.com/detail/9NR7L2G4MS08";
static BUSY: AtomicBool = AtomicBool::new(false);

struct Guard;
impl Drop for Guard { fn drop(&mut self) { BUSY.store(false, Ordering::SeqCst); } }

#[derive(Debug)]
struct Download { version: Version, url: String }

fn platform() -> String {
    let os = if cfg!(target_os="windows") {"Windows"} else if cfg!(target_os="macos") {"macOS"} else {"Linux"};
    let arch = if cfg!(target_arch="aarch64") {"arm64"} else {"x64"};
    format!("{os}-{arch}")
}

#[cfg(target_os = "windows")]
fn store_packaged() -> bool {
    #[link(name = "kernel32")]
    extern "system" {
        fn GetCurrentPackageFullName(package_full_name_length: *mut u32, package_full_name: *mut u16) -> i32;
    }
    // APPMODEL_ERROR_NO_PACKAGE (15700) means a normal unpackaged process.
    // ERROR_INSUFFICIENT_BUFFER (122) with a non-zero length means this process has package identity.
    let mut length = 0u32;
    unsafe { GetCurrentPackageFullName(&mut length, std::ptr::null_mut()) == 122 && length > 0 }
}
#[cfg(not(target_os = "windows"))]
fn store_packaged() -> bool { false }

fn candidate(release: &Value, target: &str) -> Option<Download> {
    if release["draft"] != false || release["prerelease"] != false { return None; }
    let tag = release["tag_name"].as_str()?;
    let version = Version::parse(tag.strip_prefix('v')?).ok()?;
    if version.major < 3 || !version.pre.is_empty() || !version.build.is_empty() { return None; }
    let prefix = format!("VibeZ-{version}-{target}");
    let url_prefix = format!("https://github.com/lecomputeur/vibez/releases/download/{tag}/");
    let found = release["assets"].as_array()?.iter().any(|asset| {
        let Some(name) = asset["name"].as_str() else { return false };
        let suffix = name.strip_prefix(&prefix).unwrap_or("");
        [".deb",".rpm",".AppImage",".flatpak",".pkg.tar.zst","-Setup.exe",".msi",".dmg",".zip"].contains(&suffix)
            && asset["size"].as_u64().unwrap_or(0) > 0
            && asset["browser_download_url"].as_str() == Some(format!("{url_prefix}{name}").as_str())
    });
    if !found { return None; }
    Some(Download { version, url: format!("https://github.com/lecomputeur/vibez/releases/tag/{tag}") })
}

async fn discover() -> Result<Option<Download>, String> {
    let client = reqwest::Client::builder()
        .https_only(true)
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(15))
        .user_agent(concat!("VibeZ/", env!("CARGO_PKG_VERSION")))
        .build().map_err(crate::err)?;
    let mut response = client.get(API).send().await.map_err(crate::err)?
        .error_for_status().map_err(crate::err)?;
    let mut body = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(crate::err)? {
        if body.len() + chunk.len() > 4 * 1024 * 1024 { return Err("Release response exceeds size limit".into()); }
        body.extend_from_slice(&chunk);
    }
    let data: Value = serde_json::from_slice(&body).map_err(crate::err)?;
    Ok(data.as_array().ok_or("Invalid release response")?.iter()
        .filter_map(|r| candidate(r, &platform())).max_by(|a,b| a.version.cmp(&b.version)))
}

fn open_store(app: &AppHandle) {
    if app.opener().open_url(STORE_URI, None::<&str>).is_err() {
        let _ = app.opener().open_url(STORE_WEB, None::<&str>);
    }
}

pub fn check(app: AppHandle, manual: bool) {
    if BUSY.swap(true, Ordering::SeqCst) {
        if manual { crate::message(&app, "An update check is already running."); }
        return;
    }
    tauri::async_runtime::spawn(async move {
        let _guard = Guard;
        if store_packaged() {
            if manual {
                crate::message(&app, "Microsoft Store manages updates for this installation.");
                open_store(&app);
            }
            return;
        }
        if manual { crate::message(&app, "Checking for VibeZ updates…"); }
        let current = Version::parse(env!("CARGO_PKG_VERSION")).ok();
        match discover().await {
            Ok(Some(download)) if current.as_ref().map(|v| download.version > *v).unwrap_or(false) => {
                if manual {
                    crate::message(&app, format!("VibeZ {} is available — opening the download page.", download.version));
                    if app.opener().open_url(download.url, None::<&str>).is_err() {
                        crate::message(&app, "A newer VibeZ version is available, but the download page could not be opened.");
                    }
                } else {
                    crate::message(&app, format!("VibeZ {} is available. Open Settings and choose Check for updates.", download.version));
                }
            },
            Ok(Some(_)) => { if manual { crate::message(&app, "You already have the latest VibeZ version."); } },
            Ok(None) => { if manual { crate::message(&app, "No downloadable VibeZ release was found."); } },
            Err(_) => { if manual { crate::message(&app, "Could not check for VibeZ updates. Please try again later."); } },
        }
    });
}

pub fn schedule(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(Duration::from_secs(6)).await;
        let enabled = app.state::<crate::PreviewState>().settings.lock()
            .map(|s| s.auto_updates).unwrap_or(false);
        if enabled { check(app, false); }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> Value { serde_json::json!({"draft":false,"prerelease":false,"tag_name":"v3.0.1","assets":[{"name":"VibeZ-3.0.1-Linux-x64.deb","size":100,"browser_download_url":"https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-Linux-x64.deb"}]}) }
    #[test] fn published_matching_platform_is_required() {
        assert!(candidate(&fixture(),"Linux-x64").is_some());
        assert!(candidate(&fixture(),"Windows-x64").is_none());
    }
    #[test] fn ignore_drafts_old_major_foreign_and_empty_assets() {
        for (key,value) in [("draft",serde_json::json!(true)),("prerelease",serde_json::json!(true)),("tag_name",serde_json::json!("v2.0.2"))] {
            let mut v=fixture(); v[key]=value; assert!(candidate(&v,"Linux-x64").is_none());
        }
        let mut v=fixture(); v["assets"][0]["browser_download_url"]=serde_json::json!("https://example.com/installer");
        assert!(candidate(&v,"Linux-x64").is_none());
        let mut v=fixture(); v["assets"][0]["size"]=serde_json::json!(0);
        assert!(candidate(&v,"Linux-x64").is_none());
    }
}