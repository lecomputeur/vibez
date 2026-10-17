# VibeZ 3

Rust/Tauri 3.0.7 source for Linux AppImage/DEB/RPM/Arch/Flatpak, Windows EXE/MSI/MSIX and macOS Intel/Apple Silicon app/DMG/ZIP.

The [3.0.7 validation workflow](../.github/workflows/v3.0.7-validation.yml) builds and checks one immutable source commit without publishing, tagging or submitting to the Store. Publication follows the release gates; the [release assets](https://github.com/lecomputeur/vibez/releases/tag/v3.0.7), `SHA256SUMS` and `source-commit.txt` identify the distributed packages. The [3.0.6 verified build](https://github.com/lecomputeur/vibez/actions/runs/38454538226) and its proof are historical evidence for 3.0.6 only.

App identity: `nl.lecomputeur.vibez3`; executable: `vibez3`. The app opens the normal Mistral client and retains the ordinary settings, profile and published-update flow. Existing Electron and preview profiles are not silently copied or deleted.

From the repository root, check metadata with `python3 tools/release-v3/check-inputs.py --version 3.0.7`. In `desktop`, run `npm ci --ignore-scripts`, `npm test` and `cargo test --release --locked --manifest-path src-tauri/Cargo.toml`. Build Linux native formats with `npm run build -- --bundles deb,rpm -- --locked`, then `npm run build -- --bundles appimage -- --locked`. The build wrapper applies the AppImage desktop template separately. Lockfiles are committed before frozen CI builds.

`tools/release-v3/collect.py linux` inspects and names the three native packages. The existing `arch.sh` and `flatpak.py` build the remaining Linux formats from that DEB payload; they require their own packaging tools/runtime and perform installation checks only in the validation environment. See [RELEASE-GATE.md](RELEASE-GATE.md) before calling any output release-ready.

Verified update installers close VibeZ automatically after handoff. Linux package hooks close only `/usr/bin/vibez3`; AppImage updates replace the original file after exit. Regression check: `python3 tests/update-install.py src-tauri/target/release/vibez3` in `desktop`.

Linux content webviews retain immediate native wheel scrolling, add scoped offscreen rendering and use normal GTK resize allocation. Cached heights refresh in bounded batches. Find and screenshot capture expand contained content while needed; streaming replies remain expanded. Existing code headers remain unchanged. Windows/WebView2 and macOS/WKWebView rendering behavior is unchanged. Titles use `VibeZ V3.0.7` on every platform, and the shared Rust TLS dependency is updated to rustls 0.23.46 for its upstream security fixes. See [release notes](../V3-RELEASE.md) for the measured evidence and its limits.

The [rich-chat test harness](test-tools/rich-chat/README.md) uses offline synthetic content and the ordinary built client. Anonymous Mistral source checks and synthetic DOM integration establish selector evidence without login; they do not prove the original private-chat report is resolved or guarantee performance for every live conversation.

The [3.0.7 all-format build](https://github.com/lecomputeur/vibez/actions/runs/39012314243) passed all nine required jobs; the [versioned proof](../tools/release-v3/release-proof-3.0.7.json) pins its frozen source.
