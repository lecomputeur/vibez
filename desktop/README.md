# VibeZ 3

Rust/Tauri 3.0.7 candidate source for Linux AppImage/DEB/RPM/Arch/Flatpak, Windows EXE/MSI/MSIX and macOS Intel/Apple Silicon app/DMG/ZIP. No 3.0.7 publication or all-format validation is claimed yet.

The `vibe/linux-rich-render-307` branch uses `.github/workflows/v3.0.7-validation.yml` to validate one immutable source commit without publishing, tagging or submitting to the Store. The [3.0.6 verified build](https://github.com/lecomputeur/vibez/actions/runs/38454538226) and its proof are historical evidence for 3.0.6 only. Published downloads remain in the [3.0.6 release](https://github.com/lecomputeur/vibez/releases/tag/v3.0.6).

App identity: `nl.lecomputeur.vibez3`; executable: `vibez3`. The candidate opens the normal Mistral client and retains the ordinary settings, profile and published-update flow. It does not ship the standalone experiment as the normal startup screen. Existing Electron and preview profiles are not silently copied or deleted.

From the repository root, check metadata with `python3 tools/release-v3/check-inputs.py --version 3.0.7`. In `desktop`, run `npm ci --ignore-scripts`, `npm test` and `cargo test --release --locked --manifest-path src-tauri/Cargo.toml`. Build Linux native formats with `npm run build -- --bundles deb,rpm -- --locked`, then `npm run build -- --bundles appimage -- --locked`. The build wrapper applies the AppImage desktop template separately. Lockfiles are committed before frozen CI builds.

`tools/release-v3/collect.py linux` inspects and names the three native packages. The existing `arch.sh` and `flatpak.py` build the remaining Linux formats from that DEB payload; they require their own packaging tools/runtime and perform installation checks only in the validation environment. See [RELEASE-GATE.md](RELEASE-GATE.md) before calling any output release-ready.

Verified update installers close VibeZ automatically after handoff. Linux package hooks close only `/usr/bin/vibez3`; AppImage updates replace the original file after exit. Regression check: `python3 tests/update-install.py src-tauri/target/release/vibez3` in `desktop`.

Linux content webviews retain immediate native wheel scrolling, add scoped offscreen rendering and use normal GTK resize allocation. Find and screenshot capture expand contained content while needed. Existing code headers remain unchanged. Windows/WebView2 and macOS/WKWebView rendering behavior is unchanged. Titles use `VibeZ V3.0.7` on every platform. See [candidate notes](../V3-RELEASE.md) for the measured evidence and its limits.
