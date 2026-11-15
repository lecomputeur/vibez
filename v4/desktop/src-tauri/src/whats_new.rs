//! "What's new" after an update: the changes of every version between the one
//! this installation last showed and the running one, from the changelog that
//! is built into the app. A fresh installation records its version without
//! showing anything. The last shown version is stored next to the language.
use super::*;
const CHANGELOG:&str=include_str!("changelog.json");
/// The last version without this record; an existing profile without it updated from there.
const BEFORE_RECORD:&str="4.0.0-beta.3";

/// 4.0.0-beta.3 -> (4,0,0,stage,3); alpha < beta < rc < final.
fn order(version:&str)->Option<(u64,u64,u64,u8,u64)> {
    let (core,pre)=version.split_once('-').map_or((version,None),|(c,p)|(c,Some(p)));
    let mut parts=core.split('.').map(|p|p.parse::<u64>().ok());
    let (major,minor,patch)=(parts.next()??,parts.next()??,parts.next()??);
    if parts.next().is_some() {return None;}
    let (stage,number)=match pre {
        None=>(3,0),
        Some(pre)=>{
            let (name,number)=pre.split_once('.')?;
            (match name {"alpha"=>0,"beta"=>1,"rc"=>2,_=>return None},number.parse().ok()?)
        }
    };
    Some((major,minor,patch,stage,number))
}

fn entries()->Vec<Value> {
    serde_json::from_str::<Value>(CHANGELOG).ok().and_then(|v|v["versions"].as_array().cloned()).unwrap_or_default()
        .into_iter().filter(|e|e["version"].as_str().and_then(order).is_some()&&e["changes"].is_array()).collect()
}

/// Entries newer than `after` (all when None) up to and including `current`, newest first.
fn between(all:&[Value],after:Option<&str>,current:&str)->Vec<Value> {
    let (low,high)=(after.and_then(order),order(current));
    let mut out:Vec<Value>=all.iter().filter(|e|{
        let v=e["version"].as_str().and_then(order);
        v.is_some()&&low.is_none_or(|low|v>Some(low))&&high.is_some_and(|high|v<=Some(high))
    }).cloned().collect();
    out.sort_by(|a,b|a["version"].as_str().and_then(order).cmp(&b["version"].as_str().and_then(order)).reverse());
    out
}

pub struct WhatsNew {file:std::path::PathBuf,previous:Mutex<Option<String>>}
impl WhatsNew {
    /// `existing` says whether this profile was used before (it then updated from an older build).
    pub fn load(config:&std::path::Path,existing:bool)->Self {
        let file=config.join("whats-new.json");
        let stored=std::fs::read(&file).ok().filter(|raw|raw.len()<=4096)
            .and_then(|raw|serde_json::from_slice::<Value>(&raw).ok())
            .and_then(|v|v["last_shown"].as_str().filter(|s|order(s).is_some()).map(str::to_owned));
        let previous=stored.or_else(||existing.then(||BEFORE_RECORD.to_owned()));
        let this=Self{file,previous:Mutex::new(previous.clone())};
        // A fresh installation has nothing to catch up on: record it at once.
        if previous.is_none() {let _=this.record(env!("CARGO_PKG_VERSION"));}
        this
    }
    fn record(&self,version:&str)->Result<(),String> {
        let temp=self.file.with_extension(format!("tmp-{}",std::process::id()));
        std::fs::write(&temp,serde_json::to_vec(&json!({"last_shown":version})).map_err(err)?).map_err(err)?;
        std::fs::rename(temp,&self.file).map_err(err)?;
        *self.previous.lock().map_err(err)?=Some(version.to_owned());
        Ok(())
    }
    fn pending(&self)->Vec<Value> {
        let current=env!("CARGO_PKG_VERSION");
        let previous=self.previous.lock().ok().and_then(|p|p.clone());
        match previous {
            Some(p) if order(&p)<order(current)=>between(&entries(),Some(&p),current),
            _=>Vec::new(),
        }
    }
}

/// `all`: every version up to this one (the Settings button); otherwise only what this installation has not shown yet.
#[tauri::command]
pub fn whats_new_get(webview:Webview,app:tauri::AppHandle,all:Option<bool>)->Result<Value,String> {
    require_local(&webview)?;
    let current=env!("CARGO_PKG_VERSION");
    let versions=if all==Some(true) {between(&entries(),None,current)} else {app.state::<WhatsNew>().pending()};
    Ok(json!({"current":current,"versions":versions}))
}

#[tauri::command]
pub fn whats_new_seen(webview:Webview,app:tauri::AppHandle)->Result<(),String> {
    require_local(&webview)?;
    if webview.label()!="connector-panel" {return Err("Open the project panel".into());}
    app.state::<WhatsNew>().record(env!("CARGO_PKG_VERSION"))
}

#[cfg(test)]mod tests {
    use super::*;
    fn root(name:&str)->std::path::PathBuf {let r=std::env::temp_dir().join(format!("vibez-whats-new-{name}-{}",std::process::id()));let _=std::fs::remove_dir_all(&r);std::fs::create_dir_all(&r).unwrap();r}
    fn list(names:&[&str])->Vec<Value> {names.iter().map(|v|json!({"version":v,"changes":["x"]})).collect()}
    fn versions(v:&[Value])->Vec<&str> {v.iter().map(|e|e["version"].as_str().unwrap()).collect()}
    #[test]fn versions_order_alpha_beta_rc_final_and_numbers_numerically() {
        let mut v=vec!["4.0.0","4.0.0-beta.10","4.0.0-alpha.31","4.0.0-beta.2","4.0.0-rc.1","4.1.0-alpha.1"];
        v.sort_by_key(|s|order(s));
        assert_eq!(v,["4.0.0-alpha.31","4.0.0-beta.2","4.0.0-beta.10","4.0.0-rc.1","4.0.0","4.1.0-alpha.1"]);
        for bad in ["4.0","4.0.0-gamma.1","4.0.0-beta","x.y.z","4.0.0.1"] {assert!(order(bad).is_none(),"{bad}");}
    }
    #[test]fn every_missed_version_is_listed_newest_first_up_to_the_running_one() {
        let all=list(&["4.0.0-beta.1","4.0.0-beta.3","4.0.0-beta.2","4.0.0-beta.4","4.0.0-beta.5"]);
        assert_eq!(versions(&between(&all,Some("4.0.0-beta.1"),"4.0.0-beta.4")),["4.0.0-beta.4","4.0.0-beta.3","4.0.0-beta.2"]);
        assert_eq!(versions(&between(&all,None,"4.0.0-beta.2")),["4.0.0-beta.2","4.0.0-beta.1"]);
        assert!(between(&all,Some("4.0.0-beta.4"),"4.0.0-beta.4").is_empty());
    }
    #[test]fn a_fresh_installation_records_its_version_and_an_existing_profile_catches_up_from_before_the_record() {
        let fresh=root("fresh");let state=WhatsNew::load(&fresh,false);
        assert!(state.pending().is_empty());
        assert_eq!(std::fs::read_to_string(fresh.join("whats-new.json")).unwrap(),json!({"last_shown":env!("CARGO_PKG_VERSION")}).to_string());
        let old=root("old");let state=WhatsNew::load(&old,true);
        assert_eq!(*state.previous.lock().unwrap(),Some(BEFORE_RECORD.to_owned()));
        assert!(!old.join("whats-new.json").exists(),"nothing is written before the person has seen the changes");
        state.record("4.0.0-beta.9").unwrap();
        assert_eq!(*WhatsNew::load(&old,true).previous.lock().unwrap(),Some("4.0.0-beta.9".to_owned()));
        std::fs::write(old.join("whats-new.json"),"{\"last_shown\":\"nonsense\"}").unwrap();
        assert_eq!(*WhatsNew::load(&old,false).previous.lock().unwrap(),Some(env!("CARGO_PKG_VERSION").to_owned()),"an unreadable record counts as fresh");
    }
    #[test]fn the_bundled_changelog_is_valid_and_lists_released_versions() {
        let all=entries();
        assert!(all.len()>=3);
        for e in &all {assert!(e["changes"].as_array().unwrap().iter().all(|c|c.as_str().is_some_and(|s|!s.is_empty()&&s.len()<2000)));}
        assert!(versions(&all).contains(&"4.0.0-beta.3"));
    }
}
