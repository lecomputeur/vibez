//! Serialized language transactions. Bootstrap before remote navigation;
//! later changes wait for loaded Vibe/Chat content, never an OAuth page.
use crate::{err, os_locale, policy, PreviewState};
#[path = "language_retry.rs"]
mod retry;
use std::collections::VecDeque;
use std::sync::{atomic::{AtomicBool, AtomicU64, Ordering}, Mutex};
use tauri::{AppHandle, Manager, Webview};
use tauri::webview::Cookie;
#[cfg(target_os = "linux")]
use webkit2gtk::{WebContextExt, WebViewExt};

pub struct LanguageState {
    gate: tokio::sync::Mutex<()>,
    generation: AtomicU64,
    completed: AtomicU64,
    pub bootstrap: AtomicBool,
    pub loading: AtomicBool,
    last_error: Mutex<String>,
    history: Mutex<VecDeque<String>>,
}
impl Default for LanguageState {
    fn default() -> Self {
        Self { gate: tokio::sync::Mutex::new(()), generation: AtomicU64::new(0),
            completed: AtomicU64::new(0), bootstrap: AtomicBool::new(true),
            loading: AtomicBool::new(true), last_error: Mutex::new(String::new()),
            history: Mutex::new(VecDeque::new()) }
    }
}
#[cfg(target_os = "linux")]
async fn preferred(view: &Webview, locale: &str) -> Result<(), String> {
    let locale = locale.to_owned();
    let (tx, rx) = tokio::sync::oneshot::channel();
    view.with_webview(move |p| {
        let ok = if let Some(context) = p.inner().context() {
            context.set_preferred_languages(&[locale.as_str()]); true
        } else { false };
        let _ = tx.send(ok);
    }).map_err(err)?;
    match tokio::time::timeout(std::time::Duration::from_secs(3), rx).await {
        Ok(Ok(true)) => Ok(()), _ => Err("Browser language context is unavailable".into()),
    }
}
#[cfg(target_os = "windows")]
async fn preferred(_view: &Webview, _locale: &str) -> Result<(), String> { Ok(()) }
fn cookies(view: &Webview, locale: &str) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    for host in ["https://chat.mistral.ai/", "https://vibe.mistral.ai/"] {
        for cookie in view.cookies_for_url(host.parse().map_err(err)?).map_err(err)? {
            if cookie.name() == "NEXT_LOCALE" { view.delete_cookie(cookie).map_err(err)?; }
        }
    }
    for domain in ["chat.mistral.ai", ".chat.mistral.ai", "vibe.mistral.ai", ".vibe.mistral.ai", "mistral.ai", ".mistral.ai"] {
        let stale = Cookie::build(("NEXT_LOCALE", "")).domain(domain).path("/").secure(true).build();
        let _ = view.delete_cookie(stale);
    }
    for domain in ["chat.mistral.ai", "vibe.mistral.ai", ".mistral.ai"] {
        let cookie = Cookie::build(("NEXT_LOCALE", locale.to_owned())).domain(domain).path("/").secure(true)
            .same_site(tauri::webview::cookie::SameSite::Lax).build();
        view.set_cookie(cookie).map_err(err)?;
    }
    Ok(())
}
#[cfg(target_os = "linux")]
async fn confirm(view: &Webview, locale: &str) -> Result<(), String> {
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
    loop {
        let values = view.cookies_for_url("https://chat.mistral.ai/".parse().map_err(err)?).map_err(err)?;
        let values: Vec<_> = values.iter().filter(|c| c.name() == "NEXT_LOCALE").collect();
        if !values.is_empty() && values.iter().all(|c| c.value() == locale) { return Ok(()); }
        if std::time::Instant::now() >= deadline { return Err("Browser language cookie was not confirmed".into()); }
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    }
}
#[cfg(target_os = "windows")]
async fn confirm(_view: &Webview, _locale: &str) -> Result<(), String> { Ok(()) }
fn can_reload(url: &url::Url, authenticating: bool, loading: bool) -> bool {
    policy::auth_return_url(url) && !authenticating && !loading
}
// A newly created WebKit view can temporarily report an empty URI. The
// bootstrap target is known; asking Webview::url() here would turn a successful
// language preparation into "relative URL without a base" on cold start.
fn navigation_target(first: bool, authenticating: bool, loading: bool,
    current: impl FnOnce() -> Result<url::Url, String>) -> Result<Option<url::Url>, String> {
    if authenticating { return Ok(None); }
    if first { return policy::HOME.parse().map(Some).map_err(err); }
    let url = current()?;
    Ok(if can_reload(&url, false, loading) { Some(url) } else { None })
}
fn remember(flow: &LanguageState, generation: u64, attempt: usize, detail: &str) {
    // Only operation errors, never cookie values, auth URLs or account tokens.
    let detail: String = detail.chars().map(|c| if c.is_control() { ' ' } else { c }).take(240).collect();
    if let Ok(mut history) = flow.history.lock() {
        if history.len() >= 8 { history.pop_front(); }
        history.push_back(format!("request={generation}; attempt={attempt}; {detail}"));
    }
}
fn recovered(app: &AppHandle) {
    let state = app.state::<PreviewState>();
    if let Ok(mut detail) = state.site_language.last_error.lock() { detail.clear(); }
    // Do not erase a newer screenshot, connection or settings message.
    if let Ok(mut status) = state.status.lock() { status.clear_if("site_language_failed"); };
}
async fn prepare_view(view: &Webview, locale: &str) -> Result<(), String> {
    preferred(view, locale).await.map_err(|e| format!("preferred-language: {e}"))?;
    cookies(view, locale).map_err(|e| format!("cookie-write: {e}"))?;
    confirm(view, locale).await.map_err(|e| format!("cookie-confirmation: {e}"))
}
async fn apply(app: &AppHandle) {
    let state = app.state::<PreviewState>();
    let flow = &state.site_language;
    // Keep reporting inside the same gate as preparation and navigation.
    let _gate = flow.gate.lock().await;
    let generation = flow.generation.load(Ordering::SeqCst);
    if generation == flow.completed.load(Ordering::SeqCst) { return; }
    let current = || generation == flow.generation.load(Ordering::SeqCst);
    let result: Result<bool, String> = async {
        let selected = state.settings.lock().map_err(err)?.language.clone();
        let locale = policy::mistral_site_locale(&selected, &os_locale());
        let view = app.get_webview("vibe").ok_or("Vibe view is not ready")?;
        // A cold browser profile may not yet have its cookie store ready.
        // Retrying is bounded; genuine failures still reach the user.
        let prepared = retry::prepare(|| prepare_view(&view, &locale), current,
            |attempt, error| remember(flow, generation, attempt, error),
            std::time::Duration::from_millis(250)).await?;
        if prepared == retry::Outcome::Superseded { return Ok(false); }
        let first = flow.bootstrap.load(Ordering::SeqCst);
        let target = navigation_target(first, crate::auth::active(app),
            flow.loading.load(Ordering::SeqCst), || view.url().map_err(err))?;
        if let Some(target) = target {
            if !current() { return Ok(false); }
            // Do not mark a generation complete if navigation submission fails.
            view.navigate(target).map_err(err)?;
            flow.completed.store(generation, Ordering::SeqCst);
            flow.bootstrap.store(false, Ordering::SeqCst);
            return Ok(true);
        }
        Ok(false) // Still pending: an auth/loading page must not be redirected.
    }.await;
    if !current() { return; }
    match result {
        Ok(true) => recovered(app),
        Ok(false) => (),
        Err(error) => {
            remember(flow, generation, 0, &error);
            if let Ok(mut detail) = flow.last_error.lock() { *detail = error; }
            crate::message(app, "site_language_failed");
            // Never strand the user on about:blank. A later successful page
            // load retries the pending request and clears only our warning.
            if flow.bootstrap.swap(false, Ordering::SeqCst) {
                if let Some(view) = app.get_webview("vibe") {
                    let _ = view.navigate(policy::HOME.parse().expect("constant"));
                }
            }
        }
    }
}
fn start(app: AppHandle) {
    tauri::async_runtime::spawn(async move { apply(&app).await; });
}
pub fn request(app: &AppHandle) {
    let state = app.state::<PreviewState>();
    if state.smoke { return; }
    state.site_language.generation.fetch_add(1, Ordering::SeqCst);
    start(app.clone());
}
pub fn loaded(app: &AppHandle, url: &url::Url, finished: bool) {
    let state = app.state::<PreviewState>();
    state.site_language.loading.store(!finished, Ordering::SeqCst);
    let pending = state.site_language.generation.load(Ordering::SeqCst) != state.site_language.completed.load(Ordering::SeqCst);
    if finished && policy::auth_return_url(url) && pending && !state.smoke { start(app.clone()); }
}
pub async fn inspect(app: &AppHandle) -> String {
    let state = app.state::<PreviewState>();
    let requested = state.settings.lock().map(|s| policy::mistral_site_locale(&s.language, &os_locale())).unwrap_or_default();
    let pending = state.site_language.generation.load(Ordering::SeqCst) != state.site_language.completed.load(Ordering::SeqCst);
    let failure = state.site_language.last_error.lock().map(|s| s.clone()).unwrap_or_default();
    let Some(view) = app.get_webview("vibe") else { return "page=unavailable".into() };
    let (tx, rx) = tokio::sync::oneshot::channel();
    let tx = std::sync::Arc::new(Mutex::new(Some(tx)));
    let _ = view.eval_with_callback(include_str!("site_diagnostics.js"), move |result| {
        if let Ok(mut slot) = tx.lock() { if let Some(tx) = slot.take() { let _ = tx.send(result); } }
    });
    let page = match tokio::time::timeout(std::time::Duration::from_secs(3), rx).await {
        Ok(Ok(raw)) => serde_json::from_str::<String>(&raw).unwrap_or_else(|_| "page=unavailable".into()),
        _ => "page=unavailable".into(),
    };
    let history = state.site_language.history.lock()
        .map(|h| h.iter().cloned().collect::<Vec<_>>().join("\n"))
        .unwrap_or_else(|_| "unavailable".into());
    format!("requested={requested}; pending={pending}; {page}; error={failure}\nLanguage preparation history (including recovered attempts):\n{history}")
}
#[cfg(target_os = "linux")]
pub async fn smoke_check(app: &AppHandle) -> Result<(), String> {
    if !app.state::<PreviewState>().smoke { return Err("Language probe requires smoke mode".into()); }
    let window = tauri::WebviewWindowBuilder::new(app, "language-smoke",
            tauri::WebviewUrl::External("about:blank".parse().map_err(err)?))
        .data_directory(app.path().app_data_dir().map_err(err)?.join("language-smoke"))
        .visible(false)
        .on_navigation(|u| u.as_str() == "about:blank")
        .on_new_window(|_, _| tauri::webview::NewWindowResponse::Deny)
        .on_permission_request(|_, _| tauri::webview::PermissionResponse::Deny)
        .build().map_err(|e| format!("bootstrap-probe/create: {e}"))?;
    let result: Result<(), String> = async {
        let view: &Webview = window.as_ref();
        for locale in ["nl", "en", "nl"] {
            let outcome = retry::prepare(|| prepare_view(view, locale), || true,
                |attempt, error| eprintln!("LANGUAGE_PROBE_RETRY: attempt={attempt}; {error}"),
                std::time::Duration::from_millis(250)).await?;
            if outcome != retry::Outcome::Ready { return Err("Language probe unexpectedly superseded".into()); }
            // Inspect the native URI without parsing it: an empty URI is a
            // valid not-yet-committed bootstrap state, not a remote navigation.
            let (tx, rx) = tokio::sync::oneshot::channel();
            view.with_webview(move |p| {
                let _ = tx.send(p.inner().uri().map(|u| u.to_string()).unwrap_or_default());
            }).map_err(err)?;
            let uri = tokio::time::timeout(std::time::Duration::from_secs(3), rx)
                .await.map_err(err)?.map_err(err)?;
            if !uri.is_empty() && uri != "about:blank" { return Err("Language probe navigated remotely".into()); }
        }
        println!("LANGUAGE_BOOTSTRAP_OK: real WebKit cookie preparation on a fresh about:blank profile; nl/en/nl; no remote navigation");
        Ok(())
    }.await;
    let cleanup = window.destroy().map_err(err);
    result.and(cleanup)
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn language_never_navigates_an_auth_or_loading_page() {
        for u in ["https://accounts.google.com/", "https://login.microsoftonline.com/", "https://v2.auth.mistral.ai/", "about:blank"] {
            assert!(!can_reload(&u.parse().unwrap(), false, false));
        }
        let url = "https://chat.mistral.ai/chat/example".parse().unwrap();
        assert!(!can_reload(&url, true, false)); assert!(!can_reload(&url, false, true));
        assert!(can_reload(&url, false, false));
    }
    #[test] fn cold_bootstrap_does_not_parse_unavailable_uri() {
        let target = navigation_target(true, false, true,
            || panic!("cold WebKit URI must not be queried")).unwrap().unwrap();
        assert_eq!(target.as_str(), policy::HOME);
    }
    #[test] fn bootstrap_never_redirects_active_authentication() {
        assert!(navigation_target(true, true, false,
            || panic!("auth location must not be queried")).unwrap().is_none());
    }
    #[test] fn non_bootstrap_respects_loaded_content_and_reports_real_url_errors() {
        let u = || Ok("https://chat.mistral.ai/chat/example".parse().unwrap());
        assert!(navigation_target(false, false, true, u).unwrap().is_none());
        assert_eq!(navigation_target(false, false, false, u).unwrap().unwrap(), u().unwrap());
        assert!(navigation_target(false, false, false,
            || Err("missing runtime URL".into())).is_err());
    }

}
