//! Native screenshot capture for VibeZ 3.
//! Selection uses the operating system. Visible/full-page modes capture the Vibe webview itself.

use crate::{err, PreviewState};
use tauri::{AppHandle, Manager, Webview};
use tauri_plugin_clipboard_manager::ClipboardExt;
use std::sync::atomic::Ordering;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    FullPage,
    Visible,
    Selection,
}
impl Mode {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "full_page" => Ok(Self::FullPage),
            "visible" => Ok(Self::Visible),
            "selection" => Ok(Self::Selection),
            _ => Err("Unknown screenshot mode".into()),
        }
    }
}

fn copy_image_bytes(app: &AppHandle, bytes: &[u8]) -> Result<(), String> {
    let rgba = image::load_from_memory(bytes).map_err(err)?.into_rgba8();
    let (width, height) = rgba.dimensions();
    if width == 0 || height == 0 { return Err("Screenshot is empty".into()); }
    if u64::from(width) * u64::from(height) > 120_000_000 {
        return Err("Screenshot is too large to copy safely".into());
    }
    let image = tauri::image::Image::new_owned(rgba.into_raw(), width, height);
    app.clipboard().write_image(&image).map_err(err)
}

pub async fn take(app: &AppHandle, mode: Mode) -> Result<(), String> {
    let state = app.state::<PreviewState>();
    if state.capture_busy.swap(true, Ordering::SeqCst) {
        return Err(crate::desktop_ui::status(app, "A screenshot is already in progress"));
    }
    let label = match mode {
        Mode::FullPage => "Capturing full page…",
        Mode::Visible => "Capturing visible page…",
        Mode::Selection => "Choose a screenshot in the desktop dialog…",
    };
    crate::message(app, label);

    let result = match mode {
        Mode::Selection => selection(app).await,
        Mode::Visible => page(app, false).await,
        Mode::FullPage => page(app, true).await,
    };

    state.capture_busy.store(false, Ordering::SeqCst);
    match &result {
        Ok(()) => {
            crate::message(app, "Screenshot copied — paste it into Vibe with Ctrl+V.");
            crate::show_main(app);
        }
        Err(error) => crate::message(app, format!("Screenshot cancelled or unavailable: {error}")),
    }
    result
}

async fn page(app: &AppHandle, full: bool) -> Result<(), String> {
    let view = app.get_webview("vibe").ok_or("Vibe view is not ready")?;
    let bytes = capture_webview(&view, full).await?;
    if bytes.len() > 96 * 1024 * 1024 { return Err("Screenshot exceeds the 96 MiB capture limit".into()); }
    copy_image_bytes(app, &bytes)
}

#[cfg(target_os = "linux")]
async fn capture_webview(view: &Webview, full: bool) -> Result<Vec<u8>, String> {
    use webkit2gtk::{prelude::WebViewExt, SnapshotOptions, SnapshotRegion};
    let (tx, rx) = tokio::sync::oneshot::channel();
    view.with_webview(move |platform| {
        let web = platform.inner().clone();
        let region = if full { SnapshotRegion::FullDocument } else { SnapshotRegion::Visible };
        web.snapshot(region, SnapshotOptions::NONE, None::<&webkit2gtk::gio::Cancellable>, move |result| {
            let output = result.map_err(err).and_then(|surface| {
                let mut bytes = Vec::new();
                surface.write_to_png(&mut bytes).map_err(err)?;
                Ok(bytes)
            });
            let _ = tx.send(output);
        });
    }).map_err(err)?;
    tokio::time::timeout(std::time::Duration::from_secs(if full { 20 } else { 8 }), rx)
        .await.map_err(|_| "Screenshot capture timed out".to_string())?
        .map_err(err)?
}

#[cfg(target_os = "windows")]
async fn capture_webview(view: &Webview, full: bool) -> Result<Vec<u8>, String> {
    use base64::Engine as _;
    use std::sync::{Arc, Mutex};
    use webview2_com::CallDevToolsProtocolMethodCompletedHandler;
    use windows::core::HSTRING;

    let (tx, rx) = tokio::sync::oneshot::channel();
    let tx = Arc::new(Mutex::new(Some(tx)));
    let args = serde_json::json!({
        "format": "png",
        "fromSurface": true,
        "captureBeyondViewport": full
    }).to_string();

    view.with_webview(move |platform| {
        let answer = tx.clone();
        let callback = CallDevToolsProtocolMethodCompletedHandler::create(Box::new(move |result, raw| {
            let output: Result<Vec<u8>, String> = (|| {
                result.map_err(err)?;
                let json = unsafe { raw.to_string().map_err(err)? };
                let value: serde_json::Value = serde_json::from_str(&json).map_err(err)?;
                let data = value.get("data").and_then(|v| v.as_str()).ok_or("WebView2 returned no screenshot data")?;
                base64::engine::general_purpose::STANDARD.decode(data).map_err(err)
            })();
            if let Ok(mut slot) = answer.lock() {
                if let Some(tx) = slot.take() { let _ = tx.send(output); }
            }
            Ok(())
        }));
        let result: Result<(), String> = (|| unsafe {
            let web = platform.controller().CoreWebView2().map_err(err)?;
            web.CallDevToolsProtocolMethod(
                &HSTRING::from("Page.captureScreenshot"),
                &HSTRING::from(args),
                &callback,
            ).map_err(err)
        })();
        if let Err(error) = result {
            if let Ok(mut slot) = tx.lock() {
                if let Some(tx) = slot.take() { let _ = tx.send(Err(error)); }
            }
        }
    }).map_err(err)?;

    tokio::time::timeout(std::time::Duration::from_secs(if full { 20 } else { 8 }), rx)
        .await.map_err(|_| "Screenshot capture timed out".to_string())?
        .map_err(err)?
}

#[cfg(target_os = "macos")]
async fn capture_webview(view: &Webview, full: bool) -> Result<Vec<u8>, String> {
    use block2::RcBlock;
    use objc2_foundation::{NSPoint, NSRect, NSSize, NSString};
    use objc2_app_kit::NSImage;
    use objc2_web_kit::WKWebView;
    use std::sync::{Arc, Mutex};

    let (tx, rx) = tokio::sync::oneshot::channel();
    let tx = Arc::new(Mutex::new(Some(tx)));

    view.with_webview(move |platform| {
        let ptr = platform.inner().cast::<WKWebView>();
        if ptr.is_null() {
            if let Ok(mut slot) = tx.lock() { if let Some(tx) = slot.take() { let _ = tx.send(Err("WKWebView is unavailable".into())); } }
            return;
        }

        unsafe {
            let web = &*ptr;
            let original = web.frame();

            let finish_snapshot = {
                let tx = tx.clone();
                move |restore: NSRect| {
                    let answer = tx.clone();
                    let image_block = RcBlock::new(move |image: *mut NSImage, error: *mut objc2_foundation::NSError| {
                        unsafe { (&*ptr).setFrame(restore); }
                        let output: Result<Vec<u8>, String> = (|| {
                            if !error.is_null() { return Err("WKWebView snapshot failed".into()); }
                            if image.is_null() { return Err("WKWebView returned no screenshot".into()); }
                            let data = unsafe { (&*image).TIFFRepresentation() }.ok_or("Could not encode WKWebView snapshot")?;
                            let len = data.length();
                            if len == 0 { return Err("WKWebView snapshot is empty".into()); }
                            let bytes = unsafe { std::slice::from_raw_parts(data.bytes().cast::<u8>(), len) }.to_vec();
                            Ok(bytes)
                        })();
                        if let Ok(mut slot) = answer.lock() {
                            if let Some(tx) = slot.take() { let _ = tx.send(output); }
                        }
                    });
                    unsafe { (&*ptr).takeSnapshotWithConfiguration_completionHandler(None, &image_block); }
                }
            };

            if !full {
                finish_snapshot(original);
            } else {
                let answer = tx.clone();
                let script = NSString::from_str(
                    "(() => { const d=document.documentElement,b=document.body; const w=Math.max(d.scrollWidth,d.clientWidth,b?b.scrollWidth:0); const h=Math.max(d.scrollHeight,d.clientHeight,b?b.scrollHeight:0); return String(w)+','+String(h); })()"
                );
                let metrics_block = RcBlock::new(move |value: *mut objc2::runtime::AnyObject, error: *mut objc2_foundation::NSError| {
                    if !error.is_null() || value.is_null() {
                        if let Ok(mut slot) = answer.lock() { if let Some(tx) = slot.take() { let _ = tx.send(Err("Could not measure the full page".into())); } }
                        return;
                    }
                    let raw = unsafe { &*value.cast::<NSString>() }.to_string();
                    let mut parts = raw.split(',');
                    let width = parts.next().and_then(|v| v.parse::<f64>().ok()).unwrap_or(original.size.width);
                    let height = parts.next().and_then(|v| v.parse::<f64>().ok()).unwrap_or(original.size.height);
                    if width <= 0.0 || height <= 0.0 || width * height > 120_000_000.0 || height > 50_000.0 {
                        if let Ok(mut slot) = answer.lock() { if let Some(tx) = slot.take() { let _ = tx.send(Err("Full page is too large to capture safely".into())); } }
                        return;
                    }
                    unsafe { (&*ptr).setFrame(NSRect::new(NSPoint::new(original.origin.x, original.origin.y), NSSize::new(width, height))); }
                    finish_snapshot(original);
                });
                web.evaluateJavaScript_completionHandler(&script, Some(&metrics_block));
            }
        }
    }).map_err(err)?;

    tokio::time::timeout(std::time::Duration::from_secs(if full { 25 } else { 10 }), rx)
        .await.map_err(|_| "Screenshot capture timed out".to_string())?
        .map_err(err)?
}

#[cfg(target_os = "linux")]
async fn selection(app: &AppHandle) -> Result<(), String> {
    // Cinnamon/X11 and several other desktops are more reliable with their native
    // region tool than with a portal dialog. If a tool starts, cancellation is final.
    if std::env::var("XDG_SESSION_TYPE").unwrap_or_default().eq_ignore_ascii_case("x11") {
        for (program, args) in [
            ("gnome-screenshot", vec!["-a", "-c"]),
            ("spectacle", vec!["-r", "-b", "-c"]),
            ("flameshot", vec!["gui", "-c"]),
        ] {
            match tauri::async_runtime::spawn_blocking(move || std::process::Command::new(program).args(args).status()).await.map_err(err)? {
                Ok(status) => return if status.success() { Ok(()) } else { Err("Capture cancelled".into()) },
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
                Err(error) => return Err(err(error)),
            }
        }
    }

    let response = ashpd::desktop::screenshot::Screenshot::request().interactive(true).modal(true)
        .send().await.map_err(err)?.response().map_err(err)?;
    let uri = url::Url::parse(response.uri().as_str()).map_err(err)?;
    let file = uri.to_file_path().map_err(|_| "The portal did not return a local image".to_string())?;
    if std::fs::metadata(&file).map_err(err)?.len() > 64 * 1024 * 1024 {
        return Err("Screenshot is larger than the 64 MiB preview limit".into());
    }
    let bytes = std::fs::read(file).map_err(err)?;
    copy_image_bytes(app, &bytes)
}

#[cfg(target_os = "windows")]
async fn selection(app: &AppHandle) -> Result<(), String> {
    crate::message(app, "Opening Windows screen capture…");
    app.opener().open_url("ms-screenclip:", None::<&str>).map_err(err)
}

#[cfg(target_os = "macos")]
async fn selection(_app: &AppHandle) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(|| {
        let status = std::process::Command::new("/usr/sbin/screencapture")
            .args(["-i", "-c"]).status().map_err(err)?;
        if status.success() { Ok(()) } else { Err("Capture cancelled or permission denied".to_string()) }
    }).await.map_err(err)?
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn screenshot_modes_are_explicit() {
        assert_eq!(Mode::parse("full_page").unwrap(), Mode::FullPage);
        assert_eq!(Mode::parse("visible").unwrap(), Mode::Visible);
        assert_eq!(Mode::parse("selection").unwrap(), Mode::Selection);
        assert!(Mode::parse("screen").is_err());
    }
}
