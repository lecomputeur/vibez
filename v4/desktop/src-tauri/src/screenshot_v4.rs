//! V4 adapter for the proven V3 screenshot dialog (visible page, full page,
//! selection; paste, copy, save). The capture, paste and save modules are
//! shared unchanged; this file supplies the few app services they expect.
use std::sync::atomic::AtomicBool;
use tauri::{AppHandle, Manager};

/// The Mistral page in the V4 window. (The V3 preview called it "vibe".)
pub const PAGE_VIEW: &str = "mistral-web";

pub struct PreviewState {
    pub capture_busy: AtomicBool,
    pub smoke: bool,
}
impl PreviewState {
    pub fn new() -> Self { Self { capture_busy: AtomicBool::new(false), smoke: false } }
}

pub fn title() -> String { "VibeZ V4 Beta".into() }

/// The V3 preview showed these in its status bar. The V4 dialog reports its
/// own result, so only keep a trace for diagnostics.
pub fn message(_app: &AppHandle, text: impl Into<String>) {
    let _ = text.into();
}

#[allow(dead_code)]
#[path = "policy.rs"]
pub mod policy;

pub mod rich_render {
    /// V4 has no rich-render layer to pause during a capture.
    pub struct CapturePause;
    impl CapturePause {
        pub fn new(_view: &tauri::Webview) -> Self { Self }
        pub async fn begin(&self) -> Result<(), String> { Ok(()) }
    }
}

pub mod desktop_ui {
    use super::*;
    fn preview_translations() -> &'static serde_json::Value {
        static DATA: std::sync::OnceLock<serde_json::Value> = std::sync::OnceLock::new();
        DATA.get_or_init(|| serde_json::from_str(include_str!("../../preview-i18n.json")).expect("bundled preview translations"))
    }
    pub fn language(app: &AppHandle) -> String {
        crate::classic_language::info(app)["resolved"].as_str().unwrap_or("en").to_owned()
    }
    pub fn preview_for(language: &str, key: &str) -> String {
        let data = &preview_translations()["translations"];
        data[language][key].as_str().or_else(|| data["en"][key].as_str()).unwrap_or(key).to_owned()
    }
    pub fn preview(app: &AppHandle, key: &str) -> String { preview_for(&language(app), key) }
    pub fn text(app: &AppHandle, key: &str) -> String {
        let value = preview(app, key);
        if value == "screenshot" { "Screenshot".into() } else { value }
    }
    pub fn status(app: &AppHandle, raw: &str) -> String {
        let key = match raw {
            "screenshot_busy" => "screenshotBusy",
            "screenshot_working" => "screenshotWorking",
            "screenshot_cancelled" => "screenshotCancelled",
            "screenshot_copied" => "screenshotCopied",
            _ => return raw.into(),
        };
        let value = preview(app, key);
        if cfg!(target_os = "macos") { value.replace("Ctrl+V", "⌘V") } else { value }
    }
}

/// Only the bundled dialog window may use the screenshot commands.
pub fn require_dialog(view: &tauri::Webview) -> Result<(), String> {
    let url = view.url().map_err(crate::err)?;
    if view.label() == "screenshot" && policy::local_url(&url) && url.path() == "/screenshot.html" { Ok(()) }
    else { Err("Only the VibeZ screenshot dialog can do this".into()) }
}

/// State the V3 dialog script reads: language and the selected Mistral mode.
pub async fn dialog_state(app: &AppHandle) -> serde_json::Value {
    let info = crate::classic_language::info(app);
    let resolved = info["resolved"].as_str().unwrap_or("en").to_owned();
    let mode = crate::screenshot_dialog::selected_mode(app).await;
    serde_json::json!({
        "settings": {"language": resolved},
        "os_locale": resolved,
        "screenshot_code_context": !matches!(mode.as_str(), "chat" | "work"),
        "screenshot_mode": mode,
        "screenshot_login_required": crate::screenshot_dialog::login_required(app).await,
    })
}

pub fn manage(app: &AppHandle) { app.manage(PreviewState::new()); }

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn dialog_texts_exist_for_every_status_key() {
        for key in ["screenshotBusy", "screenshotWorking", "screenshotCancelled", "screenshotCopied", "screenshotSavePng", "screenshotCancel", "screenshotDrag", "pasteConfirmed", "pasteUnconfirmed"] {
            assert_ne!(desktop_ui::preview_for("en", key), key, "{key}");
            assert_ne!(desktop_ui::preview_for("nl", key), key, "{key}");
        }
    }
    #[test]
    fn the_page_view_is_the_v4_mistral_view() { assert_eq!(PAGE_VIEW, "mistral-web"); }
}
