//! Per-installation preferences of the right-hand panel: the order of its
//! two tabs. Stored next to the language choice, with the same crash-safe
//! write. An `advanced` switch from earlier builds is ignored on read and no
//! longer written.
use super::*;
const TABS:[&str;2]=["files","advanced"];
#[derive(Clone,Debug,PartialEq,serde::Serialize,serde::Deserialize)]
pub struct Prefs {pub tab_order:Vec<String>}
impl Default for Prefs {fn default()->Self {Self{tab_order:TABS.iter().map(|t|(*t).to_owned()).collect()}}}
/// Known tabs only, each once, in the given order; missing tabs follow in the default order.
fn normalize_order(order:&[String])->Vec<String> {
    let mut out:Vec<String>=Vec::new();
    for tab in order {if TABS.contains(&tab.as_str())&&!out.contains(tab){out.push(tab.clone());}}
    for tab in TABS {if !out.iter().any(|v|v==tab){out.push(tab.to_owned());}}
    out
}
fn parse(value:&Value)->Prefs {
    let order:Vec<String>=value["tab_order"].as_array().map(|a|a.iter().filter_map(|v|v.as_str().map(str::to_owned)).collect()).unwrap_or_default();
    Prefs{tab_order:normalize_order(&order)}
}
pub struct PanelPrefs {prefs:Mutex<Prefs>,file:std::path::PathBuf}
impl PanelPrefs {
    pub fn load(config:&std::path::Path)->Self {
        let file=config.join("panel.json");
        let prefs=std::fs::read(&file).ok().filter(|raw|raw.len()<=65_536).and_then(|raw|serde_json::from_slice::<Value>(&raw).ok()).map(|v|parse(&v)).unwrap_or_default();
        Self{prefs:Mutex::new(prefs),file}
    }
    pub fn current(&self)->Prefs {self.prefs.lock().map(|p|p.clone()).unwrap_or_default()}
    fn save(&self,prefs:&Prefs)->Result<(),String> {
        static SERIAL:AtomicU64=AtomicU64::new(1);
        let temp=self.file.with_extension(format!("tmp-{}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::SeqCst)));
        let mut options=std::fs::OpenOptions::new();options.create_new(true).write(true);
        #[cfg(unix)] {use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
        let mut f=options.open(&temp).map_err(err)?;
        f.write_all(serde_json::to_string(prefs).map_err(err)?.as_bytes()).map_err(err)?;f.sync_all().map_err(err)?;
        std::fs::rename(temp,&self.file).map_err(err)
    }
    pub fn update(&self,tab_order:Option<Vec<String>>)->Result<Prefs,String> {
        let mut guard=self.prefs.lock().map_err(err)?;
        let next=Prefs{tab_order:tab_order.as_deref().map(normalize_order).unwrap_or_else(||guard.tab_order.clone())};
        if next!=*guard {self.save(&next)?;*guard=next.clone();}
        Ok(next)
    }
}
#[tauri::command]
pub fn panel_prefs_get(webview:Webview,app:tauri::AppHandle)->Result<Value,String> {
    require_local(&webview)?;
    serde_json::to_value(app.state::<PanelPrefs>().current()).map_err(err)
}
#[tauri::command]
pub fn panel_prefs_set(webview:Webview,app:tauri::AppHandle,tab_order:Option<Vec<String>>)->Result<Value,String> {
    require_local(&webview)?;
    if webview.label()!="connector-panel" {return Err("Open the project panel".into());}
    if tab_order.as_ref().is_some_and(|o|o.len()>16||o.iter().any(|t|t.len()>32)) {return Err("Invalid tab order".into());}
    serde_json::to_value(app.state::<PanelPrefs>().update(tab_order)?).map_err(err)
}
#[cfg(test)]mod tests {
    use super::*;
    fn root(name:&str)->std::path::PathBuf {let r=std::env::temp_dir().join(format!("vibez-panel-prefs-{name}-{}",std::process::id()));let _=std::fs::remove_dir_all(&r);std::fs::create_dir_all(&r).unwrap();r}
    #[test]fn a_fresh_installation_uses_the_default_order_without_writing() {
        let r=root("fresh");let p=PanelPrefs::load(&r);
        assert_eq!(p.current(),Prefs::default());assert_eq!(p.current().tab_order,["files","advanced"]);
        assert!(!r.join("panel.json").exists(),"reading never creates the file");std::fs::remove_dir_all(r).unwrap();
    }
    #[test]fn the_order_survives_a_restart_and_the_former_switch_is_ignored() {
        let r=root("restart");let p=PanelPrefs::load(&r);
        let moved=p.update(Some(vec!["advanced".into(),"files".into(),"project".into()])).unwrap();assert_eq!(moved.tab_order,["advanced","files"],"the former Project tab is dropped from a stored order");
        assert_eq!(PanelPrefs::load(&r).current(),moved);
        assert!(!std::fs::read_to_string(r.join("panel.json")).unwrap().contains("advanced\":"),"no switch is written any more");
        assert_eq!(p.update(None).unwrap(),moved);
        #[cfg(unix)] {use std::os::unix::fs::PermissionsExt;assert_eq!(std::fs::metadata(r.join("panel.json")).unwrap().permissions().mode()&0o777,0o600);}
        std::fs::write(r.join("panel.json"),r#"{"advanced":false,"tab_order":["files","project","advanced"]}"#).unwrap();
        assert_eq!(PanelPrefs::load(&r).current().tab_order,["files","advanced"],"an installation that had Advanced off still gets both tabs");
        std::fs::remove_dir_all(r).unwrap();
    }
    #[test]fn unknown_duplicate_and_missing_tabs_are_normalized_and_corrupt_files_fall_back() {
        assert_eq!(normalize_order(&["project".into(),"bogus".into(),"advanced".into()]),["advanced","files"]);
        assert_eq!(normalize_order(&[]),["files","advanced"]);
        let r=root("corrupt");std::fs::write(r.join("panel.json"),"{not json").unwrap();assert_eq!(PanelPrefs::load(&r).current(),Prefs::default());
        std::fs::write(r.join("panel.json"),r#"{"advanced":"yes","tab_order":["advanced",5,"files"]}"#).unwrap();
        assert_eq!(PanelPrefs::load(&r).current().tab_order,["advanced","files"]);
        std::fs::write(r.join("panel.json"),vec![b' ';70_000]).unwrap();assert_eq!(PanelPrefs::load(&r).current(),Prefs::default());
        std::fs::remove_dir_all(r).unwrap();
    }
}
