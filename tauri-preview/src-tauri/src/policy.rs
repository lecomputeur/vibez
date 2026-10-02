use serde::{Deserialize, Serialize};
use url::Url;

pub const APP_ID: &str = "nl.lecomputeur.vibez.tauri.preview";
pub const APP_NAME: &str = "VibeZ Tauri Preview";
pub const HOME: &str = "https://vibe.mistral.ai/";
pub const TOOLBAR_HEIGHT: f64 = 54.0;

pub fn local_url(url: &Url) -> bool {
    (url.scheme() == "tauri" && url.host_str() == Some("localhost"))
        || (url.scheme() == "http" && url.host_str() == Some("tauri.localhost"))
}

pub fn trusted_caller(label: &str, url: &Url) -> bool {
    matches!(label, "shell" | "settings") && local_url(url)
}

pub fn embedded_url(url: &Url) -> bool {
    if url.scheme() != "https" || !url.username().is_empty() || url.password().is_some() {
        return false;
    }
    let host = url.host_str().unwrap_or_default();
    host == "mistral.ai" || host.ends_with(".mistral.ai")
        || matches!(host, "accounts.google.com" | "login.microsoftonline.com" | "appleid.apple.com")
        // A recorded first-login flow navigated the MAIN view from Google to
        // this exact HTTPS origin. Handing that step to the system browser
        // splits the flow from the preview profile. Do not allow *.youtube.com.
        || (host == "accounts.youtube.com" && url.port_or_known_default() == Some(443))
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
}

impl Default for Settings {
    fn default() -> Self {
        Self { language: "system".into(), zoom_factor: 1.0, show_screenshot: true,
            close_to_tray: false, start_at_login: false }
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
        assert!(APP_NAME.contains("Preview"));
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
    #[test] fn observed_google_main_view_chain_stays_embedded() {
        // Synthetic origins from the diagnostic sequence, not real login URLs.
        // embedded_url is the first predicate used by main.on_navigation.
        for value in [
            "https://chat.mistral.ai/",
            "https://auth.mistral.ai/",
            "https://v2.auth.mistral.ai/",
            "https://accounts.google.com/",
            "https://accounts.youtube.com/",
            "https://accounts.google.com/",
            "https://v2.auth.mistral.ai/",
            "https://chat.mistral.ai/",
        ] {
            assert!(embedded_url(&u(value)), "Login step would leave the app: {value}");
        }
    }
    #[test] fn youtube_account_exception_is_exact_https_origin_only() {
        assert!(embedded_url(&u("https://accounts.youtube.com/")));
        assert!(embedded_url(&u("https://accounts.youtube.com:443/")));
        for value in [
            "http://accounts.youtube.com/",
            "https://accounts.youtube.com:444/",
            "https://accounts.youtube.com.evil.example/",
            "https://evil.accounts.youtube.com/",
            "https://notaccounts.youtube.com/",
            "https://youtube.com/",
            "https://www.youtube.com/",
            "https://user:password@accounts.youtube.com/",
            "https://accounts.youtube.com@evil.example/",
        ] {
            assert!(!embedded_url(&u(value)), "Unexpected embedded origin: {value}");
        }
    }
    #[test] fn youtube_account_page_never_gains_native_commands() {
        for label in ["vibe", "auth-popup-1", "shell", "settings"] {
            assert!(!trusted_caller(label, &u("https://accounts.youtube.com/")));
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
