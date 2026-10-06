//! Frozen desktop selection for Mint/X11, like the Electron v2 workflow.
//! All pixels and input stay in native GTK; remote content has no capture access.
use crate::err;
use gtk::{gdk, gdk_pixbuf::Pixbuf, glib, prelude::*};
use glib::translate::{from_glib_none, from_glib_full, ToGlibPtr};
use std::{cell::{Cell,RefCell},rc::{Rc,Weak},time::Duration};
use tauri::AppHandle;
type Answer = Result<Option<Vec<u8>>,String>;
type Sender = tokio::sync::oneshot::Sender<Answer>;
struct Session {
    sender: RefCell<Option<Sender>>,
    windows: RefCell<Vec<gtk::Window>>,
    done: Cell<bool>,
}
thread_local! {static ACTIVE: RefCell<Option<Weak<Session>>> = const {RefCell::new(None)};}
impl Session {
    fn finish(&self,result:Answer) {
        if self.done.replace(true) {return;}
        let windows=std::mem::take(&mut *self.windows.borrow_mut());
        for window in windows {window.hide();window.close();}
        if let Some(sender)=self.sender.borrow_mut().take(){let _=sender.send(result);}
        ACTIVE.with(|active|active.borrow_mut().take());
    }
}
pub fn cancel(app:&AppHandle) {
    let _=app.run_on_main_thread(||ACTIVE.with(|active| {
        let current=active.borrow().as_ref().and_then(Weak::upgrade);
        if let Some(current)=current {current.finish(Ok(None));}
    }));
}
pub async fn capture(app:&AppHandle,dutch:bool)->Answer {
    // Let the hidden chooser disappear from the compositor before freezing pixels.
    tokio::time::sleep(Duration::from_millis(250)).await;
    let (tx,rx)=tokio::sync::oneshot::channel();
    app.run_on_main_thread(move || {
        let session=Rc::new(Session{sender:RefCell::new(Some(tx)),windows:RefCell::new(vec![]),done:Cell::new(false)});
        if let Err(error)=start(&session,dutch){session.finish(Err(error));}
    }).map_err(err)?;
    match tokio::time::timeout(Duration::from_secs(125),rx).await {
        Ok(result)=>result.map_err(err)?,
        Err(_)=>{cancel(app);Err("Screen selection timed out".into())}
    }
}
fn start(session:&Rc<Session>,dutch:bool)->Result<(),String> {
    let display=gdk::Display::default().ok_or("No desktop display")?;
    if !display.type_().name().contains("X11") {
        return Err(if dutch {"Schermselectie in deze Mint-test vereist een X11-sessie. Zichtbare pagina en Hele pagina werken ook zonder X11."}
            else {"Desktop selection in this Mint test requires X11. Visible page and Full page do not require X11."}.into());
    }
    let screen=gdk::Screen::default().ok_or("No desktop screen")?;
    // gdk_get_default_root_window is borrowed; retain one reference for this capture.
    let root:Option<gdk::Window>=unsafe{from_glib_none(gdk::ffi::gdk_get_default_root_window())};
    let root=root.ok_or("No X11 root window")?;
    let mut frozen=vec![];
    let mut total_pixels=0i64;
    for index in 0..display.n_monitors() {
        let monitor=display.monitor(index).ok_or("Display configuration changed")?;
        let g=monitor.geometry();let scale=root.scale_factor().max(1);
        let pixels=i64::from(g.width())*i64::from(g.height())*i64::from(scale)*i64::from(scale);
        total_pixels+=pixels;
        if g.width()<1||g.height()<1||pixels>36_000_000||total_pixels>72_000_000 {return Err("Display is too large for a screenshot".into());}
        // Capture every monitor BEFORE showing any selection overlay.
        let image:Option<Pixbuf>=unsafe {from_glib_full(gdk::ffi::gdk_pixbuf_get_from_window(root.to_glib_none().0,g.x(),g.y(),g.width(),g.height()))};
        frozen.push((index,g,image.ok_or("Cannot capture this X11 screen")?));
    }
    if frozen.is_empty(){return Err("No screen available".into());}
    ACTIVE.with(|active|*active.borrow_mut()=Some(Rc::downgrade(session)));
    for (index,g,image) in frozen {
        let window=gtk::Window::new(gtk::WindowType::Toplevel);
        window.set_title("VibeZ screen selection");window.set_decorated(false);
        window.set_keep_above(true);window.set_skip_taskbar_hint(true);window.set_skip_pager_hint(true);
        window.set_default_size(g.width(),g.height());window.move_(g.x(),g.y());
        window.fullscreen_on_monitor(&screen,index);
        let area=gtk::DrawingArea::new();area.set_can_focus(true);
        area.add_events(gdk::EventMask::BUTTON_PRESS_MASK|gdk::EventMask::BUTTON_RELEASE_MASK|gdk::EventMask::POINTER_MOTION_MASK|gdk::EventMask::KEY_PRESS_MASK);
        window.add(&area);
        let start=Rc::new(Cell::new(None::<(f64,f64)>));let end=Rc::new(Cell::new((0.,0.)));
        let (start_draw,end_draw,background)=(start.clone(),end.clone(),image.clone());
        area.connect_draw(move |area,cr| {
            let (w,h)=(f64::from(area.allocated_width()),f64::from(area.allocated_height()));
            let _=cr.save();cr.scale(w/f64::from(background.width()),h/f64::from(background.height()));
            unsafe{gdk::ffi::gdk_cairo_set_source_pixbuf(cr.to_raw_none(),background.to_glib_none().0,0.,0.);}
            let _=cr.paint();let _=cr.restore();
            cr.set_source_rgba(0.,0.,0.,0.28);cr.rectangle(0.,0.,w,h);
            if let Some((sx,sy))=start_draw.get(){let (ex,ey)=end_draw.get();cr.rectangle(sx.min(ex),sy.min(ey),(sx-ex).abs(),(sy-ey).abs());}
            cr.set_fill_rule(gtk::cairo::FillRule::EvenOdd);let _=cr.fill();
            if let Some((sx,sy))=start_draw.get(){let (ex,ey)=end_draw.get();cr.set_source_rgb(1.,0.42,0.21);cr.set_line_width(2.);cr.rectangle(sx.min(ex),sy.min(ey),(sx-ex).abs(),(sy-ey).abs());let _=cr.stroke();}
            cr.set_source_rgba(0.09,0.10,0.12,0.95);cr.rectangle(16.,16.,if dutch {445.} else {380.},42.);let _=cr.fill();
            cr.set_source_rgb(1.,1.,1.);cr.set_font_size(14.);cr.move_to(30.,43.);
            let _=cr.show_text(if dutch {"Sleep een gebied op je scherm.  Esc = annuleren"} else {"Drag an area of your screen.  Esc = cancel"});
            true.into()
        });
        let (down,point,current)=(start.clone(),end.clone(),session.clone());
        area.connect_button_press_event(move |area,event| {
            if event.button()==3 {current.finish(Ok(None));return true.into();}
            if event.button()==1 {let p=event.position();down.set(Some(p));point.set(p);area.grab_focus();area.queue_draw();}
            true.into()
        });
        let (down,point)=(start.clone(),end.clone());
        area.connect_motion_notify_event(move |area,event| {
            if down.get().is_some(){let (x,y)=event.position();point.set((x.clamp(0.,f64::from(area.allocated_width())),y.clamp(0.,f64::from(area.allocated_height()))));area.queue_draw();}
            true.into()
        });
        let current=session.clone();
        area.connect_button_release_event(move |area,event| {
            if event.button()!=1{return true.into();}
            if let Some((sx,sy))=start.take(){
                let (ex,ey)=event.position();let (aw,ah)=(f64::from(area.allocated_width()),f64::from(area.allocated_height()));
                let x=sx.min(ex).clamp(0.,aw);let y=sy.min(ey).clamp(0.,ah);
                let right=sx.max(ex).clamp(0.,aw);let bottom=sy.max(ey).clamp(0.,ah);
                if right-x<4.||bottom-y<4.{current.finish(Ok(None));return true.into();}
                let result=(|| {
                    let (fx,fy)=(f64::from(image.width())/aw,f64::from(image.height())/ah);
                    let (px,py)=((x*fx).floor() as i32,(y*fy).floor() as i32);
                    let (pw,ph)=(((right*fx).ceil() as i32-px).min(image.width()-px),((bottom*fy).ceil() as i32-py).min(image.height()-py));
                    let crop=image.new_subpixbuf(px,py,pw,ph);
                    let crop=crop.scale_simple((right-x).round() as i32,(bottom-y).round() as i32,gtk::gdk_pixbuf::InterpType::Bilinear).ok_or("Cannot crop screenshot")?;
                    let png=crop.save_to_bufferv("png",&[]).map_err(err)?;
                    if png.len()>24*1024*1024{return Err("Screenshot is too large".into());}
                    Ok(Some(png))
                })();current.finish(result);
            }
            true.into()
        });
        let current=session.clone();
        window.connect_key_press_event(move |_,event| {if event.keyval()==gdk::keys::constants::Escape {current.finish(Ok(None));true.into()}else{false.into()}});
        let current=session.clone();window.connect_delete_event(move |_,_|{current.finish(Ok(None));false.into()});
        window.connect_realize(|window|{if let Some(native)=window.window(){native.set_cursor(gdk::Cursor::from_name(&native.display(),"crosshair").as_ref());}});
        session.windows.borrow_mut().push(window);
    }
    for window in session.windows.borrow().iter(){window.show_all();}
    if let Some(window)=session.windows.borrow().first(){window.present();}
    let weak=Rc::downgrade(session);
    glib::timeout_add_local_once(Duration::from_secs(120),move ||{if let Some(current)=weak.upgrade(){current.finish(Ok(None));}});
    Ok(())
}
