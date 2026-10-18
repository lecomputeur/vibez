<div align="center">

<img src="icon.png" width="128" alt="VibeZ application logo">

<h1>VibeZ 3</h1>
<h2>Same Vibe. Rebuilt in Rust.</h2>

<p><strong>Goodbye, Electron. Hello, Rust + Tauri.</strong></p>
<p>Rewritten from the ground up for VibeZ 3. A rebuilt language engine that directly addresses the earlier language-selection and startup issues.<br>Windows, macOS and Linux — one version, twelve release files.</p>

<p>
<a href="https://github.com/lecomputeur/vibez/releases/tag/v3.0.8"><strong>Explore VibeZ 3.0.8</strong></a> ·
<a href="https://lecomputeur.github.io/vibez/">Website & installation guides</a> ·
<a href="V3-RELEASE.md">What's new</a>
</p>

<p><strong>RUST / TAURI</strong> &nbsp; | &nbsp; <strong>34 INTERFACE LANGUAGES</strong> &nbsp; | &nbsp; <strong>FREE & OPEN SOURCE</strong></p>

</div>

> **VibeZ 3.0.8:** Fix Linux routing of embedded Cloudflare verification frames, and update the version shown on every platform. [Release downloads](https://github.com/lecomputeur/vibez/releases/tag/v3.0.8) · [Release notes and validation](V3-RELEASE.md). Microsoft Store delivery remains separate.

**Cloudflare verification frames on Linux stay in the app instead of opening as external browser links.**

The routing fix applies to AppImage, DEB, RPM, Arch/Pacman and Flatpak. Ordinary external links still open in your browser. Existing settings, profiles and the Linux rich-chat scrolling and resize improvements from 3.0.7 are retained. Windows and macOS receive the version/title update to `VibeZ V3.0.8`; their navigation and rendering behavior are unchanged.

The faulty routing was reproduced with controlled synthetic frames in the published 3.0.7 Linux executable. A genuine Turnstile verification and the complete reported openSUSE failure have not been reproduced. See the [validation and limits](V3-RELEASE.md#validation-and-limits).

## Not a new coat of paint. A new desktop foundation.

**VibeZ 3 was rewritten from the ground up around Rust + Tauri.** This is not an incremental Electron port: the VibeZ desktop application architecture, native window layer, settings flow, navigation integration and platform packaging were rebuilt for the new generation. The familiar VibeZ controls remain, but the application underneath is new.

Instead of shipping its own Electron runtime, VibeZ 3 uses the operating system's webview: **WebKitGTK on Linux, Microsoft WebView2 on Windows and Apple's WKWebView on macOS**. Rust handles the native application layer; the bundled interface still uses web technologies. This is not a claim that the Mistral website has been rewritten in Rust.

Back and Forward, reload, language selection, zoom, screenshot capture, optional tray/menu-bar access and optional start-at-login bring Mistral Vibe into its own focused desktop window.

**A substantial architectural change — without inventing benchmark numbers.** Package size, startup time and memory use depend on the platform and workload; no universal speed or memory reduction is claimed here.

## The language problem was rebuilt, not patched around

**System language should mean system language — not an unexpected English default.** VibeZ 3 specifically rebuilds the language flow that caused the earlier startup and switching problems. System-language detection, saved preferences, startup preparation, live switching and the handoff to Mistral's supported website locale were redesigned together instead of layering another workaround onto the old Electron behavior.

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

The **VibeZ 3.0.8** build produced and verified all twelve files below from one frozen source commit. Check the release asset list for the available downloads.

| Platform | Downloads |
|---|---|
| **Linux x86-64** | [AppImage](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-Linux-x64.AppImage) · [DEB](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-Linux-x64.deb) · [RPM](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-Linux-x64.rpm) · [Arch/Pacman](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-Linux-x64.pkg.tar.zst) · [Flatpak](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-Linux-x64.flatpak) |
| **Windows x64** | [Setup EXE](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-Windows-x64-Setup.exe) · [MSI](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-Windows-x64.msi) · [Store submission MSIX](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-Windows-x64-Store.msix) |
| **macOS Apple Silicon** | [DMG](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-macOS-arm64.dmg) · [ZIP](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-macOS-arm64.zip) |
| **macOS Intel** | [DMG](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-macOS-x64.dmg) · [ZIP](https://github.com/lecomputeur/vibez/releases/download/v3.0.8/VibeZ-3.0.8-macOS-x64.zip) |

macOS publication requires Developer ID signing, notarization and stapling. Direct Windows EXE/MSI installers are unsigned; Windows may show a reputation warning. The unsigned MSIX is for Partner Center submission, not the recommended direct installer. Building it does **not** mean Microsoft has certified or published the update.

Check downloads against the release's `SHA256SUMS`; `source-commit.txt` identifies the package source. Choose one package for your system, not every file. Installation guides: [Linux](https://lecomputeur.github.io/vibez/linux.html) · [Windows](https://lecomputeur.github.io/vibez/windows.html) · [macOS](https://lecomputeur.github.io/vibez/macos.html).

## Familiar controls. Stronger foundations.

The Linux window no longer grows its minimum size when maximized. Shrink, grow, maximize and restore are checked against requested dimensions. Window and tray icons are checked across repeated starts. Navigation now reads the native browser's history state on each platform instead of using placeholder values.

Preferences use field-level updates and conflict detection, with versioned storage and recovery for damaged settings. Automatic update checks are enabled by default for direct installs and only consider **published VibeZ 3 releases**, never expiring CI artifacts. A manual **Check for updates** action remains available. VibeZ checks for published updates automatically at startup. Download the matching package inside VibeZ, with progress, cancellation and SHA-256 verification, then open the installer. VibeZ closes automatically when it hands off the installation. AppImage updates replace the original file and start the new version after the old instance exits. Microsoft Store installations use Store delivery. Remote website content and login popups do not receive the native privileges of the bundled toolbar and settings window.

## Moving from VibeZ 2 or the Tauri preview

VibeZ 3 uses the `nl.lecomputeur.vibez3` app identity and the `vibez3` executable. Its direct installers keep their profile separate from the old Electron app and the 0.1.x preview. Existing profiles are not silently copied, deleted or overwritten; sign in once in the new app. Old releases remain in the [release archive](https://github.com/lecomputeur/vibez/releases).

On Linux, the DEB package is **`vibe-z-3`**. The DEB, RPM and Arch installers close the running installed copy automatically before replacing it. The separate preview is not automatically uninstalled. Store-delivered upgrades use the Store product identity and are a separate migration path.

Native Linux packages and AppImage require **glibc 2.39 or newer**; DEB targets Ubuntu 24.04-class systems with WebKitGTK 4.1. An AppImage is not a guarantee of compatibility with older distributions. Flatpak uses the declared GNOME runtime. macOS requires **14 or newer**. Windows requires **WebView2**.

## What the tests prove — and what they do not

The [verified 3.0.8 build](https://github.com/lecomputeur/vibez/actions/runs/39112469853) passed all nine required jobs, including dependency audits, frontend/Rust tests, native Linux Cloudflare frame and popup routing, rich-chat regressions, screenshots/paste, updates, all twelve packages and macOS signing/notarization. Its frozen source is [`b8fb3a3`](https://github.com/lecomputeur/vibez/commit/b8fb3a31692776ca8b903cab01397ab85c5e5304); the [versioned release proof](tools/release-v3/release-proof-3.0.8.json) pins the source and run. The Windows job created and validated the Store MSIX version **3.0.8.0**. See the [release notes](V3-RELEASE.md) for the reproduction and its limits. Earlier 3.0.7 and 3.0.6 evidence remains historical.

Automated native probes are offline tests. They are not a claim that every live sign-in provider, Linux distribution, Wayland session, fractional scale or website feature has been tested. Microphone/camera access, global screenshot shortcuts and unattended installer execution are not enabled in this version. Direct-download updates remain user-confirmed; Microsoft Store updates are delivered by the Store. Screenshots offer native visible-page, full-loaded-page and desktop-area capture, with optional direct paste into a draft. Downloaded updates are installed only after your confirmation.

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

## Screenshots

Visible page, Full page and Selection remain in a compact menu. Paste directly into Chat and Work drafts without sending a message. In Code, choose Screenshot as file, save as PNG and share the file separately. The short Code explanation and conditional sign-in notice are translated into all 34 interface languages. Copying and saving are available without signing in.

The macOS toolbar uses the actual area below the native titlebar. Chat/Work paste, settings, language selection and in-app update downloads remain available.
