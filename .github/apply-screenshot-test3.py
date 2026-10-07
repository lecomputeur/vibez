"""One-time, isolated-branch source migration; generated source is committed before building."""
from pathlib import Path
import json,os
root=Path('.')
marker=root/'.github/screenshot-test3-source-applied'
if marker.exists():
    print('Screenshot test 3 source already materialized');raise SystemExit(0)
if os.environ.get('GITHUB_REF') != 'refs/heads/vibe/screenshot-dialog-fix-a61c92':
    raise SystemExit('This migration is restricted to the screenshot test branch')
def read(p): return (root/p).read_text()
def write(p,s):
    f=root/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(s)
p='desktop/frontend/index.html';s=read(p)
a=s.index('    <!-- A native select popup'); b=s.index('    <button class="settings-button"',a)
s=s[:a]+'''    <div class="screenshot-control">
      <button class="screenshot-button" id="screenshot" type="button" aria-haspopup="dialog" title="Screenshot"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h5l2-3h4l2 3h5v13H3z"/><circle cx="12" cy="13" r="3"/></svg><span data-i18n="screenshot">Screenshot</span></button>
    </div>
'''+s[b:];write(p,s)
p='desktop/frontend/preview.css';s=read(p);s=s[:s.index('.screenshot-control {')]+'''.screenshot-control { display: flex; align-items: center; }
.screenshot-control[hidden] { display: none; }
''';write(p,s)
p='desktop/frontend/toolbar.js';s=read(p).replace('captureBusy = false, ','')
a=s.index('  // The OS/browser owns this popup');b=s.index('  refresh(); setInterval',a)
s=s[:a]+'''  $('screenshot').addEventListener('click', async () => {
    $('screenshot').disabled = true;
    try { await preview.invoke('show_screenshot'); }
    catch (error) { status(preview.errorText(error)); }
    finally { $('screenshot').disabled = false; }
  });
'''+s[b:];s=s.replace("$('version').textContent = state.version;","$('version').textContent = state.version + (state.build_label ? ' · ' + state.build_label : '');")
write(p,s)
p='desktop/src-tauri/src/capture_page.js';s=read(p)
s=s.replace("      const capture=await window.snapdom(document.documentElement,options);",'''      if (config.native) {
        // Keep expanded scroll containers intact until Rust has taken the snapshot.
        // No pixel data, canvas, external fetches or native privileges in this page.
        const rect = config.mode === 'full' ? fullGeometry : config.mode === 'selection'
          ? { ...options.clip, x: options.clip.x - scrollX, y: options.clip.y - scrollY }
          : { x:0, y:0, width:innerWidth, height:innerHeight };
        const viewport = { width:innerWidth, height:innerHeight };
        const source = config.mode === 'full' ? fullGeometry : viewport;
        limit(source.width * devicePixelRatio, source.height * devicePixelRatio);
        state.result = JSON.stringify({status:'ready',rect,viewport,geometry:fullGeometry});
        return;
      }
      const capture=await window.snapdom(document.documentElement,options);''')
write(p,s)
p='desktop/src-tauri/src/screenshots.rs';s=read(p)
s=s.replace('const SCRIPT: &str', '#[cfg(target_os = "linux")]\n#[path="screenshot_native_linux.rs"] mod native_linux;\nconst SCRIPT: &str')
s=s.replace('"timeoutMs":timeout}', '"timeoutMs":timeout,"native":cfg!(target_os="linux")}')
s=s.replace('Ok(format!("{SNAPDOM}\\n;\\n{}",SCRIPT.replace', 'let library=if cfg!(target_os="linux") { "" } else { SNAPDOM };\n    Ok(format!("{library}\\n;\\n{}",SCRIPT.replace')
s=s.replace('if !raw.is_empty() { return serde_json::from_str(&raw).map_err(err); }','''if !raw.is_empty() {
                let payload:Value=serde_json::from_str(&raw).map_err(err)?;
                #[cfg(target_os="linux")]
                if payload["status"]=="ready" {
                    let bytes=native_linux::snapshot(view,mode,&payload).await?;
                    let image=tauri::image::Image::from_bytes(&bytes).map_err(err)?;
                    return Ok(json!({"status":"ok","dataUrl":format!("data:image/png;base64,{}",STANDARD.encode(&bytes)),
                        "width":image.width(),"height":image.height(),"geometry":payload["geometry"],"meta":{"engine":"WebKitGTK native snapshot"}}));
                }
                return Ok(payload);
            }''')
a=s.index('pub async fn capture(app:');b=s.index('#[path="screenshot_probe.rs"]',a)
s=s[:a]+'''pub async fn capture_preview(app:&AppHandle,mode:&str)->Result<Value,String> {
    if !matches!(mode,"full"|"visible"|"selection") { return Err("Unsupported screenshot mode".into()); }
    let state=app.state::<PreviewState>();
    if state.capture_busy.swap(true,Ordering::SeqCst) { return Err(desktop_ui::status(app,"screenshot_busy")); }
    let _busy=Busy(&state.capture_busy);
    crate::screenshot_dialog::clear();
    message(app,"screenshot_working");
    let result:Result<Value,String>=async {
        let view=app.get_webview("vibe").ok_or("Vibe view is not ready")?;
        let url=view.url().map_err(err)?;
        let id=begin(&view,mode,&desktop_ui::preview(app,"screenshotDrag")).await?;
        let payload=wait_result(&view,mode,id).await?;
        match payload["status"].as_str() {
            Some("cancelled")=>Ok(json!({"cancelled":true})),
            Some("ok")=> {
                if view.url().map_err(err)?!=url { return Err("The page changed during capture; please try again".into()); }
                let bytes=png_bytes(payload["dataUrl"].as_str().ok_or("Missing screenshot data")?)?;
                let copy_error=copy_png(app,&bytes).err();
                crate::screenshot_dialog::remember(bytes)?;
                Ok(json!({"cancelled":false,"dataUrl":payload["dataUrl"],"width":payload["width"],"height":payload["height"],
                    "copied":copy_error.is_none(),"copyError":copy_error}))
            },
            _=>Err(payload["message"].as_str().unwrap_or("Screenshot failed").into())
        }
    }.await;
    match &result {
        Ok(value) if value["cancelled"]==true=>message(app,"screenshot_cancelled"),
        Ok(value) if value["copied"]==true=>message(app,"screenshot_copied"),
        Ok(_)=>message(app,"Screenshot ready — see preview"),
        Err(error)=>message(app,format!("Screenshot failed: {error}")),
    }
    result
}
pub fn cancel_active(app:&AppHandle) {
    if let Some(view)=app.get_webview("vibe") { let _=view.eval("window.__vibezCapture?.cancel?.();"); }
}
pub fn copy_last(app:&AppHandle,bytes:&[u8])->Result<(),String> { copy_png(app,bytes) }
'''+s[b:];write(p,s)
p='desktop/src-tauri/src/main.rs';s=read(p).replace('mod screenshots;','mod screenshots;\nmod screenshot_dialog;')
s=s.replace('format!("{APP_NAME} v{}", env!("CARGO_PKG_VERSION"))','format!("{APP_NAME} v{} · screenshot test 3", env!("CARGO_PKG_VERSION"))')
s=s.replace('"version": env!("CARGO_PKG_VERSION"),','"version": env!("CARGO_PKG_VERSION"), "build_label": "test 3",')
s=s.replace('screenshots::capture(app, "selection").await','screenshot_dialog::open(app).await')
s=s.replace('async fn capture_screenshot(webview: Webview, app: AppHandle, mode: String) -> Result<(), String> {\n    require_local(&webview)?;\n    screenshots::capture(&app, &mode).await\n}', '''async fn capture_screenshot(webview: Webview, app: AppHandle, mode: String) -> Result<Value, String> {
    require_local(&webview)?;
    if webview.label() != "screenshot" { return Err("Use the screenshot dialog".into()); }
    screenshot_dialog::capture(&app, &mode).await
}
#[tauri::command]
async fn show_screenshot(webview: Webview, app: AppHandle) -> Result<(), String> {
    require_local(&webview)?; screenshot_dialog::open(&app).await
}
#[tauri::command]
async fn screenshot_action(webview: Webview, app: AppHandle, action: String) -> Result<Value, String> {
    require_local(&webview)?;
    if webview.label() != "screenshot" { return Err("Use the screenshot dialog".into()); }
    screenshot_dialog::action(&app, &action).await
}''')
s=s.replace('capture_screenshot, check_for_updates, get_diagnostics]', 'capture_screenshot, show_screenshot, screenshot_action, check_for_updates, get_diagnostics]')
s=s.replace('let smoke = icon_probe || link_probe_only', 'let screenshot_ui_test = std::env::args().any(|a| a == "--screenshot-ui-test");\n    let smoke = screenshot_ui_test || icon_probe || link_probe_only')
s=s.replace('if smoke && !icon_probe {', 'if smoke && !icon_probe && !screenshot_ui_test {')
s=s.replace('if window.label() != "main" { return; }', '''if window.label() == "screenshot" {
                if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                    screenshots::cancel_active(window.app_handle()); screenshot_dialog::clear();
                }
                return;
            }
            if window.label() != "main" { return; }''')
s=s.replace('            Ok(())\n        })\n        .on_window_event', '''            if screenshot_ui_test {
                let handle=app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    tokio::time::sleep(std::time::Duration::from_secs(2)).await;
                    if let Some(view)=handle.get_webview("vibe") {
                        let _=view.eval(include_str!("screenshot_fixture.js"));
                    }
                });
            }
            Ok(())
        })
        .on_window_event''')
write(p,s)
p='desktop/src-tauri/src/policy.rs';s=read(p).replace('matches!(label, "shell" | "settings")','matches!(label, "shell" | "settings" | "screenshot")');write(p,s)
p='desktop/src-tauri/build.rs';s=read(p).replace('"capture_screenshot", "get_diagnostics",','"capture_screenshot", "show_screenshot", "screenshot_action", "get_diagnostics",');write(p,s)
p='desktop/src-tauri/capabilities/local-shell.json';data=json.loads(read(p));data['permissions'].append('allow-show-screenshot');write(p,json.dumps(data,indent=2)+'\n')
p='desktop/src-tauri/tauri.conf.json';data=json.loads(read(p));data['app']['security']['capabilities'].append('local-screenshot');write(p,json.dumps(data,indent=2)+'\n')
write('desktop/src-tauri/capabilities/local-screenshot.json',json.dumps({'identifier':'local-screenshot','description':'Only the bundled screenshot dialog can capture, preview, copy or request a native PNG save dialog. No remote page access.','local':True,'webviews':['screenshot'],'permissions':['allow-get-state','allow-capture-screenshot','allow-screenshot-action']},indent=2)+'\n')
p='desktop/test/stability.test.cjs';s=read(p).replace("if (command === 'capture_screenshot') {","if (command === 'show_screenshot' || command === 'capture_screenshot') {")
a=s.index("test('native screenshot chooser sends");b=s.index("test('new page capture script parses",a)
s=s[:a]+'''test('toolbar opens a dedicated chooser, never a hidden native select', async () => {
  const bar=environment(backend());bar.run(toolbar);await flush();
  for(let i=0;i<3;i++){await bar.get('screenshot').listeners.click();assert.equal(bar.get('screenshot').disabled,false);}
  assert.equal(bar.captureCalls.length,3);
  assert.match(read('frontend/index.html'),/aria-haspopup="dialog"/);
  assert.doesNotMatch(read('frontend/index.html'),/<select id="screenshot"|id="screenshot-panel"/);
});
test('failure opening screenshot window reenables the toolbar button',async()=>{
  const bar=environment(backend(),{captureError:true});bar.run(toolbar);await flush();
  await bar.get('screenshot').listeners.click();
  assert.equal(bar.get('screenshot').disabled,false);assert.match(bar.get('status').textContent,/capture failed/);
});
'''+s[b:];write(p,s)
marker.write_text('Screenshot test 3 source materialized. Build only this committed source.\n')
