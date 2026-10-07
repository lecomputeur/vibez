# VibeZ 3.0.2 — Mint test 6

Mint-first candidate only. No main merge, tag, public release or Partner Center submission before maintainer approval.

- Open the compact screenshot chooser on the monitor containing the VibeZ parent window, instead of generic screen centering.
- On Linux, create the chooser hidden, set native GTK CenterOnParent, and only then show it. The parent's current location is used each time a new chooser is opened.
- Manual dragging remains possible. An already open chooser is not continuously moved or snapped back. The normal hidden/restore path after cancellation retains its position.
- The 280 × 200 GTK menu size, 34 bundled languages, automatic paste and clipboard behaviour remain unchanged from test 5.
- Re-run screenshot and paste tests at 100% and 200%; add a real two-output Xorg/dummy test: VibeZ on left/right, pointer on the opposite monitor, cancel/restore, move/reopen, manual menu dragging and automatic image paste on the second monitor.
- Package version stays 3.0.2; the visible marker is test 6. Reinstall explicitly over other 3.0.2 builds.

Automated runtime is Ubuntu 24.04 with X11, not the maintainer's physical Mint hardware or authenticated Mistral session. Desktop area capture remains X11-only. No Windows/macOS/Store rollout in this change.
