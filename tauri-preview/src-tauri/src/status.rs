//! Expiration belongs to the message itself: no delayed task can overwrite it.
use std::time::{Duration, Instant};
pub struct Status { text: String, until: Option<Instant> }
impl Status {
    pub fn persistent(text: impl Into<String>) -> Self { Self { text: text.into(), until: None } }
    pub fn transient(text: impl Into<String>) -> Self { Self { text: text.into(), until: Some(Instant::now() + Duration::from_secs(5)) } }
    pub fn text(&self) -> &str { self.at(Instant::now()) }
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
}
