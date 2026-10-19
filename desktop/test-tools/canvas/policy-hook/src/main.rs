//! Synthetic native Wry/GTK policy-hook lifecycle check; no service or account.
use std::{cell::{Cell, RefCell}, rc::Rc, thread, time::{Duration, Instant}};
use gtk::{glib, prelude::*};
use webkit2gtk::{LoadEvent, NavigationPolicyDecision, NavigationPolicyDecisionExt,
    PolicyDecisionExt, PolicyDecisionType, WebViewExt};
use wry::{NewWindowResponse, WebViewBuilder, WebViewBuilderExtUnix, WebViewExtUnix};

struct Sentinel(Rc<Cell<usize>>);
impl Sentinel { fn touch(&self) {} }
impl Drop for Sentinel { fn drop(&mut self) { self.0.set(self.0.get() + 1); } }

fn pump_until(condition: impl Fn() -> bool, seconds: u64) -> bool {
    let deadline = Instant::now() + Duration::from_secs(seconds);
    let context = glib::MainContext::default();
    while !condition() && Instant::now() < deadline {
        while context.pending() { context.iteration(false); }
        thread::sleep(Duration::from_millis(5));
    }
    condition()
}
fn drain() {
    let context = glib::MainContext::default();
    let deadline = Instant::now() + Duration::from_millis(80);
    while Instant::now() < deadline {
        while context.pending() { context.iteration(false); }
        thread::sleep(Duration::from_millis(2));
    }
}
fn check(checks: &mut Vec<serde_json::Value>, label: &str, passed: bool, evidence: serde_json::Value) {
    checks.push(serde_json::json!({"name":label,"passed":passed,"evidence":evidence}));
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    gtk::init()?;
    let window = gtk::Window::new(gtk::WindowType::Toplevel);
    window.set_default_size(640, 480);
    let container = gtk::Box::new(gtk::Orientation::Vertical, 0);
    window.add(&container);
    let fallback = Rc::new(Cell::new(0));
    let fallback_counter = fallback.clone();
    let create_fallback = Rc::new(Cell::new(0));
    let create_fallback_counter = create_fallback.clone();
    let webview = WebViewBuilder::new()
        .with_navigation_handler(move |_| { fallback_counter.set(fallback_counter.get() + 1); true })
        .with_new_window_req_handler(move |_, _| { create_fallback_counter.set(create_fallback_counter.get()+1); NewWindowResponse::Deny })
        .build_gtk(&container)?;
    let native = webview.webview();
    let finished = Rc::new(Cell::new(0));
    let finished_counter = finished.clone();
    native.connect_load_changed(move |_, event| {
        if event == LoadEvent::Finished { finished_counter.set(finished_counter.get() + 1); }
    });
    window.show_all();
    let mut checks = Vec::new();
    native.load_html("<!doctype html><title>unhooked</title><p>own inline document</p>", Some("about:blank"));
    let first_completed = pump_until(|| finished.get() >= 1, 8);
    check(&mut checks,"Unhooked Wry navigation uses the existing fallback and loads own HTML",
        first_completed && fallback.get() == 1,
        serde_json::json!({"finished":finished.get(),"fallbackCalls":fallback.get()}));

    let false_calls = Rc::new(Cell::new(0));
    let false_counter = false_calls.clone();
    wry::set_webkit_policy_handler(&native, move |_, _, kind| {
        if kind == PolicyDecisionType::NavigationAction { false_counter.set(false_counter.get() + 1); }
        false
    });
    let before_finished = finished.get();
    let before_fallback = fallback.get();
    native.load_html("<!doctype html><title>fallback-false</title>", Some("about:blank"));
    let false_completed = pump_until(|| finished.get() > before_finished, 8);
    check(&mut checks,"A false hook result preserves the real Wry fallback",
        false_completed && false_calls.get() == 1 && fallback.get() == before_fallback + 1,
        serde_json::json!({"hookCalls":false_calls.get(),"fallbackIncrement":fallback.get()-before_fallback}));

    let handled_calls = Rc::new(Cell::new(0));
    let handled_counter = handled_calls.clone();
    let create_action = Rc::new(RefCell::new(None));
    let save_create_action = create_action.clone();
    wry::set_webkit_policy_handler(&native, move |_, decision, kind| {
        if kind == PolicyDecisionType::NavigationAction {
            if let Some(policy) = decision.downcast_ref::<NavigationPolicyDecision>() {
                *save_create_action.borrow_mut() = policy.navigation_action();
            }
            handled_counter.set(handled_counter.get() + 1);
            decision.ignore();
            return true;
        }
        false
    });
    let before_fallback = fallback.get();
    native.load_html("<!doctype html><title>must-not-load</title>", Some("about:blank"));
    let handled_arrived = pump_until(|| handled_calls.get() > 0, 8);
    drain();
    check(&mut checks,"A true hook result settles the native decision and bypasses Wry fallback",
        handled_arrived && handled_calls.get() == 1 && fallback.get() == before_fallback
            && native.title().is_some_and(|title| title == "fallback-false"),
        serde_json::json!({"hookCalls":handled_calls.get(),"fallbackIncrement":fallback.get()-before_fallback,"previousDocumentRetained":native.title().is_some_and(|title| title=="fallback-false")}));

    let old_drops = Rc::new(Cell::new(0));
    let replacement_drops = Rc::new(Cell::new(0));
    let old_calls = Rc::new(Cell::new(0));
    let replacement_calls = Rc::new(Cell::new(0));
    let lifecycle = Rc::new(RefCell::new(Vec::<bool>::new()));
    let sentinel = Sentinel(old_drops.clone());
    let observed_old_drops = old_drops.clone();
    let observed_replacement_drops = replacement_drops.clone();
    let old_counter = old_calls.clone();
    let new_counter = replacement_calls.clone();
    let lifecycle_inside = lifecycle.clone();
    wry::set_webkit_policy_handler(&native, move |view, decision, kind| {
        sentinel.touch();
        if kind != PolicyDecisionType::NavigationAction { return false; }
        old_counter.set(old_counter.get() + 1);
        lifecycle_inside.borrow_mut().push(observed_old_drops.get() == 0);
        let replacement = Sentinel(observed_replacement_drops.clone());
        let new_counter = new_counter.clone();
        wry::set_webkit_policy_handler(view, move |_, decision, kind| {
            replacement.touch();
            if kind != PolicyDecisionType::NavigationAction { return false; }
            new_counter.set(new_counter.get() + 1);
            decision.ignore();
            true
        });
        lifecycle_inside.borrow_mut().push(observed_old_drops.get() == 0);
        // Re-emit the actual live decision through the real GTK signal and Wry
        // wrapper. The replacement hook handles it before this invocation returns.
        let nested: bool = view.emit_by_name("decide-policy", &[decision, &kind]);
        lifecycle_inside.borrow_mut().push(nested && observed_old_drops.get() == 0);
        true
    });
    let before_fallback = fallback.get();
    native.load_html("<!doctype html><title>replacement-reentry</title>", Some("about:blank"));
    let replaced = pump_until(|| old_calls.get() > 0 && old_drops.get() == 1, 8);
    drain();
    check(&mut checks,"Replacement during a callback survives native signal re-entry and releases the old closure after return",
        replaced && old_calls.get() == 1 && replacement_calls.get() == 1
            && lifecycle.borrow().as_slice() == [true,true,true] && fallback.get() == before_fallback
            && replacement_drops.get() == 0,
        serde_json::json!({"oldCalls":old_calls.get(),"replacementCalls":replacement_calls.get(),"oldDrops":old_drops.get(),"replacementDrops":replacement_drops.get(),"oldAliveAtAllThreePoints":*lifecycle.borrow(),"fallbackIncrement":fallback.get()-before_fallback}));
    native.load_html("<!doctype html><title>replacement-next-real-navigation</title>", Some("about:blank"));
    let replacement_still_registered = pump_until(|| replacement_calls.get() >= 2, 8);
    check(&mut checks,"The replacement handles the next real native navigation",
        replacement_still_registered && replacement_calls.get() == 2 && old_calls.get() == 1
            && fallback.get() == before_fallback && replacement_drops.get() == 0,
        serde_json::json!({"oldCalls":old_calls.get(),"replacementCalls":replacement_calls.get(),"replacementDrops":replacement_drops.get()}));

    // Exercise the actual Wry create connection with a copied native action
    // from the real navigation above. This deliberately tests create-only
    // dispatch, without a preceding NewWindowAction policy signal.
    let create_allow_drops = Rc::new(Cell::new(0));
    let create_deny_drops = Rc::new(Cell::new(0));
    let create_allow_calls = Rc::new(Cell::new(0));
    let create_deny_calls = Rc::new(Cell::new(0));
    if let Some(action) = create_action.borrow().as_ref() {
        let child: Option<gtk::Widget> = native.emit_by_name("create", &[action]);
        check(&mut checks,"Unhooked native create retains Wry's existing creator callback",
            child.is_none() && create_fallback.get()==1,
            serde_json::json!({"creatorCalls":create_fallback.get(),"createdWidget":child.is_some()}));
        let allow_sentinel = Sentinel(create_allow_drops.clone());
        let allow_calls = create_allow_calls.clone();
        wry::set_webkit_new_window_handler(&native, move |_, _| { allow_sentinel.touch();allow_calls.set(allow_calls.get()+1);true });
        let child: Option<gtk::Widget> = native.emit_by_name("create", &[action]);
        check(&mut checks,"A true native creation gate preserves Wry's creator path",
            child.is_none() && create_allow_calls.get()==1 && create_fallback.get()==2,
            serde_json::json!({"gateCalls":create_allow_calls.get(),"creatorCalls":create_fallback.get()}));
        let deny_sentinel = Sentinel(create_deny_drops.clone());
        let deny_calls = create_deny_calls.clone();
        wry::set_webkit_new_window_handler(&native, move |_, _| { deny_sentinel.touch();deny_calls.set(deny_calls.get()+1);false });
        let child: Option<gtk::Widget> = native.emit_by_name("create", &[action]);
        check(&mut checks,"A false native creation gate blocks create-only dispatch before the URL callback",
            child.is_none() && create_deny_calls.get()==1 && create_fallback.get()==2 && create_allow_drops.get()==1,
            serde_json::json!({"gateCalls":create_deny_calls.get(),"creatorCalls":create_fallback.get(),"replacedGateDrops":create_allow_drops.get()}));
    } else {
        check(&mut checks,"Native action available for creation gate checks",false,serde_json::json!({}));
    }
    drop(create_action);

    let weak_native = native.downgrade();
    drop(webview);
    drop(native);
    // GTK-thread teardown, after all synchronous signal callbacks have returned.
    unsafe { window.destroy(); }
    drop(container);
    drop(window);
    let released = pump_until(|| replacement_drops.get() == 1 && weak_native.upgrade().is_none(), 8);
    check(&mut checks,"Destroying and releasing the native view releases the stored callback once",
        released && replacement_drops.get() == 1 && old_drops.get() == 1 && create_deny_drops.get()==1 && create_allow_drops.get()==1,
        serde_json::json!({"oldDrops":old_drops.get(),"replacementDrops":replacement_drops.get(),"nativeObjectFinalized":weak_native.upgrade().is_none(),"allowCreationGateDrops":create_allow_drops.get(),"denyCreationGateDrops":create_deny_drops.get()}));
    let ok = checks.iter().all(|entry| entry["passed"] == true);
    println!("VIBEZ_POLICY_HOOK_RESULT {}",serde_json::to_string(&serde_json::json!({"ok":ok,"scope":"synthetic native Wry library hook lifecycle; not VibeZ service/auth/render verification","networkRequested":false,"checks":checks}))?);
    if !ok { std::process::exit(1); }
    Ok(())
}
