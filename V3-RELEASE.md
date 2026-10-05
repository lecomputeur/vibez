# VibeZ 3.0.1 — Same Vibe. Rebuilt in Rust. Now update-aware.

**Goodbye Electron. Hello Rust + Tauri. VibeZ 3 was rewritten from the ground up, including a redesigned language system that directly addresses the earlier startup and language-switching issues.**

VibeZ 3.0.1 is the first refinement release of the completely rebuilt Rust/Tauri generation. VibeZ 3 is not a reskinned Electron build: the desktop application layer was rebuilt around Rust, Tauri and the operating system's native webview. The language flow was also redesigned as part of that rewrite, specifically to resolve the earlier system-language, startup and switching problems. Version 3.0.1 keeps those fixes and restores a capability users of VibeZ 2 expected: **automatic update checking**.

## What changed in 3.0.1

- **Automatic update checks are back.** Direct installations check published VibeZ 3 releases shortly after startup by default.
- **You stay in control.** Automatic checking can be switched off in Settings, and **Check for updates** is available manually.
- **No unsafe silent installer execution.** Direct-download builds notify you about a newer published release and leave installation user-confirmed.
- **Microsoft Store-aware.** Store installations keep the existing `LeComputeur.VibeZDesktop` product identity and use Microsoft Store delivery instead of being redirected to a GitHub installer.
- **The rebuilt language module remains intact.** System-language detection, saved language preferences, ordered switching and Mistral-site language preparation are retained.
- **Store packaging corrected.** The MSIX uses the reserved Store display name **VibeZ Desktop** while running the VibeZ 3 Rust/Tauri application.

## A different desktop foundation

VibeZ 3 moved the desktop shell from Electron to **Rust + Tauri**. Linux uses WebKitGTK, Windows uses Microsoft WebView2 and macOS uses WKWebView. The remote Mistral website is still a web application; the native VibeZ application layer is what was rebuilt.

That architecture is shared across all supported VibeZ 3 packages:

| Platform | Formats |
|---|---|
| Linux x86-64 | AppImage, DEB, RPM, Arch/Pacman, Flatpak |
| Windows x64 | Setup EXE, MSI, Microsoft Store MSIX |
| macOS Apple Silicon | Developer ID signed, notarized and stapled DMG + ZIP |
| macOS Intel | Developer ID signed, notarized and stapled DMG + ZIP |

Every release asset is version **3.0.1**; the Store package version is **3.0.1.0**. The release workflow requires all twelve application packages before the release can be promoted.

## Language handling rebuilt to solve the earlier problems

The language system was redesigned rather than carried over from Electron. System now resolves the operating-system UI language; explicit choices are stored and restored; startup prepares the selected website locale before normal browsing; and live changes are serialized so an older delayed operation cannot overwrite a newer choice. Authentication navigation is protected from language-triggered redirects, and temporary startup failures are retried without leaving stale warnings behind.

VibeZ provides **34 interface-language bundles**. Mistral controls which languages its own website supports; unsupported website languages fall back safely instead of writing invalid locale values.

## Update behavior

For GitHub/direct installations, automatic checking is enabled by default. VibeZ checks only public, non-prerelease VibeZ 3 releases and matches the current operating system/architecture. When a newer version exists, VibeZ tells the user and the installation remains user-confirmed.

For the Microsoft Store build, Microsoft Store is the delivery channel. VibeZ does not replace a Store installation with a GitHub installer.

Historical Electron 2.x release assets stay in the archive. Compatibility metadata continues to point old Electron updaters only to the original 2.x installers, never to a Tauri package.

## Validation and boundaries

The release pipeline runs frontend and Rust tests, dependency/security checks, native browser/history/language/popup probes, Linux package/icon checks, Windows WebView2 tests, and Apple Developer ID signing/notarization for both Mac architectures.

Automated native probes are not a claim that every live sign-in provider, Linux desktop, Wayland setup or fractional-scale configuration has been exercised. Microphone/camera, global screenshot shortcuts and unattended direct-installer execution are not enabled.

VibeZ is free, MIT-licensed and independent of Mistral AI.
