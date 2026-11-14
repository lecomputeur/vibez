//! Add the missing WKUIDelegate close notification to Wry's existing delegate.
//! The original delegate, upload dialogs, permissions and opener behavior remain
//! untouched. Only explicitly registered application-owned auth popups close.
use std::{collections::HashMap, ffi::{c_char, c_void}, sync::{Mutex, OnceLock}};
use objc2::{runtime::{AnyObject, Bool, Sel}, sel};
use objc2_web_kit::WKWebView;
use tauri::{AppHandle, Manager, Webview};
type Entry = (AppHandle, String);
static WINDOWS: OnceLock<Mutex<HashMap<usize, Entry>>> = OnceLock::new();
static INSTALLED: OnceLock<bool> = OnceLock::new();
#[link(name = "objc")]
unsafe extern "C" {
    fn class_addMethod(class: *const c_void, selector: Sel,
        implementation: unsafe extern "C" fn(), encoding: *const c_char) -> Bool;
}
unsafe extern "C" fn did_close(_delegate: *mut AnyObject, _selector: Sel, webview: *mut WKWebView) {
    let entry = WINDOWS.get().and_then(|map| map.lock().ok()).and_then(|mut map| map.remove(&(webview as usize)));
    if let Some((app, label)) = entry {
        tauri::async_runtime::spawn(async move {
            if let Some(window) = app.get_webview_window(&label) { let _ = window.destroy(); }
            if !app.webview_windows().keys().any(|key| key.starts_with("auth-popup-")) {
                if let Some(main) = app.get_webview("vibe") {
                    if main.url().is_ok_and(|url| crate::policy::auth_return_url(&url)) { crate::auth::end(&app); }
                }
            }
        });
    }
}
pub fn attach(app: &AppHandle, view: &Webview) -> Result<(), String> {
    if !view.label().starts_with("auth-popup-") { return Ok(()); }
    let app = app.clone(); let label = view.label().to_owned();
    let closed_label = label.clone();
    view.window().on_window_event(move |event| {
        if matches!(event, tauri::WindowEvent::Destroyed) {
            if let Some(map) = WINDOWS.get() {
                if let Ok(mut map) = map.lock() { map.retain(|_, (_, label)| label != &closed_label); }
            }
        }
    });
    view.with_webview(move |platform| unsafe {
        let native = &*platform.inner().cast::<WKWebView>();
        let Some(delegate) = native.UIDelegate() else {
            crate::message(&app, "Could not attach sign-in window close handler."); return;
        };
        let class: *const c_void = objc2::msg_send![&*delegate, class];
        let installed = INSTALLED.get_or_init(|| {
            // Objective-C encoding: void, self, selector, WKWebView object.
            let implementation = std::mem::transmute::<
                unsafe extern "C" fn(*mut AnyObject, Sel, *mut WKWebView), unsafe extern "C" fn()
            >(did_close);
            class_addMethod(class, sel!(webViewDidClose:), implementation, c"v@:@".as_ptr()).as_bool()
        });
        if !installed { crate::message(&app, "Could not attach sign-in window close handler."); return; }
        if let Ok(mut map) = WINDOWS.get_or_init(|| Mutex::new(HashMap::new())).lock() {
            map.insert(platform.inner() as usize, (app.clone(), label));
        }
        // WebKit caches optional delegate selectors when the delegate is set.
        native.setUIDelegate(Some(&delegate));
    }).map_err(crate::err)
}
