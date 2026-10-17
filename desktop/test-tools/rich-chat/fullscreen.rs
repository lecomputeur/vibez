//! Native geometry and own-WebKit PNG checks; synthetic sticky headers are preserved.
use std::{path::PathBuf, sync::mpsc, thread, time::{Duration,Instant}};
use gtk::prelude::*;
use tauri::{AppHandle,Manager,Webview,LogicalPosition,LogicalSize};
use serde_json::{json,Value};
fn eval(view:&Webview,script:&str)->Result<Value,String>{
 let(tx,rx)=mpsc::channel();view.eval_with_callback(script,move|raw|{let _=tx.send(raw);}).map_err(crate::err)?;
 let raw=rx.recv_timeout(Duration::from_secs(30)).map_err(crate::err)?;
 let text=serde_json::from_str::<String>(&raw).unwrap_or(raw);
 serde_json::from_str(&text).map_err(|error|format!("Fullscreen probe JSON: {error}: {text:?}"))
}
fn native(app:&AppHandle,view:&Webview)->Result<Value,String>{
 let(tx,rx)=mpsc::channel();view.with_webview(move|platform|{
  let widget=platform.inner();let a=widget.allocation();
  let window=widget.toplevel().and_then(|node|node.downcast::<gtk::Window>().ok());
  let full=window.as_ref().and_then(|node|node.window()).is_some_and(|window|window.state().contains(gtk::gdk::WindowState::FULLSCREEN));
  let _=tx.send(json!({"x":a.x(),"y":a.y(),"width":a.width(),"height":a.height(),"mapped":widget.is_mapped(),"nativeFullscreen":full}));
 }).map_err(crate::err)?;
 let mut value=rx.recv_timeout(Duration::from_secs(5)).map_err(crate::err)?;
 let window=app.get_window("main").ok_or("No main window")?;let pos=window.outer_position().map_err(crate::err)?;let size=window.outer_size().map_err(crate::err)?;
 let scale=window.scale_factor().map_err(crate::err)?;let inner=window.inner_size().map_err(crate::err)?.to_logical::<f64>(scale);
 value["innerLogical"]=json!({"width":inner.width.round()as u32,"height":inner.height.round()as u32,"scaleFactor":scale});
 value["outer"]=json!({"x":pos.x,"y":pos.y,"width":size.width,"height":size.height});
 value["tauriFullscreen"]=json!(window.is_fullscreen().map_err(crate::err)?);
 value["maximized"]=json!(window.is_maximized().map_err(crate::err)?);Ok(value)
}
fn settle(app:&AppHandle,view:&Webview,full:bool)->Result<Value,String>{
 let until=Instant::now()+Duration::from_secs(35);let mut stable=0;let mut previous=String::new();
 loop{
  let content=native(app,view)?;let shell=native(app,&app.get_webview("shell").ok_or("No shell")?)?;
  let page=eval(view,"JSON.stringify({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,visibility:document.visibilityState,helper:window.__vibezRichRender?.status()})")?;
  let x=content["outer"]["x"].as_i64().unwrap_or(-10000);let width=content["outer"]["width"].as_i64().unwrap_or(10000);
  let bounds=content["x"]==0&&content["y"]==54&&shell["x"]==0&&shell["y"]==0&&shell["height"]==54&&shell["width"]==content["width"]
   &&content["width"]==content["innerLogical"]["width"]
   &&content["height"].as_i64().unwrap_or(-10000)+54==content["innerLogical"]["height"].as_i64().unwrap_or(0)
   &&page["width"]==content["width"]&&page["height"]==content["height"]&&page["visibility"]=="visible"
   &&content["nativeFullscreen"]==full&&content["tauriFullscreen"]==full&&x>=0&&x+width<=2560;
  let queue=page["helper"]["running"]==false&&page["helper"]["working"]!=true&&page["helper"]["pendingMeasurements"].as_u64().unwrap_or(0)==0;
  let current=json!({"content":content,"shell":shell,"page":page,"boundsPass":bounds,"queuePass":queue});
  let key=format!("{}:{}:{}:{}",current["content"]["width"],current["content"]["height"],current["content"]["outer"]["x"],current["content"]["outer"]["y"]);
  stable=if bounds&&queue&&key==previous{stable+1}else{0};previous=key;
  if stable>=3{return Ok(current);}
  if Instant::now()>until{return Err(format!("Fullscreen visual geometry did not settle: {current}"));}
  thread::sleep(Duration::from_millis(150));
 }
}
fn fullscreen_left(app:&AppHandle,view:&Webview)->Result<Value,String>{
 let window=app.get_window("main").ok_or("No main window")?;
 // Set the explicit left-monitor hint before asking Tauri to track fullscreen.
 let(tx,rx)=mpsc::channel();view.with_webview(move|platform|{
  let answer=(||{
   let window=platform.inner().toplevel().and_then(|node|node.downcast::<gtk::Window>().ok()).ok_or("No GTK window")?;
   let display=window.display();let screen=display.default_screen();
   let index=(0..display.n_monitors()).find(|index|display.monitor(*index).is_some_and(|monitor|monitor.geometry().x()==0)).ok_or("No left monitor x=0")?;
   let geometry=display.monitor(index).ok_or("Left monitor unavailable")?.geometry();
   window.fullscreen_on_monitor(&screen,index);
   Ok::<Value,&str>(json!({"index":index,"x":geometry.x(),"y":geometry.y(),"width":geometry.width(),"height":geometry.height()}))
  })();let _=tx.send(answer.map_err(str::to_owned));
 }).map_err(crate::err)?;
 let monitor=rx.recv_timeout(Duration::from_secs(5)).map_err(crate::err)??;
 window.set_fullscreen(true).map_err(crate::err)?;Ok(monitor)
}
fn target(view:&Webview)->Result<Value,String>{
 eval(view,r#"JSON.stringify((()=>{const pane=document.querySelector('#chat'),box=document.querySelector('[data-vibez-reply="20"] .codebox');if(!pane||!box)throw Error('Known synthetic codebox absent');pane.scrollTop+=box.getBoundingClientRect().top-pane.getBoundingClientRect().top+320;return {prepared:true}})())"#)?;
 thread::sleep(Duration::from_millis(200));
 eval(view,r#"JSON.stringify((()=>{const pane=document.querySelector('#chat'),box=document.querySelector('[data-vibez-reply="20"] .codebox'),head=box.querySelector('.code-head'),pre=box.querySelector('pre');const rect=e=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height,top:r.top,bottom:r.bottom}};return{head:rect(head),pre:rect(pre),box:rect(box),pane:rect(pane),paddingTop:parseFloat(getComputedStyle(pane).paddingTop)||0,position:getComputedStyle(head).position,scrollTop:pane.scrollTop,width:innerWidth,height:innerHeight,dpr:devicePixelRatio}})())"#)
}
pub fn run(app:&AppHandle,view:&Webview)->Result<Value,String>{
 let output=PathBuf::from(std::env::var("VIBEZ_RICH_TEST_OUTPUT").unwrap_or_else(|_|"/tmp/vibez-rich-fullscreen".into()));std::fs::create_dir_all(&output).map_err(crate::err)?;
 let window=app.get_window("main").ok_or("No main window")?;
 let outcome=(||{
  let fixture=eval(view,"JSON.stringify({assistantAnswers:document.querySelectorAll('article.assistant').length,sections:document.querySelectorAll('.rich-section').length,codeBlocks:document.querySelectorAll('.codebox').length,nodes:document.querySelectorAll('*').length,textCharacters:document.body.textContent.length})")?;
  let mut rows=Vec::new();let mut left_monitor=Value::Null;
  window.set_fullscreen(false).map_err(crate::err)?;window.unmaximize().map_err(crate::err)?;window.set_position(LogicalPosition::new(64.,64.)).map_err(crate::err)?;window.set_size(LogicalSize::new(1280.,840.)).map_err(crate::err)?;
  for state in ["normal","maximized","fullscreen","left-fullscreen","unmaximized"]{
   match state{"maximized"=>window.maximize().map_err(crate::err)?,"fullscreen"=>{left_monitor=fullscreen_left(app,view)?;},"left-fullscreen"=>window.set_fullscreen(false).map_err(crate::err)?,"unmaximized"=>window.unmaximize().map_err(crate::err)?,_=>{}}
   let geometry=settle(app,view,state=="fullscreen")?;
   if state=="maximized"&&geometry["content"]["maximized"]!=true{return Err(format!("Maximize was not applied: {geometry}"));}
   let layout=target(view)?;
   if layout["position"]!="sticky"{return Err(format!("Fixture sticky header changed unexpectedly: {layout}"));}
   let png=super::resize_latency::snapshot(view)?;
   let decoded=gtk::gdk_pixbuf::PixbufLoader::new();gtk::gdk_pixbuf::prelude::PixbufLoaderExt::write(&decoded,&png).map_err(crate::err)?;gtk::gdk_pixbuf::prelude::PixbufLoaderExt::close(&decoded).map_err(crate::err)?;let image=gtk::gdk_pixbuf::prelude::PixbufLoaderExt::pixbuf(&decoded).ok_or("No PNG pixels")?;
   let dpr=layout["dpr"].as_f64().unwrap_or(1.);let dimensions=(image.width()as f64-layout["width"].as_f64().unwrap_or(0.)*dpr).abs()<=1.&&(image.height()as f64-layout["height"].as_f64().unwrap_or(0.)*dpr).abs()<=1.;
   let path=output.join(format!("{state}.png"));std::fs::write(&path,&png).map_err(crate::err)?;
   let row=json!({"state":state,"geometry":geometry,"layout":layout,"dimensionsPass":dimensions,"pngWidth":image.width(),"pngHeight":image.height(),"path":path});
   println!("SCROLL_PROBE {}",json!({"event":"fullscreen-visual","result":row}));rows.push(row.clone());
   if !dimensions{return Err(format!("Fullscreen PNG dimensions failed: {row}"));}
  }
  Ok::<Value,String>(json!({"ok":true,"leftMonitor":left_monitor,"checks":rows,"fixture":fixture,"sectionsPerAnswer":std::env::var("VIBEZ_RICH_TEST_SECTIONS").unwrap_or_else(|_|"16".into()),"captureScope":"Only this synthetic WebKit view; no desktop or private UI pixels; this is not OS compositor proof"}))
 })();
 let _=window.set_fullscreen(false);let _=window.unmaximize();let _=window.set_position(LogicalPosition::new(64.,64.));let _=window.set_size(LogicalSize::new(1280.,840.));
 if let Ok(result)=&outcome{std::fs::write(output.join("fullscreen.json"),serde_json::to_vec_pretty(result).map_err(crate::err)?).map_err(crate::err)?;}outcome
}
