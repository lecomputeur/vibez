//! User-authorized live verification. Compiled only by the native-smoke feature.
//! No alternate backend, credential export, chat messages, or file changes.
use super::*;
use std::{path::{Path,PathBuf},sync::OnceLock};
const PROJECT:&str="229ee257-4177-4f98-969c-3055311c7cae";
const PROJECT_URL:&str="https://chat.mistral.ai/work/projects/229ee257-4177-4f98-969c-3055311c7cae";
static REPORT:OnceLock<Mutex<Value>>=OnceLock::new();
fn report()->&'static Mutex<Value>{REPORT.get_or_init(||Mutex::new(json!({"live_mistral":true,"offline_engine":false,"app_left_running":true,"version":env!("CARGO_PKG_VERSION"),"phase":"starting","done":false,"passed":false})))}
pub fn requested()->bool {std::env::args().any(|a|a=="--live-connector-self-test")}
fn checked_output(raw:&Path,root:&Path)->Option<PathBuf>{
    if !raw.is_absolute() || raw.extension()?.to_str()? != "json" {return None;}
    let parent=raw.parent()?.canonicalize().ok()?;let root=root.canonicalize().ok()?;
    if !parent.starts_with(root) {return None;}
    let file=raw.file_name()?;
    Some(parent.join(file))
}
fn output()->Option<PathBuf>{
    if !requested() || std::env::args().any(|a|a=="--standalone-smoke-test"){return None;}
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).parent()?.parent()?.join("artifacts");
    checked_output(&PathBuf::from(std::env::var_os("VIBEZ4_LIVE_TEST_OUTPUT")?),&root)
}
pub fn enabled()->bool {output().is_some()}
fn save()->Result<(),String>{
    let path=output().ok_or("Live diagnostic output is not permitted")?;
    let data=serde_json::to_vec_pretty(&*report().lock().map_err(err)?).map_err(err)?;
    if data.len()>16384{return Err("Live diagnostic report is too large".into());}
    let temporary=path.with_extension(format!("{}-{}.tmp",std::process::id(),std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(err)?.as_nanos()));
    let mut options=std::fs::OpenOptions::new();options.write(true).create_new(true);
    #[cfg(unix)] {use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
    let mut file=options.open(&temporary).map_err(err)?;file.write_all(&data).map_err(err)?;file.sync_all().map_err(err)?;
    std::fs::rename(&temporary,&path).map_err(err)
}
fn done()->bool {report().lock().map(|r|r["done"].as_bool()==Some(true)).unwrap_or(true)}
fn update(phase:&str,values:&[(&str,bool)],finished:bool)->Result<(),String>{
    {let mut r=report().lock().map_err(err)?;if r["done"].as_bool()==Some(true){return Ok(());}
     r["phase"]=json!(phase);for(key,value)in values{r[*key]=json!(value);}r["done"]=json!(finished);}
    save()
}
fn trusted_console(url:&url::Url)->bool {url.scheme()=="https"&&url.host_str()==Some("console.mistral.ai")&&url.port_or_known_default()==Some(443)&&url.username().is_empty()&&url.password().is_none()}
fn allowed_chat(url:&url::Url)->bool {
    if url.scheme()!="https"||!matches!(url.host_str(),Some("chat.mistral.ai"|"vibe.mistral.ai"))||url.port_or_known_default()!=Some(443)||!url.username().is_empty()||url.password().is_some(){return false;}
    let path=url.path().strip_suffix('/').unwrap_or(url.path());let parts=path.split('/').collect::<Vec<_>>();
    let id=match parts.as_slice(){["","work",id]=>*id,["","work","chat"|"chats"|"c",id]=>*id,_=>return false};
    id.len()==36&&id.chars().enumerate().all(|(i,c)|if[8,13,18,23].contains(&i){c=='-'}else{c.is_ascii_hexdigit()})
}
async fn follow_chat(app:&tauri::AppHandle)->bool {
    let Some(view)=app.get_webview("mistral-web") else{return false;};
    let Ok(url)=view.url() else{return false;};
    if url.scheme()!="https"||url.host_str()!=Some("chat.mistral.ai")||url.path().trim_end_matches('/')!=format!("/work/projects/{PROJECT}"){return false;}
    let source=format!("JSON.stringify(JSON.parse(({})).chats || [])",include_str!("workspace_project.js"));
    let Ok(raw)=official_web::eval(&view,&source).await else{return false;};
    if view.url().ok().as_ref()!=Some(&url){return false;}
    let Ok(links)=serde_json::from_str::<Vec<String>>(&raw) else{return false;};
    let target=links.iter().take(64).filter_map(|s|s.parse::<url::Url>().ok()).find(allowed_chat);
    target.is_some_and(|target|view.navigate(target).is_ok())
}
async fn inspect_web_auth(app:&tauri::AppHandle,expected_name:&str)->Value {
    let mut result=json!({"web_auth_tested":false,"web_auth_passed":false,"web_auth_header_present":false,"web_auth_header_required":false,"web_auth_error":false,"web_auth_submitted":false,"web_auth_modal_closed":false,"web_auth_reference_visible":false,"web_auth_same_connector":false});
    let Some(view)=app.get_webview("mistral-web")else{return result;};
    let mut opened=false;let mut submitted=false;let mut saw_dialog=false;
    for step in 0..40 {
        let known=app.state::<official_web::WebState>().project.lock().map(|p|p.as_ref().is_some_and(|p|p.id==PROJECT)).unwrap_or(false);
        let trusted=view.url().ok().is_some_and(|u|allowed_chat(&u));
        if !known||!trusted{return result;}
        let mode=if step==0{"open"}else if submitted{"observe"}else{"inspect"};
        // This code reads only visible labels/dialog text, never input values.
        let script=r#"(()=>{const visible=e=>e.getClientRects().length>0&&!e.disabled;const text=e=>(e.innerText||e.textContent||'').replace(/\s+/g,' ').trim();const owned=e=>{const t=text(e).toLowerCase();return t.length<5000&&t.includes('vibez')&&t.includes('citytripxl');};const exact=e=>['connect','verbinden'].includes(text(e).toLowerCase());const dialogs=[...document.querySelectorAll('[role=dialog],dialog')].filter(visible).filter(owned);if(dialogs.length>1)return JSON.stringify({ambiguous:true});if(dialogs.length===1){const dialog=dialogs[0];const reference=text(dialog).match(/\b(?:reference|referentie)\s*:?\s+([A-Za-z0-9_.-]{1,256})/i);const same=reference?reference[1]===EXPECTED_NAME:null;const identity={reference_visible:Boolean(reference),same_connector:same===true};if(same===false)return JSON.stringify({dialog:true,...identity,wrong_connector:true});const inputs=[...dialog.querySelectorAll('input')].filter(visible);const labels=e=>[...e.labels||[]].map(text).join(' ')+' '+(e.getAttribute('aria-label')||'')+' '+(e.getAttribute('placeholder')||'');const header=inputs.find(e=>/authorization/i.test(labels(e)));if(header)return JSON.stringify({dialog:true,...identity,header:true,required:header.required||header.getAttribute('aria-required')==='true'});if(inputs.some(e=>['password','email'].includes((e.getAttribute('type')||'').toLowerCase())))return JSON.stringify({dialog:true,...identity,other_auth_input:true});const t=text(dialog).toLowerCase();if(/authentication failed|authenticatie mislukt|aanmelding mislukt|verbinding mislukt|invalid credentials/.test(t))return JSON.stringify({dialog:true,...identity,error:true});const buttons=[...dialog.querySelectorAll('button,[role=button]')].filter(visible).filter(exact);if(MODE==='inspect'&&buttons.length===1){buttons[0].click();return JSON.stringify({dialog:true,...identity,submitted:true});}return JSON.stringify({dialog:true,...identity});}if(MODE!=='open')return JSON.stringify({no_dialog:true});const candidates=[...document.querySelectorAll('button,[role=button]')].filter(visible).filter(exact).filter(button=>{let node=button;for(let n=0;n<5&&node;n++,node=node.parentElement){if(['BODY','MAIN','HTML'].includes(node.tagName)||node.getAttribute?.('role')==='main')break;if(owned(node))return true;}return false;});if(candidates.length!==1)return JSON.stringify({card_found:false,ambiguous:candidates.length>1});candidates[0].click();return JSON.stringify({card_found:true,opened:true});})()"#.replace("MODE",&serde_json::to_string(mode).unwrap()).replace("EXPECTED_NAME",&serde_json::to_string(expected_name).unwrap());
        let Some(data)=official_web::eval(&view,&script).await.ok().and_then(|v|serde_json::from_str::<Value>(&v).ok())else{return result;};
        if data["ambiguous"]==true{return result;}
        if data["opened"]==true{opened=true;result["web_auth_tested"]=json!(true);}
        if data["dialog"]==true{saw_dialog=true;result["web_auth_tested"]=json!(true);result["web_auth_reference_visible"]=json!(data["reference_visible"]==true);result["web_auth_same_connector"]=json!(data["same_connector"]==true);}
        if data["wrong_connector"]==true{return result;}
        if data["header"]==true{result["web_auth_header_present"]=json!(true);result["web_auth_header_required"]=json!(data["required"]==true);return result;}
        if data["other_auth_input"]==true{return result;}
        if data["error"]==true{result["web_auth_error"]=json!(true);return result;}
        if data["submitted"]==true{submitted=true;result["web_auth_submitted"]=json!(true);}
        if data["no_dialog"]==true&&saw_dialog&&submitted{result["web_auth_modal_closed"]=json!(true);result["web_auth_passed"]=json!(true);return result;}
        if step==0&&!opened&&!saw_dialog{return result;}
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }
    result
}
pub fn observed(app:&tauri::AppHandle,payload:&Value)->Result<bool,String>{
    if !enabled(){return Ok(false);}
    match payload["action"].as_str(){
        Some("live_connector_observation")=>{
            if done(){return Ok(true);}
            let phase=payload["phase"].as_str().filter(|s|matches!(*s,"initial_project"|"connect_requested"|"connected"|"chat_checked"|"missing_folder"|"project_unconfirmed"|"connection_failed"|"timeout"|"command_failed"|"complete")).ok_or("Unknown live diagnostic phase")?;
            let mut values=Vec::new();
            for key in ["initial_project_confirmed","remembered_folder","connect_requested","api_probe_connected","connector_enabled","chat_navigation_attempted","chat_navigated","chat_project_confirmed","chat_connector_enabled","web_auth_tested","web_auth_passed","web_auth_header_present","web_auth_header_required","web_auth_error","web_auth_submitted","web_auth_modal_closed","web_auth_reference_visible","web_auth_same_connector","passed"] {
                if let Some(value)=payload[key].as_bool(){values.push((key,value));}
            }
            let finished=payload["done"].as_bool()==Some(true);
            update(phase,&values,finished)?;Ok(true)
        },
        Some("live_connector_web_auth")=>{
            if done(){return Ok(true);}let handle=app.clone();
            let expected_name=payload["expected_name"].as_str().filter(|s|!s.is_empty()&&s.len()<=256&&!s.chars().any(char::is_control)).ok_or("No verified connector name")?.to_owned();
            tauri::async_runtime::spawn(async move{
                let result=inspect_web_auth(&handle,&expected_name).await;
                let values=["web_auth_tested","web_auth_passed","web_auth_header_present","web_auth_header_required","web_auth_error","web_auth_submitted","web_auth_modal_closed","web_auth_reference_visible","web_auth_same_connector"].iter().map(|key|(*key,result[*key].as_bool().unwrap_or(false))).collect::<Vec<_>>();
                let _=update("web_auth_checked",&values,false);
                let _=handle.emit_to(EventTarget::Webview{label:"main".into()},"live-connector-web-auth",result);
            });Ok(true)
        },
        Some("live_connector_follow_chat")=>{
            if done(){return Ok(true);}let handle=app.clone();
            tauri::async_runtime::spawn(async move{
                let navigated=follow_chat(&handle).await;
                let _=update("connected",&[("chat_navigation_attempted",true),("chat_navigated",navigated)],false);
                let _=handle.emit_to(EventTarget::Webview{label:"main".into()},"live-connector-chat-navigation",json!({"navigated":navigated}));
            });Ok(true)
        },_=>Ok(false)
    }
}
pub fn start(app:&tauri::AppHandle){
    if !enabled(){return;}
    let handle=app.clone();
    tauri::async_runtime::spawn(async move{
        let safe=screen(&handle).ok();let window=handle.get_window("main");
        let on_safe=match(safe,window){(Some(s),Some(w))=>match(w.outer_position(),w.outer_size()){(Ok(p),Ok(size))=>p.x>=s.x&&p.y>=s.y&&p.x as i64+size.width as i64<=s.x as i64+s.width as i64&&p.y as i64+size.height as i64<=s.y as i64+s.height as i64,_=>false},_=>false};
        let _=update("starting",&[("on_screen_1",on_safe)],!on_safe);if !on_safe{return;}
        tokio::time::sleep(std::time::Duration::from_millis(1500)).await;
        let follow=std::env::var("VIBEZ4_LIVE_FOLLOW_CHAT").ok().as_deref()==Some("1");
        let preferred=std::env::var("VIBEZ4_LIVE_CONNECTOR_REFERENCE").ok().filter(|v|!v.is_empty()&&v.len()<=64&&v.chars().all(|c|c.is_ascii_alphanumeric()||c=='_'||c=='-'));
        let script=r#"(async()=>{
const native=(name,args)=>window.__TAURI__.core.invoke(name,args),host=payload=>native('app_command',{payload});
const PROJECT=PROJECT_ID;let current={},automatic={},chatNavigation=null,webAuth=null;
window.__vibezLiveStopped=false;
await window.__TAURI__.event.listen('app-engine',e=>{const d=e.payload;if(d.type==='web_connector')current=d;if(d.type==='web_auto'&&d.project_id===PROJECT)automatic=d;});
await window.__TAURI__.event.listen('live-connector-chat-navigation',e=>chatNavigation=Boolean(e.payload.navigated));
await window.__TAURI__.event.listen('live-connector-web-auth',e=>webAuth=e.payload);
const wait=async(f,seconds)=>{for(let n=0;n<seconds*4;n++){if(window.__vibezLiveStopped)return false;if(f())return true;await new Promise(r=>setTimeout(r,250));}return false;};
const mark=async(phase,done=false,extra={})=>host({action:'live_connector_observation',phase,done,...extra});
await native('web_surface',{show:true,route:PROJECT_URL});await native('chrome_panel',{mode:'files'});
await native('web_command',{payload:{action:'web_hello'}});
if(!await wait(()=>current.project?.id===PROJECT,35))return mark('project_unconfirmed',true);
await mark('initial_project',false,{initial_project_confirmed:true,remembered_folder:Boolean(current.folder)});
if(!current.folder)return mark('missing_folder',true,{passed:false});
await mark('connect_requested',false,{connect_requested:true});
await native('web_command',{payload:{action:'web_connect',project_id:PROJECT,connector_reference:CONNECTOR_REFERENCE}});
if(!await wait(()=>automatic.status==='error'||(automatic.status==='connected'&&current.enabled),180))return mark('timeout',true,{passed:false});
if(automatic.status!=='connected')return mark('connection_failed',true,{api_probe_connected:false,connector_enabled:Boolean(current.enabled),passed:false});
await mark('connected',false,{api_probe_connected:true,connector_enabled:Boolean(current.enabled)});
if(FOLLOW_CHAT){
 await host({action:'live_connector_follow_chat'});
 if(await wait(()=>chatNavigation!==null,12)&&chatNavigation){
  await new Promise(r=>setTimeout(r,2200));await native('web_command',{payload:{action:'web_hello'}});await new Promise(r=>setTimeout(r,700));
  const matched=current.project?.id===PROJECT,enabled=Boolean(current.enabled);
  await mark('chat_checked',false,{chat_navigation_attempted:true,chat_navigated:true,chat_project_confirmed:matched,chat_connector_enabled:enabled});
  if(matched&&enabled){await host({action:'live_connector_web_auth',expected_name:automatic.connector_name});await wait(()=>webAuth!==null,25);}
  return mark('complete',true,{...(webAuth||{}),passed:matched&&enabled&&webAuth?.web_auth_passed===true});
 }
 return mark('complete',true,{chat_navigation_attempted:true,chat_navigated:false,passed:false});
}
await mark('complete',true,{passed:true});
})().catch(()=>{window.__TAURI__.core.invoke('app_command',{payload:{action:'live_connector_observation',phase:'command_failed',done:true,passed:false}})});"#
            .replace("PROJECT_ID",&serde_json::to_string(PROJECT).unwrap())
            .replace("PROJECT_URL",&serde_json::to_string(PROJECT_URL).unwrap())
            .replace("CONNECTOR_REFERENCE",&serde_json::to_string(&preferred).unwrap())
            .replace("FOLLOW_CHAT",if follow{"true"}else{"false"});
        if let Some(view)=handle.get_webview("main"){if view.eval(script).is_err(){let _=update("command_failed",&[],true);return;}}else{let _=update("command_failed",&[],true);return;}
        // Only exact consent buttons on the app's own trusted console popup may
        // be clicked. Sign-in forms, passwords, external identity providers and
        // arbitrary buttons are never completed by this diagnostic.
        let mut clicked=std::collections::BTreeSet::new();
        for _ in 0..480{
            if done(){return;}
            let labels=handle.state::<Bridge>().login_labels.lock().map(|v|v.clone()).unwrap_or_default();
            for label in labels{
                let Some(view)=handle.get_webview(&label)else{continue;};
                let Ok(url)=view.url()else{continue;};if url.as_str()=="about:blank"{continue;}
                // An existing identity-provider session may redirect naturally.
                // Never inspect or click external pages; wait for the console.
                if !trusted_console(&url){continue;}
                if clicked.contains(&label){continue;}
                let action=r#"(()=>{const visible=e=>e.getClientRects().length>0&&!e.disabled;if([...document.querySelectorAll('input[type=password],input[type=email],input[autocomplete=username],input[autocomplete=current-password]')].some(visible))return 'needs_sign_in';const button=[...document.querySelectorAll('button,[role=button]')].find(e=>visible(e)&&['authorize','autoriseren','toestaan','allow'].includes((e.innerText||e.textContent||'').replace(/\s+/g,' ').trim().toLowerCase()));if(!button)return 'waiting';button.click();return 'clicked';})()"#;
                match official_web::eval(&view,action).await.unwrap_or_default().as_str(){
                    "clicked"=>{clicked.insert(label);let _=update("authorizing",&[("authorization_clicked",true)],false);},
                    "needs_sign_in"=>{let _=update("needs_user_sign_in",&[("needs_user_sign_in",true)],true);if let Some(main)=handle.get_webview("main"){let _=main.eval("window.__vibezLiveStopped=true");}return;},_=>{}
                }
            }
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        }
        let _=update("timeout",&[],true);if let Some(main)=handle.get_webview("main"){let _=main.eval("window.__vibezLiveStopped=true");}
    });
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test]fn live_chat_navigation_accepts_only_exact_trusted_chat_routes(){
        for value in ["https://chat.mistral.ai/work/11111111-2222-4333-8444-555555555555","https://vibe.mistral.ai/work/chats/11111111-2222-4333-8444-555555555555"]{assert!(allowed_chat(&value.parse().unwrap()));}
        for value in [PROJECT_URL,"https://evil.test/work/11111111-2222-4333-8444-555555555555","https://user:secret@chat.mistral.ai/work/11111111-2222-4333-8444-555555555555","https://chat.mistral.ai/work/settings"]{assert!(!allowed_chat(&value.parse().unwrap()));}
    }
    #[test]fn output_requires_existing_artifact_parent_and_json_filename(){
        let root=std::env::temp_dir().join(format!("vibez-live-output-{}",std::process::id()));std::fs::create_dir_all(&root).unwrap();
        assert!(checked_output(&root.join("result.json"),&root).is_some());assert!(checked_output(&root.join("result.txt"),&root).is_none());assert!(checked_output(Path::new("result.json"),&root).is_none());assert!(checked_output(&root.join("missing/result.json"),&root).is_none());assert!(checked_output(&root.join("../outside.json"),&root).is_none());std::fs::remove_dir(&root).unwrap();
    }
}
