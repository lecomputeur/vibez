//! Native browser state. Remote documents never receive additional IPC rights.
use tauri::{AppHandle, Manager, Webview};
use crate::{err, PreviewState};
use std::sync::atomic::Ordering;

pub async fn state(view: &Webview, app: &AppHandle) -> Result<(bool, bool, bool), String> {
    let loading = app.state::<PreviewState>().site_language.loading.load(Ordering::SeqCst);
    let (tx, rx) = tokio::sync::oneshot::channel();
    view.with_webview(move |p| {
        #[cfg(target_os = "linux")]
        let result = {
            use webkit2gtk::WebViewExt;
            let v = p.inner();
            Ok((v.can_go_back(), v.can_go_forward(), v.is_loading()))
        };
        #[cfg(target_os = "windows")]
        let result = (|| unsafe {
            let v = p.controller().CoreWebView2().map_err(err)?;
            let mut back = windows::core::BOOL::default();
            let mut forward = windows::core::BOOL::default();
            v.CanGoBack(&mut back).map_err(err)?;
            v.CanGoForward(&mut forward).map_err(err)?;
            Ok((back.as_bool(), forward.as_bool(), loading))
        })();
        #[cfg(target_os = "macos")]
        let result = unsafe {
            let v = &*p.inner().cast::<objc2_web_kit::WKWebView>();
            Ok((v.canGoBack(), v.canGoForward(), v.isLoading()))
        };
        let _ = tx.send(result);
    }).map_err(err)?;
    let _ = loading;
    tokio::time::timeout(std::time::Duration::from_secs(3), rx).await.map_err(err)?.map_err(err)?
}

pub async fn history(view: &Webview, forward: bool) -> Result<(), String> {
    let (tx, rx) = tokio::sync::oneshot::channel();
    view.with_webview(move |p| {
        #[cfg(target_os = "linux")]
        let result = {
            use webkit2gtk::WebViewExt;
            if forward { p.inner().go_forward(); } else { p.inner().go_back(); }
            Ok(())
        };
        #[cfg(target_os = "windows")]
        let result = (|| unsafe {
            let v = p.controller().CoreWebView2().map_err(err)?;
            if forward { v.GoForward().map_err(err) } else { v.GoBack().map_err(err) }
        })();
        #[cfg(target_os = "macos")]
        let result = unsafe {
            let v = &*p.inner().cast::<objc2_web_kit::WKWebView>();
            if forward { let _ = v.goForward(); } else { let _ = v.goBack(); }
            Ok(())
        };
        let _ = tx.send(result);
    }).map_err(err)?;
    tokio::time::timeout(std::time::Duration::from_secs(3), rx).await.map_err(err)?.map_err(err)?
}

#[cfg(target_os = "windows")]
pub async fn preferred(view: &Webview, locale: &str) -> Result<(), String> {
    use std::sync::{Arc, Mutex};
    use windows::core::{HSTRING, Interface, PWSTR};
    use webview2_com::{CallDevToolsProtocolMethodCompletedHandler, Microsoft::Web::WebView2::Win32::ICoreWebView2Settings2};
    let locale = locale.to_owned();
    let (tx, rx) = tokio::sync::oneshot::channel();
    let tx = Arc::new(Mutex::new(Some(tx)));
    view.with_webview(move |p| {
        let answer = tx.clone();
        let result: Result<(), String> = (|| unsafe {
            let v = p.controller().CoreWebView2().map_err(err)?;
            let settings: ICoreWebView2Settings2 = v.Settings().map_err(err)?.cast().map_err(err)?;
            let mut raw = PWSTR::null();
            settings.UserAgent(&mut raw).map_err(err)?;
            let ua = raw.to_string().map_err(err);
            windows::Win32::System::Com::CoTaskMemFree(Some(raw.0.cast()));
            // Preserve the exact browser UA: only its language preference changes.
            let args = serde_json::json!({"userAgent": ua?, "acceptLanguage": locale}).to_string();
            let callback = CallDevToolsProtocolMethodCompletedHandler::create(Box::new(move |result, _| {
                if let Ok(mut slot) = answer.lock() { if let Some(tx) = slot.take() { let _ = tx.send(result.map_err(err)); } }
                Ok(())
            }));
            v.CallDevToolsProtocolMethod(&HSTRING::from("Network.setUserAgentOverride"), &HSTRING::from(args), &callback).map_err(err)
        })();
        if let Err(error) = result {
            if let Ok(mut slot) = tx.lock() { if let Some(tx) = slot.take() { let _ = tx.send(Err(error)); } }
        }
    }).map_err(err)?;
    tokio::time::timeout(std::time::Duration::from_secs(5), rx).await.map_err(err)?.map_err(err)?
}

#[cfg(target_os = "macos")]
pub async fn preferred(view: &Webview, locale: &str) -> Result<(), String> {
    use objc2::MainThreadMarker;
    use objc2_foundation::NSString;
    use objc2_web_kit::{WKUserScript, WKUserScriptInjectionTime, WKWebView};
    let locale = serde_json::to_string(locale).map_err(err)?;
    let script = format!(r#"/*VIBEZ_LANGUAGE*/(() => {{
      if (location.protocol !== 'https:' || !['chat.mistral.ai','vibe.mistral.ai'].includes(location.hostname)) return;
      const language = {locale};
      Object.defineProperty(Navigator.prototype, 'language', {{configurable:true,get:()=>language}});
      Object.defineProperty(Navigator.prototype, 'languages', {{configurable:true,get:()=>Object.freeze([language])}});
    }})();"#);
    let (tx, rx) = tokio::sync::oneshot::channel();
    view.with_webview(move |p| {
        let result: Result<(), String> = (|| unsafe {
            let mtm = MainThreadMarker::new().ok_or("WebKit operation is not on the main thread")?;
            let v = &*p.inner().cast::<WKWebView>();
            let controller = v.configuration().userContentController();
            // Keep Tauri's existing scripts and their content worlds intact.
            let existing = controller.userScripts();
            controller.removeAllUserScripts();
            for old in existing.iter() {
                if !old.source().to_string().starts_with("/*VIBEZ_LANGUAGE*/") { controller.addUserScript(&old); }
            }
            let language = WKUserScript::initWithSource_injectionTime_forMainFrameOnly(
                mtm.alloc(), &NSString::from_str(&script), WKUserScriptInjectionTime::AtDocumentStart, true);
            controller.addUserScript(&language);
            Ok(())
        })();
        let _ = tx.send(result);
    }).map_err(err)?;
    tokio::time::timeout(std::time::Duration::from_secs(3), rx).await.map_err(err)?.map_err(err)?
}
