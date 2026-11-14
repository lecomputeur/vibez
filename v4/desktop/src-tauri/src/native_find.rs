//! Memory-only native Find for Linux conversations.
//! The remote page gains neither a native command nor the user's query.
use std::{
    cell::RefCell,
    collections::HashMap,
    rc::Rc,
    sync::{atomic::{AtomicBool, AtomicU64, Ordering}, Arc, Mutex, OnceLock},
    time::Duration,
};
use gtk::prelude::*;
use tauri::{AppHandle, Manager, Webview};
use webkit2gtk::{FindControllerExt, FindOptions, WebViewExt};

static NEXT_SESSION: AtomicU64 = AtomicU64::new(1);
static OWNERS: OnceLock<Mutex<HashMap<String, Arc<AtomicU64>>>> = OnceLock::new();

#[derive(Clone)]
struct FindSession { id: u64, owner: Arc<AtomicU64> }
impl FindSession {
    // Even values own an active generation; the following odd value remembers
    // its closure. A late older claim can therefore never resurrect a session.
    fn state(&self) -> u64 { self.id * 2 }
    fn current(&self) -> bool { self.owner.load(Ordering::SeqCst) == self.state() }
    fn token(&self) -> String { self.id.to_string() }
    fn claim_script(&self) -> String {
        format!("(() => {{const next='{}',old=window.__vibezFindSession;if(old?.id&&BigInt(old.id)>=BigInt(next))return;window.__vibezFindSession={{id:next,closed:false}};}})()", self.token())
    }
    fn pause_script(&self) -> String {
        format!("(() => {{const s=window.__vibezFindSession;if(s?.id!=='{}'||s.closed)return false;window.__vibezRichRender?.pause('find');return true;}})()", self.token())
    }
    fn resume_script(&self) -> String {
        format!("(() => {{const id='{}',s=window.__vibezFindSession;if(s?.id&&BigInt(s.id)>BigInt(id))return false;if(s?.id===id&&s.closed)return false;window.__vibezFindSession={{id,closed:true}};window.__vibezRichRender?.resume('find');return true;}})()", self.token())
    }
}
fn owner(view: &Webview) -> Result<Arc<AtomicU64>, String> {
    let mut owners = OWNERS.get_or_init(|| Mutex::new(HashMap::new())).lock().map_err(crate::err)?;
    Ok(owners.entry(view.label().to_owned()).or_insert_with(|| Arc::new(AtomicU64::new(0))).clone())
}
fn claim(view: &Webview) -> Result<FindSession, String> {
    let session = FindSession { id: NEXT_SESSION.fetch_add(1, Ordering::SeqCst), owner: owner(view)? };
    session.owner.fetch_max(session.state(), Ordering::SeqCst);
    // The claim does not expand the page. It transfers any existing Find pause
    // to the new dialog, including an unqueried dialog reopened during cleanup.
    // Ignore a late claim from an older asynchronous caller.
    view.eval(session.claim_script()).map_err(crate::err)?;
    Ok(session)
}

/// A native engine search, also used by the offline regression probe.
pub async fn search(view: &Webview, query: String) -> Result<u32, String> {
    let session = claim(view)?;
    search_inner(view, query, false, None, session).await
}

async fn search_inner(
    view: &Webview,
    query: String,
    backwards: bool,
    active: Option<Arc<AtomicBool>>,
    session: FindSession,
) -> Result<u32, String> {
    if !session.current() || active.as_ref().is_some_and(|a| !a.load(Ordering::SeqCst)) {
        return Err("Find was closed".into());
    }
    // A navigation replaces the document-local token while the nonmodal dialog
    // can stay open. Reassert this still-current native session, but never reopen
    // a closed token: finish writes a watermark even into a fresh document.
    view.eval(session.claim_script()).map_err(crate::err)?;
    // Await the page process: native search must see the expanded document.
    if crate::screenshots::eval_value(view, session.pause_script()).await? != "true" {
        return Err("Find session was replaced or closed".into());
    }
    let (tx, rx) = tokio::sync::oneshot::channel::<Result<u32, String>>();
    let native_session = session.clone();
    view.with_webview(move |platform| {
        if !native_session.current() || active.as_ref().is_some_and(|a| !a.load(Ordering::SeqCst)) {
            let _ = tx.send(Err("Find was closed".into()));
            return;
        }
        let Some(controller) = platform.inner().find_controller() else {
            let _ = tx.send(Err("Native Find is unavailable".into()));
            return;
        };
        if query.is_empty() {
            controller.search_finish();
            let _ = tx.send(Ok(0));
            return;
        }
        let pending = Rc::new(RefCell::new(Some(tx)));
        let handlers = Rc::new(RefCell::new(Vec::<gtk::glib::SignalHandlerId>::new()));
        let found_pending = pending.clone();
        let found_handlers = handlers.clone();
        let found = controller.connect_found_text(move |controller, matches| {
            for handler in found_handlers.borrow_mut().drain(..) { controller.disconnect(handler); }
            if let Some(tx) = found_pending.borrow_mut().take() { let _ = tx.send(Ok(matches)); }
        });
        let failed_pending = pending.clone();
        let failed_handlers = handlers.clone();
        let failed = controller.connect_failed_to_find_text(move |controller| {
            for handler in failed_handlers.borrow_mut().drain(..) { controller.disconnect(handler); }
            if let Some(tx) = failed_pending.borrow_mut().take() { let _ = tx.send(Ok(0)); }
        });
        handlers.borrow_mut().extend([found, failed]);
        let timeout_controller = controller.clone();
        gtk::glib::timeout_add_local_once(Duration::from_secs(12), move || {
            for handler in handlers.borrow_mut().drain(..) { timeout_controller.disconnect(handler); }
            if let Some(tx) = pending.borrow_mut().take() { let _ = tx.send(Err("Native Find timed out".into())); }
        });
        if controller.search_text().as_deref() == Some(query.as_str()) {
            if backwards { controller.search_previous(); } else { controller.search_next(); }
        } else {
            let mut options = FindOptions::CASE_INSENSITIVE | FindOptions::WRAP_AROUND;
            if backwards { options |= FindOptions::BACKWARDS; }
            controller.search(&query, options.bits(), 10_000);
        }
    }).map_err(crate::err)?;
    let result = tokio::time::timeout(Duration::from_secs(14), rx).await.map_err(crate::err)?.map_err(crate::err)?;
    if !session.current() { return Err("Find session was replaced or closed".into()); }
    result
}

/// Clear native marks before restoring containment.
pub async fn finish(view: &Webview) -> Result<(), String> {
    let owner = owner(view)?;
    let state = owner.load(Ordering::SeqCst);
    if state == 0 || state % 2 == 1 { return Ok(()); }
    finish_session(view, FindSession { id: state / 2, owner }).await
}
async fn finish_session(view: &Webview, session: FindSession) -> Result<(), String> {
    let (tx, rx) = tokio::sync::oneshot::channel();
    let native_session = session.clone();
    view.with_webview(move |platform| {
        if native_session.owner.compare_exchange(native_session.state(), native_session.state() + 1, Ordering::SeqCst, Ordering::SeqCst).is_ok() {
            if let Some(controller) = platform.inner().find_controller() { controller.search_finish(); }
        }
        let _ = tx.send(());
    }).map_err(crate::err)?;
    tokio::time::timeout(Duration::from_secs(3), rx).await.map_err(crate::err)?.map_err(crate::err)?;
    view.eval(session.resume_script()).map_err(crate::err)
}

fn open_dialog(parent: &gtk::Window, view: &Webview, current: Rc<RefCell<Option<gtk::Dialog>>>) -> Result<(gtk::Dialog, gtk::Entry, gtk::Label), String> {
    let (dialog, entry, status, _) = open_dialog_with_delay(parent, view, current, Duration::ZERO, None)?;
    Ok((dialog, entry, status))
}
fn open_dialog_with_delay(parent: &gtk::Window, view: &Webview, current: Rc<RefCell<Option<gtk::Dialog>>>, cleanup_delay: Duration, cleanup_finished: Option<Arc<AtomicBool>>) -> Result<(gtk::Dialog, gtk::Entry, gtk::Label, FindSession), String> {
    let session = claim(view)?;
    let dialog = gtk::Dialog::with_buttons(
        Some("Find in conversation"), Some(parent), gtk::DialogFlags::DESTROY_WITH_PARENT,
        &[("Close", gtk::ResponseType::Close)],
    );
    dialog.set_default_size(460, 150);
    dialog.set_resizable(true);
    let area = dialog.content_area();
    area.set_spacing(10);
    area.set_border_width(12);
    let row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    let entry = gtk::Entry::new();
    entry.set_placeholder_text(Some("Find text · Enter for next match"));
    entry.set_hexpand(true);
    let previous = gtk::Button::with_label("Previous");
    let next = gtk::Button::with_label("Next");
    row.pack_start(&entry, true, true, 0);
    row.pack_start(&previous, false, false, 0);
    row.pack_start(&next, false, false, 0);
    area.pack_start(&row, false, false, 0);
    let status = gtk::Label::new(Some("Search includes messages outside the visible area."));
    status.set_xalign(0.);
    status.set_line_wrap(true);
    area.pack_start(&status, false, false, 0);
    let active = Arc::new(AtomicBool::new(true));
    let running = Arc::new(AtomicBool::new(false));
    let revision = Arc::new(AtomicU64::new(0));
    let (sender, receiver) = gtk::glib::MainContext::channel::<(u64, String)>(gtk::glib::Priority::DEFAULT);
    let status_revision = revision.clone();
    let status_active = active.clone();
    let status_display = status.clone();
    let receiver_source = Rc::new(RefCell::new(Some(receiver.attach(None, move |(generation, message)| {
        if status_active.load(Ordering::SeqCst) && status_revision.load(Ordering::SeqCst) == generation {
            status.set_text(&message);
        }
        gtk::glib::ControlFlow::Continue
    }))));
    let request: Rc<dyn Fn(bool)> = {
        let view = view.clone();
        let entry = entry.clone();
        let active = active.clone();
        let running = running.clone();
        let revision = revision.clone();
        let session = session.clone();
        Rc::new(move |backwards| {
            if running.swap(true, Ordering::SeqCst) { return; }
            let query = entry.text().to_string();
            let generation = revision.fetch_add(1, Ordering::SeqCst) + 1;
            let _ = sender.send((generation, "Searching…".into()));
            let view = view.clone();
            let active = active.clone();
            let running = running.clone();
            let sender = sender.clone();
            let session = session.clone();
            tauri::async_runtime::spawn(async move {
                let result = search_inner(&view, query, backwards, Some(active.clone()), session).await;
                running.store(false, Ordering::SeqCst);
                if !active.load(Ordering::SeqCst) { return; }
                let message = match result {
                    Ok(0) => "No matches.".into(),
                    Ok(u32::MAX) => "More than 10,000 matches.".into(),
                    Ok(count) => format!("{count} match(es). Enter or Next continues; Previous goes back."),
                    Err(error) => error,
                };
                let _ = sender.send((generation, message));
            });
        })
    };
    let enter_request = request.clone();
    entry.connect_activate(move |_| enter_request(false));
    let next_request = request.clone();
    next.connect_clicked(move |_| next_request(false));
    previous.connect_clicked(move |_| request(true));
    dialog.connect_key_press_event(|dialog, event| {
        if event.keyval() == gtk::gdk::keys::constants::Escape {
            dialog.response(gtk::ResponseType::Close);
            return true.into();
        }
        false.into()
    });
    dialog.connect_response(|dialog, _| dialog.close());
    let closed_view = view.clone();
    let closed_current = current.clone();
    let closed_session = session.clone();
    dialog.connect_destroy(move |destroyed| {
        active.store(false, Ordering::SeqCst);
        if let Some(source) = receiver_source.borrow_mut().take() { source.remove(); }
        let owns_dialog = closed_current.borrow().as_ref().is_some_and(|dialog| dialog == destroyed);
        if owns_dialog { closed_current.borrow_mut().take(); }
        let view = closed_view.clone();
        let session = closed_session.clone();
        let completed = cleanup_finished.clone();
        tauri::async_runtime::spawn(async move {
            if !cleanup_delay.is_zero() { tokio::time::sleep(cleanup_delay).await; }
            let _ = finish_session(&view, session).await;
            if let Some(completed) = completed { completed.store(true, Ordering::SeqCst); }
        });
    });
    if std::env::var_os("VIBEZ_OFFLINE_LEFT_SCREEN").is_some()
        && view.app_handle().state::<crate::PreviewState>().smoke {
        dialog.set_accept_focus(false);
        dialog.set_focus_on_map(false);
    }
    dialog.show_all();
    entry.grab_focus();
    *current.borrow_mut() = Some(dialog.clone());
    Ok((dialog, entry, status_display, session))
}

/// Exercise this process's real GTK Entry, native search status, and close path.
/// No desktop-wide input, other application windows, or remote content is read.
pub async fn smoke_dialog(app: &AppHandle, view: &Webview) -> Result<(), String> {
    let (tx, rx) = tokio::sync::oneshot::channel::<Result<(), String>>();
    let native_app = app.clone();
    let dialog_view = view.clone();
    view.with_webview(move |_| {
        let Some(window) = native_app.get_window("main") else {
            let _ = tx.send(Err("Main window is unavailable".into()));
            return;
        };
        let parent = match window.gtk_window() {
            Ok(parent) => parent,
            Err(error) => { let _ = tx.send(Err(crate::err(error))); return; }
        };
        let current = Rc::new(RefCell::new(None));
        let (dialog, entry, status) = match open_dialog(parent.upcast_ref(), &dialog_view, current) {
            Ok(opened) => opened,
            Err(error) => { let _ = tx.send(Err(error)); return; }
        };
        entry.set_text("VIBEZ_UNIQUE_REPLY_20_END");
        entry.emit_activate();
        let started = std::time::Instant::now();
        let mut tx = Some(tx);
        gtk::glib::timeout_add_local(Duration::from_millis(100), move || {
            let message = status.text();
            let result = if message.starts_with("1 match(es).") {
                Some(Ok(()))
            } else if message == "No matches." {
                Some(Err("Find dialog failed to locate its unique offline marker".into()))
            } else if started.elapsed() > Duration::from_secs(18) {
                Some(Err("Find dialog did not report one native match".into()))
            } else { None };
            if let Some(result) = result {
                dialog.response(gtk::ResponseType::Close);
                if let Some(tx) = tx.take() { let _ = tx.send(result); }
                gtk::glib::ControlFlow::Break
            } else { gtk::glib::ControlFlow::Continue }
        });
    }).map_err(crate::err)?;
    tokio::time::timeout(Duration::from_secs(22), rx).await.map_err(crate::err)?.map_err(crate::err)??;
    // Closing schedules native mark cleanup and the helper's async remeasure.
    wait_restored(view).await?;
    smoke_reopen(app, view).await
}

async fn wait_restored(view: &Webview) -> Result<(), String> {
    for _ in 0..100 {
        let state = crate::screenshots::eval_value(view,
            "(() => { const s=window.__vibezRichRender?.status(); return Boolean(s&&!s.paused.includes('find')&&s.optimized>0&&!s.working&&s.pendingMeasurements===0); })()"
        ).await?;
        if state == "true" { return Ok(()); }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    let diagnostics = crate::screenshots::eval_value(view,
        "JSON.stringify({helper:window.__vibezRichRender?.status()||null,selectionCollapsed:getSelection()?.isCollapsed??true})"
    ).await?;
    Err(format!("Closing Find did not restore the rendering helper: {diagnostics}"))
}

/// Keep a second real dialog searching while deliberately delayed cleanup from
/// the closed first dialog runs. Both native marks and the page pause must stay
/// owned by the newer dialog, then be released when that dialog closes.
async fn smoke_reopen(app: &AppHandle, view: &Webview) -> Result<(), String> {
    let (tx, rx) = tokio::sync::oneshot::channel::<Result<(), String>>();
    let app = app.clone();
    let dialog_view = view.clone();
    view.with_webview(move |platform| {
        let Some(window) = app.get_window("main") else { let _ = tx.send(Err("Main window unavailable".into())); return; };
        let parent = match window.gtk_window() {
            Ok(parent) => parent,
            Err(error) => { let _ = tx.send(Err(crate::err(error))); return; }
        };
        let current = Rc::new(RefCell::new(None));
        let cleaned = Arc::new(AtomicBool::new(false));
        let (old, old_session) = match open_dialog_with_delay(parent.upcast_ref(), &dialog_view, current.clone(), Duration::from_millis(350), Some(cleaned.clone())) {
            Ok((dialog, _, _, session)) => (dialog, session),
            Err(error) => { let _ = tx.send(Err(error)); return; }
        };
        old.response(gtk::ResponseType::Close);
        let (dialog, entry, status, session) = match open_dialog_with_delay(parent.upcast_ref(), &dialog_view, current, Duration::ZERO, None) {
            Ok(opened) => opened,
            Err(error) => { let _ = tx.send(Err(error)); return; }
        };
        let controller = platform.inner().find_controller();
        let checked = Arc::new(AtomicU64::new(0));
        entry.set_text("VIBEZ_UNIQUE_REPLY_20_END");
        entry.emit_activate();
        let started = std::time::Instant::now();
        let mut tx = Some(tx);
        gtk::glib::timeout_add_local(Duration::from_millis(100), move || {
            let mut result = None;
            if started.elapsed() > Duration::from_secs(18) {
                result = Some(Err("Reopened Find did not complete ownership check".into()));
            } else if status.text() == "No matches." {
                result = Some(Err("Reopened Find lost its native match".into()));
            } else if cleaned.load(Ordering::SeqCst) && status.text().starts_with("1 match(es).") {
                if !session.current() || controller.as_ref().and_then(|c| c.search_text()).as_deref() != Some("VIBEZ_UNIQUE_REPLY_20_END") {
                    result = Some(Err("Old dialog cleanup cleared the reopened native search".into()));
                } else if checked.load(Ordering::SeqCst) == 0 {
                    checked.store(1, Ordering::SeqCst);
                    let completed = checked.clone();
                    let script = format!("(() => {{const lateOldPause={};const before=window.__vibezFindSession,s=window.__vibezRichRender?.status();const kept=lateOldPause===false&&before?.id==='{}'&&!before.closed&&Boolean(s?.paused.includes('find'));delete window.__vibezFindSession;{};const restored={};const owner=window.__vibezFindSession;return kept&&restored===true&&owner?.id==='{}'&&!owner.closed&&Boolean(window.__vibezRichRender?.status().paused.includes('find'));}})()", old_session.pause_script(), session.token(), session.claim_script(), session.pause_script(), session.token());
                    if dialog_view.eval_with_callback(script, move |raw| {
                        completed.store(if raw.trim() == "true" { 2 } else { 3 }, Ordering::SeqCst);
                    }).is_err() { checked.store(3, Ordering::SeqCst); }
                } else if checked.load(Ordering::SeqCst) == 2 {
                    result = Some(Ok(()));
                } else if checked.load(Ordering::SeqCst) == 3 {
                    result = Some(Err("Old dialog cleanup released the reopened Find pause".into()));
                }
            }
            if let Some(result) = result {
                dialog.response(gtk::ResponseType::Close);
                if let Some(tx) = tx.take() { let _ = tx.send(result); }
                gtk::glib::ControlFlow::Break
            } else { gtk::glib::ControlFlow::Continue }
        });
    }).map_err(crate::err)?;
    tokio::time::timeout(Duration::from_secs(22), rx).await.map_err(crate::err)?.map_err(crate::err)??;
    wait_restored(view).await?;
    println!("FIND_REOPEN_OK: delayed old cleanup preserved the new native query and rendering pause");
    Ok(())
}

pub fn attach(app: &AppHandle, view: &Webview) -> Result<(), String> {
    let parent = app.get_window("main").ok_or("Main window is unavailable")?.gtk_window().map_err(crate::err)?;
    let current: Rc<RefCell<Option<gtk::Dialog>>> = Rc::new(RefCell::new(None));
    let view = view.clone();
    parent.connect_key_press_event(move |parent, event| {
        let control = event.state().contains(gtk::gdk::ModifierType::CONTROL_MASK);
        if control && (event.keyval() == gtk::gdk::keys::constants::f || event.keyval() == gtk::gdk::keys::constants::F) {
            let existing = current.borrow().clone();
            if let Some(dialog) = existing { dialog.present(); }
            else { let _ = open_dialog(parent.upcast_ref(), &view, current.clone()); }
            return true.into();
        }
        false.into()
    });
    Ok(())
}
