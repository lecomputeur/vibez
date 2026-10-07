//! Native paste, with a memory-only PNG bridge when WebKitGTK hides image files.
use crate::{desktop_ui, err, policy, screenshots, PreviewState};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::Value;
use std::time::Duration;
use tauri::{AppHandle, Manager};

pub async fn paste(app: &AppHandle, png: &[u8], only_focused: bool) -> Result<&'static str, String> {
    let view=app.get_webview("vibe").ok_or("Vibe is not ready")?;
    let url=view.url().map_err(err)?;
    let dutch=desktop_ui::language(app)=="nl";
    if !allowed_url(&url,app.state::<PreviewState>().smoke) {
        return Err(if dutch {"Open eerst je gesprek in Vibe. De opname staat op het klembord."}
            else {"Open your conversation in Vibe first. The screenshot is on the clipboard."}.into());
    }
    if !only_focused {view.set_focus().map_err(err)?;}
    let script=include_str!("paste_composer.js").replace("__VIBEZ_PASTE_FOCUSED__",if only_focused {"true"}else{"false"});
    let state:Value=serde_json::from_str(&screenshots::eval_value(&view,script).await?).map_err(err)?;
    if state["ready"]!=true {
        return Err(if dutch {"Geen geschikt berichtveld gevonden. Open Chat of Work, of sla de PNG op voor Code."}
            else {"No message composer found. Open Chat or Work, or save the PNG for Code."}.into());
    }
    let result:Result<&'static str,String>=async {
        if view.url().map_err(err)?!=url {return Err("The page changed; the image was not pasted".into());}
        #[cfg(target_os="linux")]
        {
            use webkit2gtk::WebViewExt;
            let (tx,rx)=tokio::sync::oneshot::channel();
            view.with_webview(move |platform| {
                platform.inner().execute_editing_command("Paste");let _=tx.send(());
            }).map_err(err)?;
            tokio::time::timeout(Duration::from_secs(3),rx).await.map_err(err)?.map_err(err)?;
        }
        #[cfg(not(target_os="linux"))]
        {return Err("Direct paste is enabled only in this Linux test. Use Copy.".into());}
        for _ in 0..30 {
            tokio::time::sleep(Duration::from_millis(80)).await;
            let raw=screenshots::eval_value(&view,"JSON.stringify(window.__vibezPasteReceipt ? {received:window.__vibezPasteReceipt.received,images:window.__vibezPasteReceipt.images,trusted:window.__vibezPasteReceipt.trusted} : {})").await?;
            let receipt:Value=serde_json::from_str(&raw).map_err(err)?;
            if receipt["received"]==true && receipt["trusted"]==true {
                if receipt["images"].as_u64().unwrap_or(0)>0 {return Ok("native");}
                // WebKitGTK 2.52.6 explicitly disables clipboard file exposure
                // (WebCore DataTransfer::allowsFileAccess). Pass ONLY the PNG
                // captured by VibeZ as an in-memory File to the same composer.
                // No disk paths, security setting changes, clipboard scraping,
                // form submissions, or fallback after an ambiguous timeout.
                if view.url().map_err(err)?!=url {return Err("The page changed; the image was not pasted".into());}
                let encoded=serde_json::to_string(&STANDARD.encode(png)).map_err(err)?;
                let source=include_str!("paste_png_bridge.js").replace("__VIBEZ_SCREENSHOT_PNG__",&encoded);
                let bridge:Value=serde_json::from_str(&screenshots::eval_value(&view,source).await?).map_err(err)?;
                if bridge["ok"]==true {return Ok("memory");}
                break;
            }
        }
        Err(if dutch {"Vibe heeft de afbeelding niet ontvangen. De PNG is beschikbaar via Kopiëren of Opslaan."}
            else {"Vibe did not receive the image. The PNG is available with Copy or Save."}.into())
    }.await;
    let _=screenshots::eval_value(&view,"window.__vibezPasteReceipt?.cleanup?.(); delete window.__vibezPasteReceipt; true").await;
    if result.is_ok() {crate::message(app,if dutch {"Screenshot in je concept geplakt; niet verzonden."}else{"Screenshot pasted into your draft; not sent."});}
    result
}
fn allowed_url(url:&url::Url,smoke:bool)->bool {
    policy::auth_return_url(url)||(smoke&&policy::local_url(url))
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn paste_is_limited_to_content_and_explicit_offline_tests() {
        for s in ["https://accounts.google.com/","https://auth.mistral.ai/","https://evil.example/","https://vibe.mistral.ai.evil.example/","tauri://localhost/index.html"] {
            assert!(!allowed_url(&url::Url::parse(s).unwrap(),false));
        }
        assert!(allowed_url(&url::Url::parse("https://vibe.mistral.ai/").unwrap(),false));
        assert!(allowed_url(&url::Url::parse("tauri://localhost/index.html").unwrap(),true));
    }
}
