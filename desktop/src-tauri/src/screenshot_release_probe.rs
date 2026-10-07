//! Frozen-source release checks: actual native capture -> actual browser paste receipt.
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
        view.eval(include_str!("screenshot_fixture.js")).map_err(err)?;
        tokio::time::sleep(Duration::from_millis(300)).await;
        for (index,mode) in ["visible","full"].iter().enumerate(){
            super::open(app).await?;
            // Includes local-UI initialization, same capture/paste command path as the button.
            tokio::time::sleep(Duration::from_millis(500)).await;
            let value=super::capture(app,mode,true).await?;
            if value["pasted"]!=true{return Err(format!("Release {mode} paste failed: {}",value["pasteError"]));}
            let expected=super::last()?;
            let mut actual:Option<Value>=None;
            for _ in 0..50{
                let text=screenshots::eval_value(&view,"JSON.stringify(window.__shotPasteEvents||[])").await?;
                let events:Value=serde_json::from_str(&text).map_err(err)?;
                if let Some(event)=events.as_array().and_then(|list|list.get(index)).filter(|e|e["dataUrl"].is_string()){actual=Some(event.clone());break;}
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
            super::action(app,"close").await?;
            println!("RELEASE_PASTE_OK: {mode}; actual PNG received, pixels identical, draft preserved, no message sent");
        }
        view.eval("document.getElementById('shot-composer').readOnly=true;").map_err(err)?;
        super::open(app).await?;tokio::time::sleep(Duration::from_millis(300)).await;
        let unavailable=super::capture(app,"visible",true).await?;
        if unavailable["pasted"]==true||!unavailable["dataUrl"].is_string(){return Err("Unavailable composer lost image or claimed false success".into());}
        super::action(app,"close").await?;
        println!("RELEASE_SCREENSHOT_OK: compact chooser, capture/paste and unavailable-composer recovery");Ok(())
    }.await;
    // Remove only this offline fixture's extra CSP; restore the prior test page.
    let restore=format!("(() => {{const old={old};document.body.innerHTML=old.html;document.body.style.cssText=old.style;document.head.querySelectorAll('meta[data-vibez-test-csp]').forEach(e=>e.remove());}})()");
    let _=view.eval(restore);result
}
