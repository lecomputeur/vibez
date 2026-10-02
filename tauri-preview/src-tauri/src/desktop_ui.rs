//! Native menus share the toolbar's bundled translations and language selection.
use std::sync::OnceLock;
use serde_json::Value;
use tauri::{AppHandle, Manager, menu::{Menu, MenuItem}, tray::TrayIconBuilder};
use crate::{PreviewState, policy::APP_NAME};
fn translations() -> &'static Value {
    static DATA: OnceLock<Value> = OnceLock::new();
    DATA.get_or_init(|| serde_json::from_str(include_str!("../../dist/translations.json")).expect("validated bundled translations"))
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
    if language == "nl" && key == "updates" { return "Controleren op updates…".into(); }
    translations()["translations"][language][key].as_str()
        .or_else(|| translations()["translations"]["en"][key].as_str()).unwrap_or(key).into()
}
fn menu_label(language: &str, key: &str) -> String {
    let text = text_for(language, key);
    // Existing translations already contain the name, e.g. "VibeZ openen".
    if key == "open" { text.replace("VibeZ", APP_NAME) } else { text }
}
pub fn text(app: &AppHandle, key: &str) -> String { text_for(&language(app), key) }
pub fn pair(app: &AppHandle, english: &str, dutch: &str) -> String {
    if language(app) == "nl" { dutch.into() } else { english.into() }
}
pub fn status(app: &AppHandle, raw: &str) -> String {
    if language(app) != "nl" { return raw.into(); }
    let translated = match raw {
        "Rust / WebKitGTK · isolated preview" => "Rust / WebKitGTK · aparte proefversie",
        "Choose a screenshot in the desktop dialog…" => "Kies een schermafbeelding in het Linux-dialoogvenster…",
        "Screenshot copied — paste it into Vibe with Ctrl+V." => "Schermafbeelding gekopieerd — plak deze in Vibe met Ctrl+V.",
        "A screenshot is already in progress" => "Er wordt al een schermafbeelding gemaakt",
        "Returning to Vibe. Your preview profile has not been cleared." => "Terug naar Vibe. Je profiel van de proefversie blijft behouden.",
        "Checking for preview updates…" => "Controleren op updates voor de proefversie…",
        "Preview update available." => "Er is een update voor de proefversie beschikbaar.",
        "No newer tested preview is available." => "Er is geen nieuwere geteste proefversie beschikbaar.",
        "No downloadable tested preview was found." => "Er is geen downloadbare, geteste proefversie gevonden.",
        "Could not check preview updates. Please try again later." => "Updates controleren is niet gelukt. Probeer het later opnieuw.",
        "Could not open the external link in your browser." => "De externe link kon niet in je browser worden geopend.",
        "Page could not load. Use Home to retry; details are in Settings." => "De pagina kon niet laden. Probeer opnieuw via het huisje; details staan bij Instellingen.",
        "The web process stopped. Use Home to retry; details are in Settings." => "De webweergave is gestopt. Probeer opnieuw via het huisje; details staan bij Instellingen.",
        "Sign-in opened in a separate window. Provider restrictions may still apply." => "Inloggen is in een apart venster geopend. Beperkingen van de aanbieder kunnen nog gelden.",
        "A popup with an unsupported address was blocked." => "Een pop-up met een niet-ondersteund adres is geblokkeerd.",
        "Close an existing sign-in window before opening another." => "Sluit eerst een bestaand inlogvenster voordat je een nieuw opent.",
        "Could not open the preview's sign-in profile." => "Het inlogprofiel van de proefversie kon niet worden geopend.",
        "An additional nested sign-in window was blocked." => "Een extra inlogvenster vanuit een pop-up is geblokkeerd.",
        "Could not create the sign-in window. Your Vibe page has not been replaced." => "Het inlogvenster kon niet worden geopend. Je Vibe-pagina is niet vervangen.",
        _ => raw,
    };
    for (prefix, replacement) in [
        ("Screenshot cancelled or unavailable:", "Schermafbeelding geannuleerd of niet beschikbaar:"),
        ("Tray unavailable:", "Systeemvak niet beschikbaar:"),
        ("Menu update failed:", "Bijwerken van het menu is niet gelukt:"),
    ] {
        if let Some(detail) = raw.strip_prefix(prefix) { return format!("{replacement}{detail}"); }
    }
    translated.into()
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
/// Construct real native menus off the GTK event-loop thread for integration tests.
pub fn smoke_check(app: &AppHandle) -> Result<(), String> {
    let original = app.state::<PreviewState>().settings.lock().map_err(crate::err)?.language.clone();
    for lang in ["nl", "en", "de", "nl"] {
        app.state::<PreviewState>().settings.lock().map_err(crate::err)?.language = lang.into();
        let menu = menu(app).map_err(crate::err)?;
        if menu.items().map_err(crate::err)?.len() != 5 { return Err("Tray menu lost an action".into()); }
        for (id, key) in [("open", "open"), ("capture", "screenshot"), ("settings", "settings"), ("updates", "updates"), ("quit", "quit")] {
            let item = menu.get(id).ok_or("Missing tray item")?;
            let actual = item.as_menuitem().ok_or("Wrong tray item kind")?.text().map_err(crate::err)?;
            if actual != menu_label(lang, key) { return Err(format!("Tray translation mismatch: {lang}/{id}")); }
        }
    }
    app.state::<PreviewState>().settings.lock().map_err(crate::err)?.language = original;
    println!("TRAY_OK: update action present; native menu follows Dutch, English and German selection");
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn locale_follows_settings_or_os() {
        assert_eq!(resolve("system", "nl_NL.UTF-8"), "nl");
        assert_eq!(resolve("system", "nl-BE"), "nl");
        assert_eq!(resolve("en", "nl_NL.UTF-8"), "en");
        assert_eq!(resolve("system", "zh_Hant_TW"), "zh-TW");
        assert_eq!(resolve("system", "C"), "en");
    }
    #[test] fn all_existing_languages_have_tray_translations() {
        let langs = translations()["translations"].as_object().unwrap();
        assert_eq!(langs.len(), 34);
        for (_, strings) in langs {
            for key in ["open", "screenshot", "settings", "updates", "quit"] {
                assert!(!strings[key].as_str().unwrap_or_default().is_empty(), "{key}");
            }
        }
        assert_eq!(text_for("nl", "settings"), "Instellingen");
        assert_eq!(text_for("nl", "updates"), "Controleren op updates…");
        assert_eq!(menu_label("nl", "open"), "VibeZ Tauri Preview openen");
        assert_eq!(menu_label("en", "open"), "Open VibeZ Tauri Preview");
    }
}
