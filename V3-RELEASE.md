# VibeZ 3.0.7 — Linux rich-chat scrolling and resize improvements

VibeZ 3.0.7 reduces rendering work for recognized long assistant replies on Linux and improves recovery while resizing the window. Windows and macOS receive the version/title update and the shared dependency update; their rendering behavior is unchanged. Every platform shows **VibeZ V3.0.7** in its window titles.

## Linux changes

Historical replies outside the viewport can skip rendering while retaining measured heights. Height refreshes run in bounded batches instead of expanding the entire conversation at once. The latest reply and changing replies remain expanded, and native Find and page screenshots temporarily expand content when needed. Unknown conversation markup is left untouched. This reduces rendering work without removing messages from the DOM; it is not full message virtualization.

The native GTK layout now allocates the content webview normally, avoiding the transient 1×1 viewport observed in the earlier resize path. Find handles rapid close/reopen safely, and screenshot cancellation and timeouts restore the rendering state. The changes apply to Linux AppImage, DEB, RPM, Arch/Pacman and Flatpak builds.

The existing code-header appearance, normal Mistral startup, `nl.lecomputeur.vibez3` identity, `vibez3` executable, settings, profiles and published-release update flow are retained. The ordinary client opens Mistral; the synthetic test chat is only part of the separate test harness.

## Measured results and limits

Local validation used the ordinary 3.0.7 DEB executable on Linux Mint 22.3/X11 with glibc 2.39 and WebKitGTK 2.52.6. The synthetic workload contained 40 long formatted assistant replies, 640 sections, 291,504 DOM nodes and about 3.53 million text characters. Both WebKit rendering overrides were unset. A 30-second native-wheel test compared the same binary with the rendering helper paused and enabled; the native GTK resize fix was active in both runs.

| WebKit CPU during scrolling | Helper paused | Helper enabled |
|---|---:|---:|
| Mean | 119.08% | 41.21% |
| Highest sampled interval | 134.33% | 53.38% |
| Sampled intervals above 100% | 58/58 | 0/58 |

Here, 100% means one logical CPU core. The figures sum only the test's own `WebKitWebProcess` CPU usage, sampled about every 0.5 seconds. These were single runs on the same desktop, not an isolated hardware benchmark or a comparison with a separate 3.0.6 executable. WebKit peak RSS remained about 1.2 GiB; this change does not remove the memory cost of a large loaded conversation. Startup, searching and resizing can still produce CPU peaks.

In the resize test, the first fresh nonblank WebKit PNG appeared after 136 ms and usable wheel response after 87 ms. There were no observed 1×1 frames. These measurements describe pixels in the app's own webview, not the exact moment the desktop compositor presented them.

Local regression checks passed for streaming, historical edits, responsive layout, exact height refresh, scroll preservation, style ownership, Find and screenshot timeout recovery: 54 heavy-chat checks, plus native Find and resize probes. Screenshot/paste and native app regressions passed at scales 1 and 2. The screenshot paste tests exercised the existing compatibility route. BFCache lifecycle events were simulated; an actual browser-cache hit was not established. Reproduction tools are documented in [the rich-chat test harness](desktop/test-tools/rich-chat/README.md).

Anonymous checks loaded the normal public Mistral page without signing in. Its currently loaded public source confirms the assistant-role wrapper and flex layout used by the first production selector. A further 17 checks passed with local synthetic messages under the public page's existing `main` and CSS, using the exact production helper. No messages were submitted to Mistral. This validates that selector branch with synthetic content; it does not establish the full runtime structure, streaming markers or performance of a genuine hosted conversation. The original private conversation was not accessed or reproduced, so this release does not claim that specific report is conclusively resolved. Results vary with conversation content, graphics drivers and hardware.

## Shared dependency update

The shared Rust TLS dependency is updated to **rustls 0.23.46**, which includes [upstream security fixes](https://github.com/rustls/rustls/releases/tag/v/0.23.46). This dependency update applies across platforms. It does not change the platform webview engines.

## Packages and verification

The [verified 3.0.7 validation run](https://github.com/lecomputeur/vibez/actions/runs/39012314243) passed all nine required jobs, including dependency audits, frontend/Rust tests, rich-chat and native regressions, installer/update tests, all twelve package formats and macOS signing/notarization. The packages use the frozen source commit [`e64eaf5`](https://github.com/lecomputeur/vibez/commit/e64eaf5082eae5ee0808028bda45fb0068560c80); the [versioned proof](tools/release-v3/release-proof-3.0.7.json) records the exact source and run. The actual Store MSIX was also independently inspected for its approved identity, x64 architecture, ordinary executable and version 3.0.7.0. Published assets are verified against their fresh `SHA256SUMS` and `source-commit.txt` before publication. Historical 3.0.6 proof remains unchanged.

Native Linux packages and AppImage require glibc 2.39+ and WebKitGTK 4.1; desktop-area screenshot selection on Linux requires X11. Flatpak uses its declared GNOME runtime. macOS requires version 14 or later, and Windows requires WebView2. Microsoft Store package version is `3.0.7.0`; creating the MSIX is separate from Store submission, certification and delivery.
