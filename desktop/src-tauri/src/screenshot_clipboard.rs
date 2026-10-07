//! PNG-only clipboard ownership. No file URLs or temporary screenshot files.
use crate::err;
use gtk::{gdk, Clipboard, TargetEntry, TargetFlags};
use std::{sync::{Arc, Mutex, atomic::{AtomicU64, Ordering}}, time::Duration};
use tauri::AppHandle;
static SERIAL: AtomicU64 = AtomicU64::new(1);
static CURRENT: Mutex<Option<(u64, Arc<Vec<u8>>)>> = Mutex::new(None);
struct Payload { id: u64, bytes: Arc<Vec<u8>> }
impl Drop for Payload {
    fn drop(&mut self) {
        if let Ok(mut current)=CURRENT.lock() {
            if current.as_ref().map(|(id,_)| *id)==Some(self.id) { *current=None; }
        }
    }
}
pub fn current_png() -> Option<Arc<Vec<u8>>> {
    CURRENT.lock().ok()?.as_ref().map(|(_,bytes)|bytes.clone())
}
pub async fn write(app: &AppHandle, bytes: &[u8]) -> Result<(),String> {
    let id=SERIAL.fetch_add(1,Ordering::Relaxed);
    let bytes=Arc::new(bytes.to_vec());
    let (tx,rx)=tokio::sync::oneshot::channel();
    app.run_on_main_thread(move || {
        let payload=Payload{id,bytes};
        if let Ok(mut current)=CURRENT.lock(){*current=Some((id,payload.bytes.clone()));}
        let clipboard=Clipboard::get(&gdk::SELECTION_CLIPBOARD);
        let targets=[TargetEntry::new("image/png",TargetFlags::empty(),0)];
        // GTK releases the closure on ownership loss. The payload then clears
        // CURRENT, so Ctrl+V can never substitute a stale VibeZ screenshot.
        let ok=clipboard.set_with_data(&targets,move |_,selection,_| {
            selection.set(&gdk::Atom::intern("image/png"),8,&payload.bytes);
        });
        let _=tx.send(if ok{Ok(())}else{Err("Cannot own the image clipboard".to_owned())});
    }).map_err(err)?;
    tokio::time::timeout(Duration::from_secs(5),rx).await.map_err(err)?.map_err(err)?
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn clipboard_ownership_loss_clears_only_its_own_png() {
        let old=Payload{id:1,bytes:Arc::new(vec![1])};
        let new=Payload{id:2,bytes:Arc::new(vec![2])};
        *CURRENT.lock().unwrap()=Some((2,new.bytes.clone()));
        drop(old);assert_eq!(current_png().unwrap().as_ref(),&vec![2]);
        drop(new);assert!(current_png().is_none());
    }
}
