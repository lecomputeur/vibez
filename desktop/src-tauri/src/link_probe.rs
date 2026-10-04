//! Offline link-interception regression in the actual platform webview.
//! The probe cancels all test clicks itself, after observing defaultPrevented;
//! it never navigates to Google, invokes credentials or launches a browser.
use std::{sync::{mpsc, atomic::Ordering}, thread, time::{Duration, Instant}};
use tauri::{AppHandle, Manager};
use crate::PreviewState;

fn evaluate(view: &tauri::Webview, js: &str) -> Result<String, String> {
    let (tx, rx) = mpsc::channel();
    view.eval_with_callback(js, move |result| { let _ = tx.send(result); }).map_err(crate::err)?;
    rx.recv_timeout(Duration::from_secs(5)).map_err(crate::err)
}

fn check(app: &AppHandle) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(15);
    while !app.state::<PreviewState>().shell_ready.load(Ordering::Relaxed) {
        if Instant::now() > deadline { return Err("Toolbar IPC did not become ready for link probe".into()); }
        thread::sleep(Duration::from_millis(100));
    }
    let view = app.get_webview("vibe").ok_or("Missing test view")?;
    // The toolbar is a different webview: its IPC handshake does not mean the
    // content DOM is ready yet. Do not run the test on an initial about:blank.
    let deadline = Instant::now() + Duration::from_secs(25);
    loop {
        let ready = evaluate(&view, r#"(() => {
          try {
            return document.readyState === 'complete' && Boolean(document.body)
              && document.title === 'Offline test content (not Mistral)';
          } catch (_) { return false; }
        })()"#)?;
        if ready == "true" { break; }
        if Instant::now() > deadline {
            return Err(format!("Offline content DOM did not become ready: result={ready:?}; {}", crate::link_trace::diagnostics()));
        }
        thread::sleep(Duration::from_millis(250));
    }
    let script = r#"(() => {
      try {
        const results = [];
        for (const mode of ['blank', 'ctrl', 'shift']) {
          const a = document.createElement('a');
          a.href = 'https://accounts.google.com/';
          a.target = mode === 'blank' ? '_blank' : '_self';
          document.body.appendChild(a);
          let seen = 'missing';
          window.addEventListener('click', e => {
            seen = e.defaultPrevented ? 'intercepted' : 'native';
            e.preventDefault();
          }, {once: true});
          a.dispatchEvent(new MouseEvent('click', {
            bubbles: true, composed: true, cancelable: true, button: 0,
            ctrlKey: mode === 'ctrl', shiftKey: mode === 'shift'
          }));
          results.push(seen);
          a.remove();
        }
        return results.join(',');
      } catch (error) {
        return 'probe-exception:' + String(error && error.message || error);
      }
    })()"#;
    let raw = evaluate(&view, script)?;
    let result: String = serde_json::from_str(&raw)
        .map_err(|error| format!("Link probe returned {raw:?}: {error}"))?;
    if result != "native,native,native" { return Err(format!("Unexpected injected link interception: {result}")); }
    println!("LINK_PROBE_OK: blank, Ctrl-click and Shift-click are not intercepted by injected opener JavaScript; no external navigation performed");
    Ok(())
}

pub fn start(app: AppHandle, only: bool) {
    thread::spawn(move || match check(&app) {
        Ok(()) if only => app.exit(0),
        Ok(()) => crate::smoke::start(app),
        Err(error) => { eprintln!("LINK_PROBE_FAILED: {error}"); app.exit(1); }
    });
}
