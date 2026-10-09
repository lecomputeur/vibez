//! Independent AppKit geometry check; never adjusts production layout.
use tauri::{AppHandle,Manager};
use objc2_foundation::NSPoint;
use std::{sync::mpsc,time::Duration};
use crate::{err,policy::TOOLBAR_HEIGHT};
pub fn check(app:&AppHandle)->Result<(),String>{
    for label in ["shell","vibe"] {
        let view=app.get_webview(label).ok_or("Missing native view")?;
        let(tx,rx)=mpsc::channel();
        view.with_webview(move|platform|unsafe{
            let result:Result<(),String>=(||{
                let native=&*platform.inner().cast::<objc2_web_kit::WKWebView>();
                let window=native.window().ok_or("Missing NSWindow")?;
                let content=window.contentView().ok_or("Missing content view")?;
                let rect=native.convertRect_toView(native.bounds(),Some(&content));
                let bounds=content.bounds();
                let usable=content.convertRect_fromView(window.contentLayoutRect(),None);
                let inset=if content.isFlipped(){usable.origin.y-bounds.origin.y}else{bounds.origin.y+bounds.size.height-usable.origin.y-usable.size.height};
                let top=if content.isFlipped(){rect.origin.y-bounds.origin.y}else{bounds.origin.y+bounds.size.height-rect.origin.y-rect.size.height};
                let area=window.contentLayoutRect();
                let parent=native.superview().ok_or("Missing superview")?;
                println!("MAC_NATIVE_GEOMETRY: {label}; top={top}, frame={rect:?}, content={bounds:?}, layout={area:?}, parent={:?}, flipped={}",parent.bounds(),parent.isFlipped());
                if label=="shell"{
                    // Check the actual responder at the bottom of the toolbar,
                    // not the same wrapper's setter/getter round trip.
                    let y=if content.isFlipped(){usable.origin.y+TOOLBAR_HEIGHT-3.}else{usable.origin.y+usable.size.height-TOOLBAR_HEIGHT+3.};
                    let point=content.convertPoint_toView(NSPoint::new(bounds.origin.x+40.,y),content.superview().as_deref());
                    let hit=content.hitTest(point);
                    if !hit.is_some_and(|v|v.isDescendantOf(native)){return Err("Mac toolbar is occluded in actual native hit testing".into());}
                }
                if (top-inset-if label=="shell"{0.}else{TOOLBAR_HEIGHT}).abs()>2.{return Err(format!("Mac actual view position differs from intended {label}: {top}"));}
                let expected_height=if label=="shell"{TOOLBAR_HEIGHT}else{usable.size.height-TOOLBAR_HEIGHT};
                if (rect.size.height-expected_height).abs()>2.||(rect.size.width-usable.size.width).abs()>2.{return Err("Mac views do not fill the usable content area".into());}
                println!("MAC_SAFE_AREA_OK: {label}; titlebar inset={inset}, usable={}x{}, visible height={}",usable.size.width,usable.size.height,rect.size.height);
                Ok(())
            })();
            let _=tx.send(result);
        }).map_err(err)?;
        rx.recv_timeout(Duration::from_secs(5)).map_err(err)??;
    }
    println!("MAC_NATIVE_LAYOUT_OK: independent AppKit frames and toolbar hit-test");Ok(())
}
