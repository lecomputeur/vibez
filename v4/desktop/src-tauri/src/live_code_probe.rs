//! Explicit local live-test driver. Entirely excluded from production builds.
//! It does not start sessions, grant access or inspect credentials by itself.
use super::*;
use std::path::{Path,PathBuf};
const COMMAND_LIMIT:u64=65536;
const RESULT_LIMIT:usize=65536;
static PENDING_FIXTURE:Mutex<Option<PathBuf>>=Mutex::new(None);
pub fn requested()->bool {std::env::args().any(|a|a=="--live-code-probe")}
fn checked_dir(raw:&Path,root:&Path)->Option<PathBuf>{
    if !raw.is_absolute(){return None;}
    let raw=raw.canonicalize().ok()?;let root=root.canonicalize().ok()?;
    if raw==root||!raw.starts_with(&root)||!raw.is_dir(){return None;}
    Some(raw)
}
fn directory()->Option<PathBuf>{
    if !requested()||std::env::args().any(|a|a=="--standalone-smoke-test"||a=="--live-connector-self-test"){return None;}
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).parent()?.parent()?.join("artifacts");
    checked_dir(&PathBuf::from(std::env::var_os("VIBEZ4_CODE_PROBE_DIR")?),&root)
}
pub fn enabled()->bool {directory().is_some()}
fn isolated_data(dir:&Path)->Result<PathBuf,String>{
    let data=dir.join("backend-state");
    if std::fs::symlink_metadata(&data).is_ok_and(|m|m.file_type().is_symlink()) {return Err("The probe backend directory is redirected".into());}
    std::fs::create_dir_all(&data).map_err(err)?;
    if data.canonicalize().map_err(err)?!=data {return Err("The probe backend directory is redirected".into());}
    Ok(data)
}
pub fn engine_data(original:&Path)->Result<PathBuf,String>{
    if !requested(){return Ok(original.into());}
    isolated_data(&directory().ok_or("A private Code probe directory is required")?)
}
pub fn legacy_path(original:&Path)->Result<PathBuf,String>{
    if !requested(){return Ok(original.into());}
    Ok(directory().ok_or("A private Code probe directory is required")?.join("no-legacy-projects.json"))
}
fn save(dir:&Path,id:u64,ok:bool,result:Value)->Result<(),String>{
    let mut data=serde_json::to_vec(&json!({"id":id,"ok":ok,"result":result})).map_err(|_|"Probe result invalid")?;
    if data.len()>RESULT_LIMIT {data=serde_json::to_vec(&json!({"id":id,"ok":false,"result":{"error":"Probe result too large"}})).unwrap();}
    let temporary=dir.join(format!("result-{}-{id}.tmp",std::process::id()));
    let mut options=std::fs::OpenOptions::new();options.write(true).create_new(true);
    #[cfg(unix)] {use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
    let mut file=options.open(&temporary).map_err(|_|"Probe output unavailable")?;
    file.write_all(&data).map_err(|_|"Probe output unavailable")?;file.sync_all().map_err(|_|"Probe output unavailable")?;
    std::fs::rename(temporary,dir.join("result.json")).map_err(|_|"Probe output unavailable".to_owned())
}
fn safe_window(app:&tauri::AppHandle)->Result<(),String>{
    let safe=screen(app)?;let w=app.get_window("main").ok_or("Probe main window unavailable")?;
    let p=w.outer_position().map_err(|_|"Probe geometry unavailable")?;let size=w.outer_size().map_err(|_|"Probe geometry unavailable")?;
    if p.x<safe.x||p.y<safe.y||p.x as i64+size.width as i64>safe.x as i64+safe.width as i64||p.y as i64+size.height as i64>safe.y as i64+safe.height as i64 {return Err("Probe main window outside screen 1".into());}
    Ok(())
}
fn fixture_dir(dir:&Path,name:&str)->Option<PathBuf>{
    if !matches!(name,"Alpha"|"Beta"){return None;}
    let root=dir.join("fixtures");if root.canonicalize().ok()?!=root{return None;}
    let path=root.join(name);if path.canonicalize().ok()?!=path||!path.is_dir(){return None;}
    Some(path)
}
fn choose_fixture(dir:&Path,name:&str)->Result<Value,String>{
    let path=fixture_dir(dir,name).ok_or("Probe fixture folder unavailable")?;
    *PENDING_FIXTURE.lock().map_err(|_|"Probe fixture queue unavailable")?=Some(path);
    Ok(json!({"queued":true}))
}
pub fn observe_dialog(dialog:&gtk::FileChooserDialog,safe:Screen,kind:&str){
    if !enabled()||kind!="folder"||dialog.action()!=gtk::FileChooserAction::SelectFolder{return;}
    let Some(dir)=directory()else{return;};
    let Some(path)=PENDING_FIXTURE.lock().ok().and_then(|mut p|p.take())else{return;};
    if !["Alpha","Beta"].iter().any(|name|fixture_dir(&dir,name).as_ref()==Some(&path)){return;}
    if !dialog.set_current_folder(&path){return;}
    let dialog=dialog.clone();
    // Called during normal dialog creation, before its nested GTK run loop.
    // No Tauri main-thread dispatch is attempted while a picker is running.
    gtk::glib::timeout_add_local_once(std::time::Duration::from_millis(600),move ||{
        let(x,y)=dialog.position();let(w,h)=dialog.size();
        let on_safe=x>=safe.x&&y>=safe.y&&x+w<=safe.x+safe.width as i32&&y+h<=safe.y+safe.height as i32;
        let selected=dialog.is_visible()&&on_safe&&guard_game(safe).is_ok()&&dialog.current_folder().as_ref()==Some(&path)&&dialog.filename().as_ref()==Some(&path);
        if selected {dialog.response(gtk::ResponseType::Accept);}
    });
}
async fn consent(app:&tauri::AppHandle)->Result<Value,String>{
    let labels=app.state::<Bridge>().login_labels.lock().map_err(|_|"Probe popup list unavailable")?.clone();
    let mut clicked=0;
    for label in labels {
        let Some(view)=app.get_webview(&label)else{continue;};let Ok(url)=view.url()else{continue;};
        if url.scheme()!="https"||url.host_str()!=Some("console.mistral.ai")||url.port_or_known_default()!=Some(443)||!url.username().is_empty()||url.password().is_some(){continue;}
        let script=r#"(()=>{const visible=e=>e.getClientRects().length>0&&!e.disabled;if([...document.querySelectorAll('input[type=password],input[type=email],input[autocomplete=username],input[autocomplete=current-password]')].some(visible))return 'needs_sign_in';const buttons=[...document.querySelectorAll('button,[role=button]')].filter(e=>visible(e)&&['authorize','autoriseren','toestaan','allow'].includes((e.innerText||e.textContent||'').replace(/\s+/g,' ').trim().toLowerCase()));if(buttons.length!==1)return 'waiting';buttons[0].click();return 'clicked';})()"#;
        if official_web::eval(&view,script).await.unwrap_or_default()=="clicked" {clicked+=1;}
    }
    Ok(json!({"consent_clicked":clicked}))
}
async fn execute(app:&tauri::AppHandle,dir:&Path,command:&Value)->Result<Value,String>{
    safe_window(app)?;
    match command["action"].as_str() {
        Some("choose_fixture_folder")=>return choose_fixture(dir,command["name"].as_str().ok_or("Probe fixture name missing")?),
        Some("consent")=>return consent(app).await,
        None|Some("eval")=>{},
        _=>return Err("Unknown probe action".into()),
    }
    let label=match command["surface"].as_str(){Some("mistral")=>"mistral-web",Some("panel")=>"connector-panel",Some("main")=>"main",_=>return Err("Unknown probe surface".into())};
    let view=app.get_webview(label).ok_or("Probe surface unavailable")?;let url=view.url().map_err(|_|"Probe location unavailable")?;
    if label=="mistral-web" {
        if url.scheme()!="https"||!matches!(url.host_str(),Some("chat.mistral.ai"|"vibe.mistral.ai"))||url.port_or_known_default()!=Some(443)||!url.username().is_empty()||url.password().is_some(){return Err("Probe requires a trusted Mistral page".into());}
    } else {super::super::require_local(&view).map_err(|_|"Probe requires a bundled local page")?;}
    let script=command["script"].as_str().filter(|s|!s.is_empty()&&s.len()<=32768).ok_or("Probe script missing or too large")?;
    let result=official_web::eval(&view,script).await.map_err(|_|"Probe evaluation unavailable")?;
    Ok(json!(result))
}
pub fn start(app:&tauri::AppHandle){
    let Some(dir)=directory()else{return;};let handle=app.clone();
    tauri::async_runtime::spawn(async move{
        #[cfg(unix)] {use std::os::unix::fs::PermissionsExt;if std::fs::set_permissions(&dir,std::fs::Permissions::from_mode(0o700)).is_err(){return;}}
        let _=save(&dir,0,true,json!({"ready":true,"version":env!("CARGO_PKG_VERSION"),"pid":std::process::id(),"offline_engine":false}));
        let mut last=0;
        for _ in 0..12000 {
            if handle.get_window("main").is_none(){return;}
            if std::fs::symlink_metadata(dir.join("STOP")).is_ok_and(|m|m.is_file()&&!m.file_type().is_symlink()){return;}
            let path=dir.join("command.json");
            let command=std::fs::symlink_metadata(&path).ok().filter(|m|m.is_file()&&!m.file_type().is_symlink()&&m.len()<=COMMAND_LIMIT).and_then(|_|std::fs::read(&path).ok()).filter(|b|b.len()<=COMMAND_LIMIT as usize).and_then(|b|serde_json::from_slice::<Value>(&b).ok());
            if let Some(command)=command {
                if let Some(id)=command["id"].as_u64().filter(|id|*id>last){
                    last=id;
                    let result=execute(&handle,&dir,&command).await;
                    let(ok,value)=match result{Ok(v)=>(true,v),Err(message)=>(false,json!({"error":message}))};
                    let _=save(&dir,id,ok,value);
                }
            }
            tokio::time::sleep(std::time::Duration::from_millis(300)).await;
        }
    });
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn live_code_backend_is_private_and_rejects_a_redirected_state_directory(){
        let dir=std::env::temp_dir().join(format!("vibez-live-code-private-{}",std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();let dir=dir.canonicalize().unwrap();
        let data=isolated_data(&dir).unwrap();assert_eq!(data,dir.join("backend-state"));
        assert!(data.is_dir());std::fs::remove_dir(&data).unwrap();
        let outside=dir.join("outside");std::fs::create_dir(&outside).unwrap();
        std::os::unix::fs::symlink(&outside,&data).unwrap();assert!(isolated_data(&dir).is_err());
        std::fs::remove_file(&data).unwrap();std::fs::remove_dir_all(&dir).unwrap();
    }
    #[test] fn directory_is_existing_private_artifact_child_and_fixture_names_are_fixed(){
        let root=std::env::temp_dir().join(format!("vibez-code-probe-{}",std::process::id()));let child=root.join("probe");
        std::fs::create_dir_all(child.join("fixtures/Alpha")).unwrap();
        assert_eq!(checked_dir(&child,&root),Some(child.clone()));assert!(checked_dir(&root,&root).is_none());assert!(checked_dir(Path::new("relative"),&root).is_none());assert!(checked_dir(&root.join("missing"),&root).is_none());
        assert!(fixture_dir(&child,"Alpha").is_some());assert!(fixture_dir(&child,"Beta").is_none());assert!(fixture_dir(&child,"../Alpha").is_none());
        assert_eq!(choose_fixture(&child,"Alpha").unwrap()["queued"],true);
        assert_eq!(PENDING_FIXTURE.lock().unwrap().take(),fixture_dir(&child,"Alpha"));
        assert!(choose_fixture(&child,"../Alpha").is_err());assert!(PENDING_FIXTURE.lock().unwrap().is_none());
        save(&child,1,true,json!({"result":"ok"})).unwrap();assert_eq!(serde_json::from_slice::<Value>(&std::fs::read(child.join("result.json")).unwrap()).unwrap()["id"],1);
        #[cfg(unix)] {use std::os::unix::fs::PermissionsExt;assert_eq!(std::fs::metadata(child.join("result.json")).unwrap().permissions().mode()&0o777,0o600);}
        std::fs::remove_dir_all(root).unwrap();
    }
}
