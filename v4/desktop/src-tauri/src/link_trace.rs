//! In-memory routing diagnostics. Never store URL paths, queries, cookies or tokens.
use std::{collections::VecDeque, sync::{Mutex, OnceLock}, time::Instant};
use url::Url;

const LIMIT: usize = 96;
static EVENTS: OnceLock<Mutex<VecDeque<String>>> = OnceLock::new();
static START: OnceLock<Instant> = OnceLock::new();

fn line(kind: &str, url: &Url, elapsed_ms: u128) -> String {
    format!("+{elapsed_ms}ms {kind}: {}", crate::auth::origin(url))
}
pub fn record(kind: &'static str, url: &Url) {
    let elapsed = START.get_or_init(Instant::now).elapsed().as_millis();
    if let Ok(mut events) = EVENTS.get_or_init(|| Mutex::new(VecDeque::new())).lock() {
        if events.len() >= LIMIT { events.pop_front(); }
        events.push_back(line(kind, url, elapsed));
    }
}
pub fn diagnostics() -> String {
    EVENTS.get_or_init(|| Mutex::new(VecDeque::new())).lock()
        .map(|events| events.iter().cloned().collect::<Vec<_>>().join("\n"))
        .unwrap_or_else(|_| "Routing diagnostics unavailable".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn route_logs_only_the_origin() {
        let url = Url::parse("https://user:secret@accounts.google.com/private@example.org?code=confidential&state=hidden#token").unwrap();
        assert_eq!(line("main-open-external", &url, 42), "+42ms main-open-external: https://accounts.google.com");
        assert_eq!(line("main-block", &Url::parse("data:text/plain,secret").unwrap(), 0), "+0ms main-block: blocked scheme");
    }
}
