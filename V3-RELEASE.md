# VibeZ 3.0.0 — Same Vibe. Rebuilt in Rust.

## Goodbye, Electron. Hello, Rust + Tauri.

**VibeZ's next chapter is a new desktop foundation, not a new coat of paint.** Version 3 moves the native application layer from Electron to Rust/Tauri while keeping the familiar VibeZ workspace and controls. WebKitGTK on Linux, Microsoft WebView2 on Windows and Apple WKWebView on macOS provide the web engine. The interface and the Mistral website still use web technologies; this is not a claim that every line is Rust or that every workload is faster.

## A language engine rebuilt around your choice

System-language detection, saved preferences, startup preparation and browser handoff have been reworked together. Language changes are revisioned so older responses cannot undo a new choice. Stale settings windows preserve unrelated newer changes. Temporary startup failures get bounded retries; recovery clears only the corresponding old warning. Language-triggered navigation waits during sign-in.

Native language preparation has been tested on all three browser engines. The maintainer confirmed the reported Dutch/English switching, startup and icon fixes on Linux/Cinnamon. VibeZ includes **34 interface-language bundles**. Website translation support remains Mistral's responsibility; unsupported website languages fall back to English. Physical location does not override the selected language.

## One version. All twelve release files.

| Platform | Formats |
|---|---|
| Linux x86-64 | AppImage, DEB, RPM, Arch/Pacman, Flatpak |
| Windows x64 | Setup EXE, MSI, Store-submission MSIX |
| macOS Apple Silicon | Developer ID signed, notarized and stapled DMG and ZIP |
| macOS Intel | Developer ID signed, notarized and stapled DMG and ZIP |

Every package is version **3.0.0** (Store package version **3.0.0.0**) and originates from frozen source `b30a4b58e71d3482fa79433779ff24410525ad01`. The [complete build](https://github.com/lecomputeur/vibez/actions/runs/37219669459) passed all nine jobs, including security and the twelve-file gate. `SHA256SUMS` verifies the original twelve packages and source record. The publication process rechecks them without rebuilding or changing installers.

## Native behavior, checked in the real engines

Native Back/Forward state replaces placeholder values. Tests exercise cookie preparation, popup callbacks, isolation of native privileges, actual window resize/maximize/restore dimensions and hidden-state preservation. Linux icon checks inspect window/tray pixels across repeated starts. The language and layout fixes from the tested preview are retained.

## Upgrading from version 2 or the preview

Install one version-3 package for your system and start **VibeZ 3**. The new direct-install app identity is `nl.lecomputeur.vibez3`, its executable is `vibez3`, and its DEB package is `vibe-z-3`. Profiles remain separate; sign in once. Existing data is not silently copied, deleted or overwritten. Store upgrades use the Store product identity and are a separate migration path.

Version 3 is the new public main release. Historical version-2 files remain in the archive. Small `latest*.yml` compatibility files are only for existing Electron updaters: they continue to reference the original version-2 packages, never a Tauri installer. Version 3 checks the published v3 release feed and installs updates manually. No in-place automatic Electron-to-Tauri migration is claimed.

## Requirements and boundaries

Native Linux packages/AppImage require glibc 2.39 or newer; DEB targets Ubuntu 24.04-class systems with WebKitGTK 4.1. Flatpak uses its declared GNOME runtime. macOS requires 14 or newer. Windows requires WebView2.

Direct Windows EXE/MSI downloads are unsigned and may show a reputation warning. The unsigned Store MSIX is a submission artifact, not a recommended sideload installer. Its creation does not mean the Microsoft Store listing has been updated or certified. macOS artifacts passed Developer ID signing and Apple notarization.

Automated native probes are offline checks, not a claim that every live sign-in provider, Linux desktop, Wayland configuration, fractional scale, screenshot or upload/download flow has been tested. Microphone/camera access, global screenshot shortcuts and automatic installer execution are not enabled in 3.0.0.

## Independent, free and open source

VibeZ is MIT licensed and independent of Mistral AI. Mistral provides the remote service, accounts and plans. **Enjoy the new generation? Star the project, share it and help make it better.**
