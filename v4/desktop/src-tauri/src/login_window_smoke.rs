//! Offline regression for the native permission popup after child webviews exist.
//! Compiled only with native-smoke; never starts the backend or visits Mistral.
use super::*;
use std::path::PathBuf;

pub fn requested() -> bool {
    std::env::args().any(|arg| arg == "--login-window-smoke-test")
}

fn output() -> Result<PathBuf, String> {
    let root=PathBuf::from(std::env::var("VIBEZ4_LOGIN_SMOKE_ROOT").map_err(err)?).canonicalize().map_err(err)?;
    if !root.file_name().is_some_and(|name|name.to_string_lossy().starts_with("vibez-login-smoke-")) {
        return Err("Login smoke requires its isolated temporary root".into());
    }
    for name in ["XDG_CONFIG_HOME","XDG_DATA_HOME","XDG_CACHE_HOME","XDG_RUNTIME_DIR"] {
        let path=PathBuf::from(std::env::var(name).map_err(err)?).canonicalize().map_err(err)?;
        if !path.starts_with(&root){return Err(format!("{name} is not isolated"));}
    }
    if std::env::var_os("VIBEZ_SAFE_OUTPUT").is_some() || std::env::var_os("WAYLAND_DISPLAY").is_some() {
        return Err("Host display preferences must not enter the login smoke".into());
    }
    Ok(root.join("native-result.json"))
}

async fn popup_details(app:&tauri::AppHandle,label:&str)->Result<Value,String> {
    let app=app.clone();let label=label.to_owned();let(tx,rx)=tokio::sync::oneshot::channel();
    let dispatcher=app.clone();
    dispatcher.run_on_main_thread(move || {
        let result=(|| {
            let main=app.get_window("main").ok_or("No native main window")?;
            let popup=app.get_webview_window(&label).ok_or("Permission popup missing")?;
            let native_main=main.gtk_window().map_err(|error|format!("Read native parent: {error}"))?;
            let native_popup=popup.gtk_window().map_err(|error|format!("Read native popup: {error}"))?;
            let position=popup.outer_position().map_err(|error|format!("Read popup position: {error}"))?;
            let size=popup.outer_size().map_err(|error|format!("Read popup size: {error}"))?;
            let safe=screen(&app).map_err(|error|format!("Read popup monitor: {error}"))?;
            let inside=position.x>=safe.x && position.y>=safe.y
                && position.x as i64+size.width as i64<=safe.x as i64+safe.width as i64
                && position.y as i64+size.height as i64<=safe.y as i64+safe.height as i64;
            let parent_is_main=native_popup.transient_for().as_ref()==Some(native_main.upcast_ref::<gtk::Window>());
            if !parent_is_main || !inside{return Err("Permission popup has incorrect parent or bounds".into());}
            Ok(json!({"label":label,"transient_parent_is_native_main":parent_is_main,
                "inside_isolated_monitor":inside,"visible":popup.is_visible().map_err(err)?,
                "url":popup.url().map_err(|error|format!("Read loaded popup URL: {error}"))?.as_str(),
                "geometry":[position.x,position.y,size.width,size.height]}))
        })();let _=tx.send(result);
    }).map_err(err)?;
    rx.await.map_err(err)?
}

async fn exercise(app:&tauri::AppHandle)->Result<Value,String> {
    if app.get_window("main").is_none() || app.get_webview_window("main").is_some() {
        return Err("Regression precondition failed: main must have multiple child webviews".into());
    }
    let surface_labels:Vec<_>=app.get_window("main").unwrap().webviews().iter().map(|v|v.label().to_owned()).collect();
    if !["main","connector-panel","mistral-web"].iter().all(|label|surface_labels.iter().any(|known|known==label)) {
        return Err("Regression must include the toolbar, project panel and Mistral surface".into());
    }
    if validate_login("https://console.mistral.ai/codestral?process_id=offline-fixture").is_err() {
        return Err("Official permission URL rejected".into());
    }
    for raw in ["https://example.invalid/","http://console.mistral.ai/","https://user:password@console.mistral.ai/","file:///etc/passwd","https://console.mistral.ai:444/"] {
        if validate_login(raw).is_ok(){return Err("Invalid permission URL accepted".into());}
    }
    let mut cycles=Vec::new();
    let safe=screen(app)?;
    let scale=monitor_scale(app,safe)?;
    let expected=display_policy::window_bounds(safe,scale,(620,760))?;
    for _ in 0..3 {
        // about:blank is passed only by this test harness. Production commands
        // still validate the exact pending official Mistral console URL.
        let popup=make_login(app,"about:blank".parse().unwrap(),None).map_err(|error|format!("Create native permission popup: {error}"))?;
        let label=popup.label().to_owned();
        // WebKit can expose no URI for its initial empty document. Navigate
        // the offline fixture explicitly and wait for a committed document,
        // rather than inspecting an uninitialized URI after a fixed sleep.
        popup.navigate("about:blank".parse().unwrap()).map_err(|error|format!("Load offline popup document: {error}"))?;
        for _ in 0..100 {
            if popup.url().is_ok_and(|url|url.as_str()=="about:blank"){break;}
            tokio::time::sleep(std::time::Duration::from_millis(30)).await;
        }
        if popup.url().map_err(|error|format!("Await offline popup document: {error}"))?.as_str()!="about:blank" {
            return Err("Offline popup document did not finish loading".into());
        }
        for _ in 0..80 {
            if popup.outer_size().is_ok_and(|size|size.width==expected.width && size.height==expected.height){break;}
            tokio::time::sleep(std::time::Duration::from_millis(25)).await;
        }
        let realized=popup.outer_size().map_err(|error|format!("Await popup dimensions: {error}"))?;
        if realized.width!=expected.width || realized.height!=expected.height {
            return Err(format!("Popup dimensions not realized: {}x{}, expected {}x{}",realized.width,realized.height,expected.width,expected.height));
        }
        let details=popup_details(app,&label).await?;
        if app.state::<Bridge>().login_labels.lock().map_err(err)?.as_slice()!=[label.clone()] {
            return Err("Popup registration was not exact".into());
        }
        close_login(app);
        for _ in 0..40 {
            if app.get_window(&label).is_none(){break;}
            tokio::time::sleep(std::time::Duration::from_millis(25)).await;
        }
        if app.get_window(&label).is_some() || !app.state::<Bridge>().login_labels.lock().map_err(err)?.is_empty() {
            return Err("Popup cleanup left stale window or login state".into());
        }
        if app.get_window("main").is_none() || app.get_webview("mistral-web").is_none() {
            return Err("Popup cleanup removed an existing main surface".into());
        }
        cycles.push(details);
    }
    Ok(json!({"passed":true,"version":env!("CARGO_PKG_VERSION"),"main_is_native_multi_webview":true,
        "legacy_main_webview_window_lookup_returns_none":true,"surface_labels":surface_labels,
        "permission_popup_create_close_retry_cycles":cycles,"url_validation_preserved":true,
        "backend_started":false,"remote_mistral_accessed":false,"live_code_tools_tested":false,
        "scope":"Native permission popup regression only; no live Mistral authorization or Code tool invocation."}))
}

pub fn run() {
    let output=output().expect("Isolated login smoke environment");
    let app=tauri::Builder::default().manage(Bridge::default())
        .setup(|app| {
            let config=app.path().app_config_dir()?;std::fs::create_dir_all(&config)?;
            app.manage(classic_language::Language::load(&config).map_err(std::io::Error::other)?);
            app.manage(panel_prefs::PanelPrefs::load(&config));
            let data=app.path().app_data_dir()?;std::fs::create_dir_all(&data)?;
            let _main=WebviewWindowBuilder::new(app,"main",WebviewUrl::External("about:blank".parse().unwrap()))
                .data_directory(data.join("toolbar")).title("VibeZ isolated login regression")
                .visible(false).inner_size(900.,600.).build()?;
            for (label,x) in [("connector-panel",0.),("mistral-web",450.)] {
                app.get_window("main").unwrap().add_child(
                    tauri::webview::WebviewBuilder::new(label,WebviewUrl::External("about:blank".parse().unwrap()))
                        .data_directory(data.join(label)),
                    tauri::LogicalPosition::new(x,0.),tauri::LogicalSize::new(450.,600.))?;
            }
            Ok(())
        }).build(tauri::generate_context!()).expect("Build isolated login regression");
    let target=output.clone();
    app.run(move |app,event| {
        if matches!(event,tauri::RunEvent::Ready) {
            let handle=app.clone();let target=target.clone();
            tauri::async_runtime::spawn(async move {
                let result=match exercise(&handle).await {
                    Ok(value)=>value,
                    Err(error)=>json!({"passed":false,"error":error,"remote_mistral_accessed":false}),
                };
                let success=result["passed"]==true;
                let _=std::fs::write(target,serde_json::to_vec_pretty(&result).unwrap());
                handle.exit(if success{0}else{1});
            });
        }
    });
    let success=std::fs::read(&output).ok().and_then(|raw|serde_json::from_slice::<Value>(&raw).ok()).is_some_and(|value|value["passed"]==true);
    if !success{std::process::exit(1);}
}
