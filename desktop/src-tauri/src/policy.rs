use serde::{Deserialize, Serialize};
use url::Url;

pub const APP_ID: &str = "nl.lecomputeur.vibez3";
pub const APP_NAME: &str = "VibeZ 3";
pub const HOME: &str = "https://vibe.mistral.ai/";
pub const TOOLBAR_HEIGHT: f64 = 54.0;

pub fn local_url(url: &Url) -> bool {
    (url.scheme() == "tauri" && url.host_str() == Some("localhost"))
        || (url.scheme() == "http" && url.host_str() == Some("tauri.localhost"))
}

pub fn trusted_caller(label: &str, url: &Url) -> bool {
    matches!(label, "shell" | "settings" | "screenshot") && local_url(url)
}

fn safe_https(url: &Url) -> bool {
    url.scheme() == "https"
        && url.host_str().is_some()
        && url.port_or_known_default() == Some(443)
        && url.username().is_empty()
        && url.password().is_none()
}

pub fn embedded_url(url: &Url) -> bool {
    if !safe_https(url) { return false; }
    let host = url.host_str().unwrap_or_default();
    host == "mistral.ai" || host.ends_with(".mistral.ai")
        || matches!(host, "accounts.google.com" | "login.microsoftonline.com" | "appleid.apple.com")
}

/// Origins that can legitimately START a sign-in flow. This is intentionally
/// small. After entry, the redirect chain is handled generically by
/// auth_chain_url instead of maintaining an endless provider-domain allowlist.
pub fn auth_entry_url(url: &Url) -> bool {
    if !safe_https(url) { return false; }
    let host = url.host_str().unwrap_or_default();
    host == "auth.mistral.ai" || host.ends_with(".auth.mistral.ai")
        || matches!(host,
            "accounts.google.com"
            | "login.microsoftonline.com"
            | "login.live.com"
            | "appleid.apple.com")
}

/// While authentication mode is active, normal HTTPS redirects stay inside
/// the same webview/profile. Unsafe schemes, URL credentials and nonstandard
/// ports never become valid merely because a login is in progress.
pub fn auth_chain_url(url: &Url) -> bool { safe_https(url) }

/// Reaching the actual Vibe/Chat content ends authentication mode. Mistral's
/// auth subdomains do not end it because they can be intermediate callbacks.
pub fn auth_return_url(url: &Url) -> bool {
    if !safe_https(url) { return false; }
    matches!(url.host_str().unwrap_or_default(), "vibe.mistral.ai" | "chat.mistral.ai")
}

/// Map the preview language to a locale currently exposed by Mistral's web UI.
/// The preview has more translations than Mistral itself; unsupported website
/// locales intentionally fall back to English instead of writing an invalid
/// NEXT_LOCALE value.
pub fn mistral_site_locale(selected: &str, os_locale: &str) -> String {
    let requested = if selected == "system" { os_locale } else { selected };
    let normalized = requested.replace('_', "-");
    let primary = normalized.split('-').next().unwrap_or("en").to_ascii_lowercase();
    match primary.as_str() {
        "en" | "fr" | "de" | "es" | "pl" | "it" | "pt" | "ar" | "nl" | "uk" => primary,
        _ => "en".into(),
    }
}

pub fn external_url(url: &Url) -> bool {
    matches!(url.scheme(), "https" | "http")
        && url.host_str().is_some() && url.username().is_empty() && url.password().is_none()
}

pub fn content_size(width: f64, height: f64) -> (f64, f64) {
    (width.max(1.0), (height - TOOLBAR_HEIGHT).max(1.0))
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Settings {
    pub language: String,
    pub zoom_factor: f64,
    pub show_screenshot: bool,
    pub close_to_tray: bool,
    pub start_at_login: bool,
    pub auto_updates: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self { language: "system".into(), zoom_factor: 1.0, show_screenshot: true,
            close_to_tray: false, start_at_login: false, auto_updates: true }
    }
}

impl Settings {
    pub fn validate(&self) -> Result<(), String> {
        const LANGUAGES: &[&str] = &["system", "en", "nl", "de", "fr", "es", "it", "pt", "pl", "ru", "uk", "tr", "zh-CN", "zh-TW", "ja", "ko", "hi", "bn", "pa", "mr", "te", "ta", "gu", "id", "vi", "th", "fil", "jv", "sw", "ha", "am", "ar", "he", "fa", "ur"];
        if !LANGUAGES.contains(&self.language.as_str()) { return Err("Unsupported language".into()); }
        if !self.zoom_factor.is_finite() || !(0.5..=2.0).contains(&self.zoom_factor) {
            return Err("Zoom must be between 50% and 200%".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn u(value: &str) -> Url { value.parse().unwrap() }
    #[test] fn preview_identity_is_not_electron() {
        assert_ne!(APP_ID, "com.vibez.app");
        assert_ne!(APP_ID, "LeComputeur.VibeZDesktop");
        assert_eq!(APP_NAME, "VibeZ 3");
    }
    #[test] fn native_commands_only_accept_bundled_control_views() {
        assert!(trusted_caller("shell", &u("tauri://localhost/index.html")));
        assert!(trusted_caller("shell", &u("http://tauri.localhost/index.html")));
        assert!(trusted_caller("settings", &u("tauri://localhost/settings.html")));
        assert!(!trusted_caller("vibe", &u("tauri://localhost/offline.html")));
        assert!(!trusted_caller("shell", &u(HOME)));
        assert!(!trusted_caller("settings", &u("https://localhost/settings.html")));
        assert!(!trusted_caller("auth", &u("tauri://localhost/index.html")));
    }
    #[test] fn embedded_allowlist_rejects_lookalikes_and_unsafe_schemes() {
        assert!(embedded_url(&u(HOME)));
        assert!(embedded_url(&u("https://auth.mistral.ai/login")));
        assert!(embedded_url(&u("https://accounts.google.com/")));
        for value in ["https://mistral.ai.evil.example/", "https://notmistral.ai/", "http://vibe.mistral.ai/", "file:///etc/passwd", "javascript:alert(1)", "tauri://localhost/index.html", "https://user:password@mistral.ai/"] {
            assert!(!embedded_url(&u(value)), "{value}");
        }
    }
    #[test] fn auth_entry_is_provider_agnostic_after_mistral_login_page() {
        for value in [
            "https://auth.mistral.ai/",
            "https://v2.auth.mistral.ai/",
            "https://accounts.google.com/",
            "https://login.microsoftonline.com/",
            "https://login.live.com/",
            "https://appleid.apple.com/",
        ] {
            assert!(auth_entry_url(&u(value)), "Expected auth entry: {value}");
        }
        for value in [
            "http://v2.auth.mistral.ai/",
            "https://login.live.com:444/",
            "https://login.live.com.evil.example/",
            "https://user:password@accounts.google.com/",
        ] {
            assert!(!auth_entry_url(&u(value)), "Unsafe auth entry: {value}");
        }
    }
    #[test] fn active_auth_chain_is_https_origin_generic_not_provider_specific() {
        for value in [
            "https://accounts.youtube.com/",
            "https://www.google.com/",
            "https://login.live.com/",
            "https://account.live.com/",
            "https://example.identity-provider.test/",
        ] {
            assert!(auth_chain_url(&u(value)), "Safe HTTPS redirect rejected: {value}");
        }
        for value in [
            "http://accounts.google.com/",
            "https://example.com:444/",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "data:text/html,test",
            "https://user:password@example.com/",
        ] {
            assert!(!auth_chain_url(&u(value)), "Unsafe auth redirect accepted: {value}");
        }
    }
    #[test] fn auth_mode_ends_only_on_vibe_content_origins() {
        assert!(auth_return_url(&u("https://vibe.mistral.ai/")));
        assert!(auth_return_url(&u("https://chat.mistral.ai/")));
        for value in [
            "https://v2.auth.mistral.ai/",
            "https://accounts.google.com/",
            "https://login.live.com/",
            "https://mistral.ai/",
            "http://chat.mistral.ai/",
        ] {
            assert!(!auth_return_url(&u(value)), "Auth mode ended too early: {value}");
        }
    }
    #[test] fn auth_pages_never_gain_native_commands() {
        for origin in [
            "https://accounts.google.com/",
            "https://accounts.youtube.com/",
            "https://login.live.com/",
            "https://example.identity-provider.test/",
        ] {
            for label in ["vibe", "auth-popup-1", "shell", "settings"] {
                assert!(!trusted_caller(label, &u(origin)), "Remote auth page got native access");
            }
        }
    }
    #[test] fn mistral_site_language_tracks_supported_preview_languages() {
        for (input, expected) in [
            ("en", "en"), ("nl", "nl"), ("de", "de"), ("fr", "fr"),
            ("es", "es"), ("it", "it"), ("pt", "pt"), ("pl", "pl"),
            ("ar", "ar"), ("uk", "uk"),
        ] {
            assert_eq!(mistral_site_locale(input, "en-US"), expected);
        }
        assert_eq!(mistral_site_locale("system", "nl-NL"), "nl");
        assert_eq!(mistral_site_locale("system", "de_DE.UTF-8"), "de");
    }
    #[test] fn unsupported_mistral_site_languages_fall_back_to_english() {
        for input in ["zh-CN", "ja", "ko", "hi", "ru", "tr", "he", "fa", "ur"] {
            assert_eq!(mistral_site_locale(input, "nl-NL"), "en", "{input}");
        }
    }
    #[test] fn browser_opener_never_accepts_local_files_or_commands() {
        assert!(external_url(&u("https://example.org/")));
        for value in ["file:///etc/passwd", "javascript:alert(1)", "data:text/html,test", "vibez://settings"] {
            assert!(!external_url(&u(value)), "{value}");
        }
    }
    #[test] fn resizing_preserves_fixed_toolbar_in_logical_pixels() {
        for (w,h) in [(1280.,840.), (1920.,1080.), (760.,560.), (2560./1.5,1440./1.5)] {
            let (vw,vh) = content_size(w,h);
            assert_eq!(vw,w); assert_eq!(vh+TOOLBAR_HEIGHT,h);
        }
        assert_eq!(content_size(0.,0.), (1.,1.));
    }
    #[test] fn preview_defaults_have_no_background_side_effects() {
        let s = Settings::default();
        assert!(!s.start_at_login && !s.close_to_tray);
        assert!(s.validate().is_ok());
    }
    #[test] fn reject_invalid_zoom_and_language() {
        for zoom in [f64::NAN, f64::INFINITY, -1., 0., 10.] {
            assert!(Settings { zoom_factor: zoom, ..Settings::default() }.validate().is_err());
        }
        assert!(Settings { language: "../VibeZ".into(), ..Settings::default() }.validate().is_err());
        assert!(serde_json::from_str::<Settings>(r#"{"command":"rm"}"#).is_err());
    }
}
