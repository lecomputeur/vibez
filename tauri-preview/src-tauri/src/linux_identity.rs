//! Stable desktop identity before the first native window is created.
//! GTK's application ID (Wayland) does not set the X11 WM_CLASS. Cinnamon
//! matches StartupWMClass against that separate property, not our Rust label.
use crate::policy::{APP_ID, APP_NAME};
use gtk::prelude::GtkWindowExt;
use std::{fs, io::Cursor, path::PathBuf};
use tauri::{AppHandle, Manager};

pub fn initialize() -> Result<(), String> {
    // Called on the GTK thread in setup, BEFORE WindowBuilder::build.
    // Set both halves of WM_CLASS so neither executable-name heuristics nor
    // launch order can select a different desktop entry.
    gtk::glib::set_prgname(Some(APP_ID));
    gtk::glib::set_application_name(APP_NAME);
    gtk::gdk::set_program_class(APP_ID);
    gtk::Window::set_default_icon_name(APP_ID);
    // GTK/X11 caps _NET_WM_ICON at 262144 words. A 512x512 image plus
    // its width/height header exceeds that limit and is silently discarded.
    // Use the generated 128px variant, also used by the Tauri default icon.
    let icon = gtk::gdk_pixbuf::Pixbuf::from_read(Cursor::new(
        include_bytes!("../icons/128x128.png").as_slice(),
    )).map_err(crate::err)?;
    gtk::Window::set_default_icon_list(&[icon]);
    Ok(())
}

pub fn tray_directory(app: &AppHandle) -> Result<PathBuf, String> {
    // Do not share /tmp/tray-icon with other applications/old instances:
    // one process tearing down its tray must not remove another's PNG.
    let directory = app.path().app_cache_dir().map_err(crate::err)?
        .join("tray-icons").join(std::process::id().to_string());
    fs::create_dir_all(&directory).map_err(crate::err)?;
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(&directory, fs::Permissions::from_mode(0o700)).map_err(crate::err)?;
    Ok(directory)
}

/// Set the per-window image before add_child/realize/show, not only a global
/// fallback. X11 panels can cache the first icon property they observe.
pub fn prepare_window(window: &tauri::Window) -> Result<(), String> {
    let icon = gtk::gdk_pixbuf::Pixbuf::from_read(Cursor::new(
        include_bytes!("../icons/128x128.png").as_slice(),
    )).map_err(crate::err)?;
    window.gtk_window().map_err(crate::err)?.set_icon(Some(&icon));
    Ok(())
}
