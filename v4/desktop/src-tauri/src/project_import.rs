//! User-selected native file paths never come from remote or renderer strings.
use super::*;
use std::{path::PathBuf, time::{Duration, Instant}};

#[derive(Clone, Debug, PartialEq, Eq)]
struct Binding { project: String, revision: String }
struct Grant { id: String, binding: Binding, paths: Vec<PathBuf>, created: Instant }
#[derive(Clone, Debug, PartialEq, Eq)]
struct Plan { id: String, binding: Binding, items: std::collections::BTreeMap<String,bool> }
#[derive(Default)]
pub struct ImportState {
    binding: Mutex<Option<Binding>>,
    entered: Mutex<Option<Binding>>,
    grant: Mutex<Option<Grant>>,
    plan: Mutex<Option<Plan>>,
    serial: AtomicU64,
}
fn plan_id(value:&str)->bool {
    value.len()==32&&value.bytes().all(|c|c.is_ascii_alphanumeric()||c==b'_'||c==b'-')
}
fn item_id(value:&str)->bool {
    value.len()==24&&value.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c))
}
fn event_matches(event:&Value,current:&Binding)->bool {
    event["project_id"].as_str()==Some(current.project.as_str())&&event["binding"].as_str()==Some(current.revision.as_str())
}
fn snapshot_plan(event:&Value,current:&Binding)->Option<Plan> {
    if event["type"]!="web_import_conflicts"||!event_matches(event,current) {return None;}
    let id=event["plan_id"].as_str().filter(|id|plan_id(id))?;
    let rows=event["items"].as_array()?;
    if rows.len()>50||(rows.is_empty()&&event["confirm_required"]!=true) {return None;}
    let mut items=std::collections::BTreeMap::new();
    for item in rows {
        let key=item["id"].as_str().filter(|id|item_id(id))?;
        let replace=item["can_replace"].as_bool()?;
        if items.insert(key.to_owned(),replace).is_some() {return None;}
    }
    Some(Plan{id:id.into(),binding:current.clone(),items})
}
fn validate_choices(plan:&Plan,choices:&Value)->Result<Value,String> {
    let map=choices.as_object().ok_or("Choose what to do for each conflict")?;
    if map.len()!=plan.items.len() {return Err("The list of conflicts changed. Check the choices again.".into());}
    let mut result=serde_json::Map::new();
    for (id,can_replace) in &plan.items {
        let choice=map.get(id).and_then(Value::as_str).ok_or("Choose what to do for each conflict")?;
        if !matches!(choice,"skip"|"replace"|"keep_both")||choice=="replace"&&!*can_replace {return Err("This choice is not available for this conflict".into());}
        result.insert(id.clone(),json!(choice));
    }
    Ok(Value::Object(result))
}
fn validate_cancel_choices(choices:&Value)->Result<(),String> {
    if choices.is_null()||choices.as_object().is_some_and(|value|value.is_empty()) {Ok(())}
    else {Err("Cancel contains no file choices".into())}
}

fn local_panel(view:&Webview)->Result<(),String> {
    require_local(view)?;
    if view.label()!="connector-panel" {return Err("Use the project panel".into());}
    Ok(())
}
fn snapshot_binding(event:&Value)->Option<Binding> {
    if event["type"]!="web_connector"||!event["folder"].as_str().is_some_and(|folder|!folder.is_empty()) {return None;}
    event["project"]["id"].as_str().zip(event["import_binding"].as_str())
        .filter(|(project,revision)|!project.is_empty()&&revision.len()==64&&revision.bytes().all(|c|c.is_ascii_hexdigit()))
        .map(|(project,revision)|Binding{project:project.into(),revision:revision.into()})
}
pub fn observe(app:&tauri::AppHandle,event:&Value) {
    let state=app.state::<ImportState>();
    if event["type"]=="web_import_conflicts"||event["type"]=="web_import_result" {
        let current=state.binding.lock().ok().and_then(|value|value.clone());
        if let Some(current)=current.filter(|binding|event_matches(event,binding)) {
            if let Ok(mut pending)=state.plan.lock() {
                if event["type"]=="web_import_conflicts" {*pending=snapshot_plan(event,&current);}
                else {*pending=None;}
            }
        }
        return;
    }
    if event["type"]!="web_connector" {return;}
    let next=snapshot_binding(event);
    if let Ok(mut current)=state.binding.lock() {
        if *current!=next {
            *current=next;
            if let Ok(mut grant)=state.grant.lock() {*grant=None;}
            if let Ok(mut entered)=state.entered.lock() {*entered=None;}
            if let Ok(mut plan)=state.plan.lock() {*plan=None;}
        }
    };
}
fn current_binding(app:&tauri::AppHandle)->Result<Binding,String> {
    let current=app.state::<ImportState>().binding.lock().map_err(err)?.clone()
        .ok_or("Choose a workspace for this project first")?;
    let actual=app.state::<official_web::WebState>().project.lock().map_err(err)?.as_ref().map(|p|p.id.clone());
    if actual.as_deref()!=Some(current.project.as_str()) {return Err("The project has changed. Try again.".into());}
    Ok(current)
}
fn send_files(app:&tauri::AppHandle,expected:&Binding,paths:Vec<PathBuf>)->Result<(),String> {
    if current_binding(app)?!=*expected {return Err("The project folder has changed. Choose the files again.".into());}
    if paths.is_empty()||paths.len()>50 {return Err("Choose at most 50 files or folders at once".into());}
    let paths=paths.into_iter().map(|p|p.into_os_string().into_string().map_err(|_|"This file name cannot be processed".to_owned())).collect::<Result<Vec<_>,_>>()?;
    write_engine(app,&json!({"action":"web_import","project_id":expected.project,"binding":expected.revision,"paths":paths}))
}
fn emit(app:&tauri::AppHandle,value:Value) {
    let _=app.emit_to(EventTarget::Webview{label:"connector-panel".into()},"project-drop",value);
}
fn drop_position(_app:&tauri::AppHandle,x:f64,y:f64)->(f64,f64) {
    #[cfg(target_os="linux")]
    {(x,y)}
    #[cfg(not(target_os="linux"))]
    {let scale=_app.get_window("main").and_then(|w|w.scale_factor().ok()).filter(|v|v.is_finite()&&*v>0.).unwrap_or(1.);(x/scale,y/scale)}
}
pub fn attach(app:&tauri::AppHandle,view:&Webview) {
    #[cfg(target_os="linux")]
    if view.label()=="connector-panel"{attach_portal_drop(app,view);}

    let app=app.clone();
    view.on_webview_event(move |event| {
        let tauri::WebviewEvent::DragDrop(event)=event else {return;};
        let state=app.state::<ImportState>();
        match event {
            tauri::DragDropEvent::Enter{position,..}=>{
                if let Ok(mut grant)=state.grant.lock() {*grant=None;}
                let current=current_binding(&app).ok();
                if let Ok(mut entered)=state.entered.lock() {*entered=current;}
                let(x,y)=drop_position(&app,position.x,position.y);
                emit(&app,json!({"kind":"enter","x":x,"y":y}));
            }
            tauri::DragDropEvent::Over{position}=>{let(x,y)=drop_position(&app,position.x,position.y);emit(&app,json!({"kind":"over","x":x,"y":y}));},
            tauri::DragDropEvent::Leave=>{
                if let Ok(mut entered)=state.entered.lock() {*entered=None;}
                emit(&app,json!({"kind":"leave"}));
            }
            tauri::DragDropEvent::Drop{paths,position}=>{
                let previous=state.entered.lock().ok().and_then(|mut v|v.take());
                let current=current_binding(&app).ok();
                let mut id=None;
                if previous.is_some()&&previous==current&&paths.len()<=50&&!paths.is_empty() {
                    let value=state.serial.fetch_add(1,Ordering::SeqCst).to_string();
                    if let Ok(mut grant)=state.grant.lock() {
                        *grant=Some(Grant{id:value.clone(),binding:current.unwrap(),paths:paths.clone(),created:Instant::now()});id=Some(value);
                    }
                }
                let(x,y)=drop_position(&app,position.x,position.y);
                emit(&app,json!({"kind":"drop","x":x,"y":y,"grant":id,"count":paths.len()}));
            }
            _=>{}
        }
    });
}

#[cfg(target_os="linux")]
fn native_drop_grant(app:&tauri::AppHandle,expected:Binding,paths:Vec<PathBuf>,x:i32,y:i32)->bool {
    if paths.is_empty()||paths.len()>50||!paths.iter().all(|p|p.is_absolute())||current_binding(app).ok().as_ref()!=Some(&expected){return false;}
    let state=app.state::<ImportState>();let id=state.serial.fetch_add(1,Ordering::SeqCst).to_string();let count=paths.len();
    let Ok(mut grant)=state.grant.lock()else{return false;};*grant=Some(Grant{id:id.clone(),binding:expected,paths,created:Instant::now()});drop(grant);
    emit(app,json!({"kind":"drop","x":x,"y":y,"grant":id,"count":count}));true
}

// GTK file managers can send a portal transfer key instead of file:// URIs.
// Retrieve only the files from that OS drag; never grant general home access.
#[cfg(target_os="linux")]
fn attach_portal_drop(app:&tauri::AppHandle,view:&Webview) {
    use gtk::prelude::*;
    let app=app.clone();
    let _=view.with_webview(move|platform|{
        let panel=platform.inner().clone();
        install_drop_surface(app.clone(),panel.clone(),panel.upcast::<gtk::Widget>());
    });
}

#[cfg(target_os="linux")]
fn install_drop_surface(app:tauri::AppHandle,panel:webkit2gtk::WebView,widget:gtk::Widget) {
    use gtk::{prelude::*,gio,glib};use glib::variant::ToVariant;

        let app=app.clone();let panel=panel.clone();
        let atom=gtk::gdk::Atom::intern("application/vnd.portal.filetransfer");
        let uri_atom=gtk::gdk::Atom::intern("text/uri-list");
        fn targets(widget:&gtk::Widget){
            let list=widget.drag_dest_get_target_list().unwrap_or_else(||gtk::TargetList::new(&[]));
            let portal=gtk::gdk::Atom::intern("application/vnd.portal.filetransfer");let uri=gtk::gdk::Atom::intern("text/uri-list");
            list.remove(&portal);list.remove(&uri);
            list.add(&portal,0,991);list.add(&uri,0,992);
            // Keep WebKit's other targets, including internal text drags.
            // File transfers are explicitly finished after the actual Drop.
            widget.drag_dest_set(gtk::DestDefaults::empty(),&[],gtk::gdk::DragAction::COPY|gtk::gdk::DragAction::MOVE);
            widget.drag_dest_set_target_list(Some(&list));
        }
        targets(&widget);widget.connect_map(targets);
        let hover=std::rc::Rc::new(std::cell::RefCell::new(None::<(gtk::gdk::DragContext,Binding)>));
        let entered=hover.clone();let handle=app.clone();
        let motion_panel=panel.clone();let motion_window=widget.clone();
        widget.connect_drag_motion(move|_widget,context,x,y,time|{
            if context.list_targets().contains(&atom)||context.list_targets().contains(&uri_atom) {
                if !entered.borrow().as_ref().is_some_and(|(old,_)|old==context){*entered.borrow_mut()=current_binding(&handle).ok().map(|binding|(context.clone(),binding));}
                let(px,py)=motion_panel.translate_coordinates(&motion_window,0,0).unwrap_or((0,0));
                emit(&handle,json!({"kind":"over","x":x-px,"y":y-py}));
                context.drag_status(gtk::gdk::DragAction::COPY,time);return true;
            }
            false
        });
        let pending=std::rc::Rc::new(std::cell::RefCell::new(None::<gtk::gdk::DragContext>));
        let dropping=pending.clone();
        widget.connect_drag_drop(move|widget,context,_,_,time|{
            let target=if context.list_targets().contains(&atom){Some(atom)}else if context.list_targets().contains(&uri_atom){Some(uri_atom)}else{None};
            if let Some(target)=target{*dropping.borrow_mut()=Some(context.clone());widget.drag_get_data(context,&target,time);true}else{false}
        });
        let handle=app.clone();let receiver_window=widget.clone();
        widget.connect_drag_data_received(move|_,context,x,y,data,info,time|{
            // WebKit can request data while hovering. A real native Drop on
            // this exact OS drag context is required before retrieving files.
            if !matches!(info,991|992)||pending.borrow().as_ref()!=Some(context){return;}
            receiver_window.stop_signal_emission_by_name("drag-data-received");
            pending.borrow_mut().take();
            let(px,py)=panel.translate_coordinates(&receiver_window,0,0).unwrap_or((0,0));let(x,y)=(x-px,y-py);
            let expected=hover.borrow_mut().take().filter(|(old,_)|old==context).map(|(_,binding)|binding);

            if info==992 {
                let paths=data.uris().iter().map(|raw|url::Url::parse(raw).ok().filter(|u|u.scheme()=="file"&&u.host_str().is_none_or(|host|host=="localhost")).and_then(|u|u.to_file_path().ok())).collect::<Option<Vec<_>>>();
                let accepted=expected.zip(paths).is_some_and(|(binding,paths)|native_drop_grant(&handle,binding,paths,x,y));context.drop_finish(accepted,time);return;
            }
            let key=data.data();
            let key=std::str::from_utf8(&key).ok().map(|v|v.trim_end_matches('\0').to_owned());
            let Some((expected,key))=expected.zip(key).filter(|(b,k)|current_binding(&handle).ok().as_ref()==Some(b)&&!k.is_empty()&&k.len()<=1024&&!k.chars().any(char::is_control))else{context.drop_finish(false,time);return;};
            let app=handle.clone();let context=context.clone();
            gio::bus_get(gio::BusType::Session,None::<&gio::Cancellable>,move|connection|{
                let Ok(connection)=connection else{context.drop_finish(false,time);return;};
                let options=std::collections::HashMap::<String,glib::Variant>::new();
                let params=(key,options).to_variant();
                connection.call(Some("org.freedesktop.portal.Documents"),"/org/freedesktop/portal/documents","org.freedesktop.portal.FileTransfer","RetrieveFiles",Some(&params),None,gio::DBusCallFlags::NONE,15000,None::<&gio::Cancellable>,move|result|{
                    let paths=result.ok().and_then(|v|v.get::<(Vec<String>,)>()).map(|(v,)|v.into_iter().map(PathBuf::from).collect::<Vec<_>>());
                    let accepted=paths.is_some_and(|paths|native_drop_grant(&app,expected,paths,x,y));context.drop_finish(accepted,time);

                });
            });
        });
}

#[cfg(target_os="linux")]
pub fn attach_web_hover(view:&Webview){
    let _=view.with_webview(|platform|{
        use gtk::prelude::*;let widget=platform.inner();
        widget.drag_dest_set_track_motion(true);
        widget.connect_drag_motion(|_,context,_,_,time|{
            if context.list_targets().contains(&gtk::gdk::Atom::intern("application/vnd.portal.filetransfer")){
                // WebKit can otherwise leave the OS source waiting forever
                // while the pointer travels toward the adjacent local panel.
                context.drag_status(gtk::gdk::DragAction::empty(),time);
            }false
        });
    });
}

#[tauri::command]
pub async fn project_import_commit(webview:Webview,app:tauri::AppHandle,grant:String)->Result<(),String> {
    local_panel(&webview)?;
    let state=app.state::<official_web::WebState>();
    let _gate=state.gate.lock().await;
    official_web::sync(&app).await?;
    let chosen=app.state::<ImportState>().grant.lock().map_err(err)?.take()
        .filter(|g|g.id==grant&&g.created.elapsed()<Duration::from_secs(30))
        .ok_or("Drag the files to the project folder again")?;
    send_files(&app,&chosen.binding,chosen.paths)
}

#[tauri::command]
pub async fn project_import_choose(webview:Webview,app:tauri::AppHandle,project_id:String,binding:String,folders:Option<bool>)->Result<bool,String> {
    local_panel(&webview)?;
    let state=app.state::<official_web::WebState>();
    let _gate=state.gate.lock().await;
    official_web::sync(&app).await?;
    let before=current_binding(&app)?;
    if before.project!=project_id||before.revision!=binding {return Err("The project has changed. Choose the files again.".into());}
    #[cfg(target_os="linux")]
    let paths:Result<Vec<PathBuf>,String> = {
    let handle=app.clone();let(tx,rx)=tokio::sync::oneshot::channel();
    app.run_on_main_thread(move ||{
        let result=(||{
            let s=screen(&handle)?;
            let parent=handle.get_window("main").ok_or("Het VibeZ-venster ontbreekt")?.gtk_window().map_err(err)?;
            let folder_mode=folders.unwrap_or(false);
            let title=classic_language::text(&handle,if folder_mode {"addFolder"}else{"addFiles"});
            let cancel=classic_language::text(&handle,"cancel");
            let accept=title.clone();
            let action=if folder_mode {gtk::FileChooserAction::SelectFolder}else{gtk::FileChooserAction::Open};
            if is_flatpak() {
                return Ok(portal_pick(&parent,&title,action,&accept,&cancel,true)?.unwrap_or_default());
            }
            let dialog=gtk::FileChooserDialog::with_buttons(Some(&title),Some(&parent),action,
                &[(cancel.as_str(),gtk::ResponseType::Cancel),(accept.as_str(),gtk::ResponseType::Accept)]);
            dialog.set_select_multiple(true);dialog.set_position(gtk::WindowPosition::None);
            position_dialog(&handle,&dialog,s)?;
            let response=dialog.run();
            let paths=if response==gtk::ResponseType::Accept {dialog.filenames()} else {Vec::new()};
            dialog.close();Ok(paths)
        })();let _=tx.send(result);
    }).map_err(err)?;
    rx.await.map_err(err)?

    };
    #[cfg(not(target_os="linux"))]
    let paths=platform_desktop::import_paths(&app,folders.unwrap_or(false)).await;
    let paths=paths?;if paths.is_empty(){return Ok(false);}
    official_web::sync(&app).await?;
    send_files(&app,&before,paths)?;Ok(true)
}

#[tauri::command]
pub async fn project_import_resolve(webview:Webview,app:tauri::AppHandle,project_id:String,binding:String,plan_id:String,choices:Value,cancel:Option<bool>)->Result<(),String> {
    local_panel(&webview)?;
    if !self::plan_id(&plan_id) {return Err("Invalid file selection. Add the files again.".into());}
    let state=app.state::<official_web::WebState>();
    let _gate=state.gate.lock().await;
    official_web::sync(&app).await?;
    let current=current_binding(&app)?;
    if current.project!=project_id||current.revision!=binding {return Err("The project has changed. Check the files again.".into());}
    let import=app.state::<ImportState>();
    let mut pending=import.plan.lock().map_err(err)?;
    let plan=pending.as_ref().filter(|plan|plan.id==plan_id&&plan.binding==current)
        .ok_or("This file selection has expired. Add the files again.")?;
    let command=if cancel.unwrap_or(false) {
        validate_cancel_choices(&choices)?;
        json!({"action":"web_import_cancel","project_id":current.project,"binding":current.revision,"plan_id":plan.id})
    }else{
        let choices=validate_choices(plan,&choices)?;
        json!({"action":"web_import_resolve","project_id":current.project,"binding":current.revision,"plan_id":plan.id,"choices":choices})
    };
    write_engine(&app,&command)?;
    *pending=None;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn snapshot()->Value {json!({"type":"web_connector","project":{"id":"work-fixture","name":"Fixture"},"folder":"/fixtures/Alpha","import_binding":"a".repeat(64),"token":"fixture-secret-not-retained","local_files":[{"name":"fixture.txt"}]})}
    #[test]
    fn native_drop_binding_requires_current_project_folder_and_hex_revision() {
        let valid=snapshot();
        assert_eq!(snapshot_binding(&valid),Some(Binding{project:"work-fixture".into(),revision:"a".repeat(64)}));
        for field in ["project","folder","import_binding"] {
            let mut value=valid.clone();value[field]=Value::Null;assert_eq!(snapshot_binding(&value),None);
        }
        for (field,value) in [("folder",json!("")),("import_binding",json!("z".repeat(64))),("import_binding",json!("a".repeat(63))),("type",json!("web_auto"))] {
            let mut event=valid.clone();event[field]=value;assert_eq!(snapshot_binding(&event),None);
        }
        let mut event=valid.clone();event["project"]["id"]=json!("");assert_eq!(snapshot_binding(&event),None);
    }
    #[test]
    fn native_binding_retains_no_file_paths_credentials_or_file_contents() {
        let event=snapshot();let retained=snapshot_binding(&event).unwrap();
        let debug=format!("{retained:?}");
        assert!(!debug.contains("/fixtures/"));assert!(!debug.contains("fixture-secret"));assert!(!debug.contains("fixture.txt"));
    }
    fn conflict()->(Binding,Value) {
        let current=Binding{project:"work-fixture".into(),revision:"a".repeat(64)};
        let event=json!({"type":"web_import_conflicts","project_id":current.project,"binding":current.revision,
            "plan_id":"p".repeat(32),"items":[{"id":"b".repeat(24),"name":"existing.txt","source_kind":"file","target_kind":"file","can_replace":true}]});
        (current,event)
    }
    #[test]
    fn conflict_plan_is_scoped_bounded_and_retains_no_source_paths_or_names() {
        let (current,event)=conflict();let plan=snapshot_plan(&event,&current).unwrap();
        assert_eq!(plan.binding,current);assert_eq!(plan.items.len(),1);
        assert!(!format!("{plan:?}").contains("existing.txt"));
        for field in ["project_id","binding","plan_id","items"] {
            let mut invalid=event.clone();invalid[field]=Value::Null;assert!(snapshot_plan(&invalid,&current).is_none());
        }
        for id in ["/tmp/file", "../file", "p", "p pppppppppppppppppppppppppppppp"] {
            let mut invalid=event.clone();invalid["plan_id"]=json!(id);assert!(snapshot_plan(&invalid,&current).is_none());
        }
        let mut invalid=event.clone();invalid["items"][0]["id"]=json!("/tmp/file");assert!(snapshot_plan(&invalid,&current).is_none());
        let mut invalid=event.clone();invalid["items"].as_array_mut().unwrap().push(event["items"][0].clone());assert!(snapshot_plan(&invalid,&current).is_none());
    }
    #[test]
    fn resolutions_accept_only_complete_known_item_ids_and_allowlisted_choices() {
        let(current,event)=conflict();let mut plan=snapshot_plan(&event,&current).unwrap();let id="b".repeat(24);
        for choice in ["skip","replace","keep_both"] {
            let mut map=serde_json::Map::new();map.insert(id.clone(),json!(choice));let value=Value::Object(map);
            assert_eq!(validate_choices(&plan,&value).unwrap(),value);
        }
        for invalid in [json!("replace"),json!([]),json!(null),json!({}),json!({"/tmp/file":"replace"}),json!({"paths":["/tmp/file"]})] {
            assert!(validate_choices(&plan,&invalid).is_err());
        }
        for choice in [json!("delete"),json!("/tmp/file"),json!({"path":"/tmp/file"}),json!(true)] {
            let mut map=serde_json::Map::new();map.insert(id.clone(),choice);assert!(validate_choices(&plan,&Value::Object(map)).is_err());
        }
        plan.items.insert(id.clone(),false);let mut map=serde_json::Map::new();map.insert(id,json!("replace"));assert!(validate_choices(&plan,&Value::Object(map)).is_err());
    }
    #[test]
    fn explicit_reconfirmation_can_have_zero_conflicts_and_cancel_never_accepts_paths() {
        let(current,mut event)=conflict();event["items"]=json!([]);
        assert!(snapshot_plan(&event,&current).is_none());
        event["confirm_required"]=json!(true);let plan=snapshot_plan(&event,&current).unwrap();
        assert_eq!(validate_choices(&plan,&json!({})).unwrap(),json!({}));
        assert!(validate_cancel_choices(&json!({})).is_ok());assert!(validate_cancel_choices(&Value::Null).is_ok());
        assert!(validate_cancel_choices(&json!({"paths":["/tmp/file"]})).is_err());
    }
}
