//! Display arithmetic: VibeZ opens on the native primary monitor.
use super::Screen;

pub fn select(monitors:&[Screen],primary:Option<Screen>)->Result<Screen,String> {
    let usable=|s:&Screen|s.width>0&&s.height>0;
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
    fn one_screen_and_two_screen_layouts_use_native_primary() {
        let laptop=Screen{x:0,y:0,width:1920,height:1080};
        assert_eq!(select(&[laptop],Some(laptop)).unwrap(),laptop);
        assert_eq!(select(&[laptop],None).unwrap(),laptop);
        assert!(select(&[],None).is_err());
        let right=Screen{x:1920,..laptop};
        assert_eq!(select(&[laptop,right],Some(right)).unwrap(),right);
        assert_eq!(select(&[laptop,right],None).unwrap(),laptop);
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
