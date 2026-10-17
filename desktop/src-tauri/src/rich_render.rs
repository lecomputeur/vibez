use tauri::Webview;
pub const SCRIPT:&str=include_str!("rich_render.js");
pub fn loaded(view:&Webview) {
    // Diagnostic escape hatch for driver/site regressions; normal launch opts in.
    if std::env::var_os("VIBEZ_DISABLE_RICH_RENDER").is_some() { return; }
    if let Ok(url)=view.url() {
        if url.scheme()=="https" && matches!(url.host_str(),Some("chat.mistral.ai"|"vibe.mistral.ai")) {
            let _=view.eval(SCRIPT);
        }
    }
}
pub async fn pause_capture(view:&Webview)->Result<(),String> {
    crate::screenshots::eval_value(view,"window.__vibezRichRender?.pause('capture');true").await?;
    Ok(())
}
pub fn resume_capture(view:&Webview) { let _=view.eval("window.__vibezRichRender?.resume('capture');true"); }

/// Resume even when the pause callback times out or the capture future is
/// cancelled. WebKit processes the best-effort cleanup after the queued pause.
pub struct CapturePause { view: Webview }
impl CapturePause {
    pub fn new(view: &Webview) -> Self { Self { view: view.clone() } }
    pub async fn begin(&self) -> Result<(), String> { pause_capture(&self.view).await }
}
impl Drop for CapturePause {
    fn drop(&mut self) { resume_capture(&self.view); }
}

/// Report counts only. Never read, persist or include conversation text.
pub async fn diagnostics(view: &Webview) -> String {
    if std::env::var_os("VIBEZ_DISABLE_RICH_RENDER").is_some() { return "disabled by environment".into(); }
    let result = crate::screenshots::eval_value(view,
        "(() => { const s=window.__vibezRichRender?.status(); return JSON.stringify(s?{present:true,messages:s.messages,optimized:s.optimized,working:s.working,paused:s.paused.length}: {present:false}); })()"
    ).await;
    let Ok(raw) = result else { return "unavailable".into(); };
    if raw.len() > 1024 { return "unavailable".into(); }
    let Ok(value) = serde_json::from_str::<serde_json::Value>(&raw) else { return "unavailable".into(); };
    if value["present"] != true { return "inactive on this page".into(); }
    format!("matched={}; optimized={}; working={}; pauses={}",
        value["messages"].as_u64().unwrap_or(0), value["optimized"].as_u64().unwrap_or(0),
        value["working"].as_bool().unwrap_or(false), value["paused"].as_u64().unwrap_or(0))
}
