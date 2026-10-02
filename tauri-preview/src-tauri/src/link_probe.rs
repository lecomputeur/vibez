//! Offline link-interception regression in the actual platform webview.
//! The probe cancels all test clicks itself, after observing defaultPrevented;
//! it never navigates to Google, invokes credentials or launches a browser.
use std::{sync::{mpsc, atomic::Ordering}, thread, time::{Duration, Instant}};
use tauri::{AppHandle, Manager};
use crate::PreviewState;

fn check(app: &AppHandle) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(15);
    while !app.state::<PreviewState>().shell_ready.load(Ordering::Relaxed) {
        if Instant::now() > deadline { return Err("Toolbar IPC did not become ready for link probe".into()); }
        thread::sleep(Duration::from_millis(100));
    }
    let view = app.get_webview("vibe").ok_or("Missing test view")?;
    let script = r#"(() => {
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
    })()"#;
    let (tx, rx) = mpsc::channel();
    view.eval_with_callback(script, move |result| { let _ = tx.send(result); }).map_err(crate::err)?;
    let result = rx.recv_timeout(Duration::from_secs(10)).map_err(crate::err)?;
    let result: String = serde_json::from_str(&result).map_err(crate::err)?;
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
