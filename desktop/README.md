# VibeZ 3

Rust/Tauri 3.0.8 source for Linux AppImage/DEB/RPM/Arch/Flatpak, Windows EXE/MSI/MSIX and macOS Intel/Apple Silicon app/DMG/ZIP.

The [3.0.8 validation workflow](../.github/workflows/v3.0.8-validation.yml) builds and checks one immutable source commit without publishing, tagging or submitting to the Store. Publication follows the release gates; the [release assets](https://github.com/lecomputeur/vibez/releases/tag/v3.0.8), `SHA256SUMS`, `source-commit.txt` and version-specific proof identify the distributed packages. The [3.0.7 verified build](https://github.com/lecomputeur/vibez/actions/runs/39012314243) and its [proof](../tools/release-v3/release-proof-3.0.7.json) remain historical evidence for 3.0.7 only.

App identity: `nl.lecomputeur.vibez3`; executable: `vibez3`. The app opens the normal Mistral client and retains the ordinary settings, profile and published-update flow. Existing Electron and preview profiles are not silently copied or deleted.

From the repository root, check metadata with `python3 tools/release-v3/check-inputs.py --version 3.0.8`. In `desktop`, run `npm ci --ignore-scripts`, `npm test` and `cargo test --release --locked --manifest-path src-tauri/Cargo.toml`. Build Linux native formats with `npm run build -- --bundles deb,rpm -- --locked`, then `npm run build -- --bundles appimage -- --locked`. The build wrapper applies the AppImage desktop template separately. Lockfiles are committed before frozen CI builds.

`tools/release-v3/collect.py linux` inspects and names the three native packages. The existing `arch.sh` and `flatpak.py` build the remaining Linux formats from that DEB payload; they require their own packaging tools/runtime and perform installation checks only in the validation environment. See [RELEASE-GATE.md](RELEASE-GATE.md) before calling any output release-ready.

Verified update installers close VibeZ automatically after handoff. Linux package hooks close only `/usr/bin/vibez3`; AppImage updates replace the original file after exit. Regression check: `python3 tests/update-install.py src-tauri/target/release/vibez3` in `desktop`.

Version 3.0.8 fixes Linux routing of embedded Cloudflare/Turnstile verification frames, keeping their required navigation in the webview instead of requesting external browser opens. Ordinary external links retain their normal behavior. The controlled reproduction used the unchanged published 3.0.7 binary; it did not perform a genuine Turnstile solve or reproduce the complete openSUSE report. See [release notes](../V3-RELEASE.md) for the evidence and limits.

Linux immediate wheel scrolling, scoped offscreen rendering, bounded cached-height refreshes, normal GTK resize allocation, native Find and screenshot support from 3.0.7 are retained. Existing code headers remain unchanged. Windows/WebView2 and macOS/WKWebView receive the version/title update only; navigation and rendering behavior is unchanged. Titles use `VibeZ V3.0.8` on every platform.

The [rich-chat test harness](test-tools/rich-chat/README.md) uses offline synthetic content and the ordinary built client. Historical 3.0.7 performance measurements must not be relabeled as new 3.0.8 results. Anonymous public startup and controlled frame-routing tests are separate from authenticated service compatibility; no login or private conversation is required for the local regressions.
