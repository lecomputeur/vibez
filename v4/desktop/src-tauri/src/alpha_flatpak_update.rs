//! Flatpak's own update portal: a persistent monitor, remembered consent and
//! atomic deployment of this app's existing origin. Active chats are never
//! restarted and no host filesystem or command-spawn permission is requested.
use gtk::{gio, glib};
use gtk::prelude::*;
use glib::variant::ToVariant;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{cell::RefCell, ffi::{c_char,c_void,CStr}, path::{Path,PathBuf}, sync::{Mutex,OnceLock}};
use tauri::{AppHandle,Emitter,EventTarget,Manager};

const APP_ID:&str="nl.lecomputeur.vibez4.alpha";
const BUS:&str="org.freedesktop.portal.Flatpak";
const PORTAL:&str="/org/freedesktop/portal/Flatpak";
const MONITOR:&str="org.freedesktop.portal.Flatpak.UpdateMonitor";
#[derive(Clone,Serialize,Deserialize)]
#[serde(default)]
struct Preference { automatic:bool, permission_confirmed:bool }
impl Default for Preference {fn default()->Self{Self{automatic:true,permission_confirmed:false}}}
struct MonitorState {
    started:bool, connection:Option<gio::DBusConnection>, handle:Option<String>,
    file:Option<PathBuf>, prefs:Preference, phase:&'static str, progress:u32,
    running:String, local:String, remote:String, target:Option<String>, busy:bool, error:String,
}
impl Default for MonitorState {fn default()->Self{Self{started:false,connection:None,handle:None,file:None,prefs:Preference::default(),phase:"not_flatpak",progress:0,running:String::new(),local:String::new(),remote:String::new(),target:None,busy:false,error:String::new()}}}
fn shared()->&'static Mutex<MonitorState>{static STATE:OnceLock<Mutex<MonitorState>>=OnceLock::new();STATE.get_or_init(||Mutex::new(MonitorState::default()))}
fn active_flatpak()->bool{Path::new("/.flatpak-info").is_file()&&std::env::var("FLATPAK_ID").ok().as_deref()==Some(APP_ID)}
fn restricted_screen()->bool{std::env::var_os("VIBEZ_SAFE_OUTPUT").is_some()}
fn valid_commit(value:&str)->bool{value.len()==64&&value.bytes().all(|b|b.is_ascii_hexdigit())}
fn monitor_path(value:&str)->bool{value.starts_with("/org/freedesktop/portal/Flatpak/update_monitor/")&&value.len()<=512&&value.bytes().all(|b|b.is_ascii_alphanumeric()||matches!(b,b'/'|b'_'))}
fn available(s:&MonitorState)->bool{valid_commit(&s.remote)&&s.remote!=s.local}
fn restart_needed(s:&MonitorState)->bool{valid_commit(&s.local)&&valid_commit(&s.running)&&s.local!=s.running}
fn status_for(s:&MonitorState)->&'static str{
    if s.busy{return "installing";}
    if restart_needed(s){return "restart_required";}
    if !s.prefs.automatic{return "disabled";}
    if available(s)&&!s.prefs.permission_confirmed{return "consent_required";}
    if available(s){return "available";}
    "ready"
}
pub fn state()->Value{
    let Ok(s)=shared().lock()else{return json!({"kind":"flatpak","phase":"error","error":"Update state unavailable"});};
    json!({"kind":"flatpak","channel":"alpha","current":env!("CARGO_PKG_VERSION"),
        "phase":s.phase,"status":s.phase,"automatic":s.prefs.automatic,
        "consent_required":!s.prefs.permission_confirmed,"progress":s.progress,"busy":s.busy,
        "available":available(&s),"restart_required":restart_needed(&s),"error":s.error,
        "running_commit":s.running,"local_commit":s.local,"remote_commit":s.remote})
}
fn announce(app:&AppHandle){let value=state();for label in ["main","connector-panel"]{let _=app.emit_to(EventTarget::Webview{label:label.into()},"alpha-flatpak-update",value.clone());}}
fn error(app:&AppHandle,phase:&'static str,message:impl ToString){if let Ok(mut s)=shared().lock(){s.busy=false;s.phase=phase;s.error=message.to_string().chars().take(500).collect();}glib::idle_add_once(release_parent);announce(app);}
fn read_preference(file:&Path)->Preference{
    std::fs::symlink_metadata(file).ok().filter(|m|m.is_file()&&!m.file_type().is_symlink()&&m.len()<=4096)
        .and_then(|_|std::fs::read(file).ok()).and_then(|raw|serde_json::from_slice(&raw).ok()).unwrap_or_default()
}
fn save_preference(file:&Path,prefs:&Preference)->Result<(),String>{
    use std::io::Write;use std::os::unix::fs::OpenOptionsExt;
    let temporary=file.with_extension(format!("{}.tmp",std::process::id()));
    let mut output=std::fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(&temporary).map_err(|e|e.to_string())?;
    let result=(||{output.write_all(&serde_json::to_vec(prefs).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;output.sync_all().map_err(|e|e.to_string())?;std::fs::rename(&temporary,file).map_err(|e|e.to_string())})();
    if result.is_err(){let _=std::fs::remove_file(&temporary);}result
}
fn persist()->Result<(),String>{let s=shared().lock().map_err(|_|"Update state unavailable")?;if let Some(file)=&s.file{save_preference(file,&s.prefs)}else{Ok(())}}
fn dictionary(parameters:&glib::Variant)->Option<glib::VariantDict>{
    if parameters.n_children()!=1{return None;}let value=parameters.child_value(0);(value.type_().as_str()=="a{sv}").then(||glib::VariantDict::new(Some(&value)))
}
fn string_field(dict:&glib::VariantDict,key:&str)->Option<String>{dict.lookup::<String>(key).ok().flatten()}
fn number_field(dict:&glib::VariantDict,key:&str)->Option<u32>{dict.lookup::<u32>(key).ok().flatten()}
fn merge_commits(s:&mut MonitorState,dict:&glib::VariantDict){
    for (key,target) in [("running-commit",&mut s.running),("local-commit",&mut s.local),("remote-commit",&mut s.remote)]{
        if let Some(value)=string_field(dict,key).filter(|v|valid_commit(v)){*target=value;}
    }
}
fn progress(s:&mut MonitorState,dict:&glib::VariantDict)->bool{
    s.progress=number_field(dict,"progress").unwrap_or(s.progress).min(100);
    match number_field(dict,"status"){
        Some(0)=>{s.busy=true;s.phase="installing";false},
        Some(1)|Some(2)=>{s.busy=false;s.prefs.permission_confirmed=true;s.error.clear();if number_field(dict,"status")==Some(2){if let Some(target)=s.target.take(){s.local=target;}}else{s.target=None;}s.phase=status_for(s);true},
        Some(3)=>{s.busy=false;s.target=None;s.phase="error";s.error=string_field(dict,"error_message").unwrap_or_else(||"Flatpak update failed".into()).chars().take(500).collect();let denied=string_field(dict,"error").is_some_and(|e|e.ends_with(".AccessDenied"));if denied{s.prefs.permission_confirmed=false;}denied},
        _=>false,
    }
}
fn options()->glib::Variant{glib::VariantDict::new(None).end()}
fn observe(app:&AppHandle,connection:&gio::DBusConnection,handle:&str){
    let app_update=app.clone();
    connection.signal_subscribe(Some(BUS),Some(MONITOR),Some("UpdateAvailable"),Some(handle),None,gio::DBusSignalFlags::NONE,move|_,_,_,_,_,parameters|{
        let Some(dict)=dictionary(parameters)else{return;};
        let auto=if let Ok(mut s)=shared().lock(){merge_commits(&mut s,&dict);s.error.clear();s.phase=status_for(&s);available(&s)&&s.prefs.automatic&&s.prefs.permission_confirmed&&!s.busy}else{false};
        announce(&app_update);if auto{let _=request_update(&app_update);}
    });
    let app_progress=app.clone();
    connection.signal_subscribe(Some(BUS),Some(MONITOR),Some("Progress"),Some(handle),None,gio::DBusSignalFlags::NONE,move|_,_,_,_,_,parameters|{
        let Some(dict)=dictionary(parameters)else{return;};
        let save=if let Ok(mut s)=shared().lock(){progress(&mut s,&dict)}else{false};
        if save{if let Err(e)=persist(){error(&app_progress,"error",e);return;}}
        if number_field(&dict,"status").is_some_and(|status|status!=0){release_parent();}
        announce(&app_progress);
    });
}
/// Called after GTK/Tauri setup. It creates no UI and asks for no permission.
pub fn start(app:&AppHandle){
    if !active_flatpak(){return;}
    let Ok(file)=app.path().app_config_dir().map(|p|p.join("alpha-flatpak-updates.json"))else{return;};
    if let Ok(mut s)=shared().lock(){if s.started{return;}s.started=true;s.phase="checking";s.prefs=read_preference(&file);s.file=Some(file);}else{return;}
    let app=app.clone();let handle=app.clone();
    if let Err(e)=app.run_on_main_thread(move||{
        let app=handle;
        gio::bus_get(gio::BusType::Session,None::<&gio::Cancellable>,move|result|{
            let connection=match result{Ok(c)=>c,Err(e)=>{error(&app,"error",e);return;}};
            // Keep this exact connection alive: monitor lifetime is bound to
            // the D-Bus caller, not merely to its returned object-path string.
            if let Ok(mut s)=shared().lock(){s.connection=Some(connection.clone());}
            let params=glib::Variant::tuple_from_iter([options()]);let retained=connection.clone();let app_reply=app.clone();
            connection.call(Some(BUS),PORTAL,BUS,"CreateUpdateMonitor",Some(&params),None,gio::DBusCallFlags::NONE,15000,None::<&gio::Cancellable>,move|result|{
                let value=match result{Ok(v)=>v,Err(e)=>{error(&app_reply,"error",e);return;}};
                let path=if value.n_children()==1{value.child_value(0).str().map(str::to_owned)}else{None};
                let Some(path)=path.filter(|p|monitor_path(p))else{error(&app_reply,"error","Flatpak returned an invalid update monitor");return;};
                observe(&app_reply,&retained,&path);
                if let Ok(mut s)=shared().lock(){s.handle=Some(path);s.phase=status_for(&s);}
                announce(&app_reply);
            });
        });
    }){error(&app,"error",e);}
}
/// Local UI only; root's Tauri wrapper must call require_local first.
pub fn set_automatic(app:&AppHandle,enabled:bool)->Result<Value,String>{
    if !active_flatpak(){return Err("This is not the Flatpak Alpha installation".into());}
    {let mut s=shared().lock().map_err(|_|"Update state unavailable")?;s.prefs.automatic=enabled;s.phase=status_for(&s);}
    persist()?;announce(app);
    let should_update={let s=shared().lock().map_err(|_|"Update state unavailable")?;enabled&&s.prefs.permission_confirmed&&available(&s)&&!s.busy};
    if should_update{request_update(app)?;}Ok(state())
}
/// The first call must follow an explicit local button. Success is remembered
/// locally as well as by the desktop portal; later monitor signals can update.
pub fn request_update(app:&AppHandle)->Result<Value,String>{
    if !active_flatpak(){return Err("This is not the Flatpak Alpha installation".into());}
    if restricted_screen(){error(app,"screen_restricted","A system dialog cannot be placed safely with the configured screen protection");return Err("The configured screen protection does not allow a Flatpak update window".into());}
    let (connection,path)={let mut s=shared().lock().map_err(|_|"Update state unavailable")?;if s.busy{return Ok(state_unlocked(&s));}
        let pair=(s.connection.clone().ok_or("Flatpak update monitor is not ready")?,s.handle.clone().ok_or("Flatpak update monitor is not ready")?);s.target=valid_commit(&s.remote).then(||s.remote.clone());s.busy=true;s.progress=0;s.phase="installing";s.error.clear();pair};
    announce(app);let task_app=app.clone();
    app.run_on_main_thread(move||parented_update(&task_app,connection,path)).map_err(|e|{error(app,"error",&e);e.to_string()})?;Ok(state())
}
fn state_unlocked(s:&MonitorState)->Value{json!({"kind":"flatpak","phase":s.phase,"automatic":s.prefs.automatic,"busy":s.busy,"progress":s.progress})}

// Portal parent handles are exported only while a request is outstanding.
thread_local!{static WAYLAND_PARENT:RefCell<Option<gtk::gdk::Window>>=const{RefCell::new(None)};}
#[link(name="gdk-3")]
extern "C"{
    fn gdk_x11_window_get_xid(window:*mut c_void)->std::os::raw::c_ulong;
    fn gdk_wayland_window_export_handle(window:*mut c_void,callback:Option<unsafe extern "C" fn(*mut c_void,*const c_char,*mut c_void)>,data:*mut c_void,destroy:Option<unsafe extern "C" fn(*mut c_void)>)->glib::ffi::gboolean;
    fn gdk_wayland_window_unexport_handle(window:*mut c_void);
}
struct Exported {app:AppHandle,connection:gio::DBusConnection,path:String}
unsafe extern "C" fn destroy_export(data:*mut c_void){if !data.is_null(){drop(Box::from_raw(data as *mut Exported));}}
unsafe extern "C" fn exported(_window:*mut c_void,handle:*const c_char,data:*mut c_void){
    if data.is_null(){return;}let context=&*(data as *const Exported);let app=context.app.clone();let connection=context.connection.clone();let path=context.path.clone();
    if handle.is_null(){error(&app,"error","The desktop did not provide an update window handle");return;}
    let raw=CStr::from_ptr(handle).to_string_lossy();
    if raw.is_empty()||raw.len()>1024||raw.chars().any(char::is_control){error(&app,"error","The desktop returned an invalid window handle");return;}
    call_update(&app,&connection,&path,&format!("wayland:{raw}"));
}
fn release_parent(){WAYLAND_PARENT.with(|p|{if let Some(window)=p.borrow_mut().take(){unsafe{gdk_wayland_window_unexport_handle(window.as_ptr() as *mut c_void);}}});}
fn parented_update(app:&AppHandle,connection:gio::DBusConnection,path:String){
    let parent=app.get_window("main").and_then(|w|w.gtk_window().ok()).and_then(|w|w.window());
    let Some(parent)=parent else{error(app,"error","The VibeZ update parent window is unavailable");return;};
    let backend=parent.type_().name();
    if backend.contains("X11"){
        let xid=unsafe{gdk_x11_window_get_xid(parent.as_ptr() as *mut c_void)};
        if xid==0{error(app,"error","The VibeZ X11 window handle is unavailable");return;}
        call_update(app,&connection,&path,&format!("x11:{xid:x}"));
    }else if backend.contains("Wayland"){
        let data=Box::into_raw(Box::new(Exported{app:app.clone(),connection,path}));
        WAYLAND_PARENT.with(|p|*p.borrow_mut()=Some(parent.clone()));
        let ok=unsafe{gdk_wayland_window_export_handle(parent.as_ptr() as *mut c_void,Some(exported),data as *mut c_void,Some(destroy_export))};
        if ok==0{WAYLAND_PARENT.with(|p|{p.borrow_mut().take();});unsafe{destroy_export(data as *mut c_void);}error(app,"error","This Wayland desktop cannot parent the update permission window");}
    }else{error(app,"error","This desktop cannot parent the update permission window");}
}
fn call_update(app:&AppHandle,connection:&gio::DBusConnection,path:&str,parent:&str){
    if restricted_screen(){error(app,"screen_restricted","The configured screen protection does not allow a Flatpak update window");return;}
    let parameters=glib::Variant::tuple_from_iter([parent.to_variant(),options()]);let app=app.clone();
    connection.call(Some(BUS),path,MONITOR,"Update",Some(&parameters),None,gio::DBusCallFlags::NONE,-1,None::<&gio::Cancellable>,move|result|{
        if let Err(e)=result{error(&app,"error",e);}
    });
}

#[cfg(test)] mod tests{
    use super::*;
    fn commits()->MonitorState{MonitorState{running:"a".repeat(64),local:"a".repeat(64),remote:"b".repeat(64),..Default::default()}}
    fn info(values:&[(&str,glib::Variant)])->glib::VariantDict{let dict=glib::VariantDict::new(None);for(key,value)in values{dict.insert_value(key,value);}dict}
    #[test]fn flatpak_monitor_paths_and_commits_are_bounded(){assert!(monitor_path("/org/freedesktop/portal/Flatpak/update_monitor/1_42/token"));assert!(!monitor_path("/somewhere/else"));assert!(!monitor_path("/org/freedesktop/portal/Flatpak/update_monitor/../bad"));assert!(!valid_commit("alpha.4"));assert!(valid_commit(&"a".repeat(64)));}
    #[test]fn first_update_requires_consent_and_never_claims_installed(){let s=commits();assert_eq!(status_for(&s),"consent_required");assert!(available(&s));assert!(!restart_needed(&s));}
    #[test]fn remembered_permission_enables_later_background_deployment(){let mut s=commits();s.prefs.permission_confirmed=true;assert_eq!(status_for(&s),"available");s.busy=true;s.target=Some(s.remote.clone());assert_eq!(status_for(&s),"installing");let done=info(&[("status",2u32.to_variant()),("progress",100u32.to_variant())]);assert!(progress(&mut s,&done));assert_eq!(s.phase,"restart_required");assert_eq!(s.running,"a".repeat(64));assert_eq!(s.local,"b".repeat(64));assert!(!available(&s));}
    #[test]fn errors_do_not_grant_permission_or_advance_local_commit(){let mut s=commits();let error=info(&[("status",3u32.to_variant()),("error_message","Denied".to_variant())]);assert!(!progress(&mut s,&error));assert!(!s.prefs.permission_confirmed);assert_eq!(s.local,s.running);assert_eq!(s.phase,"error");}
    #[test]fn partial_monitor_signals_preserve_previously_confirmed_commits(){let mut s=commits();let values=info(&[("remote-commit","c".repeat(64).to_variant()),("local-commit","invalid".to_variant())]);merge_commits(&mut s,&values);assert_eq!(s.local,"a".repeat(64));assert_eq!(s.remote,"c".repeat(64));}
    #[test]fn disabling_automatic_updates_retains_installed_restart_state(){let mut s=commits();s.prefs.automatic=false;assert_eq!(status_for(&s),"disabled");s.local=s.remote.clone();assert_eq!(status_for(&s),"restart_required");}
    #[test]fn newer_remote_during_download_is_not_falsely_reported_as_the_installed_target(){let mut s=commits();s.target=Some(s.remote.clone());s.remote="c".repeat(64);let done=info(&[("status",2u32.to_variant())]);assert!(progress(&mut s,&done));assert_eq!(s.local,"b".repeat(64));assert!(available(&s));}
    #[test]fn access_revocation_clears_remembered_portal_approval(){let mut s=commits();s.prefs.permission_confirmed=true;let denied=info(&[("status",3u32.to_variant()),("error","org.freedesktop.DBus.Error.AccessDenied".to_variant())]);assert!(progress(&mut s,&denied));assert!(!s.prefs.permission_confirmed);assert_eq!(s.local,s.running);}
    #[test]fn future_preference_fields_do_not_reenable_disabled_updates(){let prefs:Preference=serde_json::from_str(r#"{"automatic":false,"permission_confirmed":true,"future_field":42}"#).unwrap();assert!(!prefs.automatic);assert!(prefs.permission_confirmed);}
    #[test]fn preference_round_trip_stays_private_and_symlink_input_is_ignored(){use std::os::unix::{fs::{PermissionsExt,symlink}};let root=std::env::temp_dir().join(format!("vibez-flatpak-update-pref-{}",std::process::id()));std::fs::create_dir(&root).unwrap();let file=root.join("prefs.json");let prefs=Preference{automatic:true,permission_confirmed:true};save_preference(&file,&prefs).unwrap();assert!(read_preference(&file).permission_confirmed);assert_eq!(std::fs::metadata(&file).unwrap().permissions().mode()&0o777,0o600);symlink(&file,root.join("link")).unwrap();assert!(!read_preference(&root.join("link")).permission_confirmed);std::fs::remove_dir_all(root).unwrap();}
}
