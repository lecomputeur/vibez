# VibeZ 3.0.0 — A new native desktop generation

**Release candidate: public stable promotion requires every gate below.**

VibeZ 3 moves the desktop application to Rust and Tauri, with the operating system's WebKitGTK, WebView2 or WKWebView engine. It retains the familiar VibeZ toolbar, the Vibe website, 34 language bundles, native screenshot tools, zoom and optional tray/autostart integration.

## One version, all formats

The required artifact set is Linux x64 AppImage, DEB, RPM, Arch/Pacman and Flatpak; Windows x64 Setup.exe, MSI and Store MSIX; macOS x64 and arm64 DMG and ZIP containing signed/notarized applications. Every artifact must carry version **3.0.0**, originate from the same frozen source commit and have a SHA-256 checksum. A successful DEB build alone is not an all-platform release.

## Release gates

- Track the promoted `desktop/` source plus Cargo/npm lockfiles and a concrete Rust toolchain before native builds.
- Pass the JavaScript behavioral/isolation suite and Rust policy/update/language tests; run dependency security checks.
- Exercise actual native Back/Forward state, cookie preparation, popup callbacks, restricted native privileges and window resizing/hidden-state behavior.
- Verify installed Linux launcher/window/tray icon pixels across repeated starts, not just icon-file existence.
- Produce and validate all twelve required installer/archive files. Keep the original app identity separate from Electron/preview profiles.
- Sign macOS applications with Developer ID, obtain accepted notarization and staple tickets before distribution.
- Review platform acceptance and the complete draft. Do not promote with a failing job, missing package or known unresolved defect.

## Public download and update behavior

The v3 update checker only considers non-draft, non-prerelease GitHub releases with a matching v3-or-newer platform asset on this repository. CI artifacts are for validation, not the public update feed. Installer downloads and checksums belong on the permanent GitHub release.

Before marking v3 as GitHub's latest release, protect the installed Electron updater with legacy 2.x metadata pointing to its original immutable asset URLs. Do not offer a Tauri executable to Electron's automatic updater. The original v2 releases are retained.

## Store and signing disclosure

The direct Windows installer is unsigned until a trusted signing service is configured; do not describe it as signed. The MSIX is built for the existing approved Partner Center identity and version 3.0.0.0, but building it does not submit it or change the live Store listing. Microsoft certification remains separate. macOS artifacts must be Developer ID signed and notarized.

## Compatibility

Native Linux/AppImage builds target glibc >= 2.39; native package dependencies must resolve on the target distribution. Flatpak uses the declared GNOME runtime. macOS 14+ is required for separate persistent WKWebView stores. Windows requires WebView2. Existing profiles are not silently migrated; users can keep 2.x installed during migration.

## Acceptance still required

Automated native tests are offline probes, not a claim to have signed in with a real Google, Microsoft or Mistral account on every platform. Confirm real sign-in, screenshot/clipboard, upload/download, first start and upgrade on the supported desktop environments. Wayland and fractional scaling must not be claimed tested merely because X11 integer-scale checks passed.

No new microphone/camera privileges, global screenshot shortcut or automatic installer execution is introduced.
