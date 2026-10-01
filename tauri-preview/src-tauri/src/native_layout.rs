//! Wry packs Linux child webviews into a GtkBox with expand=true by default.
//! Let GTK allocate the content rather than applying absolute bounds to a Box.
use gtk::prelude::*;
use tauri::{AppHandle, Manager};
use crate::policy::TOOLBAR_HEIGHT;

pub fn layout(app: &AppHandle) -> Result<(), String> {
    for (label, toolbar) in [("shell", true), ("vibe", false)] {
        if let Some(view) = app.get_webview(label) {
            view.with_webview(move |platform| {
                let widget = platform.inner();
                widget.set_hexpand(true);
                widget.set_vexpand(!toolbar);
                widget.set_size_request(-1, if toolbar { TOOLBAR_HEIGHT as i32 } else { -1 });
                if let Some(container) = widget.parent().and_then(|p| p.downcast::<gtk::Box>().ok()) {
                    container.set_homogeneous(false);
                    container.set_spacing(0);
                    container.set_child_packing(&widget, !toolbar, true, 0, gtk::PackType::Start);
                }
            }).map_err(crate::err)?;
        }
    }
    Ok(())
}

/// Inspect actual GTK widget allocation, not Wry's unsupported Box position API.
/// The caller must be off the GTK event-loop thread while waiting for the result.
pub fn geometry(view: &tauri::Webview) -> Result<(f64, f64, f64, f64), String> {
    let (tx, rx) = std::sync::mpsc::channel();
    view.with_webview(move |platform| {
        let allocation = platform.inner().allocation();
        let _ = tx.send((allocation.x() as f64, allocation.y() as f64,
            allocation.width() as f64, allocation.height() as f64));
    }).map_err(crate::err)?;
    rx.recv_timeout(std::time::Duration::from_secs(5)).map_err(crate::err)
}
