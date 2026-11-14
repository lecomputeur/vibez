//! Bounded preparation retries; obsolete language requests never report failure.
use std::{future::Future, time::Duration};

#[derive(Debug, PartialEq, Eq)]
pub enum Outcome { Ready, Superseded }

pub async fn prepare<F, Fut, Current, Failed>(mut operation: F, current: Current, mut failed: Failed, delay: Duration) -> Result<Outcome, String>
where F: FnMut() -> Fut, Fut: Future<Output = Result<(), String>>,
      Current: Fn() -> bool, Failed: FnMut(usize, &str) {
    for attempt in 1..=3 {
        if !current() { return Ok(Outcome::Superseded); }
        let result = operation().await;
        if !current() { return Ok(Outcome::Superseded); }
        match result {
            Ok(()) => return Ok(Outcome::Ready),
            Err(error) => {
                failed(attempt, &error);
                if attempt == 3 { return Err(error); }
                tokio::time::sleep(delay).await;
            }
        }
    }
    unreachable!("the third attempt returns")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, AtomicBool, Ordering};
    #[test] fn cold_start_failure_recovers_without_terminal_error() {
        let calls = AtomicUsize::new(0);
        let mut history = Vec::new();
        let result = tauri::async_runtime::block_on(prepare(|| {
            let first = calls.fetch_add(1, Ordering::SeqCst) == 0;
            async move { if first { Err("initializing cookie store".into()) } else { Ok(()) } }
        }, || true, |attempt, error| history.push((attempt, error.to_string())), Duration::ZERO));
        assert_eq!(result, Ok(Outcome::Ready));
        assert_eq!(calls.load(Ordering::SeqCst), 2);
        assert_eq!(history, vec![(1, "initializing cookie store".to_string())]);
    }
    #[test] fn persistent_failure_is_bounded_and_preserved() {
        let calls = AtomicUsize::new(0);
        let mut history = Vec::new();
        let result = tauri::async_runtime::block_on(prepare(|| {
            calls.fetch_add(1, Ordering::SeqCst);
            async { Err("cookie store unavailable".into()) }
        }, || true, |attempt, _| history.push(attempt), Duration::ZERO));
        assert_eq!(result, Err("cookie store unavailable".into()));
        assert_eq!(calls.load(Ordering::SeqCst), 3);
        assert_eq!(history, vec![1, 2, 3]);
    }
    #[test] fn superseded_request_does_not_run() {
        let result = tauri::async_runtime::block_on(prepare(|| async { panic!("obsolete operation ran") },
            || false, |_, _| panic!("obsolete error reported"), Duration::ZERO));
        assert_eq!(result, Ok(Outcome::Superseded));
    }
    #[test] fn failure_from_superseded_request_is_not_reported() {
        let current = AtomicBool::new(true);
        let result = tauri::async_runtime::block_on(prepare(|| {
            current.store(false, Ordering::SeqCst);
            async { Err("old request".into()) }
        }, || current.load(Ordering::SeqCst), |_, _| panic!("stale error reported"), Duration::ZERO));
        assert_eq!(result, Ok(Outcome::Superseded));
    }
    #[test] fn late_success_cannot_complete_newer_language() {
        let current = AtomicBool::new(true);
        let result = tauri::async_runtime::block_on(prepare(|| {
            current.store(false, Ordering::SeqCst);
            async { Ok(()) }
        }, || current.load(Ordering::SeqCst), |_, _| {}, Duration::ZERO));
        assert_eq!(result, Ok(Outcome::Superseded));
    }
}
