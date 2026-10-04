fn history_check(app: &AppHandle) -> Result<(), String> {
    let view = app.get_webview("vibe").ok_or("Missing browser")?;
    let original = view.url().map_err(crate::err)?;
    for fragment in ["v3-history-one", "v3-history-two"] {
        let mut page = original.clone(); page.set_fragment(Some(fragment));
        view.navigate(page).map_err(crate::err)?;
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            if view.url().map_err(crate::err)?.fragment() == Some(fragment) { break; }
            if Instant::now() > deadline { return Err("Native history navigation timed out".into()); }
            thread::sleep(Duration::from_millis(100));
        }
    }
    let state = tauri::async_runtime::block_on(crate::browser::state(&view, app))?;
    if !state.0 { return Err("Native browser did not expose back history".into()); }
    tauri::async_runtime::block_on(crate::browser::history(&view, false))?;
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if view.url().map_err(crate::err)?.fragment() == Some("v3-history-one") { break; }
        if Instant::now() > deadline { return Err("Native Back did not reach the previous entry".into()); }
        thread::sleep(Duration::from_millis(100));
    }
    if !tauri::async_runtime::block_on(crate::browser::state(&view, app))?.1 { return Err("Native Forward state is wrong".into()); }
    tauri::async_runtime::block_on(crate::browser::history(&view, true))?;
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if view.url().map_err(crate::err)?.fragment() == Some("v3-history-two") { break; }
        if Instant::now() > deadline { return Err("Native Forward did not reach the next entry".into()); }
        thread::sleep(Duration::from_millis(100));
    }
    view.navigate(original).map_err(crate::err)?;
    thread::sleep(Duration::from_millis(500));
    println!("HISTORY_OK: native Back and Forward navigation and availability verified");
    Ok(())
}
