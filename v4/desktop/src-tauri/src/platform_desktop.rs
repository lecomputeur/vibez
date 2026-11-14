//! Native desktop integration used by the Windows and macOS Alpha builds.
//! Picked paths stay native; remote Mistral pages never choose a filesystem path.
use super::*;
use std::path::{Component,Path,PathBuf};
use tauri_plugin_dialog::{DialogExt,FilePath};
use tauri_plugin_opener::OpenerExt;

fn path(value:FilePath)->Result<PathBuf,String> {
    value.into_path().map_err(err)
}
fn main_window(app:&tauri::AppHandle)->Result<tauri::Window,String> {
    screen(app)?;
    app.get_window("main").ok_or_else(||"Het VibeZ-venster ontbreekt".into())
}
fn create_child(parent:&Path,selected:&Path)->Result<PathBuf,String> {
    let parent=parent.canonicalize().map_err(err)?;
    let name=selected.file_name().ok_or("Give the new workspace a name")?;
    if Path::new(name).components().count()!=1 || !matches!(Path::new(name).components().next(),Some(Component::Normal(_))) {
        return Err("Give the new workspace a regular folder name".into());
    }
    let location=selected.parent().ok_or("Choose a location for the new workspace")?.canonicalize().map_err(err)?;
    if location!=parent {return Err("Create the new workspace directly in the chosen location".into());}
    let target=parent.join(name);
    // create_dir is exclusive: existing directories, files and links are never
    // overwritten by the Create workspace action.
    std::fs::create_dir(&target).map_err(|e|if e.kind()==std::io::ErrorKind::AlreadyExists {
        "This name already exists. Choose another name for the new workspace.".to_owned()
    } else {err(e)})?;
    created_child(&parent,&target)
}
pub async fn workspace(app:&tauri::AppHandle,create:bool)->Result<Option<PathBuf>,String> {
    let app=app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let window=main_window(&app)?;
        let title=classic_language::text(&app,if create {"chooseWorkspaceLocation"}else{"chooseWorkspace"});
        let chosen=app.dialog().file().set_parent(&window).set_title(title)
            .set_can_create_directories(true).blocking_pick_folder();
        let Some(chosen)=chosen else{return Ok(None);};
        let chosen=path(chosen)?;
        if !create{return Ok(Some(chosen));}
        let parent=chosen.canonicalize().map_err(err)?;
        let title=classic_language::text(&app,"createWorkspace");
        let chosen=app.dialog().file().set_parent(&window).set_title(title.clone())
            .set_directory(&parent).set_file_name(title).set_can_create_directories(true).blocking_save_file();
        let Some(chosen)=chosen else{return Ok(None);};
        create_child(&parent,&path(chosen)?).map(Some)
    }).await.map_err(err)?
}
pub async fn import_paths(app:&tauri::AppHandle,folders:bool)->Result<Vec<PathBuf>,String> {
    let app=app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let window=main_window(&app)?;
        let title=classic_language::text(&app,if folders {"addFolder"}else{"addFiles"});
        let chooser=app.dialog().file().set_parent(&window).set_title(title);
        let selected=if folders {chooser.blocking_pick_folders()} else {chooser.blocking_pick_files()};
        selected.unwrap_or_default().into_iter().map(path).collect()
    }).await.map_err(err)?
}
pub async fn save_export(app:&tauri::AppHandle,text:String)->Result<bool,String> {
    let app=app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let window=main_window(&app)?;
        let title=classic_language::text(&app,"exportConversation");
        let chosen=app.dialog().file().set_parent(&window).set_title(title)
            .add_filter("Markdown",&["md"]).set_file_name("VibeZ-chat.md").blocking_save_file();
        let Some(chosen)=chosen else{return Ok(false);};
        // The OS chooser owns overwrite confirmation and the selected path.
        std::fs::write(path(chosen)?,text).map_err(err)?;Ok(true)
    }).await.map_err(err)?
}
pub fn open_folder(app:&tauri::AppHandle,folder:&Path)->Result<(),String> {
    main_window(app)?;
    let local=FilePath::Path(folder.to_owned()).simplified().into_path().map_err(err)?;
    app.opener().open_path(local.to_string_lossy().into_owned(),None::<&str>).map_err(err)
}

#[cfg(not(target_os="linux"))]
#[path="screenshot_native_other.rs"]
mod screenshot_native;
#[cfg(not(target_os="linux"))]
pub(super) async fn eval_value(view:&Webview,script:impl Into<String>)->Result<String,String> {
    official_web::eval(view,&script.into()).await
}
#[cfg(not(target_os="linux"))]
pub async fn snapshot(app:&tauri::AppHandle,view:&Webview)->Result<(),String> {
    let before=view.url().map_err(err)?;
    let raw=official_web::eval(view,"JSON.stringify({rect:{x:0,y:0,width:innerWidth,height:innerHeight},viewport:{width:innerWidth,height:innerHeight},scroll:{x:scrollX,y:scrollY}})").await?;
    let geometry:Value=serde_json::from_str(&raw).map_err(err)?;
    let bytes=screenshot_native::snapshot(view,"visible",&geometry).await?;
    if view.url().map_err(err)?!=before{return Err("The page changed during the screenshot. Try again.".into());}
    let image=tauri::image::Image::from_bytes(&bytes).map_err(err)?;
    app.clipboard().write_image(&image).map_err(err)
}

#[cfg(test)]mod tests {
    use super::*;
    #[test]fn create_workspace_is_one_new_direct_child_and_never_replaces_existing_data() {
        let root=std::env::temp_dir().join(format!("vibez-platform-create-{}",std::process::id()));
        std::fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();
        let existing=root.join("existing.txt");std::fs::write(&existing,b"untouched").unwrap();
        let created=create_child(&root,&root.join("Alpha workspace")).unwrap();assert_eq!(created.parent(),Some(root.as_path()));
        assert!(create_child(&root,&created).is_err());assert!(create_child(&root,&existing).is_err());
        assert!(create_child(&root,&created.join("nested")).is_err());assert_eq!(std::fs::read(&existing).unwrap(),b"untouched");
        std::fs::remove_dir_all(&root).unwrap();
    }
}

/// Keep the backend and its tunnel in one Windows job. Dropping the job after
/// shutdown also closes descendants when an unresponsive backend needs a kill.
#[cfg(target_os="windows")]
pub struct BackendJob(windows::Win32::Foundation::HANDLE);
#[cfg(target_os="windows")]
unsafe impl Send for BackendJob {}
#[cfg(target_os="windows")]
unsafe impl Sync for BackendJob {}
#[cfg(target_os="windows")]
impl BackendJob {
    pub fn attach(child:&std::process::Child)->Result<Self,String> {
        use std::os::windows::io::AsRawHandle;
        use windows::{core::PCWSTR,Win32::{Foundation::HANDLE,System::JobObjects::{CreateJobObjectW,SetInformationJobObject,AssignProcessToJobObject,JobObjectExtendedLimitInformation,JOBOBJECT_EXTENDED_LIMIT_INFORMATION,JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE}}};
        // Windows job handles can be closed on any thread. This object owns the
        // handle exclusively, and the child stdin is not exposed until attach.
        unsafe {
            let job=Self(CreateJobObjectW(None,PCWSTR::null()).map_err(err)?);
            let mut limits=JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
            limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            SetInformationJobObject(job.0,JobObjectExtendedLimitInformation,(&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),std::mem::size_of_val(&limits) as u32).map_err(err)?;
            AssignProcessToJobObject(job.0,HANDLE(child.as_raw_handle())).map_err(err)?;
            Ok(job)
        }
    }
}
#[cfg(target_os="windows")]
impl Drop for BackendJob {fn drop(&mut self){unsafe{let _=windows::Win32::Foundation::CloseHandle(self.0);}}}
