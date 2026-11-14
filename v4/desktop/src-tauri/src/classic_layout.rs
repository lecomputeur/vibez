//! Real GTK packing, rather than Tauri cached child bounds.
#[cfg(target_os="linux")]
use gtk::prelude::*;
use tauri::{AppHandle,Manager};
const TOOLBAR_HEIGHT:f64=54.;
const BOX_SURFACE:&str="vibez-classic-layout";
const SHELL:&str="vibez-toolbar";
const ROW:&str="vibez-content-row";
const CONTENT:&str="vibez-content";
#[cfg(target_os="linux")]
pub fn layout(app: &AppHandle) -> Result<(), String> {
    for (label, name) in [("main", SHELL), ("mistral-web", CONTENT), ("connector-panel", "vibez-local-files")] {
        let Some(view) = app.get_webview(label) else { continue };
        let visible = app.state::<crate::official_web::WebState>().panel.load(std::sync::atomic::Ordering::SeqCst);
        view.with_webview(move |platform| {
            let widget = platform.inner();
            let Some(window) = widget.toplevel().and_then(|w| w.downcast::<gtk::Window>().ok()) else { return };
            let Some(vbox) = window.child().and_then(|w| w.downcast::<gtk::Box>().ok()) else { return };
            let surface = vbox.children().into_iter().find_map(|w| {
                w.downcast::<gtk::Box>().ok().filter(|s| s.widget_name().as_str() == BOX_SURFACE)
            }).unwrap_or_else(|| {
                let s = gtk::Box::new(gtk::Orientation::Vertical, 0);
                s.set_widget_name(BOX_SURFACE);
                s.set_homogeneous(false);
                s.set_hexpand(true); s.set_vexpand(true);
                s.set_halign(gtk::Align::Fill); s.set_valign(gtk::Align::Fill);
                vbox.pack_start(&s, true, true, 0);
                s.show(); s
            });
            let row = surface.children().into_iter().find_map(|w| {
                w.downcast::<gtk::Box>().ok().filter(|s| s.widget_name().as_str() == ROW)
            }).unwrap_or_else(|| {
                let row = gtk::Box::new(gtk::Orientation::Horizontal, 0);
                row.set_widget_name(ROW); row.set_hexpand(true); row.set_vexpand(true);
                surface.pack_end(&row, true, true, 0); row.show(); row
            });
            let parent = if label == "main" { &surface } else { &row };
            let attached = widget.parent().and_then(|p| p.downcast::<gtk::Box>().ok()).is_some_and(|p| &p == parent);
            if !attached {
                if let Some(old) = widget.parent().and_then(|p| p.downcast::<gtk::Container>().ok()) { old.remove(&widget); }
                let content = label != "main";
                widget.set_widget_name(name);
                widget.set_hexpand(label == "mistral-web"); widget.set_vexpand(content);
                widget.set_halign(gtk::Align::Fill); widget.set_valign(gtk::Align::Fill);
                widget.set_size_request(if label == "connector-panel" { 400 } else { 1 }, if content { 1 } else { TOOLBAR_HEIGHT as i32 });
                
                parent.pack_start(&widget, label == "mistral-web", true, 0);
                parent.reorder_child(&widget, if label == "connector-panel" { -1 } else { 0 });
            }
            if label == "connector-panel" {
                // A child webview, never another application window.
                widget.set_visible(visible);
                widget.set_child_visible(visible);
            } else { widget.set_child_visible(true); widget.show(); }
            row.show();
            // Showing child containers never shows a hidden toplevel window.
            vbox.show(); surface.show();
        }).map_err(super::err)?;
    }
    Ok(())
}

// macOS contentView can extend behind the titlebar. Use AppKit's live
// unobscured contentLayoutRect, converted to each actual parent in points.
// This is the same safe-area approach already used by VibeZ 3's Mac shell.
#[cfg(target_os="macos")]
pub fn layout(app:&AppHandle)->Result<(),String> {
    use objc2_foundation::{NSRect,NSPoint,NSSize};
    let state=app.state::<crate::official_web::WebState>();
    let panel=state.panel.load(std::sync::atomic::Ordering::SeqCst);
    let visible=state.visible.load(std::sync::atomic::Ordering::SeqCst);
    for (index,label) in ["main","mistral-web","connector-panel"].into_iter().enumerate() {
        let Some(view)=app.get_webview(label) else {continue;};
        view.set_auto_resize(false).map_err(super::err)?;
        view.with_webview(move|platform|unsafe {
            let result:Result<(),String>=(||{
                let native=&*platform.inner().cast::<objc2_web_kit::WKWebView>();
                let window=native.window().ok_or("The Mac window is unavailable")?;
                let content=window.contentView().ok_or("The Mac content view is unavailable")?;
                let parent=native.superview().ok_or("The Mac webview parent is unavailable")?;
                let safe=content.convertRect_fromView(window.contentLayoutRect(),None);
                let (_,x,offset,width,height,show)=frames(safe.size.width,safe.size.height,panel,visible)[index];
                let y=if content.isFlipped(){safe.origin.y+offset}else{safe.origin.y+safe.size.height-offset-height};
                let desired=NSRect::new(NSPoint::new(safe.origin.x+x,y),NSSize::new(width,height));
                // Origin and size are applied atomically in the native parent,
                // without a fixed titlebar inset or physical/logical mixing.
                native.setFrame(content.convertRect_toView(desired,Some(&parent)));
                native.setHidden(!show);
                Ok(())
            })();
            if let Err(error)=result {eprintln!("Could not arrange VibeZ Mac views: {error}");}
        }).map_err(super::err)?;
    }
    Ok(())
}

#[cfg(target_os="windows")]
pub fn layout(app:&AppHandle)->Result<(),String> {desktop_layout(app)}

#[cfg(any(target_os="macos",test))]
fn frames(width:f64,height:f64,panel:bool,visible:bool)->[(&'static str,f64,f64,f64,f64,bool);3] {
    let width=width.max(1.);
    let content_height=(height-TOOLBAR_HEIGHT).max(1.);
    let panel_width=if panel {400_f64.min((width-320.).max(0.))} else {0.};
    [
        ("main",0.,0.,width,TOOLBAR_HEIGHT,true),
        ("mistral-web",0.,TOOLBAR_HEIGHT,(width-panel_width).max(1.),content_height,visible),
        ("connector-panel",width-panel_width,TOOLBAR_HEIGHT,panel_width.max(1.),content_height,panel),
    ]
}

// Windows retains its existing layout. Linux unit builds compile that API too.
#[cfg(any(target_os="windows",test))]
fn desktop_layout(app:&AppHandle)->Result<(),String> {
    use tauri::{LogicalPosition,LogicalSize};
    let window=app.get_window("main").ok_or("Het VibeZ-venster ontbreekt")?;
    let scale=window.scale_factor().map_err(super::err)?;
    let size=window.inner_size().map_err(super::err)?.to_logical::<f64>(scale);
    let panel=app.state::<crate::official_web::WebState>().panel.load(std::sync::atomic::Ordering::SeqCst);
    let panel_width=if panel {400_f64.min((size.width-320.).max(0.))} else {0.};
    let content_height=(size.height-TOOLBAR_HEIGHT).max(1.);
    for (label,x,y,width,height,show) in [
        ("main",0.,0.,size.width,TOOLBAR_HEIGHT,true),
        ("mistral-web",0.,TOOLBAR_HEIGHT,(size.width-panel_width).max(1.),content_height,
            app.state::<crate::official_web::WebState>().visible.load(std::sync::atomic::Ordering::SeqCst)),
        ("connector-panel",size.width-panel_width,TOOLBAR_HEIGHT,panel_width.max(1.),content_height,panel),
    ] {
        if let Some(view)=app.get_webview(label) {
            view.set_auto_resize(false).map_err(super::err)?;
            view.set_position(LogicalPosition::new(x,y)).map_err(super::err)?;
            view.set_size(LogicalSize::new(width.max(1.),height)).map_err(super::err)?;
            if show {view.show().map_err(super::err)?;} else {view.hide().map_err(super::err)?;}
        }
    }
    Ok(())
}

#[cfg(test)]mod layout_tests {
    use super::*;
    #[test]fn content_never_covers_the_toolbar_at_supported_sizes(){
        for(width,height)in [(760.,520.),(1280.,860.),(1693.,980.),(2560.,1440.)] {
            for panel in [false,true] {
                let f=frames(width,height,panel,true);
                assert_eq!(f[0].4,54.);
                assert_eq!(f[1].2,f[0].2+f[0].4);
                assert_eq!(f[2].2,f[1].2);
                assert_eq!(f[1].2+f[1].4,height);
                if panel {assert_eq!(f[1].1+f[1].3,f[2].1);assert_eq!(f[2].1+f[2].3,width);}
                else {assert_eq!(f[1].3,width);assert!(!f[2].5);}
            }
        }
    }
    #[test]fn a_hidden_web_surface_stays_hidden(){assert!(!frames(1280.,860.,true,false)[1].5);}
}
