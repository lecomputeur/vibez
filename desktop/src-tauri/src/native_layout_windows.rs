//! Windows child webviews use explicit bounds; WebView2 supports absolute child-view layout.
use tauri::{AppHandle, Manager, LogicalPosition, LogicalSize, Rect};
use crate::policy::TOOLBAR_HEIGHT;

pub fn layout(app: &AppHandle) -> Result<(), String> {
    let Some(window) = app.get_window("main") else { return Ok(()); };
    let scale = window.scale_factor().map_err(crate::err)?;
    let size = window.inner_size().map_err(crate::err)?.to_logical::<f64>(scale);
    let width = size.width.max(1.0);
    let height = (size.height - TOOLBAR_HEIGHT).max(1.0);
    if let Some(shell) = app.get_webview("shell") {
        shell.set_bounds(Rect {
            position: LogicalPosition::new(0.0, 0.0).into(),
            size: LogicalSize::new(width, TOOLBAR_HEIGHT).into(),
        }).map_err(crate::err)?;
    }
    if let Some(vibe) = app.get_webview("vibe") {
        vibe.set_bounds(Rect {
            position: LogicalPosition::new(0.0, TOOLBAR_HEIGHT).into(),
            size: LogicalSize::new(width, height).into(),
        }).map_err(crate::err)?;
    }
    Ok(())
}

pub fn geometry(view: &tauri::Webview) -> Result<(f64, f64, f64, f64), String> {
    let scale = view.window().scale_factor().map_err(crate::err)?;
    let position = view.position().map_err(crate::err)?.to_logical::<f64>(scale);
    let size = view.size().map_err(crate::err)?.to_logical::<f64>(scale);
    Ok((position.x, position.y, size.width, size.height))
}

pub fn repair(app: &AppHandle) -> Result<(), String> { layout(app) }
