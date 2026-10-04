# VibeZ 3.0.0 — Same Vibe. Rebuilt in Rust.

## Goodbye, Electron. Hello, Rust + Tauri.

**This is a new chapter for VibeZ — not just another version number.** The desktop application has moved from Electron to a Rust-powered Tauri foundation while retaining its familiar toolbar and focused Mistral Vibe experience.

VibeZ 3 uses the operating system's browser engine instead of bundling an Electron runtime: WebKitGTK on Linux, WebView2 on Windows and WKWebView on macOS. The native layer is written in Rust; the bundled interface and the remote website still use web technologies. No unmeasured speed or memory claims are implied.

## Your language. From the very first launch.

The language module has been rebuilt around system-language detection, explicit user choice and reliable application to the embedded browser. It now prepares the browser before the first remote navigation, confirms the language cookie natively, preserves saved preferences and serializes language changes so stale replies cannot undo your latest choice.

A settings window left open on an older language no longer reverses a newer toolbar choice when you change something unrelated. Language navigation waits during authentication. Temporary startup errors have bounded retries, and a recovered language warning no longer remains above an otherwise working page.

**34 VibeZ interface-language bundles; native language-cookie checks on all three browser engines.** Dutch/English switching and startup recovery have also been checked in the maintainer's Linux/Cinnamon use. The Mistral website controls its own supported translations; unsupported website-language choices fall back to English. Language follows preferences, not physical location.

## One release. Twelve files. Every supported package family.

| Platform | VibeZ 3.0.0 files |
|---|---|
| Linux x64 | AppImage, DEB, RPM, Arch/Pacman and Flatpak |
| Windows x64 | Setup EXE, MSI and Store MSIX |
| macOS Apple Silicon | Developer ID signed, notarized and stapled app in DMG and ZIP |
| macOS Intel | Developer ID signed, notarized and stapled app in DMG and ZIP |

The entire set was built together. No missing platform was waved through to obtain a green release gate. Choose one installer for your operating system; `SHA256SUMS` covers the release files.

## More of the foundations fixed

Window resizing and restore-after-maximize are tested against real requested dimensions. Linux launcher/window/tray icons are checked across repeated starts. Windows and macOS navigation read real browser history state rather than placeholders. Preference updates are field-level and conflict-aware, damaged settings are recoverable, and the manual updater discovers permanent published releases instead of expiring CI downloads.

Remote website content and login popups remain separated from the native privileges of the local toolbar and settings.

## Verified build and publication status

- Frozen application/build source: `b30a4b58e71d3482fa79433779ff24410525ad01`.
- Successful all-platform workflow: [37219669459](https://github.com/lecomputeur/vibez/actions/runs/37219669459).
- All nine required jobs passed, including the dependency advisory audit and the twelve-file completeness gate.
- The successful workflow produced the full release draft. **A draft is not a public release.** Public availability is shown on the [v3.0.0 release page](https://github.com/lecomputeur/vibez/releases/tag/v3.0.0).
- Publication-only documentation and workflow changes do not replace the tested application binaries.

Native tests exercise language cookies, history navigation, popup callbacks, restricted native privileges, resizing and hidden-state behavior. They are offline probes, not a claim of live Google/Microsoft/Mistral account sign-in testing on every platform. Wayland, fractional scaling and every distribution are not claimed validated merely because X11 tests passed.

## Installing and moving from older versions

Use the [platform installation guides](https://lecomputeur.github.io/vibez/). VibeZ 3 direct installers use `nl.lecomputeur.vibez3`, executable `vibez3`, and a separate profile. Existing Electron and preview data is not silently migrated or deleted. Sign in once in the new application; keep your old installation until you have confirmed your workflow. The Linux DEB package name is `vibe-z-3`.

Native Linux packages/AppImage require glibc >= 2.39. DEB targets Ubuntu 24.04-class systems with WebKitGTK 4.1; RPM/Arch dependencies must resolve on the target system. Flatpak uses its declared GNOME runtime. macOS requires 14+. Windows requires WebView2.

The old Electron release files remain available. VibeZ 3 must not be offered as an Electron automatic update: publication either preserves the old Latest selection or adds verified legacy update metadata and its original files before switching Latest. Store upgrades are a separate delivery path.

## Signing, Store and feature boundaries

Direct Windows EXE/MSI installers are **unsigned** and may trigger Windows reputation warnings. The unsigned MSIX is built for the approved Partner Center product with version `3.0.0.0`, but is for Store submission, not ordinary direct installation. It has **not** been submitted or certified just because this GitHub build passed. macOS packages are Developer ID signed, notarized and stapled.

Screenshots use the operating system's interactive capture tools. Automatic installer execution, global screenshot shortcuts and microphone/camera access are not enabled in this release.

## About the old Electron security check

The separately retained Electron build dependency tree has a reported `http-cache-semantics` advisory (GHSA-ch52-4w7c-c8xp). It is not part of VibeZ 3's independently audited dependency tree. The finding must remain visible for Electron maintenance; it is not a reason to label the Rust/Tauri audit as failed or to remove security auditing.

---

**A new foundation. A rebuilt language engine. The same VibeZ spirit.**

VibeZ is independent, free and MIT licensed. It is not affiliated with or endorsed by Mistral AI. The website, account features and service availability remain provided by Mistral.
