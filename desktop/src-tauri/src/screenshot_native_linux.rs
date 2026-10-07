//! Capture actual rendered WebKit pixels; never re-fetch or rasterize website assets.
use super::*;
use gtk::gio::prelude::*;
use webkit2gtk::WebViewExt;

#[derive(Clone,Copy,serde::Deserialize)]
struct Rect { #[serde(default)] x:f64, #[serde(default)] y:f64, width:f64, height:f64 }
impl Rect {
    fn valid(self)->Result<Self,String> {
        if [self.x,self.y,self.width,self.height].iter().any(|v| !v.is_finite()) || self.x<0. || self.y<0.
            || self.width<1. || self.height<1. || self.width>32760. || self.height>32760.
            || self.width*self.height>36_000_000. { return Err("Invalid or oversized screenshot area".into()); }
        Ok(self)
    }
}
pub async fn snapshot(view:&Webview,mode:&str,payload:&Value)->Result<Vec<u8>,String> {
    let rect:Rect=serde_json::from_value(payload["rect"].clone()).map_err(err)?;
    let rect=rect.valid()?;
    let full=mode=="full";
    let source:Rect=serde_json::from_value(if full {payload["geometry"].clone()} else {payload["viewport"].clone()}).map_err(err)?;
    let source=source.valid()?;
    if rect.x+rect.width>source.width+1. || rect.y+rect.height>source.height+1. { return Err("Selection is outside the page".into()); }
    let cancellable=gtk::gio::Cancellable::new();
    let token=cancellable.clone();
    let (tx,rx)=tokio::sync::oneshot::channel();
    view.with_webview(move |platform| {
        platform.inner().snapshot(
            if full {webkit2gtk::SnapshotRegion::FullDocument} else {webkit2gtk::SnapshotRegion::Visible},
            webkit2gtk::SnapshotOptions::empty(),Some(&token),move |result| {
                let answer:Result<Vec<u8>,String>=(|| {
                    let surface=result.map_err(err)?;
                    let image=gtk::cairo::ImageSurface::try_from(surface.clone()).map_err(|_|"WebKit returned an unsupported surface")?;
                    let (sw,sh)=(image.width(),image.height());
                    if sw<1 || sh<1 || sw>32760 || sh>32760 || i64::from(sw)*i64::from(sh)>36_000_000 {
                        return Err("Page is too large. Use visible page or selection.".into());
                    }
                    // Snapshot surfaces include display scale and browser zoom. Map
                    // CSS coordinates through the measured surface, not a guessed DPR.
                    let sx=f64::from(sw)/source.width; let sy=f64::from(sh)/source.height;
                    let x=(rect.x*sx).floor() as i32;let y=(rect.y*sy).floor() as i32;
                    let right=((rect.x+rect.width)*sx).ceil().min(f64::from(sw)) as i32;
                    let bottom=((rect.y+rect.height)*sy).ceil().min(f64::from(sh)) as i32;
                    if right<=x||bottom<=y {return Err("Empty screenshot selection".into());}
                    let pixels=gtk::gdk::pixbuf_get_from_surface(&surface,x,y,right-x,bottom-y).ok_or("Cannot read rendered screenshot")?;
                    let (w,h)=(rect.width.round() as i32,rect.height.round() as i32);
                    let pixels=if pixels.width()==w&&pixels.height()==h {pixels} else {
                        pixels.scale_simple(w,h,gtk::gdk_pixbuf::InterpType::Bilinear).ok_or("Cannot scale screenshot")?
                    };
                    let bytes=pixels.save_to_bufferv("png",&[]).map_err(err)?;
                    if bytes.len()>24*1024*1024 {return Err("Screenshot PNG is too large".into());}
                    Ok(bytes)
                })();
                let _=tx.send(answer);
            });
    }).map_err(err)?;
    match tokio::time::timeout(Duration::from_secs(15),rx).await {
        Ok(result)=>result.map_err(err)?,
        Err(_)=>{cancellable.cancel();Err("WebKit screenshot timed out; try a smaller area".into())}
    }
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn rejects_bad_geometry() {
        for width in [0.,-1.,f64::NAN,f64::INFINITY,40000.] {
            assert!(Rect{x:0.,y:0.,width,height:100.}.valid().is_err());
        }
        assert!(Rect{x:0.,y:0.,width:120.,height:100.}.valid().is_ok());
    }
}
