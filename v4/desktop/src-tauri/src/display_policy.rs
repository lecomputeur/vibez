//! Display arithmetic shared by normal desktop and explicit safe-output mode.
use super::Screen;
use std::path::Path;

/// Remember an explicit personal monitor in the Alpha profile so an ordinary
/// public package update cannot erase it by replacing the desktop launcher.
/// Other installations with no preference continue to use their primary screen.
pub fn load_safe_output(config:&Path,explicit:Option<&str>)->Result<Option<String>,String> {
    use std::io::{Read,Write};
    use std::sync::atomic::{AtomicU64,Ordering};
    static SERIAL:AtomicU64=AtomicU64::new(1);
    let directory=std::fs::symlink_metadata(config).map_err(|_|"The Alpha settings folder is not available")?;
    if !directory.is_dir()||directory.file_type().is_symlink(){return Err("The Alpha settings folder is redirected".into());}
    let path=config.join("safe-output.json");
    match std::fs::symlink_metadata(&path) {
        Ok(meta) if !meta.is_file()||meta.file_type().is_symlink()=>return Err("The saved safe screen choice is redirected".into()),
        Ok(_)=>{},Err(e) if e.kind()==std::io::ErrorKind::NotFound=>{},
        Err(_)=>return Err("The saved safe screen choice cannot be checked".into()),
    }
    if let Some(output)=requested_output(explicit)? {
        let temp=config.join(format!(".safe-output-{}-{}.tmp",std::process::id(),SERIAL.fetch_add(1,Ordering::SeqCst)));
        struct Pending(std::path::PathBuf);
        impl Drop for Pending {fn drop(&mut self){let _=std::fs::remove_file(&self.0);}}
        let _pending=Pending(temp.clone());
        let mut options=std::fs::OpenOptions::new();options.create_new(true).write(true);
        #[cfg(unix)] {use std::os::unix::fs::OpenOptionsExt;options.mode(0o600);}
        let mut file=options.open(&temp).map_err(|_|"The safe screen choice cannot be saved")?;
        let data=serde_json::to_vec(&serde_json::json!({"output":output})).map_err(|_|"The safe screen choice is not valid")?;
        file.write_all(&data).and_then(|_|file.sync_all()).map_err(|_|"The safe screen choice cannot be saved")?;
        drop(file);
        std::fs::rename(&temp,&path).map_err(|_|"The safe screen choice cannot be saved")?;
        return Ok(Some(output.into()));
    }
    let mut options=std::fs::OpenOptions::new();options.read(true);
    #[cfg(target_os="linux")] {use std::os::unix::fs::OpenOptionsExt;options.custom_flags(0x20000);}
    let file=match options.open(&path) {
        Ok(file)=>file,Err(e) if e.kind()==std::io::ErrorKind::NotFound=>return Ok(None),
        Err(_)=>return Err("The saved safe screen choice cannot be read".into()),
    };
    if file.metadata().map_err(|_|"The safe screen choice cannot be checked")?.len()>2048 {
        return Err("The saved safe screen choice is not valid".into());
    }
    let mut data=Vec::new();file.take(2049).read_to_end(&mut data).map_err(|_|"The safe screen choice cannot be read")?;
    if data.len()>2048{return Err("The saved safe screen choice is not valid".into());}
    let data:serde_json::Value=serde_json::from_slice(&data).map_err(|_|"The saved safe screen choice is not valid")?;
    let raw=data["output"].as_str().ok_or("The saved safe screen choice is not valid")?;
    requested_output(Some(raw)).map(|value|value.map(str::to_owned))
}

pub fn requested_output(raw:Option<&str>)->Result<Option<&str>,String> {
    let Some(raw)=raw else{return Ok(None);};
    if raw.is_empty()||raw.len()>128||!raw.bytes().all(|c|c.is_ascii_alphanumeric()||matches!(c,b'-'|b'_'|b'.'|b':')) {
        return Err("The configured screen name is not valid".into());
    }
    Ok(Some(raw))
}
pub fn parse_monitor(line:&str,output:&str)->Option<Screen> {
    let parts:Vec<_>=line.split_whitespace().collect();
    if parts.last().copied()!=Some(output){return None;}
    let geometry=*parts.get(2)?;let coordinate=geometry.find(['+','-'])?;
    let mut sizes=geometry[..coordinate].split('x');
    let width=sizes.next()?.split('/').next()?.parse::<u32>().ok()?;
    let height=sizes.next()?.split('/').next()?.parse::<u32>().ok()?;
    let coords=&geometry[coordinate..];let second=coords[1..].find(['+','-'])?+1;
    let result=Screen{x:coords[..second].parse().ok()?,y:coords[second..].parse().ok()?,width,height};
    (width>0&&height>0).then_some(result)
}
pub fn select(monitors:&[Screen],primary:Option<Screen>,requested:Option<Screen>)->Result<Screen,String> {
    let usable=|s:&Screen|s.width>0&&s.height>0;
    if let Some(requested)=requested {
        return monitors.iter().find(|s|**s==requested&&usable(s)).copied()
            .ok_or_else(||"The chosen screen does not match the screen layout".into());
    }
    primary.filter(|s|usable(s)&&monitors.contains(s)).or_else(||monitors.iter().find(|s|usable(s)).copied())
        .ok_or_else(||"No available screen was found".into())
}
pub fn logical_bounds(screen:Screen,scale:f64)->Result<(i32,i32,u32,u32),String> {
    if !scale.is_finite()||scale<0.5||scale>8.||screen.width==0||screen.height==0 {
        return Err("The screen scale is not valid".into());
    }
    Ok(((screen.x as f64/scale).round() as i32,(screen.y as f64/scale).round() as i32,
        (screen.width as f64/scale).floor().max(1.) as u32,(screen.height as f64/scale).floor().max(1.) as u32))
}
pub fn window_bounds(screen:Screen,scale:f64,desired:(u32,u32))->Result<Screen,String> {
    logical_bounds(screen,scale)?;
    let margin=((40.*scale).round() as u32).min(screen.width/8).min(screen.height/8);
    let width=((desired.0 as f64*scale).round() as u32).min(screen.width.saturating_sub(margin*2)).max(1);
    let height=((desired.1 as f64*scale).round() as u32).min(screen.height.saturating_sub(margin*2)).max(1);
    Ok(Screen{x:screen.x.saturating_add(margin as i32),y:screen.y.saturating_add(margin as i32),width,height})
}
pub fn dialog_bounds(screen:Screen,scale:f64)->Result<(i32,i32,i32,i32),String> {
    let(x,y,width,height)=logical_bounds(screen,scale)?;
    let w=820.min(width.saturating_sub(40)).max(1);let h=620.min(height.saturating_sub(40)).max(1);
    let dx=120.min(width.saturating_sub(w));let dy=100.min(height.saturating_sub(h));
    Ok((x.saturating_add(dx as i32),y.saturating_add(dy as i32),w as i32,h as i32))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn explicit_output_survives_a_plain_public_launcher_and_unknown_files_fail_closed() {
        let root=std::env::temp_dir().join(format!("vibez-alpha-display-{}",std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        assert_eq!(load_safe_output(&root,None).unwrap(),None);
        assert_eq!(load_safe_output(&root,Some("DisplayPort-1")).unwrap(),Some("DisplayPort-1".into()));
        assert_eq!(load_safe_output(&root,None).unwrap(),Some("DisplayPort-1".into()));
        let before=std::fs::read(root.join("safe-output.json")).unwrap();
        assert!(load_safe_output(&root,Some("$(unsafe)")).is_err());
        assert_eq!(std::fs::read(root.join("safe-output.json")).unwrap(),before);
        #[cfg(unix)] {use std::os::unix::fs::PermissionsExt;assert_eq!(std::fs::metadata(root.join("safe-output.json")).unwrap().permissions().mode()&0o777,0o600);}
        std::fs::write(root.join("safe-output.json"),b"invalid").unwrap();assert!(load_safe_output(&root,None).is_err());
        #[cfg(unix)] {
            std::fs::remove_file(root.join("safe-output.json")).unwrap();
            let outside=root.join("untouched");std::fs::write(&outside,b"preserved").unwrap();
            std::os::unix::fs::symlink(&outside,root.join("safe-output.json")).unwrap();
            assert!(load_safe_output(&root,Some("DisplayPort-1")).is_err());
            assert_eq!(std::fs::read(&outside).unwrap(),b"preserved");
        }
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn one_screen_and_unknown_connector_models_use_native_primary() {
        let laptop=Screen{x:0,y:0,width:1920,height:1080};
        assert_eq!(select(&[laptop],Some(laptop),None).unwrap(),laptop);
        assert_eq!(select(&[laptop],None,None).unwrap(),laptop);
        assert!(select(&[],None,None).is_err());
    }
    #[test]
    fn explicit_output_never_falls_back_to_another_monitor() {
        let left=Screen{x:0,y:0,width:2560,height:1440};let right=Screen{x:2560,..left};
        assert_eq!(select(&[left,right],Some(right),Some(left)).unwrap(),left);
        assert!(select(&[right],Some(right),Some(left)).is_err());
        assert_eq!(requested_output(None).unwrap(),None);
        assert_eq!(requested_output(Some("DisplayPort-1")).unwrap(),Some("DisplayPort-1"));
        for raw in ["","DP-1\n","$(x)","DP 1"] {assert!(requested_output(Some(raw)).is_err());}
    }
    #[test]
    fn arbitrary_connector_and_negative_coordinates_are_parsed_without_assumptions() {
        let monitor=parse_monitor(" 0: +*eDP-1 1920/310x1080/170-1920-1080 eDP-1","eDP-1").unwrap();
        assert_eq!(monitor,Screen{x:-1920,y:-1080,width:1920,height:1080});
        assert!(parse_monitor(" 0: +*eDP-1 1920/310x1080/170+0+0 eDP-1","DisplayPort-1").is_none());
        assert!(parse_monitor(" 0: +eDP-1 0/310x1080/170+0+0 eDP-1","eDP-1").is_none());
    }
    #[test]
    fn hidpi_and_small_screen_sizes_fit_in_native_monitor() {
        for (monitor,scale) in [(Screen{x:0,y:0,width:1920,height:1080},2.),
            (Screen{x:-2560,y:0,width:2560,height:1440},1.25),
            (Screen{x:0,y:0,width:800,height:600},1.)] {
            let placed=window_bounds(monitor,scale,(1280,860)).unwrap();
            assert!(placed.x>=monitor.x&&placed.y>=monitor.y);
            assert!(placed.x as i64+placed.width as i64<=monitor.x as i64+monitor.width as i64);
            assert!(placed.y as i64+placed.height as i64<=monitor.y as i64+monitor.height as i64);
            let(x,y,w,h)=dialog_bounds(monitor,scale).unwrap();let(lx,ly,lw,lh)=logical_bounds(monitor,scale).unwrap();
            assert!(x>=lx&&y>=ly&&x+w<=lx+lw as i32&&y+h<=ly+lh as i32);
        }
        assert!(logical_bounds(Screen{x:0,y:0,width:1920,height:1080},f64::NAN).is_err());
    }
}
