//! GTK clipboard representations for both image consumers and WebKit file pastes.
//! Only the captured PNG is exposed. Its temporary file is private and owned
//! by the clipboard payload, and is removed when that payload is released.
use crate::err;
use gtk::{gdk, Clipboard, TargetEntry, TargetFlags};
use std::{fs, io::Write, path::PathBuf, sync::atomic::{AtomicU64, Ordering}, time::{Duration, SystemTime, UNIX_EPOCH}};
use tauri::AppHandle;
static SERIAL: AtomicU64 = AtomicU64::new(1);
struct Payload { bytes: Vec<u8>, directory: PathBuf, path: PathBuf, uri: String }
impl Drop for Payload {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
        let _ = fs::remove_dir(&self.directory);
    }
}
impl Payload {
    fn create(bytes: Vec<u8>) -> Result<Self, String> {
        use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
        let nonce = SystemTime::now().duration_since(UNIX_EPOCH).map_err(err)?.as_nanos();
        let directory = std::env::temp_dir().join(format!("vibez-clipboard-{}-{nonce}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::Relaxed)));
        // create_dir (not create_dir_all) fails instead of reusing an existing path.
        fs::DirBuilder::new().mode(0o700).create(&directory).map_err(err)?;
        let path = directory.join("VibeZ-screenshot.png");
        let mut payload = Self { bytes, directory, path, uri:String::new() };
        payload.uri = url::Url::from_file_path(&payload.path).map_err(|_| "Invalid clipboard file path")?.to_string();
        let mut file = fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(&payload.path).map_err(err)?;
        file.write_all(&payload.bytes).map_err(err)?;
        Ok(payload)
    }
}
pub async fn write(app: &AppHandle, bytes: &[u8]) -> Result<(),String> {
    let payload = Payload::create(bytes.to_vec())?;
    let (tx,rx) = tokio::sync::oneshot::channel();
    app.run_on_main_thread(move || {
        let clipboard = Clipboard::get(&gdk::SELECTION_CLIPBOARD);
        let targets = [TargetEntry::new("image/png",TargetFlags::empty(),0),
            TargetEntry::new("text/uri-list",TargetFlags::empty(),1)];
        // Native GTK serves PNG to image apps and a normal File to WebKit.
        // No HTML, arbitrary paths, clipboard text or synthetic events.
        let ok = clipboard.set_with_data(&targets,move |_,selection,info| {
            if info == 0 { selection.set(&gdk::Atom::intern("image/png"),8,&payload.bytes); }
            else if info == 1 { selection.set_uris(&[&payload.uri]); }
        });
        let _ = tx.send(if ok {Ok(())} else {Err("Cannot own the image clipboard".to_owned())});
    }).map_err(err)?;
    tokio::time::timeout(Duration::from_secs(5),rx).await.map_err(err)?.map_err(err)?
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn temporary_png_is_private_and_removed_with_its_payload() {
        use std::os::unix::fs::PermissionsExt;
        let payload = Payload::create(vec![1,2,3]).unwrap();
        assert_eq!(fs::metadata(&payload.directory).unwrap().permissions().mode() & 0o777,0o700);
        assert_eq!(fs::metadata(&payload.path).unwrap().permissions().mode() & 0o777,0o600);
        assert_eq!(fs::read(&payload.path).unwrap(),vec![1,2,3]);
        let directory = payload.directory.clone();drop(payload);assert!(!directory.exists());
    }
}
