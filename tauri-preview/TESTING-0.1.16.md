# Preview 0.1.16 acceptance criteria

Keep all 0.1.15 regressions enabled. In addition:

- A failed first browser-language preparation followed by success must not return a terminal error. Three consecutive failures must return an error (no silent suppression or infinite retry).
- Superseded requests must neither run new preparations nor publish old failures/successes.
- Successful language recovery clears only `site_language_failed`, preserving unrelated newer status messages. Recovered attempts remain in bounded diagnostics.
- Navigation must succeed before its generation is marked complete. Authentication/loading pages remain protected from language navigation.
- A native Linux probe uses a fresh, isolated, hidden `about:blank` webview and prepares nl/en/nl through real WebKit cookie APIs without any remote navigation. Run together with exact resize/maximize/restore, hidden-window and popup/IPC tests at 100% and 200% scale.
- User acceptance: fully quit/reopen with the existing profile, then change language and restart again. Confirm no stale warning, correct website language and unchanged layout. Never clear the user's browser data to pass the test.

Live OAuth, Wayland, installer lifecycle and Windows behavior are separate checks. Passing this suite does not close the release gate for all platforms.
