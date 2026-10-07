//! OS save dialogs. Only the local screenshot controls can reach these functions.
use crate::{desktop_ui,err};
use std::path::PathBuf;
use tauri::{AppHandle,Manager};

pub async fn save(app:&AppHandle,bytes:Vec<u8>)->Result<serde_json::Value,String>{
    let Some(path)=choose(app).await? else{return Ok(serde_json::json!({"cancelled":true}));};
    // The native dialog owns the exact path and overwrite confirmation.
    tauri::async_runtime::spawn_blocking(move ||{
        use std::io::Write;
        let mut options=std::fs::OpenOptions::new();options.create(true).truncate(true).write(true);
        #[cfg(unix)]{use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
        let mut file=options.open(&path).map_err(err)?;file.write_all(&bytes).map_err(err)?;file.sync_all().map_err(err)?;
        Ok(serde_json::json!({"saved":true,"path":path.display().to_string()}))
    }).await.map_err(err)?
}
#[cfg(target_os="windows")]
async fn choose(app:&AppHandle)->Result<Option<PathBuf>,String>{
    let window=app.get_webview_window("screenshot").ok_or("Screenshot window closed")?;
    let title=desktop_ui::preview(app,"screenshotSavePng");
    let(tx,rx)=tokio::sync::oneshot::channel();
    app.run_on_main_thread(move ||{
        use windows::{core::{w,HSTRING},Win32::{Foundation::HWND,System::Com::{CoCreateInstance,CoTaskMemFree,CLSCTX_INPROC_SERVER},UI::Shell::{IFileSaveDialog,FileSaveDialog,FOS_FORCEFILESYSTEM,SIGDN_FILESYSPATH,Common::COMDLG_FILTERSPEC}}};
        let result:Result<Option<PathBuf>,String>=(||unsafe{
            let dialog:IFileSaveDialog=CoCreateInstance(&FileSaveDialog,None,CLSCTX_INPROC_SERVER).map_err(err)?;
            dialog.SetOptions(dialog.GetOptions().map_err(err)?|FOS_FORCEFILESYSTEM).map_err(err)?;
            dialog.SetTitle(&HSTRING::from(title)).map_err(err)?;
            dialog.SetFileName(w!("VibeZ-screenshot.png")).map_err(err)?;
            dialog.SetDefaultExtension(w!("png")).map_err(err)?;
            dialog.SetFileTypes(&[COMDLG_FILTERSPEC{pszName:w!("PNG"),pszSpec:w!("*.png")}]).map_err(err)?;
            let parent=HWND(window.hwnd().map_err(err)?.0);
            match dialog.Show(Some(parent)){
                Ok(())=>{},Err(error) if error.code().0==0x800704C7u32 as i32=>return Ok(None),Err(error)=>return Err(err(error))
            }
            let raw=dialog.GetResult().map_err(err)?.GetDisplayName(SIGDN_FILESYSPATH).map_err(err)?;
            let path=raw.to_string().map_err(err);CoTaskMemFree(Some(raw.0.cast()));
            Ok(Some(PathBuf::from(path?)))
        })();let _=tx.send(result);
    }).map_err(err)?;
    rx.await.map_err(err)?
}
#[cfg(target_os="macos")]
async fn choose(app:&AppHandle)->Result<Option<PathBuf>,String>{
    let window=app.get_webview_window("screenshot").ok_or("Screenshot window closed")?;
    let title=desktop_ui::preview(app,"screenshotSavePng");
    let(tx,rx)=tokio::sync::oneshot::channel();
    app.run_on_main_thread(move ||{
        use objc2::MainThreadMarker;
        use objc2_app_kit::{NSSavePanel,NSWindow,NSModalResponseOK};
        use objc2_foundation::{NSArray,NSString};
        let Some(mtm)=MainThreadMarker::new()else{let _=tx.send(Err("Save dialog requires main thread".into()));return;};
        let Ok(parent)=window.ns_window()else{let _=tx.send(Err("Screenshot window closed".into()));return;};
        let panel=NSSavePanel::savePanel(mtm);panel.setTitle(&NSString::from_str(&title));
        panel.setNameFieldStringValue(&NSString::from_str("VibeZ-screenshot.png"));
        #[allow(deprecated)] panel.setAllowedFileTypes(Some(&NSArray::from_retained_slice(&[NSString::from_str("png")])));
        panel.setAllowsOtherFileTypes(false);panel.setCanCreateDirectories(true);
        let keep=panel.clone();let sender=std::cell::RefCell::new(Some(tx));
        let done=block2::RcBlock::new(move |response|{
            let result=if response==NSModalResponseOK{keep.URL().and_then(|url|url.path()).map(|s|Some(PathBuf::from(s.to_string()))).ok_or("No local path selected".into())}else{Ok(None)};
            if let Some(tx)=sender.borrow_mut().take(){let _=tx.send(result);}
        });
        unsafe{panel.beginSheetModalForWindow_completionHandler(&*parent.cast::<NSWindow>(),&done);}
    }).map_err(err)?;
    rx.await.map_err(err)?
}
