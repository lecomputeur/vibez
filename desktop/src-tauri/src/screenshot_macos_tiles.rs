//! WKWebView snapshots only render its viewport. Stitch native viewport pixels
//! after scrolling the already-expanded loaded document, then restore scroll.
use super::{geometry,number,snapshot_region};
use crate::err;
use serde_json::{json,Value};
use std::time::{Duration,Instant};
use tauri::Webview;

pub async fn capture(view:&Webview,payload:&Value)->Result<Vec<u8>,String>{
    let(_,_,width,height)=geometry(payload)?;
    let vw=number(&payload["viewport"],"width")?.round() as u32;
    let vh=number(&payload["viewport"],"height")?.round() as u32;
    if vw<64||vh<64{return Err("The page is still resizing".into());}
    if width.div_ceil(vw)*height.div_ceil(vh)>256{return Err("Page is too large; use visible page or selection".into());}
    let initial=super::super::eval_value(view,"JSON.stringify([scrollX,scrollY])").await?;
    let initial:Value=serde_json::from_str(&initial).map_err(err)?;
    let start=Instant::now();
    let result:Result<Vec<u8>,String>=async{
        let mut assembled=image::RgbaImage::new(width,height);
        for y in (0..height).step_by(vh as usize){
            for x in (0..width).step_by(vw as usize){
                if start.elapsed()>Duration::from_secs(25){return Err("Full-page screenshot timed out; use a smaller area".into());}
                let script=format!("(() => {{window.__vibezTileReady=false;scrollTo({x},{y});requestAnimationFrame(()=>requestAnimationFrame(()=>{{window.__vibezTileReady=true;}}));return true;}})()");
                super::super::eval_value(view,script).await?;
                let mut ready=false;
                for _ in 0..50{
                    tokio::time::sleep(Duration::from_millis(40)).await;
                    if super::super::eval_value(view,"window.__vibezTileReady===true").await?=="true"{ready=true;break;}
                }
                if !ready{return Err("The page did not finish painting".into());}
                let measured=super::super::eval_value(view,"JSON.stringify({x:scrollX,y:scrollY,width:innerWidth,height:innerHeight})").await?;
                let measured:Value=serde_json::from_str(&measured).map_err(err)?;
                if number(&measured,"width")?.round() as u32!=vw||number(&measured,"height")?.round() as u32!=vh{
                    return Err("The page resized during capture; try again".into());
                }
                let sx=number(&measured,"x")?;let sy=number(&measured,"y")?;
                let ox=f64::from(x)-sx;let oy=f64::from(y)-sy;
                let cw=(width-x).min(vw);let ch=(height-y).min(vh);
                if ox< -0.5||oy< -0.5||ox+f64::from(cw)>f64::from(vw)+0.5||oy+f64::from(ch)>f64::from(vh)+0.5{
                    return Err("The full page could not be scrolled into view".into());
                }
                let tile_payload=json!({"rect":{"x":0,"y":0,"width":vw,"height":vh},"viewport":{"width":vw,"height":vh}});
                let png=snapshot_region(view,"visible",&tile_payload).await?;
                let tile=image::load_from_memory_with_format(&png,image::ImageFormat::Png).map_err(err)?.to_rgba8();
                let crop=image::imageops::crop_imm(&tile,ox.max(0.).round() as u32,oy.max(0.).round() as u32,cw,ch).to_image();
                image::imageops::replace(&mut assembled,&crop,i64::from(x),i64::from(y));
            }
        }
        let mut output=std::io::Cursor::new(Vec::new());
        image::DynamicImage::ImageRgba8(assembled).write_to(&mut output,image::ImageFormat::Png).map_err(err)?;
        let bytes=output.into_inner();
        if bytes.len()>24*1024*1024{return Err("Screenshot exceeds PNG size limit".into());}
        Ok(bytes)
    }.await;
    let x=initial[0].as_f64().unwrap_or(0.);let y=initial[1].as_f64().unwrap_or(0.);
    let cleanup=super::super::eval_value(view,format!("delete window.__vibezTileReady;scrollTo({x},{y});true")).await;
    match(result,cleanup){(Ok(value),Ok(_))=>Ok(value),(Err(error),_)=>Err(error),(_,Err(error))=>Err(error)}
}
