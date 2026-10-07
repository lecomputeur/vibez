//! Download only named, published repository artifacts. Never install from this module.
use crate::err;
use semver::Version;
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest,Sha256};
use std::{path::{Path,PathBuf},io::{Read,Write},time::Duration,sync::atomic::{AtomicBool,AtomicU64,Ordering}};
const MAX_PACKAGE:u64=512*1024*1024;
const API:&str="https://api.github.com/repos/lecomputeur/vibez/releases?per_page=100";
static SERIAL:AtomicU64=AtomicU64::new(1);
#[derive(Clone,Debug,Serialize)]
pub struct Asset {pub name:String,pub kind:String,pub size:u64,pub sha256:String,#[serde(skip)]pub url:String}
#[derive(Clone,Debug,Serialize)]
pub struct Release {pub version:String,pub assets:Vec<Asset>}
pub fn platform()->String {
    let os=if cfg!(target_os="windows"){"Windows"}else if cfg!(target_os="macos"){"macOS"}else{"Linux"};
    let arch=if cfg!(target_arch="aarch64"){"arm64"}else{"x64"};format!("{os}-{arch}")
}
fn suffixes(target:&str)->&'static [(&'static str,&'static str)] {
    if target.starts_with("Windows-"){&[("-Setup.exe","EXE"),(".msi","MSI")]}
    else if target.starts_with("macOS-"){&[(".dmg","DMG")]}
    else {&[(".deb","DEB"),(".rpm","RPM"),(".AppImage","AppImage"),(".pkg.tar.zst","Arch/Pacman"),(".flatpak","Flatpak")]}
}
pub fn candidate(value:&Value,target:&str)->Option<Release>{
    if value["draft"]!=false||value["prerelease"]!=false{return None;}
    let version=Version::parse(value["tag_name"].as_str()?.strip_prefix('v')?).ok()?;
    if version.major!=3||!version.pre.is_empty()||!version.build.is_empty(){return None;}
    let prefix=format!("VibeZ-{version}-{target}");
    let base=format!("https://github.com/lecomputeur/vibez/releases/download/v{version}/");
    let mut assets=vec![];
    for (suffix,kind) in suffixes(target){
        let name=format!("{prefix}{suffix}");
        let Some(a)=value["assets"].as_array()?.iter().find(|a|a["name"]==name) else{continue;};
        let size=a["size"].as_u64()?;
        let Some(hash)=a["digest"].as_str().and_then(|s|s.strip_prefix("sha256:")) else{continue;};
        if size==0||size>MAX_PACKAGE||hash.len()!=64||!hash.bytes().all(|c|c.is_ascii_hexdigit())||a["state"]!="uploaded"||a["browser_download_url"]!=format!("{base}{name}"){continue;}
        assets.push(Asset{name:name.clone(),kind:kind.to_string(),size,sha256:hash.to_lowercase(),url:format!("{base}{name}")});
    }
    if assets.is_empty(){None}else{Some(Release{version:version.to_string(),assets})}
}
pub fn allowed_download_url(url:&url::Url)->bool{
    url.scheme()=="https"&&url.username().is_empty()&&url.password().is_none()&&url.port_or_known_default()==Some(443)&&
        matches!(url.host_str(),Some("github.com"|"api.github.com"|"release-assets.githubusercontent.com"|"objects.githubusercontent.com"))
}
fn client()->Result<reqwest::Client,String>{
    reqwest::Client::builder().https_only(true).connect_timeout(Duration::from_secs(15)).timeout(Duration::from_secs(300))
        .redirect(reqwest::redirect::Policy::custom(|attempt|{
            if attempt.previous().len()>=5||!allowed_download_url(attempt.url()){attempt.error("Untrusted update redirect")}else{attempt.follow()}
        })).user_agent(concat!("VibeZ/",env!("CARGO_PKG_VERSION"))).build().map_err(err)
}
pub async fn discover()->Result<Option<Release>,String>{
    let mut r=client()?.get(API).send().await.map_err(err)?.error_for_status().map_err(err)?;
    let mut bytes=vec![];
    while let Some(part)=r.chunk().await.map_err(err)?{
        if bytes.len()+part.len()>4*1024*1024{return Err("Release metadata too large".into());}bytes.extend(part);
    }
    let data:Value=serde_json::from_slice(&bytes).map_err(err)?;
    Ok(data.as_array().ok_or("Invalid release metadata")?.iter().filter_map(|v|candidate(v,&platform()))
        .max_by_key(|v|Version::parse(&v.version).ok()))
}
struct Partial {directory:PathBuf,committed:bool}
impl Drop for Partial{fn drop(&mut self){if !self.committed{let _=std::fs::remove_dir_all(&self.directory);}}}
fn verify_count_hash(size:u64,hash:&str,asset:&Asset)->Result<(),String>{
    if size!=asset.size||hash!=asset.sha256{Err("Update checksum or size mismatch; the download was discarded".into())}else{Ok(())}
}
pub fn verify_file(path:&Path,asset:&Asset)->Result<(),String>{
    let metadata=std::fs::symlink_metadata(path).map_err(err)?;
    if !metadata.file_type().is_file()||metadata.len()!=asset.size{return Err("Downloaded update was changed".into());}
    let mut file=std::fs::File::open(path).map_err(err)?;let mut hasher=Sha256::new();let mut count=0u64;let mut buf=[0u8;65536];
    loop{let n=file.read(&mut buf).map_err(err)?;if n==0{break;}count+=n as u64;if count>asset.size{return Err("Update grew during validation".into());}hasher.update(&buf[..n]);}
    verify_count_hash(count,&format!("{:x}",hasher.finalize()),asset)
}
pub async fn download<F:Fn(u64)>(root:&Path,asset:&Asset,cancel:&AtomicBool,progress:F)->Result<PathBuf,String>{
    let parsed=url::Url::parse(&asset.url).map_err(err)?;
    if !allowed_download_url(&parsed)||asset.name.contains(['/', '\\'])||asset.name.contains("..")||asset.size==0||asset.size>MAX_PACKAGE{return Err("Invalid update asset".into());}
    std::fs::create_dir_all(root).map_err(err)?;
    let dir=root.join(format!("download-{}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::SeqCst)));
    let mut builder=std::fs::DirBuilder::new();
    #[cfg(unix)] {use std::os::unix::fs::DirBuilderExt;builder.mode(0o700);}
    builder.create(&dir).map_err(err)?;let mut guard=Partial{directory:dir.clone(),committed:false};
    let partial=dir.join("download.part");
    let mut opts=std::fs::OpenOptions::new();opts.create_new(true).write(true);
    #[cfg(unix)]{use std::os::unix::fs::OpenOptionsExt;opts.mode(0o600);}
    let mut file=opts.open(&partial).map_err(err)?;
    let mut response=client()?.get(&asset.url).send().await.map_err(err)?.error_for_status().map_err(err)?;
    if response.content_length().is_some_and(|n|n!=asset.size){return Err("Unexpected update size".into());}
    let(mut received,mut hash)=(0u64,Sha256::new());
    loop {
        if cancel.load(Ordering::SeqCst){return Err("cancelled".into());}
        let part=tokio::time::timeout(Duration::from_secs(30),response.chunk()).await.map_err(err)?.map_err(err)?;
        let Some(part)=part else{break;};received+=part.len() as u64;
        if received>asset.size{return Err("Download exceeds declared size".into());}
        file.write_all(&part).map_err(err)?;hash.update(&part);progress(received);
    }
    if cancel.load(Ordering::SeqCst){return Err("cancelled".into());}
    verify_count_hash(received,&format!("{:x}",hash.finalize()),asset)?;file.sync_all().map_err(err)?;drop(file);
    let target=dir.join(&asset.name);std::fs::rename(&partial,&target).map_err(err)?;
    // Preserve normal OS provenance/security prompts. Never remove quarantine.
    #[cfg(target_os="windows")]
    std::fs::write(format!("{}:Zone.Identifier",target.display()),format!("[ZoneTransfer]\r\nZoneId=3\r\nHostUrl={}\r\n",asset.url)).map_err(err)?;
    #[cfg(target_os="macos")]
    {
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(err)?.as_secs();
        let status=std::process::Command::new("/usr/bin/xattr").args(["-w","com.apple.quarantine",&format!("0083;{stamp:x};VibeZ;")]).arg(&target).status().map_err(err)?;
        if !status.success(){return Err("Cannot mark update quarantine".into());}
    }
    guard.committed=true;Ok(target)
}
#[cfg(test)] mod tests{
    use super::*;
    fn fixture()->Value{serde_json::json!({"draft":false,"prerelease":false,"tag_name":"v3.0.4","assets":[{"state":"uploaded","name":"VibeZ-3.0.4-Windows-x64-Setup.exe","size":3,"digest":format!("sha256:{}","a".repeat(64)),"browser_download_url":"https://github.com/lecomputeur/vibez/releases/download/v3.0.4/VibeZ-3.0.4-Windows-x64-Setup.exe"}]})}
    #[test] fn no_preview_or_wrong_channel_or_unknown_hash(){
        assert!(candidate(&fixture(),"Windows-x64").is_some());assert!(candidate(&fixture(),"macOS-arm64").is_none());
        for key in ["draft","prerelease"]{let mut f=fixture();f[key]=true.into();assert!(candidate(&f,"Windows-x64").is_none());}
        for tag in ["v2.9.0","v4.0.0","v3.0.4-beta.1","garbage"]{let mut f=fixture();f["tag_name"]=tag.into();assert!(candidate(&f,"Windows-x64").is_none());}
        for (key,value) in [("digest","sha256:123"),("browser_download_url","https://evil.test/file.exe"),("name","../bad.exe")]{let mut f=fixture();f["assets"][0][key]=value.into();assert!(candidate(&f,"Windows-x64").is_none());}
    }
    #[test]fn hosts_are_strict(){
        for u in ["http://github.com/file","https://github.com.evil.test/file","https://user@github.com/file","https://github.com:444/file","file:///tmp/test","https://localhost/file"]{assert!(!allowed_download_url(&u.parse().unwrap()),"{u}");}
        assert!(allowed_download_url(&"https://release-assets.githubusercontent.com/download?sig=1".parse().unwrap()));
    }
    #[test]fn corrupted_truncated_and_modified_files_fail(){
        let mut a=candidate(&fixture(),"Windows-x64").unwrap().assets.remove(0);a.sha256=format!("{:x}",Sha256::digest(b"abc"));
        let p=std::env::temp_dir().join(format!("vibez-hash-{}",std::process::id()));std::fs::write(&p,b"abc").unwrap();assert!(verify_file(&p,&a).is_ok());
        std::fs::write(&p,b"abd").unwrap();assert!(verify_file(&p,&a).is_err());std::fs::write(&p,b"ab").unwrap();assert!(verify_file(&p,&a).is_err());let _=std::fs::remove_file(p);
    }
}
