//! Patch-only, compare-and-set preferences and crash-safe, versioned storage.
use crate::policy::Settings;
use serde::{Deserialize, Serialize};
use std::{fs, io::Write, path::Path, sync::atomic::{AtomicU64, Ordering}};

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub struct Patch {
    pub language: Option<String>,
    pub zoom_factor: Option<f64>,
    pub show_screenshot: Option<bool>,
    pub close_to_tray: Option<bool>,
    pub start_at_login: Option<bool>,
}
impl Patch {
    pub fn apply(&self, expected: &Self, current: &Settings) -> Result<Settings, String> {
        let mut next = current.clone();
        macro_rules! field {
            ($key:ident) => {
                if let Some(value) = &self.$key {
                    if current.$key != *value && expected.$key.as_ref() != Some(&current.$key) {
                        return Err("settings_conflict".into());
                    }
                    next.$key = value.clone();
                }
            };
        }
        field!(language); field!(zoom_factor); field!(show_screenshot);
        field!(close_to_tray); field!(start_at_login);
        next.validate()?;
        Ok(next)
    }
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Document { schema_version: u32, settings: Settings }
pub struct Loaded { pub settings: Settings, pub recovered: bool }
static NEXT_FILE: AtomicU64 = AtomicU64::new(1);

pub fn read(path: &Path) -> Result<Loaded, String> {
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Loaded { settings: Settings::default(), recovered: false }),
        Err(e) => return Err(e.to_string()),
    };
    let raw = serde_json::from_slice::<serde_json::Value>(&bytes);
    let parsed = match raw {
        Ok(v) if v.get("schema_version").is_some() => {
            if v["schema_version"] != 1 {
                return Err("Settings use an unsupported schema version; the file has not been changed".into());
            }
            serde_json::from_value::<Document>(v).map(|d| d.settings)
        }
        Ok(v) => serde_json::from_value::<Settings>(v),
        Err(e) => Err(e),
    };
    if let Ok(settings) = parsed {
        if settings.validate().is_ok() { return Ok(Loaded { settings, recovered: false }); }
    }
    // Back up corrupt bytes before a later save can replace the original file.
    let backup = path.with_extension(format!("invalid-{}-{}", std::process::id(), NEXT_FILE.fetch_add(1, Ordering::Relaxed)));
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)] { use std::os::unix::fs::OpenOptionsExt; options.mode(0o600); }
    let mut file = options.open(backup).map_err(crate::err)?;
    file.write_all(&bytes).map_err(crate::err)?;
    file.sync_all().map_err(crate::err)?;
    Ok(Loaded { settings: Settings::default(), recovered: true })
}
pub fn write(path: &Path, settings: &Settings) -> Result<(), String> {
    settings.validate()?;
    let temp = path.with_extension(format!("{}-{}.tmp", std::process::id(), NEXT_FILE.fetch_add(1, Ordering::Relaxed)));
    let result = (|| {
        let mut options = fs::OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)] { use std::os::unix::fs::OpenOptionsExt; options.mode(0o600); }
        let mut out = options.open(&temp).map_err(crate::err)?;
        let data = Document { schema_version: 1, settings: settings.clone() };
        out.write_all(&serde_json::to_vec_pretty(&data).map_err(crate::err)?).map_err(crate::err)?;
        out.sync_all().map_err(crate::err)?;
        drop(out);
        fs::rename(&temp, path).map_err(crate::err)
    })();
    if result.is_err() { let _ = fs::remove_file(temp); }
    result
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn unrelated_stale_preferences_are_never_overwritten() {
        let current = Settings { language: "en".into(), ..Settings::default() };
        let patch = Patch { zoom_factor: Some(1.25), ..Patch::default() };
        let expected = Patch { zoom_factor: Some(1.), ..Patch::default() };
        let next = patch.apply(&expected, &current).unwrap();
        assert_eq!(next.language, "en"); assert_eq!(next.zoom_factor, 1.25);
        assert!(Patch { language: Some("de".into()), ..Patch::default() }
            .apply(&Patch { language: Some("nl".into()), ..Patch::default() }, &current).is_err());
    }
    #[test] fn reject_unknown_and_invalid_patches() {
        assert!(serde_json::from_str::<Patch>(r#"{"unknown":true}"#).is_err());
        assert!(Patch { zoom_factor: Some(9.), ..Patch::default() }
            .apply(&Patch { zoom_factor: Some(1.), ..Patch::default() }, &Settings::default()).is_err());
    }
    #[test] fn migrate_legacy_recover_corruption_and_preserve_future_schema() {
        let dir = std::env::temp_dir().join(format!("vibez-settings-test-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap(); let file = dir.join("settings.json");
        fs::write(&file, r#"{"language":"nl","zoom_factor":1.25}"#).unwrap();
        let old = read(&file).unwrap(); assert_eq!(old.settings.language, "nl");
        write(&file, &old.settings).unwrap();
        assert_eq!(read(&file).unwrap().settings.zoom_factor, 1.25);
        assert!(fs::read_to_string(&file).unwrap().contains("schema_version"));
        fs::write(&file, b"{broken").unwrap(); assert!(read(&file).unwrap().recovered);
        assert!(fs::read_dir(&dir).unwrap().any(|e| e.unwrap().path().to_string_lossy().contains("invalid-")));
        fs::write(&file, r#"{"schema_version":99}"#).unwrap(); assert!(read(&file).is_err());
        assert_eq!(fs::read_to_string(&file).unwrap(), r#"{"schema_version":99}"#);
        fs::remove_dir_all(dir).unwrap();
    }
}
