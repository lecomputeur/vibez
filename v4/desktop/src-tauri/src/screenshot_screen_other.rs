//! User-initiated OS desktop selection. No webpage privileges or arbitrary paths.
use crate::err;
use std::{io::Read,process::{Command,Stdio},time::{Duration,Instant}};

fn run(mut command:Command)->Result<std::process::Output,String>{
    command.stdout(Stdio::piped()).stderr(Stdio::piped()).stdin(Stdio::null());
    #[cfg(target_os="windows")] {use std::os::windows::process::CommandExt;command.creation_flags(0x08000000);}
    let mut child=command.spawn().map_err(err)?;
    let mut out=child.stdout.take().ok_or("Cannot read screen capture output")?;
    let mut errors=child.stderr.take().ok_or("Cannot read screen capture errors")?;
    // Drain both pipes while the process runs: large PNGs must not deadlock on
    // a full stdout pipe. Output limits and a hard timeout bound this operation.
    let stdout=std::thread::spawn(move ||{let mut bytes=Vec::new();out.by_ref().take(36*1024*1024).read_to_end(&mut bytes).map(|_|bytes)});
    let stderr=std::thread::spawn(move ||{let mut bytes=Vec::new();errors.by_ref().take(16384).read_to_end(&mut bytes).map(|_|bytes)});
    let deadline=Instant::now()+Duration::from_secs(125);
    let status=loop {
        if let Some(status)=child.try_wait().map_err(err)?{break status;}
        if Instant::now()>deadline{let _=child.kill();let _=child.wait();return Err("Screen selection timed out".into());}
        std::thread::sleep(Duration::from_millis(40));
    };
    Ok(std::process::Output{status,stdout:stdout.join().map_err(|_|"Screen capture reader failed")?.map_err(err)?,stderr:stderr.join().map_err(|_|"Screen capture error reader failed")?.map_err(err)?})
}
#[cfg(target_os="windows")]
pub async fn capture()->Result<Option<Vec<u8>>,String>{
    tauri::async_runtime::spawn_blocking(||{
        use base64::{engine::general_purpose::STANDARD,Engine as _};
        let script=include_str!("screenshot_screen_windows.ps1");
        let encoded=STANDARD.encode(script.encode_utf16().flat_map(u16::to_le_bytes).collect::<Vec<_>>());
        let system=std::env::var_os("SystemRoot").ok_or("Windows system directory unavailable")?;
        let exe=std::path::PathBuf::from(system).join("System32/WindowsPowerShell/v1.0/powershell.exe");
        let mut command=Command::new(exe);command.args(["-NoLogo","-NoProfile","-NonInteractive","-STA","-EncodedCommand",&encoded]);
        let output=run(command)?;
        if !output.status.success(){return Err(format!("Windows screen capture failed: {}",String::from_utf8_lossy(&output.stderr).chars().take(300).collect::<String>()));}
        let encoded=String::from_utf8(output.stdout).map_err(err)?;
        if encoded.trim()=="CANCEL"{return Ok(None);}
        if encoded.len()>34*1024*1024{return Err("Screenshot exceeds size limit".into());}
        Ok(Some(STANDARD.decode(encoded.trim()).map_err(err)?))
    }).await.map_err(err)?
}
#[cfg(target_os="macos")]
pub async fn capture()->Result<Option<Vec<u8>>,String>{
    tauri::async_runtime::spawn_blocking(||{
        use std::os::unix::fs::DirBuilderExt;
        use std::sync::atomic::{AtomicU64,Ordering};
        static SERIAL:AtomicU64=AtomicU64::new(1);
        let directory=std::env::temp_dir().join(format!("vibez-screen-{}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::Relaxed)));
        // Refuse an existing path instead of following a pre-created symlink.
        std::fs::DirBuilder::new().mode(0o700).create(&directory).map_err(err)?;
        struct Temp(std::path::PathBuf);impl Drop for Temp{fn drop(&mut self){let _=std::fs::remove_dir_all(&self.0);}}
        let _temp=Temp(directory.clone());let path=directory.join("selection.png");
        let mut command=Command::new("/usr/sbin/screencapture");command.args(["-i","-s","-x","-t","png"]);command.arg(&path);
        let output=run(command)?;
        if !path.is_file(){
            if output.status.success()||output.stderr.is_empty(){return Ok(None);}
            return Err("macOS screen capture failed. Allow VibeZ in System Settings > Privacy & Security > Screen Recording, then try again.".into());
        }
        if std::fs::metadata(&path).map_err(err)?.len()>26*1024*1024{return Err("Screenshot exceeds size limit".into());}
        Ok(Some(std::fs::read(path).map_err(err)?))
    }).await.map_err(err)?
}
