//! GTK Layout isolates child requisitions from the toplevel minimum size.
//! Its virtual canvas follows the allocation; resizing never shows the window.
use crate::policy::TOOLBAR_HEIGHT;
use gtk::prelude::*;
use tauri::{AppHandle, Manager};
const SURFACE: &str = "vibez-tauri-layout";
const SHELL: &str = "vibez-toolbar";
const CONTENT: &str = "vibez-content";
fn allocate(surface: &gtk::Layout, width: i32, height: i32) {
    let width = width.max(1);
    let height = height.max(1);
    let toolbar = (TOOLBAR_HEIGHT as i32).min(height);
    // Virtual extents are not a minimum size request on the parent.
    if surface.size() != (width as u32, height as u32) { surface.set_size(width as u32, height as u32); }
    for widget in surface.children() {
        let (y, h) = match widget.widget_name().as_str() {
            SHELL => (0, toolbar), CONTENT => (toolbar, (height - toolbar).max(1)), _ => continue,
        };
        surface.move_(&widget, 0, y);
        if widget.size_request() != (width, h) { widget.set_size_request(width, h); }
    }
}
pub fn layout(app: &AppHandle) -> Result<(), String> {
    for (label, name) in [("shell", SHELL), ("vibe", CONTENT)] {
        let Some(view) = app.get_webview(label) else { continue };
        view.with_webview(move |platform| {
            let widget = platform.inner();
            let Some(window) = widget.toplevel().and_then(|w| w.downcast::<gtk::Window>().ok()) else { return };
            let Some(vbox) = window.child().and_then(|w| w.downcast::<gtk::Box>().ok()) else { return };
            let surface = vbox.children().into_iter().find_map(|w| {
                w.downcast::<gtk::Layout>().ok().filter(|s| s.widget_name().as_str() == SURFACE)
            }).unwrap_or_else(|| {
                let s = gtk::Layout::new(gtk::Adjustment::NONE, gtk::Adjustment::NONE);
                s.set_widget_name(SURFACE); s.set_hexpand(true); s.set_vexpand(true);
                s.connect_size_allocate(|s, a| allocate(s, a.width(), a.height()));
                vbox.pack_start(&s, true, true, 0); s.show(); s
            });
            let attached = widget.parent().and_then(|p| p.downcast::<gtk::Layout>().ok()).is_some_and(|p| p == surface);
            if !attached {
                if let Some(p) = widget.parent().and_then(|p| p.downcast::<gtk::Container>().ok()) { p.remove(&widget); }
                widget.set_widget_name(name); widget.set_hexpand(false); widget.set_vexpand(false);
                surface.put(&widget, 0, 0); widget.show();
            }
            let a = surface.allocation(); allocate(&surface, a.width(), a.height());
        }).map_err(crate::err)?;
    }
    Ok(())
}
pub fn repair(app: &AppHandle) -> Result<(), String> { layout(app) }
pub fn geometry(view: &tauri::Webview) -> Result<(f64, f64, f64, f64), String> {
    let (tx, rx) = std::sync::mpsc::channel();
    view.with_webview(move |p| {
        let a = p.inner().allocation();
        let _ = tx.send((a.x() as f64, a.y() as f64, a.width() as f64, a.height() as f64));
    }).map_err(crate::err)?;
    rx.recv_timeout(std::time::Duration::from_secs(5)).map_err(crate::err)
}
