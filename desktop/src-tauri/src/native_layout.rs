//! Let GTK allocate the two child webviews through an ordinary vertical box.
//! Startup visibility belongs to main.rs, not layout or repair callbacks.
use crate::policy::TOOLBAR_HEIGHT;
use gtk::prelude::*;
use std::{cell::Cell, rc::Rc, time::{SystemTime, UNIX_EPOCH}};
use tauri::{AppHandle, Manager};
const BOX_SURFACE: &str = "vibez-tauri-box-layout";
const SHELL: &str = "vibez-toolbar";
const CONTENT: &str = "vibez-content";

fn allocation_probe(widget: &webkit2gtk::WebView, label: &'static str, layout: &'static str) {
    if std::env::var_os("VIBEZ_RESIZE_TEST").is_none() { return; }
    let count = Rc::new(Cell::new(0_u64));
    let tiny = Rc::new(Cell::new(0_u64));
    widget.connect_size_allocate(move |_, allocation| {
        count.set(count.get() + 1);
        if allocation.width() <= 1 || allocation.height() <= 1 { tiny.set(tiny.get() + 1); }
        println!("SCROLL_PROBE {}", serde_json::json!({
            "event":"native-allocation", "layout":layout, "label":label,
            "count":count.get(), "tinyCount":tiny.get(),
            "wallMs":SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64()*1000.,
            "x":allocation.x(), "y":allocation.y(),
            "width":allocation.width(), "height":allocation.height()
        }));
    });
}

pub fn layout(app: &AppHandle) -> Result<(), String> {
    for (label, name) in [("shell", SHELL), ("vibe", CONTENT)] {
        let Some(view) = app.get_webview(label) else { continue };
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
            let attached = widget.parent().and_then(|p| p.downcast::<gtk::Box>().ok()).is_some_and(|p| p == surface);
            if !attached {
                if let Some(parent) = widget.parent().and_then(|p| p.downcast::<gtk::Container>().ok()) { parent.remove(&widget); }
                let content = label == "vibe";
                widget.set_widget_name(name);
                widget.set_hexpand(true); widget.set_vexpand(content);
                widget.set_halign(gtk::Align::Fill); widget.set_valign(gtk::Align::Fill);
                // These are genuine minima, independent of the current window
                // dimensions. GtkBox fills the content with the remaining area
                // in its normal allocation pass, without first allocating 1x1.
                widget.set_size_request(1, if content { 1 } else { TOOLBAR_HEIGHT as i32 });
                allocation_probe(&widget, name, "gtk-box");
                surface.pack_start(&widget, content, true, 0);
                surface.reorder_child(&widget, if content { -1 } else { 0 });
                widget.set_child_visible(true); widget.show();
            }
            // Showing child containers never shows a hidden toplevel window.
            vbox.show(); surface.show();
        }).map_err(crate::err)?;
    }
    Ok(())
}

pub fn repair(app: &AppHandle) -> Result<(), String> { layout(app) }
pub fn geometry(view: &tauri::Webview) -> Result<(f64, f64, f64, f64), String> {
    let (tx, rx) = std::sync::mpsc::channel();
    view.with_webview(move |p| {
        let widget = p.inner();
        let a = widget.allocation();
        let mut ancestor = Some(widget.upcast::<gtk::Widget>());
        for _ in 0..6 {
            let Some(node) = ancestor else { break };
            eprintln!("GTK_ALLOCATION: type={} name={} visible={} mapped={} bounds={:?}",
                node.type_().name(), node.widget_name(), node.is_visible(), node.is_mapped(), node.allocation());
            ancestor = node.parent();
        }
        let _ = tx.send((a.x() as f64, a.y() as f64, a.width() as f64, a.height() as f64));
    }).map_err(crate::err)?;
    rx.recv_timeout(std::time::Duration::from_secs(5)).map_err(crate::err)
}

/// Host-test option: place our offline window on the left monitor without
/// requesting focus. Live windows never use this test-only option.
pub fn place_offline_test(app: &AppHandle) -> Result<(), String> {
    if std::env::var_os("VIBEZ_OFFLINE_LEFT_SCREEN").is_none()
        || !app.state::<crate::PreviewState>().smoke { return Ok(()); }
    let window = app.get_window("main").ok_or("No main window")?;
    let native = window.gtk_window().map_err(crate::err)?;
    native.set_accept_focus(false);
    native.set_focus_on_map(false);
    native.move_(64, 64);
    Ok(())
}
