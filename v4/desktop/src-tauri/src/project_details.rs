//! A bounded mirror of verified visible Work overview controls, with no private APIs.
use super::*;

const MAX_CACHED_PROJECTS:usize=32;
#[derive(Default)]
struct DetailsCache {
    verified:std::collections::BTreeMap<String,Value>,
    order:std::collections::VecDeque<String>,
    last:Option<Value>,
}
impl DetailsCache {
    fn forget(&mut self,id:&str) {
        self.verified.remove(id);self.order.retain(|known|known!=id);
    }
    fn remember(&mut self,id:&str,data:&Value) {
        // A lazy-mount transition is not evidence that previously verified
        // controls disappeared. It also cannot create a new cache entry.
        if valid_id(id)&&pending_details(data){return;}
        if !valid_id(id)||data["available"]!=true {self.forget(id);return;}
        let mut data=data.clone();data["project_id"]=json!(id);
        data["cached"]=json!(false);data["can_open_project"]=json!(data["reason"]!="composer_busy");
        self.order.retain(|known|known!=id);self.order.push_back(id.into());
        self.verified.insert(id.into(),data);
        while self.order.len()>MAX_CACHED_PROJECTS {if let Some(old)=self.order.pop_front(){self.verified.remove(&old);}}
    }
    fn for_chat(&self,id:&str)->Option<Value> {
        let mut data=self.verified.get(id)?.clone();
        data["cached"]=json!(true);data["can_edit"]=json!(false);data["can_context"]=json!(false);data["can_open_project"]=json!(true);
        if let Some(settings)=data["settings"].as_array_mut() {
            for setting in settings {
                if let Some(object)=setting.as_object_mut(){object.remove("action");object.remove("action_label");}
            }
        }
        Some(data)
    }
}
fn cache()->&'static Mutex<DetailsCache> {
    static CACHE:std::sync::OnceLock<Mutex<DetailsCache>>=std::sync::OnceLock::new();
    CACHE.get_or_init(||Mutex::new(DetailsCache::default()))
}
fn valid_id(id:&str)->bool {
    id.len()==36&&id.chars().enumerate().all(|(i,c)|if [8,13,18,23].contains(&i){c=='-'}else{c.is_ascii_hexdigit()})
}

fn origin(url: &url::Url) -> bool {
    url.scheme() == "https" && matches!(url.host_str(), Some("chat.mistral.ai" | "vibe.mistral.ai"))
        && url.port_or_known_default() == Some(443) && url.username().is_empty() && url.password().is_none()
}
fn overview(url: &url::Url, project_id: &str) -> bool {
    valid_id(project_id)
        && origin(url)
        && [format!("/work/projects/{project_id}"),format!("/work/projects/{project_id}/")].contains(&url.path().to_owned())
}
fn work_chat(url:&url::Url)->bool {
    if !origin(url){return false;}
    let parts:Vec<_>=url.path().split('/').collect();
    match parts.as_slice() {
        ["","work",id]|["","work",id,""]=>valid_id(id),
        ["","work","chat"|"chats"|"c",id]|["","work","chat"|"chats"|"c",id,""]=>valid_id(id),
        _=>false,
    }
}
fn unavailable(can_open_project:bool)->Value {
    json!({"available":false,"cached":false,"can_open_project":can_open_project,"settings":[]})
}
fn cached_for_current(cache:&DetailsCache,url:&url::Url,project_id:Option<&str>,confirmed:bool)->Option<Value> {
    let id=project_id.filter(|id|valid_id(id))?;
    if !confirmed||!work_chat(url){return None;}
    Some(cache.for_chat(id).unwrap_or_else(||unavailable(true)))
}
fn can_open_project(current:&url::Url,target:&url::Url,id:&str,confirmed:bool)->bool {
    valid_id(id)&&overview(target,id)&&(overview(current,id)||work_chat(current))&&confirmed
}
fn script(project_id: Option<&str>, action: Option<&str>, enabled: Option<bool>) -> String {
    include_str!("project_details.js")
        .replace("__VIBEZ_PROJECT_ID__", &serde_json::to_string(&project_id.unwrap_or("")).unwrap())
        .replace("__VIBEZ_PROJECT_ACTION__", &serde_json::to_string(&action).unwrap())
        .replace("__VIBEZ_PROJECT_ENABLED__", &serde_json::to_string(&enabled).unwrap())
}

// A single in-memory draft belongs to a native-confirmed Work overview. The
// website form is closed while the user types in the local project panel.
#[derive(Clone)]
struct RulesDraft { project:String,url:String,nonce:String,value:String,opened:std::time::Instant }
fn rules_draft()->&'static Mutex<Option<RulesDraft>> {
    static DRAFT:std::sync::OnceLock<Mutex<Option<RulesDraft>>>=std::sync::OnceLock::new();
    DRAFT.get_or_init(||Mutex::new(None))
}
fn rules_nonce()->Result<String,String> {
    let mut bytes=[0_u8;16];
    getrandom::fill(&mut bytes).map_err(err)?;
    Ok(bytes.iter().map(|byte|format!("{byte:02x}")).collect())
}
fn valid_rules_text(value:&str)->bool { value.encode_utf16().count()<=8000 && !value.contains('\0') }
fn rules_script(project:&str,action:&str,nonce:&str,expected:Option<&str>,value:Option<&str>)->String {
    let source=include_str!("project_rules_form.js");
    // Replace only the final argument list so user text containing a marker
    // remains literal, and can never be recursively interpreted as source.
    let (body,_) = source.rsplit_once(")(__VIBEZ_RULES_PROJECT__").expect("rules argument boundary");
    format!("{body})({}, {}, {}, {}, {})\n",json!(project),json!(action),json!(nonce),json!(expected),json!(value))
}
fn matching_rules_draft(draft:&RulesDraft,project:&str,url:&url::Url,nonce:&str)->bool {
    draft.project==project && draft.url==url.as_str() && draft.nonce==nonce &&
        draft.opened.elapsed()<std::time::Duration::from_secs(30*60) && overview(url,project)
}
fn require_rules_context(app:&tauri::AppHandle,view:&Webview,url:&url::Url,project:&str)->Result<(),String> {
    if view.url().map_err(err)?!=*url || !overview(url,project) || !official_web::confirmed_project(app,url,project) {
        return Err("Open the overview of this Mistral project first".into());
    }
    Ok(())
}
async fn rules_eval(app:&tauri::AppHandle,view:&Webview,url:&url::Url,project:&str,action:&str,nonce:&str,expected:Option<&str>,value:Option<&str>)->Result<Value,String> {
    require_rules_context(app,view,url,project)?;
    let raw=official_web::eval(view,&rules_script(project,action,nonce,expected,value)).await?;
    require_rules_context(app,view,url,project)?;
    if raw.len()>65536 {return Err("Het instructieformulier is te groot".into());}
    serde_json::from_str(&raw).map_err(err)
}
// The tabbed website mounts either its project settings or its composer.
// Finish each short settings visit before the native gate is released so the
// original composer is mounted again. No draft contents cross this bridge.
fn pending_details(data:&Value)->bool { data["pending"]==true }
fn details_error(data:&Value)->String {
    match data["reason"].as_str() {
        Some("composer_busy")=>"Finish your message or attachment before changing the project settings.".into(),
        Some("dialog_open")=>"Close the open Mistral window and try again.".into(),
        _=>"Open this project again to change the settings.".into(),
    }
}
async fn wait_details(app:&tauri::AppHandle,view:&Webview,url:&url::Url,project:&str,action:Option<&str>,enabled:Option<bool>)->Result<Value,String> {
    let deadline=std::time::Instant::now()+std::time::Duration::from_secs(2);
    loop {
        require_rules_context(app,view,url,project)?;
        let raw=official_web::eval(view,&script(Some(project),action,enabled)).await?;
        require_rules_context(app,view,url,project)?;
        if raw.len()>131072 {return Err("The project settings are too large".into());}
        let data:Value=serde_json::from_str(&raw).map_err(err)?;
        if !data.is_object(){return Err("The project settings are not available".into());}
        if !pending_details(&data)||std::time::Instant::now()>=deadline{return Ok(data);}
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    }
}
async fn finish_settings(app:&tauri::AppHandle,view:&Webview,url:&url::Url,project:&str)->Result<Value,String> {
    let result=async {
        let data=wait_details(app,view,url,project,Some("finish"),None).await?;
        if pending_details(&data){return Err("Mistral has not restored the input field yet. Open the project again.".into());}
        if data["finished"]==false||(data["finished"]!=true&&data["available"]!=true){return Err(details_error(&data));}
        Ok(data)
    }.await;
    if result.is_err()&&require_rules_context(app,view,url,project).is_ok() {
        // An empty expected project only restores our recorded styles. Even
        // when React declines a tab switch, its own tabs remain recoverable.
        let _=official_web::eval(view,&script(None,None,None)).await;
    }
    result
}
async fn open_rules_form(app:&tauri::AppHandle,view:&Webview,url:&url::Url,project:&str)->Result<(),String> {
    let result=wait_details(app,view,url,project,Some("instructions"),None).await?;
    if result["acted"]!=true {return Err(details_error(&result));}
    Ok(())
}
async fn wait_rules_form(app:&tauri::AppHandle,view:&Webview,url:&url::Url,project:&str,action:&str,nonce:&str,expected:Option<&str>,value:Option<&str>)->Result<Value,String> {
    for _ in 0..16 {
        let data=rules_eval(app,view,url,project,action,nonce,expected,value).await?;
        if action=="read"&&(data["ready"]==true||data["reason"]=="too_long") {
            for _ in 0..16 {
                if rules_eval(app,view,url,project,"status",nonce,None,None).await?["closed"]==true {return Ok(data);}
                tokio::time::sleep(std::time::Duration::from_millis(75)).await;
            }
            return Err("Mistral has not closed the instructions window yet".into());
        }
        if data["reason"]!="form_unavailable" {return Ok(data);}
        tokio::time::sleep(std::time::Duration::from_millis(75)).await;
    }
    Err("The Mistral instructions form is not available".into())
}
/// Only explicit panel actions open or save the proved native instructions
/// form. Saved content is read back from that same form before success.
#[tauri::command]
pub async fn project_rules_edit(webview:Webview,app:tauri::AppHandle,project_id:String,action:String,value:Option<String>,nonce:Option<String>)->Result<Value,String> {
    require_local(&webview)?;
    if webview.label()!="connector-panel" {return Err("Use the project panel".into());}
    if !valid_id(&project_id)||!matches!(action.as_str(),"open"|"save"|"cancel"|"api-read"|"api-save") {return Err("Onbekende projecthandeling".into());}
    let state=app.state::<official_web::WebState>();
    let _gate=state.gate.lock().await;
    if action=="cancel" {
        let mut draft=rules_draft().lock().map_err(err)?;
        if draft.as_ref().is_some_and(|draft|draft.project==project_id&&Some(draft.nonce.as_str())==nonce.as_deref()) {*draft=None;}
        return Ok(json!({"project_id":project_id,"cancelled":true}));
    }
    let view=app.get_webview("mistral-web").ok_or("Mistral has not loaded yet")?;
    let url=view.url().map_err(err)?;
    if action=="api-read"||action=="api-save" {return rules_api(&app,&view,&url,&project_id,&action,value).await;}
    require_rules_context(&app,&view,&url,&project_id)?;
    let result=async {
    if action=="open" {
        *rules_draft().lock().map_err(err)?=None;
        let nonce=rules_nonce()?;
        open_rules_form(&app,&view,&url,&project_id).await?;
        let result=wait_rules_form(&app,&view,&url,&project_id,"read",&nonce,None,None).await?;
        let value=result["value"].as_str().filter(|value|result["ready"]==true&&valid_rules_text(value)).ok_or("The instructions form cannot be read safely")?.to_owned();
        *rules_draft().lock().map_err(err)?=Some(RulesDraft{project:project_id.clone(),url:url.as_str().into(),nonce:nonce.clone(),value:value.clone(),opened:std::time::Instant::now()});
        return Ok(json!({"project_id":project_id,"value":value,"nonce":nonce}));
    }
    let value=value.filter(|value|valid_rules_text(value)).ok_or("Use at most 8000 characters for the project rules")?;
    let nonce=nonce.ok_or("Open the project rules again")?;
    let draft=rules_draft().lock().map_err(err)?.clone().filter(|draft|matching_rules_draft(draft,&project_id,&url,&nonce)).ok_or("The project changed; open the project rules again")?;
    open_rules_form(&app,&view,&url,&project_id).await?;
    if value==draft.value {
        let current=wait_rules_form(&app,&view,&url,&project_id,"read",&nonce,None,None).await?;
        if current["ready"]!=true||current["value"].as_str()!=Some(value.as_str()) {return Err("The project rules changed in the meantime; open them again".into());}
        *rules_draft().lock().map_err(err)?=None;
        return Ok(json!({"project_id":project_id,"saved":true}));
    }
    let fill=wait_rules_form(&app,&view,&url,&project_id,"fill",&nonce,Some(&draft.value),Some(&value)).await?;
    if fill["reason"]=="stale" {return Err("The project rules changed in the meantime; open them again".into());}
    if fill["filled"]!=true {return Err("The instructions form changed; open the project rules again".into());}
    let mut submitted=Value::Null;
    for _ in 0..16 {
        tokio::time::sleep(std::time::Duration::from_millis(75)).await;
        submitted=rules_eval(&app,&view,&url,&project_id,"submit",&nonce,None,None).await?;
        if submitted["reason"]!="submit_pending" {break;}
    }
    if submitted["submitted"]!=true {
        let _=rules_eval(&app,&view,&url,&project_id,"abort",&nonce,None,None).await;
        return Err("Mistral could not save the project rules".into());
    }
    let mut closed=false;
    for _ in 0..40 {
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        if rules_eval(&app,&view,&url,&project_id,"status",&nonce,None,None).await?["closed"]==true {closed=true;break;}
    }
    if !closed {
        let _=rules_eval(&app,&view,&url,&project_id,"abort",&nonce,None,None).await;
        return Err("Mistral has not confirmed saving yet; open the project rules again".into());
    }
    open_rules_form(&app,&view,&url,&project_id).await?;
    let confirmation=wait_rules_form(&app,&view,&url,&project_id,"read",&nonce,None,None).await?;
    if confirmation["ready"]!=true||confirmation["value"].as_str()!=Some(value.as_str()) {return Err("Mistral did not confirm the changed project rules".into());}
    *rules_draft().lock().map_err(err)?=None;
    Ok(json!({"project_id":project_id,"saved":true}))
    }.await;
    // This is deliberately outside the whole read/save/read-back operation:
    // switching tabs sooner would detach the original instructions dialog.
    let finished=finish_settings(&app,&view,&url,&project_id).await;
    match result {
        Ok(value)=>{finished?;sync(&app).await?;Ok(value)},
        Err(error)=>Err(error),
    }
}
fn publish(app: &tauri::AppHandle, mut data: Value, project_id: Option<&str>) -> Result<(),String> {
    data["project_id"] = json!(project_id);
    let mut cached = cache().lock().map_err(err)?;
    if cached.last.as_ref() != Some(&data) {
        app.emit_to(EventTarget::Webview{label:"connector-panel".into()}, "project-details", data.clone()).map_err(err)?;
        cached.last = Some(data);
    }
    Ok(())
}
/// Replay cached settings when the user opens the panel after its listener loads.
/// A cache for an unconfirmed chat or a different project is never replayed.
pub fn replay(app: &tauri::AppHandle) -> Result<(),String> {
    let state=app.state::<official_web::WebState>();
    let project_id={let project=state.project.lock().map_err(err)?;project.as_ref().map(|p|p.id.clone())};
    let current=app.get_webview("mistral-web").and_then(|view|view.url().ok());
    let confirmed=project_id.as_deref().is_some_and(|id|current.as_ref().is_some_and(|url|official_web::confirmed_project(app,url,id)));
    let cached=cache().lock().map_err(err)?;
    let mut data=if let Some(url)=current.as_ref() {
        cached_for_current(&cached,url,project_id.as_deref(),confirmed).or_else(||{
            let valid=confirmed&&project_id.as_deref().is_some_and(|id|overview(url,id));
            cached.last.clone().filter(|data|valid&&data["cached"]!=true&&data["project_id"].as_str()==project_id.as_deref())
        }).unwrap_or_else(||unavailable(confirmed&&project_id.as_deref().is_some_and(|id|valid_id(id)&&(overview(url,id)||work_chat(url)))))
    }else{unavailable(false)};
    data["project_id"]=json!(project_id);
    app.emit_to(EventTarget::Webview{label:"connector-panel".into()},"project-details",data).map_err(err)
}
/// Call after native project recognition; this function does not acquire its gate.
pub async fn sync(app: &tauri::AppHandle) -> Result<(),String> {
    let state = app.state::<official_web::WebState>();
    let project_id = { let project = state.project.lock().map_err(err)?; project.as_ref().map(|p|p.id.clone()) };
    let Some(view) = app.get_webview("mistral-web") else {return publish(app,unavailable(false),None);};
    let url = view.url().map_err(err)?;
    if !origin(&url) {return publish(app,unavailable(false),None);}
    let expected = project_id.as_deref().filter(|id|overview(&url,id));
    let confirmed=project_id.as_deref().is_some_and(|id|official_web::confirmed_project(app,&url,id));
    // Only a native-confirmed overview may request a short settings visit.
    // Other routes merely restore former presentation without reading chats.
    let data=if let Some(id)=expected.filter(|_|confirmed) {
        match wait_details(app,&view,&url,id,None,None).await {
            Ok(data) if pending_details(&data)=>{
                // Preserve a same-project snapshot during transient mounting;
                // never publish it as proof for a different route or project.
                let _=finish_settings(app,&view,&url,id).await;
                return Ok(());
            },
            Ok(data)=>Some(data),
            Err(_)=>{let _=finish_settings(app,&view,&url,id).await;None},
        }
    }else{
        let _=official_web::eval(&view,&script(None,None,None)).await;
        None
    };
    if view.url().map_err(err)? != url {return publish(app,unavailable(false),None);}
    if expected.is_none() {
        let data={
            let cached=cache().lock().map_err(err)?;
            cached_for_current(&cached,&url,project_id.as_deref(),confirmed).unwrap_or_else(||unavailable(false))
        };
        return publish(app,data,project_id.as_deref());
    }
    let id=expected.unwrap();
    let mut data=data.filter(|data|data["available"].is_boolean()).unwrap_or_else(||unavailable(true));
    cache().lock().map_err(err)?.remember(id,&data);
    data["cached"]=json!(false);
    // Reloading the overview would throw away the draft that just blocked a
    // settings visit. Keep that action absent until the composer is safe.
    data["can_open_project"]=json!(data["reason"]!="composer_busy");
    publish(app,data,Some(id))
}

#[tauri::command]
pub async fn project_details_action(webview: Webview, app: tauri::AppHandle, project_id: String, action: String, enabled: Option<bool>) -> Result<(),String> {
    require_local(&webview)?;
    if webview.label() != "connector-panel" {return Err("Use the project panel".into());}
    if !matches!(action.as_str(),"instructions"|"context"|"open_project") || (action=="context" && enabled.is_none()) {
        return Err("Onbekende projecthandeling".into());
    }
    let state = app.state::<official_web::WebState>();
    let _gate = state.gate.lock().await;
    let target={
        let project = state.project.lock().map_err(err)?;
        if project.as_ref().map(|p|p.id.as_str()) != Some(project_id.as_str()) {return Err("Het Mistral-project is gewisseld".into());}
        project.as_ref().map(|p|p.url.clone()).unwrap()
    };
    let view = app.get_webview("mistral-web").ok_or("Mistral has not loaded yet")?;
    let url = view.url().map_err(err)?;
    if action=="open_project" {
        let target:url::Url=target.parse().map_err(err)?;
        if !can_open_project(&url,&target,&project_id,official_web::confirmed_project(&app,&url,&project_id)) {
            return Err("Open this Mistral project first".into());
        }
        return view.navigate(target).map_err(err);
    }
    if !overview(&url,&project_id) {return Err("Open the overview of this Mistral project first".into());}
    let result=wait_details(&app,&view,&url,&project_id,Some(&action),enabled).await;
    let finished=finish_settings(&app,&view,&url,&project_id).await;
    let result=result?;
    if result["acted"]!=true&&result["unchanged"]!=true{return Err(details_error(&result));}
    // Direct native-instructions callers keep their opened dialog. finish
    // reveals the original website while it is open; it never closes it.
    if action!="instructions" {finished?;}
    sync(&app).await
}

#[cfg(test)]
mod tests {
    use super::*;
    const ID:&str="229ee257-4177-4f98-969c-3055311c7cae";
    #[test]
    fn actions_require_exact_trusted_work_overview() {
        assert!(overview(&format!("https://chat.mistral.ai/work/projects/{ID}").parse().unwrap(),ID));
        for url in [format!("https://example.org/work/projects/{ID}"),format!("https://chat.mistral.ai/code/{ID}"),format!("https://chat.mistral.ai/work/{ID}"),format!("https://chat.mistral.ai/work/projects/{ID}/settings"),format!("https://user@chat.mistral.ai/work/projects/{ID}")] {
            assert!(!overview(&url.parse().unwrap(),ID),"{url}");
        }
        assert!(!overview(&format!("https://chat.mistral.ai/work/projects/{ID}").parse().unwrap(),"../project"));
    }
    #[test]
    fn action_inputs_are_json_literals_and_no_arbitrary_selector_is_accepted() {
        let value=script(Some(ID),Some("context"),Some(true));
        assert!(!value.contains("__VIBEZ_PROJECT_"));
        assert!(value.ends_with("\"context\", true)\n"));
    }
    fn settings(text:&str)->Value {
        json!({"available":true,"tone":"Default","instructions":text,"context_checked":true,"can_edit":true,"can_context":true,
            "settings":[{"kind":"tone","label":"Tone","text":"Default"},
                {"kind":"instructions","label":"Instructions","text":text,"action":"instructions","action_label":"Edit"},
                {"kind":"context","label":"Context","text":"Include chats","checked":true,"action":"context"}]})
    }
    #[test]
    fn rules_cache_preserves_only_same_confirmed_project_and_disables_cached_actions() {
        let mut cache=DetailsCache::default();cache.remember(ID,&settings("Alpha rules"));
        let other="cace260d-d95d-4859-b45b-f56f185f15da";cache.remember(other,&settings("Beta rules"));
        let chat:url::Url="https://chat.mistral.ai/work/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa".parse().unwrap();
        let cached=cached_for_current(&cache,&chat,Some(ID),true).unwrap();
        assert_eq!(cached["instructions"],"Alpha rules");assert_eq!(cached["project_id"],ID);
        assert_eq!(cached["cached"],true);assert_eq!(cached["can_edit"],false);assert_eq!(cached["can_context"],false);assert_eq!(cached["can_open_project"],true);
        for item in cached["settings"].as_array().unwrap(){assert!(item.get("action").is_none());assert!(item.get("action_label").is_none());}
        assert_eq!(cache.verified[ID]["can_edit"],true);assert_eq!(cache.verified[ID]["settings"][1]["action"],"instructions");
        assert_eq!(cached_for_current(&cache,&chat,Some(other),true).unwrap()["instructions"],"Beta rules");
        assert!(cached_for_current(&cache,&chat,Some(ID),false).is_none());
        assert!(cached_for_current(&cache,&chat,None,true).is_none());
        assert!(cached_for_current(&cache,&chat,Some(&format!("code-{ID}")),true).is_none());
    }
    #[test]
    fn untrusted_unknown_and_non_chat_routes_never_receive_rules_cache() {
        let mut cache=DetailsCache::default();cache.remember(ID,&settings("Private rules"));
        for raw in ["https://example.org/work/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","https://user:secret@chat.mistral.ai/work/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "https://chat.mistral.ai:444/work/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","https://chat.mistral.ai/work/settings","https://chat.mistral.ai/work/new",
            "https://chat.mistral.ai/work/chat/not-a-chat","https://chat.mistral.ai/work/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/extra",
            "https://chat.mistral.ai//work/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","https://chat.mistral.ai/work/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa//",
            "https://chat.mistral.ai/code/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"] {
            let url=raw.parse().unwrap();assert!(cached_for_current(&cache,&url,Some(ID),true).is_none(),"{raw}");
        }
        for prefix in ["work","work/chat","work/chats","work/c"] {
            for ending in ["","/"] {
                let url=format!("https://vibe.mistral.ai/{prefix}/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa{ending}?tab=context#section").parse().unwrap();
                assert!(cached_for_current(&cache,&url,Some(ID),true).is_some());
            }
        }
    }
    #[test]
    fn fresh_unavailable_removes_only_that_projects_cache_and_missing_cache_is_honest() {
        let mut cache=DetailsCache::default();cache.remember(ID,&settings("Old rules"));
        let other="cace260d-d95d-4859-b45b-f56f185f15da";cache.remember(other,&settings("Other rules"));
        cache.remember(ID,&unavailable(true));assert!(cache.for_chat(ID).is_none());assert!(cache.for_chat(other).is_some());
        let chat="https://chat.mistral.ai/work/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa".parse().unwrap();
        let data=cached_for_current(&cache,&chat,Some(ID),true).unwrap();
        assert_eq!(data["available"],false);assert_eq!(data["cached"],false);assert_eq!(data["can_open_project"],true);assert_eq!(data["settings"],json!([]));
    }
    #[test]
    fn lazy_mounting_preserves_only_existing_project_snapshots_until_a_definite_result() {
        let mut cache=DetailsCache::default();
        let other="cace260d-d95d-4859-b45b-f56f185f15da";
        let fresh="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
        cache.remember(ID,&settings("Original rules"));cache.remember(other,&settings("Other rules"));
        let pending=json!({"available":false,"pending":true,"settings":[]});
        cache.remember(ID,&pending);cache.remember(fresh,&pending);
        assert_eq!(cache.for_chat(ID).unwrap()["instructions"],"Original rules");
        assert!(cache.for_chat(fresh).is_none());
        assert_eq!(cache.for_chat(other).unwrap()["instructions"],"Other rules");
        cache.remember(ID,&settings("Refreshed rules"));
        assert_eq!(cache.for_chat(ID).unwrap()["instructions"],"Refreshed rules");
        cache.remember(ID,&unavailable(true));assert!(cache.for_chat(ID).is_none());
        assert!(cache.for_chat(other).is_some());
    }
    #[test]
    fn session_cache_is_bounded_and_invalid_or_code_project_ids_are_never_cached() {
        let mut cache=DetailsCache::default();
        cache.remember("../../project",&settings("Invalid"));cache.remember(&format!("code-{ID}"),&settings("Code"));assert!(cache.verified.is_empty());
        for number in 0..MAX_CACHED_PROJECTS+1 {cache.remember(&format!("{number:08x}-0000-0000-0000-000000000000"),&settings("Rules"));}
        assert_eq!(cache.verified.len(),MAX_CACHED_PROJECTS);assert_eq!(cache.order.len(),MAX_CACHED_PROJECTS);
        assert!(!cache.verified.contains_key("00000000-0000-0000-0000-000000000000"));
    }
    #[test]
    fn opening_project_only_navigates_to_its_matching_canonical_overview() {
        let overview=format!("https://chat.mistral.ai/work/projects/{ID}").parse().unwrap();
        let chat="https://chat.mistral.ai/work/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa".parse().unwrap();
        assert!(can_open_project(&chat,&overview,ID,true));assert!(can_open_project(&overview,&overview,ID,true));
        assert!(!can_open_project(&chat,&overview,ID,false));
        assert!(!can_open_project(&chat,&"https://example.org/".parse().unwrap(),ID,true));
        assert!(!can_open_project(&chat,&overview,"cace260d-d95d-4859-b45b-f56f185f15da",true));
        assert!(!can_open_project(&"https://chat.mistral.ai/work/new".parse().unwrap(),&overview,ID,true));
    }
    #[test]
    fn rules_drafts_are_scoped_to_exact_project_url_nonce_and_expire() {
        let url:url::Url=format!("https://chat.mistral.ai/work/projects/{ID}").parse().unwrap();
        let mut draft=RulesDraft{project:ID.into(),url:url.as_str().into(),nonce:"a".repeat(32),value:"original".into(),opened:std::time::Instant::now()};
        assert!(matching_rules_draft(&draft,ID,&url,&"a".repeat(32)));
        assert!(!matching_rules_draft(&draft,ID,&url,&"b".repeat(32)));
        assert!(!matching_rules_draft(&draft,"cace260d-d95d-4859-b45b-f56f185f15da",&url,&"a".repeat(32)));
        assert!(!matching_rules_draft(&draft,ID,&format!("https://chat.mistral.ai/work/projects/{ID}?changed=1").parse().unwrap(),&"a".repeat(32)));
        draft.opened=std::time::Instant::now()-std::time::Duration::from_secs(1801);
        assert!(!matching_rules_draft(&draft,ID,&url,&"a".repeat(32)));
    }
    #[test]
    fn rules_text_is_bounded_in_browser_units_and_user_markers_stay_literal() {
        assert!(valid_rules_text(&"x".repeat(8000)));assert!(!valid_rules_text(&"x".repeat(8001)));
        assert!(valid_rules_text(&"😀".repeat(4000)));assert!(!valid_rules_text(&"😀".repeat(4001)));assert!(!valid_rules_text("unsafe\0text"));
        let value="quote\"\n__VIBEZ_RULES_VALUE__";
        let source=rules_script(ID,"fill",&"a".repeat(32),Some(value),Some(value));
        assert!(source.ends_with(&format!(", {}, {})\n",json!(value),json!(value))));
    }
}

// Project rules from any page of the open project (a conversation included),
// through Mistral's own project request in the signed-in page. Only the rules
// text of the project shown in the panel is read or written.
async fn rules_api(app:&tauri::AppHandle,view:&Webview,url:&url::Url,project:&str,action:&str,value:Option<String>)->Result<Value,String> {
    let current=||view.url().is_ok_and(|now|now==*url)&&official_web::confirmed_project(app,url,project);
    if !current() {return Err("Open a conversation or the overview of this Mistral project first".into());}
    let value=if action=="api-save" {Some(value.filter(|value|valid_rules_text(value)).ok_or("Use at most 8000 characters for the project rules")?)} else {None};
    let input=json!({"id":project,"save":value.is_some(),"instructions":value});
    let start=format!("({})({})",include_str!("project_rules_api.js"),input);
    let started=official_web::eval(view,&start).await?;
    if started!="started" {return Err("The project rules could not be retrieved".into());}
    for _ in 0..60 {
        tokio::time::sleep(std::time::Duration::from_millis(150)).await;
        if !current() {return Err("The project has switched; try again".into());}
        let raw=official_web::eval(view,"(()=>{const r=window.__vibezRulesApi;if(!r||r.state==='pending')return JSON.stringify({state:'pending'});delete window.__vibezRulesApi;return JSON.stringify(r);})()").await?;
        if raw.len()>65536 {return Err("The project rules are too large".into());}
        let result:Value=serde_json::from_str(&raw).map_err(err)?;
        match result["state"].as_str() {
            Some("pending")=>continue,
            Some("done") if result["id"]==project=>{
                let text=result["instructions"].as_str().unwrap_or("");
                if !valid_rules_text(text) {return Err("The project rules could not be read safely".into());}
                if let Some(expected)=input["instructions"].as_str() {
                    if text!=expected {return Err("Mistral did not confirm the project rules".into());}
                    return Ok(json!({"project_id":project,"saved":true,"value":text}));
                }
                return Ok(json!({"project_id":project,"value":text}));
            }
            _=>return Err(if input["save"]==true {"Mistral could not save the project rules".into()} else {"The project rules could not be retrieved".into()}),
        }
    }
    Err("Mistral is not responding; try again".into())
}
