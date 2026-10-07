//! Native page pixels on Windows and macOS. No DOM-to-image asset fetching.
use crate::err;
use serde_json::{json,Value};
use std::{sync::{Arc,Mutex},time::Duration};
use tauri::Webview;

fn number(value:&Value,key:&str)->Result<f64,String>{
    let n=value[key].as_f64().ok_or("Missing screenshot geometry")?;
    if !n.is_finite()||n<0.||n>32760.{return Err("Invalid screenshot geometry".into());}Ok(n)
}
fn geometry(payload:&Value)->Result<(f64,f64,u32,u32),String>{
    let r=&payload["rect"];let(x,y,w,h)=(number(r,"x")?,number(r,"y")?,number(r,"width")?,number(r,"height")?);
    if w<1.||h<1.||w*h>36_000_000.{return Err("Screenshot is too large".into());}
    Ok((x,y,w.round() as u32,h.round() as u32))
}
fn normalize(bytes:&[u8],w:u32,h:u32)->Result<Vec<u8>,String>{
    if bytes.len()<33||bytes.len()>26*1024*1024||&bytes[..8]!=b"\x89PNG\r\n\x1a\n"{return Err("Invalid native PNG".into());}
    let sw=u32::from_be_bytes(bytes[16..20].try_into().map_err(err)?);let sh=u32::from_be_bytes(bytes[20..24].try_into().map_err(err)?);
    if sw==0||sh==0||sw>32760||sh>32760||u64::from(sw)*u64::from(sh)>36_000_000{return Err("Native screenshot exceeds pixel limit".into());}
    if sw==w&&sh==h{return Ok(bytes.to_vec());}
    let image=image::load_from_memory_with_format(bytes,image::ImageFormat::Png).map_err(err)?;
    let mut out=std::io::Cursor::new(Vec::new());
    image.resize_exact(w,h,image::imageops::FilterType::Triangle).write_to(&mut out,image::ImageFormat::Png).map_err(err)?;
    Ok(out.into_inner())
}
#[cfg(target_os="windows")]
pub async fn devtools(view:&Webview,method:&str,args:Value)->Result<Value,String>{
    use windows::core::HSTRING;
    use webview2_com::CallDevToolsProtocolMethodCompletedHandler;
    let method=method.to_owned();let args=args.to_string();
    let(tx,rx)=tokio::sync::oneshot::channel();let tx=Arc::new(Mutex::new(Some(tx)));
    view.with_webview(move |p|{
        let answer=tx.clone();
        let result:Result<(),String>=(||unsafe{
            let v=p.controller().CoreWebView2().map_err(err)?;
            let handler=CallDevToolsProtocolMethodCompletedHandler::create(Box::new(move |result,text|{
                let value=result.map_err(err).and_then(|_|serde_json::from_str(&text).map_err(err));
                if let Ok(mut slot)=answer.lock(){if let Some(tx)=slot.take(){let _=tx.send(value);}}Ok(())
            }));
            v.CallDevToolsProtocolMethod(&HSTRING::from(method),&HSTRING::from(args),&handler).map_err(err)
        })();
        if let Err(error)=result{if let Ok(mut slot)=tx.lock(){if let Some(tx)=slot.take(){let _=tx.send(Err(error));}}}
    }).map_err(err)?;
    tokio::time::timeout(Duration::from_secs(20),rx).await.map_err(err)?.map_err(err)?
}
#[cfg(target_os="windows")]
pub async fn snapshot(view:&Webview,_mode:&str,payload:&Value)->Result<Vec<u8>,String>{
    use base64::{engine::general_purpose::STANDARD,Engine as _};
    let(x,y,w,h)=geometry(payload)?;
    let sx=payload["scroll"]["x"].as_f64().unwrap_or(0.);let sy=payload["scroll"]["y"].as_f64().unwrap_or(0.);
    if !sx.is_finite()||!sy.is_finite(){return Err("Invalid page scroll offset".into());}
    let result=devtools(view,"Page.captureScreenshot",json!({"format":"png","fromSurface":true,"captureBeyondViewport":true,
        "clip":{"x":x+sx,"y":y+sy,"width":w,"height":h,"scale":1}})).await?;
    let encoded=result["data"].as_str().ok_or("WebView2 returned no PNG")?;
    if encoded.len()>34*1024*1024{return Err("Screenshot exceeds size limit".into());}
    normalize(&STANDARD.decode(encoded).map_err(err)?,w,h)
}
#[cfg(target_os="macos")]
pub async fn snapshot(view:&Webview,_mode:&str,payload:&Value)->Result<Vec<u8>,String>{
    use objc2::AnyThread;
    use objc2_app_kit::{NSImage,NSBitmapImageRep,NSBitmapImageFileType};
    use objc2_foundation::{NSError,NSDictionary,NSNumber,NSRect,NSPoint,NSSize};
    use objc2_web_kit::{WKWebView,WKSnapshotConfiguration};
    let(x,y,w,h)=geometry(payload)?;
    let viewport=number(&payload["viewport"],"width")?;
    if viewport<1.{return Err("The page has no viewport".into());}
    let(tx,rx)=tokio::sync::oneshot::channel();let tx=Arc::new(Mutex::new(Some(tx)));
    view.with_webview(move |p|unsafe{
        let v=&*p.inner().cast::<WKWebView>();let scale=v.bounds().size.width/viewport;
        let Some(mtm)=objc2::MainThreadMarker::new() else {
            if let Ok(mut slot)=tx.lock(){if let Some(tx)=slot.take(){let _=tx.send(Err("Snapshot requires main thread".into()));}}
            return;
        };
        let config=WKSnapshotConfiguration::new(mtm);
        config.setRect(NSRect::new(NSPoint::new(x*scale,y*scale),NSSize::new(f64::from(w)*scale,f64::from(h)*scale)));
        config.setSnapshotWidth(Some(&NSNumber::new_f64(f64::from(w))));
        config.setAfterScreenUpdates(false);
        let callback=block2::RcBlock::new(move |image:*mut NSImage,error:*mut NSError|{
            let result:Result<Vec<u8>,String>=(||{
                if !error.is_null(){return Err((&*error).localizedDescription().to_string());}
                let image=image.as_ref().ok_or("WKWebView returned no image")?;
                let data=image.TIFFRepresentation().ok_or("Cannot read WKWebView image")?;
                let rep=NSBitmapImageRep::initWithData(NSBitmapImageRep::alloc(),&data).ok_or("Cannot decode WKWebView image")?;
                let png=rep.representationUsingType_properties(NSBitmapImageFileType::PNG,&NSDictionary::new()).ok_or("Cannot encode WKWebView PNG")?;
                let len:usize=objc2::msg_send![&*png,length];
                if len>26*1024*1024{return Err("Screenshot exceeds size limit".into());}
                let ptr:*const u8=objc2::msg_send![&*png,bytes];
                if ptr.is_null(){return Err("Empty WKWebView image".into());}
                normalize(std::slice::from_raw_parts(ptr,len),w,h)
            })();
            if let Ok(mut slot)=tx.lock(){if let Some(tx)=slot.take(){let _=tx.send(result);}}
        });
        v.takeSnapshotWithConfiguration_completionHandler(Some(&config),&callback);
    }).map_err(err)?;
    tokio::time::timeout(Duration::from_secs(20),rx).await.map_err(err)?.map_err(err)?
}
#[cfg(test)] mod tests{
    use super::*;
    #[test] fn rejects_oversized_geometry(){assert!(geometry(&json!({"rect":{"x":0,"y":0,"width":32760,"height":32760}})).is_err());}
    #[test] fn rejects_non_png_before_image_decode(){assert!(normalize(b"not a PNG",120,100).is_err());}
}
