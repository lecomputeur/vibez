//! Hand the verified update to the OS, then release the running application.
use crate::err;
use std::path::Path;
use tauri::AppHandle;
use tauri_plugin_opener::OpenerExt;
use crate::update_download::Asset;
#[cfg(target_os = "linux")]
use crate::update_download;

fn launch_then_exit<L: FnOnce() -> Result<(), String>, Q: FnOnce()>(launch: L, quit: Q) -> Result<(), String> {
    launch()?;
    quit();
    Ok(())
}

pub fn open(app: &AppHandle, path: &Path, asset: &Asset) -> Result<(), String> {
    launch_then_exit(|| {
        #[cfg(target_os = "linux")]
        if asset.kind == "AppImage" {
            return appimage::schedule(path, asset);
        }
        let _ = asset;
        app.opener().open_path(path.to_string_lossy().into_owned(), None::<&str>).map_err(err)
    }, || app.exit(0))
}

#[cfg(target_os = "linux")]
pub mod appimage {
    use super::*;
    use std::{ffi::OsString, fs, process::{Command, Stdio}, time::{Duration, Instant}};
    use std::os::unix::process::CommandExt;
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
    use serde::{Deserialize, Serialize};
    const FLAG: &str = "--launch-appimage-after-exit";

    #[derive(Serialize, Deserialize)]
    struct Replacement { path: std::path::PathBuf, staged: std::path::PathBuf, device: u64, inode: u64 }

    struct Staged(Option<Replacement>);
    impl Drop for Staged {
        fn drop(&mut self) {
            if let Some(replacement) = &self.0 { let _ = fs::remove_file(&replacement.staged); }
        }
    }

    fn stage_replacement(path: &Path, asset: &Asset) -> Result<Staged, String> {
        let Some(original) = std::env::var_os("APPIMAGE") else { return Ok(Staged(None)); };
        let Some(appdir) = std::env::var_os("APPDIR") else { return Ok(Staged(None)); };
        if !std::env::current_exe().map_err(err)?.starts_with(appdir) { return Ok(Staged(None)); }
        let original = fs::canonicalize(original).map_err(err)?;
        let metadata = fs::metadata(&original).map_err(err)?;
        if !metadata.is_file() { return Err("The installed AppImage is not a regular file".into()); }
        let staged = original.with_file_name(format!(".vibez-update-{}.AppImage", std::process::id()));
        let output = fs::OpenOptions::new().create_new(true).write(true).mode(0o600).open(&staged).map_err(err)?;
        let replacement = Staged(Some(Replacement { path: original, staged: staged.clone(), device: metadata.dev(), inode: metadata.ino() }));
        let mut input = fs::File::open(path).map_err(err)?;
        let mut output = output;
        std::io::copy(&mut input, &mut output).map_err(err)?;
        output.sync_all().map_err(err)?;
        update_download::verify_file(&staged, asset)?;
        fs::set_permissions(&staged, fs::Permissions::from_mode(metadata.mode() & 0o777)).map_err(err)?;
        Ok(replacement)
    }

    fn token(pid: u32) -> Result<Option<String>, String> {
        let stat = match fs::read_to_string(format!("/proc/{pid}/stat")) {
            Ok(stat) => stat,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(err(e)),
        };
        // comm can contain spaces and parentheses. Fields after its last ') '
        // start at field 3; field 22 identifies this process, even if a PID is reused.
        let fields: Vec<_> = stat.rsplit_once(") ").ok_or("Invalid process status")?.1.split_whitespace().collect();
        if fields.first() == Some(&"Z") { return Ok(None); }
        Ok(Some(fields.get(19).ok_or("Missing process start time")?.to_string()))
    }

    pub fn schedule(path: &Path, asset: &Asset) -> Result<(), String> {
        update_download::prepare_appimage(path)?;
        let mut replacement = stage_replacement(path, asset)?;
        let pid = std::process::id();
        let start = token(pid)?.ok_or("Cannot identify the running application")?;
        // The helper runs before Tauri/single-instance initialization. Starting
        // the AppImage while this instance lives would only activate the old app.
        Command::new(std::env::current_exe().map_err(err)?)
            .args([FLAG, &pid.to_string(), &start]).arg(path)
            .args([asset.size.to_string(), asset.sha256.clone()])
            .arg(serde_json::to_string(&replacement.0).map_err(err)?)
            .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null())
            .process_group(0).spawn().map_err(err)?;
        // The launched helper now owns cleanup of the staged replacement.
        replacement.0 = None;
        Ok(())
    }

    pub fn run_helper() -> Option<Result<(), String>> {
        let args: Vec<OsString> = std::env::args_os().collect();
        if args.get(1).is_none_or(|arg| arg != FLAG) { return None; }
        Some(run(&args))
    }

    fn run(args: &[OsString]) -> Result<(), String> {
        if args.len() != 8 { return Err("Invalid AppImage handoff".into()); }
        let pid: u32 = args[2].to_str().ok_or("Invalid parent PID")?.parse().map_err(err)?;
        let start = args[3].to_str().ok_or("Invalid process start time")?;
        if pid == 0 || start.is_empty() || !start.bytes().all(|b| b.is_ascii_digit()) {
            return Err("Invalid parent process".into());
        }
        let path = Path::new(&args[4]);
        let name = path.file_name().and_then(|n| n.to_str()).filter(|n| n.ends_with(".AppImage")).ok_or("Invalid AppImage path")?;
        let size: u64 = args[5].to_str().ok_or("Invalid update size")?.parse().map_err(err)?;
        let sha256 = args[6].to_str().ok_or("Invalid update checksum")?;
        if size == 0 || size > 512 * 1024 * 1024 || sha256.len() != 64 || !sha256.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err("Invalid update integrity data".into());
        }
        let replacement: Option<Replacement> = serde_json::from_str(args[7].to_str().ok_or("Invalid replacement metadata")?).map_err(err)?;
        if let Some(r) = &replacement {
            if r.staged != r.path.with_file_name(format!(".vibez-update-{pid}.AppImage")) {
                return Err("Invalid replacement location".into());
            }
        }
        let mut replacement = Staged(replacement);
        let deadline = Instant::now() + Duration::from_secs(30);
        while token(pid)?.as_deref() == Some(start) {
            if Instant::now() >= deadline { return Err("VibeZ did not exit; update was not started".into()); }
            std::thread::sleep(Duration::from_millis(50));
        }
        let asset = Asset { name: name.into(), kind: "AppImage".into(), size, sha256: sha256.to_lowercase(), url: String::new() };
        // Recheck after waiting; never execute bytes changed since the UI check.
        update_download::verify_file(path, &asset)?;
        let launch_path = if let Some(r) = &replacement.0 {
            update_download::verify_file(&r.staged, &asset)?;
            let current = fs::symlink_metadata(&r.path).map_err(err)?;
            if !current.is_file() || current.dev() != r.device || current.ino() != r.inode {
                return Err("The installed AppImage changed; it was not replaced".into());
            }
            fs::rename(&r.staged, &r.path).map_err(err)?;
            let installed = r.path.clone();
            replacement.0 = None;
            installed
        } else { path.to_path_buf() };
        Command::new(launch_path).env_remove("APPIMAGE").env_remove("APPDIR")
            .env_remove("LD_LIBRARY_PATH").stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null())
            .process_group(0).spawn().map_err(err)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;

    #[test]
    fn the_app_exits_only_after_a_successful_handoff() {
        let events = RefCell::new(Vec::new());
        launch_then_exit(|| { events.borrow_mut().push("launch"); Ok(()) }, || events.borrow_mut().push("exit")).unwrap();
        assert_eq!(*events.borrow(), vec!["launch", "exit"]);
    }

    #[test]
    fn a_failed_launch_keeps_the_app_running() {
        let missing = std::env::temp_dir().join(format!("vibez-missing-installer-{}", std::process::id()));
        let exited = RefCell::new(false);
        let result = launch_then_exit(|| std::process::Command::new(missing).spawn().map(|_| ()).map_err(err), || *exited.borrow_mut() = true);
        assert!(result.is_err());
        assert!(!*exited.borrow());
    }
}
