//! Cross-platform Vibe page screenshots.
//! The capture engine runs inside the already-loaded Vibe webview and receives
//! no native IPC privileges. Rust only asks the webview to render, retrieves the
//! resulting PNG, and writes it to the native clipboard.
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::Value;
use std::{sync::atomic::Ordering, time::{Duration, Instant}};
use tauri::{AppHandle, Manager};
use tauri_plugin_clipboard_manager::ClipboardExt;

use crate::{desktop_ui, err, message, PreviewState};

const SNAPDOM: &str = include_str!("../../node_modules/@zumer/snapdom/dist/snapdom.js");
const MAX_DATA_URL_BYTES: usize = 34 * 1024 * 1024;

fn decode_eval(raw: String) -> String {
    serde_json::from_str::<String>(&raw).unwrap_or(raw)
}

async fn eval_value(view: &tauri::Webview, script: impl Into<String>) -> Result<String, String> {
    let (tx, rx) = tokio::sync::oneshot::channel();
    view.eval_with_callback(script, move |result| { let _ = tx.send(result); }).map_err(err)?;
    let raw = tokio::time::timeout(Duration::from_secs(4), rx).await.map_err(err)?.map_err(err)?;
    Ok(decode_eval(raw))
}

fn capture_script(mode: &str, drag_hint: &str) -> Result<String, String> {
    if !matches!(mode, "full" | "visible" | "selection") {
        return Err("Unsupported screenshot mode".into());
    }
    let mode = serde_json::to_string(mode).map_err(err)?;
    let drag_hint = serde_json::to_string(drag_hint).map_err(err)?;
    Ok(format!(r#"
{SNAPDOM}
(() => {{
  const MODE = {mode};
  const DRAG_HINT = {drag_hint};
  window.__vibezCaptureResult = null;
  window.__vibezCaptureCancel?.();
  window.__vibezCaptureCancel = null;

  const finish = value => {{ window.__vibezCaptureResult = JSON.stringify(value); }};
  const visible = el => {{
    if (!el || !el.isConnected) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 40 && r.height > 40 && s.display !== 'none' && s.visibility !== 'hidden';
  }};
  const background = () => {{
    for (const el of [document.body, document.documentElement]) {{
      if (!el) continue;
      const value = getComputedStyle(el).backgroundColor;
      if (value && value !== 'rgba(0, 0, 0, 0)' && value !== 'transparent') return value;
    }}
    return '#ffffff';
  }};
  const toDataUrl = blob => new Promise((resolve,reject) => {{
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error('Could not read screenshot'));
    reader.onload = () => resolve(String(reader.result || ''));
    reader.readAsDataURL(blob);
  }});
  const pickScrollableRoot = () => {{
    const scrolling = document.scrollingElement || document.documentElement;
    let best = scrolling;
    let bestScore = Math.max(1, scrolling?.scrollHeight || 0) * Math.max(1, scrolling?.clientWidth || innerWidth);
    const nodes = [...document.querySelectorAll('main,[role="main"],section,article,div')].slice(0, 2500);
    for (const el of nodes) {{
      if (!visible(el)) continue;
      const style = getComputedStyle(el);
      if (!/(auto|scroll)/.test(style.overflowY || '') || el.scrollHeight <= el.clientHeight + 40) continue;
      const r = el.getBoundingClientRect();
      if (r.width < innerWidth * 0.35 || r.height < innerHeight * 0.25) continue;
      const score = el.scrollHeight * Math.max(el.clientWidth, r.width);
      if (score > bestScore) {{ best = el; bestScore = score; }}
    }}
    return best || document.documentElement;
  }};
  const chooseRect = () => new Promise(resolve => {{
    const overlay = document.createElement('div');
    const box = document.createElement('div');
    const hint = document.createElement('div');
    overlay.id='vibez-screenshot-selection-overlay'; box.id='vibez-screenshot-selection-box'; hint.id='vibez-screenshot-selection-hint';
    Object.assign(overlay.style, {{
      position:'fixed', inset:'0', zIndex:'2147483646', cursor:'crosshair',
      background:'rgba(0,0,0,.12)', userSelect:'none', touchAction:'none'
    }});
    Object.assign(box.style, {{
      position:'fixed', display:'none', zIndex:'2147483647',
      border:'2px solid #ff6b35', background:'rgba(255,107,53,.12)',
      boxShadow:'0 0 0 99999px rgba(0,0,0,.15)', pointerEvents:'none'
    }});
    Object.assign(hint.style, {{
      position:'fixed', top:'16px', left:'50%', transform:'translateX(-50%)',
      zIndex:'2147483647', padding:'9px 13px', borderRadius:'8px',
      background:'#17191f', color:'#fff', font:'600 13px system-ui,sans-serif',
      boxShadow:'0 6px 22px rgba(0,0,0,.35)', pointerEvents:'none'
    }});
    hint.textContent = DRAG_HINT;
    document.documentElement.append(overlay, box, hint);
    let sx=0, sy=0, active=false;
    const cleanup = () => {{
      overlay.remove(); box.remove(); hint.remove();
      window.removeEventListener('keydown', onKey, true);
      window.__vibezCaptureCancel = null;
    }};
    const cancel = () => {{ cleanup(); resolve(null); }};
    window.__vibezCaptureCancel = cancel;
    const onKey = event => {{ if (event.key === 'Escape') {{ event.preventDefault(); event.stopPropagation(); cancel(); }} }};
    window.addEventListener('keydown', onKey, true);
    overlay.addEventListener('pointerdown', event => {{
      event.preventDefault(); active=true; sx=event.clientX; sy=event.clientY;
      box.style.display='block'; box.style.left=sx+'px'; box.style.top=sy+'px';
      box.style.width='0px'; box.style.height='0px';
      overlay.setPointerCapture?.(event.pointerId);
    }});
    overlay.addEventListener('pointermove', event => {{
      if (!active) return;
      const x=Math.min(sx,event.clientX), y=Math.min(sy,event.clientY);
      const w=Math.abs(event.clientX-sx), h=Math.abs(event.clientY-sy);
      Object.assign(box.style,{{left:x+'px',top:y+'px',width:w+'px',height:h+'px'}});
    }});
    overlay.addEventListener('pointerup', event => {{
      if (!active) return; active=false;
      const x=Math.min(sx,event.clientX), y=Math.min(sy,event.clientY);
      const width=Math.abs(event.clientX-sx), height=Math.abs(event.clientY-sy);
      cleanup();
      if (width < 4 || height < 4) resolve(null);
      else resolve({{x:x+scrollX,y:y+scrollY,width,height}});
    }});
  }});

  (async () => {{
    let restore = null;
    try {{
      let target = document.documentElement;
      const options = {{ dpr:1, backgroundColor:background(), invalidate:true }};
      if (MODE === 'visible') {{
        options.clip = {{x:scrollX,y:scrollY,width:innerWidth,height:innerHeight}};
      }} else if (MODE === 'selection') {{
        const rect = await chooseRect();
        if (!rect) {{ finish({{status:'cancelled'}}); return; }}
        options.clip = rect;
      }} else {{
        target = pickScrollableRoot();
        if (target !== document.documentElement && target !== document.body && target !== document.scrollingElement) {{
          const previous = {{
            height:target.style.height, maxHeight:target.style.maxHeight,
            overflow:target.style.overflow, overflowY:target.style.overflowY,
            scrollTop:target.scrollTop
          }};
          const fullHeight = Math.min(target.scrollHeight, 60000);
          target.scrollTop = 0;
          target.style.height = fullHeight + 'px';
          target.style.maxHeight = 'none';
          target.style.overflow = 'visible';
          target.style.overflowY = 'visible';
          restore = () => {{
            target.style.height=previous.height; target.style.maxHeight=previous.maxHeight;
            target.style.overflow=previous.overflow; target.style.overflowY=previous.overflowY;
            target.scrollTop=previous.scrollTop;
          }};
        }}
      }}
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      const capture = await window.snapdom(target, options);
      const meta = capture.meta || {{}};
      const estimatedWidth = Number(meta.w0 || target.scrollWidth || innerWidth);
      const estimatedHeight = Number(meta.h0 || target.scrollHeight || innerHeight);
      const pixels = Math.max(1, estimatedWidth * estimatedHeight);
      const scale = MODE === 'full' ? Math.max(0.45, Math.min(1, Math.sqrt(36000000 / pixels))) : 1;
      const blob = await capture.toBlob({{format:'png', dpr:1, scale}});
      restore?.(); restore = null;
      if (!blob || !blob.size) throw new Error('Screenshot engine returned an empty image');
      if (blob.size > 24 * 1024 * 1024) throw new Error('Screenshot is too large to copy safely');
      const dataUrl = await toDataUrl(blob);
      finish({{status:'ok',dataUrl,width:estimatedWidth,height:estimatedHeight,scale}});
    }} catch (error) {{
      try {{ restore?.(); }} catch (_) {{}}
      finish({{status:'error',message:String(error?.message || error || 'Screenshot failed')}});
    }}
  }})();
  return 'started';
}})()
"#))
}

async fn wait_result(view: &tauri::Webview, mode: &str) -> Result<Value, String> {
    let timeout = if mode == "selection" { Duration::from_secs(120) } else { Duration::from_secs(45) };
    let deadline = Instant::now() + timeout;
    loop {
        if Instant::now() >= deadline {
            let _ = view.eval("window.__vibezCaptureCancel?.(); window.__vibezCaptureResult=null;");
            return Err("Screenshot timed out".into());
        }
        tokio::time::sleep(Duration::from_millis(180)).await;
        let raw = eval_value(view, "window.__vibezCaptureResult || ''").await?;
        if raw.is_empty() { continue; }
        let _ = view.eval("window.__vibezCaptureResult=null;");
        return serde_json::from_str(&raw).map_err(err);
    }
}

fn copy_png(app: &AppHandle, data_url: &str) -> Result<(), String> {
    if data_url.len() > MAX_DATA_URL_BYTES { return Err("Screenshot result is too large".into()); }
    let encoded = data_url.strip_prefix("data:image/png;base64,").ok_or("Screenshot engine returned an unsupported image format")?;
    let bytes = STANDARD.decode(encoded).map_err(err)?;
    if bytes.len() > 26 * 1024 * 1024 { return Err("Screenshot result is too large".into()); }
    let image = tauri::image::Image::from_bytes(&bytes).map_err(err)?;
    app.clipboard().write_image(&image).map_err(err)
}

pub async fn capture(app: &AppHandle, mode: &str) -> Result<(), String> {
    let state = app.state::<PreviewState>();
    if state.capture_busy.swap(true, Ordering::SeqCst) {
        return Err(desktop_ui::status(app, "screenshot_busy"));
    }
    message(app, "screenshot_working");
    let result = async {
        let view = app.get_webview("vibe").ok_or("Vibe view is not ready")?;
        let drag = desktop_ui::preview(app, "screenshotDrag");
        view.eval(capture_script(mode, &drag)?).map_err(err)?;
        let payload = wait_result(&view, mode).await?;
        match payload["status"].as_str() {
            Some("cancelled") => return Ok(false),
            Some("ok") => {
                let data = payload["dataUrl"].as_str().ok_or("Screenshot data is missing")?;
                copy_png(app, data)?;
                Ok(true)
            }
            _ => Err(payload["message"].as_str().unwrap_or("Screenshot failed").to_string()),
        }
    }.await;
    state.capture_busy.store(false, Ordering::SeqCst);
    match result {
        Ok(true) => {
            message(app, "screenshot_copied");
            crate::show_main(app);
            Ok(())
        }
        Ok(false) => {
            message(app, "screenshot_cancelled");
            Ok(())
        }
        Err(error) => {
            message(app, format!("Screenshot cancelled or unavailable: {error}"));
            Err(error)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn modes_are_explicit() {
        for mode in ["full","visible","selection"] {
            let script=capture_script(mode,"drag").unwrap();
            assert!(script.contains("window.snapdom"));
            assert!(script.contains(mode));
        }
        assert!(capture_script("screen","drag").is_err());
    }
    #[test]
    fn capture_does_not_grant_remote_native_ipc() {
        let script=capture_script("visible","drag").unwrap();
        assert!(!script.contains("__TAURI__"));
        assert!(!script.contains("invoke("));
    }
}

pub async fn smoke_check(app: &AppHandle) -> Result<(), String> {
    if !app.state::<PreviewState>().smoke { return Err("Screenshot probe requires smoke mode".into()); }
    let view = app.get_webview("vibe").ok_or("Missing Vibe view")?;
    view.eval("document.body.insertAdjacentHTML('beforeend','<div id=\"vibez-shot-scroll-probe\" style=\"width:90vw;height:260px;overflow-y:auto\"><div style=\"height:1500px;width:20px\"></div></div>');").map_err(err)?;
    tokio::time::sleep(Duration::from_millis(120)).await;

    for mode in ["visible","full","selection"] {
        view.eval(capture_script(mode, "drag")?).map_err(err)?;
        if mode == "selection" {
            tokio::time::sleep(Duration::from_millis(160)).await;
            view.eval(r#"(() => {
              const o=document.getElementById('vibez-screenshot-selection-overlay');
              if(!o) return;
              const e=(type,x,y)=>o.dispatchEvent(new PointerEvent(type,{bubbles:true,clientX:x,clientY:y,pointerId:1}));
              e('pointerdown',30,30); e('pointermove',230,180); e('pointerup',230,180);
            })()"#).map_err(err)?;
        }
        let payload=wait_result(&view, mode).await?;
        if payload["status"].as_str()!=Some("ok") { return Err(format!("Screenshot mode {mode} failed: {payload}")); }
        let data=payload["dataUrl"].as_str().ok_or("Screenshot smoke test returned no image")?;
        if !data.starts_with("data:image/png;base64,") || data.len()<200 { return Err(format!("Screenshot mode {mode} returned invalid PNG")); }
        let width=payload["width"].as_f64().unwrap_or(0.0);
        let height=payload["height"].as_f64().unwrap_or(0.0);
        if width<=0.0 || height<=0.0 { return Err(format!("Screenshot mode {mode} returned invalid geometry")); }
        if mode=="full" {
            let viewport=eval_value(&view,"innerHeight").await?.parse::<f64>().unwrap_or(0.0);
            if height <= viewport { return Err(format!("Full-page capture did not exceed viewport: {height} <= {viewport}")); }
        }
    }
    let _=view.eval("document.getElementById('vibez-shot-scroll-probe')?.remove();");
    println!("SCREENSHOT_OK: full page, visible page and selection rendered through the Vibe webview without native IPC");
    Ok(())
}
