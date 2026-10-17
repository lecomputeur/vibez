//! Offline native resize-latency probe. Native PNGs prove actual WebKit pixels,
//! not compositor presentation; no full-document height oracle runs while timed.
use std::{sync::mpsc, thread, time::{Duration, Instant, SystemTime, UNIX_EPOCH}, path::PathBuf};
use gtk::{gdk, prelude::*, glib::translate::*};
use tauri::{AppHandle, LogicalSize, Manager, Webview};
use webkit2gtk::WebViewExt;
use serde_json::{json, Value};

fn wall_ms() -> f64 { (SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs_f64() * 1000.).floor() }
fn emit(value: Value) { println!("SCROLL_PROBE {value}"); }
fn eval_json(view: &Webview, script: &str) -> Result<Value, String> {
    let (tx, rx) = mpsc::channel();
    view.eval_with_callback(script, move |raw| { let _ = tx.send(raw); }).map_err(crate::err)?;
    let raw = rx.recv_timeout(Duration::from_secs(35)).map_err(crate::err)?;
    let text = serde_json::from_str::<String>(&raw).unwrap_or(raw);
    serde_json::from_str(&text).map_err(|error| format!("Resize probe callback invalid JSON: {error}: {text:?}"))
}
fn report(view: &Webview) -> Result<Value, String> { eval_json(view, "JSON.stringify(window.__resizeLatency.report())") }
fn allocation(view: &Webview) -> Result<Value, String> {
    let (tx, rx) = mpsc::channel();
    view.with_webview(move |platform| {
        let widget = platform.inner(); let a = widget.allocation();
        let _ = tx.send(json!({"wallMs":wall_ms(),"x":a.x(),"y":a.y(),"width":a.width(),"height":a.height(),"mapped":widget.is_mapped()}));
    }).map_err(crate::err)?;
    rx.recv_timeout(Duration::from_secs(5)).map_err(crate::err)
}
fn wheel(view: &Webview, down: bool) -> Result<(), String> {
    let (tx, rx) = mpsc::channel();
    view.with_webview(move |platform| {
        let widget = platform.inner();
        let answer = (|| {
            let window = widget.window().ok_or("No native scroll window")?;
            let pointer = widget.display().default_seat().and_then(|seat| seat.pointer()).ok_or("No native pointer")?;
            let mut event = gdk::Event::new(gdk::EventType::Scroll).downcast::<gdk::EventScroll>().map_err(|_|"Wrong native event type")?;
            event.set_device(Some(&pointer));
            let e = event.as_mut(); e.window = window.to_glib_full(); e.send_event = 0; e.time = 0; e.x = 500.; e.y = 350.; e.state = 0; e.direction = if down {gdk::ffi::GDK_SCROLL_DOWN} else {gdk::ffi::GDK_SCROLL_UP};
            widget.emit_by_name::<bool>("scroll-event", &[&*event]);
            Ok::<(), &str>(())
        })();
        let _ = tx.send(answer.map_err(str::to_owned));
    }).map_err(crate::err)?;
    rx.recv_timeout(Duration::from_secs(5)).map_err(crate::err)?
}
pub(super) fn snapshot(view: &Webview) -> Result<Vec<u8>, String> {
    let (tx, rx) = mpsc::channel();
    let cancel = gtk::gio::Cancellable::new(); let token = cancel.clone();
    view.with_webview(move |platform| {
        platform.inner().snapshot(webkit2gtk::SnapshotRegion::Visible, webkit2gtk::SnapshotOptions::empty(), Some(&token), move |answer| {
            let pixels = (|| {
                let surface = answer.map_err(crate::err)?;
                let image = gtk::cairo::ImageSurface::try_from(surface.clone()).map_err(|_|"Snapshot returned non-image surface".to_string())?;
                let pixels = gtk::gdk::pixbuf_get_from_surface(&surface, 0, 0, image.width(), image.height()).ok_or("Cannot read native WebKit pixels")?;
                pixels.save_to_bufferv("png", &[]).map_err(crate::err)
            })();
            let _ = tx.send(pixels);
        });
    }).map_err(crate::err)?;
    match rx.recv_timeout(Duration::from_secs(15)) {
        Ok(answer) => answer,
        Err(error) => { cancel.cancel(); Err(format!("Native snapshot callback: {error}")) }
    }
}
fn pixels(bytes: &[u8]) -> Result<Value, String> {
    let loader = gtk::gdk_pixbuf::PixbufLoader::new();
    loader.write(bytes).map_err(crate::err)?;
    loader.close().map_err(crate::err)?;
    let image = loader.pixbuf().ok_or("Native PNG decoder returned no pixels")?;
    let (width, height) = (image.width() as u32, image.height() as u32);
    let channels=image.n_channels() as usize; let stride=image.rowstride() as usize;
    if channels<3 {return Err("Native PNG has fewer than three color channels".into());}
    let storage=image.read_pixel_bytes(); let data=storage.as_ref();
    let rgb_at=|x:u32,y:u32| {let index=y as usize*stride+x as usize*channels;[data[index],data[index+1],data[index+2]]};
    if width < 100 || height < 100 { return Ok(json!({"nonblank":false,"width":width,"height":height})); }
    // The tiny frame patch is at CSS right:8/top:8. DPR is inferred from the
    // final 1280x786 viewport, rather than assuming native pixels equal CSS px.
    let sx = width as f64 / 1280.; let sy = height as f64 / 786.;
    let px = ((1280. - 20.) * sx).floor().clamp(0., (width-1) as f64) as u32;
    let py = (16. * sy).floor().clamp(0., (height-1) as f64) as u32;
    let patch = rgb_at(px, py);
    let patch_id = if patch[2].abs_diff(170) <= 2 && (40..240).contains(&patch[0]) && (40..240).contains(&patch[1]) {
        Some(u32::from(patch[0]-40) + 200 * u32::from(patch[1]-40))
    } else { None };
    let x0 = (width as f64 * 0.28) as u32; let x1 = (width as f64 * 0.95) as u32;
    let y0 = (height as f64 * 0.20) as u32; let y1 = (height as f64 * 0.79) as u32;
    let mut bright = 0u64; let mut tiles = [false; 20]; let mut bands = [false; 4];
    for y in (y0..y1).step_by(2) { for x in (x0..x1).step_by(2) {
        let rgb = rgb_at(x,y);
        if *rgb.iter().max().unwrap() >= 120 {
            bright += 1;
            let column = ((x-x0)*5/(x1-x0)).min(4) as usize;
            let row = ((y-y0)*4/(y1-y0)).min(3) as usize;
            tiles[row*5+column] = true; bands[row] = true;
        }
    }}
    let occupied = tiles.into_iter().filter(|value|*value).count();
    let vertical = bands.into_iter().filter(|value|*value).count();
    Ok(json!({"width":width,"height":height,"brightSamples":bright,"occupiedTiles":occupied,"occupiedVerticalBands":vertical,"nonblank":bright>=150&&occupied>=6&&vertical>=3,"patchRgb":patch,"patchId":patch_id}))
}
fn number(value: &Value, key: &str) -> f64 { value[key].as_f64().unwrap_or(f64::NAN) }
fn first_after<'a>(rows: &'a Value, since: f64, require_viewport: bool) -> Option<&'a Value> {
    rows.as_array()?.iter().find(|row| number(row,"wallMs")>=since && (!require_viewport || (row["width"]==1280&&row["height"]==786)))
}
fn max_gap(rows: &Value, from: f64, through: f64) -> f64 {
    rows.as_array().into_iter().flatten().filter(|row| {
        let end=number(row,"wallMs"); let gap=number(row,"gapMs"); end>=from&&end-gap<=through
    }).map(|row|number(row,"gapMs")).fold(0., f64::max)
}

pub fn run(app: &AppHandle, view: &Webview) -> Result<Value, String> {
    let label = std::env::var("VIBEZ_RICH_TEST_LABEL").unwrap_or_else(|_|"resize".into());
    let output = PathBuf::from(std::env::var("VIBEZ_RICH_TEST_OUTPUT").unwrap_or_else(|_|"/tmp/vibez-resize-latency".into()));
    std::fs::create_dir_all(&output).map_err(crate::err)?;
    let setup = format!("JSON.stringify({})",include_str!("resize_latency.js"));
    let installed=eval_json(view,&setup)?;
    emit(json!({"event":"phase","name":"resize-warmup","label":label,"installed":installed}));
    thread::sleep(Duration::from_millis(800));
    let before=report(view)?;
    if before["width"]!=1280||before["height"]!=786||before["visibility"]!="visible" {return Err(format!("Resize test has invalid starting viewport: {before}"));}
    if before["helper"]["paused"].as_array().is_none_or(|reasons|!reasons.is_empty())
        ||before["helper"]["running"]!=false
        ||before["helper"]["working"].as_bool().is_some_and(|working|working)
        ||before["helper"]["pendingMeasurements"].as_u64().is_some_and(|pending|pending>0) {
        return Err(format!("Resize test helper is not active and settled: {}",before["helper"]));
    }
    let window=app.get_window("main").ok_or("No main native window")?;
    let mut requests=Vec::new();
    let mut waypoints=Vec::new();
    let anchors=[(1280.,840.),(980.,720.),(1440.,900.),(1280.,840.)];
    for pair in anchors.windows(2) { for step in 1..=12 {
        let t=step as f64/12.; let w:f64=pair[0].0+(pair[1].0-pair[0].0)*t; let h:f64=pair[0].1+(pair[1].1-pair[0].1)*t;
        waypoints.push((w.round(),h.round()));
    }}
    emit(json!({"event":"phase","name":"native-resize-drag","label":label,"requests":waypoints.len(),"requestedStepMs":60}));
    let start=Instant::now(); let native_start_wall=wall_ms(); let mut final_request_wall=native_start_wall; let mut final_request_elapsed=0.;
    for (index,(width,height)) in waypoints.iter().enumerate() {
        let requested=wall_ms();
        if index+1==waypoints.len(){final_request_wall=requested;final_request_elapsed=start.elapsed().as_secs_f64()*1000.;}
        window.set_size(LogicalSize::new(*width,*height)).map_err(crate::err)?;
        thread::sleep(Duration::from_millis(60));
        let actual=allocation(view)?;
        requests.push(json!({"index":index,"requestedWallMs":requested,"width":width,"height":height,"allocation":actual}));
    }
    let wheel_wall=wall_ms(); wheel(view,false)?;
    emit(json!({"event":"phase","name":"resize-recovery","label":label,"nativeFinalRequestWallMs":final_request_wall,"wheelInjectedWallMs":wheel_wall}));
    let mut captures=Vec::new(); let mut fresh_capture=None; let mut stable_capture=None;
    let mut recovered_wheel_wall=None;
    let minimum_observation_ms=5000.; let stable_window_ms=2000.;
    let deadline=Instant::now()+Duration::from_secs(70);
    while Instant::now()<deadline {
        let requested=wall_ms(); let snap_start=Instant::now();
        match snapshot(view) {
            Ok(bytes) => {
                let completed=wall_ms(); let snapshot_ms=snap_start.elapsed().as_secs_f64()*1000.; let metrics=pixels(&bytes)?;
                let js=report(view)?;
                let patch_id=metrics["patchId"].as_u64();
                let patch_frame=js["frames"].as_array().and_then(|frames|frames.iter().find(|frame|frame["id"].as_u64()==patch_id));
                let fresh=patch_frame.is_some_and(|frame|number(frame,"wallMs")>=final_request_wall&&frame["width"]==1280&&frame["height"]==786);
                let final_pixel_dimensions=patch_frame.is_some_and(|frame|{
                    let dpr=frame["dpr"].as_f64().unwrap_or(1.);
                    (number(&metrics,"width")-1280.*dpr).abs()<=1.&&(number(&metrics,"height")-786.*dpr).abs()<=1.
                });
                let valid=metrics["nonblank"]==true&&fresh&&final_pixel_dimensions&&js["width"]==1280&&js["height"]==786&&js["visibility"]=="visible";
                let observed=number(&js,"currentWallMs");
                let recent_raf_gap=max_gap(&js["frames"],observed-stable_window_ms,observed);
                let recent_heartbeat_gap=max_gap(&js["heartbeats"],observed-stable_window_ms,observed);
                let last_frame=js["frames"].as_array().and_then(|rows|rows.last());
                let last_heartbeat=js["heartbeats"].as_array().and_then(|rows|rows.last());
                let additional_measurements=number(&js["helper"],"measurements")-number(&before["helper"],"measurements");
                let resize_work_completed=js["helper"]["running"]==false
                    &&number(&js["helper"],"passes")>number(&before["helper"],"passes")
                    &&additional_measurements>=number(&before["helper"],"optimized")
                    &&js["helper"]["pendingMeasurements"].as_u64().is_none_or(|pending|pending==0)
                    &&js["helper"]["working"].as_bool().is_none_or(|working|!working);
                // A successful early frame is insufficient: a debounced resize
                // handler can freeze the page immediately afterwards. Require
                // five seconds of observation and a recent, continuous recovery
                // interval, including a new actual-pixel capture.
                let stable=valid&&resize_work_completed&&observed-final_request_wall>=minimum_observation_ms
                    &&recent_raf_gap<250.&&recent_heartbeat_gap<350.
                    &&last_frame.is_some_and(|frame|observed-number(frame,"wallMs")<150.)
                    &&last_heartbeat.is_some_and(|beat|observed-number(beat,"wallMs")<300.);
                let mut row=json!({"requestedWallMs":requested,"completedWallMs":completed,"snapshotMs":snapshot_ms,"afterFinalRequestMs":completed-final_request_wall,"pixels":metrics,"freshPatch":fresh,"finalPixelDimensions":final_pixel_dimensions,"patchFrame":patch_frame,"accepted":valid,"stableRecovery":stable,"resizeWorkCompleted":resize_work_completed,"additionalHelperMeasurements":additional_measurements,"helper":js["helper"],"recentRafGapMs":recent_raf_gap,"recentHeartbeatGapMs":recent_heartbeat_gap});
                if captures.is_empty()||(valid&&fresh_capture.is_none())||stable {
                    let suffix=if stable{"stable-nonblank"}else if valid{"first-fresh-nonblank"}else{"first-capture"};
                    let path=output.join(format!("{label}-{suffix}.png"));
                    std::fs::write(&path,&bytes).map_err(crate::err)?; row["path"]=json!(path);
                }
                captures.push(row.clone());
                if valid&&fresh_capture.is_none(){fresh_capture=Some(row.clone());}
                if valid&&recovered_wheel_wall.is_none(){
                    // The immediate UP gesture can land outside a temporarily
                    // 1x1 WebKit viewport. Preserve that failure independently;
                    // a distinct DOWN gesture tests actual recovered usability.
                    recovered_wheel_wall=Some(wall_ms());
                    wheel(view,true)?;
                }
                if stable {stable_capture=Some(row);break;}
            }
            Err(error) => captures.push(json!({"requestedWallMs":requested,"completedWallMs":wall_ms(),"error":error})),
        }
        thread::sleep(Duration::from_millis(500));
    }
    // Give the injected native wheel an opportunity to produce its queued
    // scroll event; doing this after the capture does not alter the time stamps.
    thread::sleep(Duration::from_millis(350));
    let timed=report(view)?;
    let raf=first_after(&timed["frames"],final_request_wall,true);
    let heartbeat=first_after(&timed["heartbeats"],final_request_wall,true);
    let immediate_wheel=timed["wheels"].as_array().and_then(|rows|rows.iter().find(|row|number(row,"wallMs")>=wheel_wall&&number(row,"deltaY")<0.&&row["trusted"]==true));
    let immediate_scroll=immediate_wheel.and_then(|event|timed["scrolls"].as_array()?.iter().find(|row|number(row,"wallMs")>=number(event,"wallMs")&&number(row,"y")<number(event,"beforeY")-0.5));
    let recovered_wheel=recovered_wheel_wall.and_then(|requested|timed["wheels"].as_array()?.iter().find(|row|number(row,"wallMs")>=requested&&number(row,"deltaY")>0.&&row["trusted"]==true));
    let recovered_scroll=recovered_wheel.and_then(|event|timed["scrolls"].as_array()?.iter().find(|row|number(row,"wallMs")>=number(event,"wallMs")&&number(row,"y")>number(event,"beforeY")+0.5));
    let immediate_trusted=immediate_wheel.is_some_and(|event|event["trusted"]==true);
    let recovered_trusted=recovered_wheel.is_some_and(|event|event["trusted"]==true);
    let trusted=immediate_trusted||recovered_trusted;
    let fresh_ms=fresh_capture.as_ref().map(|row|number(row,"completedWallMs")-final_request_wall);
    let raf_ms=raf.map(|row|number(row,"wallMs")-final_request_wall);
    let heartbeat_ms=heartbeat.map(|row|number(row,"wallMs")-final_request_wall);
    let wheel_ms=immediate_wheel.map(|row|number(row,"wallMs")-wheel_wall);
    let scroll_ms=immediate_scroll.map(|row|number(row,"wallMs")-wheel_wall);
    let recovered_wheel_ms=recovered_wheel.zip(recovered_wheel_wall).map(|(row,requested)|number(row,"wallMs")-requested);
    let recovered_scroll_ms=recovered_scroll.zip(recovered_wheel_wall).map(|(row,requested)|number(row,"wallMs")-requested);
    let usable_ms=immediate_scroll.into_iter().chain(recovered_scroll).map(|row|number(row,"wallMs")-final_request_wall).reduce(f64::min);
    let stable_ms=stable_capture.as_ref().map(|row|number(row,"completedWallMs")-final_request_wall);
    let raf_gap=max_gap(&timed["frames"],native_start_wall,number(&timed,"currentWallMs"));
    let heartbeat_gap=max_gap(&timed["heartbeats"],native_start_wall,number(&timed,"currentWallMs"));
    let trusted_wheels:Vec<&Value>=timed["wheels"].as_array().into_iter().flatten().filter(|event|event["trusted"]==true).collect();
    let wheel_delta_sum: f64=trusted_wheels.iter().map(|event|number(event,"deltaY")).sum();
    let expected_final_y=trusted_wheels.first().map(|event|number(event,"beforeY")+wheel_delta_sum);
    let actual_final_y=number(&timed,"scrollTop");
    let persistence_error=expected_final_y.map(|expected|actual_final_y-expected);
    let wheel_persistence_pass=persistence_error.is_some_and(|error|error.abs()<=3.);
    let wheel_persistence=json!({"pass":wheel_persistence_pass,"tolerancePixels":3,"trustedEvents":trusted_wheels.len(),"firstWheelBeforeY":trusted_wheels.first().map(|event|number(event,"beforeY")),"sumTrustedDeltaY":wheel_delta_sum,"expectedFinalY":expected_final_y,"actualFinalY":actual_final_y,"errorPixels":persistence_error});
    let frame_rows=timed["frames"].as_array().ok_or("Missing resize frame trace")?;
    let resize_rows=timed["resizes"].as_array().ok_or("Missing resize event trace")?;
    let mut viewports:Vec<&Value>=frame_rows.iter().chain(resize_rows.iter()).filter(|row|number(row,"wallMs")>=native_start_wall).collect();
    viewports.sort_by(|a,b|number(a,"wallMs").total_cmp(&number(b,"wallMs")));
    let tiny=|row:&&Value|number(row,"width")<=1.||number(row,"height")<=1.;
    let first_tiny=viewports.iter().find(|row|tiny(row)).copied();
    let last_tiny=viewports.iter().rev().find(|row|tiny(row)).copied();
    let recovered_non_tiny=last_tiny.and_then(|last|viewports.iter().find(|row|number(row,"wallMs")>number(last,"wallMs")&&!tiny(row)).copied());
    let recovered_final=last_tiny.and_then(|last|viewports.iter().find(|row|number(row,"wallMs")>number(last,"wallMs")&&row["width"]==1280&&row["height"]==786).copied());
    let native_correct_tiny=viewports.iter().filter(|row|tiny(row)).filter(|row| {
        let latest=requests.iter().rev().find(|request|number(&request["allocation"],"wallMs")<=number(row,"wallMs"));
        latest.is_some_and(|request|number(&request["allocation"],"width")==number(request,"width")&&number(&request["allocation"],"height")==number(request,"height")-54.)
    }).count();
    let tiny_diagnostics=json!({
        "minimumObservedViewportWidth":viewports.iter().map(|row|number(row,"width")).reduce(f64::min),
        "minimumObservedViewportHeight":viewports.iter().map(|row|number(row,"height")).reduce(f64::min),
        "onePixelFrames":frame_rows.iter().filter(|row|number(row,"wallMs")>=native_start_wall&&(number(row,"width")<=1.||number(row,"height")<=1.)).count(),
        "onePixelResizeEvents":resize_rows.iter().filter(|row|number(row,"wallMs")>=native_start_wall&&(number(row,"width")<=1.||number(row,"height")<=1.)).count(),
        "onePixelObservationsWhileNativeAllocationCorrect":native_correct_tiny,
        "firstOnePixelObservation":first_tiny,"lastOnePixelObservation":last_tiny,
        "firstRecoveredNonTinyViewport":recovered_non_tiny,"firstRecoveredFinalViewport":recovered_final,
        "observedOnePixelSpanMs":first_tiny.zip(last_tiny).map(|(a,b)|number(b,"wallMs")-number(a,"wallMs")),
        "onePixelToObservedNonTinyRecoveryMs":first_tiny.zip(recovered_non_tiny).map(|(a,b)|number(b,"wallMs")-number(a,"wallMs")),
        "onePixelToObservedFinalRecoveryMs":first_tiny.zip(recovered_final).map(|(a,b)|number(b,"wallMs")-number(a,"wallMs"))
    });
    let stopped=eval_json(view,"JSON.stringify(window.__resizeLatency.stop())")?;
    let summary=json!({
        "event":"resize-latency","label":label,"requestedNativeSteps":requests.len(),"nativeRequests":requests,
        "nativeStartWallMs":native_start_wall,"nativeFinalRequestWallMs":final_request_wall,
        "nativeFinalRequestElapsedMs":final_request_elapsed,"totalTimedWallMs":start.elapsed().as_secs_f64()*1000.,
        "firstPostFinalRafMs":raf_ms,"firstPostFinalHeartbeatMs":heartbeat_ms,
        "firstFreshNonblankCaptureMs":fresh_ms,"firstStableRecoveryCaptureMs":stable_ms,
        "minimumRecoveryObservationMs":minimum_observation_ms,"stableRecoveryWindowMs":stable_window_ms,
        "immediateWheelInjectedWallMs":wheel_wall,"immediateTrustedWheelReceived":immediate_trusted,
        "wheelDispatchResponseMs":wheel_ms,"wheelScrollResponseMs":scroll_ms,
        "recoveredWheelInjectedWallMs":recovered_wheel_wall,"recoveredTrustedWheelReceived":recovered_trusted,
        "recoveredWheelDispatchResponseMs":recovered_wheel_ms,"recoveredWheelScrollResponseMs":recovered_scroll_ms,
        "firstUsableWheelAfterFinalMs":usable_ms,"trustedWheelReceived":trusted,
        "wheelPersistence":wheel_persistence,
        "maxRafGapDuringResizeMs":max_gap(&timed["frames"],native_start_wall,final_request_wall),
        "maxHeartbeatGapDuringResizeMs":max_gap(&timed["heartbeats"],native_start_wall,final_request_wall),
        "maxRafGapThroughRecoveryMs":raf_gap,"maxHeartbeatGapThroughRecoveryMs":heartbeat_gap,
        "viewportDiagnostics":tiny_diagnostics,"firstFreshCapture":fresh_capture,"stableRecoveryCapture":stable_capture,
        "captures":captures,"before":before,"timed":timed,"stopped":stopped,
        "pixelProof":"Native WebKit visible snapshot with fresh per-rAF final-viewport frame patch plus distributed bright chat pixels; does not prove OS compositor presentation",
        "noFullHeightOracleDuringTiming":true,
        "pixelAndInputPass":fresh_ms.is_some()&&stable_ms.is_some()&&trusted&&usable_ms.is_some()&&wheel_persistence_pass,
        "underOneSecondTarget":fresh_ms.is_some_and(|ms|ms<1000.)&&usable_ms.is_some_and(|ms|ms<1000.)&&raf_gap<1000.&&heartbeat_gap<1000.&&stable_ms.is_some()&&wheel_persistence_pass
    });
    let path=output.join(format!("{label}-resize-latency.json")); std::fs::write(path,serde_json::to_vec_pretty(&summary).map_err(crate::err)?).map_err(crate::err)?;
    emit(summary.clone());
    if summary["pixelAndInputPass"]!=true {return Err("Resize test lacked fresh nonblank pixel proof or trusted native scroll response".into());}
    Ok(summary)
}
