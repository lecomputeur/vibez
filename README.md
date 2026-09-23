# VibeZ

A free cross-platform desktop client for [Mistral Vibe](https://vibe.mistral.ai/) with native desktop integration, screenshot tools and automatic update checks.

> VibeZ is an independent desktop client and is not affiliated with or supported by Mistral AI. A Mistral account may be required to use Vibe.

## Platforms

VibeZ brings the same experience to all three major desktop platforms from one shared Electron codebase.

| Platform | Architectures | Packages |
| --- | --- | --- |
| **Windows** | x64 | NSIS `.exe` (unsigned direct download); MSIX for Microsoft Store |
| **macOS** | Apple Silicon, Intel | Developer ID signed and Apple-notarized `.dmg` and `.zip` |
| **Linux** | x86_64 | AppImage, DEB, RPM, Pacman and Flatpak |

VibeZ 2 macOS builds are Developer ID signed and Apple-notarized. The Windows x64 installer downloaded directly from GitHub remains **unsigned** while VibeZ builds enough public adoption to qualify for sponsored signing. A separate Store MSIX named **VibeZ Desktop** is being prepared as the recommended Windows route. Microsoft re-signs that MSIX after certification. See **[Windows & macOS installation](WINDOWS-MACOS.md)** for Windows SmartScreen guidance, macOS screenshot permission and checksum verification.

See the **[Code signing policy](https://lecomputeur.github.io/vibez/code-signing-policy.html)** for the current Windows and macOS release policy.

## Features

- Opens the official Mistral Vibe web app in a dedicated desktop window.
- **Global Screenshot** shortcut (`Ctrl+Shift+S` by default; Command is used on macOS where appropriate).
- Built-in Screenshot button with multi-monitor support.
- System tray/menu-bar access with Open, Screenshot, Settings, Check for updates, About and Quit actions.
- Platform-aware start-at-login, tray behavior, hardware acceleration, zoom, language and update settings.
- Wayland/X11 display-backend controls on Linux only.
- VibeZ-owned interface follows the operating-system language automatically, with 34 built-in languages and RTL support.
- Optional start at login, minimize to tray and close to tray.
- Safer update flow with **Restart & update** or **Later** where the platform supports in-app installation.
- External links open in your normal browser and web permissions are restricted to trusted Mistral pages.
- About window with version and system information for bug reports.
- `vibez://` protocol support.
- Automated CI builds and package verification on Linux, Windows and macOS.
- SHA-256 checksums for public release downloads.

## Questions & Support

Need help using VibeZ, have a question, or want to suggest an idea? Start a **[Q&A discussion](https://github.com/lecomputeur/vibez/discussions/categories/q-a)**. Discussions are the preferred place for how-to questions, ideas, feedback and general conversation.

Found a reproducible bug or error? **[Open a bug report](https://github.com/lecomputeur/vibez/issues/new?template=bug_report.yml)**. Please include your operating system, VibeZ version, what you expected, what happened and the steps needed to reproduce the problem.

Before posting, please check the existing **[Discussions](https://github.com/lecomputeur/vibez/discussions)** and **[Issues](https://github.com/lecomputeur/vibez/issues)** to see whether your question or problem has already been reported.

## Download

Public releases are available on the **[GitHub Releases page](https://github.com/lecomputeur/vibez/releases)**.

### Windows

- Most Windows PCs: `VibeZ-<version>-Windows-x64.exe`

The direct GitHub installer is unsigned, so Windows may show **Windows protected your PC** or **Unknown publisher**. Verify `SHA256SUMS` and use the steps in [WINDOWS-MACOS.md](WINDOWS-MACOS.md) only when the installer came from this official repository. The Microsoft Store version will become the recommended Windows installation route after its listing is approved.

### macOS

- Apple Silicon (M1/M2/M3/M4 and newer): `VibeZ-<version>-macOS-arm64.dmg`
- Intel Mac: `VibeZ-<version>-macOS-x64.dmg`
- ZIP builds are also published for both architectures.

VibeZ 2 macOS builds are Developer ID signed and Apple-notarized. The Screenshot feature still requires macOS Screen & System Audio Recording / Screen Recording permission.

### Linux quick install

Install the latest Linux release with one command:

```bash
curl -fsSL https://raw.githubusercontent.com/lecomputeur/vibez/main/install.sh | bash
```

The installer supports x86_64 Linux, detects your distribution, downloads the matching package from the latest GitHub release and verifies its SHA-256 checksum when `SHA256SUMS` is available.

To uninstall a package installed this way:

```bash
curl -fsSL https://raw.githubusercontent.com/lecomputeur/vibez/main/install.sh | bash -s -- --uninstall
```

### Linux packages

For x86_64 Linux systems, the release page provides:

- Debian / Ubuntu / Linux Mint: `.deb`
- Fedora and RPM-based distributions: `.rpm`
- Arch Linux / Manjaro / EndeavourOS: `.pacman` / `.pkg.tar.zst`
- Portable Linux: `.AppImage`
- Flatpak bundle on x86_64: `.flatpak`

Manual examples:

```bash
sudo apt install ./VibeZ_<version>_amd64.deb
sudo dnf install ./VibeZ-<version>.x86_64.rpm
sudo pacman -U ./VibeZ-<version>.pacman
chmod +x VibeZ-<version>.AppImage && ./VibeZ-<version>.AppImage
flatpak install --user ./VibeZ-<version>-x86_64.flatpak
```

## Security and direct Windows downloads

VibeZ does **not** bypass Windows SmartScreen or administrator policies. Direct GitHub Windows installers remain unsigned and are clearly identified as such. VibeZ 2 macOS packages are Developer ID signed and Apple-notarized.

For every release:

1. Download VibeZ only from this repository or the website linked by this repository.
2. Download `SHA256SUMS` from the same release.
3. Verify the checksum if you want an additional integrity check.
4. For a direct Windows download, follow the SmartScreen instructions in [WINDOWS-MACOS.md](WINDOWS-MACOS.md).

Managed work/school computers can block unsigned Windows software completely; an administrator may be required in that case.

## Languages

By default, **System** follows the language reported by Windows, macOS or Linux. VibeZ has complete built-in translations for 34 major languages, including English, Dutch, German, French, Spanish, Italian, Portuguese, Polish, Russian, Ukrainian, Turkish, Simplified and Traditional Chinese, Japanese, Korean, Hindi, Bengali, Punjabi, Marathi, Telugu, Tamil, Gujarati, Indonesian, Vietnamese, Thai, Filipino, Javanese, Swahili, Hausa, Amharic, Arabic, Hebrew, Persian and Urdu.

Arabic, Hebrew, Persian and Urdu use right-to-left layout in VibeZ-owned interfaces. Unsupported system locales fall back to English. Choosing a VibeZ language manually changes VibeZ menus, dialogs, screenshot tools and Settings; it does not force the embedded Mistral Vibe website into that language.

## Screenshot workflow

Start the Screenshot tool from VibeZ or use the global shortcut, then drag over the area you want to share. VibeZ captures the selected region across multi-monitor setups and brings VibeZ forward.

In Vibe Chat and Work, VibeZ places the screenshot on the clipboard and pastes it into the composer. In Vibe Code, VibeZ keeps the screenshot on the clipboard and shows guidance for saving it into your project as context.

On macOS, screen capture is protected by an operating-system permission. Enable VibeZ under **System Settings → Privacy & Security → Screen & System Audio Recording** (or **Screen Recording** on versions that use that name) when prompted.

## Desktop integration

VibeZ can stay available in the Windows system tray, macOS menu bar or Linux system tray, start automatically when you sign in, and optionally minimize or close to the tray.

Hardware acceleration can be Automatic, Enabled or Disabled on every platform. Linux additionally exposes Automatic, Wayland and X11 display-backend choices; these Linux-only controls are hidden on Windows and macOS.

## Command line

Package builds accept:

```text
vibez --version
vibez --screenshot
vibez --settings
```

The executable name/path differs by operating system, so Windows and macOS users will usually launch these through their installed app or a terminal path rather than a globally installed `vibez` shell command.

## Updates

VibeZ checks GitHub Releases for updates. Linux, Windows and the signed and notarized macOS packages support VibeZ's in-app update flow where their package type allows it.

Automatic update checking and install-on-quit can be configured in Settings. On macOS, VibeZ downloads the signed ZIP matching the Mac's processor and offers **Restart & update** or **Later** after verification.

## Build from source

### Requirements

- Windows, macOS or Linux
- A current Node.js LTS release
- npm

### Development

```bash
git clone https://github.com/lecomputeur/vibez.git
cd vibez
npm install
npm test
npm start
```

Build the packages configured for the current operating system with:

```bash
npm run build
```

Public release packages are built on native GitHub Actions runners: Ubuntu for Linux, Windows for Windows installers and macOS for DMG/ZIP packages.

## Testing

GitHub CI runs:

- dependency security audit at high severity and above;
- unit tests and JavaScript syntax checks;
- shell syntax validation for the Linux installer;
- x86_64 Linux package builds;
- x86_64 Flatpak build;
- Windows x64 NSIS build;
- macOS Intel and Apple Silicon DMG/ZIP builds;
- packaged-app version smoke checks on all supported native CI runners where practical;
- a full Linux packaged application smoke test under a virtual display with Chromium sandboxing enabled.

## Project structure

VibeZ is built with [Electron](https://www.electronjs.org/). The main application code is in [`main.js`](main.js), screenshot handling is in [`screenshot.js`](screenshot.js), persistent desktop preferences are handled by [`settings-store.js`](settings-store.js), and GitHub Actions workflows live in [`.github/workflows`](.github/workflows).

## Privacy

See the [Privacy Policy](PRIVACY.md) for details about local settings, browser data, screenshots, Mistral Vibe and update checks.

## License

VibeZ is released under the [MIT License](LICENSE).
