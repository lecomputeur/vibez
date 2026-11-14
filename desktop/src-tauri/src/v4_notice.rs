//! One-time local notice that VibeZ V4 Beta is available, plus fixed project links.
//! Only the constant HTTPS addresses below can be opened; pages pass a link name, never a URL.
use std::{path::{Path,PathBuf},time::Duration};
use tauri::{AppHandle,Manager,WebviewUrl,WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;
use crate::{desktop_ui,err,policy};
pub const LABEL:&str="v4notice";
const MARKER:&str="v4-beta-notice-shown";
pub const LINKS:[(&str,&str);4]=[
    ("v4beta","https://github.com/lecomputeur/vibez/releases/tag/v4.0.0-beta.3"),
    ("discussions","https://github.com/lecomputeur/vibez/discussions"),
    ("issue","https://github.com/lecomputeur/vibez/issues/new/choose"),
    ("repo","https://github.com/lecomputeur/vibez"),
];
pub fn link(name:&str)->Option<&'static str>{LINKS.iter().find(|(id,_)|*id==name).map(|(_,url)|*url)}
pub fn open_link(app:&AppHandle,name:&str)->Result<(),String>{
    let url=link(name).ok_or("Unknown link")?;
    app.opener().open_url(url,None::<&str>).map_err(|_|"Could not open the external link in your browser.".to_string())
}
fn marker(app:&AppHandle)->Result<PathBuf,String>{Ok(app.path().app_config_dir().map_err(err)?.join(MARKER))}
fn record(path:&Path)->Result<(),String>{std::fs::write(path,b"1\n").map_err(err)}
pub async fn show(app:&AppHandle)->Result<(),String>{
    if let Some(w)=app.get_webview_window(LABEL){w.show().map_err(err)?;return w.set_focus().map_err(err);}
    let window=WebviewWindowBuilder::new(app,LABEL,WebviewUrl::App("v4notice.html".into()))
        .title(format!("{} · {}",crate::title(),desktop_ui::preview(app,"v4NoticeTitle")))
        .inner_size(460.,330.).min_inner_size(360.,280.).visible(false).resizable(true)
        .data_directory(app.path().app_data_dir().map_err(err)?.join("controls"))
        .data_store_identifier([118,105,98,101,122,51,0,0,0,0,0,0,0,0,0,1])
        .on_navigation(policy::local_url).on_new_window(|_,_|tauri::webview::NewWindowResponse::Deny).build().map_err(err)?;
    crate::preview_updates::center_on_main(app,&window)?;
    window.show().map_err(err)?;window.set_focus().map_err(err)
}
/// Shows the notice once per profile, a few seconds after a visible start.
/// A start hidden in the tray (login autostart) postpones it to the next visible start.
pub fn schedule(app:AppHandle){
    let Ok(path)=marker(&app) else{return;};
    if path.exists(){return;}
    tauri::async_runtime::spawn(async move{
        tokio::time::sleep(Duration::from_secs(3)).await;
        if show(&app).await.is_ok(){let _=record(&path);}
    });
}
pub async fn action(app:&AppHandle,action:&str)->Result<(),String>{
    match action{
        "close"=>{if let Some(w)=app.get_webview_window(LABEL){w.close().map_err(err)?;}Ok(())},
        name if link(name).is_some()=>open_link(app,name),
        _=>Err("Unsupported notice action".into()),
    }
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn links_are_fixed_project_https_addresses() {
        for (name,url) in LINKS {
            let parsed=url::Url::parse(url).unwrap();
            assert_eq!(parsed.scheme(),"https",  "{name}");
            assert_eq!(parsed.host_str(),Some("github.com"),"{name}");
            assert!(parsed.path().starts_with("/lecomputeur/vibez"),"{name}");
            assert_eq!(link(name),Some(url));
        }
        assert!(link("https://example.com").is_none());
        assert!(link("close").is_none());
        assert!(link("").is_none());
    }
    #[test] fn marker_records_once() {
        let dir=std::env::temp_dir().join(format!("vibez-v4-notice-{}",std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path=dir.join(MARKER);
        assert!(!path.exists());record(&path).unwrap();assert!(path.exists());
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
