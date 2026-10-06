//! Offline screenshot probes validate actual pixels, crop dimensions and clipboard.
use super::*;
fn contains_colour(image:&tauri::image::Image<'_>, colour:[u8;3])->usize {
    image.rgba().chunks_exact(4).filter(|p| p[3]>240 && (0..3).all(|i| (p[i] as i16-colour[i] as i16).abs()<8)).count()
}
pub async fn run(app:&AppHandle)->Result<(),String> {
    if !app.state::<PreviewState>().smoke { return Err("Screenshot probe requires smoke mode".into()); }
    let view=app.get_webview("vibe").ok_or("Missing Vibe view")?;
    // Synthetic content only. These artifacts contain no account data.
    if let Ok(dir)=std::env::var("VIBEZ_SCREENSHOT_ARTIFACT_DIR") {
        std::fs::create_dir_all(&dir).map_err(err)?;
        std::fs::write(std::path::Path::new(&dir).join("capture-engine.js"),SNAPDOM).map_err(err)?;
    }
    let setup=eval_value(&view,r#"(() => {
      window.__shotOriginal={html:document.body.innerHTML,style:document.body.getAttribute('style')};
      document.body.style.margin='0';
      document.body.innerHTML='<div id="shot-host" data-shot-style="position:fixed;inset:0;display:flex;overflow:hidden"><aside data-shot-style="width:80px;flex-shrink:0;background:rgb(0,200,180)">Sidebar</aside><main id="shot-scroll" data-shot-style="height:100%;flex:1;overflow-y:auto;padding:0;max-width:none"><div data-shot-style="height:1500px;position:relative;background:white"><div data-shot-style="position:absolute;left:24px;top:24px;width:120px;height:100px;background:rgb(230,30,40)"></div><p data-shot-style="position:absolute;top:250px">Screenshot fixture</p><div data-shot-style="position:absolute;left:24px;top:1200px;width:120px;height:100px;background:rgb(30,60,230)"></div></div></main></div>';
      // Keep the strict page CSP intact. CSSOM assignments, unlike parsed
      // inline style attributes, are permitted in the trusted offline probe.
      for(const el of document.querySelectorAll('[data-shot-style]')) {
        el.style.cssText=el.getAttribute('data-shot-style'); el.removeAttribute('data-shot-style');
      }
      const host=document.getElementById('shot-host'), scroller=document.getElementById('shot-scroll');
      return JSON.stringify({viewportWidth:innerWidth,viewportHeight:innerHeight,width:host.getBoundingClientRect().width,height:host.getBoundingClientRect().height,client:scroller.clientHeight,scroll:scroller.scrollHeight});
    })()"#).await?;
    let setup:Value=serde_json::from_str(&setup).map_err(err)?;
    if (setup["width"].as_f64().unwrap_or(0.)-setup["viewportWidth"].as_f64().unwrap_or(-999.)).abs()>2.
        || (setup["height"].as_f64().unwrap_or(0.)-setup["viewportHeight"].as_f64().unwrap_or(-999.)).abs()>2.
        || setup["scroll"].as_u64().unwrap_or(0)<1500
        || setup["client"].as_u64().unwrap_or(u64::MAX)>=setup["scroll"].as_u64().unwrap_or(0) {
        return Err(format!("Screenshot fixture did not create a real scrollable viewport: {setup}"));
    }
    println!("SCREENSHOT_FIXTURE_OK: strict CSP retained; {setup}");
    tokio::time::sleep(Duration::from_millis(150)).await;
    let before=eval_value(&view,"JSON.stringify([document.getElementById('shot-host').style.cssText,document.getElementById('shot-scroll').style.cssText,document.getElementById('shot-scroll').scrollTop])").await?;
    let size:Value=serde_json::from_str(&eval_value(&view,"JSON.stringify([innerWidth,innerHeight])").await?).map_err(err)?;
    let result:Result<(),String>=async {
        for mode in ["visible","full","selection"] {
            let id=begin(&view,mode,"Drag to select").await?;
            if mode=="selection" {
                for _ in 0..40 {
                    if eval_value(&view,"Boolean(document.getElementById('vibez-screenshot-selection-overlay'))").await?=="true" {break;}
                    tokio::time::sleep(Duration::from_millis(50)).await;
                }
                view.eval(r#"(() => { const o=document.getElementById('vibez-screenshot-selection-overlay'); if(!o)throw new Error('No selection overlay');
                  for(const [type,x,y] of [['pointerdown',224,124],['pointermove',104,24],['pointerup',104,24]])o.dispatchEvent(new PointerEvent(type,{bubbles:true,button:0,clientX:x,clientY:y,pointerId:1}));
                })()"#).map_err(err)?;
            }
            let payload=wait_result(&view,mode,id).await?;
            if payload["status"]!="ok" {return Err(format!("Screenshot {mode}: {}",payload["message"]));}
            let bytes=png_bytes(payload["dataUrl"].as_str().ok_or("Missing probe PNG")?)?;
            let image=tauri::image::Image::from_bytes(&bytes).map_err(err)?;
            let (w,h)=(image.width(),image.height());
            println!("SCREENSHOT_GEOMETRY: {mode} {w}x{h}; expanded={}, capture={}",payload["geometry"],payload["meta"]);
            if let Ok(dir)=std::env::var("VIBEZ_SCREENSHOT_ARTIFACT_DIR") {
                std::fs::create_dir_all(&dir).map_err(err)?;
                std::fs::write(std::path::Path::new(&dir).join(format!("{mode}.png")),&bytes).map_err(err)?;
            }
            if mode=="visible" && (w!=size[0].as_u64().unwrap_or(0) as u32 || h!=size[1].as_u64().unwrap_or(0) as u32) {return Err(format!("Visible crop wrong: {w}x{h}, viewport={size}"));}
            if mode=="selection" && (w!=120||h!=100) {return Err(format!("Selection crop wrong: {w}x{h}"));}
            let red=contains_colour(&image,[230,30,40]);
            let blue=contains_colour(&image,[30,60,230]);
            if red<5000 {return Err(format!("{mode} missing visible red pixels: {red}"));}
            if mode=="full" && (blue<5000||h<1500||contains_colour(&image,[0,200,180])<5000) {return Err(format!("Full page lost bottom or sidebar: {w}x{h}, bottom={blue}"));}
            if mode!="full" && blue>100 {return Err("Offscreen content leaked into visible/selection screenshot".into());}
            let after=eval_value(&view,"JSON.stringify([document.getElementById('shot-host').style.cssText,document.getElementById('shot-scroll').style.cssText,document.getElementById('shot-scroll').scrollTop])").await?;
            if before!=after {return Err("Screenshot left the page layout or scroll position modified".into());}
            copy_png(app,&bytes)?;
            let clipboard=app.clipboard().read_image().map_err(err)?;
            if clipboard.width()!=w||clipboard.height()!=h {return Err("Clipboard PNG dimensions changed".into());}
            println!("SCREENSHOT_MODE_OK: {mode} {w}x{h}; pixels, page restoration and clipboard verified");
        }
        let id=begin(&view,"selection","Cancel probe").await?;
        tokio::time::sleep(Duration::from_millis(200)).await;
        view.eval("window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));").map_err(err)?;
        if wait_result(&view,"selection",id).await?["status"]!="cancelled" {return Err("Escape did not cancel screenshot".into());}
        if eval_value(&view,"Boolean(document.getElementById('vibez-screenshot-selection-overlay'))").await?!="false" {return Err("Cancelled capture left an overlay".into());}
        println!("SCREENSHOT_OK: all page capture modes, real PNG pixels, clipboard and Escape cancellation verified");
        Ok(())
    }.await;
    let _=view.eval("if(window.__shotOriginal){document.body.innerHTML=window.__shotOriginal.html;const s=window.__shotOriginal.style;if(s===null)document.body.removeAttribute('style');else document.body.style.cssText=s;delete window.__shotOriginal;}");
    result
}
