<div align="center">

<img src="icon.png" width="128" alt="VibeZ application logo">

<h1>VibeZ 3</h1>
<h2>Same Vibe. Rebuilt in Rust.</h2>

<p><strong>Goodbye, Electron. Hello, Rust + Tauri.</strong></p>
<p>A new desktop foundation. A rebuilt language engine.<br>Windows, macOS and Linux — one version, twelve release files.</p>

<p>
<a href="https://github.com/lecomputeur/vibez/releases/tag/v3.0.1"><strong>Explore VibeZ 3.0.1</strong></a> ·
<a href="https://lecomputeur.github.io/vibez/">Website & installation guides</a> ·
<a href="V3-RELEASE.md">What's new</a>
</p>

<p><strong>RUST / TAURI</strong> &nbsp; | &nbsp; <strong>34 INTERFACE LANGUAGES</strong> &nbsp; | &nbsp; <strong>FREE & OPEN SOURCE</strong></p>

</div>

> **Release status:** the complete 3.0.1 build has passed its all-format gate. Public availability is determined by the [release page](https://github.com/lecomputeur/vibez/releases/tag/v3.0.1); the Microsoft Store listing is updated separately. [View the verified build](https://github.com/lecomputeur/vibez/actions/runs/37219669459).

## Not a new coat of paint. A new desktop foundation.

**VibeZ 3 is the project's move from an Electron desktop shell to a Rust-powered Tauri application.** The familiar VibeZ controls remain; the technology underneath has changed.

Instead of shipping its own Electron runtime, VibeZ 3 uses the operating system's webview: **WebKitGTK on Linux, Microsoft WebView2 on Windows and Apple's WKWebView on macOS**. Rust handles the native application layer; the bundled interface still uses web technologies. This is not a claim that the Mistral website has been rewritten in Rust.

Back and Forward, reload, language selection, zoom, screenshot capture, optional tray/menu-bar access and optional start-at-login bring Mistral Vibe into its own focused desktop window.

**A substantial architectural change — without inventing benchmark numbers.** Package size, startup time and memory use depend on the platform and workload; no universal speed or memory reduction is claimed here.

## A language engine rebuilt around your choice

**System language should mean system language — not an unexpected English default.** The language module was reworked from startup preparation to saved preferences and browser handoff.

| What you choose | What VibeZ 3 does |
|---|---|
| **System** | Resolves the operating-system language and selects the matching VibeZ interface bundle. |
| **A specific language** | Saves your choice and applies the corresponding supported preference to the Mistral page. |
| **Switch languages while using the app** | Processes changes in order; an older delayed response cannot overwrite your newer choice. |
| **Open the app again** | Restores the saved preference and prepares the browser language before opening remote content. |
| **Sign in** | Defers language-triggered navigation during authentication instead of sending an in-progress login back to Home. |

The rebuilt module also prevents stale settings windows from reverting a newer language, retries temporary startup failures within a fixed limit and clears only its own recovered warning. Detailed diagnostics stay in Settings rather than filling the toolbar.

**Tested, not just translated:** the automated suite exercises native language-cookie preparation on WebKitGTK, WebView2 and WKWebView. The reported Dutch/English switching and startup issues were also tested by the maintainer on Linux/Cinnamon. VibeZ includes **34 interface-language bundles**; the embedded website's available translations are controlled by Mistral, and unsupported website languages fall back to English. Your physical location does not override your language choice.

## One version. Every distribution format.

All files below belong to the same **VibeZ 3.0.1** release. No platform was dropped to make the build green.

| Platform | Downloads |
|---|---|
| **Linux x86-64** | [AppImage](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-Linux-x64.AppImage) · [DEB](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-Linux-x64.deb) · [RPM](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-Linux-x64.rpm) · [Arch/Pacman](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-Linux-x64.pkg.tar.zst) · [Flatpak](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-Linux-x64.flatpak) |
| **Windows x64** | [Setup EXE](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-Windows-x64-Setup.exe) · [MSI](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-Windows-x64.msi) · [Store submission MSIX](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-Windows-x64-Store.msix) |
| **macOS Apple Silicon** | [DMG](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-macOS-arm64.dmg) · [ZIP](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-macOS-arm64.zip) |
| **macOS Intel** | [DMG](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-macOS-x64.dmg) · [ZIP](https://github.com/lecomputeur/vibez/releases/download/v3.0.1/VibeZ-3.0.1-macOS-x64.zip) |

**Downloads become accessible when the release is published.** Until then the complete set is held in the release draft. macOS packages are Developer ID signed, notarized and stapled. Direct Windows EXE/MSI installers are unsigned; Windows may show a reputation warning. The unsigned MSIX is for Partner Center submission, not the recommended direct installer. Building it does **not** mean Microsoft has certified or published version 3.

Check downloads against the release's `SHA256SUMS`. Choose one package for your system, not every file. Installation guides: [Linux](https://lecomputeur.github.io/vibez/linux.html) · [Windows](https://lecomputeur.github.io/vibez/windows.html) · [macOS](https://lecomputeur.github.io/vibez/macos.html).

## Familiar controls. Stronger foundations.

The Linux window no longer grows its minimum size when maximized. Shrink, grow, maximize and restore are checked against requested dimensions. Window and tray icons are checked across repeated starts. Navigation now reads the native browser's history state on each platform instead of using placeholder values.

Preferences use field-level updates and conflict detection, with versioned storage and recovery for damaged settings. Automatic update checks are enabled by default for direct installs and only consider **published VibeZ 3 releases**, never expiring CI artifacts. A manual **Check for updates** action remains available. Microsoft Store installations use Store delivery. Remote website content and login popups do not receive the native privileges of the bundled toolbar and settings window.

## Moving from VibeZ 2 or the Tauri preview

VibeZ 3 uses the `nl.lecomputeur.vibez3` app identity and the `vibez3` executable. Its direct installers keep their profile separate from the old Electron app and the 0.1.x preview. Existing profiles are not silently copied, deleted or overwritten; sign in once in the new app. Old releases remain in the [release archive](https://github.com/lecomputeur/vibez/releases).

On Linux, the DEB package is **`vibe-z-3`**. Close any running copy before updating. The separate preview is not automatically uninstalled. Store-delivered upgrades use the Store product identity and are a separate migration path.

Native Linux packages and AppImage require **glibc 2.39 or newer**; DEB targets Ubuntu 24.04-class systems with WebKitGTK 4.1. An AppImage is not a guarantee of compatibility with older distributions. Flatpak uses the declared GNOME runtime. macOS requires **14 or newer**. Windows requires **WebView2**.

## What the tests prove — and what they do not

The verified release workflow passed its dependency-security check, frontend/Rust tests, native browser/window probes, Linux icon tests, packaging checks and macOS signing/notarization gates. All twelve required deliverables were collected from the frozen source. See [validation and release notes](V3-RELEASE.md).

Automated native probes are offline tests. They are not a claim that every live sign-in provider, Linux distribution, Wayland session, fractional scale or website feature has been tested. Microphone/camera access, global screenshot shortcuts and unattended installer execution are not enabled in this version. Direct-download updates remain user-confirmed; Microsoft Store updates are delivered by the Store. Screenshots use the operating system's interactive tools; updates are installed manually.

## Build, contribute, make it better

The new application lives in [`desktop/`](desktop/). The original root JavaScript/package files retain the Electron 2.x source, and [`tauri-preview/`](tauri-preview/) retains the preview history.

```sh
cd desktop
npm ci --ignore-scripts
npm test
npm run build -- -- --locked
```

Install the native Tauri build prerequisites for your operating system first. Dependency lockfiles and the Rust toolchain version are tracked with the source.

**Enjoy the new generation? Star the project, share it, or report a reproducible issue.** VibeZ is free and MIT licensed.

---

VibeZ is an independent desktop client for [Mistral Vibe](https://vibe.mistral.ai/). It is **not affiliated with, endorsed by or supported by Mistral AI**. Internet access and a Mistral account may be required; website features and account plans remain provided by Mistral.
