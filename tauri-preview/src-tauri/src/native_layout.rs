//! Linux uses one GtkFixed canvas so child WebKit views keep exact bounds on
//! both X11 and Wayland. GtkBox natural-size negotiation can otherwise let the
//! toolbar webview consume a large fraction of the window after its HTML loads.
use gtk::prelude::*;
use tauri::{AppHandle, Manager};
use crate::policy::TOOLBAR_HEIGHT;

const LAYOUT_NAME: &str = "vibez-tauri-fixed-layout";

fn fixed_layout(app: &AppHandle) -> Result<(tauri::Window, gtk::Fixed), String> {
    let window = app.get_window("main").ok_or("Missing main window")?;
    let vbox = window.default_vbox().map_err(crate::err)?;

    if let Some(fixed) = vbox.children().into_iter().find_map(|child| {
        child.downcast::<gtk::Fixed>().ok()
            .filter(|fixed| fixed.widget_name().as_str() == LAYOUT_NAME)
    }) {
        return Ok((window, fixed));
    }

    let fixed = gtk::Fixed::new();
    fixed.set_widget_name(LAYOUT_NAME);
    fixed.set_hexpand(true);
    fixed.set_vexpand(true);
    vbox.pack_start(&fixed, true, true, 0);
    vbox.set_child_packing(&fixed, true, true, 0, gtk::PackType::Start);
    fixed.show();
    Ok((window, fixed))
}

fn place(view: &tauri::Webview, fixed: &gtk::Fixed, x: i32, y: i32, width: i32, height: i32) -> Result<(), String> {
    let fixed = fixed.clone();
    view.with_webview(move |platform| {
        let widget = platform.inner();

        let already_in_fixed = widget.parent()
            .and_then(|parent| parent.downcast::<gtk::Fixed>().ok())
            .is_some_and(|parent| parent == fixed);

        if !already_in_fixed {
            if let Some(parent) = widget.parent().and_then(|parent| parent.downcast::<gtk::Container>().ok()) {
                parent.remove(&widget);
            }
            fixed.put(&widget, x, y);
        }

        fixed.move_(&widget, x, y);
        widget.set_hexpand(false);
        widget.set_vexpand(false);
        widget.set_size_request(width.max(1), height.max(1));
        widget.show();
        fixed.show();
    }).map_err(crate::err)
}

fn apply(app: &AppHandle) -> Result<(), String> {
    if app.get_webview("shell").is_none() || app.get_webview("vibe").is_none() {
        return Ok(());
    }

    let (window, fixed) = fixed_layout(app)?;
    let scale = window.scale_factor().map_err(crate::err)?;
    let size = window.inner_size().map_err(crate::err)?.to_logical::<f64>(scale);
    let width = size.width.round().max(1.0) as i32;
    let total_height = size.height.round().max(1.0) as i32;
    let toolbar_height = (TOOLBAR_HEIGHT.round() as i32).clamp(1, total_height);
    let content_height = (total_height - toolbar_height).max(1);

    fixed.set_size_request(width, total_height);

    if let Some(shell) = app.get_webview("shell") {
        place(&shell, &fixed, 0, 0, width, toolbar_height)?;
    }
    if let Some(vibe) = app.get_webview("vibe") {
        place(&vibe, &fixed, 0, toolbar_height, width, content_height)?;
    }

    fixed.queue_resize();
    if let Some(gtk_window) = fixed.toplevel().and_then(|w| w.downcast::<gtk::Window>().ok()) {
        gtk_window.queue_resize();
    }
    window.show().map_err(crate::err)?;
    Ok(())
}

pub fn layout(app: &AppHandle) -> Result<(), String> {
    apply(app)
}

pub fn repair(app: &AppHandle) -> Result<(), String> {
    apply(app)
}

/// Inspect actual GTK widget allocation. The caller must be off the GTK event
/// loop thread while waiting for the callback.
pub fn geometry(view: &tauri::Webview) -> Result<(f64, f64, f64, f64), String> {
    let (tx, rx) = std::sync::mpsc::channel();
    view.with_webview(move |platform| {
        let widget = platform.inner();
        let allocation = widget.allocation();
        eprintln!("GTK_GEOMETRY: visible={} mapped={} allocation={:?}", widget.is_visible(), widget.is_mapped(), allocation);
        let _ = tx.send((
            allocation.x() as f64,
            allocation.y() as f64,
            allocation.width() as f64,
            allocation.height() as f64,
        ));
    }).map_err(crate::err)?;
    rx.recv_timeout(std::time::Duration::from_secs(5)).map_err(crate::err)
}
