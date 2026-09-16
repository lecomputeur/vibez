# Changelog

All notable changes to VibeZ will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.0.0] - 2026-09-16

### Added
- A native VibeZ toolbar around the official Mistral Vibe web app using Electron `WebContentsView`.
- Integrated Back, Forward, Reload, Screenshot and Settings controls without browser-style address chrome.
- A Microsoft Store x64 MSIX build using the reserved `LeComputeur.VibeZDesktop` Partner Center identity.
- Developer ID signing, Apple notarization, stapling and Gatekeeper verification for Intel and Apple Silicon macOS packages.
- Production packages for Linux x86_64 in AppImage, DEB, RPM, Pacman and Flatpak formats.

### Changed
- Promoted the VibeZ 2 shell to version 2.0.0 and restored the stable `com.vibez.app` identity, `vibez` executable, normal profile and `vibez://` protocol.
- Replaced the development-only update placeholder with production GitHub Release update checks and supported installer updates.
- Consolidated verification into one VibeZ CI workflow and removed unused Windows ARM64 and Linux ARM64 package jobs.
- Kept the direct Windows x64 NSIS installer unsigned and made the Microsoft Store the recommended trusted Windows route.

### Security
- Restricted embedded navigation and permissions to trusted Mistral pages while opening external links in the default browser.
- Kept private signing material in GitHub Secrets and verified final macOS signatures and notarization before publication.
- Added SHA-256 checksums for published release assets and explicit verification that the direct Windows installer is unsigned.

## [1.4.1] - 2026-09-09

### Added
- Automatic macOS update-availability checks that notify users about a newer GitHub Release while keeping unsigned installation manual.
- Shared multilingual account-control detection used by both native and injected Screenshot UI paths.
- Regression coverage for centralized account labels, named Screenshot layout constants and the macOS notification-only update flow.

### Changed
- Replaced repeated Screenshot positioning magic numbers in the main process with named layout constants.
- Expanded the injected Screenshot fallback to use the same multilingual Sign in / Sign up detection as the native Screenshot button.
- Automatic update checking is now configurable on macOS; install-on-quit remains disabled there because unsigned in-place installation is intentionally unsupported.
- Expected navigation/render races stay quiet, while unexpected Screenshot UI failures now produce targeted diagnostic warnings.

### Security
- Refreshed the transitive `js-yaml` dependency to 4.3.2 after a newly reported high-severity advisory; the release gate requires `npm audit --audit-level=high` to return clean before publication.

### Kept intentionally
- Electron 43 automatic Ozone selection remains unchanged when Linux display backend is set to Automatic.
- The native Screenshot overlay still hides when VibeZ loses focus so it cannot float over unrelated applications.
- `electron-updater` remains on the valid 6.8.x release line; no downgrade is applied.

## [1.4.0] - 2026-09-08

### Added
- Windows x64 and Windows ARM64 NSIS installers.
- macOS DMG and ZIP packages for Apple Silicon and Intel Macs.
- Native Windows and macOS package verification in GitHub Actions alongside the existing Linux build matrix.
- Cross-platform download and first-launch documentation, including SmartScreen and Gatekeeper guidance for the zero-cost unsigned builds.
- Platform-aware start-at-login implementation for Windows and macOS while preserving Linux XDG autostart.
- macOS Screen Recording permission detection and a direct route to the relevant System Settings page when access is blocked.

### Changed
- VibeZ is now presented as a Windows, macOS and Linux desktop client from one shared Electron codebase.
- Linux-only Wayland/X11 settings are hidden on Windows and macOS and no longer affect those platforms.
- System information and shortcut labels are platform-aware.
- Free unsigned macOS builds use manual GitHub Release updates instead of claiming reliable unsigned in-place installation.
- Release automation builds, verifies, checksums and publishes Linux, Windows and macOS packages together.

### Security
- Windows and macOS packages remain unsigned by design to keep distribution at €0; release documentation explains the resulting OS warnings and SHA-256 verification.
- Existing renderer sandboxing, trusted-origin restrictions and dependency security auditing are preserved on all platforms.

## [1.3.2] - 2026-09-08

### Fixed
- Screenshot now anchors to the left edge of the complete account-action cluster, so separate Sign in / Login and Sign up / Register controls cannot overlap it.
- Native Screenshot overlay is kept above the embedded Mistral web content while VibeZ is focused.
- Screenshot overlay is hidden when VibeZ loses focus, preventing it from floating above other applications.

## [1.3.1] - 2026-09-08

### Added
- Central VibeZ internationalization layer covering all VibeZ-owned menus, dialogs, Settings and screenshot interfaces.
- 34 built-in interface languages with automatic Linux/OS locale detection and English fallback.
- Simplified and Traditional Chinese support.
- Right-to-left layout support for Arabic, Hebrew, Persian and Urdu.
- Regression tests that require every advertised language to contain every VibeZ translation key.

### Changed
- **System** language now follows the Linux/Electron OS locale instead of the language reported by the Mistral web page.
- Manual VibeZ language selection applies to VibeZ-owned UI without forcing the embedded Mistral Vibe website to that language.
- Native Screenshot button localizes its label, adapts its width for longer translations and repositions itself relative to the account action.
- Screenshot selection and error dialogs now use the same central VibeZ language source.

### Fixed
- Fixed the Screenshot button overlapping **Aanmelden / Sign up / Register** on narrower windows.
- Screenshot button now anchors with a fixed gap to the account action and uses the BrowserWindow content bounds for more reliable Linux window-manager positioning.

## [1.3.0] - 2026-09-08

### Added
- Global screenshot shortcut, available outside the VibeZ window.
- Native system tray with Open, Screenshot, Settings, update, About and Quit actions.
- Settings window for screenshot behavior, startup, tray behavior, hardware acceleration, display backend, zoom, language and updates.
- Optional start at login, minimize to tray and close to tray.
- Hardware acceleration modes: Automatic, Enabled and Disabled.
- Display backend selection: Automatic, Wayland and X11.
- Configurable zoom and interface language preferences.
- About window with copyable system information for support and bug reports.
- CLI commands including `vibez --version`, `vibez --screenshot` and `vibez --settings`.
- `vibez://` protocol integration and single-instance handling.
- ARM64 AppImage, DEB, RPM and Pacman release packages.
- x86_64 Flatpak release bundle with Wayland support.
- SHA-256 checksum file for release assets.
- One-line installer support for both x86_64 and ARM64, including checksum verification and uninstall mode.
- Automated dependency security audit in CI and the release pipeline.
- Packaged x86_64 application smoke test with Chromium sandboxing enabled.

### Changed
- Reworked Screenshot access so a native desktop entry point remains available even if the Mistral web interface changes.
- External links now open in the system browser instead of navigating VibeZ away from trusted Mistral pages.
- Restricted web permissions and navigation to trusted Mistral origins.
- Update flow now prompts with Restart & update or Later instead of restarting unexpectedly.
- Updated Electron from 43.4.1 to 43.6.0.
- Updated electron-builder from 24.13.3 to 26.15.3.
- Updated GitHub Actions checkout/setup-node workflows to v5.
- Linux desktop integration now uses an explicit desktop name and application icon.
- Release workflow now refuses to publish when security audit, tests or packaged-app smoke checks fail.

### Security
- Reduced renderer exposure through narrow context-isolated preload bridges.
- Added persistent security auditing with `npm audit --audit-level=high`.
- Dependency upgrade removed the previously reported high/critical npm audit findings.
- Chromium sandbox remains enabled in packaged-app smoke testing.

### Fixed
- Fixed Electron/Chromium sandbox handling in CI smoke tests without disabling the sandbox.
- Fixed Linux icon and desktop-name configuration for electron-builder 26.
- Removed the obsolete VibeZ 1.1.0-only Arch build workflow.

## [1.2.0] - 2026-08-25

### Added
- Browser-language interface text for the Screenshot button, screenshot selection, context menu, and Vibe Code guidance.
- Clear, localized instructions for using a screenshot with a Vibe Code project and test branch.
- VibeZ version in the application title bar.

### Changed
- Replaced the Vibe page title in the title bar with the VibeZ application name and version.
- Localized the right-click menu, including Google and DuckDuckGo search options.

### Fixed
- Restored reliable direct screenshot pasting in Chat and Work.

## [1.1.0] - 2026-08-24

### Added
- Added a native **Screenshot** button to VibeZ.
- Added multi-monitor screenshot selection and capture.
- Screenshots are automatically inserted into the Vibe chat composer after capture.
- Added automatic update support through GitHub Releases.
- Added Linux release packages for AppImage, DEB, RPM, and Arch Linux / Pacman.
- Added a native Arch Linux package for Arch, Manjaro, EndeavourOS, and other Arch-based distributions.
- Added update metadata generation through `latest-linux.yml` for `electron-updater`.

### Changed
- Integrated the Screenshot button into the existing Vibe interface.
- Improved Screenshot button placement for logged-in and logged-out views.
- Kept the Screenshot button hidden on the authentication form.
- Stabilized Screenshot button positioning so it no longer jumps when Vibe action buttons appear or disappear.

### Fixed
- Fixed Screenshot button overlap with Vibe's star and share controls.

[Unreleased]: https://github.com/lecomputeur/vibez/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/lecomputeur/vibez/compare/v1.4.1...v2.0.0
[1.4.1]: https://github.com/lecomputeur/vibez/releases/tag/v1.4.1
[1.4.0]: https://github.com/lecomputeur/vibez/releases/tag/v1.4.0
[1.3.2]: https://github.com/lecomputeur/vibez/releases/tag/v1.3.2
[1.3.1]: https://github.com/lecomputeur/vibez/releases/tag/v1.3.1
[1.3.0]: https://github.com/lecomputeur/vibez/releases/tag/v1.3.0
[1.2.0]: https://github.com/lecomputeur/vibez/releases/tag/v1.2.0
[1.1.0]: https://github.com/lecomputeur/vibez/releases/tag/v1.1.0
