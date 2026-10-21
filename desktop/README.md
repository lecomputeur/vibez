> **3.0.9 candidate:** validation and stable publication are pending. [3.0.8 remains the stable download](https://github.com/lecomputeur/vibez/releases/tag/v3.0.8). The original 100% idle CPU workload remains open in #49. Store 3.0.9 has not been submitted.

# VibeZ 3

Rust/Tauri 3.0.9 source for Linux AppImage/DEB/RPM/Arch/Flatpak, Windows EXE/MSI/MSIX and macOS Intel/Apple Silicon app/DMG/ZIP.

The [3.0.9 validation run](https://github.com/lecomputeur/vibez/actions/runs/39630746331) passed Linux, Windows and Apple Silicon packaging and the required native/security tests. Intel compilation/native tests passed, but Apple CloudKit ticket validation failed repeatedly. Stable publication is blocked, no complete 3.0.9 proof exists, and the 3.0.8 evidence remains historical. See [release status](../RELEASE-STATUS-3.0.9.md).

App identity: `nl.lecomputeur.vibez3`; executable: `vibez3`. The app opens the normal Mistral client and retains the ordinary settings, profile and published-update flow. Existing Electron and preview profiles are not silently copied or deleted.

From the repository root, check metadata with `python3 tools/release-v3/check-inputs.py --version 3.0.9`. In `desktop`, run `npm ci --ignore-scripts`, `npm test` and `cargo test --release --locked --manifest-path src-tauri/Cargo.toml`. Build Linux native formats with `npm run build -- --bundles deb,rpm -- --locked`, then `npm run build -- --bundles appimage -- --locked`. The build wrapper applies the AppImage desktop template separately. Lockfiles are committed before frozen CI builds.

`tools/release-v3/collect.py linux` inspects and names the three native packages. The existing `arch.sh` and `flatpak.py` build the remaining Linux formats from that DEB payload; they require their own packaging tools/runtime and perform installation checks only in the validation environment. See [RELEASE-GATE.md](RELEASE-GATE.md) before calling any output release-ready.

Verified update installers close VibeZ automatically after handoff. Linux package hooks close only `/usr/bin/vibez3`; AppImage updates replace the original file after exit. Regression check: `python3 tests/update-install.py src-tauri/target/release/vibez3` in `desktop`.

Version 3.0.9 promotes the frame-aware Canvas/chart and verification routing tested in test.3. Unknown automatic navigations/popups are blocked; deliberate external hyperlinks remain supported. The openSUSE reporters separately confirmed working previews and a completed Cloudflare/Mistral sign-in in the test Flatpak. The original heavy conversation still reaches 100% idle CPU; it is not claimed fixed. See [release notes](../V3-RELEASE.md) for evidence and limits.

Linux immediate wheel scrolling, scoped offscreen rendering, bounded cached-height refreshes, normal GTK resize allocation, native Find and screenshot support from 3.0.7 are retained. Existing code headers remain unchanged. Windows/WebView2 and macOS/WKWebView receive version/title and TLS dependency updates; navigation/rendering paths remain unchanged. Titles use `VibeZ V3.0.9` on every platform.

The [rich-chat test harness](test-tools/rich-chat/README.md) uses offline synthetic content and the ordinary built client. Historical 3.0.7 performance measurements must not be relabeled as new 3.0.9 results. Anonymous public startup and controlled frame-routing tests are separate from authenticated service compatibility; no login or private conversation is required for the local regressions.
