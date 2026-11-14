//! Open only the native-confirmed linked folder, never a renderer-supplied path.
use super::*;
use std::path::{Component,Path,PathBuf};

#[derive(Clone,Debug,PartialEq,Eq)]
struct FolderBinding {project:String,revision:String,folder:PathBuf,folders:Vec<(String,PathBuf)>}
#[derive(Default)]
pub struct OverviewState {binding:Mutex<Option<FolderBinding>>}

fn valid_project(value:&str)->bool {
    let id=value.strip_prefix("code-").or_else(||value.strip_prefix("chat-")).unwrap_or(value);
    id.len()==36&&id.chars().enumerate().all(|(i,c)|if [8,13,18,23].contains(&i){c=='-'}else{c.is_ascii_hexdigit()})
}
fn valid_folder(path:&Path)->bool {
    path.is_absolute()&&!path.components().any(|part|matches!(part,Component::ParentDir|Component::CurDir))
        &&!path.as_os_str().is_empty()
}
fn snapshot(event:&Value)->Option<FolderBinding> {
    if event["type"]!="web_connector" {return None;}
    let project=event["project"]["id"].as_str().filter(|id|valid_project(id))?;
    let revision=event["import_binding"].as_str().filter(|value|value.len()==64&&value.bytes().all(|c|c.is_ascii_hexdigit()))?;
    let raw=event["folder"].as_str().filter(|value|!value.contains('\0'))?;
    let folder=PathBuf::from(raw);
    if !valid_folder(&folder){return None;}
    let mut folders=Vec::new();
    if let Some(entries)=event.get("folders") {
        let entries=entries.as_array()?;
        if entries.is_empty()||entries.len()>16{return None;}
        for entry in entries {
            let id=entry["id"].as_str().filter(|id|id.len()==32&&id.bytes().all(|c|c.is_ascii_hexdigit()))?;
            let raw=entry["path"].as_str().filter(|path|!path.contains('\0'))?;
            let path=PathBuf::from(raw);
            if !valid_folder(&path)||folders.iter().any(|(other,_)|other==id){return None;}
            folders.push((id.to_owned(),path));
        }
        let target=event["target_folder_id"].as_str()?;
        if !folders.iter().any(|(id,path)|id==target&&path==&folder){return None;}
    }
    Some(FolderBinding{project:project.into(),revision:revision.into(),folder,folders})
}
pub fn observe(app:&tauri::AppHandle,event:&Value) {
    if event["type"]!="web_connector"&&!(event["type"]=="error"&&event["code"]=="engine_stopped"){return;}
    if let Ok(mut binding)=app.state::<OverviewState>().binding.lock(){*binding=snapshot(event);};
}
fn current(app:&tauri::AppHandle,project:&str,revision:&str)->Result<FolderBinding,String> {
    let binding=app.state::<OverviewState>().binding.lock().map_err(err)?.clone().ok_or("Link a workspace to this project first")?;
    if binding.project!=project||binding.revision!=revision {return Err("The project folder has changed. Try again.".into());}
    let view=app.get_webview("mistral-web").ok_or("Mistral has not loaded yet")?;
    let url=view.url().map_err(err)?;
    if !official_web::confirmed_project(app,&url,project){return Err("The Mistral project changed. Open the workspace folder again.".into());}
    Ok(binding)
}
fn selected_folder(mut binding:FolderBinding,id:Option<&str>)->Result<FolderBinding,String> {
    if let Some(id)=id {
        binding.folder=binding.folders.iter().find(|(known,_)|known==id).map(|(_,path)|path.clone())
            .ok_or("The chosen workspace folder is no longer linked")?;
    }
    Ok(binding)
}
fn canonical_folder(folder:&Path)->Result<PathBuf,String> {
    if !valid_folder(folder){return Err("The linked workspace folder is not valid".into());}
    let metadata=std::fs::symlink_metadata(folder).map_err(|_|"The linked workspace folder is not available")?;
    if metadata.file_type().is_symlink()||!metadata.is_dir(){return Err("The linked workspace folder was replaced. Link the folder again.".into());}
    let canonical=folder.canonicalize().map_err(|_|"The linked workspace folder is not available")?;
    if canonical!=folder {return Err("The linked workspace folder is redirected. Link the folder again.".into());}
    Ok(canonical)
}
fn geometry(safe:Screen,scale:f64,session:&str)->Result<String,String> {
    // Nemo's GTK geometry is global X11 logical coordinates. Negative positions
    // use edge-relative semantics, so those layouts fail closed here.
    if session!="x11"||!scale.is_finite()||(scale-1.).abs()>f64::EPSILON||safe.x<0||safe.y<0 {
        return Err("The workspace cannot be opened safely on screen 1 with this screen setting".into());
    }
    let width=safe.width.saturating_sub(240).min(1000);
    let height=safe.height.saturating_sub(220).min(720);
    if width<640||height<480{return Err("Screen 1 is too small to open the workspace folder safely".into());}
    let x=safe.x.checked_add(100).ok_or("Invalid screen position")?;
    let y=safe.y.checked_add(100).ok_or("Invalid screen position")?;
    Ok(format!("{width}x{height}+{x}+{y}"))
}
fn arguments(folder:&Path,geometry:&str)->Result<Vec<String>,String> {
    let uri=url::Url::from_directory_path(folder).map_err(|_|"The workspace cannot be opened")?;
    Ok(vec!["--no-default-window".into(),format!("--geometry={geometry}"),"--".into(),uri.into()])
}
fn desktop_uri(folder:&Path)->Result<String,String> {
    if !valid_folder(folder){return Err("The linked workspace folder is not valid".into());}
    url::Url::from_directory_path(folder).map(String::from).map_err(|_|"The workspace cannot be opened".into())
}

#[tauri::command]
pub async fn project_open_folder(webview:Webview,app:tauri::AppHandle,project_id:String,binding:String,folder_id:Option<String>)->Result<(),String> {
    require_local(&webview)?;
    if webview.label()!="connector-panel" {return Err("Use the project panel".into());}
    let state=app.state::<official_web::WebState>();
    let _gate=state.gate.lock().await;
    official_web::sync(&app).await?;
    let selected=selected_folder(current(&app,&project_id,&binding)?,folder_id.as_deref())?;
    #[cfg(not(target_os="linux"))]
    {
        let latest=selected_folder(current(&app,&project_id,&binding)?,folder_id.as_deref())?;
        if latest!=selected{return Err("The project folder has changed. Try again.".into());}
        platform_desktop::open_folder(&app,&canonical_folder(&latest.folder)?)
    }
    #[cfg(target_os="linux")]
    {
    let handle=app.clone();let(tx,rx)=tokio::sync::oneshot::channel();
    app.run_on_main_thread(move ||{
        let result=(||{
            let latest=selected_folder(current(&handle,&project_id,&binding)?,folder_id.as_deref())?;
            if latest!=selected{return Err("The project folder has changed. Try again.".into());}
            let safe=screen(&handle)?;
            let window=handle.get_window("main").ok_or("Het VibeZ-venster ontbreekt")?;
            let folder=canonical_folder(&latest.folder)?;
            if safe_output()?.is_some() {
                let scale=window.scale_factor().map_err(err)?;
                let placement=geometry(safe,scale,&std::env::var("XDG_SESSION_TYPE").unwrap_or_default())?;
                if !Path::new("/usr/bin/nemo").is_file(){return Err("The safe screen choice needs the Nemo file manager to open the folder".into());}
                // Only the explicit personal safety mode uses a manager whose
                // new-window position is known before show. Never reuse an
                // existing file-manager window on another monitor.
                let mut child=Command::new("/usr/bin/nemo").args(arguments(&folder,&placement)?)
                    .env("GDK_BACKEND","x11").env_remove("DESKTOP_STARTUP_ID")
                    .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).spawn()
                    .map_err(|_|"The workspace could not be opened")?;
                std::thread::spawn(move ||{let _=child.wait();});
            } else {
                // GTK supplies the parent-window activation context and GIO
                // opens the registered desktop file manager. Inside Flatpak
                // this uses the desktop portal, without host command access.
                let parent=window.gtk_window().map_err(err)?;
                gtk::show_uri_on_window(Some(&parent),&desktop_uri(&folder)?,0)
                    .map_err(|_|"The workspace could not be opened in the file manager")?;
            }
            Ok(())
        })();let _=tx.send(result);
    }).map_err(err)?;
    rx.await.map_err(err)?
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const ID:&str="229ee257-4177-4f98-969c-3055311c7cae";
    fn fixture_folder()->&'static str {
        #[cfg(target_os="windows")] {r"C:\fixtures\Alpha"}
        #[cfg(not(target_os="windows"))] {"/fixtures/Alpha"}
    }
    fn metadata()->Value {json!({"type":"web_connector","project":{"id":ID,"name":"Project"},"folder":fixture_folder(),"import_binding":"a".repeat(64),"token":"credential-not-retained","url":"https://fixture.invalid/mcp"})}
    #[test]
    fn folder_metadata_is_exact_and_contains_no_authentication_or_renderer_paths() {
        let event=metadata();let value=snapshot(&event).unwrap();
        assert_eq!(value.project,ID);assert_eq!(value.folder,PathBuf::from(fixture_folder()));assert!(!format!("{value:?}").contains("credential-not-retained"));assert!(!format!("{value:?}").contains("fixture.invalid"));
        for (field,data) in [("folder",json!("https://example.org/")),("folder",json!("relative/folder")),("folder",json!("/fixtures/../Other")),("folder",Value::Null),("import_binding",json!("invalid")),("type",json!("web_auto"))] {
            let mut invalid=event.clone();invalid[field]=data;assert!(snapshot(&invalid).is_none());
        }
        let mut invalid=event.clone();invalid["project"]["id"]=json!("/fixtures/Other");assert!(snapshot(&invalid).is_none());
    }
    #[test]
    fn workspace_opening_retains_exact_work_code_or_conversation_binding() {
        for prefix in ["", "code-", "chat-"] {
            let id=format!("{prefix}{ID}");let mut event=metadata();event["project"]["id"]=json!(id);
            assert_eq!(snapshot(&event).unwrap().project,id);
        }
        for prefix in ["chat-code-", "code-chat-", "chat-chat-", "conversation-"] {
            let mut event=metadata();event["project"]["id"]=json!(format!("{prefix}{ID}"));assert!(snapshot(&event).is_none());
        }
    }
    #[test]
    fn opening_a_listed_folder_never_changes_the_destination_or_accepts_a_renderer_path() {
        let mut event=metadata();
        let second=PathBuf::from(fixture_folder()).join("Second");
        event["folders"]=json!([{"id":"1".repeat(32),"path":fixture_folder()},{"id":"2".repeat(32),"path":second}]);
        event["target_folder_id"]=json!("1".repeat(32));
        let original=snapshot(&event).unwrap();
        assert_eq!(selected_folder(original.clone(),Some(&"2".repeat(32))).unwrap().folder,second);
        assert_eq!(original.folder,PathBuf::from(fixture_folder()));
        for invalid in ["3".repeat(32),fixture_folder().to_owned(),"../escape".into(),String::new()] {
            assert!(selected_folder(original.clone(),Some(&invalid)).is_err());
        }
        assert_eq!(selected_folder(original.clone(),None).unwrap(),original);
        let mut duplicate=event.clone();duplicate["folders"][1]["id"]=json!("1".repeat(32));assert!(snapshot(&duplicate).is_none());
        let mut unlisted=event.clone();unlisted["target_folder_id"]=json!("3".repeat(32));assert!(snapshot(&unlisted).is_none());
        let mut invalid=event.clone();invalid["folders"][1]["path"]=json!("../escape");assert!(snapshot(&invalid).is_none());
        let mut invalid=event;invalid["folder"]=json!(second);assert!(snapshot(&invalid).is_none());
    }
    #[test]
    fn nemo_geometry_is_inside_safe_screen_before_show_or_fails_closed() {
        let screen=Screen{x:0,y:0,width:2560,height:1440};
        assert_eq!(geometry(screen,1.,"x11").unwrap(),"1000x720+100+100");
        for (s,scale,session) in [(Screen{x:-2560,..screen},1.,"x11"),(screen,2.,"x11"),(screen,1.,"wayland"),(screen,f64::NAN,"x11"),(Screen{width:800,height:600,..screen},1.,"x11")] {
            assert!(geometry(s,scale,session).is_err());
        }
    }
    #[test]
    #[cfg(target_os="linux")]
    fn manager_arguments_are_a_new_window_with_encoded_local_uri_and_no_shell() {
        let args=arguments(Path::new("/fixtures/folder #?;$(value)"),"1000x720+100+100").unwrap();
        assert_eq!(&args[..3],["--no-default-window","--geometry=1000x720+100+100","--"]);
        assert!(args[3].starts_with("file:///fixtures/"));assert!(args[3].contains("%20"));assert!(args[3].contains("%23"));assert!(args[3].contains("%3F"));
        assert!(!args.iter().any(|arg|matches!(arg.as_str(),"--existing-window"|"--tabs"|"sh"|"-c"|"xdg-open")));
    }
    #[test]
    #[cfg(target_os="linux")]
    fn desktop_file_manager_uses_a_local_encoded_uri_without_nemo_or_screen_assumptions() {
        let uri=desktop_uri(Path::new("/run/user/1000/doc/allowed/map #?;$(value)")).unwrap();
        assert!(uri.starts_with("file:///run/user/1000/doc/allowed/"));
        assert!(uri.contains("%20")&&uri.contains("%23")&&uri.contains("%3F"));
        assert!(!uri.contains("nemo"));
        for path in [Path::new("relative"),Path::new("/tmp/../other")] {assert!(desktop_uri(path).is_err());}
    }
    #[test]
    fn opening_only_accepts_a_current_real_canonical_directory() {
        let root=std::env::temp_dir().join(format!("vibez-overview-folder-{}",std::process::id()));
        std::fs::create_dir_all(&root).unwrap();let canonical=root.canonicalize().unwrap();
        assert_eq!(canonical_folder(&canonical).unwrap(),canonical);
        let file=root.join("file.txt");std::fs::write(&file,"Fixture").unwrap();assert!(canonical_folder(&file).is_err());
        #[cfg(unix)] {let alias=root.join("alias");std::os::unix::fs::symlink(&canonical,&alias).unwrap();assert!(canonical_folder(&alias).is_err());}
        assert!(canonical_folder(&root.join("missing")).is_err());std::fs::remove_dir_all(root).unwrap();
    }
}
