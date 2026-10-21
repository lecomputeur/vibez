# VibeZ 3

Rust/Tauri 3.0.9 source for Linux AppImage/DEB/RPM/Arch/Flatpak, Windows EXE/MSI/MSIX and macOS Intel/Apple Silicon app/DMG/ZIP.

The [verified 3.0.9 build](https://github.com/lecomputeur/vibez/actions/runs/39643498884) passed all nine required platform/security jobs, including native regressions, advisory checks, all twelve packages and Developer ID signing, Apple notarization and stapled-ticket validation for both Mac architectures. Both Mac jobs also verified the native architecture and macOS 14 deployment minimum in Info.plist and Mach-O. Frozen source: `64dbf09e8a24b1d1859b3571cd3b83b87a39f14c`. The [release proof](../tools/release-v3/release-proof-3.0.9.json) records the source and run. The files are validated for publication; the GitHub release asset list records public availability. Windows MSIX version: **3.0.9.0**. Microsoft Store submission and certification remain separate. The original heavy-conversation high-CPU issue remains open; see [release notes](../RELEASE-NOTES-3.0.9.md). See [release status](../RELEASE-STATUS-3.0.9.md).

App identity: `nl.lecomputeur.vibez3`; executable: `vibez3`. The app opens the normal Mistral client and retains the ordinary settings, profile and published-update flow. Existing Electron and preview profiles are not silently copied or deleted.

From the repository root, check metadata with `python3 tools/release-v3/check-inputs.py --version 3.0.9`. In `desktop`, run `npm ci --ignore-scripts`, `npm test` and `cargo test --release --locked --manifest-path src-tauri/Cargo.toml`. Build Linux native formats with `npm run build -- --bundles deb,rpm -- --locked`, then `npm run build -- --bundles appimage -- --locked`. The build wrapper applies the AppImage desktop template separately. Lockfiles are committed before frozen CI builds.

`tools/release-v3/collect.py linux` inspects and names the three native packages. The existing `arch.sh` and `flatpak.py` build the remaining Linux formats from that DEB payload; they require their own packaging tools/runtime and perform installation checks only in the validation environment. See [RELEASE-GATE.md](RELEASE-GATE.md) before calling any output release-ready.

Verified update installers close VibeZ automatically after handoff. Linux package hooks close only `/usr/bin/vibez3`; AppImage updates replace the original file after exit. Regression check: `python3 tests/update-install.py src-tauri/target/release/vibez3` in `desktop`.

Version 3.0.9 promotes the frame-aware Canvas/chart and verification routing tested in test.3. Unknown automatic navigations/popups are blocked; deliberate external hyperlinks remain supported. The openSUSE reporters separately confirmed working previews and a completed Cloudflare/Mistral sign-in in the test Flatpak. The original heavy conversation still reaches 100% idle CPU; it is not claimed fixed. See [release notes](../V3-RELEASE.md) for evidence and limits.

Linux immediate wheel scrolling, scoped offscreen rendering, bounded cached-height refreshes, normal GTK resize allocation, native Find and screenshot support from 3.0.7 are retained. Existing code headers remain unchanged. Windows/WebView2 and macOS/WKWebView receive version/title and TLS dependency updates; navigation/rendering paths remain unchanged. Titles use `VibeZ V3.0.9` on every platform.

The [rich-chat test harness](test-tools/rich-chat/README.md) uses offline synthetic content and the ordinary built client. Historical 3.0.7 performance measurements must not be relabeled as new 3.0.9 results. Anonymous public startup and controlled frame-routing tests are separate from authenticated service compatibility; no login or private conversation is required for the local regressions.
