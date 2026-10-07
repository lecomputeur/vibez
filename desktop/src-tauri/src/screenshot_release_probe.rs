//! Offline native capture -> upload/paste -> application-rendered attachment.
use crate::{err,screenshots,PreviewState};
use serde_json::Value;
use tauri::{AppHandle,Manager};
use std::time::Duration;
use base64::{engine::general_purpose::STANDARD,Engine as _};
pub async fn run(app:&AppHandle)->Result<(),String>{
    if !app.state::<PreviewState>().smoke{return Err("Release probe requires explicit offline smoke mode".into());}
    let view=app.get_webview("vibe").ok_or("Missing test webview")?;
    let old=screenshots::eval_value(&view,"JSON.stringify({html:document.body.innerHTML,style:document.body.style.cssText})").await?;
    let result:Result<(),String>=async{
        view.eval(include_str!("screenshot_fixture.js")).map_err(err)?;tokio::time::sleep(Duration::from_millis(300)).await;
        let mut clipboard_png:Option<Vec<u8>>=None;
        for(index,mode)in ["visible","full"].iter().enumerate(){
            super::open(app).await?;tokio::time::sleep(Duration::from_millis(500)).await;
            let value=super::capture(app,mode,true).await?;
            if value["pasted"]!=true{return Err(format!("Release {mode} paste failed: {}",value["pasteError"]));}
            let expected=super::last()?;let mut actual:Option<Value>=None;
            for _ in 0..50{
                let text=screenshots::eval_value(&view,"JSON.stringify(window.__shotPasteEvents||[])").await?;
                let events:Value=serde_json::from_str(&text).map_err(err)?;
                if let Some(event)=events.as_array().and_then(|l|l.get(index)).filter(|e|e["dataUrl"].is_string()){actual=Some(event.clone());break;}
                tokio::time::sleep(Duration::from_millis(40)).await;
            }
            let event=actual.ok_or("No image reached the browser composer")?;
            if event["type"]!="image/png"||event["draft"]!="Bestaande concepttekst"||event["submits"]!=0{return Err("Paste changed draft or submitted a message".into());}
            let data=event["dataUrl"].as_str().ok_or("Missing received image")?;
            let data=STANDARD.decode(data.strip_prefix("data:image/png;base64,").ok_or("Received image is not PNG")?).map_err(err)?;
            let(a,b)=(tauri::image::Image::from_bytes(&expected).map_err(err)?,tauri::image::Image::from_bytes(&data).map_err(err)?);
            if a.width()!=b.width()||a.height()!=b.height()||a.rgba()!=b.rgba(){return Err("Received image differs from captured pixels".into());}
            if let Ok(dir)=std::env::var("VIBEZ_SCREENSHOT_ARTIFACT_DIR"){
                std::fs::create_dir_all(&dir).map_err(err)?;std::fs::write(std::path::Path::new(&dir).join(format!("pasted-{mode}.png")),&data).map_err(err)?;
            }
            // Closing intentionally clears the dialog's retained screenshot, not
            // the native clipboard. Retain test-owned bytes for the next probe.
            clipboard_png=Some(expected);
            super::action(app,"close").await?;println!("RELEASE_PASTE_OK: {mode}; visible attachment, pixels identical, draft preserved, no message sent");
        }
        view.set_focus().map_err(err)?;
        view.eval("document.getElementById('shot-composer').focus();").map_err(err)?;
        super::paste_composer::paste(app,clipboard_png.as_deref().ok_or("Missing clipboard probe fixture")?,true).await?;
        println!("NATIVE_CLIPBOARD_ATTACHMENT_OK: focused native paste produced a visible attachment");
        for behaviour in ["ignore","reject","delay"]{
            view.eval(format!("window.__shotPasteMode='{behaviour}';document.querySelectorAll('[role=alert]').forEach(e=>e.remove());")).map_err(err)?;
            super::open(app).await?;tokio::time::sleep(Duration::from_millis(300)).await;
            let result=super::capture(app,"visible",true).await?;
            if behaviour=="delay"{if result["pasted"]!=true{return Err("Delayed real attachment was not confirmed".into());}}
            else if result["pasted"]==true||!result["dataUrl"].is_string(){return Err(format!("False success or lost PNG when site {behaviour}s upload"));}
            super::action(app,"close").await?;println!("ATTACHMENT_ACK_OK: {behaviour}; no false success, PNG preserved");
        }
        view.eval("window.__shotPasteMode='normal';document.querySelectorAll('[role=alert]').forEach(e=>e.remove());document.getElementById('shot-composer').readOnly=true;").map_err(err)?;
        super::open(app).await?;tokio::time::sleep(Duration::from_millis(300)).await;
        let unavailable=super::capture(app,"visible",true).await?;
        if unavailable["pasted"]==true||!unavailable["dataUrl"].is_string(){return Err("Unavailable composer lost image or claimed false success".into());}
        super::action(app,"close").await?;println!("RELEASE_SCREENSHOT_OK: capture, attachment, ignored/rejected/delayed upload and recovery");Ok(())
    }.await;
    let restore=format!("(() => {{const old={old};document.body.innerHTML=old.html;document.body.style.cssText=old.style;document.head.querySelectorAll('meta[data-vibez-test-csp]').forEach(e=>e.remove());}})()");
    let _=view.eval(restore);result
}
