//! Related OAuth and Canvas popups retain opener semantics and no native privileges.
use std::{collections::VecDeque, sync::{Arc, Mutex, OnceLock, atomic::{AtomicU64, Ordering}}};
use tauri::{AppHandle, Manager, Webview, WebviewUrl, WebviewWindowBuilder};
use tauri::webview::{NewWindowFeatures, NewWindowResponse};
use tauri_plugin_opener::OpenerExt;
use url::Url;
#[cfg(target_os = "linux")]
use gtk::prelude::WidgetExt;
#[cfg(target_os = "linux")]
use webkit2gtk::WebViewExt;
use crate::{policy, PreviewState};
const PREFIX: &str = "auth-popup-";
static NEXT_ID: AtomicU64 = AtomicU64::new(1);
static EVENTS: OnceLock<Mutex<VecDeque<String>>> = OnceLock::new();
pub fn origin(url: &Url) -> String {
    if url.as_str() == "about:blank" { return "about:blank".into(); }
    if policy::local_url(url) { return "bundled test page".into(); }
    match url.scheme() { "https" | "http" => url.origin().ascii_serialization(), _ => "blocked scheme".into() }
}
fn record(kind: &str, url: &Url) {
    let event = format!("{kind}: {}", origin(url));
    if let Ok(mut events) = EVENTS.get_or_init(|| Mutex::new(VecDeque::new())).lock() {
        if events.len() == 24 { events.pop_front(); } events.push_back(event);
    }
}
pub fn diagnostics() -> String {
    EVENTS.get_or_init(|| Mutex::new(VecDeque::new())).lock().map(|e| e.iter().cloned().collect::<Vec<_>>().join("\n"))
        .unwrap_or_else(|_| "Navigation diagnostics unavailable".into())
}
fn initial_allowed(url: &Url, smoke: bool) -> bool {
    url.as_str() == "about:blank" || policy::embedded_url(url) || (smoke && policy::local_url(url))
}
fn auth_chain_allowed(url: &Url, smoke: bool) -> bool {
    if smoke && policy::local_url(url) { return true; }
    if url.as_str() == "about:blank" { return true; }
    #[cfg(target_os = "linux")]
    if policy::embedded_internal_url(url) { return true; }
    policy::auth_chain_url(url)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum PopupPurpose {
    Authentication,
    #[cfg(target_os = "linux")]
    Pending,
    #[cfg(target_os = "linux")]
    Canvas,
}

fn opening_purpose(url: &Url, inherited: PopupPurpose) -> PopupPurpose {
    #[cfg(target_os = "linux")]
    {
        if inherited == PopupPurpose::Canvas || policy::canvas_preview_target(url) { return PopupPurpose::Canvas; }
        if url.as_str() == "about:blank" { return PopupPurpose::Pending; }
    }
    let _ = (url, inherited);
    PopupPurpose::Authentication
}

fn popup_open_allowed(url: &Url, smoke: bool, trusted_chain: bool, purpose: PopupPurpose) -> bool {
    #[cfg(target_os = "linux")]
    if purpose == PopupPurpose::Canvas { return policy::canvas_window_url(url); }
    let _ = purpose;
    if trusted_chain { auth_chain_allowed(url, smoke) } else { initial_allowed(url, smoke) }
}

fn popup_navigation_allowed(url: &Url, smoke: bool, purpose: PopupPurpose) -> bool {
    #[cfg(target_os = "linux")]
    {
        // Malformed preview targets must never inherit generic auth permission.
        if policy::canvas_preview_target(url) { return policy::embedded_canvas_url(url); }
        if purpose == PopupPurpose::Canvas { return policy::canvas_window_url(url); }
    }
    let _ = purpose;
    auth_chain_allowed(url, smoke)
}

fn navigated_purpose(url: &Url, current: PopupPurpose) -> PopupPurpose {
    #[cfg(target_os = "linux")]
    if current == PopupPurpose::Pending && !policy::embedded_internal_url(url)
        && !policy::embedded_challenge_url(url) && policy::auth_chain_url(url) {
        return if policy::embedded_canvas_url(url) { PopupPurpose::Canvas } else { PopupPurpose::Authentication };
    }
    let _ = url;
    current
}
pub fn page(url: &Url, finished: bool) { record(if finished { "load-finished" } else { "load-started" }, url); }
#[cfg(target_os = "linux")]
pub fn attach_errors(app: &AppHandle, view: &Webview) -> Result<(), String> {
    let handle = app.clone(); let label = view.label().to_owned();
    view.with_webview(move |platform| {
        let native = platform.inner(); let failed = handle.clone();
        native.connect_load_failed(move |_, _, uri, error| {
            if error.matches(webkit2gtk::NetworkError::Cancelled) { return false; }
            if let Ok(url) = Url::parse(uri) { record("load-error", &url); }
            crate::message(&failed, "Page could not load. Use Home to retry; details are in Settings."); false
        });
        let terminated = handle.clone();
        native.connect_web_process_terminated(move |_, _| { crate::message(&terminated, "The web process stopped. Use Home to retry; details are in Settings."); });
        if label.starts_with(PREFIX) {
            native.connect_destroy(move |_| {
                record("popup-native-view-destroyed", &Url::parse("about:blank").expect("constant"));
                let app = handle.clone(); let label = label.clone();
                tauri::async_runtime::spawn(async move {
                    if let Some(window) = app.get_webview_window(&label) { let _ = window.destroy(); }
                    tokio::time::sleep(std::time::Duration::from_millis(80)).await;
                    let _ = crate::native_layout::repair(&app);
                    let any_popup = app.webview_windows().keys().any(|key| key.starts_with(PREFIX));
                    if !any_popup {
                        if let Some(view) = app.get_webview("vibe") {
                            if view.url().is_ok_and(|u| policy::auth_return_url(&u)) { end(&app); }
                        }
                    }
                });
            });
        }
    }).map_err(crate::err)
}
#[cfg(target_os = "windows")]
pub fn attach_errors(app: &AppHandle, view: &Webview) -> Result<(), String> {
    if !view.label().starts_with(PREFIX) { return Ok(()); }
    let app = app.clone(); let label = view.label().to_owned();
    view.with_webview(move |platform| {
        let callback_app = app.clone();
        let callback = webview2_com::WindowCloseRequestedEventHandler::create(Box::new(move |_, _| {
            let app = callback_app.clone(); let label = label.clone();
            tauri::async_runtime::spawn(async move {
                if let Some(window) = app.get_webview_window(&label) { let _ = window.destroy(); }
                if !app.webview_windows().keys().any(|key| key.starts_with(PREFIX)) {
                    if let Some(main) = app.get_webview("vibe") {
                        if main.url().is_ok_and(|url| policy::auth_return_url(&url)) { end(&app); }
                    }
                }
            });
            Ok(())
        }));
        let result = unsafe {
            platform.controller().CoreWebView2().and_then(|view| {
                let mut token = 0; view.add_WindowCloseRequested(&callback, &mut token)
            })
        };
        if result.is_err() { crate::message(&app, "Could not attach sign-in window close handler."); }
    }).map_err(crate::err)
}
#[cfg(target_os = "macos")]
#[path = "macos_popup.rs"]
mod macos_popup;
#[cfg(target_os = "macos")]
pub fn attach_errors(app: &AppHandle, view: &Webview) -> Result<(), String> { macos_popup::attach(app, view) }
pub fn close_popups(app: &AppHandle) {
    for (label, window) in app.webview_windows() { if label.starts_with(PREFIX) { let _ = window.close(); } }
}
fn create_auth_window(app: &AppHandle, url: Url, features: NewWindowFeatures, trusted_chain: bool, inherited: PopupPurpose) -> NewWindowResponse<tauri::Wry> {
    #[cfg(target_os = "linux")]
    if policy::cloudflare_challenge_target(&url) {
        // Turnstile frames must keep their embedding context. A standalone
        // challenge popup cannot complete that flow and must not spawn tabs.
        record("challenge-popup-blocked", &url);
        return NewWindowResponse::Deny;
    }
    let purpose = opening_purpose(&url, inherited);
    record(if trusted_chain { "auth-chain-popup-request" } else { "popup-request" }, &url);
    let smoke = app.state::<PreviewState>().smoke;
    let permitted = popup_open_allowed(&url, smoke, trusted_chain, purpose);
    if !permitted {
        #[cfg(target_os = "linux")]
        if policy::canvas_preview_target(&url) { record("canvas-popup-blocked", &url); return NewWindowResponse::Deny; }
        if policy::external_url(&url) {
            if app.opener().open_url(url.as_str(), None::<&str>).is_err() { crate::message(app, "Could not open the external link in your browser."); }
        } else { crate::message(app, "A popup with an unsupported address was blocked."); }
        return NewWindowResponse::Deny;
    }
    if app.webview_windows().keys().filter(|key| key.starts_with(PREFIX)).count() >= 4 {
        crate::message(app, "Close an existing sign-in window before opening another."); return NewWindowResponse::Deny;
    }
    let data = match app.path().app_data_dir() {
        Ok(path) => path.join("webview"),
        Err(_) => { crate::message(app, "Could not open the preview's sign-in profile."); return NewWindowResponse::Deny; }
    };
    let label = format!("{PREFIX}{}", NEXT_ID.fetch_add(1, Ordering::Relaxed));
    #[cfg(not(target_os = "linux"))]
    let navigation_app = app.clone();
    let nested_app = app.clone();
    let navigation_purpose = Arc::new(Mutex::new(purpose));
    let nested_purpose = navigation_purpose.clone();
    #[cfg(target_os = "linux")]
    let native_purpose = navigation_purpose.clone();
    let builder = WebviewWindowBuilder::new(app, &label, WebviewUrl::External("about:blank".parse().expect("constant URL")))
        .data_directory(data).data_store_identifier([118,105,98,101,122,51,0,0,0,0,0,0,0,0,0,2]).window_features(features).title(format!("{} · {}", crate::title(), origin(&url)))
        .inner_size(560., 760.).min_inner_size(400., 400.).center().prevent_overflow().visible(true).focused(true)
        .on_permission_request(|_, _| tauri::webview::PermissionResponse::Deny)
        .on_navigation(move |next| {
            #[cfg(target_os = "linux")]
            { let _ = next; true }
            #[cfg(not(target_os = "linux"))]
            {
            let Ok(mut purpose) = navigation_purpose.lock() else { return false; };
            if popup_navigation_allowed(next, smoke, *purpose) {
                *purpose = navigated_purpose(next, *purpose); return true;
            }
            let current = *purpose;
            drop(purpose);
            let _ = current;
            record("popup-navigation-blocked", next); crate::message(&navigation_app, "A popup with an unsupported address was blocked."); false
            }
        })
        .on_new_window(move |next, nested_features| {
            let purpose = match nested_purpose.lock() { Ok(purpose) => *purpose, Err(_) => return NewWindowResponse::Deny };
            create_auth_window(&nested_app, next, nested_features, true, purpose)
        })
        .on_page_load(|window, payload| {
            page(payload.url(), matches!(payload.event(), tauri::webview::PageLoadEvent::Finished));
            let _ = window.set_title(&format!("{} · {}", crate::title(), origin(payload.url())));
        });
    match builder.build() {
        Ok(window) => {
            #[cfg(target_os = "linux")]
            {
                let allowed_purpose = native_purpose.clone(); let arrived_purpose = native_purpose.clone();
                let popup_purpose = native_purpose;
                if crate::linux_navigation::attach(app, window.as_ref(), move |next| {
                    allowed_purpose.lock().is_ok_and(|purpose| popup_navigation_allowed(next, smoke, *purpose))
                }, move |next| {
                    if let Ok(mut purpose) = arrived_purpose.lock() { *purpose = navigated_purpose(next, *purpose); }
                }, move |next| {
                    popup_purpose.lock().is_ok_and(|purpose| {
                        let purpose = opening_purpose(next, *purpose);
                        !policy::cloudflare_challenge_target(next) && popup_open_allowed(next, smoke, true, purpose)
                    })
                }, false).is_err() {
                    record("popup-routing-attach-failed", &url); let _ = window.destroy(); return NewWindowResponse::Deny;
                }
            }
            if attach_errors(app, window.as_ref()).is_err() {
                record("popup-handler-attach-failed", &url); let _ = window.destroy(); return NewWindowResponse::Deny;
            }
            #[cfg(target_os = "linux")]
            if purpose == PopupPurpose::Canvas { crate::message(app, "Preview opened in a separate window."); }
            else { crate::message(app, "Sign-in opened in a separate window. Provider restrictions may still apply."); }
            #[cfg(not(target_os = "linux"))]
            crate::message(app, "Sign-in opened in a separate window. Provider restrictions may still apply.");
            NewWindowResponse::Create { window }
        },
        Err(_) => { record("popup-create-failed", &url); crate::message(app, "Could not create the sign-in window. Your Vibe page has not been replaced."); NewWindowResponse::Deny },
    }
}
pub fn begin(app: &AppHandle) {
    let state = app.state::<PreviewState>();
    let mut started = state.auth_started.lock().expect("auth timer");
    if started.is_none() { *started = Some(std::time::Instant::now()); }
    state.auth_active.store(true, Ordering::SeqCst);
}
pub fn end(app: &AppHandle) {
    let state = app.state::<PreviewState>();
    if let Ok(mut started) = state.auth_started.lock() { *started = None; }
    state.auth_active.store(false, Ordering::SeqCst);
}
pub fn active(app: &AppHandle) -> bool {
    let state = app.state::<PreviewState>();
    if !state.auth_active.load(Ordering::SeqCst) { return false; }
    let expired = state.auth_started.lock().map(|s| s.is_none_or(|t| t.elapsed() > std::time::Duration::from_secs(600))).unwrap_or(true);
    if expired { end(app); return false; } true
}
#[cfg(target_os = "linux")]
pub fn main_popup_allowed(app: &AppHandle, url: &Url) -> bool {
    if policy::cloudflare_challenge_target(url) { return false; }
    let smoke = app.state::<PreviewState>().smoke;
    let purpose = opening_purpose(url, PopupPurpose::Authentication);
    popup_open_allowed(url, smoke, (policy::auth_entry_url(url) || active(app)) && auth_chain_allowed(url, smoke), purpose)
}
pub fn new_window(app: &AppHandle, url: Url, features: NewWindowFeatures) -> NewWindowResponse<tauri::Wry> {
    let state = app.state::<PreviewState>();
    #[cfg(not(target_os = "linux"))]
    if policy::auth_entry_url(&url) { begin(app); crate::link_trace::record("auth-mode-start-popup", &url); }
    // Linux popups have their own auth policy. A popup may originate inside an
    // untrusted iframe, so it must not enable generic HTTPS in the main view.
    #[cfg(target_os = "linux")]
    let trusted_chain = (policy::auth_entry_url(&url) || active(app)) && auth_chain_allowed(&url, state.smoke);
    #[cfg(not(target_os = "linux"))]
    let trusted_chain = active(app) && auth_chain_allowed(&url, state.smoke);
    create_auth_window(app, url, features, trusted_chain, PopupPurpose::Authentication)
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn blank_bootstrap_is_allowed_but_not_arbitrary_local_content() {
        assert!(initial_allowed(&Url::parse("about:blank").unwrap(), false));
        assert!(initial_allowed(&Url::parse("https://accounts.google.com/o/oauth2/v2/auth").unwrap(), false));
        for raw in ["about:srcdoc", "about:blank?token=x", "file:///etc/passwd", "data:text/html,test", "javascript:alert(1)", "tauri://localhost/settings.html", "https://accounts.google.com.evil.example/", "http://accounts.google.com/"] {
            assert!(!initial_allowed(&Url::parse(raw).unwrap(), false), "{raw}");
        }
    }
    #[test] fn trusted_auth_chain_can_follow_https_redirects_without_native_privileges() {
        for raw in ["https://accounts.google.com/signin/oauth/consent", "https://www.google.com/", "https://accounts.youtube.com/", "https://example.identity-provider.test/callback"] {
            assert!(auth_chain_allowed(&Url::parse(raw).unwrap(), false), "{raw}");
        }
        for raw in ["http://accounts.google.com/", "file:///etc/passwd", "javascript:alert(1)", "data:text/html,test", "https://user:secret@example.com/"] {
            assert!(!auth_chain_allowed(&Url::parse(raw).unwrap(), false), "{raw}");
        }
    }
    #[cfg(target_os = "linux")]
    #[test] fn pending_popup_classifies_once_without_reclassifying_auth_subframes() {
        let canvas = Url::parse("https://canvas.mistralusercontent.com/chart").unwrap();
        let provider = Url::parse("https://accounts.google.com/signin").unwrap();
        let blank = Url::parse("about:blank").unwrap();
        let challenge = Url::parse("https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/g/normal").unwrap();
        assert_eq!(opening_purpose(&canvas, PopupPurpose::Authentication), PopupPurpose::Canvas);
        assert_eq!(opening_purpose(&blank, PopupPurpose::Authentication), PopupPurpose::Pending);
        assert_eq!(navigated_purpose(&blank, PopupPurpose::Pending), PopupPurpose::Pending);
        let pending = navigated_purpose(&challenge, PopupPurpose::Pending);
        assert_eq!(pending, PopupPurpose::Pending);
        assert_eq!(navigated_purpose(&canvas, pending), PopupPurpose::Canvas);
        assert_eq!(navigated_purpose(&provider, pending), PopupPurpose::Authentication);
        assert_eq!(navigated_purpose(&canvas, PopupPurpose::Pending), PopupPurpose::Canvas);
        assert_eq!(navigated_purpose(&provider, PopupPurpose::Pending), PopupPurpose::Authentication);
        // The callback also sees subframes: an actual auth popup must keep its redirect policy.
        assert_eq!(navigated_purpose(&canvas, PopupPurpose::Authentication), PopupPurpose::Authentication);
        assert_eq!(navigated_purpose(&challenge, PopupPurpose::Authentication), PopupPurpose::Authentication);
        assert!(popup_navigation_allowed(&provider, false, PopupPurpose::Authentication));
    }
    #[cfg(target_os = "linux")]
    #[test] fn canvas_related_popups_cannot_inherit_generic_auth_redirect_permission() {
        for raw in ["https://canvas.mistralusercontent.com/chart", "about:blank", "https://chat.mistral.ai/chat/1"] {
            let url = Url::parse(raw).unwrap();
            assert_eq!(opening_purpose(&url, PopupPurpose::Canvas), PopupPurpose::Canvas);
            assert!(popup_open_allowed(&url, false, true, PopupPurpose::Canvas));
            assert!(popup_navigation_allowed(&url, false, PopupPurpose::Canvas));
        }
        for raw in ["https://accounts.google.com/signin", "https://example.com/", "https://other.mistralusercontent.com/", "http://canvas.mistralusercontent.com/", "https://canvas.mistralusercontent.com:444/", "https://user:secret@canvas.mistralusercontent.com/"] {
            let url = Url::parse(raw).unwrap();
            assert!(!popup_open_allowed(&url, false, true, PopupPurpose::Canvas), "{raw}");
            assert!(!popup_navigation_allowed(&url, false, PopupPurpose::Canvas), "{raw}");
        }
        // Unsafe canvas targets stay blocked even while a real auth chain is active.
        let invalid = Url::parse("https://canvas.mistralusercontent.com:444/").unwrap();
        assert!(!popup_navigation_allowed(&invalid, false, PopupPurpose::Authentication));
    }
    #[cfg(target_os = "linux")]
    #[test] fn embedded_internal_and_challenge_frames_work_in_existing_popups() {
        for raw in ["about:blank", "about:srcdoc", "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/g/normal"] {
            let url = Url::parse(raw).unwrap();
            for purpose in [PopupPurpose::Pending, PopupPurpose::Authentication, PopupPurpose::Canvas] {
                assert!(popup_navigation_allowed(&url, false, purpose), "{raw}: {purpose:?}");
            }
        }
        for raw in ["about:config", "about:srcdoc#x", "data:text/html,test", "file:///etc/passwd"] {
            for purpose in [PopupPurpose::Pending, PopupPurpose::Authentication, PopupPurpose::Canvas] {
                assert!(!popup_navigation_allowed(&Url::parse(raw).unwrap(), false, purpose));
            }
        }
    }
    #[test] fn diagnostics_never_include_credentials_paths_queries_or_fragments() {
        let url = Url::parse("https://user:secret@v2.auth.mistral.ai/person@example.org?code=secret&state=private#token").unwrap();
        assert_eq!(origin(&url), "https://v2.auth.mistral.ai");
        assert_eq!(origin(&Url::parse("data:text/plain,secret").unwrap()), "blocked scheme");
    }
}
