//! Offline, native-engine guest -> signed-in UI transition. Never signs in.
use tauri::{AppHandle,Manager};
use std::time::Duration;
use crate::{err,screenshots};
pub async fn run(app:&AppHandle)->Result<(),String>{
    if !app.state::<crate::PreviewState>().smoke{return Err("Guest probe requires offline mode".into());}
    #[cfg(target_os="macos")] {
        let handle=app.clone();
        tauri::async_runtime::spawn_blocking(move||super::macos_layout_probe::check(&handle)).await.map_err(err)??;
    }
    let view=app.get_webview("vibe").ok_or("Missing fixture webview")?;
    let old=screenshots::eval_value(&view,"JSON.stringify({html:document.body.innerHTML,style:document.body.style.cssText})").await?;
    view.eval(include_str!("screenshot_fixture.js")).map_err(err)?;
    tokio::time::sleep(Duration::from_millis(300)).await;
    let result=check(app).await;
    let _=view.eval(format!("(()=>{{const old={old};document.body.innerHTML=old.html;document.body.style.cssText=old.style;document.head.querySelectorAll('meta[data-vibez-test-csp]').forEach(e=>e.remove());}})()"));
    result
}
async fn check(app:&AppHandle)->Result<(),String>{
    let view=app.get_webview("vibe").ok_or("Missing fixture webview")?;
    for (labels,expected) in [("['Sign in','Sign up']",true),("['Account']",false),("['Inloggen','Aanmelden']",true),("[]",false)]{
        view.eval(format!("(()=>{{document.getElementById('guest-header')?.remove();const h=document.createElement('header');h.id='guest-header';h.style.cssText='position:fixed;top:4px;left:200px;height:40px;z-index:50;display:flex;gap:8px';for(const label of {labels}){{const b=document.createElement('button');b.textContent=label;h.append(b);}}document.body.append(h);}})()")).map_err(err)?;
        tokio::time::sleep(Duration::from_millis(150)).await;
        super::open(app).await?;
        let chooser=app.get_webview("screenshot").ok_or("No chooser")?;
        let mut seen=false;
        for _ in 0..40{
            tokio::time::sleep(Duration::from_millis(100)).await;
            let raw=match screenshots::eval_value(&chooser,"JSON.stringify({ready:!document.querySelector('[data-mode=visible]')?.disabled,shown:document.getElementById('login-hint')?.hidden===false,text:document.getElementById('login-hint')?.textContent})").await{Ok(v)=>v,Err(_)=>continue};
            let v:serde_json::Value=serde_json::from_str(&raw).map_err(err)?;
            if v["ready"]==true&&v["shown"]==expected&&v["text"].as_str().is_some_and(|s|s.contains("PNG")){seen=true;break;}
        }
        if !seen{return Err(format!("Guest note incorrect before capture for {labels}"));}
        if screenshots::eval_value(&view,"String(window.__shotPasteEvents.length)").await?!="0"{return Err("Guest note caused a paste".into());}
        println!("GUEST_NOTICE_OK: {labels}; shown={expected}, before capture, no paste");
        // Leave it open for the next state: disappearance after login is tested
        // by the production one-second refresh, not by recreating its HTML.
    }
    super::action(app,"close").await?;
    view.eval("document.getElementById('guest-header')?.remove();").map_err(err)?;Ok(())
}
