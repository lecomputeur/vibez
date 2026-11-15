//! Fixed web pages the Settings menu may open in the person's own browser.
//! The panel names a page; it can never pass an address of its own.
use super::*;
#[cfg(not(target_os="linux"))]
use tauri_plugin_opener::OpenerExt;

fn address(link:&str)->Option<&'static str> {
    Some(match link {
        "report"=>"https://github.com/lecomputeur/vibez/issues/new/choose",
        "feedback"=>"https://github.com/lecomputeur/vibez/discussions/56",
        "source"=>"https://github.com/lecomputeur/vibez/tree/main/v4",
        "license"=>"https://github.com/lecomputeur/vibez/blob/main/v4/LICENSE",
        "website"=>"https://lecomputeur.github.io/vibez/",
        "tester"=>"https://github.com/ActiveUser435",
        _=>return None,
    })
}

#[tauri::command]
pub async fn app_open_link(webview:Webview,app:tauri::AppHandle,link:String)->Result<(),String> {
    require_local(&webview)?;
    if webview.label()!="connector-panel" {return Err("Open the project panel".into());}
    let url=address(&link).ok_or("Unknown link")?;
    #[cfg(not(target_os="linux"))]
    {app.opener().open_url(url,None::<&str>).map_err(err)}
    // On Linux GTK opens the default browser (through the portal inside Flatpak), as for folders.
    #[cfg(target_os="linux")]
    {
        let handle=app.clone();let(tx,rx)=tokio::sync::oneshot::channel();
        app.run_on_main_thread(move ||{
            let result=(||{
                let window=handle.get_window("main").ok_or("The VibeZ window is missing")?;
                let parent=window.gtk_window().map_err(err)?;
                gtk::show_uri_on_window(Some(&parent),url,0).map_err(|_|"The page could not be opened in your browser".to_string())
            })();let _=tx.send(result);
        }).map_err(err)?;
        rx.await.map_err(err)?
    }
}

#[cfg(test)]mod tests {
    use super::*;
    #[test]fn only_known_names_open_and_every_address_is_https_on_github_or_the_site() {
        for name in ["report","feedback","source","license","website","tester"] {
            let url=address(name).unwrap();
            assert!(url.starts_with("https://github.com/")||url.starts_with("https://lecomputeur.github.io/vibez/"),"{url}");
        }
        for name in ["","https://example.org","file:///etc/passwd","Report","report ","../report"] {assert!(address(name).is_none(),"{name}");}
    }
}
