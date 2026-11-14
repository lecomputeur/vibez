//! Native chat downloads keep the website's cookies and blob store. Website
//! content never supplies a local path: a native Save dialog selects it.
use super::*;
use std::{collections::BTreeMap,path::{Path,PathBuf},sync::{Mutex,OnceLock},io::{Read,Write,Seek,SeekFrom}};
use tauri::webview::{DownloadEvent,NewWindowFeatures,NewWindowResponse};
#[cfg(not(target_os="linux"))]
use tauri_plugin_dialog::DialogExt;
#[cfg(target_os="linux")]
use gtk::prelude::DialogExt;
const MAX_DOWNLOAD:u64=128*1024*1024;
const MAX_PENDING:usize=4;
#[derive(Debug)]
struct Transfer {folder:PathBuf,path:PathBuf,name:String,initial_directory:Option<PathBuf>}
#[derive(Clone,Debug,PartialEq,Eq)]
struct SaveFolder {project:String,path:PathBuf}
#[derive(Default)]
pub struct SaveState(Mutex<Option<SaveFolder>>);
// Only the fresh native backend snapshot supplies a default directory. Neither
// the attachment URL nor hosted JavaScript can choose a local path.
fn snapshot_folder(event:&Value)->Option<SaveFolder> {
    let project=event["project"]["id"].as_str()?;
    let raw=project.strip_prefix("code-").or_else(||project.strip_prefix("chat-")).unwrap_or(project);
    if !official_web::projects::valid_id(raw){return None;}
    let hex=|value:&str,n:usize|value.len()==n&&value.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c));
    event["workspace_binding"].as_str().filter(|v|hex(v,64))?;
    let target=event["target_folder_id"].as_str().filter(|v|hex(v,32))?;
    let rows=event["folders"].as_array()?;
    if rows.is_empty()||rows.len()>16{return None;}
    let mut ids=std::collections::BTreeSet::new();
    for row in rows {let id=row["id"].as_str().filter(|v|hex(v,32))?;if !ids.insert(id){return None;}}
    let row=rows.iter().find(|row|row["id"].as_str()==Some(target))?;
    let folder=event["folder"].as_str()?;
    if row["path"].as_str()!=Some(folder)||folder.len()>32768||folder.contains('\0'){return None;}
    let path=PathBuf::from(folder);if !path.is_absolute(){return None;}
    Some(SaveFolder{project:project.into(),path})
}
impl SaveState {
    fn observe(&self,event:&Value) {
        if event["type"]=="web_connector" {
            if let Ok(mut folder)=self.0.lock(){*folder=snapshot_folder(event);}
        }else if event["type"]=="error"&&event["code"]=="engine_stopped" {
            if let Ok(mut folder)=self.0.lock(){*folder=None;}
        }
    }
    fn for_project(&self,project:Option<&str>)->Option<PathBuf> {
        self.0.lock().ok()?.as_ref().filter(|folder|Some(folder.project.as_str())==project).map(|folder|folder.path.clone())
    }
}
pub fn observe(app:&tauri::AppHandle,event:&Value){app.state::<SaveState>().observe(event);}
fn linked_directory(app:&tauri::AppHandle,download:&url::Url)->Option<PathBuf> {
    let project=official_web::download_project(app,download)?;
    app.state::<SaveState>().for_project(Some(&project))
}
fn initial_directory(linked: Option<&Path>) -> Option<PathBuf> {
    // A linked folder is a suggestion. Otherwise let the native dialog
    // choose its starting location without creating or selecting Downloads.
    linked
        .filter(|path| {
            path.is_absolute()
                && std::fs::symlink_metadata(path).is_ok_and(|meta| meta.is_dir())
        })
        .map(Path::to_path_buf)
}
#[cfg(target_os="linux")]
fn configure_save_chooser(chooser:&impl gtk::prelude::FileChooserExt,name:&str,directory:Option<&Path>){
    if let Some(directory)=directory {chooser.set_current_folder(directory);}
    chooser.set_current_name(name);chooser.set_do_overwrite_confirmation(true);
}
static PENDING:OnceLock<Mutex<BTreeMap<String,Transfer>>>=OnceLock::new();
static BLOB_INTENTS:OnceLock<Mutex<BTreeMap<String,std::time::Instant>>>=OnceLock::new();
fn blob_intents()->&'static Mutex<BTreeMap<String,std::time::Instant>> {BLOB_INTENTS.get_or_init(||Mutex::new(BTreeMap::new()))}
fn consume_blob_intent(url:&url::Url)->bool {blob_intents().lock().ok().and_then(|mut m|m.remove(url.as_str())).is_some_and(|at|at.elapsed()<std::time::Duration::from_secs(5))}
fn pending()->&'static Mutex<BTreeMap<String,Transfer>> {PENDING.get_or_init(||Mutex::new(BTreeMap::new()))}
fn mistral(url:&url::Url)->bool {
    url.scheme()=="https"&&matches!(url.host_str(),Some("chat.mistral.ai"|"vibe.mistral.ai"))
        &&url.port_or_known_default()==Some(443)&&url.username().is_empty()&&url.password().is_none()
}
pub fn blob(url:&url::Url)->bool {
    url.scheme()=="blob"&&url.query().is_none()&&url.fragment().is_none()
        &&url::Url::parse(url.path()).is_ok_and(|inner|mistral(&inner)&&inner.path().trim_matches('/').len()==36)
}
fn downloadable(url:&url::Url)->bool {
    blob(url)||(url.scheme()=="https"&&url.host_str().is_some()&&url.port_or_known_default()==Some(443)&&url.username().is_empty()&&url.password().is_none())
}
fn filename(path:&Path)->String {
    let raw=path.file_name().and_then(|s|s.to_str()).unwrap_or("Mistral-file");
    let leaf=raw.rsplit(['/', '\\']).next().unwrap_or("");
    let mut name=String::new();
    for c in leaf.chars(){if name.len()+c.len_utf8()>180{break;}if c.is_control()||matches!(c,':'|'*'|'?'|'"'|'<'|'>'|'|'){name.push('_');}else{name.push(c);}}
    name=name.trim_matches([' ','.']).to_owned();
    let stem=name.split('.').next().unwrap_or("").to_ascii_uppercase();
    if name.is_empty(){return "Mistral-file".into();}
    if ["CON","PRN","AUX","NUL","COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9","LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"].contains(&stem.as_str()){name.insert(0,'_');}
    name
}
fn random_name()->Result<String,String> {
    let mut bytes=[0u8;16];getrandom::fill(&mut bytes).map_err(err)?;
    Ok(bytes.iter().map(|v|format!("{v:02x}")).collect())
}
fn stage(cache:&Path,name:&Path)->Result<Transfer,String> {
    let root=cache.join("chat-downloads");
    std::fs::create_dir_all(cache).map_err(err)?;
    if !root.exists(){let mut b=std::fs::DirBuilder::new();#[cfg(unix)]{use std::os::unix::fs::DirBuilderExt;b.mode(0o700);}match b.create(&root){Ok(())=>{},Err(e)if e.kind()==std::io::ErrorKind::AlreadyExists=>{},Err(e)=>return Err(err(e))}}
    let m=std::fs::symlink_metadata(&root).map_err(err)?;
    if !m.is_dir()||m.file_type().is_symlink(){return Err("Invalid download cache".into());}
    let folder=root.join(format!("download-{}",random_name()?));
    let mut b=std::fs::DirBuilder::new();#[cfg(unix)]{use std::os::unix::fs::DirBuilderExt;b.mode(0o700);}b.create(&folder).map_err(err)?;
    Ok(Transfer{path:folder.join("payload"),folder,name:filename(name),initial_directory:None})
}
fn cleanup(transfer:&Transfer){let _=std::fs::remove_dir_all(&transfer.folder);}
pub fn cancel_all(){if let Ok(mut p)=pending().lock(){for (_,t)in std::mem::take(&mut *p){cleanup(&t);}}if let Ok(mut m)=blob_intents().lock(){m.clear();}}
fn safe_parent(app:&tauri::AppHandle)->Result<tauri::Window,String> {
    let safe=screen(app)?;let parent=app.get_window("main").ok_or("VibeZ window unavailable")?;
    if safe_output()?.is_some(){let p=parent.outer_position().map_err(err)?;let size=parent.outer_size().map_err(err)?;
        if p.x<safe.x||p.y<safe.y||i64::from(p.x)+i64::from(size.width)>i64::from(safe.x)+i64::from(safe.width)||i64::from(p.y)+i64::from(size.height)>i64::from(safe.y)+i64::from(safe.height){return Err("VibeZ is not on the selected safe display".into());}}
    Ok(parent)
}
fn notice(app:&tauri::AppHandle){send(app,json!({"type":"error","message":classic_language::text(app,"operationFailed")}));}
fn publish(source:&Path,target:&Path)->Result<(),String> {
    if !target.is_absolute(){return Err("Choose a local file".into());}
    let parent=target.parent().ok_or("Choose a local file")?.canonicalize().map_err(err)?;
    let leaf=target.file_name().ok_or("Choose a file name")?;
    let target=parent.join(leaf);
    if std::fs::symlink_metadata(&target).is_ok_and(|m|!m.is_file()||m.file_type().is_symlink()){return Err("Choose a regular file".into());}
    let meta=std::fs::symlink_metadata(source).map_err(err)?;
    if !meta.is_file()||meta.file_type().is_symlink()||meta.len()>MAX_DOWNLOAD{return Err("Invalid downloaded file".into());}
    let temporary=parent.join(format!(".vibez-save-{}",random_name()?));
    let result=(||{
        let mut input=std::fs::File::open(source).map_err(err)?;
        let mut options=std::fs::OpenOptions::new();options.create_new(true).write(true);#[cfg(unix)]{use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
        let mut output=options.open(&temporary).map_err(err)?;
        let bytes=std::io::copy(&mut (&mut input).take(MAX_DOWNLOAD+1),&mut output).map_err(err)?;
        if bytes>MAX_DOWNLOAD{return Err("Downloaded file is too large".into());}output.flush().map_err(err)?;output.sync_all().map_err(err)?;drop(output);
        #[cfg(not(target_os="windows"))]
        std::fs::rename(&temporary,&target).map_err(err)?;
        #[cfg(target_os="windows")]
        {
            // std::fs::rename cannot replace a Windows destination. Keep an
            // existing, user-confirmed file until its complete replacement is ready.
            let backup=parent.join(format!(".vibez-previous-{}",random_name()?));let old=target.exists();
            if old{std::fs::rename(&target,&backup).map_err(err)?;}
            if let Err(e)=std::fs::rename(&temporary,&target){if old{let _=std::fs::rename(&backup,&target);}return Err(err(e));}
            if old{let _=std::fs::remove_file(&backup);}
        }
        Ok(())
    })();let _=std::fs::remove_file(&temporary);result
}
// A Flatpak SaveFile grant may cover only this selected file, not its
// parent directory. Do not require creation/renaming of a sibling there.
fn replace_granted<F>(file:&mut std::fs::File,data:&[u8],writer:F)->Result<(),String>
where F:FnOnce(&mut std::fs::File,&[u8])->std::io::Result<()> {
    let mut original=Vec::new();file.seek(SeekFrom::Start(0)).map_err(err)?;
    (&mut *file).take(MAX_DOWNLOAD+1).read_to_end(&mut original).map_err(err)?;
    if original.len() as u64>MAX_DOWNLOAD{return Err("Selected file is too large to safely replace".into());}
    file.seek(SeekFrom::Start(0)).map_err(err)?;
    let result=writer(file,data).and_then(|_|file.set_len(data.len() as u64)).and_then(|_|file.sync_all());
    if let Err(error)=result{
        file.seek(SeekFrom::Start(0)).and_then(|_|file.write_all(&original)).and_then(|_|file.set_len(original.len() as u64)).and_then(|_|file.sync_all()).map_err(err)?;
        return Err(err(error));
    }
    Ok(())
}
pub(crate) fn publish_granted(source:&Path,target:&Path)->Result<(),String> {
    if !target.is_absolute(){return Err("Choose a local file".into());}
    let meta=std::fs::symlink_metadata(source).map_err(err)?;
    if !meta.is_file()||meta.file_type().is_symlink()||meta.len()>MAX_DOWNLOAD{return Err("Invalid downloaded file".into());}
    if std::fs::symlink_metadata(target).is_ok_and(|m|!m.is_file()||m.file_type().is_symlink()){return Err("Choose a regular file".into());}
    let mut data=Vec::new();std::fs::File::open(source).map_err(err)?.take(MAX_DOWNLOAD+1).read_to_end(&mut data).map_err(err)?;
    if data.len() as u64>MAX_DOWNLOAD{return Err("Downloaded file is too large".into());}
    let mut options=std::fs::OpenOptions::new();options.read(true).write(true).create(true);#[cfg(unix)]{use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
    let mut file=options.open(target).map_err(err)?;
    if !file.metadata().map_err(err)?.is_file(){return Err("Choose a regular file".into());}
    replace_granted(&mut file,&data,|file,data|file.write_all(data))
}
#[cfg(target_os="linux")]
async fn choose(app:&tauri::AppHandle,name:String,linked:Option<PathBuf>)->Result<Option<PathBuf>,String> {
    let parent=safe_parent(app)?;let directory=initial_directory(linked.as_deref());let app=app.clone();let(tx,rx)=tokio::sync::oneshot::channel();
    app.clone().run_on_main_thread(move||{
        let result=(||{
            let parent=parent.gtk_window().map_err(err)?;let title=classic_language::text(&app,"filesSave");let yes=title.clone();let cancel=classic_language::text(&app,"cancel");
            if is_flatpak(){
                if safe_output()?.is_some(){return Err("A system dialog cannot be safely positioned".into());}
                let chooser=gtk::FileChooserNative::new(Some(&title),Some(&parent),gtk::FileChooserAction::Save,Some(&yes),Some(&cancel));
                configure_save_chooser(&chooser,&name,directory.as_deref());chooser.set_modal(true);
                let result=if chooser.run()==gtk::ResponseType::Accept{chooser.filename()}else{None};chooser.destroy();return Ok(result);
            }
            let dialog=gtk::FileChooserDialog::new(Some(&title),Some(&parent),gtk::FileChooserAction::Save);dialog.add_buttons(&[(&cancel,gtk::ResponseType::Cancel),(&yes,gtk::ResponseType::Accept)]);
            configure_save_chooser(&dialog,&name,directory.as_deref());dialog.set_modal(true);position_dialog(&app,&dialog,screen(&app)?)?;
            let result=if dialog.run()==gtk::ResponseType::Accept{dialog.filename()}else{None};dialog.close();Ok(result)
        })();let _=tx.send(result);
    }).map_err(err)?;rx.await.map_err(err)?
}
#[cfg(not(target_os="linux"))]
async fn choose(app:&tauri::AppHandle,name:String,linked:Option<PathBuf>)->Result<Option<PathBuf>,String> {
    let parent=safe_parent(app)?;let directory=initial_directory(linked.as_deref());let handle=app.clone();
    tauri::async_runtime::spawn_blocking(move||{
        let title=classic_language::text(&handle,"filesSave");
        let mut dialog=handle.dialog().file().set_parent(&parent).set_title(title).set_file_name(name);
        if let Some(directory)=directory {dialog=dialog.set_directory(directory);}
        dialog.blocking_save_file()
            .map(|file|file.into_path().map_err(err)).transpose()
    }).await.map_err(err)?
}
pub fn handle(view:Webview,event:DownloadEvent<'_>)->bool {
    let app=view.app_handle();
    match event{
        DownloadEvent::Requested{url,destination}=>{
            // macOS download-attribute actions bypass the navigation hook.
            consume_blob_intent(&url);
            // WebKit may expose the provisional attachment URL here, before
            // it restores the chat document. Keep the native session and save
            // chooser; do not require the attachment host to be the chat host.
            let own=view.label()=="mistral-web"||view.label().starts_with("mistral-login-");
            if !own||!downloadable(&url)||!app.get_webview("mistral-web").and_then(|v|v.url().ok()).is_some_and(|u|safe_https(&u)||blob(&u))||safe_parent(app).is_err(){return false;}
            let Ok(mut state)=pending().lock()else{return false;};
            if state.len()>=MAX_PENDING||state.contains_key(url.as_str()){return false;}
            let prepared=app.path().app_cache_dir().map_err(err).and_then(|root|stage(&root,destination));
            match prepared{Ok(mut transfer)=>{transfer.initial_directory=linked_directory(app,&url);*destination=transfer.path.clone();state.insert(url.as_str().into(),transfer);true},Err(_)=>{notice(app);false}}
        },
        DownloadEvent::Finished{url,path,success}=>{
            let transfer=pending().lock().ok().and_then(|mut p|p.remove(url.as_str()));
            if let Some(transfer)=transfer{
                if !success||path.as_ref().is_some_and(|p|p!=&transfer.path)||!std::fs::symlink_metadata(&transfer.path).is_ok_and(|m|m.is_file()&&!m.file_type().is_symlink()&&m.len()<=MAX_DOWNLOAD){cleanup(&transfer);notice(app);return true;}
                let app=app.clone();tauri::async_runtime::spawn(async move{
                    let result=match choose(&app,transfer.name.clone(),transfer.initial_directory.clone()).await{Ok(Some(target))=>if safe_parent(&app).is_ok(){if is_flatpak(){publish_granted(&transfer.path,&target)}else{publish(&transfer.path,&target)}}else{Err("Safe display changed".into())},Ok(None)=>Ok(()),Err(e)=>Err(e)};
                    cleanup(&transfer);if result.is_err(){notice(&app);}
                });
            }
            true
        },
        _=>false
    }
}
fn start_blob(app:&tauri::AppHandle,url:&url::Url)->Result<(),String> {
    safe_parent(app)?;
    let view=app.get_webview("mistral-web").ok_or("Mistral is not loaded")?;
    {let mut intents=blob_intents().lock().map_err(err)?;intents.retain(|_,at|at.elapsed()<std::time::Duration::from_secs(5));
        if intents.len()>=MAX_PENDING{return Err("Download busy".into());}intents.insert(url.as_str().into(),std::time::Instant::now());}
    let script=include_str!("chat_download.js").replace("__VIBEZ_DOWNLOAD_URL__",&json!(url.as_str()).to_string());
    if let Err(error)=view.eval(script){consume_blob_intent(url);return Err(err(error));}Ok(())
}
pub fn navigation(app:&tauri::AppHandle,url:&url::Url)->bool {
    if blob(url){
        // Only the one-shot native reissued download anchor may proceed. A
        // renderable blob navigation must not replace the chat document.
        if consume_blob_intent(url){return true;}
        if start_blob(app,url).is_err(){notice(app);}return false;
    }
    url.as_str()=="about:blank"||safe_https(url)
}
pub fn popup(app:&tauri::AppHandle,url:url::Url,_features:NewWindowFeatures)->NewWindowResponse<tauri::Wry> {
    // A generated file may be renderable (text/PDF/HTML). Download it inside
    // its original session instead of rendering it in a hidden popup.
    if blob(&url)&&start_blob(app,&url).is_err(){notice(app);}
    NewWindowResponse::Deny
}
#[cfg(test)]mod tests{
    use super::*;
    #[test]fn a_native_blob_download_intent_is_exact_and_one_shot(){
        let url:url::Url="blob:https://chat.mistral.ai/01234567-1111-4222-8333-0123456789ab".parse().unwrap();
        blob_intents().lock().unwrap().insert(url.as_str().into(),std::time::Instant::now());assert!(consume_blob_intent(&url));assert!(!consume_blob_intent(&url));
        blob_intents().lock().unwrap().insert(url.as_str().into(),std::time::Instant::now()-std::time::Duration::from_secs(6));assert!(!consume_blob_intent(&url));
    }
    #[test]fn only_https_and_mistral_owned_blob_sources_can_download(){
        for u in ["https://chat.mistral.ai/api/files/download/1","https://signed.example/file?sig=secret","blob:https://chat.mistral.ai/11111111-2222-4333-8444-555555555555","blob:https://vibe.mistral.ai/11111111-2222-4333-8444-555555555555"]{assert!(downloadable(&u.parse().unwrap()),"{u}");}
        for u in ["file:///etc/passwd","data:text/plain,secret","http://chat.mistral.ai/file","blob:null/11111111-2222-4333-8444-555555555555","blob:https://evil.test/11111111-2222-4333-8444-555555555555","https://user:secret@host.test/file","https://host.test:444/file"]{assert!(!downloadable(&u.parse().unwrap()),"{u}");}
    }
    #[test]fn suggested_names_never_choose_paths_or_windows_special_files(){
        for (raw,wanted)in [("/a/b/report.odt","report.odt"),("/a/../report.docx","report.docx"),(r"C:\a\secret.xlsx","secret.xlsx"),("../..","Mistral-file"),("/a/CON.txt","_CON.txt"),("a\0b.odt","a_b.odt")]{assert_eq!(filename(Path::new(raw)),wanted);}
        assert!(filename(Path::new(&"é".repeat(200))).len()<=180);
    }
    #[test]fn staging_cancellation_and_atomic_save_use_only_owned_temporary_files(){
        let root=std::env::temp_dir().join(format!("vibez-download-test-{}",random_name().unwrap()));std::fs::create_dir(&root).unwrap();
        let source=stage(&root,Path::new("../../report.odt")).unwrap();assert_eq!(source.name,"report.odt");assert!(source.path.starts_with(root.join("chat-downloads")));std::fs::write(&source.path,b"new bytes").unwrap();
        let existing=root.join("old.odt");std::fs::write(&existing,b"keep until explicit save").unwrap();
        cleanup(&source);assert!(!source.folder.exists());assert_eq!(std::fs::read(&existing).unwrap(),b"keep until explicit save");
        let source=stage(&root,Path::new("report.odt")).unwrap();std::fs::write(&source.path,b"downloaded bytes").unwrap();publish(&source.path,&existing).unwrap();assert_eq!(std::fs::read(&existing).unwrap(),b"downloaded bytes");
        assert!(publish(&source.path,Path::new("relative.odt")).is_err());assert!(publish(&source.path,&root).is_err());cleanup(&source);std::fs::remove_dir_all(root).unwrap();
    }
    #[test]fn selected_file_only_save_replaces_bytes_and_restores_original_after_partial_error(){
        let root=std::env::temp_dir().join(format!("vibez-download-grant-{}",random_name().unwrap()));std::fs::create_dir(&root).unwrap();
        let source=root.join("source.odt");let target=root.join("chosen.odt");std::fs::write(&source,b"new").unwrap();std::fs::write(&target,b"original longer bytes").unwrap();
        let mut file=std::fs::OpenOptions::new().read(true).write(true).open(&target).unwrap();
        assert!(replace_granted(&mut file,b"replacement",|f,data|{f.write_all(&data[..2])?;Err(std::io::Error::other("fixture write failure"))}).is_err());
        assert_eq!(std::fs::read(&target).unwrap(),b"original longer bytes");drop(file);
        publish_granted(&source,&target).unwrap();assert_eq!(std::fs::read(&target).unwrap(),b"new");assert_eq!(std::fs::read_dir(&root).unwrap().count(),2);std::fs::remove_dir_all(root).unwrap();
    }
    #[cfg(unix)]#[test]fn symlink_destinations_and_staging_roots_are_rejected(){
        use std::os::unix::fs::symlink;
        let root=std::env::temp_dir().join(format!("vibez-download-links-{}",random_name().unwrap()));std::fs::create_dir(&root).unwrap();let original=root.join("original");std::fs::write(&original,b"untouched").unwrap();
        let source=stage(&root,Path::new("report.odt")).unwrap();std::fs::write(&source.path,b"changed").unwrap();let link=root.join("link");symlink(&original,&link).unwrap();assert!(publish(&source.path,&link).is_err());assert_eq!(std::fs::read(original).unwrap(),b"untouched");cleanup(&source);
        std::fs::remove_dir(root.join("chat-downloads")).unwrap();symlink(root.join("elsewhere"),root.join("chat-downloads")).unwrap();assert!(stage(&root,Path::new("report.odt")).is_err());std::fs::remove_dir_all(root).unwrap();
    }
}

#[cfg(test)]mod save_directory_tests {
    use super::*;
    const A:&str="cace260d-d95d-4859-b45b-f56f185f15da";
    const B:&str="code-01a0296a-296a-748f-aba4-6dc79fa08bc2";
    fn root()->PathBuf {let p=std::env::temp_dir().join(format!("vibez-save-directory-{}",random_name().unwrap()));std::fs::create_dir(&p).unwrap();p}
    fn snapshot(project:&str,one:&Path,two:&Path)->Value {
        json!({"type":"web_connector","project":{"id":project},"folder":two,"enabled":false,
            "workspace_binding":"a".repeat(64),"target_folder_id":"2".repeat(32),
            "folders":[{"id":"1".repeat(32),"path":one},{"id":"2".repeat(32),"path":two}]})
    }
    #[test]fn linked_target_is_scoped_to_work_code_and_conversations_even_when_paused(){
        let root=root();let one=root.join("One");let two=root.join("Two");
        let state=SaveState::default();
        for project in [A,B,"chat-cace260d-d95d-4859-b45b-f56f185f15da"] {
            state.observe(&snapshot(project,&one,&two));assert_eq!(state.for_project(Some(project)),Some(two.clone()));
            assert_eq!(state.for_project(None),None);assert_eq!(state.for_project(Some("another")),None);
        }
        state.observe(&snapshot(A,&one,&two));assert_eq!(state.for_project(Some(B)),None);
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]fn invalid_unlinked_and_stopped_snapshots_clear_the_previous_folder(){
        let root=root();let event=snapshot(A,&root,&root.join("Target"));let state=SaveState::default();
        for (field,value) in [("project",json!({"id":"bad"})),("folder",json!("relative")),("folder",json!("/not-the-selected-folder")),("target_folder_id",json!("3".repeat(32))),
            ("workspace_binding",Value::Null),("folders",json!([])),("folders",json!([{"id":"2".repeat(32),"path":root},{"id":"2".repeat(32),"path":root}]))] {
            state.observe(&event);assert!(state.for_project(Some(A)).is_some());let mut invalid=event.clone();invalid[field]=value;state.observe(&invalid);assert_eq!(state.for_project(Some(A)),None);
        }
        state.observe(&event);state.observe(&json!({"type":"error","code":"engine_stopped"}));assert_eq!(state.for_project(Some(A)),None);
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]fn project_switch_during_a_transfer_keeps_its_original_default_and_cleanup_is_private(){
        let root=root();let one=root.join("Project A");let two=root.join("Project B");std::fs::create_dir(&one).unwrap();std::fs::create_dir(&two).unwrap();
        let state=SaveState::default();state.observe(&snapshot(A,&one,&one));
        let mut transfer=stage(&root,Path::new("report.docx")).unwrap();transfer.initial_directory=state.for_project(Some(A));
        state.observe(&snapshot(B,&two,&two));assert_eq!(state.for_project(Some(B)),Some(two));assert_eq!(transfer.initial_directory,Some(one.clone()));
        std::fs::write(one.join("sentinel.txt"),b"unchanged").unwrap();cleanup(&transfer);
        assert_eq!(std::fs::read(one.join("sentinel.txt")).unwrap(),b"unchanged");assert!(!one.join("report.docx").exists());std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn only_an_existing_linked_directory_is_suggested() {
        let root = root();
        let linked = root.join("Project");
        std::fs::create_dir(&linked).unwrap();
        assert_eq!(initial_directory(Some(&linked)), Some(linked.clone()));
        assert_eq!(initial_directory(None), None);

        std::fs::remove_dir(&linked).unwrap();
        assert_eq!(initial_directory(Some(&linked)), None);
        assert!(!linked.exists());
        assert_eq!(initial_directory(Some(Path::new("relative"))), None);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn a_replaced_project_symlink_is_not_suggested() {
        let root = root();
        let actual = root.join("Other location");
        let link = root.join("Project");
        std::fs::create_dir(&actual).unwrap();
        std::os::unix::fs::symlink(&actual, &link).unwrap();
        assert_eq!(initial_directory(Some(&link)), None);
        std::fs::remove_dir_all(root).unwrap();
    }
    #[cfg(target_os="linux")]
    #[test]#[ignore="Run only on the isolated Broadway display"]
    fn native_save_dialog_supports_own_location_and_cancel_writes_nothing(){
        assert_eq!(std::env::var("GDK_BACKEND").as_deref(),Ok("broadway"));
        assert_eq!(std::env::var("VIBEZ_SAVE_CHOOSER_TEST").as_deref(),Ok("1"));
        gtk::init().unwrap();
        let root=root();let a=root.join("Project A");let b=root.join("Project B");let own_choice=root.join("My chosen folder");
        for p in [&a,&b,&own_choice]{std::fs::create_dir(p).unwrap();}
        std::fs::write(a.join("existing.docx"),b"keep existing bytes").unwrap();
        let state=SaveState::default();state.observe(&snapshot(A,&a,&a));let captured=state.for_project(Some(A));state.observe(&snapshot(B,&a,&b));
        let cases=[(captured, Some(a.clone())),(state.for_project(Some(B)),Some(b.clone())),(None,None),(Some(root.join("Deleted project")),None)];
        for (linked,expected) in cases {
            let chosen=initial_directory(linked.as_deref());
            assert_eq!(chosen, expected);
            let dialog=gtk::FileChooserDialog::new(Some("VibeZ isolated Save test"),None::<&gtk::Window>,gtk::FileChooserAction::Save);
            dialog.add_buttons(&[("Cancel",gtk::ResponseType::Cancel),("Save",gtk::ResponseType::Accept)]);
            configure_save_chooser(&dialog,"report.docx",chosen.as_deref());dialog.show_all();
            let expected = expected.unwrap_or_else(|| {
                assert!(dialog.set_current_folder(&own_choice));
                own_choice.clone()
            });
            let deadline=std::time::Instant::now()+std::time::Duration::from_secs(8);
            while dialog.current_folder().as_deref()!=Some(expected.as_path()) {
                assert!(std::time::Instant::now()<deadline,"Chooser did not open expected directory");
                while gtk::events_pending(){gtk::main_iteration_do(false);}std::thread::sleep(std::time::Duration::from_millis(10));
            }
            assert_eq!(dialog.current_name().as_deref(),Some("report.docx"));assert_eq!(dialog.filename(),Some(expected.join("report.docx")));assert!(dialog.does_overwrite_confirmation());
            let cancel=dialog.clone();gtk::glib::idle_add_local_once(move||cancel.response(gtk::ResponseType::Cancel));assert_eq!(dialog.run(),gtk::ResponseType::Cancel);dialog.close();
            assert!(!expected.join("report.docx").exists());
        }
        assert_eq!(std::fs::read(a.join("existing.docx")).unwrap(),b"keep existing bytes");
        std::fs::remove_dir_all(root).unwrap();
    }
}
