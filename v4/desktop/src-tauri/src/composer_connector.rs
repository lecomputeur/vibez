//! Public connector identity only. No paths, secrets, website APIs or chat text.
use super::*;
use super::official_web::projects;
#[derive(Clone,Debug,PartialEq,Eq)]
struct Ready {project:String,id:String,title:String}
#[derive(Default)]
struct State {project:Option<String>,enabled:bool,ready:Option<Ready>,cached:Option<Ready>}
#[derive(Default)]
pub struct ComposerState(Mutex<State>);
fn project_id(raw:&str)->bool{projects::valid_id(raw.strip_prefix("code-").or_else(||raw.strip_prefix("chat-")).unwrap_or(raw))}
fn identity(event:&Value)->Option<Ready>{
    let project=event["project_id"].as_str().filter(|p|project_id(p))?;
    let id=event["connector_id"].as_str().filter(|id|projects::valid_id(id))?;
    let name=event["connector_name"].as_str()?;
    let remote_title=event["connector_title"].as_str()?;
    let title=if event["method"]=="work" {
        let (slug,suffix)=name.rsplit_once('_')?;
        let stamp=slug.strip_prefix("vibezwork")?;
        if project.starts_with("code-")||remote_title!=slug||stamp.len()!=16
            ||!stamp.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c))
            ||!(4..=12).contains(&suffix.len())||!suffix.bytes().all(|c|c.is_ascii_lowercase()||c.is_ascii_digit()) {
            return None;
        }
        remote_title.into()
    }else{
        if !name.starts_with("vibez_")||name.len()>64||!name.bytes().all(|c|c.is_ascii_alphanumeric()||matches!(c,b'_'|b'-'))
            ||!remote_title.starts_with("VibeZ · ")||remote_title.chars().count()>160||remote_title.chars().any(char::is_control) {
            return None;
        }
        remote_title.into()
    };
    Some(Ready{project:project.into(),id:id.into(),title})
}
impl State {
    fn observe(&mut self,event:&Value){
        match event["type"].as_str(){
            Some("web_connector")=>{
                let project=event["project"]["id"].as_str().filter(|p|project_id(p)).map(str::to_owned);
                let project_name=event["project"]["name"].as_str()
                    .filter(|n|!n.is_empty()&&n.chars().count()<=120&&!n.chars().any(char::is_control));
                self.cached=project.as_deref().and_then(|project|{
                    let id=event["local_connector_id"].as_str().filter(|id|projects::valid_id(id))?;
                    let name=project_name?;
                    event["folder"].as_str().filter(|path|!path.is_empty())?;
                    Some(Ready{project:project.into(),id:id.into(),title:format!("VibeZ · {name}")})
                });
                let enabled=event["enabled"]==true&&event["workspace_binding"].as_str().is_some_and(|s|s.len()==64&&s.bytes().all(|c|c.is_ascii_hexdigit()));
                if self.project!=project||!enabled{self.ready=None;}
                self.project=project;self.enabled=enabled;
            },
            Some("web_auto")=>{
                if event["project_id"].as_str()!=self.project.as_deref(){return;}
                self.ready=if self.enabled&&event["status"]=="connected"{identity(event)}else{None};
            },
            Some("error") if event["code"]=="engine_stopped"=>*self=Self::default(),
            _=>(),
        }
    }
    fn payload(&self,project:Option<&str>,url:&url::Url)->Value{
        if !projects::origin(url)||project!=self.project.as_deref(){return Value::Null;}
        let ready=self.ready.as_ref().filter(|r|self.enabled&&Some(r.project.as_str())==project);
        let Some(r)=ready.or_else(||self.cached.as_ref().filter(|r|Some(r.project.as_str())==project))else{return Value::Null;};
        json!({"project":r.project,"connector_id":r.id,"title":r.title,"url":url.as_str(),"attach":ready.is_some()})
    }
}
pub fn observe(app:&tauri::AppHandle,event:&Value){if let Ok(mut state)=app.state::<ComposerState>().0.lock(){state.observe(event);}}
pub fn sync(app:&tauri::AppHandle,view:&Webview,url:&url::Url,project:Option<&projects::Project>){
    if !projects::origin(url){return;}
    let verified=project.filter(|p|official_web::confirmed_project(app,url,&p.id));
    let payload=app.state::<ComposerState>().0.lock().map(|s|s.payload(verified.map(|p|p.id.as_str()),url)).unwrap_or(Value::Null);
    let source=include_str!("connector_mention.js").replace("__VIBEZ_CONNECTOR_CONTEXT__",&payload.to_string());
    let _=view.eval(source);
}
#[cfg(test)]mod tests{
    use super::*;
    const A:&str="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";
    const B:&str="bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb";
    fn scope(p:&str,on:bool)->Value{json!({"type":"web_connector","project":{"id":p},"enabled":on,"workspace_binding":"a".repeat(64)})}
    fn connected()->Value{json!({"type":"web_auto","project_id":A,"status":"connected","connector_id":B,"connector_name":"vibez_fixture_ab12","connector_title":"VibeZ · Fixture · 1234abcd"})}
    #[test]fn only_a_ready_verified_current_scope_supplies_public_mention_identity(){
        let u: url::Url=format!("https://chat.mistral.ai/work/projects/{A}").parse().unwrap();let mut s=State::default();s.observe(&connected());assert!(s.payload(Some(A),&u).is_null());s.observe(&scope(A,true));s.observe(&connected());let p=s.payload(Some(A),&u);assert_eq!(p["connector_id"],B);assert_eq!(p.as_object().unwrap().len(),5);assert!(s.payload(Some(B),&u).is_null());assert!(s.payload(None,&u).is_null());assert!(s.payload(Some(A),&"https://evil.invalid/work".parse().unwrap()).is_null());
    }
    #[test]fn pause_scope_switch_failed_connection_and_engine_stop_revoke_the_hint(){
        let u: url::Url=format!("https://chat.mistral.ai/work/projects/{A}").parse().unwrap();for event in [scope(A,false),scope(B,true),json!({"type":"web_auto","project_id":A,"status":"error"}),json!({"type":"error","code":"engine_stopped"})]{let mut s=State::default();s.observe(&scope(A,true));s.observe(&connected());s.observe(&event);assert!(s.payload(Some(A),&u).is_null());}
    }
    #[test]fn cached_identity_only_changes_presentation_and_never_authorizes_attachment(){
        let url:url::Url=format!("https://chat.mistral.ai/work/projects/{A}").parse().unwrap();let mut s=State::default();
        let mut event=scope(A,false);event["project"]["name"]=json!("Fixture");event["folder"]=json!("/private/not-sent-to-Mistral");event["local_connector_id"]=json!(B);
        s.observe(&event);let p=s.payload(Some(A),&url);assert_eq!(p["attach"],false);assert_eq!(p["connector_id"],B);assert_eq!(p.as_object().unwrap().len(),5);assert!(!p.to_string().contains("private"));assert!(s.payload(Some(B),&url).is_null());
        s.observe(&json!({"type":"web_auto","project_id":A,"status":"paused","pause_reason":"sign_in"}));assert_eq!(s.payload(Some(A),&url)["attach"],false);
        event["enabled"]=json!(true);s.observe(&event);s.observe(&connected());assert_eq!(s.payload(Some(A),&url)["attach"],true);
        event["enabled"]=json!(false);s.observe(&event);assert_eq!(s.payload(Some(A),&url)["attach"],false);
        s.observe(&json!({"type":"error","code":"engine_stopped"}));assert!(s.payload(Some(A),&url).is_null());
    }
    #[test]fn malformed_cached_identity_is_not_used_for_presentation(){
        let url:url::Url=format!("https://chat.mistral.ai/work/projects/{A}").parse().unwrap();
        for (field,value) in [("local_connector_id",json!("bad")),("folder",Value::Null),("project",json!({"id":A,"name":"Bad\nname"}))]{
            let mut e=scope(A,false);e["project"]["name"]=json!("Fixture");e["folder"]=json!("/fixture");e["local_connector_id"]=json!(B);e[field]=value;let mut s=State::default();s.observe(&e);assert!(s.payload(Some(A),&url).is_null());
        }
    }
    #[test]fn verified_work_identity_preserves_the_provider_label_and_rejects_other_slugs(){
        let url:url::Url=format!("https://chat.mistral.ai/work/projects/{A}").parse().unwrap();
        let mut state=State::default();
        let mut snapshot=scope(A,true);snapshot["project"]["name"]=json!("CityTripXL");
        state.observe(&snapshot);
        let mut event=connected();
        event["method"]=json!("work");
        event["connector_name"]=json!("vibezwork0123456789abcdef_a1z9");
        event["connector_title"]=json!("vibezwork0123456789abcdef");
        state.observe(&event);
        let payload=state.payload(Some(A),&url);
        assert_eq!(payload["connector_id"],B);
        assert_eq!(payload["title"],"vibezwork0123456789abcdef");
        for (key,value) in [
            ("connector_name",json!("other_0123456789abcdef_a1z9")),
            ("connector_title",json!("vibezwork1123456789abcdef")),
            ("project_id",json!(format!("code-{A}"))),
        ] {
            let mut invalid=event.clone();invalid[key]=value;
            assert!(identity(&invalid).is_none());
        }
    }
    #[test]fn connector_metadata_requires_valid_ids_and_a_human_title(){
        for(key,value)in [("project_id",json!("not-a-project")),("connector_id",json!("bad")),("connector_name",json!("other")),("connector_title",json!("Other connector")),("connector_title",json!("VibeZ · Bad\n · 1234abcd"))]{let mut e=connected();e[key]=value;assert!(identity(&e).is_none());}
    }
}
