<div align="center">
<img src="icon.png" width="112" alt="VibeZ logo">
<h1>VibeZ 3</h1>
<h3>A new native desktop generation for Mistral Vibe.</h3>
<p><strong>Rust + Tauri · Windows · macOS · Linux</strong></p>
<p>One desktop experience. Every distribution format. Your operating system's web engine.</p>
</div>

> **3.0.0 release candidate — all-platform verification in progress.**
> This branch is preparing the complete next-generation release. Installer availability and successful validation are tracked in the **VibeZ 3 — all desktop formats** workflow. It is not a claim that version 3 is already published or certified by a store.

## Built for the desktop

VibeZ opens Mistral Vibe in its own application window, with a dedicated navigation toolbar, language selection, zoom, screenshot controls, optional system-tray behavior and optional start-at-login. The interface includes 34 language bundles. Version 3 uses Rust/Tauri and the system webview instead of bundling Electron.

VibeZ is an independent project. It is **not affiliated with, endorsed by or supported by Mistral AI**. A Mistral account and internet connection may be required. Website functionality and account plans remain provided by Mistral.

## The complete 3.0.0 distribution family

| Platform | Formats being built and verified |
|---|---|
| Linux x86-64 | **AppImage · DEB · RPM · Arch/Pacman · Flatpak** |
| Windows x64 | **Setup EXE · MSI · Microsoft Store MSIX** |
| macOS Intel | **Signed and notarized app / DMG / ZIP** |
| macOS Apple Silicon | **Signed and notarized app / DMG / ZIP** |

No stable release is published with a missing or failing required format. Store package creation is separate from store submission and certification. Existing 2.x releases remain available in the repository's release archive.

## What changes in version 3

The tested Linux language, window sizing and icon corrections are retained. The v3 implementation adds native Windows/macOS browser-state handling, verified language preference application, macOS screenshot support and a shared update checker that only selects **published releases**, never temporary CI artifacts.

The release process freezes source and dependency lockfiles before building, runs frontend and Rust tests, checks real browser/window behavior, validates native packaging and requires Apple notarization for macOS distribution. See [the release checklist](V3-RELEASE.md) for what is proved by the checks and what still needs platform acceptance.

## Compatibility and migration

The native application uses its own `nl.lecomputeur.vibez3` identity and `vibez3` executable. Existing Electron and preview profiles are not silently imported, deleted or overwritten. This makes it possible to keep the previous application installed during migration; sign in once in the new application.

Linux native packages currently target glibc 2.39 / Ubuntu 24.04-class systems with WebKitGTK 4.1. An AppImage is not a promise to support older glibc versions. Flatpak supplies its declared runtime. macOS requires version 14 or newer. Windows uses Microsoft WebView2.

## Deliberate boundaries

Only the bundled controls can call native commands; the remote site and sign-in popups do not receive those privileges. Diagnostics omit credential-bearing URLs and chat content. Microphone/camera access, global shortcuts and automatic package installation are not enabled in this release. Updates are checked manually; screenshots use the operating system's interactive capture tools.

## Source layout

`desktop/` contains VibeZ 3 after the tracked source promotion. `tauri-preview/` preserves the proven 0.1.x preview. The original root JavaScript and package files preserve the Electron 2.x implementation; they are not renamed to pretend to be version 3.

MIT licensed. Contributions and reproducible issue reports are welcome.
