//! Browser sign-in in the main view's existing WebKit profile. No cookie
//! values are read/copied and this remote view has no native capabilities.
use super::*;
use tauri::{WebviewWindowBuilder, webview::{NewWindowResponse, PermissionResponse}};

const LABEL: &str = "workspace-login";

fn navigation_allowed(url: &url::Url) -> bool {
    url.as_str()=="about:blank" || crate::policy::auth_chain_url(url)
}
fn build(app: &tauri::AppHandle, related: webkit2gtk::WebView, url: url::Url) -> Result<(),String> {
    let data=app.path().app_data_dir().map_err(crate::err)?.join("webview");
    let nested=app.clone();
    let builder=WebviewWindowBuilder::new(app,LABEL,WebviewUrl::External(url.clone()))
        .data_directory(data).with_related_view(related)
        .title("VibeZ 4 Test · Allow Mistral connection")
        .inner_size(620.,760.).min_inner_size(420.,480.).center()
        .on_permission_request(|_,_|PermissionResponse::Deny)
        .on_navigation(navigation_allowed)
        .on_new_window(move |url,features| {
            // Preserve the existing, related-profile provider popup handling.
            // The native file API is not made available to any auth document.
            let before:std::collections::HashSet<_>=nested.webview_windows().into_keys().collect();
            let response=crate::auth::new_window(&nested,url,features);
            if matches!(&response,NewWindowResponse::Create{..}) {
                if let Ok(mut children)=nested.state::<Bridge>().login_children.lock() {
                    children.extend(nested.webview_windows().into_keys().filter(|label|!before.contains(label)));
                }
            }
            response
        });
    let parent=app.get_window("main").ok_or("Het hoofdvenster ontbreekt")?;
    let window=builder.transient_for_raw(&parent.gtk_window().map_err(crate::err)?).build().map_err(crate::err)?;
    crate::auth::attach_errors(app,window.as_ref())?;
    Ok(())
}
pub async fn open(app: &tauri::AppHandle, url: String) -> Result<(),String> {
    if let Some(window)=app.get_webview_window(LABEL) {
        window.show().map_err(crate::err)?;return window.set_focus().map_err(crate::err);
    }
    let view=app.get_webview("vibe").ok_or("The Mistral main window is not available yet")?;
    let handle=app.clone();
    let url=url.parse().map_err(|_|"Invalid Mistral address")?;
    let(tx,rx)=tokio::sync::oneshot::channel();
    view.with_webview(move |platform| {
        // Construct on the GTK thread. Related views inherit the exact context,
        // including HttpOnly sign-in cookies, rather than a second cookie jar.
        let _=tx.send(build(&handle,platform.inner().clone(),url));
    }).map_err(crate::err)?;
    rx.await.map_err(|_|"The Mistral window could not be opened")?
}
pub fn close(app: &tauri::AppHandle) {
    if let Some(window)=app.get_webview_window(LABEL) {let _=window.destroy();}
    let labels=app.state::<Bridge>().login_children.lock().map(|mut c|std::mem::take(&mut *c)).unwrap_or_default();
    for label in labels { if let Some(window)=app.get_webview_window(&label) {let _=window.destroy();} }
}
#[cfg(feature="native-smoke")]
pub fn verify_profile(app: &tauri::AppHandle) -> Result<(),String> {
    use gtk::glib::object::ObjectType;
    use webkit2gtk::{WebViewExt,WebContextExt};
    let main=app.get_webview("vibe").ok_or("No main view")?;
    let handle=app.clone();
    main.with_webview(move |platform| {
        let native=platform.inner();
        let context=native.context().unwrap();
        let manager=context.website_data_manager().unwrap();
        let context_ptr=context.as_ptr() as usize;
        let manager_ptr=manager.as_ptr() as usize;
        build(&handle,native.clone(),"about:blank".parse().unwrap()).unwrap();
        let check=handle.clone();
        handle.get_webview_window(LABEL).unwrap().with_webview(move |p| {
            let context=p.inner().context().unwrap();
            let manager=context.website_data_manager().unwrap();
            let report=json!({"same_context":context.as_ptr() as usize==context_ptr,"same_data_manager":manager.as_ptr() as usize==manager_ptr,
                "no_cookie_copy":true,"live_mistral":false});
            let path=std::env::var("VIBEZ4_NATIVE_SMOKE_OUTPUT").unwrap()+".shared-login.json";
            std::fs::write(path,serde_json::to_vec_pretty(&report).unwrap()).unwrap();
            close(&check);
        }).unwrap();
    }).map_err(crate::err)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn shared_login_keeps_https_auth_redirects_and_rejects_local_documents() {
        for raw in ["about:blank","https://console.mistral.ai/codestral?process_id=test","https://auth.mistral.ai/authorize","https://accounts.google.com/signin"] {assert!(navigation_allowed(&raw.parse().unwrap()));}
        for raw in ["file:///etc/passwd","tauri://localhost/workspace.html","http://console.mistral.ai/","https://user:secret@console.mistral.ai/","https://console.mistral.ai:444/","javascript:alert(1)"] {assert!(!navigation_allowed(&raw.parse().unwrap()));}
    }
}
