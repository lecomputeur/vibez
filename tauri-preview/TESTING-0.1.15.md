# Preview 0.1.15 acceptance criteria

- Frontend behavioral regressions: only changed fields are sent, stale settings windows preserve newer language preferences, late polls cannot roll back toolbar state, same-field conflicts do not silently overwrite, diagnostics outages do not block saving, and language cookies are read regardless of their pair position.
- Rust: validate and merge patches, migrate legacy preferences, preserve corrupt bytes, reject unknown future schema, expire messages without overwriting newer ones, and reject language navigation during login/loading or on non-content URLs.
- Native Linux: request 1100x720, 760x560, 1450x950 and 1280x840; check the actual logical size reaches each target. Maximize then restore to each target and verify maximized state changes. Child geometry must match these actual sizes with a 54px toolbar.
- Native Linux: related direct/about:blank/nested popup opener callbacks and content/native-command isolation remain checked. No test-only repair may precede resize assertions. Layout must not show a hidden window.
- Package: independent name/version/architecture, GTK app-ID desktop entry, PNG icon, libc6 minimum and SHA256.

CI exercises an isolated X11/Openbox desktop, not a user's live Mistral account. Wayland, fractional scaling, real OAuth, installed menu/tray behavior and Windows platform parity remain explicit follow-up checks. This stabilization release does not close every item in the 0.1.14 audit.
