//! Serialized language transactions. Bootstrap before remote navigation;
//! later changes wait for loaded Vibe/Chat content, never an OAuth page.
use crate::{err, os_locale, policy, PreviewState};
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
}
impl Default for LanguageState {
    fn default() -> Self {
        Self { gate: tokio::sync::Mutex::new(()), generation: AtomicU64::new(0),
            completed: AtomicU64::new(0), bootstrap: AtomicBool::new(true),
            loading: AtomicBool::new(true), last_error: Mutex::new(String::new()) }
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
async fn apply(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<PreviewState>();
    let flow = &state.site_language;
    let _gate = flow.gate.lock().await;
    if flow.generation.load(Ordering::SeqCst) == flow.completed.load(Ordering::SeqCst) { return Ok(()); }
    let generation = flow.generation.load(Ordering::SeqCst);
    let selected = state.settings.lock().map_err(err)?.language.clone();
    let locale = policy::mistral_site_locale(&selected, &os_locale());
    let view = app.get_webview("vibe").ok_or("Vibe view is not ready")?;
    preferred(&view, &locale).await?;
    cookies(&view, &locale)?;
    confirm(&view, &locale).await?;
    if generation != flow.generation.load(Ordering::SeqCst) { return Ok(()); }
    *flow.last_error.lock().map_err(err)? = String::new();
    let current = view.url().map_err(err)?;
    let first = flow.bootstrap.load(Ordering::SeqCst);
    if first || can_reload(&current, crate::auth::active(app), flow.loading.load(Ordering::SeqCst)) {
        // Complete only this generation. Newer requests remain pending.
        flow.completed.store(generation, Ordering::SeqCst);
        flow.bootstrap.store(false, Ordering::SeqCst);
        let target = if first { policy::HOME.parse().map_err(err)? } else { current };
        view.navigate(target).map_err(err)?;
    }
    Ok(())
}
fn start(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        if let Err(error) = apply(&app).await {
            let state = app.state::<PreviewState>();
            if let Ok(mut detail) = state.site_language.last_error.lock() { *detail = error; }
            crate::message(&app, "site_language_failed");
            // Never strand the user on about:blank when a preference fails.
            if state.site_language.bootstrap.swap(false, Ordering::SeqCst) {
                if let Some(view) = app.get_webview("vibe") { let _ = view.navigate(policy::HOME.parse().expect("constant")); }
            }
        }
    });
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
    format!("requested={requested}; pending={pending}; {page}; error={failure}")
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
}
