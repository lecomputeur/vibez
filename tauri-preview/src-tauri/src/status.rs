//! Expiration belongs to the message itself: no delayed task can overwrite it.
use std::time::{Duration, Instant};
pub struct Status { text: String, until: Option<Instant> }
impl Status {
    pub fn persistent(text: impl Into<String>) -> Self { Self { text: text.into(), until: None } }
    pub fn transient(text: impl Into<String>) -> Self { Self { text: text.into(), until: Some(Instant::now() + Duration::from_secs(5)) } }
    pub fn text(&self) -> &str { self.at(Instant::now()) }
    pub fn clear_if(&mut self, expected: &str) -> bool {
        if self.text != expected { return false; }
        self.text.clear(); self.until = None; true
    }
    fn at(&self, now: Instant) -> &str {
        if self.until.is_some_and(|end| now >= end) { "" } else { &self.text }
    }
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn expiration_cannot_replace_a_newer_message() {
        let mut s = Status::transient("saved"); let later = Instant::now() + Duration::from_secs(6);
        assert_eq!(s.at(later), ""); s = Status::persistent("error"); assert_eq!(s.at(later), "error");
    }
    #[test] fn recovered_language_clears_only_its_own_warning() {
        let mut s = Status::persistent("site_language_failed");
        assert!(s.clear_if("site_language_failed")); assert_eq!(s.text(), "");
    }
    #[test] fn recovery_preserves_a_newer_unrelated_message() {
        for message in ["Screenshot copied", "Page could not load", "settings_saved"] {
            let mut s = Status::persistent(message);
            assert!(!s.clear_if("site_language_failed")); assert_eq!(s.text(), message);
        }
    }
}
