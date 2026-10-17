//! Explicit opt-in offline tests for the ordinary Linux client.
#[path="resize_latency.rs"] mod resize_latency;
#[path="fullscreen.rs"] mod fullscreen;
use std::{sync::{mpsc,atomic::Ordering},thread,time::{Duration,Instant}};
use tauri::{AppHandle,Manager,LogicalSize,Webview};
use serde_json::{json,Value};
use gtk::{gdk,prelude::*,glib::translate::*};
fn eval(view:&Webview,js:&str)->Result<String,String>{
 let(tx,rx)=mpsc::channel();view.eval_with_callback(js,move|v|{let _=tx.send(v);}).map_err(crate::err)?;
 let raw=rx.recv_timeout(Duration::from_secs(30)).map_err(crate::err)?;
 Ok(serde_json::from_str::<String>(&raw).unwrap_or(raw))
}
fn value(view:&Webview,js:&str)->Result<Value,String>{serde_json::from_str(&eval(view,js)?).map_err(crate::err)}
fn emit(v:Value){println!("SCROLL_PROBE {v}");}
fn ready(app:&AppHandle,view:&Webview)->Result<(),String>{
 let deadline=Instant::now()+Duration::from_secs(50);
 loop{
  if app.state::<crate::PreviewState>().shell_ready.load(Ordering::Relaxed)&&eval(view,"document.readyState==='complete' && document.title==='Offline test content (not Mistral)'")?=="true"{return Ok(());}
  if Instant::now()>deadline{return Err("Offline page did not become ready".into());} thread::sleep(Duration::from_millis(150));
 }
}
fn size(app:&AppHandle,view:&Webview,w:f64,h:f64)->Result<(),String>{
 let window=app.get_window("main").ok_or("No main window")?;
 let current=window.inner_size().map_err(crate::err)?.to_logical::<f64>(window.scale_factor().map_err(crate::err)?);
 // Reissuing an identical native resize is unnecessary during heavy page work.
 if current.width!=w||current.height!=h{window.set_size(LogicalSize::new(w,h)).map_err(crate::err)?;}
 let deadline=Instant::now()+Duration::from_secs(30);let mut stable=None;let mut last=Value::Null;let mut empty=0;
 let js=format!("JSON.stringify({{ok:innerWidth==={}&&innerHeight==={}&&document.visibilityState==='visible',width:innerWidth,height:innerHeight,visibility:document.visibilityState}})",w as u32,(h-54.) as u32);
 loop{
  let raw=eval(view,&js)?;
  if raw.is_empty(){empty+=1;stable=None;}else{
   last=serde_json::from_str(&raw).map_err(|e|format!("Invalid viewport callback: {e}; raw={raw:?}"))?;
   if last["ok"]==true&&last["width"].as_f64()==Some(w)&&last["height"].as_f64()==Some(h-54.)&&last["visibility"]=="visible"{
    let since=stable.get_or_insert_with(Instant::now);if since.elapsed()>=Duration::from_millis(1600){return Ok(());}
   }else{stable=None;}
  }
  if Instant::now()>deadline{let native=crate::native_layout::geometry(view);return Err(format!("Native viewport did not settle: expected={w}x{}, last={last}, empty_callbacks={empty}, native={native:?}",h-54.));}
  thread::sleep(Duration::from_millis(150));
 }
}
fn wheel(view:&Webview,down:bool)->Result<(),String>{
 let(tx,rx)=mpsc::channel();view.with_webview(move|p|{
  let widget=p.inner();let r=(||{let window=widget.window().ok_or("No native window")?;let pointer=widget.display().default_seat().and_then(|s|s.pointer()).ok_or("No pointer")?;
   let mut event=gdk::Event::new(gdk::EventType::Scroll).downcast::<gdk::EventScroll>().map_err(|_|"Wrong event")?;event.set_device(Some(&pointer));let e=event.as_mut();e.window=window.to_glib_full();e.send_event=0;e.time=0;e.x=500.;e.y=350.;e.state=0;e.direction=if down{gdk::ffi::GDK_SCROLL_DOWN}else{gdk::ffi::GDK_SCROLL_UP};widget.emit_by_name::<bool>("scroll-event",&[&*event]);Ok::<(),&str>(())})();let _=tx.send(r.map_err(str::to_owned));
 }).map_err(crate::err)?;rx.recv_timeout(Duration::from_secs(5)).map_err(crate::err)?
}
fn async_geometry(view:&Webview,label:&str)->Result<Value,String>{
 eval(view,&format!("window.__nativeGeometry=null;__richCheckGeometry({}).then(v=>{{window.__nativeGeometry=v}}).catch(e=>{{window.__nativeGeometry={{pass:false,error:String(e)}}}});true",serde_json::to_string(label).unwrap()))?;
 let deadline=Instant::now()+Duration::from_secs(30);loop{let v=value(view,"JSON.stringify(window.__nativeGeometry)")?;if !v.is_null(){return Ok(v);}if Instant::now()>deadline{return Err("Native resize oracle timed out".into());}thread::sleep(Duration::from_millis(200));}
}
fn lifecycle(app:&AppHandle,view:&Webview)->Result<Value,String>{
 eval(view,include_str!("rich_lifecycle.js"))?;
 eval(view,"__richLifecycleStart();true")?;
 let start=Instant::now();let mut previous=String::new();
 loop{let v=value(view,"JSON.stringify({done:__richLifecycle.done,phase:__richLifecycle.phase})")?;
  if v["done"]==true{break;}
  let phase=v["phase"].as_str().unwrap_or("lifecycle").to_owned();if phase!=previous{emit(json!({"event":"phase","name":phase}));previous=phase;}
  if start.elapsed()>Duration::from_secs(360){emit(json!({"event":"lifecycle","result":value(view,"JSON.stringify(__richLifecycle)")?}));return Err(format!("Lifecycle timed out in {previous}"));}thread::sleep(Duration::from_millis(350));
 }
 let mut result=value(view,"JSON.stringify(__richLifecycle)")?;
 if result["ok"]!=true{emit(json!({"event":"lifecycle","result":result}));return Err("Offline lifecycle checks failed".into());}
 let mut resizes=Vec::new();
 for(w,h)in [(1024.,760.),(1440.,900.),(1280.,840.)]{emit(json!({"event":"phase","name":"native-resize","width":w,"height":h}));size(app,view,w,h)?;let row=async_geometry(view,&format!("Native window {w}x{h}"))?;if row["pass"]!=true{return Err(format!("Native resize geometry failed: {row}"));}resizes.push(row);}
 // Search through real WebKit FindController using the same API as Ctrl+F.
 emit(json!({"event":"phase","name":"native-find"}));
 let mut searches=Vec::new();
 for term in ["VIBEZ_UNIQUE_REPLY_00_END","VIBEZ_UNIQUE_REPLY_20_END","VIBEZ_UNIQUE_REPLY_39_END","VIBEZ_NO_SUCH_MARKER_6d209"] {
  let count=tauri::async_runtime::block_on(crate::native_find::search(view,term.into()))?;
  let expected=if term.contains("NO_SUCH"){0}else{1};
  let paused=value(view,"JSON.stringify(window.__vibezRichRender.status())")?;
  searches.push(json!({"term":term,"matches":count,"expected":expected,"helper":paused}));
  if count!=expected{return Err(format!("Native find count wrong: {count} != {expected}"));}
 }
 emit(json!({"event":"native-search-results","results":searches}));
 tauri::async_runtime::block_on(crate::native_find::finish(view))?;thread::sleep(Duration::from_millis(700));
 tauri::async_runtime::block_on(crate::native_find::smoke_dialog(app,view))?;
 let resumed=value(view,"JSON.stringify(window.__vibezRichRender.status())")?;
 if resumed["optimized"].as_u64().unwrap_or(0)==0 {return Err("Optimization did not resume after native find".into());}
 // Deliberately make the pause IPC callback miss its five-second deadline.
 // A failed capture must release its pause once WebKit drains the queued work.
 emit(json!({"event":"phase","name":"capture-timeout-recovery"}));
 view.eval("(() => {const until=performance.now()+6000;while(performance.now()<until){};window.__captureTimeoutBusyDone=true;})()").map_err(crate::err)?;
 let capture_started=Instant::now();
 let capture_error=tauri::async_runtime::block_on(crate::screenshots::capture_preview(app,"visible")).err().ok_or("Busy WebKit capture unexpectedly succeeded; timeout path was not exercised")?;
 if !capture_error.to_lowercase().contains("deadline")&&!capture_error.to_lowercase().contains("timed out"){return Err(format!("Capture failed before the intended pause timeout: {capture_error}"));}
 let deadline=Instant::now()+Duration::from_secs(12);
 let capture_recovered=loop{
  let status=value(view,"JSON.stringify({done:window.__captureTimeoutBusyDone===true,helper:window.__vibezRichRender.status()})")?;
  let helper=&status["helper"];
  let unpaused=helper["paused"].as_array().is_some_and(|reasons|!reasons.iter().any(|reason|reason=="capture"));
  if status["done"]==true&&unpaused&&helper["optimized"].as_u64().unwrap_or(0)>0&&helper["running"]==false&&helper["working"]!=true&&helper["pendingMeasurements"].as_u64().unwrap_or(0)==0{break status;}
  if Instant::now()>deadline{return Err(format!("Failed capture left rendering paused: {status}"));}thread::sleep(Duration::from_millis(150));
 };
 result["capture_timeout_recovery"]=json!({"pass":true,"error":capture_error,"elapsedMs":capture_started.elapsed().as_millis(),"after":capture_recovered,"clipboardOperationReached":false});
 result["native_resizes"]=json!(resizes);result["native_searches"]=json!(searches);result["after_find"]=resumed;
 emit(json!({"event":"lifecycle","result":result.clone()}));Ok(result)
}
fn benchmark(view:&Webview)->Result<Value,String>{
 if std::env::var_os("VIBEZ_RICH_TEST_BASELINE").is_some(){eval(view,"__vibezRichRender.pause('baseline');true")?;}
 emit(json!({"event":"phase","name":"idle"}));thread::sleep(Duration::from_secs(5));
 eval(view,"window.__invalidViewport=false;window.__checkViewport=()=>{if(innerWidth!==1280||innerHeight!==786||document.visibilityState!=='visible')__invalidViewport=true;};addEventListener('resize',__checkViewport);document.addEventListener('visibilitychange',__checkViewport);__checkViewport();true")?;
 emit(json!({"event":"phase","name":"wheel"}));let start=Instant::now();let mut sent=0;
 while start.elapsed()<Duration::from_secs(30){wheel(view,(start.elapsed().as_secs()/4)%2==0)?;sent+=1;thread::sleep(Duration::from_millis(100));}
 emit(json!({"event":"phase","name":"post-wheel","sent":sent}));thread::sleep(Duration::from_secs(20));
 let stats=value(view,"JSON.stringify(__benchResult())")?;let received=stats["trustedWheelEvents"].as_u64().unwrap_or(0);
 if value(view,"JSON.stringify({invalid:__invalidViewport})")?["invalid"]==true||received<sent*95/100||received>sent||stats["innerWidth"]!=1280||stats["innerHeight"]!=786{return Err(format!("Invalid native wheel test: sent={sent}, stats={stats}"));}
 emit(json!({"event":"input","sent":sent,"received":received}));Ok(stats)
}
fn anonymous_mistral(app:&AppHandle,view:&Webview)->Result<(),String>{
 // Same ordinary language bootstrap, explicitly allowed only in a fresh test profile.
 crate::site_language::request_anonymous_probe(app);
 emit(json!({"event":"phase","name":"anonymous-public-navigation"}));
 let deadline=Instant::now()+Duration::from_secs(65);let mut public_since=None;
 let inspect=r#"JSON.stringify((()=>{const allowed=['https://chat.mistral.ai','https://vibe.mistral.ai'].includes(location.origin);const selectors=['main [data-message-author-role="assistant"]','main [data-role="assistant"][data-message-id]','main [data-testid="assistant-message"]','main [data-testid="message-assistant"]'];return{origin:location.origin,publicOrigin:allowed,title:allowed?document.title:null,readyState:document.readyState,visibility:document.visibilityState,width:innerWidth,height:innerHeight,helper:allowed?(window.__vibezRichRender?.status()||null):null,selectorCounts:allowed?Object.fromEntries(selectors.map(s=>[s,document.querySelectorAll(s).length])):{},challengePresent:allowed&&Boolean(document.querySelector('iframe[src*="challenges.cloudflare.com"],#challenge-running,#challenge-stage,script[src*="/cdn-cgi/challenge-platform/"]'))}})())"#;
 let final_state=loop{
  let state=value(view,inspect)?;
  if state["publicOrigin"]==true{let since=public_since.get_or_insert_with(Instant::now);if since.elapsed()>=Duration::from_secs(20){break state;}}
  if Instant::now()>deadline{break state;}
  thread::sleep(Duration::from_millis(500));
 };
 let title=final_state["title"].as_str().unwrap_or("").to_lowercase();
 let classification=if final_state["publicOrigin"]!=true{"public-navigation-not-observed"}else if final_state["challengePresent"]==true||title.contains("just a moment")||title.contains("attention required"){"public-challenge-page"}else if final_state["helper"].is_null(){"public-page-helper-unavailable"}else{"anonymous-public-page-helper-present"};
 let result=json!({"event":"complete","mode":"mistral","classification":classification,"state":final_state,"authenticConversationReproduction":false,"limitations":"Anonymous public navigation only; no sign-in, challenge interaction, message, cookies, input values or conversation text inspected."});
 emit(result);Ok(())
}
fn run(app:&AppHandle,mode:&str)->Result<(),String>{
 if !["lifecycle","resize","wheel","fullscreen","mistral"].contains(&mode){return Err("Unknown rich-chat test mode".into());}
 if std::env::var_os("VIBEZ_RICH_TEST_BASELINE").is_some()&&mode!="wheel"{return Err("Baseline is valid only for wheel mode".into());}
 let view=app.get_webview("vibe").ok_or("No view")?;ready(app,&view)?;
 if mode=="mistral"{return anonymous_mistral(app,&view);}
 // Native layouts can briefly report 1x1 during startup; wait before fixture.
 size(app,&view,1280.,840.)?;
 // Tauri reports JavaScript exceptions as an ordinary callback result. Capture
 // fixture failures explicitly rather than misreporting them as a missing helper.
 let fixture_source=if mode=="fullscreen"&&std::env::var("VIBEZ_RICH_TEST_SECTIONS").as_deref()==Ok("2"){include_str!("rich_fixture.js").replace("{length:16}","{length:2}")}else{include_str!("rich_fixture.js").to_owned()};
 let fixture_js=format!(r#"(() => {{try {{const count=
{};
return JSON.stringify({{ok:true,count}});}}catch(e){{const chat=document.querySelector('#chat');return JSON.stringify({{ok:false,error:String(e),stack:String(e.stack||''),width:innerWidth,height:innerHeight,visibility:document.visibilityState,stylesheets:document.styleSheets.length,chatHeight:chat?.clientHeight||0,display:document.querySelector('.app')?getComputedStyle(document.querySelector('.app')).display:null}});}}}})()"#,fixture_source);
 for attempt in 0..2 {
  let built=value(&view,&fixture_js)?;
  if built["ok"]==true {break;}
  emit(json!({"event":"fixture-error","attempt":attempt,"details":built}));
  let geometry_changed=built["width"]!=1280||built["height"]!=786||built["visibility"]!="visible";
  if attempt==0&&geometry_changed&&built["error"]=="Error: Fixture CSS or scroll pane is invalid"{size(app,&view,1280.,840.)?;continue;}
  return Err(format!("Offline fixture failed: {built}"));
 }
 // The native viewport was established before building the large DOM. Avoid
 // another native resize/stability loop in the middle of its queued layout.
 // Automated cases validate the final viewport again after helper settlement.

 // Explicit offline comparison only; the live injection always uses the fixed helper.
 let helper_script=crate::rich_render::SCRIPT;
 let helper_js=format!(r#"(() => {{try {{
{}
return JSON.stringify({{ok:Boolean(window.__vibezRichRender),marker:document.documentElement.dataset.vibezOfflineFixture,origin:location.origin,supported:CSS.supports('content-visibility','auto')}});}}catch(e){{return JSON.stringify({{ok:false,error:String(e),stack:String(e.stack||'')}});}}}})()"#,helper_script);
 let installed=value(&view,&helper_js)?;
 if installed["ok"]!=true{return Err(format!("Render helper could not start: {installed}"));}
 eval(&view,"window.__initialRichReady=false;__vibezRichRender.refresh().then(()=>{window.__initialRichReady=true});true")?;
 {
  let deadline=Instant::now()+Duration::from_secs(150);
  loop{let state=value(&view,"JSON.stringify({ready:window.__initialRichReady,status:__vibezRichRender.status()})")?;
   if state["ready"]==true&&state["status"]["running"]==false&&state["status"]["working"]!=true&&state["status"]["pendingMeasurements"].as_u64().unwrap_or(0)==0&&state["status"]["optimized"].as_u64().unwrap_or(0)>=39{break;}
   if Instant::now()>deadline{return Err(format!("Initial helper did not settle: {state}"));}thread::sleep(Duration::from_millis(250));
  }
 }
 let fixture_stats=value(&view,"JSON.stringify(__benchResult())")?;
 if fixture_stats["innerWidth"]!=1280||fixture_stats["innerHeight"]!=786||value(&view,"JSON.stringify({visibility:document.visibilityState})")?["visibility"]!="visible"{return Err(format!("Invalid settled fixture viewport: {fixture_stats}"));}
 emit(json!({"event":"fixture","stats":fixture_stats,"helper":value(&view,"JSON.stringify(__vibezRichRender.status())")?}));
 if mode=="resize"{
  let result=self::resize_latency::run(app,&view)?;emit(json!({"event":"resize-result","result":result}));
  emit(json!({"event":"complete","mode":"resize","stats":value(&view,"JSON.stringify(__benchResult())")?}));return Ok(());
 }
 if mode=="fullscreen"{let result=self::fullscreen::run(app,&view)?;emit(json!({"event":"complete","mode":"fullscreen","result":result}));return Ok(());}
 let stats=if mode=="lifecycle"{lifecycle(app,&view)?;value(&view,"JSON.stringify(__benchResult())")?}else{benchmark(&view)?};
 emit(json!({"event":"complete","stats":stats,"mode":mode}));Ok(())
}
pub fn start(app:AppHandle,mode:&str){let mode=mode.to_owned();thread::spawn(move||{let result=run(&app,&mode);if let Err(error)=&result{emit(json!({"event":"error","error":error}));}{app.exit(if result.is_ok(){0}else{1});}});}
