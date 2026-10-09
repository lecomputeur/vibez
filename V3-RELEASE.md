# VibeZ 3.0.3 — Screenshots, in-app downloads and macOS layout

Stable promotion of maintainer-approved **3.0.3 test 7**, source `7ab2bbc8e03b07ca0389e2f809a8f1d8805c4217`. The maintainer confirmed that test 7 works and authorized release on all platforms. Functional code is preserved; the test display labels are removed.

## Screenshots

Visible page, Full page and Selection remain compact. Paste directly into Chat and Work drafts without sending a message. In Code, choose **Screenshot as file**, save as PNG and share the file separately. The explanation explicitly says that Chat and Work support direct pasting. A conditional sign-in notice appears when guest sign-in controls are visible; copying and saving remain available without signing in. All notices follow the 34 interface-language bundles.

## Updates

Direct installs check for published releases at startup and offer an in-app download, with progress, cancellation, size and SHA-256 verification. Opening the installer is explicit; VibeZ does not silently install or restart. Store installations keep Microsoft Store delivery. Existing 3.0.2 installations need one manual installation to acquire this new downloader.

## macOS

The toolbar and content are placed below the actual native titlebar area. The approved correction is included in both Intel and Apple Silicon packages, with Developer ID signing, notarization and stapled tickets. Windows and Linux keep their accepted layout and paste implementation.

## Downloads and requirements

Linux x64: DEB, RPM, AppImage, Arch/Pacman and Flatpak. Windows x64: EXE, MSI and Store submission MSIX. macOS Intel and Apple Silicon: DMG and ZIP. All twelve files are required before publication, from one frozen source commit, with a matching SHA256SUMS file.

Native Linux: Ubuntu 24.04 / Mint 22-class systems with glibc 2.39+ and WebKitGTK 4.1. Linux desktop selection requires X11. macOS 14 or later; Screen Recording permission may be required. Windows 10/11 with WebView2. Full-page screenshots cover loaded content, not unloaded history.

## Installation and release checks

Quit VibeZ completely before replacing a previous installation. Test packages also used version 3.0.3; on Mint install the final DEB with `sudo apt install --reinstall ./VibeZ-3.0.3-Linux-x64.deb`. The final app no longer displays a test label. Existing VibeZ 3 profiles are retained; archived Electron and preview profiles stay separate.

The complete all-format workflow requires dependency auditing, frontend/Rust tests, native browser/window/screenshot checks, Linux UI and monitor checks, package integrity and Apple signing/notarization. Automated fixtures are not a claim of testing every current website, machine, permission state or completed installer-driven upgrade.

The MSIX retains LeComputeur.VibeZDesktop, product 9NR7L2G4MS08, version 3.0.3.0. Package creation is not Microsoft Store submission, certification or publication. Historical Electron feeds keep their original Electron packages, not an incompatible Tauri executable.
