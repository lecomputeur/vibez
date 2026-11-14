//! Live Mistral Work self-test driver. Compiled only by the native-smoke
//! feature and active only with `--live-work-self-test` plus a private
//! directory under the source tree's artifacts folder.
//!
//! The Python driver (tools/live-work-self-test.py) writes one command at a
//! time to `command.json`; this module answers in `result.json`. It never reads
//! credentials, never logs addresses or tokens, and only clicks the exact
//! consent button on Mistral's own console page.
use super::*;
use std::path::{Path,PathBuf};
const COMMAND_LIMIT:u64=65536;
const RESULT_LIMIT:usize=65536;
pub fn requested()->bool {std::env::args().any(|a|a=="--live-work-self-test")}
fn other_modes()->bool {
    std::env::args().any(|a|matches!(a.as_str(),"--standalone-smoke-test"|"--live-connector-self-test"|"--live-code-probe"|"--live-alpha7-fixture"))
}
fn source_root()->Option<PathBuf>{Path::new(env!("CARGO_MANIFEST_DIR")).parent()?.parent().map(Path::to_path_buf)}
fn checked_dir(raw:&Path,root:&Path)->Option<PathBuf>{
    if !raw.is_absolute(){return None;}
    let canonical=raw.canonicalize().ok()?;let root=root.canonicalize().ok()?;
    if canonical!=raw||canonical==root||!canonical.starts_with(&root)||!canonical.is_dir(){return None;}
    Some(canonical)
}
fn directory()->Option<PathBuf>{
    if !requested()||other_modes(){return None;}
    let root=source_root()?.join("artifacts");
    checked_dir(&PathBuf::from(std::env::var_os("VIBEZ4_LIVE_WORK_DIR")?),&root)
}
pub fn enabled()->bool {directory().is_some()}
/// The engine wrapper adds one diagnostic command (count or remove this
/// installation's own test connectors) and otherwise runs the real engine.
pub fn engine_script(original:&Path)->Result<PathBuf,String>{
    if !requested(){return Ok(original.into());}
    directory().ok_or("A private live Work self-test directory is required")?;
    let driver=source_root().ok_or("No source root")?.join("tools/live-work-self-test.py");
    if !driver.is_file()||std::fs::symlink_metadata(&driver).map_err(err)?.file_type().is_symlink(){return Err("The live Work self-test driver is missing".into());}
    Ok(driver)
}
/// The engine under test is the source tree's backend, not the resource copy:
/// a binary built outside a folder named `target` resolves its resources to
/// the installed VibeZ, which would silently test the installed release.
pub fn engine_source(original:&Path)->PathBuf{
    let source=source_root().map(|root|root.join("backend/standalone_engine.py"));
    match source {
        Some(path) if path.is_file()&&std::fs::symlink_metadata(&path).is_ok_and(|m|!m.file_type().is_symlink())=>path,
        _=>original.to_path_buf(),
    }
}
pub fn configure_engine(command:&mut Command,original:&Path){
    if enabled(){command.arg("--engine-source").arg(engine_source(original));}
}
fn save(dir:&Path,id:u64,ok:bool,result:Value)->Result<(),String>{
    let mut data=serde_json::to_vec(&json!({"id":id,"ok":ok,"result":result})).map_err(|_|"Self-test result invalid")?;
    if data.len()>RESULT_LIMIT {data=serde_json::to_vec(&json!({"id":id,"ok":false,"result":{"error":"Self-test result too large"}})).unwrap();}
    let temporary=dir.join(format!("result-{}-{id}.tmp",std::process::id()));
    let mut options=std::fs::OpenOptions::new();options.write(true).create_new(true);
    #[cfg(unix)] {use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
    let mut file=options.open(&temporary).map_err(|_|"Self-test output unavailable")?;
    file.write_all(&data).map_err(|_|"Self-test output unavailable")?;file.sync_all().map_err(|_|"Self-test output unavailable")?;
    std::fs::rename(temporary,dir.join("result.json")).map_err(|_|"Self-test output unavailable".to_owned())
}
fn window_report(app:&tauri::AppHandle)->Result<Value,String>{
    let safe=screen(app)?;let w=app.get_window("main").ok_or("Self-test main window unavailable")?;
    let p=w.outer_position().map_err(|_|"Self-test geometry unavailable")?;let size=w.outer_size().map_err(|_|"Self-test geometry unavailable")?;
    let on_safe=p.x>=safe.x&&p.y>=safe.y&&p.x as i64+size.width as i64<=safe.x as i64+safe.width as i64&&p.y as i64+size.height as i64<=safe.y as i64+safe.height as i64;
    let engine_pid=app.state::<Bridge>().process.lock().ok().and_then(|p|p.as_ref().map(|p|p.child.id()));
    let popups=app.state::<Bridge>().login_labels.lock().map(|v|v.len()).unwrap_or(0);
    Ok(json!({"on_screen_1":on_safe,"visible":w.is_visible().unwrap_or(false),"engine_pid":engine_pid,"login_windows":popups,"pid":std::process::id(),"version":env!("CARGO_PKG_VERSION")}))
}
fn safe_window(app:&tauri::AppHandle)->Result<(),String>{
    if window_report(app)?["on_screen_1"]!=true {return Err("Self-test main window outside screen 1".into());}
    Ok(())
}
fn trusted_console(url:&url::Url)->bool {url.scheme()=="https"&&url.host_str()==Some("console.mistral.ai")&&url.port_or_known_default()==Some(443)&&url.username().is_empty()&&url.password().is_none()}
/// Click only the exact consent button on Mistral's own console page. A
/// sign-in form is reported and never completed.
async fn consent(app:&tauri::AppHandle)->Result<Value,String>{
    let labels=app.state::<Bridge>().login_labels.lock().map_err(|_|"Self-test popup list unavailable")?.clone();
    let mut clicked=0;let mut waiting=0;let mut needs_sign_in=false;let mut other=0;
    for label in labels {
        let Some(view)=app.get_webview(&label)else{continue;};let Ok(url)=view.url()else{continue;};
        if url.as_str()=="about:blank"{waiting+=1;continue;}
        if !trusted_console(&url){other+=1;continue;}
        let script=r#"(()=>{const visible=e=>e.getClientRects().length>0&&!e.disabled;if([...document.querySelectorAll('input[type=password],input[type=email],input[autocomplete=username],input[autocomplete=current-password]')].some(visible))return 'needs_sign_in';const buttons=[...document.querySelectorAll('button,[role=button]')].filter(e=>visible(e)&&['authorize','autoriseren','toestaan','allow','autoryzuj','zezwól'].includes((e.innerText||e.textContent||'').replace(/\s+/g,' ').trim().toLowerCase()));if(buttons.length!==1)return 'waiting';buttons[0].click();return 'clicked';})()"#;
        match official_web::eval(&view,script).await.unwrap_or_default().as_str(){
            "clicked"=>clicked+=1,
            "needs_sign_in"=>needs_sign_in=true,
            _=>waiting+=1,
        }
    }
    Ok(json!({"clicked":clicked,"waiting":waiting,"needs_sign_in":needs_sign_in,"other_pages":other}))
}
fn choose_folder(app:&tauri::AppHandle,dir:&Path,raw:&str)->Result<Value,String>{
    let path=PathBuf::from(raw);
    let canonical=checked_dir(&path,dir).ok_or("The self-test workspace must be a folder inside the self-test directory")?;
    let state=app.state::<official_web::WebState>();
    let project=state.project.lock().map_err(err)?.as_ref().map(|p|p.id.clone()).ok_or("No confirmed Mistral project")?;
    *state.choice.lock().map_err(err)?=Some((project.clone(),canonical.to_string_lossy().into_owned()));
    Ok(json!({"queued":true,"project":project}))
}
/// Work projects use the bare UUID; conversations and Code projects carry
/// the `chat-` or `code-` prefix the engine keys them by.
fn test_project_id(id:&str)->bool {
    official_web::projects::valid_id(id.strip_prefix("chat-").or_else(||id.strip_prefix("code-")).unwrap_or(id))
}
fn engine_command(app:&tauri::AppHandle,payload:&Value)->Result<Value,String>{
    // Only the wrapper's own diagnostic command; ordinary actions go through
    // the main webview exactly as the user interface sends them.
    if payload["action"]!="self_test_connectors"{return Err("Unknown self-test engine command".into());}
    let project=payload["project_id"].as_str().filter(|id|test_project_id(id)).ok_or("Invalid project")?;
    let remove=payload["remove"].as_bool().unwrap_or(false);
    let request=payload["request_id"].as_str().filter(|v|!v.is_empty()&&v.len()<=40&&v.chars().all(|c|c.is_ascii_alphanumeric()||c=='-')).ok_or("Invalid request id")?;
    write_engine(app,&json!({"action":"self_test_connectors","project_id":project,"remove":remove,"request_id":request}))?;
    Ok(json!({"sent":true}))
}
/// Real keyboard and pointer input for the Mistral page. Page scripts act
/// only on trusted events, which a script on the page cannot produce; these
/// events enter WebKit the same way the user's own keys and clicks do.
#[cfg(target_os="linux")]
enum Input{Text(String),Key(u32,u32),Click(f64,f64)}
#[cfg(target_os="linux")]
fn parse_input(command:&Value)->Result<Input,String>{
    use gtk::gdk::keys::constants as k;
    match command["kind"].as_str(){
        Some("text")=>{
            let text=command["text"].as_str().filter(|t|!t.is_empty()&&t.len()<=2000&&t.chars().all(|c|!c.is_control())).ok_or("Self-test text invalid")?;
            Ok(Input::Text(text.into()))
        }
        Some("key")=>{
            let key=match command["key"].as_str(){
                Some("Enter")=>*k::Return,Some("Backspace")=>*k::BackSpace,Some("Escape")=>*k::Escape,Some("Left")=>*k::Left,Some("Right")=>*k::Right,
                Some("Home")=>*k::Home,Some("End")=>*k::End,Some("a")=>*k::a,
                _=>return Err("Unknown self-test key".into()),
            };
            let mut state=0;
            for m in command["mods"].as_array().map(Vec::as_slice).unwrap_or(&[]){
                state|=match m.as_str(){Some("shift")=>gtk::gdk::ModifierType::SHIFT_MASK.bits(),Some("ctrl")=>gtk::gdk::ModifierType::CONTROL_MASK.bits(),_=>return Err("Unknown self-test modifier".into())};
            }
            Ok(Input::Key(key,state))
        }
        Some("click")=>{
            let x=command["x"].as_f64().filter(|v|v.is_finite()&&(0.0..10000.0).contains(v)).ok_or("Self-test point invalid")?;
            let y=command["y"].as_f64().filter(|v|v.is_finite()&&(0.0..10000.0).contains(v)).ok_or("Self-test point invalid")?;
            Ok(Input::Click(x,y))
        }
        _=>Err("Unknown self-test input".into()),
    }
}
#[cfg(target_os="linux")]
fn deliver(widget:&webkit2gtk::WebView,input:&Input)->Result<u32,String>{
    use gtk::prelude::*;use gtk::gdk;use gtk::glib::translate::*;use webkit2gtk::WebViewExt;
    let window=widget.window().ok_or("Self-test surface not realized")?;
    let seat=widget.display().default_seat().ok_or("Self-test seat unavailable")?;
    let time=(gtk::glib::monotonic_time()/1000) as u32;let mut sent=0;
    let key=|keyval:u32,state:u32,press:bool|{
        let mut event=gdk::Event::new(if press {gdk::EventType::KeyPress}else{gdk::EventType::KeyRelease});
        let code=gdk::Keymap::for_display(&widget.display()).and_then(|m|m.entries_for_keyval(keyval).first().map(|e|e.keycode())).unwrap_or(0);
        unsafe{
            let raw=ToGlibPtrMut::<*mut gdk::ffi::GdkEvent>::to_glib_none_mut(&mut event).0 as *mut gdk::ffi::GdkEventKey;
            (*raw).window=gtk::glib::gobject_ffi::g_object_ref(window.as_ptr() as *mut _) as *mut _;
            (*raw).time=time;(*raw).state=state;(*raw).keyval=keyval;(*raw).hardware_keycode=code as u16;
        }
        event.set_device(seat.keyboard().as_ref());widget.event(&event);
    };
    match input{
        Input::Text(text)=>for c in text.chars(){
            let keyval=unsafe{gdk::ffi::gdk_unicode_to_keyval(c as u32)};key(keyval,0,true);key(keyval,0,false);sent+=1;
        },
        Input::Key(keyval,state)=>{key(*keyval,*state,true);key(*keyval,*state,false);sent=1;}
        Input::Click(x,y)=>{
            let zoom=widget.zoom_level();let(x,y)=(x*zoom,y*zoom);let(ox,oy)=window.root_origin();
            for(kind,state) in [(gdk::EventType::MotionNotify,0),(gdk::EventType::ButtonPress,0),(gdk::EventType::ButtonRelease,gdk::ModifierType::BUTTON1_MASK.bits())]{
                let mut event=gdk::Event::new(kind);
                unsafe{
                    let object=gtk::glib::gobject_ffi::g_object_ref(window.as_ptr() as *mut _) as *mut _;
                    if kind==gdk::EventType::MotionNotify{
                        let raw=ToGlibPtrMut::<*mut gdk::ffi::GdkEvent>::to_glib_none_mut(&mut event).0 as *mut gdk::ffi::GdkEventMotion;
                        (*raw).window=object;(*raw).time=time;(*raw).x=x;(*raw).y=y;(*raw).x_root=x+ox as f64;(*raw).y_root=y+oy as f64;(*raw).state=state;
                    }else{
                        let raw=ToGlibPtrMut::<*mut gdk::ffi::GdkEvent>::to_glib_none_mut(&mut event).0 as *mut gdk::ffi::GdkEventButton;
                        (*raw).window=object;(*raw).time=time;(*raw).x=x;(*raw).y=y;(*raw).x_root=x+ox as f64;(*raw).y_root=y+oy as f64;(*raw).state=state;(*raw).button=1;
                    }
                }
                event.set_device(seat.pointer().as_ref());widget.event(&event);
            }
            sent=1;
        }
    }
    Ok(sent)
}
#[cfg(target_os="linux")]
async fn input(view:&tauri::Webview,command:&Value)->Result<Value,String>{
    let input=parse_input(command)?;let(tx,rx)=tokio::sync::oneshot::channel();
    view.with_webview(move|platform|{let _=tx.send(deliver(&platform.inner(),&input));}).map_err(|_|"Self-test input unavailable")?;
    let sent=tokio::time::timeout(std::time::Duration::from_secs(5),rx).await.map_err(|_|"Self-test input timed out")?.map_err(|_|"Self-test input unavailable")??;
    Ok(json!({"sent":sent}))
}
#[cfg(not(target_os="linux"))]
async fn input(_view:&tauri::Webview,_command:&Value)->Result<Value,String>{Err("Self-test input is available on Linux only".into())}
async fn execute(app:&tauri::AppHandle,dir:&Path,command:&Value)->Result<Value,String>{
    safe_window(app)?;
    match command["action"].as_str() {
        Some("window")=>return window_report(app),
        Some("consent")=>return consent(app).await,
        Some("choose_folder")=>return choose_folder(app,dir,command["path"].as_str().ok_or("Self-test folder missing")?),
        Some("engine")=>return engine_command(app,&command["payload"]),
        Some("quit")=>return Ok(json!({"quitting":true})),
        None|Some("eval")|Some("input")=>{},
        _=>return Err("Unknown self-test action".into()),
    }
    let label=match command["surface"].as_str(){Some("mistral")=>"mistral-web",Some("panel")=>"connector-panel",Some("main")=>"main",Some("screenshot")=>"screenshot",_=>return Err("Unknown self-test surface".into())};
    let view=app.get_webview(label).ok_or("Self-test surface unavailable")?;let url=view.url().map_err(|_|"Self-test location unavailable")?;
    if label=="mistral-web" {
        if url.scheme()!="https"||!matches!(url.host_str(),Some("chat.mistral.ai"|"vibe.mistral.ai"))||url.port_or_known_default()!=Some(443)||!url.username().is_empty()||url.password().is_some(){return Err("Self-test requires a trusted Mistral page".into());}
    } else if label=="screenshot" {super::super::screenshot_v4::require_dialog(&view).map_err(|_|"Self-test requires the bundled screenshot dialog")?;
    } else {super::super::require_local(&view).map_err(|_|"Self-test requires a bundled local page")?;}
    if command["action"]=="input"{
        if label!="mistral-web"{return Err("Self-test input is limited to the Mistral page".into());}
        return input(&view,command).await;
    }
    let script=command["script"].as_str().filter(|s|!s.is_empty()&&s.len()<=32768).ok_or("Self-test script missing or too large")?;
    let result=official_web::eval(&view,script).await.map_err(|_|"Self-test evaluation unavailable")?;
    Ok(json!(result))
}
pub fn start(app:&tauri::AppHandle){
    let Some(dir)=directory()else{return;};let handle=app.clone();
    tauri::async_runtime::spawn(async move{
        #[cfg(unix)] {use std::os::unix::fs::PermissionsExt;if std::fs::set_permissions(&dir,std::fs::Permissions::from_mode(0o700)).is_err(){return;}}
        tokio::time::sleep(std::time::Duration::from_millis(800)).await;
        let mut ready=window_report(&handle).unwrap_or_else(|e|json!({"error":e}));
        if let Some(map)=ready.as_object_mut(){map.insert("ready".into(),json!(true));map.insert("live_mistral".into(),json!(true));map.insert("offline_engine".into(),json!(false));}
        let _=save(&dir,0,true,ready);
        let mut last=0;
        for _ in 0..40000 {
            if handle.get_window("main").is_none(){return;}
            if std::fs::symlink_metadata(dir.join("STOP")).is_ok_and(|m|m.is_file()&&!m.file_type().is_symlink()){return;}
            let path=dir.join("command.json");
            let command=std::fs::symlink_metadata(&path).ok().filter(|m|m.is_file()&&!m.file_type().is_symlink()&&m.len()<=COMMAND_LIMIT).and_then(|_|std::fs::read(&path).ok()).filter(|b|b.len()<=COMMAND_LIMIT as usize).and_then(|b|serde_json::from_slice::<Value>(&b).ok());
            if let Some(command)=command {
                if let Some(id)=command["id"].as_u64().filter(|id|*id>last){
                    last=id;
                    let result=execute(&handle,&dir,&command).await;
                    let quit=command["action"]=="quit"&&result.is_ok();
                    let(ok,value)=match result{Ok(v)=>(true,v),Err(message)=>(false,json!({"error":message}))};
                    let _=save(&dir,id,ok,value);
                    if quit {tokio::time::sleep(std::time::Duration::from_millis(300)).await;handle.exit(0);return;}
                }
            }
            tokio::time::sleep(std::time::Duration::from_millis(250)).await;
        }
    });
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn the_engine_under_test_comes_from_the_source_tree(){
        let chosen=engine_source(Path::new("/usr/lib/VibeZ V4 Alpha/backend/standalone_engine.py"));
        assert_eq!(chosen,source_root().unwrap().join("backend/standalone_engine.py"));assert!(chosen.is_file());
    }
    #[test] fn directory_is_an_existing_private_artifact_child(){
        let root=std::env::temp_dir().join(format!("vibez-live-work-{}",std::process::id()));let child=root.join("self-test");
        std::fs::create_dir_all(child.join("workspace")).unwrap();
        assert_eq!(checked_dir(&child,&root),Some(child.clone()));assert!(checked_dir(&root,&root).is_none());
        assert!(checked_dir(Path::new("relative"),&root).is_none());assert!(checked_dir(&root.join("missing"),&root).is_none());
        assert_eq!(checked_dir(&child.join("workspace"),&child),Some(child.join("workspace")));
        save(&child,1,true,json!({"result":"ok"})).unwrap();
        assert_eq!(serde_json::from_slice::<Value>(&std::fs::read(child.join("result.json")).unwrap()).unwrap()["id"],1);
        #[cfg(unix)] {use std::os::unix::fs::PermissionsExt;assert_eq!(std::fs::metadata(child.join("result.json")).unwrap().permissions().mode()&0o777,0o600);}
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test] fn the_connector_count_accepts_work_chat_and_code_projects(){
        let uuid="0f0e0d0c-0b0a-4908-8706-050403020100";
        assert!(test_project_id(uuid));
        assert!(test_project_id(&format!("chat-{uuid}")));
        assert!(test_project_id(&format!("code-{uuid}")));
        assert!(!test_project_id(&format!("work-{uuid}")));
        assert!(!test_project_id("code-"));
        assert!(!test_project_id(""));
    }
    #[cfg(target_os="linux")]
    #[test] fn real_input_accepts_only_plain_text_known_keys_and_points(){
        assert!(matches!(parse_input(&json!({"kind":"text","text":"VibeZ test. OK"})),Ok(Input::Text(t)) if t=="VibeZ test. OK"));
        assert!(matches!(parse_input(&json!({"kind":"key","key":"Enter"})),Ok(Input::Key(_,0))));
        assert!(matches!(parse_input(&json!({"kind":"key","key":"Left","mods":["shift"]})),Ok(Input::Key(_,s)) if s==gtk::gdk::ModifierType::SHIFT_MASK.bits()));
        assert!(matches!(parse_input(&json!({"kind":"click","x":10.5,"y":20})),Ok(Input::Click(..))));
        for bad in [json!({"kind":"text","text":""}),json!({"kind":"text","text":"a\nb"}),json!({"kind":"key","key":"F4"}),json!({"kind":"key","key":"a","mods":["alt"]}),
            json!({"kind":"click","x":-1,"y":2}),json!({"kind":"click","x":1}),json!({"kind":"paste"})]{assert!(parse_input(&bad).is_err());}
    }
    #[test] fn consent_is_limited_to_the_official_console(){
        assert!(trusted_console(&"https://console.mistral.ai/codestral?process_id=x".parse().unwrap()));
        for raw in ["https://evil.test/","http://console.mistral.ai/","https://user:secret@console.mistral.ai/","https://console.mistral.ai:444/"]{assert!(!trusted_console(&raw.parse().unwrap()));}
    }
}
