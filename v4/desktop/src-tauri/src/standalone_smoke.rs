//! Offline native layout and connector test; excluded from production DEB.
use super::*;
#[path="alpha7_live_fixture.rs"]
mod alpha7;
#[path="live_connector_smoke.rs"]
mod live;
#[path="live_code_probe.rs"]
mod code_probe;
#[path="live_work_self_test.rs"]
mod work;
pub fn enabled()->bool {
    !live::requested() && !code_probe::requested() && !work::requested() && std::env::args().any(|a|a=="--standalone-smoke-test") && std::env::var("XDG_DATA_HOME").unwrap_or_default().contains("vibez4-standalone-") && std::env::var_os("VIBEZ4_STANDALONE_TEST_OUTPUT").is_some()
}
pub fn engine_script(original:&std::path::Path)->Result<std::path::PathBuf,String> {
    if alpha7::requested(){return alpha7::engine_script(original);}
    if work::requested(){return work::engine_script(original);}
    if enabled(){Ok(std::env::var("VIBEZ4_STANDALONE_DRIVER").map_err(err)?.into())}else{Ok(original.into())}
}
pub fn engine_data(original:&std::path::Path)->Result<std::path::PathBuf,String> {if alpha7::requested(){alpha7::engine_data(original)}else{code_probe::engine_data(original)}}
pub fn legacy_path(original:&std::path::Path)->Result<std::path::PathBuf,String> {if alpha7::requested(){alpha7::legacy_path(original)}else{code_probe::legacy_path(original)}}
pub fn configure_engine(command:&mut Command,original:&std::path::Path) {if alpha7::requested(){alpha7::configure_engine(command,original);return;}if work::requested(){work::configure_engine(command,original);return;}if enabled(){command.arg("--engine-source").arg(original);}}
pub fn observe_dialog(dialog: &gtk::FileChooserDialog,safe:Screen,kind:&str) {code_probe::observe_dialog(dialog,safe,kind);}
async fn geometry(app:&tauri::AppHandle,label:&str)->Result<Value,String> {
    let view=app.get_webview(label).ok_or("Missing native view")?;
    let(tx,rx)=tokio::sync::oneshot::channel();
    view.with_webview(move |p| {
        let widget=p.inner();let a=widget.allocation();
        let root=widget.toplevel().unwrap();let(x,y)=widget.translate_coordinates(&root,0,0).unwrap_or((-1,-1));
        let _=tx.send(json!({"x":x,"y":y,"width":a.width(),"height":a.height(),"mapped":widget.is_mapped()}));
    }).map_err(err)?;
    rx.await.map_err(err)
}
async fn capture(app:&tauri::AppHandle,name:&str)->Result<(),String> {
    let window=app.get_window("main").ok_or("No window")?;let handle=app.clone();let name=name.to_owned();let(tx,rx)=tokio::sync::oneshot::channel();
    window.run_on_main_thread(move || {
        let result=(||{
            let window=handle.get_window("main").ok_or("No window")?.gtk_window().map_err(err)?;
            let safe=screen(&handle)?;let(x,y)=window.position();let(w,h)=window.size();
            if x<safe.x || y<safe.y || x+w>safe.x+safe.width as i32 || y+h>safe.y+safe.height as i32 {return Err("Wrong screen".into());}
            let g=window.window().ok_or("No GDK window")?;
            let image=g.pixbuf(0,0,g.width(),g.height()).ok_or("Could not capture own window")?;
            let output=std::path::PathBuf::from(std::env::var("VIBEZ4_STANDALONE_TEST_OUTPUT").unwrap()).with_file_name(name);
            image.savev(output,"png",&[]).map_err(err)?;Ok(())
        })();let _=tx.send(result);
    }).map_err(err)?;rx.await.map_err(err)?
}
pub fn observed(app:&tauri::AppHandle,payload:&Value)->Result<bool,String> {
    if alpha7::observed(app,payload)?{return Ok(true);}
    if live::observed(app,payload)?{return Ok(true);}
    if !enabled(){return Ok(false);}
    let root=std::env::var("VIBEZ4_STANDALONE_ROOT").map_err(err)?;
    match payload["action"].as_str() {
        Some("fixture_language")=>{let lang=payload["language"].as_str().ok_or("No language")?;let script=format!("document.getElementById('quick-language').value={};document.getElementById('quick-language').dispatchEvent(new Event('change',{{bubbles:true}}))",serde_json::to_string(lang).unwrap());app.get_webview("main").ok_or("No toolbar")?.eval(script).map_err(err)?;Ok(true)},
        Some("fixture_language_probe")=>{
            let label=payload["label"].as_str().ok_or("No label")?.to_owned();let handle=app.clone();
            tauri::async_runtime::spawn(async move {
                let view=handle.get_webview("mistral-web").unwrap();
                let cookies=view.cookies_for_url("https://chat.mistral.ai/".parse().unwrap()).unwrap_or_default();
                let locales:Vec<_>=cookies.iter().filter(|c|c.name()=="NEXT_LOCALE").map(|c|c.value().to_owned()).collect();
                let auth=cookies.iter().any(|c|c.name()=="vibez_fixture_auth"&&c.value()=="preserve-me");
                let doc=official_web::eval(&view,"document.documentElement.lang").await.unwrap_or_default();
                let data=json!({"label":label,"state":classic_language::info(&handle),"locale_cookies":locales,"auth_preserved":auth,"document_language":doc,"url":view.url().ok().map(|u|u.to_string())});
                let _=handle.emit_to(EventTarget::Webview{label:"main".into()},"language-probe",data);
            });Ok(true)
        },
        Some("fixture_language_seed")=>{let view=app.get_webview("mistral-web").ok_or("No web")?;view.set_cookie(tauri::webview::Cookie::build(("vibez_fixture_auth","preserve-me")).domain("chat.mistral.ai").path("/").secure(true).build()).map_err(err)?;Ok(true)},
        Some("fixture_auth_page")|Some("fixture_content_page")=>{
            let auth=payload["action"]=="fixture_auth_page";
            app.get_webview("mistral-web").ok_or("No web")?.with_webview(move |p|{
                use webkit2gtk::WebViewExt;
                p.inner().load_html("<!doctype html><main><h1>CityTripXL</h1></main>",Some(if auth{"https://accounts.google.com/auth/probe"}else{"https://chat.mistral.ai/work/projects/cace260d-d95d-4859-b45b-f56f185f15da"}));
            }).map_err(err)?;Ok(true)
        },
        Some("fixture_alpha9_ready")=>{
            let handle=app.clone();tauri::async_runtime::spawn(async move{
                let outcome=async{
                    let panel=handle.get_webview("connector-panel").ok_or("No panel")?;
                    let raw=official_web::eval(&panel,"(()=>{const e=document.getElementById('project-drop-zone');e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()").await?;
                    let point:Value=serde_json::from_str(&raw).map_err(err)?;let offset=geometry(&handle,"connector-panel").await?;
                    let position=handle.get_window("main").unwrap().outer_position().map_err(err)?;
                    Ok::<Value,String>(json!({"x":position.x as f64+offset["x"].as_f64().unwrap()+point["x"].as_f64().unwrap(),"y":position.y as f64+offset["y"].as_f64().unwrap()+point["y"].as_f64().unwrap()}))
                }.await;
                let path=std::path::PathBuf::from(std::env::var("VIBEZ4_STANDALONE_TEST_OUTPUT").unwrap()).with_file_name("drop-ready.json");
                let value=match outcome{Ok(v)=>v,Err(e)=>json!({"error":e})};let _=std::fs::write(path,serde_json::to_vec(&value).unwrap());
            });Ok(true)
        },
        Some("fixture_alpha9_finish")=>{
            let output=std::env::var("VIBEZ4_STANDALONE_TEST_OUTPUT").unwrap();std::fs::write(output,serde_json::to_vec_pretty(&payload["report"]).unwrap()).map_err(err)?;app.exit(0);Ok(true)
        },
        Some("fixture_web_choose")=>{
            let state=app.state::<official_web::WebState>();let id=state.project.lock().map_err(err)?.as_ref().map(|p|p.id.clone()).ok_or("No web project")?;
            *state.choice.lock().map_err(err)?=Some((id,root));Ok(true)
        },
        Some("fixture_web_make")=>{write_engine(app,&json!({"action":"fixture_web_make"}))?;Ok(true)},
        Some("fixture_click_connect")=>{app.get_webview("connector-panel").ok_or("No panel")?.eval("if(document.getElementById('advanced-setup').open)throw Error('Advanced setup should be closed');document.getElementById('auto-connect').click()").map_err(err)?;Ok(true)},
        Some("fixture_click_approval")=>{app.get_webview("connector-panel").ok_or("No panel")?.eval("document.querySelector('.approval-actions .primary').click()").map_err(err)?;Ok(true)},
        Some("fixture_before")=>{if std::fs::read_to_string(std::path::Path::new(&root).join("tekst.txt")).map_err(err)?!="Originele tekst.\n" {return Err("Write before approval".into());}Ok(true)},
        Some("fixture_probe")=>{
            let phase=payload["phase"].as_str().ok_or("Missing phase")?.to_owned();let handle=app.clone();
            tauri::async_runtime::spawn(async move {
                let report=async {
                    let toolbar=geometry(&handle,"main").await?;let web=geometry(&handle,"mistral-web").await?;let panel=geometry(&handle,"connector-panel").await?;
                    capture(&handle,&format!("{phase}.png")).await?;
                    Ok::<Value,String>(json!({"phase":phase,"toolbar":toolbar,"web":web,"panel":panel}))
                }.await;
                let _=handle.emit_to(EventTarget::Webview{label:"main".into()},"layout-probe",match report{Ok(v)=>v,Err(e)=>json!({"phase":phase,"error":e})});
            });Ok(true)
        },
        Some("fixture_finish")=>{
            let mut report=payload["report"].clone();report["written"]=json!(std::fs::read_to_string(std::path::Path::new(&root).join("tekst.txt")).map_err(err)?=="Verbeterde tekst van VibeZ.\n");
            let w=app.get_window("main").ok_or("No window")?;let p=w.outer_position().map_err(err)?;let s=w.outer_size().map_err(err)?;let safe=screen(app)?;
            report["on_safe_screen"]=json!(p.x>=safe.x&&p.y>=safe.y&&p.x as i64+s.width as i64<=safe.x as i64+safe.width as i64);
            let output=std::env::var("VIBEZ4_STANDALONE_TEST_OUTPUT").unwrap();std::fs::write(output,serde_json::to_vec_pretty(&report).unwrap()).map_err(err)?;app.exit(0);Ok(true)
        },_=>Ok(false)
    }
}
pub fn start(app:&tauri::AppHandle) {
    if alpha7::enabled(){alpha7::start(app);return;}
    if code_probe::enabled(){code_probe::start(app);return;}
    if live::enabled(){live::start(app);return;}
    if work::enabled(){work::start(app);return;}
    if !enabled(){return;}
    let handle=app.clone();let root=std::env::var("VIBEZ4_STANDALONE_ROOT").unwrap();
    if std::env::args().any(|a|a=="--alpha9-files-fixture"){
        tauri::async_runtime::spawn(async move{
            tokio::time::sleep(std::time::Duration::from_millis(1200)).await;
            let script=r#"(async()=>{
const invoke=(name,args)=>window.__TAURI__.core.invoke(name,args),host=payload=>invoke('app_command',{payload});let state={},copies=0,errors=[];
await window.__TAURI__.event.listen('app-engine',event=>{const d=event.payload;if(d.type==='web_connector')state=d;if(d.type==='web_import_result'){if(d.error)errors.push(d.error);else copies=Math.max(copies,d.count||0);}});
const wait=async(f,n=300)=>{for(let i=0;i<n;i++){if(f())return;await new Promise(r=>setTimeout(r,100));}throw Error('Fixture timeout '+JSON.stringify({project:state.project?.id,linked:Boolean(state.folder),copies,errors}));};
await invoke('web_surface',{show:true});await wait(()=>state.project?.id);
await invoke('chrome_panel',{mode:'files'});await host({action:'fixture_web_choose'});
await invoke('web_command',{payload:{action:'web_link',project_id:state.project.id,path:ROOT}});await wait(()=>state.folder===ROOT);
await host({action:'fixture_alpha9_ready'});await wait(()=>copies>=1||errors.length,150);
await host({action:'fixture_alpha9_finish',report:{passed:copies===1&&!errors.length,copied:copies,errors,native_OS_drop_pipeline:true,remote_mistral:false}});
})().catch(error=>window.__TAURI__.core.invoke('app_command',{payload:{action:'fixture_alpha9_finish',report:{passed:false,error:String(error)}}}));"#.replace("ROOT",&serde_json::to_string(&root).unwrap());
            if let Some(view)=handle.get_webview("main"){let _=view.eval(script);}
        });return;
    }

    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_millis(1400)).await;
        let script=r#"(async()=>{
const native=(name,args)=>window.__TAURI__.core.invoke(name,args),host=payload=>native('app_command',{payload});
let current={},automatic={},saved=false;const probes={};const languages={};
await window.__TAURI__.event.listen('language-probe',e=>languages[e.payload.label]=e.payload);
await window.__TAURI__.event.listen('app-engine',e=>{if(e.payload.type==='web_auto')automatic=e.payload;if(e.payload.type==='web_connector')current=e.payload;if(e.payload.type==='fixture_saved')saved=e.payload.written;});
await window.__TAURI__.event.listen('layout-probe',e=>probes[e.payload.phase]=e.payload);
const wait=async f=>{for(let i=0;i<160;i++){if(f())return;await new Promise(r=>setTimeout(r,60));}throw Error('Timeout: '+JSON.stringify({current,automatic})+' '+document.body.innerText);};
await native('web_command',{payload:{action:'web_hello'}});await wait(()=>current.project?.name==='CityTripXL');
await new Promise(r=>setTimeout(r,400));await host({action:'fixture_probe',phase:'closed'});await wait(()=>probes.closed);
await native('chrome_panel',{mode:'files'});await new Promise(r=>setTimeout(r,400));await host({action:'fixture_probe',phase:'files'});await wait(()=>probes.files);
await host({action:'fixture_web_choose'});await native('web_command',{payload:{action:'web_link',project_id:current.project.id,path:ROOT}});await wait(()=>current.folder===ROOT);
await host({action:'fixture_click_connect'});await wait(()=>automatic.status==='connected'&&current.enabled);const automaticallyConnected=true;await host({action:'fixture_probe',phase:'automatic'});await wait(()=>probes.automatic);
await host({action:'fixture_web_make'});await wait(()=>current.pending.length===1);await host({action:'fixture_before'});
await host({action:'fixture_probe',phase:'proposal'});await wait(()=>probes.proposal);
await host({action:'fixture_click_approval'});await wait(()=>saved);
await native('chrome_panel',{mode:'settings'});await new Promise(r=>setTimeout(r,300));await host({action:'fixture_probe',phase:'settings'});await wait(()=>probes.settings);
await native('chrome_panel',{mode:'closed'});await new Promise(r=>setTimeout(r,400));await host({action:'fixture_probe',phase:'restored'});await wait(()=>probes.restored);
await host({action:'fixture_language_seed'});

for(const language of ['nl','en','ar','nl']){
 await host({action:'fixture_language',language});await wait(()=>window.vibezLanguage.state().language===language&&!window.vibezLanguage.state().pending);
 await host({action:'fixture_language_probe',label:language});await wait(()=>languages[language]);
 if(document.documentElement.dir!==(language==='ar'?'rtl':'ltr'))throw Error('Wrong text direction');
 if($('language-code').textContent!==language.toUpperCase())throw Error('Wrong language badge');
}
await host({action:'fixture_auth_page'});await new Promise(r=>setTimeout(r,500));
await host({action:'fixture_language',language:'fr'});await wait(()=>window.vibezLanguage.state().language==='fr');await new Promise(r=>setTimeout(r,400));
await host({action:'fixture_language_probe',label:'auth'});await wait(()=>languages.auth);
if(!languages.auth.state.pending||!languages.auth.url.startsWith('https://accounts.google.com/'))throw Error('Authentication was interrupted');
await host({action:'fixture_content_page'});await wait(()=>!window.vibezLanguage.state().pending&&current.project?.name==='CityTripXL');
await host({action:'fixture_language',language:'nl'});await wait(()=>window.vibezLanguage.state().language==='nl'&&!window.vibezLanguage.state().pending);
await host({action:'fixture_probe',phase:'language'});await wait(()=>probes.language);
await native('chrome_panel',{mode:'closed'});
const clean=!document.body.innerText.includes('Lokale gesprekken')&&!document.body.innerText.includes('Webversie')&&!document.querySelector('input');
await host({action:'fixture_finish',report:{automatic_connected:automaticallyConnected,clean_toolbar:clean,project_name:current.project?.name==='CityTripXL',probes,languages,language_restored:document.getElementById('language-button')!==null,live_mistral:false}});
})().catch(e=>{window.__TAURI__.core.invoke('app_command',{payload:{action:'fixture_finish',report:{error:String(e)}}})});"#.replace("ROOT",&serde_json::to_string(&root).unwrap());
        if let Some(v)=handle.get_webview("main"){let _=v.eval(script);}
    });
}
