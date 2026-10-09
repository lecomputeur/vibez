//! macOS contentView may extend BEHIND the title bar. Place both child
//! webviews inside AppKit's actual unobscured contentLayoutRect in points.
use tauri::{AppHandle,Manager};
use objc2_foundation::{NSRect,NSPoint,NSSize};
use crate::{err,policy::TOOLBAR_HEIGHT};
pub fn layout(app:&AppHandle)->Result<(),String>{
    for label in ["shell","vibe"] {
        let Some(view)=app.get_webview(label) else{continue;};
        let handle=app.clone();
        view.with_webview(move|platform|unsafe{
            let result:Result<(),String>=(||{
                let native=&*platform.inner().cast::<objc2_web_kit::WKWebView>();
                let window=native.window().ok_or("Missing Mac window")?;
                let content=window.contentView().ok_or("Missing Mac content view")?;
                let parent=native.superview().ok_or("Missing Mac webview parent")?;
                // contentLayoutRect is in window coordinates. Do not subtract
                // a fixed titlebar value, mix physical pixels, or use frame as bounds.
                let safe=content.convertRect_fromView(window.contentLayoutRect(),None);
                let bar=TOOLBAR_HEIGHT.min(safe.size.height.max(0.));
                let (offset,height)=if label=="shell"{(0.,bar)}else{(bar,(safe.size.height-bar).max(1.))};
                let y=if content.isFlipped(){safe.origin.y+offset}else{safe.origin.y+safe.size.height-offset-height};
                let desired=NSRect::new(NSPoint::new(safe.origin.x,y),NSSize::new(safe.size.width.max(1.),height));
                let frame=content.convertRect_toView(desired,Some(&parent));
                native.setFrame(frame);
                Ok(())
            })();
            if let Err(e)=result{crate::message(&handle,format!("macOS layout: {e}"));}
        }).map_err(err)?;
    }
    Ok(())
}
/// Read-only geometry for offline assertions, called from their worker thread.
/// Returns the safe area in the same top-left point coordinates as Wry bounds.
pub fn safe_area(app:&AppHandle)->Result<(f64,f64,f64,f64),String>{
    use std::{sync::mpsc,time::Duration};
    let view=app.get_webview("shell").ok_or("Missing Mac shell")?;
    let(tx,rx)=mpsc::channel();
    view.with_webview(move|platform|unsafe{
        let result:Result<_,String>=(||{
            let native=&*platform.inner().cast::<objc2_web_kit::WKWebView>();
            let window=native.window().ok_or("Missing Mac window")?;
            let parent=native.superview().ok_or("Missing Mac parent")?;
            let safe=parent.convertRect_fromView(window.contentLayoutRect(),None);
            let bounds=parent.bounds();
            let top=if parent.isFlipped(){safe.origin.y-bounds.origin.y}else{bounds.origin.y+bounds.size.height-safe.origin.y-safe.size.height};
            Ok((safe.origin.x-bounds.origin.x,top,safe.size.width,safe.size.height))
        })();let _=tx.send(result);
    }).map_err(err)?;
    rx.recv_timeout(Duration::from_secs(5)).map_err(err)?
}
