//! Delivery and application-rendered attachment confirmation are separate operations.
use crate::{desktop_ui,err,policy,screenshots,PreviewState};
use base64::{engine::general_purpose::STANDARD,Engine as _};
use serde_json::Value;
use std::{time::Duration,sync::Mutex};
static DIAGNOSTIC:Mutex<String>=Mutex::new(String::new());
fn record(phase:&str,detail:&Value){if let Ok(mut d)=DIAGNOSTIC.lock(){*d=format!("{phase}: {detail}");}}
pub fn diagnostics()->String{DIAGNOSTIC.lock().map(|v|v.clone()).unwrap_or_default()}
use tauri::{AppHandle,Manager};
pub async fn paste(app:&AppHandle,png:&[u8],only_focused:bool)->Result<&'static str,String>{
    let view=app.get_webview("vibe").ok_or("Vibe is not ready")?;
    let url=view.url().map_err(err)?;
    let dutch=desktop_ui::language(app)=="nl";
    if !allowed_url(&url,app.state::<PreviewState>().smoke){return Err(if dutch{"Open eerst je gesprek in Vibe. De opname staat op het klembord."}else{"Open your conversation in Vibe first. The screenshot is on the clipboard."}.into());}
    if !only_focused{view.set_focus().map_err(err)?;}
    let script=include_str!("paste_composer.js").replace("__VIBEZ_PASTE_FOCUSED__",if only_focused{"true"}else{"false"});
    // Native focus and GTK allocation settle asynchronously after a chooser
    // or screen selector is hidden. Retry discovery, never the paste itself.
    let mut state=serde_json::json!({"ready":false,"reason":"not-inspected"});
    for _ in 0..25 {
        if view.url().map_err(err)?!=url{return Err(desktop_ui::preview(app,"pasteUnconfirmed"));}
        state=serde_json::from_str(&screenshots::eval_value(&view,script.clone()).await?).map_err(err)?;
        if state["ready"]==true{break;}
        tokio::time::sleep(Duration::from_millis(80)).await;
    }
    record("composer",&state);
    if state["ready"]!=true {
        return Err(format!("{} [P:{}]",desktop_ui::preview(app,"pasteUnconfirmed"),state["reason"].as_str().unwrap_or("unavailable")));
    }
    let result:Result<&'static str,String>=async{
        if view.url().map_err(err)?!=url{return Err("page-changed".into());}
        // Restore native Paste on every platform. Setting a hidden upload
        // input first is not equivalent to the user's normal paste action.
        #[cfg(target_os="linux")]{
            use webkit2gtk::WebViewExt;
            let(tx,rx)=tokio::sync::oneshot::channel();
            view.with_webview(move|platform|{platform.inner().execute_editing_command("Paste");let _=tx.send(());}).map_err(err)?;
            tokio::time::timeout(Duration::from_secs(3),rx).await.map_err(err)?.map_err(err)?;
        }
        #[cfg(target_os="windows")]{
            for kind in ["rawKeyDown","keyUp"]{
                screenshots::native_other::devtools(&view,"Input.dispatchKeyEvent",serde_json::json!({"type":kind,"modifiers":2,"key":"v","code":"KeyV","windowsVirtualKeyCode":86,"nativeVirtualKeyCode":86})).await?;
            }
        }
        #[cfg(target_os="macos")]{
            let(tx,rx)=tokio::sync::oneshot::channel();
            view.with_webview(move|platform|unsafe{
                let native=&*platform.inner().cast::<objc2_web_kit::WKWebView>();
                let _:()=objc2::msg_send![native,paste:std::ptr::null::<objc2::runtime::AnyObject>()];let _=tx.send(());
            }).map_err(err)?;
            tokio::time::timeout(Duration::from_secs(3),rx).await.map_err(err)?.map_err(err)?;
        }
        for _ in 0..30{
            tokio::time::sleep(Duration::from_millis(80)).await;
            let raw=screenshots::eval_value(&view,"JSON.stringify(window.__vibezPasteReceipt ? {received:window.__vibezPasteReceipt.received,images:window.__vibezPasteReceipt.images,trusted:window.__vibezPasteReceipt.trusted} : {})").await?;
            let receipt:Value=serde_json::from_str(&raw).map_err(err)?;
            record("native-paste",&receipt);
            if receipt["received"]==true&&receipt["trusted"]==true{
                if receipt["images"].as_u64().unwrap_or(0)>0{return confirmed(&view,&url,"native").await;}
                // Only an empty trusted native paste allows the memory fallback.
                // No ambiguous-timeout retry that could attach the image twice.
                if view.url().map_err(err)?!=url{return Err("The page changed; the image was not pasted".into());}
                let encoded=serde_json::to_string(&STANDARD.encode(png)).map_err(err)?;
                let source=include_str!("paste_png_bridge.js").replace("__VIBEZ_SCREENSHOT_PNG__",&encoded);
                let bridge:Value=serde_json::from_str(&screenshots::eval_value(&view,source).await?).map_err(err)?;
                if bridge["ok"]==true{return confirmed(&view,&url,"memory").await;}
                break;
            }
        }
        Err("The composer did not receive the image".into())
    }.await;
    let _=screenshots::eval_value(&view,"window.__vibezPasteReceipt?.cleanup?.(); delete window.__vibezPasteReceipt; true").await;
    if result.is_ok(){crate::message(app,desktop_ui::preview(app,"pasteConfirmed"));}
    result.map_err(|error|{record("not-confirmed",&serde_json::json!({"reason":error}));desktop_ui::preview(app,"pasteUnconfirmed")})
}
async fn confirmed(view:&tauri::Webview,url:&url::Url,method:&'static str)->Result<&'static str,String>{
    for _ in 0..60{
        tokio::time::sleep(Duration::from_millis(150)).await;
        if view.url().map_err(err)?.as_str()!=url.as_str(){return Err("Page changed".into());}
        let raw=screenshots::eval_value(view,"JSON.stringify(window.__vibezPasteReceipt?.status?.() || {})").await?;
        let receipt:Value=serde_json::from_str(&raw).map_err(err)?;
        record("attachment",&receipt);
        if receipt["rejected"]==true||receipt["reason"]=="composer-changed"{return Err("Attachment rejected".into());}
        if receipt["attached"]==true{return Ok(method);}
    }
    Err("The site did not show a new attachment".into())
}
fn allowed_url(url:&url::Url,smoke:bool)->bool{policy::auth_return_url(url)||(smoke&&policy::local_url(url))}
#[cfg(test)]mod tests{
    use super::*;
    #[test]fn paste_is_limited_to_content_and_explicit_offline_tests(){
        for s in ["https://accounts.google.com/","https://auth.mistral.ai/","https://evil.example/","https://vibe.mistral.ai.evil.example/","tauri://localhost/index.html"]{assert!(!allowed_url(&url::Url::parse(s).unwrap(),false));}
        assert!(allowed_url(&url::Url::parse("https://vibe.mistral.ai/").unwrap(),false));assert!(allowed_url(&url::Url::parse("tauri://localhost/index.html").unwrap(),true));
    }
}
