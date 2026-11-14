//! Only compiled into a separate verification binary, never into the DEB.
use super::*;
static PROJECT: AtomicU64=AtomicU64::new(0);
fn fixture() -> bool {
    std::env::var_os("VIBEZ4_NATIVE_SMOKE_OUTPUT").is_some()
        && std::env::var("XDG_DATA_HOME").unwrap_or_default().contains("vibez4-native-")
}
pub fn detected() -> Option<Option<projects::Project>> {
    if !fixture() { return None; }
    let index=PROJECT.load(Ordering::SeqCst);
    if index==2 {return Some(None);}
    let id=if index==0 {"cace260d-d95d-4859-b45b-f56f185f15da"} else {"11111111-1111-4111-8111-111111111111"};
    let mut p=projects::parse(&format!("https://chat.mistral.ai/work/projects/{id}").parse().unwrap()).unwrap();
    p.name=if index==0 {"Project A"} else {"Project B"}.into();
    Some(Some(p))
}
pub fn observed(app: &tauri::AppHandle, payload: &Value) -> Result<bool, String> {
    if !fixture() {return Ok(false);}
    let output=std::env::var("VIBEZ4_NATIVE_SMOKE_OUTPUT").unwrap();
    if let Some(report)=payload.get("native_smoke_observed") {
        let state=app.state::<Bridge>();
        let mut report=report.clone();
        report["engine_pid"]=json!(state.process.lock().map_err(|_|"No engine")?.as_ref().map(|p|p.child.id()));
        report["same_window"]=json!(app.get_webview("workspace").map(|v|v.window().label()=="main").unwrap_or(false));
        report["no_extra_window"]=json!(app.get_window("workspace").is_none());
        report["saved_bindings"]=json!(projects::read(&bindings_path(app)?)?.folders.len());
        if let (Some(vibe),Some(local))=(app.get_webview("vibe"),app.get_webview("workspace")) {
            report["vibe_geometry"]=json!(crate::native_layout::geometry(&vibe)?);
            report["workspace_geometry"]=json!(crate::native_layout::geometry(&local)?);
        }
        std::fs::write(output,serde_json::to_vec_pretty(&report).unwrap()).map_err(crate::err)?;
        let handle=app.clone();
        std::thread::spawn(move||{std::thread::sleep(std::time::Duration::from_millis(300));handle.exit(0);});
        return Ok(true);
    }
    if payload["action"]=="fixture_project" {
        PROJECT.store(payload["index"].as_u64().unwrap(),Ordering::SeqCst);return Ok(true);
    }
    if payload["action"]=="fixture_choose" {
        let index=PROJECT.load(Ordering::SeqCst);
        let root=std::env::var(if index==0 {"VIBEZ4_NATIVE_SMOKE_ROOT"} else {"VIBEZ4_NATIVE_SMOKE_ROOT_B"}).map_err(crate::err)?;
        let state=app.state::<Bridge>();
        let mut c=state.context.lock().unwrap();
        c.chosen_project=c.project.as_ref().map(|p|p.id.clone());
        *state.chosen_folder.lock().unwrap()=Some(std::fs::canonicalize(root).unwrap().to_string_lossy().into_owned());
        return Ok(true);
    }
    if matches!(payload["action"].as_str(),Some("login"|"chat")) {return Err("The offline check does not use a Mistral account".into());}
    Ok(false)
}
pub fn start(app: &tauri::AppHandle) {
    if !fixture() {return;}
    login::verify_profile(app).unwrap();
    let root=std::env::var("VIBEZ4_NATIVE_SMOKE_ROOT").unwrap();
    let other=std::env::var("VIBEZ4_NATIVE_SMOKE_ROOT_B").unwrap();
    let handle=app.clone();
    std::thread::spawn(move||{
        std::thread::sleep(std::time::Duration::from_millis(700));
        let js=r#"(async()=>{
          const invoke=(payload)=>window.__TAURI__.core.invoke('workspace_command',{payload});
          let latest={};
          await window.__TAURI__.event.listen('workspace-engine',e=>{if(e.payload.type==='state')latest=e.payload;});
          const wait=async f=>{for(let i=0;i<120;i++){if(f())return;await new Promise(r=>setTimeout(r,50));}throw Error('Project UI timeout');};
          const change=async index=>{await invoke({action:'fixture_project',index});await invoke({action:'hello'});};
          await invoke({action:'hello'});
          await wait(()=>latest.project?.name==='Project A');
          await invoke({action:'fixture_choose'});
          await invoke({action:'workspace',path:ROOT,project_key:latest.project.id});
          await wait(()=>latest.workspace===ROOT&&document.querySelectorAll('#files button').length===2);
          await change(1);
          await wait(()=>latest.project?.name==='Project B'&&!latest.workspace&&document.querySelectorAll('#files button').length===0);
          const emptyB=true;
          await invoke({action:'fixture_choose'});
          await invoke({action:'workspace',path:OTHER,project_key:latest.project.id});
          await wait(()=>latest.workspace===OTHER);
          await change(0);
          await wait(()=>latest.project?.name==='Project A'&&latest.workspace===ROOT&&document.querySelectorAll('#files button').length===2);
          const restoredA=true;
          await change(1);
          await wait(()=>latest.project?.name==='Project B'&&latest.workspace===OTHER);
          const restoredB=true;
          await change(0);
          await wait(()=>latest.workspace===ROOT&&document.querySelectorAll('#files button').length===2);
          let staleRejected=false;
          try{await invoke({action:'approve',id:'old-token',allow:true,project_key:'11111111-1111-4111-8111-111111111111'});}catch(_){staleRejected=true;}
          await invoke({action:'hello',native_smoke_observed:{ipc_reply:true,workspace:document.getElementById('workspace-path').textContent,
            file_buttons:document.querySelectorAll('#files button').length,scope:document.getElementById('scope-label').textContent,
            project_label:document.getElementById('project-name').textContent,emptyB,restoredA,restoredB,staleRejected,
            no_key_input:!document.querySelector('input[type=password]'),model_calls:0}});
        })().catch(error=>{window.__nativeSmokeError=String(error);});"#
            .replace("ROOT",&serde_json::to_string(&root).unwrap()).replace("OTHER",&serde_json::to_string(&other).unwrap());
        if let Some(view)=handle.get_webview("workspace") {let _=view.eval(&js);}
        std::thread::sleep(std::time::Duration::from_secs(4));
        if let Some(view)=handle.get_webview("workspace") {let _=view.eval_with_callback("JSON.stringify({error:window.__nativeSmokeError,text:document.body.innerText})",|r|eprintln!("Project test: {r}"));}
    });
}
