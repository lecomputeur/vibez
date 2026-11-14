//! Local associations only. Mistral never receives these paths or native IPC.
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::Path};
use url::Url;
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Project {
    pub id:String,pub name:String,pub url:String,
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub kind:Option<String>,
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub conversation_id:Option<String>,
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub draft:Option<bool>,
}
pub fn origin(url: &Url) -> bool {
    url.scheme() == "https" && matches!(url.host_str(), Some("chat.mistral.ai" | "vibe.mistral.ai"))
        && url.port_or_known_default() == Some(443) && url.username().is_empty() && url.password().is_none()
}
pub fn fallback_name(id:&str)->String {
    let raw=id.strip_prefix("code-").unwrap_or(id);
    format!("Project {}",raw.chars().take(8).collect::<String>())
}
pub fn parse(url: &Url) -> Option<Project> {
    if !origin(url) { return None; }
    let parts: Vec<_> = url.path().trim_matches('/').split('/').collect();
    let (raw,code)=match parts.as_slice() {
        ["work","projects",id,..] => (*id,false),
        ["code",id] if valid_id(id) => (*id,true),
        ["code",id,session] if valid_id(id)&&valid_code_session(session) => (*id,true),
        _ => return None,
    };
    if !valid_id(raw) { return None; }
    if code {
        let expected=if parts.len()==3 {format!("/code/{raw}/{}",parts[2])} else {format!("/code/{raw}")};
        if url.path()!=expected && url.path()!=format!("{expected}/") {return None;}
    }
    let raw = raw.to_ascii_lowercase();
    // Code and Work are separate project spaces even if their UUIDs coincide.
    // Existing Work bindings retain their exact IDs and canonical addresses.
    let id=if code {format!("code-{raw}")} else {raw.clone()};
    let url=if code {format!("https://chat.mistral.ai/code/{raw}")} else {format!("https://chat.mistral.ai/work/projects/{raw}")};
    Some(Project { name: fallback_name(&id), url, id,kind:None,conversation_id:None,draft:None })
}
pub fn valid_id(id:&str)->bool {
    id.len()==36 && id.chars().enumerate().all(|(i,c)| if [8,13,18,23].contains(&i) {c=='-'} else {c.is_ascii_hexdigit()})
}
pub fn conversation_id(url:&Url)->Option<String> {
    if !origin(url){return None;}
    let parts:Vec<_>=url.path().trim_end_matches('/').split('/').collect();
    let raw=match parts.as_slice(){["","work",id]|["","work","chat"|"chats"|"c",id]=>*id,_=>return None};
    if !valid_id(raw)||url.path().ends_with("//"){return None;}
    Some(raw.to_ascii_lowercase())
}
pub fn draft_url(url:&Url)->bool {
    origin(url)&&matches!(url.path(),"/work"|"/work/"|"/work/new"|"/work/new/")
        &&url.query().is_none()&&url.fragment().is_none()
}
pub fn conversation(url:&Url,stable_id:Option<&str>,name:&str)->Option<Project> {
    let remote=conversation_id(url)?;
    let id=stable_id.map(str::to_owned).unwrap_or_else(||format!("chat-{remote}"));
    if !id.strip_prefix("chat-").is_some_and(valid_id){return None;}
    Some(Project{id,name:name.chars().take(120).collect(),url:format!("https://chat.mistral.ai/work/{remote}"),kind:Some("conversation".into()),conversation_id:Some(remote),draft:Some(false)})
}
pub fn draft(stable_id:&str,name:&str)->Option<Project> {
    if !stable_id.strip_prefix("chat-").is_some_and(valid_id){return None;}
    Some(Project{id:stable_id.into(),name:name.chars().take(120).collect(),url:"https://chat.mistral.ai/work".into(),kind:Some("conversation".into()),conversation_id:None,draft:Some(true)})
}
fn valid_code_session(session:&str)->bool {
    if valid_id(session){return true;}
    // Code first creates an explicit draft child under the same project URL.
    // Decode only colons; never accept encoded slashes or arbitrary children.
    let draft=session.to_ascii_lowercase().replace("%3a",":");
    draft.strip_prefix("draft:session:").is_some_and(valid_id)
}
#[derive(Default, Serialize, Deserialize)]
pub struct Bindings { pub folders: BTreeMap<String, String> }
pub fn read(path: &Path) -> Result<Bindings, String> {
    if !path.exists() { return Ok(Bindings::default()); }
    let bytes = std::fs::read(path).map_err(crate::err)?;
    if bytes.len() > 1_000_000 { return Err("The workspace folders file is too large".into()); }
    serde_json::from_slice(&bytes).map_err(|_| "The saved project links could not be read".into())
}
pub fn write(path: &Path, bindings: &Bindings) -> Result<(), String> {
    use std::io::Write;
    static SERIAL:std::sync::atomic::AtomicU64=std::sync::atomic::AtomicU64::new(1);
    let temporary = path.with_extension(format!("tmp-{}-{}",std::process::id(),SERIAL.fetch_add(1,std::sync::atomic::Ordering::SeqCst)));
    let mut options = std::fs::OpenOptions::new(); options.write(true).create_new(true);
    #[cfg(unix)] { use std::os::unix::fs::OpenOptionsExt; options.mode(0o600); }
    let mut file = options.open(&temporary).map_err(crate::err)?;
    file.write_all(&serde_json::to_vec_pretty(bindings).map_err(crate::err)?).map_err(crate::err)?;
    file.sync_all().map_err(crate::err)?;
    std::fs::rename(temporary, path).map_err(crate::err)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn stable_project_identity_across_hosts_and_chats() {
        let id = "cace260d-d95d-4859-b45b-f56f185f15da";
        for host in ["chat.mistral.ai", "vibe.mistral.ai"] {
            for suffix in ["", "/", "/chat/123?tab=files"] {
                assert_eq!(parse(&format!("https://{host}/work/projects/{id}{suffix}").parse().unwrap()).unwrap().id,id);
            }
        }
        for raw in ["https://chat.mistral.ai/work/projects/", "https://chat.mistral.ai/work/projects/new", "https://chat.mistral.ai/work/123", "https://evil.test/work/projects/cace260d-d95d-4859-b45b-f56f185f15da", "https://chat.mistral.ai:444/work/projects/cace260d-d95d-4859-b45b-f56f185f15da"] { assert!(parse(&raw.parse().unwrap()).is_none()); }
    }
    #[test] fn associations_survive_restart_and_unlink_only_affects_one_project() {
        let root=std::env::temp_dir().join(format!("vibez4-bindings-{}",std::process::id()));
        std::fs::create_dir_all(&root).unwrap(); let path=root.join("projects.json");
        let mut b=read(&path).unwrap(); b.folders.insert("A".into(),"/project-a".into()); b.folders.insert("B".into(),"/project-b".into()); write(&path,&b).unwrap();
        let mut b=read(&path).unwrap(); assert_eq!(b.folders["A"],"/project-a"); b.folders.remove("A"); write(&path,&b).unwrap(); let b=read(&path).unwrap(); assert!(!b.folders.contains_key("A")); assert_eq!(b.folders["B"],"/project-b"); std::fs::remove_dir_all(root).unwrap();
    }
    #[test] fn code_project_and_sessions_share_only_their_code_identity() {
        let id="01a0296a-296a-748f-aba4-6dc79fa08bc2";
        let session="01a084bf-d80c-721c-ac67-aa266ecd5662";
        for host in ["chat.mistral.ai","vibe.mistral.ai"] {
            for suffix in ["".to_owned(),"/".to_owned(),format!("/{session}?tab=context#view"),format!("/draft%3Asession%3A{session}"),format!("/draft%3asession%3a{session}"),format!("/draft:session:{session}"),format!("/draft%3Asession:{session}")] {
                let p=parse(&format!("https://{host}/code/{id}{suffix}").parse().unwrap()).unwrap();
                assert_eq!(p.id,format!("code-{id}"));assert_eq!(p.url,format!("https://chat.mistral.ai/code/{id}"));
                assert_eq!(p.name,"Project 01a0296a");
                assert_ne!(p.id,parse(&format!("https://{host}/work/projects/{id}").parse().unwrap()).unwrap().id);
            }
        }
        for route in ["/code","/code/extensions","/code/settings","/code/new",&format!("/code/{id}/settings"),&format!("/code/{id}/{session}/other"),&format!("/code/{id}/new"),&format!("/code/{id}//"),&format!("//code/{id}"),&format!("/code/{id}/draft%3Asession%3Anew"),&format!("/code/{id}/draft%3Asession%3A{session}/other"),&format!("/code/{id}/draft%3Asession%3A{session}%2Fother"),&format!("/code/{id}/draft%253Asession%253A{session}"),&format!("/code/{id}/draft:other:{session}")] {
            assert!(parse(&format!("https://chat.mistral.ai{route}").parse().unwrap()).is_none(),"{route}");
        }
        for raw in [format!("https://evil.test/code/{id}"),format!("https://user:secret@chat.mistral.ai/code/{id}"),format!("https://chat.mistral.ai:444/code/{id}")] {
            assert!(parse(&raw.parse().unwrap()).is_none());
        }
    }
    #[test] fn project_fallback_names_use_raw_uuid_without_merging_namespaces() {
        let id="01a0296a-296a-748f-aba4-6dc79fa08bc2";
        let work=parse(&format!("https://chat.mistral.ai/work/projects/{id}").parse().unwrap()).unwrap();
        let code=parse(&format!("https://chat.mistral.ai/code/{id}").parse().unwrap()).unwrap();
        assert_eq!(work.name,"Project 01a0296a");assert_eq!(code.name,work.name);
        assert_ne!(code.id,work.id);assert_ne!(code.url,work.url);
        assert_eq!(fallback_name(&code.id),code.name);assert_eq!(fallback_name(&work.id),work.name);
    }
    #[test] fn loose_conversation_routes_have_a_separate_stable_namespace_and_canonical_url() {
        let id="11111111-2222-4333-8444-555555555555";
        for host in ["chat.mistral.ai","vibe.mistral.ai"] {for prefix in ["work","work/chat","work/chats","work/c"] {for suffix in ["","/?tab=files#section"] {
            let url:Url=format!("https://{host}/{prefix}/{id}{suffix}").parse().unwrap();
            let context=conversation(&url,None,"A loose conversation").unwrap();
            assert_eq!(context.id,format!("chat-{id}"));assert_eq!(context.url,format!("https://chat.mistral.ai/work/{id}"));assert_eq!(context.conversation_id.as_deref(),Some(id));assert_eq!(context.kind.as_deref(),Some("conversation"));assert_eq!(context.draft,Some(false));
            assert!(parse(&url).is_none());
        }}}
        for route in [format!("//work/{id}"),format!("/work/{id}//"),format!("/work/{id}/extra"),format!("/work/chat/{id}/extra"),"/work/new".into(),"/work/settings".into(),format!("/work/projects/{id}")] {assert!(conversation_id(&format!("https://chat.mistral.ai{route}").parse().unwrap()).is_none());}
        for raw in [format!("https://evil.test/work/{id}"),format!("https://user@chat.mistral.ai/work/{id}"),format!("https://chat.mistral.ai:444/work/{id}")] {assert!(conversation_id(&raw.parse().unwrap()).is_none());}
        assert!(conversation(&format!("https://chat.mistral.ai/work/{id}").parse().unwrap(),Some(id),"bad key").is_none());
    }
    #[test] fn existing_project_dtos_remain_exactly_three_fields_while_conversations_carry_strict_metadata() {
        let id="11111111-2222-4333-8444-555555555555";
        let project=parse(&format!("https://chat.mistral.ai/work/projects/{id}").parse().unwrap()).unwrap();
        let value=serde_json::to_value(&project).unwrap();assert_eq!(value.as_object().unwrap().len(),3);
        let roundtrip:Project=serde_json::from_value(value).unwrap();assert_eq!(roundtrip,project);
        let conversation=conversation(&format!("https://chat.mistral.ai/work/{id}").parse().unwrap(),None,"saved").unwrap();
        let value=serde_json::to_value(conversation).unwrap();assert_eq!(value["draft"],false);assert_eq!(value["kind"],"conversation");assert_eq!(value["conversation_id"],id);
        let draft=draft(&format!("chat-{id}"),"new").unwrap();let value=serde_json::to_value(draft).unwrap();assert_eq!(value["draft"],true);assert!(value.get("conversation_id").is_none());
    }
    #[test] fn draft_routes_are_only_exact_home_pages_and_never_restore_a_persisted_draft_identity() {
        for path in ["/work","/work/","/work/new","/work/new/"] {let url=format!("https://chat.mistral.ai{path}").parse().unwrap();assert!(draft_url(&url));assert!(parse(&url).is_none());}
        for path in ["/work//","/work/new/other","/work?draft=old","/work#old","//work","/code/new"] {assert!(!draft_url(&format!("https://chat.mistral.ai{path}").parse().unwrap()));}
    }
}
