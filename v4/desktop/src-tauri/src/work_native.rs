//! Runs only the official Work connector form in a restricted child of the app.
use super::*;
use std::time::Duration;
use tauri::{LogicalPosition, LogicalSize};

const TIMEOUT: Duration = Duration::from_secs(50);
const POLL_INTERVAL: Duration = Duration::from_millis(300);
/// Connectors reconnected in the hidden view whose chat page has not been loaded afresh yet.
static RECONNECTED: std::sync::Mutex<std::collections::BTreeSet<String>> = std::sync::Mutex::new(std::collections::BTreeSet::new());
const STAGES: &[(&str, &str)] = &[
    ("open-menu", "advanced"),
    ("open-form", "advanced"),
    ("title", "advanced"),
    ("endpoint", "advanced"),
    ("description", "advanced"),
    ("auth", "advanced"),
    ("submit", "submitted"),
    ("detail", "detail"),
];

#[derive(Default)]
pub(super) struct SetupState(Mutex<Option<Active>>);
struct Active {
    id: String,
    project: String,
    cancelled: bool,
}

struct Lease {
    app: tauri::AppHandle,
    id: String,
}
impl Drop for Lease {
    fn drop(&mut self) {
        if let Ok(mut active) = self.app.state::<SetupState>().0.lock() {
            if active.as_ref().is_some_and(|active| active.id == self.id) {
                *active = None;
            }
        }
    }
}

struct SetupView(Webview);
impl Drop for SetupView {
    fn drop(&mut self) {
        let _ = self.0.close();
    }
}

struct Request {
    id: String,
    project: String,
    binding: String,
    endpoint: String,
    // Still validated as part of the request; the secret address replaces its use.
    #[allow(dead_code)]
    token: String,
    title: String,
    description: String,
    slug: String,
}

struct Attachment {
    id: String,
    project: String,
    binding: String,
    connector_id: String,
    name: String,
    marker: String,
    token: String,
}

impl Attachment {
    fn parse(event: &Value) -> Option<Self> {
        let id = event["job_id"].as_str().filter(|v| hex(v, 32))?;
        let project = event["project_id"].as_str().filter(|v| project_id(v))?;
        let binding = event["binding"].as_str().filter(|v| hex(v, 64))?;
        let connector_id = event["connector_id"].as_str().filter(|v| uuid(v))?;
        let name = event["connector_name"].as_str()?;
        let (slug, suffix) = name.split_once('_')?;
        if !slug.strip_prefix("vibezwork").is_some_and(|v| hex(v, 16))
            || !(4..=12).contains(&suffix.len())
            || !suffix
                .bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        {
            return None;
        }
        let marker = event["marker"].as_str()?;
        let installation = marker.strip_prefix("[VibeZ-work:")?.split(':').next()?;
        if !hex(installation, 32)
            || marker != format!("[VibeZ-work:{installation}:{project}:{slug}]")
        {
            return None;
        }
        let token = event["token"].as_str().filter(|v| valid_token(v))?;
        Some(Self {
            id: id.into(),
            project: project.into(),
            binding: binding.into(),
            connector_id: connector_id.into(),
            name: name.into(),
            marker: marker.into(),
            token: token.into(),
        })
    }
}

fn valid_token(value: &str) -> bool {
    (50..=85).contains(&value.len())
        && value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, b'_' | b'-'))
}

fn current(app: &tauri::AppHandle, job: &str, project: &str, binding: &str) -> bool {
    app.state::<SetupState>().0.lock().is_ok_and(|active| {
        active
            .as_ref()
            .is_some_and(|active| active.id == job && !active.cancelled)
    }) && official_web::work_setup_current(app, project, binding)
}

fn hex(value: &str, len: usize) -> bool {
    value.len() == len
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

fn uuid(value: &str) -> bool {
    official_web::projects::valid_id(value) && !value.bytes().any(|c| c.is_ascii_uppercase())
}

fn project_id(value: &str) -> bool {
    uuid(value.strip_prefix("chat-").unwrap_or(value))
}

fn endpoint_matches(raw: &str, project: &str) -> bool {
    let Ok(url) = raw.parse::<url::Url>() else {
        return false;
    };
    let label = url
        .host_str()
        .and_then(|host| host.strip_suffix(".trycloudflare.com"))
        .unwrap_or("");
    safe_https(&url)
        && !label.is_empty()
        && label.len() <= 63
        && label
            .bytes()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-')
        && secret_path(url.path(), project)
        && url.query().is_none()
        && url.fragment().is_none()
        && raw == url.as_str()
}

/// `/mcp/<project>` or the secret project address `/mcp/<project>/<key>`.
fn secret_path(path: &str, project: &str) -> bool {
    let Some(rest) = path.strip_prefix(&format!("/mcp/{project}")) else {
        return false;
    };
    rest.is_empty()
        || rest.strip_prefix('/').is_some_and(|secret| {
            (43..=86).contains(&secret.len())
                && secret
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || matches!(c, b'_' | b'-'))
        })
}

impl Request {
    fn parse(event: &Value) -> Option<Self> {
        let id = event["job_id"].as_str().filter(|value| hex(value, 32))?;
        let project = event["project_id"]
            .as_str()
            .filter(|value| project_id(value))?;
        let binding = event["binding"].as_str().filter(|value| hex(value, 64))?;
        let endpoint = event["endpoint"]
            .as_str()
            .filter(|value| endpoint_matches(value, project))?;
        let slug = event["slug_prefix"].as_str().filter(|value| {
            value
                .strip_prefix("vibezwork")
                .is_some_and(|suffix| hex(suffix, 16))
        })?;
        let title = event["title"].as_str().filter(|value| *value == slug)?;
        let description = event["description"].as_str().filter(|value| {
            !value.is_empty()
                && value.chars().count() <= 600
                && !value.chars().any(char::is_control)
        })?;
        let token = event["token"].as_str().filter(|value| valid_token(value))?;
        Some(Self {
            id: id.into(),
            project: project.into(),
            binding: binding.into(),
            endpoint: endpoint.into(),
            token: token.into(),
            title: title.into(),
            description: description.into(),
            slug: slug.into(),
        })
    }

    fn current(&self, app: &tauri::AppHandle) -> bool {
        current(app, &self.id, &self.project, &self.binding)
    }
}

fn detail_path(path: &str, slug: &str) -> bool {
    let Some(name) = path.strip_prefix("/connections/") else {
        return false;
    };
    if name == slug {
        return true;
    }
    let Some(suffix) = name
        .strip_prefix(slug)
        .and_then(|rest| rest.strip_prefix('_'))
    else {
        return false;
    };
    (4..=12).contains(&suffix.len())
        && suffix
            .bytes()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
}

fn sign_in_route(url: &url::Url) -> bool {
    ["/auth", "/login", "/signin", "/sign-in"]
        .iter()
        .any(|path| {
            url.path() == *path
                || url
                    .path()
                    .strip_prefix(*path)
                    .is_some_and(|rest| rest.starts_with('/'))
        })
}

fn permitted_url(url: &url::Url, origin: &url::Origin, slug: &str) -> bool {
    if url.as_str() == "about:blank" {
        return true;
    }
    if !safe_https(url) || &url.origin() != origin {
        return false;
    }
    if sign_in_route(url) {
        return true;
    }
    if url.query().is_none()
        && url.fragment().is_none()
        && (url.path() == "/connections" || detail_path(url.path(), slug))
    {
        return true;
    }
    false
}

fn build_view(
    app: &tauri::AppHandle,
    job_id: &str,
    slug: &str,
    target: &url::Url,
    #[cfg(target_os = "linux")] related: webkit2gtk::WebView,
) -> Result<SetupView, &'static str> {
    let window = app.get_window("main").ok_or("work_setup_failed")?;
    let size = window
        .inner_size()
        .map_err(|_| "work_setup_failed")?
        .to_logical::<f64>(window.scale_factor().map_err(|_| "work_setup_failed")?);
    let origin = target.origin();
    let slug = slug.to_owned();
    let directory = app
        .path()
        .app_data_dir()
        .map_err(|_| "work_setup_failed")?
        .join("webview");
    let builder = tauri::webview::WebviewBuilder::new(
        format!("mistral-connector-setup-{job_id}"),
        WebviewUrl::External("about:blank".parse().unwrap()),
    )
    .data_directory(directory)
    .focused(false)
    .disable_drag_drop_handler()
    .on_navigation(move |url| permitted_url(url, &origin, &slug))
    .on_permission_request(|_, _| tauri::webview::PermissionResponse::Deny)
    .on_new_window(|_, _| tauri::webview::NewWindowResponse::Deny);
    #[cfg(target_os = "linux")]
    let builder = builder.with_related_view(related);
    let view = SetupView(
        window
            .add_child(
                builder,
                LogicalPosition::new(0., 54.),
                LogicalSize::new(size.width.max(1.), (size.height - 54.).max(1.)),
            )
            .map_err(|_| "work_setup_failed")?,
    );
    view.0.hide().map_err(|_| "work_setup_failed")?;
    view.0
        .navigate(target.clone())
        .map_err(|_| "work_setup_failed")?;
    Ok(view)
}

async fn make_view(
    app: &tauri::AppHandle,
    job_id: &str,
    slug: &str,
    target: &url::Url,
    _main: &Webview,
) -> Result<SetupView, &'static str> {
    #[cfg(target_os = "linux")]
    {
        let (send, receive) = tokio::sync::oneshot::channel();
        let app = app.clone();
        let job_id = job_id.to_owned();
        let slug = slug.to_owned();
        let target = target.clone();
        // WebKitGTK's related view uses the exact Work process and session.
        _main
            .with_webview(move |platform| {
                let view = build_view(&app, &job_id, &slug, &target, platform.inner().clone());
                let _ = send.send(view);
            })
            .map_err(|_| "work_setup_failed")?;
        tokio::time::timeout(Duration::from_secs(5), receive)
            .await
            .map_err(|_| "work_setup_failed")?
            .map_err(|_| "work_setup_failed")?
    }
    #[cfg(not(target_os = "linux"))]
    build_view(app, job_id, slug, target)
}

async fn enroll(
    app: &tauri::AppHandle,
    request: &Request,
    trace: &mut Value,
) -> Result<String, &'static str> {
    if !request.current(app) {
        return Err("work_setup_failed");
    }
    let main = app.get_webview("mistral-web").ok_or("sign_in")?;
    let mut target = main.url().map_err(|_| "sign_in")?;
    if !official_web::projects::origin(&target) {
        return Err("sign_in");
    }
    target.set_path("/connections");
    target.set_query(None);
    target.set_fragment(None);
    let origin = target.origin();
    let started = tokio::time::Instant::now();
    let view = make_view(app, &request.id, &request.slug, &target, &main).await?;
    note(trace, started, "view");
    let deadline = tokio::time::Instant::now() + TIMEOUT;
    let mut page_seen = false;

    for (stage, expected) in STAGES {
        trace["stage"] = json!(stage);
        trace["state"] = json!("pending");
        let mut last_reason = String::new();
        let mut navigated = false;
        let stage_started = tokio::time::Instant::now();
        #[cfg(feature = "native-smoke")]
        if std::env::var_os("VIBEZ4_CODE_PROBE_DIR").is_some() {
            eprintln!("Work probe stage: {stage}");
        }
        loop {
            if !request.current(app) || tokio::time::Instant::now() >= deadline {
                trace["state"] = json!(if request.current(app) { "timeout" } else { "scope-changed" });
                return Err("work_setup_failed");
            }
            let url = view.0.url().map_err(|_| "work_setup_failed")?;
            if url.as_str() == "about:blank" {
                tokio::time::sleep(POLL_INTERVAL).await;
                continue;
            }
            if !page_seen {
                page_seen = true;
                note(trace, started, "page");
            }
            if *stage == "detail" && !navigated && url.path() != "/connections" {
                navigated = true;
                note(trace, started, "navigated");
            }
            if *stage == "detail" && !navigated && stage_started.elapsed() >= Duration::from_secs(12) {
                // Measured live: Mistral had made the connector 5 s after Save
                // but its form stayed open for the remaining 41 s. Stop here;
                // the engine finds the new connector itself, without a second Save.
                #[cfg(feature = "native-smoke")]
                dump(&view.0, "enroll-stuck").await;
                note(trace, started, "form-stuck");
                trace["state"] = json!("timeout");
                trace["reason"] = json!("form-stuck");
                return Err("work_setup_failed");
            }
            if !permitted_url(&url, &origin, &request.slug) {
                return Err("work_setup_failed");
            }
            if sign_in_route(&url) {
                return Err("sign_in");
            }
            let payload = json!({
                "origin": origin.ascii_serialization(), "stage": stage, "title": request.title,
                "slugPrefix": request.slug, "description": request.description,
                "endpoint": request.endpoint,
            });
            // The secret project address needs no key in Mistral's form.
            let script = format!(
                "JSON.stringify(({})({payload}))",
                include_str!("work_native_wizard.js"),
            );
            let result = official_web::eval(&view.0, &script).await;
            // Submitting can unload the callback. Inspect the next page instead of submitting again.
            let raw = match result {
                Ok(raw) => raw,
                Err(_) if *stage == "submit" => break,
                Err(_) => {
                    tokio::time::sleep(POLL_INTERVAL).await;
                    continue;
                }
            };
            if !request.current(app) || raw.len() > 1024 {
                return Err("work_setup_failed");
            }
            let result: Value = serde_json::from_str(&raw).map_err(|_| "work_setup_failed")?;
            trace["state"] = json!(step_name(result["state"].as_str().unwrap_or("")));
            match result["reason"].as_str() {
                Some(reason) => {
                    trace["reason"] = json!(step_name(reason));
                    // First time each wait reason shows in this stage: timing only.
                    if reason != last_reason {
                        last_reason = reason.to_owned();
                        let name = format!("{stage}-{}", step_name(reason));
                        note(trace, started, &name[..name.len().min(32)]);
                    }
                }
                None => {
                    if let Some(map) = trace.as_object_mut() {
                        map.remove("reason");
                    }
                }
            }
            match result["state"].as_str() {
                Some("wait") => tokio::time::sleep(POLL_INTERVAL).await,
                Some("sign-in") => return Err("sign_in"),
                Some("permission") => return Err("permission"),
                Some(state) if state == *expected => {
                    note(trace, started, stage);
                    if *stage == "detail" {
                        let path = result["path"]
                            .as_str()
                            .filter(|path| detail_path(path, &request.slug))
                            .ok_or("work_setup_failed")?;
                        if view
                            .0
                            .url()
                            .ok()
                            .as_ref()
                            .is_none_or(|url| url.origin() != origin || url.path() != path)
                        {
                            return Err("work_setup_failed");
                        }
                        return Ok(path
                            .strip_prefix("/connections/")
                            .ok_or("work_setup_failed")?
                            .to_owned());
                    }
                    break;
                }
                _ => return Err("work_setup_failed"),
            }
        }
    }
    Err("work_setup_failed")
}

/// Diagnostic step name: lowercase ASCII and '-', never page text or values.
fn step_name(value: &str) -> &str {
    if (1..=32).contains(&value.len()) && value.bytes().all(|c| c.is_ascii_lowercase() || c == b'-') {
        value
    } else {
        "other"
    }
}

/// Timing of the native steps: fixed step names and seconds since the request
/// started, for connector-timing.json. Never page text or values.
fn note(trace: &mut Value, started: tokio::time::Instant, name: &str) {
    let seconds = (started.elapsed().as_secs_f64() * 10.0).round() / 10.0;
    match trace["timing"].as_array_mut() {
        Some(list) if list.len() < 40 => list.push(json!([name, seconds])),
        Some(_) => {}
        None => trace["timing"] = json!([[name, seconds]]),
    }
}

async fn cover(app: &tauri::AppHandle, view: &tauri::Webview, show: bool) {
    let text = classic_language::text(app, "workAttachCover");
    let source = format!(
        "JSON.stringify(({})({}))",
        include_str!("work_chat_cover.js"),
        json!({"show": show, "text": text})
    );
    let _ = official_web::eval(view, &source).await;
}

async fn attach(app: &tauri::AppHandle, request: &Attachment) -> (Result<String, &'static str>, Value) {
    let mut trace = json!({"stage": "start", "state": "none"});
    let mut english = false;
    let result = attach_traced(app, request, &mut trace, &mut english).await;
    if let Some(view) = app.get_webview("mistral-web") {
        if english {
            // Restore the user's site language for the next page load. The
            // conversation is not reloaded, so the selected folder stays.
            let _ = super::classic_language::work_english(app, &view, false).await;
        }
        cover(app, &view, false).await;
    }
    (result, trace)
}

/// Labels the chat automation could not recognise in the page's language.
fn label_unrecognized(stage: &str, reason: Option<&str>, reloads: u8) -> bool {
    match (stage, reason) {
        ("open-picker", Some("menu-unrecognized")) => true,
        ("confirm" | "authorize", Some("no-connect-button")) => true,
        // The picker's search field is found by its label too.
        ("choose", Some("no-row")) => reloads >= 1,
        _ => false,
    }
}

/// Switch the Mistral site to English for the Work connector pages (list,
/// form, detail), so every app language works, or back to the user's language.
async fn site_english(app: &tauri::AppHandle, on: bool) -> bool {
    match app.get_webview("mistral-web") {
        Some(view) => super::classic_language::work_english(app, &view, on).await.is_ok(),
        None => false,
    }
}

async fn attach_traced(
    app: &tauri::AppHandle,
    request: &Attachment,
    trace: &mut Value,
    english: &mut bool,
) -> Result<String, &'static str> {
    let view = app.get_webview("mistral-web").ok_or("work_setup_failed")?;
    let url = view.url().map_err(|_| "work_setup_failed")?;
    let current = || {
        current(app, &request.id, &request.project, &request.binding)
            && view.url().is_ok_and(|now| now == url)
    };
    if !current() || !official_web::projects::origin(&url) {
        trace["state"] = json!("scope-changed");
        return Err("work_setup_failed");
    }
    let mut payload = json!({"url":url.as_str(), "job":request.id, "project":request.project,
                             "connectorId":request.connector_id, "connectorName":request.name,
                             "marker":request.marker});
    let started = tokio::time::Instant::now();
    let mut deadline = tokio::time::Instant::now() + TIMEOUT;
    let stages = [
        ("open-menu", "advanced"),
        ("open-picker", "advanced"),
        ("choose", "advanced"),
        ("authorize", "advanced"),
        ("confirm", "submitted"),
        ("reselect", "advanced"),
        ("selected", "selected"),
    ];
    let result = async {
        // A connector enrolled or reconnected moments ago can be missing from,
        // or stale in, the already loaded page's picker: the row is absent, or
        // choosing it inserts nothing. Reload this same page and start over.
        let mut reloads = 0u8;
        // Entries are a reconnected connector's name or, after an enrolment, its
        // name prefix (the name itself is not known when Mistral's form hangs).
        let mut fresh_first = RECONNECTED.lock().is_ok_and(|mut names| {
            let before = names.len();
            names.retain(|entry| !request.name.starts_with(entry.as_str()));
            names.len() != before
        });
        'attempt: loop {
        for (stage, expected) in stages {
            let stage_started = tokio::time::Instant::now();
            trace["stage"] = json!(stage);
            trace["state"] = json!("pending");
            if let Some(map) = trace.as_object_mut() {
                map.remove("reason");
            }
            loop {
                if !current() {
                    trace["state"] = json!("scope-changed");
                    return Err("work_setup_failed");
                }
                if tokio::time::Instant::now() >= deadline {
                    trace["state"] = json!("timeout");
                    return Err("work_setup_failed");
                }
                payload["stage"] = json!(stage);
                payload.as_object_mut().unwrap().remove("token");
                if matches!(stage, "authorize" | "confirm") {
                    payload["token"] = json!(request.token);
                }
                cover(app, &view, true).await;
                let source = format!(
                    "JSON.stringify(({})({payload}))",
                    include_str!("work_chat_authorize.js")
                );
                let Ok(raw) = official_web::eval(&view, &source).await else {
                    trace["state"] = json!("eval-error");
                    return Err("work_setup_failed");
                };
                if !current() || raw.len() > 1024 {
                    trace["state"] = json!(if raw.len() > 1024 { "reply-too-large" } else { "scope-changed" });
                    return Err("work_setup_failed");
                }
                let Ok(value) = serde_json::from_str::<Value>(&raw) else {
                    trace["state"] = json!("reply-invalid");
                    return Err("work_setup_failed");
                };
                trace["state"] = json!(step_name(value["state"].as_str().unwrap_or("")));
                match value["reason"].as_str() {
                    Some(reason) => trace["reason"] = json!(step_name(reason)),
                    None => {
                        if let Some(map) = trace.as_object_mut() {
                            map.remove("reason");
                        }
                    }
                }
                if let Some(detail) = value["detail"].as_array() {
                    let names: Vec<String> = detail
                        .iter()
                        .filter_map(Value::as_str)
                        .take(12)
                        .map(|name| step_name(name).to_owned())
                        .collect();
                    trace["detail"] = json!(names);
                }
                let stale_picker = (stage == "choose" && value["reason"] == "no-row")
                    || (stage == "authorize"
                        && matches!(
                            value["reason"].as_str(),
                            Some("no-password-dialog-open" | "no-password-no-dialog" | "stale-row-reference")
                        ));
                // A stale row that inserted the replaced connector is certain at
                // once; a missing row needs a moment for the list to fill; Work
                // without any dialog may still be inserting the reference.
                let stale_after = match value["reason"].as_str() {
                    Some("stale-row-reference") => Duration::ZERO,
                    Some("no-row") => Duration::from_secs(2),
                    _ => Duration::from_secs(4),
                };
                let switch_language = !*english
                    && label_unrecognized(stage, value["reason"].as_str(), reloads)
                    && stage_started.elapsed() >= Duration::from_secs(3);
                if switch_language {
                    // Not recognised in this site language: reload this same
                    // conversation once in English and start over.
                    *english = true;
                    trace["site_language"] = json!("en");
                    if super::classic_language::work_english(app, &view, true).await.is_err() {
                        trace["state"] = json!("language-failed");
                        return Err("work_setup_failed");
                    }
                }
                if switch_language || fresh_first || (stale_picker && reloads < 2 && stage_started.elapsed() >= stale_after) {
                    if !switch_language && !fresh_first {
                        reloads += 1;
                        trace["reloaded"] = json!(if reloads == 1 { "once" } else { "twice" });
                    }
                    note(trace, started, if switch_language { "english" } else if fresh_first { "fresh-page" } else { "reload" });
                    fresh_first = false;
                    payload["stage"] = json!("cancel");
                    let source = format!(
                        "JSON.stringify(({})({payload}))",
                        include_str!("work_chat_authorize.js")
                    );
                    let _ = official_web::eval(&view, &source).await;
                    // Mark the old document, so the new one is told apart from it
                    // (the address does not change on a reload).
                    let _ = official_web::eval(&view, "window.__vibezWorkReloadMark=1;'ok'").await;
                    if view.navigate(url.clone()).is_err() {
                        trace["state"] = json!("reload-failed");
                        return Err("work_setup_failed");
                    }
                    // Wait for the new document in the same scope; the steps then
                    // wait for its editor themselves.
                    for _ in 0..80 {
                        tokio::time::sleep(Duration::from_millis(250)).await;
                        if !current() {
                            continue;
                        }
                        if let Ok(raw) = official_web::eval(&view, "typeof window.__vibezWorkReloadMark").await {
                            if raw.contains("undefined") {
                                break;
                            }
                        }
                    }
                    deadline = tokio::time::Instant::now() + TIMEOUT;
                    continue 'attempt;
                }
                if stage == "authorize" && stale_picker && reloads >= 2 && stage_started.elapsed() >= Duration::from_secs(8) {
                    // Two reloads did not help: Mistral keeps refusing this
                    // connector. Stop now, so it is replaced without a long wait.
                    return Err("work_setup_failed");
                }
                match value["state"].as_str() {
                    Some("selected") => {
                        note(trace, started, "selected");
                        return Ok(request.connector_id.clone());
                    }
                    Some("wait") => tokio::time::sleep(POLL_INTERVAL).await,
                    Some(state) if state == expected => {
                        note(trace, started, stage);
                        break;
                    }
                    _ => return Err("work_setup_failed"),
                }
            }
        }
        trace["state"] = json!("stages-exhausted");
        break Err("work_setup_failed");
        }
    }
    .await;
    if result.is_err() && view.url().is_ok_and(|now| now == url) {
        payload["stage"] = json!("cancel");
        payload["token"] = json!(request.token);
        let source = format!(
            "JSON.stringify(({})({payload}))",
            include_str!("work_chat_authorize.js")
        );
        let _ = official_web::eval(&view, &source).await;
    }
    result
}

struct Refresh {
    id: String,
    project: String,
    binding: String,
    name: String,
    slug: String,
}

impl Refresh {
    fn parse(event: &Value) -> Option<Self> {
        let id = event["job_id"].as_str().filter(|v| hex(v, 32))?;
        let project = event["project_id"].as_str().filter(|v| project_id(v))?;
        let binding = event["binding"].as_str().filter(|v| hex(v, 64))?;
        let name = event["connector_name"].as_str()?;
        let (slug, suffix) = name.split_once('_')?;
        if !slug.strip_prefix("vibezwork").is_some_and(|v| hex(v, 16))
            || !(4..=12).contains(&suffix.len())
            || !suffix
                .bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        {
            return None;
        }
        Some(Self {
            id: id.into(),
            project: project.into(),
            binding: binding.into(),
            name: name.into(),
            slug: slug.into(),
        })
    }
}

/// Re-check this installation's own no-key connector on its Mistral page, as
/// "Reconnect" does, so a stale "cannot reach" status does not keep it out of chats.
async fn refresh(
    app: &tauri::AppHandle,
    request: &Refresh,
    trace: &mut Value,
) -> Result<String, &'static str> {
    let is_current = || current(app, &request.id, &request.project, &request.binding);
    if !is_current() {
        return Err("work_setup_failed");
    }
    let main = app.get_webview("mistral-web").ok_or("sign_in")?;
    let mut target = main.url().map_err(|_| "sign_in")?;
    if !official_web::projects::origin(&target) {
        return Err("sign_in");
    }
    target.set_path(&format!("/connections/{}", request.name));
    target.set_query(None);
    target.set_fragment(None);
    let origin = target.origin();
    let started = tokio::time::Instant::now();
    let view = make_view(app, &request.id, &request.slug, &target, &main).await?;
    note(trace, started, "view");
    let deadline = tokio::time::Instant::now() + Duration::from_secs(90);
    trace["stage"] = json!("refresh");
    let mut page_seen = false;
    // A connector page that does not appear is loaded once more after 10 s and
    // given up after 25 s: choosing the connector in the chat may still work,
    // and waiting the full 90 s here was measured to add over a minute.
    let mut reloaded = false;
    loop {
        if !is_current() {
            trace["state"] = json!("scope-changed");
            return Err("work_setup_failed");
        }
        if tokio::time::Instant::now() >= deadline {
            trace["state"] = json!("timeout");
            return Err("work_setup_failed");
        }
        if trace["reason"] == "loading" || !page_seen {
            let waited = started.elapsed();
            if waited >= Duration::from_secs(25) {
                trace["state"] = json!("timeout");
                trace["reason"] = json!("loading");
                return Err("work_setup_failed");
            }
            if waited >= Duration::from_secs(10) && !reloaded {
                reloaded = true;
                note(trace, started, "reload");
                let _ = view.0.navigate(target.clone());
            }
        }
        let url = view.0.url().map_err(|_| "work_setup_failed")?;
        if url.as_str() == "about:blank" {
            tokio::time::sleep(POLL_INTERVAL).await;
            continue;
        }
        if !page_seen {
            page_seen = true;
            note(trace, started, "page");
        }
        if sign_in_route(&url) {
            return Err("sign_in");
        }
        if !permitted_url(&url, &origin, &request.slug) {
            trace["state"] = json!("wrong-page");
            return Err("work_setup_failed");
        }
        #[allow(unused_mut)]
        let mut payload = json!({"name": request.name});
        #[cfg(feature = "native-smoke")]
        if std::env::var_os("VIBEZ_LIVE_FORCE_RECONNECT").is_some() {
            payload["force"] = json!(true);
        }
        let script = format!(
            "JSON.stringify(({})({payload}))",
            include_str!("work_native_refresh.js")
        );
        let Ok(raw) = official_web::eval(&view.0, &script).await else {
            tokio::time::sleep(POLL_INTERVAL).await;
            continue;
        };
        if raw.len() > 1024 {
            trace["state"] = json!("reply-too-large");
            return Err("work_setup_failed");
        }
        let Ok(value) = serde_json::from_str::<Value>(&raw) else {
            tokio::time::sleep(POLL_INTERVAL).await;
            continue;
        };
        trace["state"] = json!(step_name(value["state"].as_str().unwrap_or("")));
        match value["reason"].as_str() {
            Some(reason) => trace["reason"] = json!(step_name(reason)),
            None => {
                if let Some(map) = trace.as_object_mut() {
                    map.remove("reason");
                }
            }
        }
        match value["state"].as_str() {
            Some("ok") => {
                note(trace, started, "ok");
                if value["reason"] == "reconnected" {
                    // Measured live: the chat page loaded before this reconnect
                    // still holds the connector as unreachable; choosing it there
                    // makes Mistral show "Token verification failed" and insert
                    // nothing. The attach step loads that page afresh first.
                    note(trace, started, "reconnected");
                    if let Ok(mut names) = RECONNECTED.lock() {
                        names.insert(request.name.clone());
                    }
                }
                return Ok(request.name.clone());
            }
            Some("wait") => tokio::time::sleep(POLL_INTERVAL).await,
            _ => {
                #[cfg(feature = "native-smoke")]
                dump(&view.0, "refresh-stuck").await;
                return Err("work_setup_failed");
            }
        }
    }
}

/// Live test only: what Mistral's hidden page shows when a form hangs, written
/// to the file named by VIBEZ_LIVE_DUMP. Addresses and long tokens are left out.
#[cfg(feature = "native-smoke")]
async fn dump(view: &Webview, label: &str) {
    let Some(path) = std::env::var_os("VIBEZ_LIVE_DUMP") else { return };
    let script = r#"JSON.stringify((() => {
        const clean = t => (t || '').replace(/https?:\/\/\S+/g, '<url>').replace(/[A-Za-z0-9_-]{24,}/g, '<tok>').replace(/\s+/g, ' ').slice(0, 500);
        const seen = n => !!n.getClientRects().length;
        return {
            path: location.pathname.replace(/[A-Za-z0-9_-]{24,}/g, '<tok>'),
            dialogs: [...document.querySelectorAll('[role=dialog],[role=alertdialog]')].filter(seen).map(d => ({
                text: clean(d.innerText),
                buttons: [...d.querySelectorAll('button')].filter(seen).map(b => [clean(b.innerText || b.getAttribute('aria-label')).slice(0, 30), b.disabled, b.getAttribute('aria-busy'), !!b.querySelector('svg.animate-spin,[class*=spin]')]),
            })),
            notices: [...document.querySelectorAll('[data-sonner-toast],[role=status],[role=alert]')].filter(seen).map(n => clean(n.innerText)),
            online: navigator.onLine,
        };
    })())"#;
    let text = official_web::eval(view, script).await.unwrap_or_else(|_| "eval-failed".to_owned());
    use std::io::Write;
    if let Ok(mut file) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{label} {text}");
    }
}

enum WorkRequest {
    Enroll(Request),
    Attach(Attachment),
    Refresh(Refresh),
}
impl WorkRequest {
    fn identity(&self) -> (&str, &str) {
        match self {
            Self::Enroll(r) => (&r.id, &r.project),
            Self::Attach(r) => (&r.id, &r.project),
            Self::Refresh(r) => (&r.id, &r.project),
        }
    }
    fn attaches(&self) -> bool {
        matches!(self, Self::Attach(_))
    }
}

fn finish(
    app: &tauri::AppHandle,
    job: &str,
    project: &str,
    attaches: bool,
    result: Result<String, &'static str>,
    diagnostic: Value,
) {
    let mut payload = json!({"action":"web_work_enroll_result","job_id":job,"project_id":project});
    // Step timing (names and seconds only) goes with every outcome.
    if diagnostic["timing"].is_array() {
        payload["timing"] = diagnostic["timing"].clone();
    }
    match result {
        Ok(reference) => {
            payload[if attaches {
                "connector_id"
            } else {
                "connector_name"
            }] = json!(reference)
        }
        Err(code) => {
            payload["error"] = json!(code);
            // Step and state names only; never tokens, URLs or page text.
            if diagnostic.is_object() {
                payload["diagnostic"] = diagnostic;
            }
        }
    }
    let _ = write_engine(app, &payload);
}

/// Runs before the normal engine event forwarding. Never expose its key to a UI event.
pub(super) fn handle_event(app: &tauri::AppHandle, event: &Value) -> bool {
    if event["type"] == "web_work_enroll_cancel" {
        let label = app
            .state::<SetupState>()
            .0
            .lock()
            .ok()
            .and_then(|mut state| {
                let active = state.as_mut()?;
                if event["job_id"].as_str() != Some(active.id.as_str())
                    || event["project_id"].as_str() != Some(active.project.as_str())
                {
                    return None;
                }
                active.cancelled = true;
                Some(format!("mistral-connector-setup-{}", active.id))
            });
        if let Some(view) = label.and_then(|label| app.get_webview(&label)) {
            let _ = view.close();
        }
        return true;
    }
    let request = match event["type"].as_str() {
        Some("web_work_enroll") => Request::parse(event).map(WorkRequest::Enroll),
        Some("web_work_attach") => Attachment::parse(event).map(WorkRequest::Attach),
        Some("web_work_refresh") => Refresh::parse(event).map(WorkRequest::Refresh),
        _ => return false,
    };
    let Some(request) = request else {
        if let (Some(job), Some(project)) = (event["job_id"].as_str(), event["project_id"].as_str())
        {
            if hex(job, 32) && project_id(project) {
                finish(app, job, project, false, Err("work_setup_failed"), Value::Null);
            }
        }
        return true;
    };
    let (job, project) = request.identity();
    let state = app.state::<SetupState>();
    let Ok(mut active) = state.0.lock() else {
        return true;
    };
    if active.as_ref().is_some_and(|active| active.id == job) {
        return true;
    }
    if active.is_some() {
        drop(active);
        finish(
            app,
            job,
            project,
            request.attaches(),
            Err("work_setup_failed"),
            json!({"stage": "start", "state": "busy"}),
        );
        return true;
    }
    *active = Some(Active {
        id: job.to_owned(),
        project: project.to_owned(),
        cancelled: false,
    });
    drop(active);
    let lease = Lease {
        app: app.clone(),
        id: job.to_owned(),
    };
    tauri::async_runtime::spawn(async move {
        let (result, diagnostic) = match &request {
            WorkRequest::Enroll(value) => {
                let mut trace = json!({"stage": "start", "state": "none"});
                let english = site_english(&lease.app, true).await;
                let result = enroll(&lease.app, value, &mut trace).await;
                // A chat page loaded before this connector existed shows Mistral's
                // "Token verification failed" when it is chosen there (measured
                // live), so the attach step loads that page afresh first.
                if let Ok(mut names) = RECONNECTED.lock() {
                    names.insert(value.slug.clone());
                }
                site_english(&lease.app, false).await;
                trace["site_language"] = json!(if english { "en" } else { "unchanged" });
                (result, trace)
            }
            WorkRequest::Attach(value) => attach(&lease.app, value).await,
            WorkRequest::Refresh(value) => {
                let mut trace = json!({"stage": "start", "state": "none"});
                let english = site_english(&lease.app, true).await;
                let result = refresh(&lease.app, value, &mut trace).await;
                site_english(&lease.app, false).await;
                trace["site_language"] = json!(if english { "en" } else { "unchanged" });
                (result, trace)
            }
        };
        let (job, project) = request.identity();
        let app = lease.app.clone();
        drop(lease);
        finish(&app, job, project, request.attaches(), result, diagnostic);
    });
    true
}

#[cfg(test)]
mod tests {
    use super::*;
    const ID: &str = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";
    const SLUG: &str = "vibezwork0123456789abcdef";

    #[test]
    fn unrecognised_labels_switch_the_chat_to_english_once() {
        assert!(label_unrecognized("open-picker", Some("menu-unrecognized"), 0));
        assert!(label_unrecognized("confirm", Some("no-connect-button"), 0));
        assert!(label_unrecognized("authorize", Some("no-connect-button"), 0));
        // A missing row is first treated as a stale picker (reload), then as language.
        assert!(!label_unrecognized("choose", Some("no-row"), 0));
        assert!(label_unrecognized("choose", Some("no-row"), 1));
        for (stage, reason) in [("open-menu", Some("no-editor")), ("authorize", Some("no-password-dialog-open")),
                                ("open-picker", Some("no-menu")), ("confirm", None)] {
            assert!(!label_unrecognized(stage, reason, 2), "{stage}");
        }
    }

    #[test]
    fn only_connector_list_and_owned_detail_are_navigable() {
        let origin = "https://chat.mistral.ai"
            .parse::<url::Url>()
            .unwrap()
            .origin();
        for path in ["/connections".into(), format!("/connections/{SLUG}_f12b")] {
            assert!(permitted_url(
                &format!("https://chat.mistral.ai{path}").parse().unwrap(),
                &origin,
                SLUG
            ));
        }
        for path in [
            "/connections/another".into(),
            format!("/connections/{SLUG}_ff12?other=1"),
            format!("/work?integrations={ID}"),
            format!("/work/{ID}"),
        ] {
            assert!(!permitted_url(
                &format!("https://chat.mistral.ai{path}").parse().unwrap(),
                &origin,
                SLUG
            ));
        }
        assert!(!permitted_url(
            &"https://evil.invalid/connections".parse().unwrap(),
            &origin,
            SLUG
        ));
    }

    #[test]
    fn secret_project_address_is_accepted_only_in_its_own_scope() {
        let key = format!("chat-{ID}");
        let secret = "A".repeat(54);
        let url = format!("https://temporary-example.trycloudflare.com/mcp/{key}/{secret}");
        assert!(endpoint_matches(&url, &key));
        assert!(!endpoint_matches(&url, ID));
        for bad in [
            format!("https://temporary-example.trycloudflare.com/mcp/{key}/short"),
            format!("https://temporary-example.trycloudflare.com/mcp/{key}/{secret}/extra"),
            format!("https://temporary-example.trycloudflare.com/mcp/{key}/{}", "a.b".repeat(20)),
            format!("{url}?x=1"),
        ] {
            assert!(!endpoint_matches(&bad, &key), "{bad}");
        }
    }

    #[test]
    fn key_only_enters_exact_temporary_scope() {
        let key = format!("chat-{ID}");
        let url = format!("https://temporary-example.trycloudflare.com/mcp/{key}");
        assert!(endpoint_matches(&url, &key));
        assert!(!endpoint_matches(&url, ID));
        assert!(!endpoint_matches(&format!("{url}?share=yes"), &key));
        assert!(!endpoint_matches(
            &format!("https://trycloudflare.com/mcp/{key}"),
            &key
        ));
        assert!(!endpoint_matches(
            &format!("https://temporary-example.trycloudflare.com.other.invalid/mcp/{key}"),
            &key
        ));
    }
}
