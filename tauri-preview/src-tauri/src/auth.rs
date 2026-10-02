//! Preserve window.open/opener semantics; never move popup requests into the main view.
//! No user-agent spoofing, credential interception, token logging or cookie export.
use std::{collections::VecDeque, sync::{Mutex, OnceLock, atomic::{AtomicU64, Ordering}}};
use tauri::{AppHandle, Manager, Webview, WebviewUrl, WebviewWindowBuilder};
use tauri::webview::{NewWindowFeatures, NewWindowResponse};
use tauri_plugin_opener::OpenerExt;
use url::Url;
use webkit2gtk::WebViewExt;
use crate::{policy, PreviewState};

const PREFIX: &str = "auth-popup-";
static NEXT_ID: AtomicU64 = AtomicU64::new(1);
static EVENTS: OnceLock<Mutex<VecDeque<String>>> = OnceLock::new();

pub fn origin(url: &Url) -> String {
    if url.as_str() == "about:blank" { return "about:blank".into(); }
    if policy::local_url(url) { return "bundled test page".into(); }
    match url.scheme() {
        "https" | "http" => url.origin().ascii_serialization(),
        _ => "blocked scheme".into(),
    }
}
fn record(kind: &str, url: &Url) {
    let event = format!("{kind}: {}", origin(url));
    if let Ok(mut events) = EVENTS.get_or_init(|| Mutex::new(VecDeque::new())).lock() {
        if events.len() == 24 { events.pop_front(); }
        events.push_back(event);
    }
}
pub fn diagnostics() -> String {
    EVENTS.get_or_init(|| Mutex::new(VecDeque::new())).lock()
        .map(|e| e.iter().cloned().collect::<Vec<_>>().join("\n"))
        .unwrap_or_else(|_| "Navigation diagnostics unavailable".into())
}
fn allowed(url: &Url, smoke: bool) -> bool {
    url.as_str() == "about:blank" || policy::embedded_url(url)
        || (smoke && policy::local_url(url))
}
pub fn page(url: &Url, finished: bool) {
    record(if finished { "load-finished" } else { "load-started" }, url);
}

pub fn attach_errors(app: &AppHandle, view: &Webview) -> Result<(), String> {
    let handle = app.clone();
    let label = view.label().to_owned();
    view.with_webview(move |platform| {
        let native = platform.inner();
        let failed = handle.clone();
        native.connect_load_failed(move |_, _, uri, error| {
            if error.matches(webkit2gtk::NetworkError::Cancelled) { return false; }
            if let Ok(url) = Url::parse(uri) { record("load-error", &url); }
            crate::message(&failed, "Page could not load. Use Home to retry; details are in Settings.");
            false
        });
        let terminated = handle.clone();
        native.connect_web_process_terminated(move |_, _| {
            crate::message(&terminated, "The web process stopped. Use Home to retry; details are in Settings.");
        });
        if label.starts_with(PREFIX) {
            record("popup-close-handler-attached", &Url::parse("about:blank").expect("constant"));
            native.connect_close(move |view| {
                if let Some(uri) = view.uri() { if let Ok(url) = Url::parse(&uri) { record("popup-close-request", &url); } }
                let app = handle.clone(); let label = label.clone();
                tauri::async_runtime::spawn(async move {
                    if let Some(window) = app.get_webview_window(&label) { let _ = window.destroy(); }
                });
            });
        }
    }).map_err(crate::err)
}

pub fn close_popups(app: &AppHandle) {
    for (label, window) in app.webview_windows() {
        if label.starts_with(PREFIX) { let _ = window.close(); }
    }
}

pub fn new_window(app: &AppHandle, url: Url, features: NewWindowFeatures) -> NewWindowResponse<tauri::Wry> {
    record("popup-request", &url);
    let smoke = app.state::<PreviewState>().smoke;
    if !allowed(&url, smoke) {
        if policy::external_url(&url) {
            if app.opener().open_url(url.as_str(), None::<&str>).is_err() {
                crate::message(app, "Could not open the external link in your browser.");
            }
        } else { crate::message(app, "A popup with an unsupported address was blocked."); }
        return NewWindowResponse::Deny;
    }
    if app.webview_windows().keys().filter(|key| key.starts_with(PREFIX)).count() >= 4 {
        crate::message(app, "Close an existing sign-in window before opening another.");
        return NewWindowResponse::Deny;
    }
    let data = match app.path().app_data_dir() {
        Ok(path) => path.join("webview"),
        Err(_) => { crate::message(app, "Could not open the preview's sign-in profile."); return NewWindowResponse::Deny; }
    };
    let label = format!("{PREFIX}{}", NEXT_ID.fetch_add(1, Ordering::Relaxed));
    let navigation_app = app.clone();
    let nested_app = app.clone();
    let builder = WebviewWindowBuilder::new(app, &label, WebviewUrl::External("about:blank".parse().expect("constant URL")))
        .data_directory(data)
        .window_features(features)
        .title(format!("VibeZ Preview · {}", origin(&url)))
        .inner_size(560., 760.).min_inner_size(400., 400.)
        .center().prevent_overflow().visible(true).focused(true)
        .on_permission_request(|_, _| tauri::webview::PermissionResponse::Deny)
        .on_navigation(move |next| {
            if allowed(next, smoke) { return true; }
            record("popup-navigation-blocked", next);
            crate::message(&navigation_app, crate::desktop_ui::pair(&navigation_app,
                &format!("Sign-in destination not supported: {}. No account data was copied to another browser.", origin(next)),
                &format!("Deze inlogbestemming wordt niet ondersteund: {}. Er zijn geen accountgegevens naar een andere browser gekopieerd.", origin(next))));
            false
        })
        .on_new_window(move |_, _| {
            crate::message(&nested_app, "An additional nested sign-in window was blocked.");
            NewWindowResponse::Deny
        })
        .on_page_load(|window, payload| {
            page(payload.url(), matches!(payload.event(), tauri::webview::PageLoadEvent::Finished));
            let _ = window.set_title(&format!("VibeZ Preview · {}", origin(payload.url())));
        });
    match builder.build() {
        Ok(window) => {
            // Use the returned view directly, not a timing-dependent registry lookup.
            if attach_errors(app, window.as_ref()).is_err() {
                record("popup-handler-attach-failed", &url);
                let _ = window.destroy();
                return NewWindowResponse::Deny;
            }
            crate::message(app, "Sign-in opened in a separate window. Provider restrictions may still apply.");
            NewWindowResponse::Create { window }
        },
        Err(_) => {
            record("popup-create-failed", &url);
            crate::message(app, "Could not create the sign-in window. Your Vibe page has not been replaced.");
            NewWindowResponse::Deny
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn blank_bootstrap_is_allowed_but_not_arbitrary_local_content() {
        assert!(allowed(&Url::parse("about:blank").unwrap(), false));
        assert!(allowed(&Url::parse("https://accounts.google.com/o/oauth2/v2/auth").unwrap(), false));
        for raw in ["about:srcdoc", "about:blank?token=x", "file:///etc/passwd", "data:text/html,test", "javascript:alert(1)", "tauri://localhost/settings.html", "https://accounts.google.com.evil.example/", "http://accounts.google.com/"] {
            assert!(!allowed(&Url::parse(raw).unwrap(), false), "{raw}");
        }
    }
    #[test]
    fn diagnostics_never_include_credentials_paths_queries_or_fragments() {
        let url = Url::parse("https://user:secret@v2.auth.mistral.ai/person@example.org?code=secret&state=private#token").unwrap();
        assert_eq!(origin(&url), "https://v2.auth.mistral.ai");
        assert_eq!(origin(&Url::parse("data:text/plain,secret").unwrap()), "blocked scheme");
    }
}
