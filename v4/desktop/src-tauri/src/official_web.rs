//! Official website is an unprivileged child. Native code reads only visible
//! project identity. All file configuration/approval stays in the local main UI.
use super::*;
use std::sync::{Arc, atomic::AtomicBool};
use tauri::{LogicalPosition, LogicalSize};
#[path="workspace_projects.rs"]
pub(super) mod projects;
// Session-only associations come exclusively from visible links on a confirmed
// project overview. An arbitrary chat URL never inherits the previous project.
#[derive(Default)]
struct ProjectRecognition {
    confirmed_url: Option<String>,
    project_names: std::collections::BTreeMap<String,String>,
    chats: std::collections::BTreeMap<String, projects::Project>,
    order: std::collections::VecDeque<String>,
    conversations:std::collections::BTreeMap<String,projects::Project>,
    pending_promotions:std::collections::BTreeMap<String,projects::Project>,
    pending_order:std::collections::VecDeque<String>,
    conversation_conflicts:std::collections::BTreeSet<String>,
    snapshot_sequence:Option<u64>,
    draft:Option<DraftContext>,
    project_start:Option<ProjectStart>,
    project_page:Option<ProjectPage>,
    sidebar_return_pages:std::collections::VecDeque<ProjectPage>,
    navigation_last:Option<Value>,
    navigation_events:std::collections::VecDeque<Value>,
}
struct ProjectPage {
    project:projects::Project,source:String,chats:std::collections::BTreeSet<String>,at:u64,
}
struct ProjectStart {
    document:String,nonce:String,project:projects::Project,source:String,
    known:std::collections::BTreeSet<String>,at:u64,
}
struct DraftContext {
    document:String,nonce:String,project:projects::Project,
    known:std::collections::BTreeSet<String>,
}
fn fresh_draft_id()->Option<String> {
    // No persisted orphan draft or website-provided identifier chooses a local
    // workspace. Each newly observed draft gets its own native random UUID.
    let mut bytes=[0_u8;16];
    getrandom::fill(&mut bytes).ok()?;
    bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
    Some(format!("chat-{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",bytes[0],bytes[1],bytes[2],bytes[3],bytes[4],bytes[5],bytes[6],bytes[7],bytes[8],bytes[9],bytes[10],bytes[11],bytes[12],bytes[13],bytes[14],bytes[15]))
}
fn navigation_trace(url:&url::Url,data:&Value,accepted:bool,has_project_page:bool,has_sidebar_page:bool)->Value {
    let route=if projects::draft_url(url){"new_chat"}else if projects::conversation_id(url).is_some(){"conversation"}else if projects::parse(url).is_some(){"project"}else{"other"};
    let mut result=json!({"route":route,"return_accepted":accepted,"project_page_known":has_project_page,"sidebar_page_known":has_sidebar_page});
    for key in ["armed","chosen","confirmed","owner_known","return_ready"]{result[key]=json!(data["navigation_trace"][key].as_bool().unwrap_or(false));}
    result
}
impl ProjectRecognition {
    fn apply_project_name(&mut self,project:&mut projects::Project,name:Option<&str>)->bool {
        if let Some(name)=name.filter(|name|!name.trim().is_empty()&&!name.chars().any(char::is_control)) {
            let name:String=name.trim().chars().take(120).collect();
            self.project_names.insert(project.id.clone(),name.clone());project.name=name;
            while self.project_names.len()>256 {let key=self.project_names.keys().find(|id|*id!=&project.id).cloned();if let Some(key)=key {self.project_names.remove(&key);}else{break;}}
            return true;
        }
        if let Some(name)=self.project_names.get(&project.id){project.name=name.clone();return true;}
        false
    }
    fn accept_snapshot(&mut self,event:&Value)->bool {
        if event["type"]!="web_connector"{return true;}
        match event.get("snapshot_sequence") {
            None=>self.snapshot_sequence.is_none(),
            Some(value)=>{
                let Some(sequence)=value.as_u64().filter(|n|*n>0)else{return false;};
                if self.snapshot_sequence.is_some_and(|last|sequence<=last){return false;}
                self.snapshot_sequence=Some(sequence);true
            }
        }
    }
    fn observe_event(&mut self,event:&Value)->bool {
        if !self.accept_snapshot(event){return false;}
        self.observe_conversations(event);true
    }
    fn observe_conversations(&mut self,event:&Value) {
        if event["type"]!="web_connector"{return;}
        let Some(items)=event["projects"].as_array()else{return;};
        let mut aliases=std::collections::BTreeMap::new();
        let mut conflicting=std::collections::BTreeSet::new();
        for item in items.iter().take(4096) {
            if item["kind"]!="conversation"||item["draft"].as_bool()!=Some(false){continue;}
            let Some(remote)=item["conversation_id"].as_str().filter(|id|projects::valid_id(id))else{continue;};
            let Some(stable)=item["id"].as_str().filter(|id|id.strip_prefix("chat-").is_some_and(projects::valid_id))else{continue;};
            let Some(url)=item["url"].as_str().and_then(|raw|raw.parse::<url::Url>().ok()).filter(|url|projects::conversation_id(url).as_deref()==Some(remote))else{continue;};
            let name=item["name"].as_str().unwrap_or("");
            let Some(project)=projects::conversation(&url,Some(stable),name)else{continue;};
            if conflicting.contains(remote){continue;}
            if aliases.get(remote).is_some_and(|old:&projects::Project|old.id!=project.id){aliases.remove(remote);conflicting.insert(remote.to_owned());continue;}
            aliases.insert(remote.to_owned(),project);
        }
        // A native first-send observation may precede its backend select/save.
        // An older complete snapshot therefore cannot disprove that pending
        // identity. Only the exact saved alias acknowledges it. A contradictory
        // alias instead pauses this conversation; no alternate folder is chosen.
        for remote in self.pending_order.iter().cloned().collect::<Vec<_>>() {
            let pending=self.pending_promotions.get(&remote).unwrap();
            let acknowledgment=aliases.get(&remote);
            if conflicting.contains(&remote)||acknowledgment.is_some_and(|known|known.id!=pending.id) {
                aliases.remove(&remote);conflicting.insert(remote.clone());
                self.pending_promotions.remove(&remote);self.pending_order.retain(|old|old!=&remote);
            }else if acknowledgment.is_some() {
                self.pending_promotions.remove(&remote);self.pending_order.retain(|old|old!=&remote);
            }
        }
        self.conversations=aliases;
        self.conversation_conflicts=conflicting;
    }
    fn loose_conversation(&mut self,url:&url::Url,name:&str,fallback:&str,previous:Option<&projects::Project>)->Option<projects::Project> {
        let remote=projects::conversation_id(url)?;
        if self.conversation_conflicts.contains(&remote){self.confirmed_url=None;return None;}
        let prior=previous.filter(|p|p.kind.as_deref()==Some("conversation")&&p.draft==Some(false)&&p.conversation_id.as_deref()==Some(remote.as_str()));
        let known=self.conversations.get(&remote).or_else(||self.pending_promotions.get(&remote)).or(prior);
        let stable=known.map(|project|project.id.as_str());
        let mut project=projects::conversation(url,stable,name)?;
        if project.name.is_empty(){project.name=known.filter(|p|!p.name.is_empty()).map(|p|p.name.clone()).unwrap_or_else(||fallback.into());}
        self.confirmed_url=Some(url.as_str().to_owned());Some(project)
    }
    fn draft_proof(&self,url:&url::Url,data:&Value,now_ms:u64)->bool {
        let Some(draft)=self.draft.as_ref()else{return false;};
        let info=&data["loose"];let proof=&info["submitted"];
        let Some(at)=proof["at"].as_u64()else{return false;};
        let Some(from)=proof["from"].as_str().and_then(|raw|raw.parse::<url::Url>().ok())else{return false;};
        let Some(remote)=projects::conversation_id(url)else{return false;};
        info["document"].as_str()==Some(draft.document.as_str())&&info["nonce"].as_str()==Some(draft.nonce.as_str())
            &&proof["document"].as_str()==Some(draft.document.as_str())&&proof["nonce"].as_str()==Some(draft.nonce.as_str())
            &&proof["sequence"].as_u64().is_some_and(|n|n>0)&&at<=now_ms.saturating_add(1000)&&now_ms.saturating_sub(at)<=30_000
            &&projects::draft_url(&from)&&from.origin()==url.origin()
            &&!draft.known.contains(&remote)&&!self.conversations.contains_key(&remote)&&!self.pending_promotions.contains_key(&remote)&&!self.conversation_conflicts.contains(&remote)
            &&!self.chats.keys().any(|raw|raw.parse::<url::Url>().ok().and_then(|url|projects::conversation_id(&url)).as_ref()==Some(&remote))
    }
    fn loose_context(&mut self,url:&url::Url,data:&Value,name:&str,fallback:&str,now_ms:u64,previous:Option<&projects::Project>)->Option<projects::Project> {
        if projects::draft_url(url) {
            let info=&data["loose"];
            let document=info["document"].as_str().filter(|id|projects::valid_id(id));
            let nonce=info["nonce"].as_str().filter(|id|projects::valid_id(id));
            let (Some(document),Some(nonce))=(document,nonce)else{self.draft=None;return None;};
            if info["ready"]!=true{self.draft=None;return None;}
            if !self.draft.as_ref().is_some_and(|old|old.document==document&&old.nonce==nonce) {
                let mut known=std::collections::BTreeSet::new();
                if let Some(ids)=info["known"].as_array(){for id in ids.iter().take(512).filter_map(Value::as_str).filter(|id|projects::valid_id(id)){known.insert(id.to_ascii_lowercase());}}
                let project=projects::draft(&fresh_draft_id()?,fallback)?;
                self.draft=Some(DraftContext{document:document.into(),nonce:nonce.into(),project,known});
            }
            self.confirmed_url=Some(url.as_str().into());
            return self.draft.as_ref().map(|draft|draft.project.clone());
        }
        if self.draft_proof(url,data,now_ms) {
            let draft=self.draft.take().unwrap();
            let mut project=projects::conversation(url,Some(&draft.project.id),if name.is_empty(){&draft.project.name}else{name})?;
            project.draft=Some(false);
            let remote=project.conversation_id.clone().unwrap();
            self.pending_order.retain(|old|old!=&remote);self.pending_order.push_back(remote.clone());
            self.pending_promotions.insert(remote,project.clone());
            while self.pending_order.len()>32{if let Some(old)=self.pending_order.pop_front(){self.pending_promotions.remove(&old);}}
            self.confirmed_url=Some(url.as_str().into());return Some(project);
        }
        self.draft=None;
        self.loose_conversation(url,name,fallback,previous)
    }
    fn project_first_send(&mut self,url:&url::Url,previous:Option<&projects::Project>,detected:Option<&projects::Project>,ambiguous:bool,data:&Value,now:u64)->Option<projects::Project> {
        let start=self.project_start.take();
        if ambiguous{return None;}
        let info=&data["project_start"];
        if let Some(project)=detected.filter(|p|p.kind.is_none()&&projects::valid_id(&p.id)) {
            // Only a confirmed, exact project overview can arm a first send.
            let parsed=projects::parse(url);
            if parsed.as_ref().is_some_and(|p|p.id==project.id&&url.path().trim_end_matches('/')==format!("/work/projects/{}",project.id))
                &&info["ready"]==true&&info["project"].as_str()==Some(project.id.as_str())&&info["from"].as_str()==Some(url.as_str()) {
                if let (Some(document),Some(nonce))=(info["document"].as_str().filter(|s|projects::valid_id(s)),info["nonce"].as_str().filter(|s|projects::valid_id(s))) {
                    let mut known=std::collections::BTreeSet::new();
                    if let Some(ids)=info["known"].as_array(){for id in ids.iter().take(512).filter_map(Value::as_str).filter(|s|projects::valid_id(s)){known.insert(id.to_ascii_lowercase());}}
                    self.project_start=Some(ProjectStart{document:document.into(),nonce:nonce.into(),project:project.clone(),source:url.as_str().into(),known,at:now});
                }
                return None;
            }
        }
        let start=start?;
        let remote=projects::conversation_id(url)?;
        let proof=&info["submitted"];let at=proof["at"].as_u64()?;
        let source=start.source.parse::<url::Url>().ok()?;
        if !previous.is_some_and(|p|p.id==start.project.id&&p.kind.is_none())
            ||detected.is_some_and(|p|p.id!=start.project.id)||url.query().is_some()||url.fragment().is_some()||source.origin()!=url.origin()
            ||info["ready"]!=false||info["project"].as_str()!=Some(start.project.id.as_str())||info["from"].as_str()!=Some(start.source.as_str())
            ||info["document"].as_str()!=Some(start.document.as_str())||info["nonce"].as_str()!=Some(start.nonce.as_str())
            ||proof["document"].as_str()!=Some(start.document.as_str())||proof["nonce"].as_str()!=Some(start.nonce.as_str())
            ||proof["project"].as_str()!=Some(start.project.id.as_str())||proof["from"].as_str()!=Some(start.source.as_str())
            ||!proof["sequence"].as_u64().is_some_and(|n|n>0)||at>now.saturating_add(1000)||now.saturating_sub(at)>30_000
            ||now.saturating_sub(start.at)>30_000||at.saturating_add(1000)<start.at
            ||start.known.contains(&remote)||self.conversations.contains_key(&remote)||self.pending_promotions.contains_key(&remote)||self.conversation_conflicts.contains(&remote)
            ||self.chats.keys().any(|raw|raw.parse::<url::Url>().ok().and_then(|u|projects::conversation_id(&u)).as_deref()==Some(remote.as_str())) {return None;}
        let key=Self::chat_url(url)?;
        self.order.retain(|old|old!=&key);self.order.push_back(key.clone());self.chats.insert(key,start.project.clone());
        while self.order.len()>256{if let Some(old)=self.order.pop_front(){self.chats.remove(&old);}}
        Some(start.project)
    }
    fn context(&mut self,url:&url::Url,previous:Option<&projects::Project>,detected:Option<projects::Project>,ambiguous:bool,data:&Value,fallback:&str,now_ms:u64)->Option<projects::Project> {
        let detected=self.project_first_send(url,previous,detected.as_ref(),ambiguous,data,now_ms).or(detected);
        // A home route may start another draft without changing URL. It never
        // inherits a former project's missing breadcrumb solely from that URL.
        let previous=if projects::draft_url(url){None}else{previous};
        let project=self.resolve(url,previous,detected,ambiguous);
        if ambiguous{self.draft=None;return None;}
        if project.as_ref().is_some_and(|p|p.kind.as_deref()!=Some("conversation")){self.draft=None;return project;}
        let name=data["conversation_name"].as_str().unwrap_or("");
        self.loose_context(url,data,name,fallback,now_ms,previous)
    }
    fn remember_project_page(&mut self,url:&url::Url,project:Option<&projects::Project>,links:&[String],now:u64) {
        // The home route is an intermediate redirect after deletion, not proof
        // of project ownership. Its composer never inherits this saved context.
        if projects::draft_url(url){return;}
        let prior=self.project_page.take();
        let Some(project)=project.filter(|p|p.kind.is_none()&&projects::valid_id(&p.id))else{return;};
        let Some(canonical)=project.url.parse::<url::Url>().ok().and_then(|u|projects::parse(&u))else{return;};
        if canonical.id!=project.id||canonical.url!=project.url{return;}
        let mut chats=std::collections::BTreeSet::new();
        if let Some(chat)=projects::conversation_id(url){chats.insert(chat);}
        else if projects::parse(url).as_ref().map(|p|&p.id)!=Some(&project.id){return;}
        // Sidebar deletion may target another conversation in this same project.
        // These IDs are used only for returning to the project, never to grant
        // a chat access to its folder. Retain just-seen rows across their removal.
        chats.extend(links.iter().take(64).filter_map(|raw|raw.parse::<url::Url>().ok()).filter(|u|u.origin()==url.origin()).filter_map(|u|projects::conversation_id(&u)));
        if let Some(old)=prior.filter(|old|old.project.id==project.id&&old.source==url.as_str()&&now.saturating_sub(old.at)<=30_000){chats.extend(old.chats);}
        while chats.len()>128{let last=chats.last().cloned().unwrap();chats.remove(&last);}
        self.project_page=Some(ProjectPage{project:project.clone(),source:url.as_str().into(),chats,at:now});
    }
    fn record_navigation(&mut self,app:&tauri::AppHandle,url:&url::Url,data:&Value,accepted:bool,now:u64) {
        if !projects::origin(url){return;}
        let mut state=navigation_trace(url,data,accepted,self.project_page.is_some(),!self.sidebar_return_pages.is_empty());
        if self.navigation_last.as_ref()==Some(&state){return;}
        self.navigation_last=Some(state.clone());state["at_ms"]=json!(now);self.navigation_events.push_back(state);
        while self.navigation_events.len()>16{self.navigation_events.pop_front();}
        // Only fixed phase flags are written. No URLs, project names, messages,
        // folder paths or credentials are collected from the hosted page.
        let Ok(root)=app.path().app_data_dir()else{return;};
        let target=root.join("navigation-status.json");let temp=root.join("navigation-status.tmp");
        if [&target,&temp].iter().any(|p|std::fs::symlink_metadata(p).is_ok_and(|m|m.file_type().is_symlink())){return;}
        let mut options=std::fs::OpenOptions::new();options.create(true).write(true).truncate(true);
        #[cfg(unix)] {use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
        if let Ok(mut file)=options.open(&temp){
            let record=json!({"schema":1,"version":env!("CARGO_PKG_VERSION"),"events":self.navigation_events});
            if serde_json::to_writer(&mut file,&record).is_ok(){let _=std::fs::rename(&temp,&target);}
        }
    }
    fn remember_sidebar_returns(&mut self,url:&url::Url,data:&Value,now:u64) {
        if !projects::origin(url)||!(projects::draft_url(url)||projects::conversation_id(url).is_some()||projects::parse(url).is_some_and(|p|projects::valid_id(&p.id))){self.sidebar_return_pages.clear();return;}
        self.sidebar_return_pages.retain(|page|now.saturating_sub(page.at)<=30_000);
        let Some(rows)=data["sidebar_return_projects"].as_array()else{return;};
        for row in rows.iter().take(64){
            let Some(raw)=row["url"].as_str().and_then(|raw|raw.parse::<url::Url>().ok()).filter(|u|u.origin()==url.origin())else{continue;};
            let Some(mut project)=projects::parse(&raw).filter(|p|projects::valid_id(&p.id)&&row["id"].as_str()==Some(p.id.as_str())&&raw.as_str()==p.url)else{continue;};
            if let Some(name)=row["name"].as_str(){project.name=name.chars().take(120).collect();}
            let Some(links)=row["chats"].as_array()else{continue;};
            let mut chats=std::collections::BTreeSet::new();
            for link in links.iter().take(64){if let Some(chat)=link.as_str().and_then(|s|s.parse::<url::Url>().ok()).filter(|u|u.origin()==url.origin()).and_then(|u|projects::conversation_id(&u)){chats.insert(chat);}}
            if let Some(index)=self.sidebar_return_pages.iter().position(|old|old.source==url.as_str()&&old.project.id==project.id){let prior=self.sidebar_return_pages.remove(index).unwrap();chats.extend(prior.chats);}
            while chats.len()>128{let last=chats.last().cloned().unwrap();chats.remove(&last);}
            self.sidebar_return_pages.push_back(ProjectPage{project,source:url.as_str().into(),chats,at:now});
        }
        while self.sidebar_return_pages.len()>128{self.sidebar_return_pages.pop_front();}
    }
    fn removed_chat_return(&mut self,url:&url::Url,data:&Value,now:u64)->Option<url::Url> {
        let proof=&data["project_return"];
        let matches=|page:&&ProjectPage|proof["project"].as_str()==Some(page.project.id.as_str())&&proof["from"].as_str()==Some(page.source.as_str())&&proof["chat"].as_str().is_some_and(|id|page.chats.contains(id));
        let page=self.project_page.as_ref().filter(matches).or_else(||self.sidebar_return_pages.iter().find(matches))?;
        let home=proof["reason"]=="removed_project_chat"&&projects::draft_url(url);
        let missing=proof["reason"]=="missing_project_chat"&&url.as_str()==page.source
            &&projects::conversation_id(url).as_deref()==proof["chat"].as_str();
        if (!home&&!missing)||data["ambiguous"]==true{return None;}
        let at=proof["at"].as_u64()?;
        let source=page.source.parse::<url::Url>().ok()?;
        if proof["project"].as_str()!=Some(page.project.id.as_str())
            ||proof["from"].as_str()!=Some(page.source.as_str())||source.origin()!=url.origin()
            ||!proof["chat"].as_str().is_some_and(|id|page.chats.contains(id))
            ||at>now.saturating_add(1000)||now.saturating_sub(at)>30_000||now.saturating_sub(page.at)>30_000{return None;}
        // Navigate to the already confirmed overview instead of attaching its
        // folder to a fresh loose conversation. Consume once to avoid loops.
        let target=page.project.url.parse().ok()?;
        let removed=proof["chat"].as_str()?;
        let forgotten:Vec<_>=self.chats.keys().filter(|raw|raw.parse::<url::Url>().ok().and_then(|u|projects::conversation_id(&u)).as_deref()==Some(removed)).cloned().collect();
        for key in forgotten{self.chats.remove(&key);self.order.retain(|old|old!=&key);}
        self.project_page=None;self.sidebar_return_pages.clear();self.draft=None;self.project_start=None;self.confirmed_url=None;
        Some(target)
    }
    fn chat_url(url: &url::Url) -> Option<String> {
        if !projects::origin(url) { return None; }
        let parts: Vec<_> = url.path().trim_end_matches('/').split('/').collect();
        let id=match parts.as_slice() {
            ["", "work", id] => *id,
            ["", "work", "chat" | "chats" | "c", id] => *id,
            _ => return None,
        };
        if id.len()!=36 || !id.chars().enumerate().all(|(i,c)| if [8,13,18,23].contains(&i) {c=='-'} else {c.is_ascii_hexdigit()}) {return None;}
        let prefix=if parts.len()==3 {"/work".to_owned()} else {format!("/work/{}",parts[2])};
        Some(format!("{}{prefix}/{}",url.origin().ascii_serialization(),id.to_ascii_lowercase()))
    }
    fn observe_url(&mut self,url:&url::Url) {
        if self.confirmed_url.as_deref()!=Some(url.as_str()) {self.confirmed_url=None;}
    }
    fn remember_overview(&mut self,url:&url::Url,project:&projects::Project,links:&[String]) {
        let path=url.path().trim_end_matches('/');
        if !path.starts_with("/work/projects/") || path.split('/').count()!=4 || projects::parse(url).as_ref().map(|p|&p.id)!=Some(&project.id) {return;}
        for raw in links.iter().take(64) {
            let Some(chat)=raw.parse().ok().and_then(|u|Self::chat_url(&u)) else {continue;};
            self.order.retain(|old|old!=&chat);
            self.order.push_back(chat.clone());self.chats.insert(chat,project.clone());
            while self.order.len()>256 {if let Some(old)=self.order.pop_front() {self.chats.remove(&old);}}
        }
    }
    fn resolve(&mut self,url:&url::Url,previous:Option<&projects::Project>,detected:Option<projects::Project>,ambiguous:bool)->Option<projects::Project> {
        self.observe_url(url);
        let code=projects::parse(url).is_some_and(|p|p.id.starts_with("code-"));
        if !projects::origin(url) || !(url.path().starts_with("/work/") || projects::draft_url(url) || code) {self.confirmed_url=None;return None;}
        let chat=Self::chat_url(url);
        if let Some(project)=detected {
            // Fresh visible evidence wins over a previously collected association.
            if let Some(key)=chat.as_ref() {
                if self.chats.get(key).is_some_and(|old|old.id!=project.id) {self.chats.remove(key);self.order.retain(|old|old!=key);}
            }
            self.confirmed_url=Some(url.as_str().to_owned());return Some(project);
        }
        if ambiguous {
            self.confirmed_url=None;
            if let Some(key)=chat {self.chats.remove(&key);self.order.retain(|old|old!=&key);}
            return None;
        }
        if let Some(project)=chat.as_ref().and_then(|key|self.chats.get(key)).cloned() {
            self.confirmed_url=Some(url.as_str().to_owned());return Some(project);
        }
        if self.confirmed_url.as_deref()==Some(url.as_str()) {return previous.cloned();}
        self.confirmed_url=None;None
    }
}
// Local UI mutations use only opaque IDs from a fresh backend snapshot.
// No folder paths, authentication tokens, or imported file names are cached.
#[derive(Clone,Debug,PartialEq,Eq)]
struct FolderAccess {
    project:String,
    binding:Option<String>,
    ids:std::collections::BTreeSet<String>,
    roots_known:bool,
}
fn folder_id(value:&str)->bool {
    value.len()==32&&value.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c))
}
fn workspace_binding(value:&str)->bool {
    value.len()==64&&value.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c))
}
fn subfolder_name(value:&str)->bool {
    !value.is_empty()&&value.len()<=255&&value.trim()==value&&!value.starts_with('.')
        &&!value.contains('/')&&!value.contains('\\')&&!value.chars().any(char::is_control)
}
fn folder_request_id(value:&str)->bool {
    !value.is_empty()&&value.len()<=80&&value.chars().all(|c|c.is_ascii_alphanumeric()||c=='-')
}
fn folder_access_snapshot(event:&Value)->Option<FolderAccess> {
    if event["type"]!="web_connector"{return None;}
    let project=event["project"]["id"].as_str()?;
    let raw=project.strip_prefix("code-").or_else(||project.strip_prefix("chat-")).unwrap_or(project);
    if !projects::valid_id(raw){return None;}
    // Older isolated fixture backends expose one folder without a roots DTO.
    // Their original single-folder link remains usable, never the new actions.
    if event.get("folders").is_none()&&event.get("workspace_binding").is_none() {
        return Some(FolderAccess{project:project.into(),binding:None,ids:Default::default(),roots_known:false});
    }
    let rows=event["folders"].as_array()?;
    if rows.len()>16{return None;}
    let mut ids=std::collections::BTreeSet::new();
    for row in rows {
        let id=row["id"].as_str().filter(|id|folder_id(id))?;
        if !ids.insert(id.to_owned()){return None;}
    }
    let binding=if ids.is_empty() {
        if !event["workspace_binding"].is_null()||!event["target_folder_id"].is_null(){return None;}
        None
    }else{
        let binding=event["workspace_binding"].as_str().filter(|value|workspace_binding(value))?;
        let selected=event["target_folder_id"].as_str()?;
        if !ids.contains(selected){return None;}
        Some(binding.to_owned())
    };
    Some(FolderAccess{project:project.into(),binding,ids,roots_known:true})
}
fn authorize_workspace_creation(access:Option<&FolderAccess>,project:&str)->Result<(),String> {
    let current=access.filter(|access|access.project==project&&access.roots_known).ok_or("Wait until the workspace folder is loaded")?;
    if current.binding.is_some()||!current.ids.is_empty(){return Err("This project already has a workspace folder. You can change it or create a subfolder in it.".into());}
    Ok(())
}
fn authorize_folder_action(access:Option<&FolderAccess>,project:&str,payload:&Value,choice:Option<&(String,String)>)->Result<(),String> {
    let current=access.filter(|access|access.project==project).ok_or("Wait until the linked folders have loaded")?;
    let action=payload["action"].as_str().unwrap_or("");
    if let Some(binding)=current.binding.as_deref() {
        if payload["workspace_binding"].as_str()!=Some(binding){return Err("The linked folders have changed. Try again.".into());}
    }else{
        if action!="web_link"||!payload["workspace_binding"].is_null(){return Err("Choose a workspace for this project first".into());}
    }
    let id=match payload.get("folder_id") {
        None=>None,
        Some(value)=>Some(value.as_str().filter(|id|folder_id(id)&&current.ids.contains(*id)).ok_or("The chosen workspace folder is no longer linked")?),
    };
    match action {
        "web_link"|"web_add_folder"=>{
            if action=="web_link"&&id.is_none()&&current.ids.len()>1 {return Err("Choose which workspace you want to change".into());}
            if !choice.is_some_and(|(id,path)|id==project&&Some(path.as_str())==payload["path"].as_str()) {return Err("Choose the workspace with the folder picker".into());}
        }
        "web_local_files"=>{
            if !folder_request_id(payload["request_id"].as_str().unwrap_or(""))||!matches!(payload["operation"].as_str(),Some("list"|"move"|"mkdir")){return Err("Invalid file action".into());}
            for key in ["path","destination","name"] {if let Some(value)=payload.get(key){if !value.as_str().is_some_and(|v|v.len()<=2048&&!v.chars().any(char::is_control)){return Err("Invalid file path".into());}}}
        }
        "web_select_folder"|"web_remove_folder"=>{
            if id.is_none(){return Err("Choose a linked workspace".into());}
        }
        "web_create_folder"=>{
            if payload["project_id"].as_str()!=Some(project) {return Err("The project or conversation has changed".into());}
            if current.ids.is_empty() {return Err("Choose a workspace for this project first".into());}
            let fields=payload.as_object().ok_or("Invalid folder request")?;
            if fields.keys().any(|key|!matches!(key.as_str(),"action"|"project_id"|"workspace_binding"|"request_id"|"name")) {return Err("A new folder has only a name inside the workspace".into());}
            if !payload["name"].as_str().is_some_and(subfolder_name) {return Err("Enter one visible folder name, without paths".into());}
            if !payload["request_id"].as_str().is_some_and(folder_request_id) {return Err("Geen geldig mapverzoek".into());}
        }
        _=>return Err("Onbekende maphandeling".into()),
    }
    Ok(())
}
#[derive(Default)]
pub struct WebState {
    pub visible: AtomicBool,
    pub panel: AtomicBool,
    pub project: Mutex<Option<projects::Project>>,
    recognition: Mutex<ProjectRecognition>,
    pub gate: tokio::sync::Mutex<()>,
    pub choice: Mutex<Option<(String, String)>>,
    folder_access:Mutex<Option<FolderAccess>>,
    last_project_click: Mutex<Option<String>>,
}
/// Only backend-produced, bounded identity metadata is retained. Folder paths,
/// tokens, credentials, and stored orphan drafts never enter this alias table.
pub fn observe(app:&tauri::AppHandle,event:&Value)->bool {
    if event["type"]=="error"&&event["code"]=="engine_stopped" {
        if let Ok(mut access)=app.state::<WebState>().folder_access.lock(){*access=None;}
        return true;
    }
    if event["type"]!="web_connector"{return true;}
    let state=app.state::<WebState>();
    let fresh={let Ok(mut recognition)=state.recognition.lock()else{return false;};recognition.observe_event(event)};
    if !fresh{return false;}
    let Ok(mut access)=state.folder_access.lock()else{return false;};
    *access=folder_access_snapshot(event);true
}
pub(super) async fn eval(view: &Webview, script: &str) -> Result<String,String> {
    let (tx,rx)=tokio::sync::oneshot::channel();
    let tx=Arc::new(Mutex::new(Some(tx)));
    view.eval_with_callback(script,move |result| {
        if let Ok(mut slot)=tx.lock() { if let Some(tx)=slot.take() { let _=tx.send(result); } }
    }).map_err(err)?;
    let raw=tokio::time::timeout(std::time::Duration::from_secs(3),rx).await.map_err(err)?.map_err(err)?;
    Ok(serde_json::from_str::<String>(&raw).unwrap_or(raw))
}
pub(super) fn confirmed_project(app:&tauri::AppHandle,url:&url::Url,id:&str)->bool {
    if !projects::origin(url) {return false;}
    let state=app.state::<WebState>();
    let Ok(project)=state.project.lock() else {return false;};
    let Ok(recognition)=state.recognition.lock() else {return false;};
    project.as_ref().is_some_and(|project|project.id==id)&&recognition.confirmed_url.as_deref()==Some(url.as_str())
}
pub(super) fn work_setup_current(app:&tauri::AppHandle,project:&str,binding:&str)->bool {
    let state=app.state::<WebState>();
    if !state.visible.load(Ordering::SeqCst) {return false;}
    let Some(url)=app.get_webview("mistral-web").and_then(|view|view.url().ok())else{return false;};
    confirmed_project(app,&url,project)&&state.folder_access.lock().is_ok_and(|access|{
        access.as_ref().is_some_and(|access|access.project==project&&access.binding.as_deref()==Some(binding))
    })
}
// During an attachment download WebKit can temporarily expose the attachment
// URL. Otherwise require the still-confirmed chat route, so a project switch
// cannot reuse the previous project's default Save directory.
fn download_route_matches(confirmed:Option<&str>,current:&url::Url,download:&url::Url)->bool {
    confirmed.and_then(|value|url::Url::parse(value).ok()).is_some_and(|url|projects::origin(&url)&&(current==&url||current==download))
}
pub(super) fn download_project(app:&tauri::AppHandle,download:&url::Url)->Option<String> {
    let current=app.get_webview("mistral-web")?.url().ok()?;
    let state=app.state::<WebState>();
    let project=state.project.lock().ok()?;
    let recognition=state.recognition.lock().ok()?;
    download_route_matches(recognition.confirmed_url.as_deref(),&current,download).then(||project.as_ref().map(|p|p.id.clone())).flatten()
}
fn preserve_known_project_name(project:&mut projects::Project,previous:Option<&projects::Project>) {
    if project.name==projects::fallback_name(&project.id) {
        if let Some(previous)=previous.filter(|old|old.id==project.id) {project.name=previous.name.clone();}
    }
}
pub(super) async fn sync(app: &tauri::AppHandle) -> Result<(),String> {
    let state=app.state::<WebState>();
    if !state.visible.load(Ordering::SeqCst) { return Ok(()); }
    let view=app.get_webview("mistral-web").ok_or("Mistral has not loaded yet")?;
    let url=view.url().map_err(err)?;
    state.recognition.lock().map_err(err)?.observe_url(&url);
    let mut project=projects::parse(&url);
    let direct_project=project.is_some();
    let mut ambiguous=false;
    let mut chat_links=Vec::new();
    let mut clicked=None;
    let mut context_data=Value::Null;
    if projects::origin(&url) {
        let raw=eval(&view,include_str!("workspace_project.js")).await.unwrap_or_default();
        if view.url().map_err(err)? != url {state.recognition.lock().map_err(err)?.confirmed_url=None;return Err("Mistral wisselt van pagina".into());}
        if let Ok(data)=serde_json::from_str::<Value>(&raw) {
            context_data=data.clone();
            if let (Some(id),Some(stamp))=(data["clicked"]["id"].as_str(),data["clicked"]["stamp"].as_str()) {
                if stamp.len()<=64&&stamp.chars().all(|c|c.is_ascii_digit()||c==':') {clicked=Some((id.to_owned(),stamp.to_owned()));}
            }
            if let Some(chats)=data["chats"].as_array() {chat_links=chats.iter().take(64).filter_map(|v|v.as_str().map(str::to_owned)).collect();}
            if project.is_none()&&(url.path().starts_with("/work/")||projects::draft_url(&url)) {
                ambiguous=data["ambiguous"].as_bool().unwrap_or(false);
                let mut candidates=std::collections::BTreeMap::new();
                if let Some(links)=data["links"].as_array() {
                    for link in links.iter().take(6) {
                        if let Some(mut p)=link["href"].as_str().and_then(|u|u.parse().ok()).and_then(|u|projects::parse(&u)) {
                            if let Some(name)=link["name"].as_str().filter(|v|!v.trim().is_empty()) {p.name=name.chars().take(120).collect();}
                            candidates.insert(p.id.clone(),p);
                        }
                    }
                }
                ambiguous|=candidates.len()>1;
                if candidates.len()==1 && !ambiguous {project=candidates.into_values().next();}
            }
        }
    }
    if direct_project {
        if let Some(p)=project.as_mut() {
            if !state.recognition.lock().map_err(err)?.apply_project_name(p,context_data["name"].as_str()) {
                // The URL changed before Mistral rendered the matching project.
                // Do not register a connector with the prior page's title.
                project=None;ambiguous=true;
            }
        }
    }
    let mut old=state.project.lock().map_err(err)?;
    let mut recognition=state.recognition.lock().map_err(err)?;
    let now_ms=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_millis().min(u64::MAX as u128) as u64;
    if let Some(target)=recognition.removed_chat_return(&url,&context_data,now_ms) {
        recognition.record_navigation(app,&url,&context_data,true,now_ms);
        // Revoke the old scope while navigation is in flight. Only the next
        // verified project URL can resume its previously approved connection.
        *old=None;*state.choice.lock().map_err(err)?=None;
        write_engine(app,&json!({"action":"web_context","project":null}))?;
        drop(recognition);drop(old);
        view.eval("window.__vibezProjectReturn?.reset();window.__vibezLooseConversations?.reset();window.__vibezProjectStart?.reset();").map_err(err)?;
        view.navigate(target).map_err(err)?;return Ok(());
    }
    recognition.record_navigation(app,&url,&context_data,false,now_ms);
    let fallback=super::classic_language::text(app,if projects::draft_url(&url){"newConversation"}else{"conversationPanel"});
    project=recognition.context(&url,old.as_ref(),project,ambiguous,&context_data,&fallback,now_ms);
    if let Some(p)=project.as_mut() {
        preserve_known_project_name(p,old.as_ref());
    }
    if let Some(p)=project.as_ref() {recognition.remember_overview(&url,p,&chat_links);}
    let mut return_links=chat_links.clone();
    if let Some(rows)=context_data["project_chats"].as_array(){return_links.extend(rows.iter().take(64).filter_map(|value|value.as_str().map(str::to_owned)));}
    recognition.remember_project_page(&url,project.as_ref(),&return_links,now_ms);
    recognition.remember_sidebar_returns(&url,&context_data,now_ms);
    let project_changed=old.as_ref().map(|p|&p.id)!=project.as_ref().map(|p|&p.id);
    if *old != project {
        *old=project.clone();
        if project_changed {*state.choice.lock().map_err(err)?=None;}
        write_engine(app,&json!({"action":"web_context","project":project}))?;
    }
    let mut clicked_at=None;
    let clicked_current=if let Some((id,stamp))=clicked {
        let mut last=state.last_project_click.lock().map_err(err)?;
        let fresh=last.as_ref()!=Some(&stamp);
        let matches=project.as_ref().is_some_and(|p|p.id==id||p.kind.as_deref()==Some("conversation")&&p.conversation_id.as_deref()==id.strip_prefix("chat-"));
        if matches&&(fresh||project_changed) {clicked_at=stamp.split(':').next().and_then(|time|time.parse::<u64>().ok());}
        *last=Some(stamp);
        fresh&&matches
    }else{false};
    if (project_changed||clicked_current)&&project.is_some() {
        let _=app.emit_to(EventTarget::Webview{label:"main".into()},"project-panel-open",json!({"project_id":project.as_ref().unwrap().id,"clicked_at":clicked_at}));
    }
    drop(recognition);drop(old);
    super::composer_connector::sync(app,&view,&url,project.as_ref());
    Ok(())
}
pub fn monitor(app:&tauri::AppHandle) {
    let handle=app.clone();
    tauri::async_runtime::spawn(async move {
        loop {
            tokio::time::sleep(std::time::Duration::from_millis(900)).await;
            if handle.get_window("main").is_none() {break;}
            let state=handle.state::<WebState>();
            let _gate=state.gate.lock().await;
            let _=sync(&handle).await;
            let _=super::project_details::sync(&handle).await;
            super::classic_language::retry_pending(&handle);
        }
    });
}
#[tauri::command]
pub async fn web_surface(webview:Webview,app:tauri::AppHandle,show:bool,route:Option<String>) -> Result<(),String> {
    require_local(&webview)?;
    screen(&app)?;
    if !show {
        app.state::<WebState>().visible.store(false,Ordering::SeqCst);
        if let Some(v)=app.get_webview("mistral-web") {v.hide().map_err(err)?;}
        write_engine(&app,&json!({"action":"web_context","project":null}))?;
        *app.state::<WebState>().project.lock().map_err(err)?=None;
        let state=app.state::<WebState>();let mut recognition=state.recognition.lock().map_err(err)?;
        recognition.confirmed_url=None;recognition.draft=None;recognition.project_start=None;
        return Ok(());
    }
    let navigate=route.is_some();
    if navigate {let state=app.state::<WebState>();let mut recognition=state.recognition.lock().map_err(err)?;recognition.draft=None;recognition.project_start=None;recognition.confirmed_url=None;recognition.project_page=None;recognition.sidebar_return_pages.clear();}
    let url=if let Some(raw)=route {
        let u=url::Url::parse(&raw).map_err(err)?;
        if projects::parse(&u).is_none()&&projects::conversation_id(&u).is_none() {return Err("Use a Mistral project link".into());}
        u
    } else { "https://chat.mistral.ai/work".parse().unwrap() };
    #[cfg(all(feature="native-smoke",target_os="linux"))]
    let url=if super::smoke::enabled() {"about:blank".parse().unwrap()} else {url};
    if app.get_webview("mistral-web").is_none() {
        let window=app.get_window("main").ok_or("Geen hoofdvenster")?;
        let popup=app.clone();
        let download_navigation=app.clone();
        let builder=tauri::webview::WebviewBuilder::new("mistral-web",WebviewUrl::External("about:blank".parse().unwrap()))
            .data_directory(app.path().app_data_dir().map_err(err)?.join("webview"))
            .disable_drag_drop_handler()
            .initialization_script(include_str!("chat_download_keep.js"))
            .on_download(super::chat_downloads::handle)
            .on_page_load(|view,event|super::classic_language::loaded(view.app_handle(),matches!(event.event(),tauri::webview::PageLoadEvent::Finished)))
            .on_navigation(move |u| {
                // Auth providers and challenge frames may use other HTTPS origins.
                // This entire surface remains unprivileged; only the confirmed
                // Mistral origin is eligible for project detection.
                super::chat_downloads::navigation(&download_navigation,u)
            })
            .on_permission_request(|_,_|tauri::webview::PermissionResponse::Deny)
            .on_new_window(move |u,features| {
                if super::chat_downloads::blob(&u) {return super::chat_downloads::popup(&popup,u,features);}
                if !(u.as_str()=="about:blank" || safe_https(&u)) {return tauri::webview::NewWindowResponse::Deny;}
                match make_login(&popup,u,Some(features)) {
                    Ok(window)=>tauri::webview::NewWindowResponse::Create{window},
                    Err(_)=>tauri::webview::NewWindowResponse::Deny,
                }
            });
        let scale=window.scale_factor().map_err(err)?;
        let size=window.inner_size().map_err(err)?.to_logical::<f64>(scale);
        app.get_window("main").ok_or("Geen hoofdvenster")?.add_child(builder,LogicalPosition::new(0.,54.),LogicalSize::new(size.width.max(1.),(size.height-54.).max(1.))).map_err(err)?;
        #[cfg(target_os="linux")]
        super::project_import::attach_web_hover(&app.get_webview("mistral-web").unwrap());
        super::classic_language::bootstrap(&app,&app.get_webview("mistral-web").unwrap(),url.clone()).await?;
    } else if navigate {
        app.get_webview("mistral-web").unwrap().navigate(url).map_err(err)?;
    }
    #[cfg(all(feature="native-smoke",target_os="linux"))]
    if super::smoke::enabled() {
        use webkit2gtk::WebViewExt;
        app.get_webview("mistral-web").unwrap().with_webview(|platform| {
            platform.inner().load_html(r#"<!doctype html><style>*{box-sizing:border-box}body{margin:0;display:flex;height:100vh;font:16px system-ui;background:#fff;color:#242424}aside{width:245px;background:#f8f7f5;border-right:1px solid #ddd;padding:22px}main{padding:35px;flex:1}h1{font-size:25px}p{margin:24px 0}.input{border:1px solid #ddd;border-radius:12px;padding:20px;margin-top:170px;color:#888}</style><aside><b style='color:#ff5421'>▣ Vibe</b><p>Work　 Code</p><p>＋ Nieuwe chat</p><p>Projecten</p><p>▱ CityTripXL</p><p>Gesprekken</p><p>Voorbeeld van webhistorie</p></aside><main><h1>CityTripXL</h1><p>Dit is uitsluitend een offline proefpagina.</p><div class='input'>Stel je vraag aan Mistral…</div></main>"#,Some("https://chat.mistral.ai/work/projects/cace260d-d95d-4859-b45b-f56f185f15da"));
        }).map_err(err)?;
    }
    app.state::<WebState>().visible.store(true,Ordering::SeqCst);
    app.get_webview("mistral-web").unwrap().show().map_err(err)?;
    super::classic_layout::layout(&app)?;
    write_engine(&app,&json!({"action":"web_hello"}))?;
    Ok(())
}
pub fn resize(app:&tauri::AppHandle) {let _=super::classic_layout::layout(app);}

fn connect_command(mut payload:Value)->Value {
    // Keep Code projects and explicit legacy connector recovery on their
    // existing route. Only verified Work scopes use the embedded Work form.
    let work=payload["connector_reference"].is_null()&&payload["project_id"].as_str().is_some_and(|id|{
        projects::valid_id(id.strip_prefix("chat-").unwrap_or(id))
    });
    if let Some(fields)=payload.as_object_mut() {
        fields.remove("method");
        if work {fields.insert("method".into(),json!("work"));}
    }
    payload
}
#[tauri::command]
pub async fn web_command(webview:Webview,app:tauri::AppHandle,payload:Value) -> Result<(),String> {
    require_local(&webview)?;
    let state=app.state::<WebState>();
    let _gate=state.gate.lock().await;
    sync(&app).await?;
    let action=payload["action"].as_str().ok_or("Geen handeling")?;
    if !matches!(action,"web_hello"|"web_diagnostics"|"web_local_files"|"web_add_folder"|"web_select_folder"|"web_remove_folder"|"web_link"|"web_create_folder"|"web_unlink"|"web_enable"|"web_rotate"|"web_start"|"web_stop"|"web_approve"|"web_connect"|"web_abort"|"web_set_api_key"|"web_goal"|"web_auto_connect") {return Err("Onbekende webhandeling".into());}
    if action=="web_auto_connect"&&(webview.label()!="connector-panel"||!payload["enabled"].is_boolean()) {return Err("Open the project panel".into());}
    if matches!(action,"web_diagnostics"|"web_local_files"|"web_create_folder"|"web_add_folder"|"web_select_folder"|"web_remove_folder")&&webview.label()!="connector-panel" {return Err("Use the project panel to create a folder".into());}
    if matches!(action,"web_local_files"|"web_add_folder"|"web_select_folder"|"web_remove_folder"|"web_link"|"web_create_folder"|"web_unlink"|"web_enable"|"web_rotate"|"web_connect"|"web_abort"|"web_set_api_key"|"web_goal") {
        let p=state.project.lock().map_err(err)?;
        let key=p.as_ref().map(|p|p.id.as_str());
        if key.is_none() || payload["project_id"].as_str()!=key {return Err("The Mistral project changed. Wait for the right project name.".into());}
        if matches!(action,"web_local_files"|"web_add_folder"|"web_select_folder"|"web_remove_folder"|"web_link"|"web_create_folder") {
            let access=state.folder_access.lock().map_err(err)?;
            let choice=state.choice.lock().map_err(err)?;
            authorize_folder_action(access.as_ref(),key.unwrap(),&payload,choice.as_ref())?;
        }
    }
    if action=="web_goal" {
        if webview.label()!="connector-panel" {return Err("Open the project panel".into());}
        let goal=payload["goal"].as_str().ok_or("Enter a short project goal")?;
        if goal.chars().count()>240||goal.chars().any(|c|c.is_control()||c=='\u{2028}'||c=='\u{2029}') {return Err("Use one paragraph of at most 240 characters".into());}
        let request=payload["request_id"].as_str().ok_or("Geen geldig opslagverzoek")?;
        if request.is_empty()||request.len()>80||!request.chars().all(|c|c.is_ascii_alphanumeric()||c=='-') {return Err("Geen geldig opslagverzoek".into());}
    }
    if action=="web_set_api_key" {
        let key=payload["api_key"].as_str().ok_or("Geen geldige Mistral-toegang")?;
        if key.is_empty()||key.len()>4096||key.chars().any(|c|c.is_whitespace()||c.is_control()){return Err("Geen geldige Mistral-toegang".into());}
    }
    if action=="web_connect" {return write_engine(&app,&connect_command(payload));}
    write_engine(&app,&payload)?;
    if matches!(action,"web_link"|"web_add_folder") {*state.choice.lock().map_err(err)?=None;}
    Ok(())
}
#[tauri::command]
pub async fn web_choose_folder(webview:Webview,app:tauri::AppHandle,create:Option<bool>) -> Result<Option<String>,String> {
    require_local(&webview)?;
    let state=app.state::<WebState>();
    let _gate=state.gate.lock().await;
    sync(&app).await?;
    let project=state.project.lock().map_err(err)?.as_ref().map(|p|p.id.clone()).ok_or("Open your Mistral project first")?;
    // Starting another picker invalidates an earlier unused choice, including
    // when this dialog is canceled or fails before returning a new path.
    *state.choice.lock().map_err(err)?=None;
    let create=create.unwrap_or(false);
    if create {authorize_workspace_creation(state.folder_access.lock().map_err(err)?.as_ref(),&project)?;}
    let chosen=app_choose_folder_mode(webview,app.clone(),create).await?;
    sync(&app).await?;
    if state.project.lock().map_err(err)?.as_ref().map(|p|&p.id)!=Some(&project) {return Err("The project changed while choosing a folder. Choose again.".into());}
    // A backend update can bind a root while the native dialog is open.
    if create {authorize_workspace_creation(state.folder_access.lock().map_err(err)?.as_ref(),&project)?;}
    if let Some(ref path)=chosen {*state.choice.lock().map_err(err)?=Some((project,path.clone()));}
    Ok(chosen)
}

#[tauri::command]
pub async fn web_navigate(webview:Webview,app:tauri::AppHandle,destination:String) -> Result<(),String> {
    require_local(&webview)?;
    let view=app.get_webview("mistral-web").ok_or("Mistral is still opening")?;
    if !matches!(destination.as_str(),"home"|"back"|"forward"|"reload"){return Err("Invalid destination".into());}
    {
        let state=app.state::<WebState>();let mut recognition=state.recognition.lock().map_err(err)?;
        recognition.draft=None;recognition.project_start=None;recognition.confirmed_url=None;recognition.project_page=None;recognition.sidebar_return_pages.clear();
    }
    // Native toolbar navigation is not a first-send transition, including a
    // click that returns to the same /work URL in the same SPA document.
    view.eval("window.__vibezLooseConversations?.reset();window.__vibezProjectReturn?.reset();").map_err(err)?;
    match destination.as_str() {
        "home"=>view.navigate("https://chat.mistral.ai/work".parse().unwrap()).map_err(err)?,
        "back"=>view.eval("history.back()").map_err(err)?,
        "forward"=>view.eval("history.forward()").map_err(err)?,
        "reload"=>view.eval("location.reload()").map_err(err)?,
        _=>return Err("Invalid destination".into()),
    }
    Ok(())
}
#[tauri::command]
pub async fn chrome_panel(webview:Webview,app:tauri::AppHandle,mode:String)->Result<(),String> {
    require_local(&webview)?;
    if !matches!(mode.as_str(),"closed"|"files"|"settings"|"language") {return Err("Onbekend paneel".into());}
    app.state::<WebState>().panel.store(mode!="closed",Ordering::SeqCst);
    for label in ["main","connector-panel"] {let _=app.emit_to(EventTarget::Webview{label:label.into()},"chrome-panel",mode.clone());}
    super::classic_layout::layout(&app)?;
    if mode!="closed" {super::project_details::replay(&app)?;write_engine(&app,&json!({"action":"web_hello"}))?;}
    Ok(())
}
#[tauri::command]
pub async fn chrome_snapshot(webview:Webview,app:tauri::AppHandle)->Result<(),String> {
    require_local(&webview)?;
    app.get_webview("mistral-web").ok_or("Mistral has not loaded yet")?;
    // The V3 dialog: visible page, full page or a selection; paste, copy or save.
    super::screenshot_dialog::open(&app).await
}

#[cfg(test)]
mod work_connection_tests {
    use super::*;
    #[test]
    fn normal_work_connect_and_refresh_use_work_but_code_and_legacy_recovery_do_not() {
        let id="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";
        for project in [id.to_owned(),format!("chat-{id}")] {
            let request=connect_command(json!({"action":"web_connect","project_id":project}));
            assert_eq!(request["method"],"work");
            assert_eq!(request["action"],"web_connect");
        }
        let code=connect_command(json!({"action":"web_connect","project_id":format!("code-{id}"),"method":"work"}));
        assert!(code.get("method").is_none());
        let legacy=connect_command(json!({"action":"web_connect","project_id":id,"connector_reference":id}));
        assert!(legacy.get("method").is_none());
    }
}
#[cfg(test)]
mod recognition_tests {
    use super::*;
    fn project(id:&str,name:&str)->projects::Project {projects::Project{id:id.into(),name:name.into(),url:format!("https://chat.mistral.ai/work/projects/{id}"),kind:None,conversation_id:None,draft:None}}
    const A:&str="cace260d-d95d-4859-b45b-f56f185f15da";
    const B:&str="229ee257-1234-4567-890a-123456789abc";
    const CHAT:&str="https://chat.mistral.ai/work/11111111-2222-4333-8444-555555555555";
    #[test] fn project_names_are_confirmed_by_exact_id_and_cached_across_route_transitions() {
        let mut recognition=ProjectRecognition::default();
        let mut work=projects::parse(&format!("https://chat.mistral.ai/work/projects/{A}").parse().unwrap()).unwrap();
        let mut code=projects::parse(&format!("https://chat.mistral.ai/code/{A}").parse().unwrap()).unwrap();
        assert!(!recognition.apply_project_name(&mut work,None));
        assert!(recognition.apply_project_name(&mut work,Some("Work Alpha")));
        assert!(!recognition.apply_project_name(&mut code,None));
        assert!(recognition.apply_project_name(&mut code,Some("Code Beta")));
        assert!(recognition.apply_project_name(&mut work,None));assert_eq!(work.name,"Work Alpha");
        assert!(recognition.apply_project_name(&mut code,None));assert_eq!(code.name,"Code Beta");
        assert!(recognition.apply_project_name(&mut work,Some("Renamed Alpha")));
        assert!(recognition.apply_project_name(&mut work,None));assert_eq!(work.name,"Renamed Alpha");
    }
    #[test] fn missing_project_title_preserves_only_the_same_namespaced_known_title() {
        let mut work=projects::parse(&format!("https://chat.mistral.ai/work/projects/{A}").parse().unwrap()).unwrap();
        let mut code=projects::parse(&format!("https://chat.mistral.ai/code/{A}").parse().unwrap()).unwrap();
        let mut known_work=work.clone();known_work.name="Work project".into();
        let mut known_code=code.clone();known_code.name="Code project".into();
        preserve_known_project_name(&mut work,Some(&known_code));
        preserve_known_project_name(&mut code,Some(&known_work));
        assert_eq!(work.name,projects::fallback_name(A));assert_eq!(code.name,work.name);
        preserve_known_project_name(&mut work,Some(&known_work));
        preserve_known_project_name(&mut code,Some(&known_code));
        assert_eq!(work.name,"Work project");assert_eq!(code.name,"Code project");
        let mut renamed=known_code.clone();renamed.name="Renamed Code project".into();
        preserve_known_project_name(&mut renamed,Some(&known_code));
        assert_eq!(renamed.name,"Renamed Code project");
        let mut unknown=projects::parse(&known_code.url.parse().unwrap()).unwrap();
        preserve_known_project_name(&mut unknown,None);
        assert_eq!(unknown.name,projects::fallback_name(&unknown.id));
    }
    fn project_start_data(project:&projects::Project,sent:bool)->Value {
        let mut value=json!({"project_start":{"document":A,"nonce":B,"project":project.id,"from":project.url,"ready":true,"known":[]}});
        if sent {value["project_start"]["ready"]=json!(false);value["project_start"]["submitted"]=json!({"document":A,"nonce":B,"project":project.id,"from":project.url,"sequence":1,"at":10_000});}
        value
    }
    #[test] fn new_work_project_chat_keeps_its_identity_before_breadcrumb_and_sidebar_render() {
        let mut r=ProjectRecognition::default();let p=project(A,"Fixture project");let overview=p.url.parse().unwrap();let chat=CHAT.parse().unwrap();
        let before=r.context(&overview,None,Some(p.clone()),false,&project_start_data(&p,false),"Conversation",9_000).unwrap();
        let after=r.context(&chat,Some(&before),None,false,&project_start_data(&p,true),"Conversation",10_100);
        assert_eq!(after,Some(p.clone()),"first send must not momentarily select a loose chat and revoke the project connection");
        assert_eq!(r.context(&chat,Some(&p),None,false,&Value::Null,"Conversation",10_200),Some(p));
    }
    #[test] fn project_first_send_never_adopts_unrelated_known_stale_or_untrusted_conversations() {
        for mode in ["not-armed","no-submit","wrong-document","wrong-nonce","wrong-source","wrong-project","wrong-inner-document","wrong-inner-nonce","wrong-inner-source","wrong-inner-project","zero-sequence","expired","future","not-ready","known-link","saved-conversation","known-project-chat","no-previous","other-previous","fresh-other-project","ambiguous","query","fragment","other-host","old-overview"] {
            let mut r=ProjectRecognition::default();let p=project(A,"Original");let other=project(B,"Other");let overview=p.url.parse().unwrap();let mut url:url::Url=CHAT.parse().unwrap();
            let mut ready=project_start_data(&p,false);let mut sent=project_start_data(&p,true);let mut now=10_100;let mut previous=Some(&p);let mut detected=None;let ambiguous=mode=="ambiguous";
            if mode=="known-link"{ready["project_start"]["known"]=json!(["11111111-2222-4333-8444-555555555555"]);}
            if mode!="not-armed"{r.context(&overview,None,Some(p.clone()),false,&ready,"Conversation",9_000);}
            match mode {
                "no-submit"=>sent["project_start"]["submitted"]=Value::Null,
                "wrong-document"=>sent["project_start"]["document"]=json!(B),
                "wrong-nonce"=>sent["project_start"]["nonce"]=json!(A),
                "wrong-source"=>sent["project_start"]["from"]=json!(other.url),
                "wrong-project"=>sent["project_start"]["project"]=json!(B),
                "wrong-inner-document"=>sent["project_start"]["submitted"]["document"]=json!(B),
                "wrong-inner-nonce"=>sent["project_start"]["submitted"]["nonce"]=json!(A),
                "wrong-inner-source"=>sent["project_start"]["submitted"]["from"]=json!(other.url),
                "wrong-inner-project"=>sent["project_start"]["submitted"]["project"]=json!(B),
                "zero-sequence"=>sent["project_start"]["submitted"]["sequence"]=json!(0),
                "expired"=>now=40_001,
                "future"=>sent["project_start"]["submitted"]["at"]=json!(12_000),
                "not-ready"=>sent["project_start"]["ready"]=json!(true),
                "saved-conversation"=>{r.conversations.insert(projects::conversation_id(&url).unwrap(),projects::conversation(&url,None,"Own folder").unwrap());},
                "known-project-chat"=>{r.remember_overview(&other.url.parse().unwrap(),&other,&[CHAT.into()]);},
                "no-previous"=>previous=None,
                "other-previous"=>previous=Some(&other),
                "fresh-other-project"=>detected=Some(other),
                "query"=>url.set_query(Some("unrelated=1")),
                "fragment"=>url.set_fragment(Some("unrelated")),
                "other-host"=>url.set_host(Some("vibe.mistral.ai")).unwrap(),
                "old-overview"=>{r.project_start.as_mut().unwrap().at=0;now=30_001;sent["project_start"]["submitted"]["at"]=json!(30_000);},
                _=>{}
            }
            let result=r.context(&url,previous,detected,ambiguous,&sent,"Conversation",now);
            assert!(!result.is_some_and(|v|v.id==A),"must not inherit project in case {mode}");
            assert!(r.project_start.is_none(),"consume stale proof in case {mode}");
        }
    }
    #[test] fn first_send_proof_is_single_use_and_fresh_project_evidence_still_wins() {
        let mut r=ProjectRecognition::default();let p=project(A,"Original");let overview=p.url.parse().unwrap();let url=CHAT.parse().unwrap();let data=project_start_data(&p,true);
        r.context(&overview,None,Some(p.clone()),false,&project_start_data(&p,false),"Conversation",9_000);
        assert_eq!(r.context(&url,Some(&p),None,false,&data,"Conversation",10_100),Some(p.clone()));
        let other_chat=format!("https://chat.mistral.ai/work/{B}").parse().unwrap();
        assert_ne!(r.context(&other_chat,Some(&p),None,false,&data,"Conversation",10_200).unwrap().id,A);
        let other=project(B,"Moved to another project");
        assert_eq!(r.context(&url,None,Some(other.clone()),false,&Value::Null,"Conversation",10_300),Some(other));
        assert!(!r.chats.contains_key(CHAT));
    }
    #[test] fn unchanged_confirmed_url_survives_empty_breadcrumb_and_modal() {
        let mut r=ProjectRecognition::default();let url=CHAT.parse().unwrap();let p=project(A,"CityTripXL");
        assert_eq!(r.resolve(&url,None,Some(p.clone()),false),Some(p.clone()));
        assert_eq!(r.resolve(&url,Some(&p),None,false),Some(p));
    }
    #[test] fn changed_or_unknown_url_never_inherits_previous_project() {
        for raw in ["https://chat.mistral.ai/work/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "https://chat.mistral.ai/work", "https://chat.mistral.ai/work/11111111-2222-4333-8444-555555555555?new=1", "https://chat.mistral.ai/work/11111111-2222-4333-8444-555555555555#other", "https://evil.test/work/11111111-2222-4333-8444-555555555555"] {
            let mut r=ProjectRecognition::default();let p=project(A,"CityTripXL");let url=CHAT.parse().unwrap();r.resolve(&url,None,Some(p.clone()),false);
            assert_eq!(r.resolve(&raw.parse().unwrap(),Some(&p),None,false),None, "{raw}");
            assert_eq!(r.resolve(&url,Some(&p),None,false),None);
        }
    }
    #[test] fn only_confirmed_project_overview_can_associate_visible_chat_links() {
        let p=project(A,"CityTripXL");let overview=p.url.parse().unwrap();let url=CHAT.parse().unwrap();
        let mut r=ProjectRecognition::default();r.remember_overview(&url,&p,&[CHAT.into()]);assert_eq!(r.resolve(&url,None,None,false),None);
        r.remember_overview(&overview,&project(B,"Other"),&[CHAT.into()]);assert_eq!(r.resolve(&url,None,None,false),None);
        r.remember_overview(&overview,&p,&[CHAT.into(),"https://evil.test/work/11111111-2222-4333-8444-555555555555".into()]);
        assert_eq!(r.resolve(&url,None,None,false),Some(p.clone()));
        assert_eq!(r.resolve(&format!("{CHAT}?tab=files#view").parse().unwrap(),None,None,false),Some(p));
    }
    #[test] fn fresh_different_project_or_ambiguity_defeats_old_association() {
        let a=project(A,"CityTripXL");let b=project(B,"Other");let url=CHAT.parse().unwrap();
        let mut r=ProjectRecognition::default();r.remember_overview(&a.url.parse().unwrap(),&a,&[CHAT.into()]);
        assert_eq!(r.resolve(&url,None,Some(b.clone()),false),Some(b.clone()));
        assert_eq!(r.resolve(&url,Some(&b),None,false),Some(b));
        assert!(!r.chats.contains_key(CHAT));
        r.remember_overview(&a.url.parse().unwrap(),&a,&[CHAT.into()]);
        assert_eq!(r.resolve(&url,Some(&a),None,true),None);
        assert_eq!(r.resolve(&url,Some(&a),None,false),None);
    }
    #[test] fn remembered_links_use_only_exact_mistral_chat_routes_and_stay_bounded() {
        for route in ["/work/11111111-2222-4333-8444-555555555555", "/work/chat/11111111-2222-4333-8444-555555555555/", "/work/chats/11111111-2222-4333-8444-555555555555", "/work/c/11111111-2222-4333-8444-555555555555"] {
            assert!(ProjectRecognition::chat_url(&format!("https://chat.mistral.ai{route}").parse().unwrap()).is_some());
        }
        for raw in ["https://chat.mistral.ai/work/projects/cace260d-d95d-4859-b45b-f56f185f15da", "https://chat.mistral.ai/work/settings", "https://chat.mistral.ai/work/chat/11111111-2222-4333-8444-555555555555/other", "https://evil.test/work/11111111-2222-4333-8444-555555555555"] {assert!(ProjectRecognition::chat_url(&raw.parse().unwrap()).is_none());}
        let p=project(A,"CityTripXL");let mut r=ProjectRecognition::default();
        for batch in 0..6 {let links=(0..64).map(|n|format!("https://chat.mistral.ai/work/{:08x}-2222-4333-8444-555555555555",batch*64+n)).collect::<Vec<_>>();r.remember_overview(&p.url.parse().unwrap(),&p,&links);}
        assert_eq!(r.chats.len(),256);assert_eq!(r.order.len(),256);
    }
    #[test] fn code_and_work_switches_use_explicit_route_identity_and_unknown_code_pauses() {
        let mut r=ProjectRecognition::default();let work=project(A,"Work project");
        let overview:url::Url=format!("https://chat.mistral.ai/code/{A}").parse().unwrap();
        let session:url::Url=format!("https://chat.mistral.ai/code/{A}/{B}").parse().unwrap();
        let code=projects::parse(&overview).unwrap();
        assert_eq!(r.resolve(&work.url.parse().unwrap(),None,Some(work.clone()),false),Some(work.clone()));
        assert_eq!(r.resolve(&overview,Some(&work),Some(code.clone()),false),Some(code.clone()));
        for suffix in [format!("draft%3Asession%3A{B}"),format!("draft:session:{B}")] {
            let draft:url::Url=format!("https://chat.mistral.ai/code/{A}/{suffix}").parse().unwrap();
            assert_eq!(r.resolve(&draft,Some(&code),projects::parse(&draft),false),Some(code.clone()));
        }
        assert_eq!(r.resolve(&session,Some(&code),projects::parse(&session),false),Some(code.clone()));
        assert_eq!(r.resolve(&session,Some(&code),None,false),Some(code.clone()));
        for route in ["/code/extensions","/code/settings","/code/new","/code"] {
            assert_eq!(r.resolve(&format!("https://chat.mistral.ai{route}").parse().unwrap(),Some(&code),None,false),None);
        }
        // Neither a Code overview nor a session may associate an unrelated Work chat.
        r.remember_overview(&overview,&code,&[CHAT.into()]);r.remember_overview(&session,&code,&[CHAT.into()]);
        assert_eq!(r.resolve(&CHAT.parse().unwrap(),Some(&code),None,false),None);
        assert_eq!(r.resolve(&work.url.parse().unwrap(),Some(&code),Some(work.clone()),false),Some(work));
    }
    fn removal_proof(from:&str)->Value {json!({"project_return":{"project":A,"from":from,"chat":"11111111-2222-4333-8444-555555555555","at":10_000,"reason":"removed_project_chat"}})}
    #[test] fn removed_chat_returns_only_to_the_previously_confirmed_work_project() {
        for source in [CHAT, &format!("https://chat.mistral.ai/work/projects/{A}")] {
            let mut r=ProjectRecognition::default();let p=project(A,"Fixture project");let from=source.parse().unwrap();let home="https://chat.mistral.ai/work".parse().unwrap();
            r.remember_project_page(&from,Some(&p),&[CHAT.into()],10_000);
            assert_eq!(r.removed_chat_return(&home,&removal_proof(source),10_100).unwrap().as_str(),p.url);
            assert!(r.removed_chat_return(&home,&removal_proof(source),10_100).is_none(),"consumed once");
            assert!(r.context(&home,None,None,false,&loose_data(false),"New",10_101).unwrap().id.starts_with("chat-"),"home never inherits the project map");
        }
    }
    #[test] fn removed_chat_return_rejects_unknown_cross_project_stale_and_non_home_requests() {
        for mode in ["unknown","other-project","other-source","other-chat","expired","future","missing-action","wrong-route","cross-host","native-reset","loose-chat","code"] {
            let mut r=ProjectRecognition::default();let mut p=project(A,"Project");let mut url:url::Url="https://chat.mistral.ai/work".parse().unwrap();let from=CHAT.parse().unwrap();let mut proof=removal_proof(CHAT);let mut now=10_100;
            if mode=="loose-chat"{p=projects::conversation(&from,None,"Loose").unwrap();}
            if mode=="code"{p=projects::parse(&format!("https://chat.mistral.ai/code/{A}").parse().unwrap()).unwrap();}
            if mode!="unknown"{r.remember_project_page(&from,Some(&p),&[],10_000);}
            match mode {
                "other-project"=>proof["project_return"]["project"]=json!(B),
                "other-source"=>proof["project_return"]["from"]=json!("https://chat.mistral.ai/work/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
                "other-chat"=>proof["project_return"]["chat"]=json!(B),
                "expired"=>now=41_000,
                "future"=>proof["project_return"]["at"]=json!(12_000),
                "missing-action"=>proof["project_return"]["reason"]=json!("new_chat"),
                "wrong-route"=>url=CHAT.parse().unwrap(),
                "cross-host"=>url="https://vibe.mistral.ai/work".parse().unwrap(),
                "native-reset"=>r.project_page=None,
                _=>{}
            }
            assert!(r.removed_chat_return(&url,&proof,now).is_none(),"{mode}");
        }
    }
    #[test] fn removed_chat_return_survives_an_intermediate_home_snapshot_but_not_another_project() {
        let mut r=ProjectRecognition::default();let p=project(A,"Fixture");let from=CHAT.parse().unwrap();let home="https://chat.mistral.ai/work".parse().unwrap();
        r.remember_project_page(&from,Some(&p),&[],10_000);
        let loose=r.context(&home,Some(&p),None,false,&loose_data(false),"New",10_100).unwrap();
        r.remember_project_page(&home,Some(&loose),&[],10_100);
        assert!(r.removed_chat_return(&home,&removal_proof(CHAT),10_200).is_some());
        r.remember_project_page(&from,Some(&p),&[],10_000);
        let other=project(B,"Other");r.remember_project_page(&other.url.parse().unwrap(),Some(&other),&[],10_100);
        assert!(r.removed_chat_return(&home,&removal_proof(CHAT),10_200).is_none());
    }

    #[test] fn removed_chat_missing_page_returns_and_forgets_all_stale_url_aliases() {
        let mut r=ProjectRecognition::default();let p=project(A,"Project");let url=CHAT.parse().unwrap();
        let deleted=vec![CHAT.to_string(),"https://chat.mistral.ai/work/chat/11111111-2222-4333-8444-555555555555".into(),format!("https://chat.mistral.ai/work/{B}")];
        r.remember_overview(&p.url.parse().unwrap(),&p,&deleted);r.remember_project_page(&url,Some(&p),&[],10_000);
        let mut proof=removal_proof(CHAT);proof["project_return"]["reason"]=json!("missing_project_chat");
        assert_eq!(r.removed_chat_return(&url,&proof,10_100).unwrap().as_str(),p.url);
        assert!(!r.chats.contains_key(CHAT));assert!(!r.chats.contains_key(&deleted[1]));assert!(r.chats.contains_key(&deleted[2]));
        assert_eq!(r.order.len(),1);assert!(r.removed_chat_return(&url,&proof,10_200).is_none());
        assert!(r.resolve(&url,None,None,false).is_none());
    }
    #[test] fn removed_chat_missing_page_never_redirects_another_chat_or_ambiguous_context() {
        let p=project(A,"Project");let from=CHAT.parse().unwrap();let mut proof=removal_proof(CHAT);proof["project_return"]["reason"]=json!("missing_project_chat");
        for raw in ["https://chat.mistral.ai/work", "https://chat.mistral.ai/work/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "https://evil.test/work/11111111-2222-4333-8444-555555555555"] {
            let mut r=ProjectRecognition::default();r.remember_project_page(&from,Some(&p),&[],10_000);
            assert!(r.removed_chat_return(&raw.parse().unwrap(),&proof,10_100).is_none());
        }
        let mut r=ProjectRecognition::default();r.remember_project_page(&from,Some(&p),&[],10_000);proof["ambiguous"]=json!(true);
        assert!(r.removed_chat_return(&from,&proof,10_100).is_none());
    }

    #[test] fn removed_sidebar_chat_can_be_another_conversation_in_the_same_project() {
        let mut r=ProjectRecognition::default();let p=project(A,"Project");let source=format!("https://chat.mistral.ai/work/{B}");let url=source.parse().unwrap();let home="https://chat.mistral.ai/work".parse().unwrap();
        r.remember_project_page(&url,Some(&p),&[CHAT.into()],10_000);
        // The deleted row vanishes while the previously opened chat remains.
        r.remember_project_page(&url,Some(&p),&[],10_100);
        assert_eq!(r.removed_chat_return(&home,&removal_proof(&source),10_200).unwrap().as_str(),p.url);
    }
    #[test] fn removed_sidebar_parent_is_explicit_even_when_home_or_another_project_was_open() {
        let p=project(A,"Target project");
        let data=json!({"sidebar_return_projects":[{"id":A,"name":"Target project","url":p.url,"chats":[CHAT]}]});
        for raw in ["https://chat.mistral.ai/work".to_owned(),format!("https://chat.mistral.ai/work/projects/{B}"),format!("https://chat.mistral.ai/work/{B}")] {
            let mut r=ProjectRecognition::default();let source=raw.parse().unwrap();let home="https://chat.mistral.ai/work".parse().unwrap();r.remember_sidebar_returns(&source,&data,10_000);
            let mut empty=data.clone();empty["sidebar_return_projects"][0]["chats"]=json!([]);r.remember_sidebar_returns(&source,&empty,10_100);
            assert_eq!(r.removed_chat_return(&home,&removal_proof(&raw),10_200).unwrap().as_str(),p.url);
        }
    }
    #[test] fn sidebar_return_evidence_is_bounded_and_rejects_other_origins_and_wrong_parents() {
        let mut r=ProjectRecognition::default();let source=CHAT.parse().unwrap();let home="https://chat.mistral.ai/work".parse().unwrap();
        let data=json!({"sidebar_return_projects":[{"id":A,"url":format!("https://evil.test/work/projects/{A}"),"chats":[CHAT]},{"id":A,"url":format!("https://chat.mistral.ai/work/projects/{B}"),"chats":[CHAT]}]});
        r.remember_sidebar_returns(&source,&data,10_000);assert!(r.sidebar_return_pages.is_empty());assert!(r.removed_chat_return(&home,&removal_proof(CHAT),10_100).is_none());
        let p=project(A,"Project");let data=json!({"sidebar_return_projects":[{"id":A,"url":p.url,"chats":[CHAT]}]});r.remember_sidebar_returns(&source,&data,10_000);
        assert!(r.removed_chat_return(&home,&removal_proof(CHAT),41_000).is_none());
        r.remember_sidebar_returns(&"https://chat.mistral.ai/auth/callback?credential=private".parse().unwrap(),&data,41_000);assert!(r.sidebar_return_pages.is_empty());
    }
    #[test] fn navigation_diagnostics_contain_only_phase_flags_not_hosted_page_content() {
        let data=json!({"navigation_trace":{"armed":true,"chosen":true,"confirmed":"secret-token","owner_known":false,"return_ready":false,"url":"private-url","folder":"private-folder","message":"private-chat"},"token":"private-token"});
        let trace=navigation_trace(&format!("https://chat.mistral.ai/work/{B}?private-url").parse().unwrap(),&data,false,true,false);
        assert_eq!(trace["armed"],true);assert_eq!(trace["confirmed"],false);assert_eq!(trace["route"],"conversation");assert!(!trace.to_string().contains("private"));assert!(!trace.to_string().contains("secret"));
    }

    fn loose_data(submitted:bool)->Value {
        let mut value=json!({"conversation_name":"A loose chat","loose":{"document":A,"nonce":B,"ready":true,"known":[]}});
        if submitted{value["loose"]["submitted"]=json!({"document":A,"nonce":B,"sequence":1,"at":10_000,"from":"https://chat.mistral.ai/work"});}
        value
    }
    #[test] fn saved_loose_chats_never_replace_explicit_or_verified_project_associations() {
        let url=CHAT.parse().unwrap();let p=project(A,"Project map");let mut r=ProjectRecognition::default();
        r.remember_overview(&p.url.parse().unwrap(),&p,&[CHAT.into()]);
        assert_eq!(r.context(&url,None,None,false,&loose_data(false),"New conversation",10_001),Some(p.clone()));
        let different=project(B,"Another project");assert_eq!(r.context(&url,Some(&p),Some(different.clone()),false,&loose_data(true),"New",10_001),Some(different));
        assert!(r.context(&url,None,None,true,&loose_data(true),"New",10_001).is_none());
        let mut r=ProjectRecognition::default();let loose=r.context(&url,Some(&p),None,false,&loose_data(false),"New",10_001).unwrap();
        assert_eq!(loose.id,"chat-11111111-2222-4333-8444-555555555555");assert_eq!(loose.kind.as_deref(),Some("conversation"));assert_ne!(loose.id,p.id);
    }
    #[test] fn draft_to_first_sent_chat_preserves_only_its_same_native_local_identity() {
        let home="https://chat.mistral.ai/work".parse().unwrap();let url=CHAT.parse().unwrap();let mut r=ProjectRecognition::default();
        let draft=r.context(&home,None,None,false,&loose_data(false),"New conversation",10_000).unwrap();
        assert_eq!(draft.draft,Some(true));assert!(projects::valid_id(draft.id.strip_prefix("chat-").unwrap()));
        assert_eq!(r.context(&home,Some(&draft),None,false,&loose_data(false),"New",10_000).unwrap().id,draft.id);
        let mut first=loose_data(true);first["loose"]["ready"]=json!(false);
        let saved=r.context(&url,Some(&draft),None,false,&first,"New",10_100).unwrap();
        assert_eq!(saved.id,draft.id);assert_eq!(saved.draft,Some(false));assert_eq!(saved.conversation_id.as_deref(),Some("11111111-2222-4333-8444-555555555555"));assert_eq!(saved.url,CHAT);
        // An older backend snapshot may arrive before the promotion acknowledgment.
        // The exact same actual conversation still retains its proven local ID.
        r.observe_conversations(&json!({"type":"web_connector","projects":[]}));
        assert_eq!(r.context(&format!("{CHAT}?tab=files").parse().unwrap(),Some(&saved),None,false,&Value::Null,"New",10_200).unwrap().id,draft.id);
    }
    #[test] fn a_new_home_nonce_rotates_the_draft_and_no_orphan_or_last_project_is_inherited() {
        let home="https://chat.mistral.ai/work".parse().unwrap();let mut r=ProjectRecognition::default();let old=project(A,"Must not inherit");
        let draft=r.context(&home,Some(&old),None,false,&loose_data(false),"New",10_000).unwrap();assert_ne!(draft.id,old.id);
        let mut changed=loose_data(false);changed["loose"]["nonce"]=json!("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee");
        let new=r.context(&home,Some(&draft),None,false,&changed,"New",10_000).unwrap();assert_ne!(new.id,draft.id);
        r.observe_conversations(&json!({"type":"web_connector","projects":[draft]}));assert!(r.conversations.is_empty());
        assert!(r.context(&home,Some(&new),None,false,&Value::Null,"New",10_000).is_none());
    }
    #[test] fn history_click_missing_or_stale_submit_and_other_document_never_promote_a_draft_map() {
        let home="https://chat.mistral.ai/work".parse().unwrap();let url=CHAT.parse().unwrap();
        for mode in ["missing","document","nonce","old","future","wrong-source","known-history"] {
            let mut r=ProjectRecognition::default();let mut initial=loose_data(false);
            if mode=="known-history"{initial["loose"]["known"]=json!(["11111111-2222-4333-8444-555555555555"]);}
            let draft=r.context(&home,None,None,false,&initial,"New",10_000).unwrap();let mut next=loose_data(true);
            match mode {
                "missing"=>next["loose"]["submitted"]=Value::Null,
                "document"=>next["loose"]["document"]=json!(B),
                "nonce"=>next["loose"]["submitted"]["nonce"]=json!(A),
                "old"=>next["loose"]["submitted"]["at"]=json!(0),
                "future"=>next["loose"]["submitted"]["at"]=json!(90_000),
                "wrong-source"=>next["loose"]["submitted"]["from"]=json!("https://evil.test/work"),
                _=>{},
            }
            let now=if mode=="old"{50_000}else{10_100};
            let saved=r.context(&url,Some(&draft),None,false,&next,"New",now).unwrap();assert_ne!(saved.id,draft.id,"{mode}");
        }
    }
    #[test] fn only_valid_non_draft_backend_aliases_survive_restart_and_conflicts_fail_closed() {
        let url=CHAT.parse().unwrap();let local=format!("chat-{A}");let mut r=ProjectRecognition::default();
        let saved=projects::conversation(&url,Some(&local),"Saved name").unwrap();
        r.observe_conversations(&json!({"type":"web_connector","projects":[saved]}));
        assert_eq!(r.context(&url,None,None,false,&Value::Null,"New",10_000).unwrap().id,local);
        let mut other=projects::conversation(&url,Some(&format!("chat-{B}")),"Conflicting").unwrap();
        r.observe_conversations(&json!({"type":"web_connector","projects":[saved,other]}));assert!(r.conversations.is_empty());
        other.draft=Some(true);r.observe_conversations(&json!({"type":"web_connector","projects":[other]}));assert!(r.conversations.is_empty());
    }
    #[test] fn pending_first_send_alias_survives_older_snapshot_and_a_different_chat_until_acknowledged() {
        let home="https://chat.mistral.ai/work".parse().unwrap();let url=CHAT.parse().unwrap();let other_url=format!("https://chat.mistral.ai/work/{B}").parse().unwrap();
        let mut r=ProjectRecognition::default();
        let draft=r.context(&home,None,None,false,&loose_data(false),"New",10_000).unwrap();
        let saved=r.context(&url,Some(&draft),None,false,&loose_data(true),"Conversation",10_100).unwrap();
        r.observe_conversations(&json!({"type":"web_connector","projects":[]}));
        let other=r.context(&other_url,Some(&saved),None,false,&Value::Null,"Conversation",10_200).unwrap();
        let back=r.context(&url,Some(&other),None,false,&Value::Null,"Conversation",10_300).unwrap();
        assert_eq!(back.id,draft.id);assert_eq!(r.pending_promotions.len(),1);
        r.observe_conversations(&json!({"type":"web_connector","projects":[saved]}));
        assert!(r.pending_promotions.is_empty());assert!(r.pending_order.is_empty());assert_eq!(r.conversations.len(),1);
        // After an acknowledgment, a real unlink must remove the alias. A
        // pending record must not resurrect the old ID when this chat is revisited.
        r.observe_conversations(&json!({"type":"web_connector","projects":[]}));
        let other=r.context(&other_url,Some(&back),None,false,&Value::Null,"Conversation",10_400).unwrap();
        let unlinked=r.context(&url,Some(&other),None,false,&Value::Null,"Conversation",10_500).unwrap();
        assert_eq!(unlinked.id,"chat-11111111-2222-4333-8444-555555555555");assert_ne!(unlinked.id,draft.id);
    }
    #[test] fn contradictory_saved_alias_does_not_select_another_folder_after_a_first_send() {
        let home="https://chat.mistral.ai/work".parse().unwrap();let url=CHAT.parse().unwrap();let mut r=ProjectRecognition::default();
        let draft=r.context(&home,None,None,false,&loose_data(false),"New",10_000).unwrap();
        let saved=r.context(&url,Some(&draft),None,false,&loose_data(true),"Conversation",10_100).unwrap();
        let contradictory=projects::conversation(&url,Some(&format!("chat-{B}")),"Different binding").unwrap();
        r.observe_conversations(&json!({"type":"web_connector","projects":[contradictory]}));
        assert!(r.pending_promotions.is_empty());assert!(r.conversations.is_empty());
        assert!(r.context(&url,Some(&saved),None,false,&Value::Null,"Conversation",10_200).is_none());
    }
    #[test] fn pending_promotions_remain_bounded_without_backend_acknowledgments() {
        let home="https://chat.mistral.ai/work".parse().unwrap();let mut r=ProjectRecognition::default();
        for n in 0..40 {
            let draft=r.context(&home,None,None,false,&loose_data(false),"New",10_000).unwrap();
            let url=format!("https://chat.mistral.ai/work/{n:08x}-2222-4333-8444-555555555555").parse().unwrap();
            assert_eq!(r.context(&url,Some(&draft),None,false,&loose_data(true),"Conversation",10_100).unwrap().id,draft.id);
        }
        assert_eq!(r.pending_promotions.len(),32);assert_eq!(r.pending_order.len(),32);
    }
    #[test] fn sequenced_snapshots_preserve_pending_ack_and_unlink_against_late_older_events() {
        let home="https://chat.mistral.ai/work".parse().unwrap();let url=CHAT.parse().unwrap();let mut r=ProjectRecognition::default();
        assert!(r.observe_event(&json!({"type":"web_connector","snapshot_sequence":1,"projects":[]})));
        let draft=r.context(&home,None,None,false,&loose_data(false),"New",10_000).unwrap();
        let saved=r.context(&url,Some(&draft),None,false,&loose_data(true),"Conversation",10_100).unwrap();
        assert!(!r.observe_event(&json!({"type":"web_connector","snapshot_sequence":1,"projects":[]})));assert_eq!(r.pending_promotions.len(),1);
        let acknowledgment=json!({"type":"web_connector","snapshot_sequence":3,"projects":[saved]});
        assert!(r.observe_event(&acknowledgment));assert!(r.pending_promotions.is_empty());assert_eq!(r.conversations.len(),1);
        assert!(!r.observe_event(&json!({"type":"web_connector","snapshot_sequence":2,"projects":[]})));assert_eq!(r.conversations.len(),1);
        assert!(r.observe_event(&json!({"type":"web_connector","snapshot_sequence":4,"projects":[]})));assert!(r.conversations.is_empty());
        assert!(!r.observe_event(&acknowledgment));assert!(r.conversations.is_empty());assert!(r.pending_promotions.is_empty());
    }
    #[test] fn legacy_snapshots_work_only_before_the_first_positive_sequence_and_other_events_pass() {
        let mut r=ProjectRecognition::default();let legacy=json!({"type":"web_connector","projects":[]});
        assert!(r.accept_snapshot(&legacy));assert!(r.accept_snapshot(&legacy));
        for invalid in [json!(0),json!(-1),json!(1.5),json!("1"),Value::Null,json!(true)] {assert!(!r.accept_snapshot(&json!({"type":"web_connector","snapshot_sequence":invalid})));}
        assert!(r.accept_snapshot(&json!({"type":"web_connector","snapshot_sequence":5})));
        assert!(!r.accept_snapshot(&legacy));assert!(!r.accept_snapshot(&json!({"type":"web_connector","snapshot_sequence":5})));assert!(!r.accept_snapshot(&json!({"type":"web_connector","snapshot_sequence":4})));
        assert!(r.accept_snapshot(&json!({"type":"web_auto","snapshot_sequence":1})));assert_eq!(r.snapshot_sequence,Some(5));
        assert!(r.accept_snapshot(&json!({"type":"web_connector","snapshot_sequence":6})));
    }
    fn folders_event()->Value {
        json!({"type":"web_connector","project":{"id":A},"workspace_binding":"a".repeat(64),"target_folder_id":"1".repeat(32),
            "folders":[{"id":"1".repeat(32),"path":"/fixtures/Alpha","alias":"Alpha"}],
            "token":"private-token-never-retained"})
    }
    #[test] fn folder_mutation_cache_accepts_bounded_roots_and_retains_no_paths_or_tokens() {
        let event=folders_event();let current=folder_access_snapshot(&event).unwrap();
        assert_eq!(current.project,A);assert_eq!(current.ids.len(),1);assert_eq!(current.binding,Some("a".repeat(64)));
        let shown=format!("{current:?}");assert!(!shown.contains("/fixtures/"));assert!(!shown.contains("private-token"));assert!(!shown.contains("Alpha"));
        for (field,value) in [("workspace_binding",json!("invalid")),("workspace_binding",Value::Null),("target_folder_id",json!("3".repeat(32))),("folders",Value::Null),("folders",json!([{"id":"1".repeat(32)},{"id":"1".repeat(32)}])),("folders",json!([{"id":"Z".repeat(32)}]))] {
            let mut invalid=event.clone();invalid[field]=value;assert!(folder_access_snapshot(&invalid).is_none());
        }
    }
    #[test] fn replacing_one_root_requires_native_picker_proof_and_the_exact_current_binding() {
        let current=folder_access_snapshot(&folders_event()).unwrap();let choice=(A.to_owned(),"/fixtures/Chosen".to_owned());
        let replace=json!({"action":"web_link","workspace_binding":"a".repeat(64),"path":"/fixtures/Chosen","folder_id":"1".repeat(32)});
        assert!(authorize_folder_action(Some(&current),A,&replace,Some(&choice)).is_ok());
        assert!(authorize_folder_action(Some(&current),A,&replace,None).is_err());
        assert!(authorize_folder_action(Some(&current),B,&replace,Some(&choice)).is_err());
        assert!(authorize_folder_action(None,A,&replace,Some(&choice)).is_err());
        for (field,value) in [("workspace_binding",json!("b".repeat(64))),("workspace_binding",Value::Null),("path",json!("/fixtures/Unchosen")),("folder_id",json!("2".repeat(32)))] {
            let mut invalid=replace.clone();invalid[field]=value;assert!(authorize_folder_action(Some(&current),A,&invalid,Some(&choice)).is_err());
        }
        for action in ["web_add_folder","web_select_folder","web_remove_folder"] {
            let mut valid=replace.clone();valid["action"]=json!(action);assert!(authorize_folder_action(Some(&current),A,&valid,Some(&choice)).is_ok());
        }
    }
    #[test] fn main_folder_creation_requires_a_known_unlinked_current_project_or_chat() {
        for id in [A.to_owned(),format!("code-{A}"),format!("chat-{A}")] {
            let event=json!({"type":"web_connector","project":{"id":id},"folders":[],"workspace_binding":null,"target_folder_id":null});
            let access=folder_access_snapshot(&event).unwrap();
            assert!(authorize_workspace_creation(Some(&access),&id).is_ok());
            assert!(authorize_workspace_creation(Some(&access),B).is_err());
        }
        assert!(authorize_workspace_creation(None,A).is_err());
        let bound=folder_access_snapshot(&folders_event()).unwrap();
        assert!(authorize_workspace_creation(Some(&bound),A).is_err());
        // A legacy snapshot does not prove whether its single root exists.
        for folder in [Value::Null,json!("/fixtures/Existing")] {
            let legacy=folder_access_snapshot(&json!({"type":"web_connector","project":{"id":A},"folder":folder})).unwrap();
            assert!(authorize_workspace_creation(Some(&legacy),A).is_err());
        }
    }
    #[test] fn subfolder_creation_requires_current_single_root_name_and_bounded_correlation_id() {
        let current=folder_access_snapshot(&folders_event()).unwrap();
        let create=json!({"action":"web_create_folder","project_id":A,"workspace_binding":"a".repeat(64),"request_id":"new-folder-123","name":"Reis plannen"});
        assert!(authorize_folder_action(Some(&current),A,&create,None).is_ok());
        assert!(authorize_folder_action(Some(&current),B,&create,None).is_err());
        assert!(authorize_folder_action(None,A,&create,None).is_err());
        for (field,value) in [("project_id",json!(B)),("project_id",Value::Null),("workspace_binding",json!("b".repeat(64))),("workspace_binding",Value::Null),("name",json!("../escape")),("name",json!("/outside")),("name",json!("nested/child")),("name",json!("nested\\child")),("name",json!(".hidden")),("name",json!(" name")),("name",json!("name ")),("name",json!("name\n")),("name",json!("")),("name",json!("x".repeat(256))),("name",json!("é".repeat(128))),("name",Value::Null),("request_id",Value::Null),("request_id",json!("")),("request_id",json!("x".repeat(81))),("request_id",json!("bad/id")),("path",json!("/outside")),("folder_id",json!("1".repeat(32))),("unknown",json!(true))] {
            let mut invalid=create.clone();invalid[field]=value;assert!(authorize_folder_action(Some(&current),A,&invalid,None).is_err(),"{field}: {invalid}");
        }
        for name in ["Documenten", "Foto’s 2026", "日本語", "CON", "x.y"] {let mut valid=create.clone();valid["name"]=json!(name);assert!(authorize_folder_action(Some(&current),A,&valid,None).is_ok());}
        let mut empty=folders_event();empty["folders"]=json!([]);empty["workspace_binding"]=Value::Null;empty["target_folder_id"]=Value::Null;
        assert!(authorize_folder_action(folder_access_snapshot(&empty).as_ref(),A,&create,None).is_err());
    }
    #[test] fn first_binding_and_legacy_single_root_keep_only_the_original_picker_action() {
        let choice=(A.to_owned(),"/fixtures/Chosen".to_owned());let request=json!({"action":"web_link","path":"/fixtures/Chosen"});
        for event in [json!({"type":"web_connector","project":{"id":A},"folder":null}),json!({"type":"web_connector","project":{"id":A},"folder":"/fixtures/Old"}),json!({"type":"web_connector","project":{"id":A},"folder":null,"folders":[],"workspace_binding":null,"target_folder_id":null})] {
            let access=folder_access_snapshot(&event).unwrap();assert!(authorize_folder_action(Some(&access),A,&request,Some(&choice)).is_ok());
            for action in ["web_add_folder","web_select_folder","web_remove_folder","web_create_folder"] {let mut invalid=request.clone();invalid["action"]=json!(action);assert!(authorize_folder_action(Some(&access),A,&invalid,Some(&choice)).is_err());}
        }
        let access=folder_access_snapshot(&folders_event()).unwrap();assert!(authorize_folder_action(Some(&access),A,&request,Some(&choice)).is_err());
        let mut updated=request;updated["workspace_binding"]=json!("a".repeat(64));assert!(authorize_folder_action(Some(&access),A,&updated,Some(&choice)).is_ok());
    }

}

#[cfg(test)]mod download_scope_tests {
    use super::*;
    #[test]fn download_directory_uses_only_the_current_confirmed_route_or_its_provisional_attachment(){
        let a="https://chat.mistral.ai/work/projects/cace260d-d95d-4859-b45b-f56f185f15da";
        let b:url::Url="https://chat.mistral.ai/code/01a0296a-296a-748f-aba4-6dc79fa08bc2".parse().unwrap();
        let attachment:url::Url="https://files.example/attachment.docx".parse().unwrap();
        assert!(download_route_matches(Some(a),&a.parse().unwrap(),&attachment));
        assert!(download_route_matches(Some(a),&attachment,&attachment));
        assert!(!download_route_matches(Some(a),&b,&attachment));
        assert!(!download_route_matches(None,&b,&attachment));
        assert!(!download_route_matches(Some("https://evil.test/work"),&attachment,&attachment));
    }
}
