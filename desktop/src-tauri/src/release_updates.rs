//! Manual updates use published v3 releases, never temporary CI artifacts.
use std::{sync::atomic::{AtomicBool, Ordering}, time::Duration};
use serde_json::Value;
use semver::Version;
use tauri::AppHandle;
use tauri_plugin_opener::OpenerExt;
const API: &str = "https://api.github.com/repos/lecomputeur/vibez/releases?per_page=100";
static BUSY: AtomicBool = AtomicBool::new(false);
struct Guard;
impl Drop for Guard { fn drop(&mut self) { BUSY.store(false, Ordering::SeqCst); } }
#[derive(Debug)] struct Download { version: Version, url: String }
fn platform() -> String {
    let os = if cfg!(target_os="windows") {"Windows"} else if cfg!(target_os="macos") {"macOS"} else {"Linux"};
    let arch = if cfg!(target_arch="aarch64") {"arm64"} else {"x64"};
    format!("{os}-{arch}")
}
fn candidate(release: &Value, target: &str) -> Option<Download> {
    if release["draft"] != false || release["prerelease"] != false { return None; }
    let tag=release["tag_name"].as_str()?;
    let version=Version::parse(tag.strip_prefix('v')?).ok()?;
    if version.major < 3 || !version.pre.is_empty() || !version.build.is_empty() { return None; }
    let prefix=format!("VibeZ-{version}-{target}");
    let url_prefix=format!("https://github.com/lecomputeur/vibez/releases/download/{tag}/");
    let found=release["assets"].as_array()?.iter().any(|asset| {
        let Some(name)=asset["name"].as_str() else {return false};
        let suffix=name.strip_prefix(&prefix).unwrap_or("");
        [".deb",".rpm",".AppImage",".flatpak",".pkg.tar.zst","-Setup.exe",".msi",".dmg",".zip"].contains(&suffix)
            && asset["size"].as_u64().unwrap_or(0)>0
            && asset["browser_download_url"].as_str()==Some(format!("{url_prefix}{name}").as_str())
    });
    if !found {return None;}
    Some(Download {version,url:format!("https://github.com/lecomputeur/vibez/releases/tag/{tag}")})
}
async fn discover() -> Result<Option<Download>,String> {
    let client=reqwest::Client::builder().https_only(true).redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(15)).user_agent(concat!("VibeZ/",env!("CARGO_PKG_VERSION"))).build().map_err(crate::err)?;
    let mut response=client.get(API).send().await.map_err(crate::err)?.error_for_status().map_err(crate::err)?;
    let mut body=Vec::new();
    while let Some(chunk)=response.chunk().await.map_err(crate::err)? {
        if body.len()+chunk.len()>4*1024*1024 {return Err("Release response exceeds size limit".into());}
        body.extend_from_slice(&chunk);
    }
    let data:Value=serde_json::from_slice(&body).map_err(crate::err)?;
    Ok(data.as_array().ok_or("Invalid release response")?.iter().filter_map(|r|candidate(r,&platform())).max_by(|a,b|a.version.cmp(&b.version)))
}
pub fn start(app: AppHandle) {
    if BUSY.swap(true,Ordering::SeqCst) {return;}
    crate::message(&app,"Checking for preview updates…");
    tauri::async_runtime::spawn(async move {
        let _guard=Guard;
        match discover().await {
            Ok(Some(d)) if Version::parse(env!("CARGO_PKG_VERSION")).map(|v|d.version>v).unwrap_or(false) => {
                crate::message(&app,"Preview update available.");
                if app.opener().open_url(d.url,None::<&str>).is_err() {crate::message(&app,"Could not open the external link in your browser.");}
            },
            Ok(Some(_)) => crate::message(&app,"No newer tested preview is available."),
            Ok(None) => crate::message(&app,"No downloadable tested preview was found."),
            Err(_) => crate::message(&app,"Could not check preview updates. Please try again later."),
        }
    });
}
#[cfg(test)] mod tests {
    use super::*;
    fn fixture()->Value {serde_json::json!({"draft":false,"prerelease":false,"tag_name":"v3.0.1","assets":[{"name":"VibeZ-3.0.1-Linux-x64.deb","size":100,"browser_download_url":"https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-Linux-x64.deb"}]})}
    #[test] fn published_matching_platform_is_required() {assert!(candidate(&fixture(),"Linux-x64").is_some());assert!(candidate(&fixture(),"Windows-x64").is_none());}
    #[test] fn ignore_drafts_preview_foreign_and_empty_assets() {
        for (key,value) in [("draft",serde_json::json!(true)),("prerelease",serde_json::json!(true)),("tag_name",serde_json::json!("v2.0.2"))] {let mut v=fixture();v[key]=value;assert!(candidate(&v,"Linux-x64").is_none());}
        let mut v=fixture();v["assets"][0]["browser_download_url"]=serde_json::json!("https://example.com/installer");assert!(candidate(&v,"Linux-x64").is_none());
        let mut v=fixture();v["assets"][0]["size"]=serde_json::json!(0);assert!(candidate(&v,"Linux-x64").is_none());
    }
}
