<div align="center">

<img src="icon.png" width="128" alt="VibeZ application logo">

<h1>VibeZ</h1>
<h2>Mistral Vibe has its own desktop app</h2>

<p><strong>VibeZ is winding down.</strong></p>

<p>
<a href="https://mistral.ai/products/vibe/"><strong>Get the official Vibe Desktop</strong></a> ·
<a href="https://lecomputeur.github.io/vibez/linux.html">VibeZ for Linux</a> ·
<a href="https://github.com/lecomputeur/vibez/releases">Release archive</a>
</p>

</div>

On 17 November 2026 Mistral released **Vibe Desktop** for macOS and Windows: Work, local folders and coding in one official app ([release notes](https://docs.mistral.ai/resources/release-notes)). It has been quite an undertaking, but our beloved Mistral Vibe finally has its long-awaited desktop client. VibeZ was always a stand-in for that app, so VibeZ is now winding down.

## What happens now

- **Windows and macOS:** use the official [Vibe Desktop](https://mistral.ai/products/vibe/). VibeZ for Windows and Mac is no longer developed and receives no further updates. The existing downloads stay available in the [release archive](https://github.com/lecomputeur/vibez/releases).
- **Linux:** Mistral says Linux support is coming soon. Until the official Linux app is available, VibeZ keeps supporting Linux: VibeZ 3.2.0 and the V4 Beta, with fixes for [reported problems](https://github.com/lecomputeur/vibez/issues/new/choose).
- **The code:** stays on GitHub under the MIT license. Development is winding down; no new features are planned.

## Thank you

**A special thank you to [ActiveUser435](https://github.com/ActiveUser435) and [HumanistAtypik](https://github.com/HumanistAtypik).** Your detailed reports and patient testing shaped VibeZ 3 and V4: Linux packages, local folders, the V4 interface, French wording, systems without a standard file layout and much more. Many fixes exist only because you took the time to write them down so carefully.

Thank you also to [wdeschepper-btb](https://github.com/wdeschepper-btb), [punk1234567](https://github.com/punk1234567) and everyone who downloaded, starred, tested, reported a problem or shared VibeZ. See all [community contributors](CONTRIBUTORS.md).

It has been a true pleasure.
— Le Computeur

## VibeZ V4 Beta for Linux

V4 lets Mistral Work and Code use local folders you choose, with every file change shown for your approval. It installs next to VibeZ 3 with its own profile and settings.

> VibeZ 4.0.0 is available for Linux. VibeZ 4 is final: Mistral Work and Code with your own folders on Linux, every change shown for your approval. It also works on systems such as NixOS and uses your desktop's own file dialog.
>
> [Download VibeZ 4.0.0](https://github.com/lecomputeur/vibez/releases/tag/v4.0.0) · [Linux installation guide](https://lecomputeur.github.io/vibez/linux.html#v4-alpha) · [Report a Linux problem](https://github.com/lecomputeur/vibez/issues/new/choose)

## VibeZ 3.2.0 downloads

The **VibeZ 3.2.0** build produced and verified all twelve files below from one frozen source commit. Linux is still supported; the Windows and macOS files remain as an archive and are no longer updated.

| Platform | Downloads |
|---|---|
| **Linux x86-64** | [AppImage](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-Linux-x64.AppImage) · [DEB](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-Linux-x64.deb) · [RPM](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-Linux-x64.rpm) · [Arch/Pacman](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-Linux-x64.pkg.tar.zst) · [Flatpak](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-Linux-x64.flatpak) |
| **Windows x64** (archive) | [Setup EXE](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-Windows-x64-Setup.exe) · [MSI](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-Windows-x64.msi) · [Store submission MSIX](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-Windows-x64-Store.msix) |
| **macOS Apple Silicon** (archive) | [DMG](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-macOS-arm64.dmg) · [ZIP](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-macOS-arm64.zip) |
| **macOS Intel** (archive) | [DMG](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-macOS-x64.dmg) · [ZIP](https://github.com/lecomputeur/vibez/releases/download/v3.2.0/VibeZ-3.2.0-macOS-x64.zip) |

macOS publication requires Developer ID signing, notarization and stapling. Direct Windows EXE/MSI installers are unsigned; Windows may show a reputation warning. The unsigned MSIX is for Partner Center submission, not the recommended direct installer. Building it does **not** mean Microsoft has certified or published the update.

Check downloads against the release's `SHA256SUMS`; `source-commit.txt` identifies the package source. Choose one package for your system, not every file. Installation guides: [Linux](https://lecomputeur.github.io/vibez/linux.html) · [Windows](https://lecomputeur.github.io/vibez/windows.html) · [macOS](https://lecomputeur.github.io/vibez/macos.html).

## Build from source

VibeZ V4 lives in [`v4/`](v4/) (build and test steps in [`v4/README.md`](v4/README.md)); the VibeZ 3 application lives in [`desktop/`](desktop/). The original root JavaScript/package files retain the Electron 2.x source, and [`tauri-preview/`](tauri-preview/) retains the preview history.

```sh
cd desktop
npm ci --ignore-scripts
npm test
npm run build -- -- --locked
```

Install the native Tauri build prerequisites for your operating system first. Dependency lockfiles and the Rust toolchain version are tracked with the source.

VibeZ is free and MIT licensed.

---

VibeZ is an independent desktop client for [Mistral Vibe](https://vibe.mistral.ai/). It is **not affiliated with, endorsed by or supported by Mistral AI**. Internet access and a Mistral account may be required; website features and account plans remain provided by Mistral.
