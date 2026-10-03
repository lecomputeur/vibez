//! Native menus and preview-specific status text share the saved language selection.
use std::sync::OnceLock;
use serde_json::Value;
use tauri::{AppHandle, Manager, menu::{Menu, MenuItem}, tray::TrayIconBuilder};
use crate::{PreviewState, policy::APP_NAME};
fn translations() -> &'static Value {
    static DATA: OnceLock<Value> = OnceLock::new();
    DATA.get_or_init(|| serde_json::from_str(include_str!("../../dist/translations.json")).expect("validated bundled translations"))
}
fn preview_translations() -> &'static Value {
    static DATA: OnceLock<Value> = OnceLock::new();
    DATA.get_or_init(|| serde_json::from_str(include_str!("../../dist/preview-translations.json")).expect("validated preview translations"))
}
pub fn resolve(setting: &str, locale: &str) -> String {
    let raw = if setting.is_empty() || setting == "system" { locale } else { setting };
    let raw = raw.replace('_', "-").to_lowercase();
    let candidate = if raw.starts_with("zh") {
        if ["tw", "hk", "mo", "hant"].iter().any(|s| raw.contains(s)) { "zh-TW" } else { "zh-CN" }
    } else { raw.split(['.', '-']).next().unwrap_or("en") };
    if translations()["translations"].get(candidate).is_some() { candidate.into() } else { "en".into() }
}
pub fn language(app: &AppHandle) -> String {
    let setting = app.state::<PreviewState>().settings.lock().map(|s| s.language.clone()).unwrap_or_else(|_| "system".into());
    resolve(&setting, &crate::os_locale())
}
pub fn text_for(language: &str, key: &str) -> String {
    translations()["translations"][language][key].as_str()
        .or_else(|| translations()["translations"]["en"][key].as_str()).unwrap_or(key).into()
}
pub fn preview_for(language: &str, key: &str) -> String {
    preview_translations()["translations"][language][key].as_str()
        .or_else(|| preview_translations()["translations"]["en"][key].as_str()).unwrap_or(key).into()
}
pub fn text(app: &AppHandle, key: &str) -> String { text_for(&language(app), key) }
pub fn preview(app: &AppHandle, key: &str) -> String { preview_for(&language(app), key) }
fn menu_label(language: &str, key: &str) -> String {
    let text = text_for(language, key);
    if key == "open" { text.replace("VibeZ", APP_NAME) } else { text }
}
pub fn status(app: &AppHandle, raw: &str) -> String {
    let lang = language(app);
    if let Some(key) = match raw {
        "Rust / WebKitGTK · isolated preview" | "Rust / WebView2 · isolated preview" | "Rust / Tauri · isolated preview" => Some("isolatedStatus"),
        "Choose a screenshot in the desktop dialog…" => Some("screenshotChoose"),
        "Opening Windows screen capture…" => Some("windowsCaptureOpening"),
        "Windows screen capture opened — select an area, then paste it into Vibe with Ctrl+V." => Some("windowsCaptureOpened"),
        "Screenshot copied — paste it into Vibe with Ctrl+V." => Some("screenshotCopied"),
        "A screenshot is already in progress" => Some("screenshotBusy"),
        "Returning to Vibe. Your preview profile has not been cleared." => Some("returningVibe"),
        "Could not open the external link in your browser." => Some("externalLinkFailed"),
        "Page could not load. Use Home to retry; details are in Settings." => Some("pageLoadFailed"),
        "The web process stopped. Use Home to retry; details are in Settings." => Some("webProcessStopped"),
        "Sign-in opened in a separate window. Provider restrictions may still apply." => Some("signInOpened"),
        "A popup with an unsupported address was blocked." => Some("popupUnsupported"),
        "Close an existing sign-in window before opening another." => Some("popupLimit"),
        "Could not open the preview's sign-in profile." => Some("signInProfileFailed"),
        "An additional nested sign-in window was blocked." => Some("nestedPopupBlocked"),
        "Could not create the sign-in window. Your Vibe page has not been replaced." => Some("signInWindowFailed"),
        "settings_saved" => Some("saved"),
        "settings_recovered" => Some("settingsRecovered"),
        "site_language_failed" => Some("siteLanguageFailed"),
        _ => None,
    } { return preview_for(&lang, key); }
    match raw {
        "Checking for preview updates…" => text_for(&lang, "checking"),
        "Preview update available." => text_for(&lang, "updateReady"),
        "No newer tested preview is available." => text_for(&lang, "latest"),
        "No downloadable tested preview was found." => preview_for(&lang, "noDownloadHelp"),
        "Could not check preview updates. Please try again later." => text_for(&lang, "updateFailed"),
        _ if raw.starts_with("Screenshot cancelled or unavailable:") => text_for(&lang, "shotFailed"),
        _ if raw.starts_with("Tray unavailable:") => preview_for(&lang, "trayUnavailable"),
        _ if raw.starts_with("Menu update failed:") => preview_for(&lang, "serviceErrorHelp"),
        _ => raw.into(),
    }
}
pub fn menu(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let lang = language(app);
    let label = |key| menu_label(&lang, key);
    let open = MenuItem::with_id(app, "open", label("open"), true, None::<&str>)?;
    let capture = MenuItem::with_id(app, "capture", label("screenshot"), true, None::<&str>)?;
    let settings = MenuItem::with_id(app, "settings", label("settings"), true, None::<&str>)?;
    let updates = MenuItem::with_id(app, "updates", label("updates"), true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", label("quit"), true, None::<&str>)?;
    Menu::with_items(app, &[&open, &capture, &settings, &updates, &quit])
}
pub fn refresh(app: &AppHandle) -> tauri::Result<()> {
    if let Some(tray) = app.tray_by_id("vibez-tauri-preview") { tray.set_menu(Some(menu(app)?))?; }
    if let Some(window) = app.get_webview_window("settings") {
        window.set_title(&format!("{} · {}", crate::title(), text(app, "settings")))?;
    }
    Ok(())
}
pub fn create_tray(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let mut builder = TrayIconBuilder::with_id("vibez-tauri-preview")
        .tooltip(crate::title()).menu(&menu(app)?).show_menu_on_left_click(true)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => crate::show_main(app),
            "quit" => app.exit(0),
            "settings" => { let app = app.clone(); tauri::async_runtime::spawn(async move {
                if let Err(e) = crate::open_settings(&app).await { crate::message(&app, e); }
            }); },
            "capture" => { let app = app.clone(); tauri::async_runtime::spawn(async move { let _ = crate::take_screenshot(&app).await; }); },
            "updates" => crate::preview_updates::start(app.clone()),
            _ => (),
        });
    if let Some(icon) = app.default_window_icon() { builder = builder.icon(icon.clone()); }
    builder.build(app)?;
    Ok(())
}
pub fn smoke_check(app: &AppHandle) -> Result<(), String> {
    let original = app.state::<PreviewState>().settings.lock().map_err(crate::err)?.language.clone();
    for lang in ["nl", "en", "de", "ar"] {
        app.state::<PreviewState>().settings.lock().map_err(crate::err)?.language = lang.into();
        let menu = menu(app).map_err(crate::err)?;
        if menu.items().map_err(crate::err)?.len() != 5 { return Err("Tray menu lost an action".into()); }
        for (id, key) in [("open", "open"), ("capture", "screenshot"), ("settings", "settings"), ("updates", "updates"), ("quit", "quit")] {
            let item = menu.get(id).ok_or("Missing tray item")?;
            let actual = item.as_menuitem().ok_or("Wrong tray item kind")?.text().map_err(crate::err)?;
            if actual != menu_label(lang, key) { return Err(format!("Tray translation mismatch: {lang}/{id}")); }
        }
        if preview_for(lang, "languageButton").is_empty() { return Err(format!("Missing preview language text: {lang}")); }
    }
    app.state::<PreviewState>().settings.lock().map_err(crate::err)?.language = original;
    println!("TRAY_OK: native menu and preview text follow saved language selection");
    Ok(())
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn locale_follows_settings_or_os() {
        assert_eq!(resolve("system", "nl_NL.UTF-8"), "nl");
        assert_eq!(resolve("system", "nl-BE"), "nl");
        assert_eq!(resolve("en", "nl_NL.UTF-8"), "en");
        assert_eq!(resolve("system", "zh_Hant_TW"), "zh-TW");
        assert_eq!(resolve("system", "C"), "en");
    }
    #[test] fn all_34_languages_have_native_and_preview_text() {
        let langs = translations()["translations"].as_object().unwrap();
        let preview = preview_translations()["translations"].as_object().unwrap();
        assert_eq!(langs.len(), 34); assert_eq!(preview.len(), 34);
        for (code, strings) in langs {
            for key in ["open", "screenshot", "settings", "updates", "quit"] {
                assert!(!strings[key].as_str().unwrap_or_default().is_empty(), "{code}/{key}");
            }
            let extras = preview.get(code).expect("matching preview language");
            for key in ["intro", "limits", "saved", "languageButton", "chooseLanguage", "updateManualHelp", "settingsConflict", "settingsRecovered", "siteLanguageFailed", "trayUnavailable"] {
                assert!(!extras[key].as_str().unwrap_or_default().is_empty(), "{code}/{key}");
            }
        }
        assert_eq!(text_for("nl", "settings"), "Instellingen");
        assert_eq!(preview_for("nl", "languageButton"), "Taal");
        assert_eq!(menu_label("nl", "open"), "VibeZ Tauri Preview openen");
    }
}
