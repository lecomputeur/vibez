# VibeZ 3.2.0 — Mistral Vibe has its own desktop app

On 17 November 2026 Mistral released **[Vibe Desktop](https://mistral.ai/products/vibe/)**, the official app for macOS and Windows. VibeZ was a stand-in for that app and is now winding down. VibeZ 3.2.0 tells you so inside the app.

## Changes

- **One-time farewell notice.** On the first visible start after updating, VibeZ 3 shows a short window: Mistral Vibe has its own desktop app, VibeZ is winding down, and a button to get Vibe Desktop. On Windows and macOS it says that VibeZ receives no further updates and recommends the official app. On Linux it says that VibeZ for Linux stays supported until the official Linux app is available. The notice appears once per profile, also for profiles that saw the 3.1.0 V4 Beta notice. A start hidden in the tray (start at login) postpones it to the next visible start.
- **Tray menu:** "Try VibeZ V4 Beta" is replaced by **Get Vibe Desktop**, which opens [mistral.ai/products/vibe](https://mistral.ai/products/vibe/) in your default browser. Discussions, Report a problem and VibeZ on GitHub stay. Only these four fixed addresses can be opened.
- The notice and the menu links are translated into all 34 interface languages.
- Windows/macOS/Linux receive version 3.2.0 and window title VibeZ V3.2.0.

Nothing else changed: app identity, profile, settings, sign-in, screenshots, link routing and the update check are the same as in 3.1.0.

## What happens now

- **Windows and macOS:** 3.2.0 is the last VibeZ 3 version. Please switch to the official Vibe Desktop.
- **Linux:** VibeZ 3 stays supported with fixes until the official Linux app is available.
- The source stays on GitHub under the MIT license.

Thank you to everyone who used, tested and improved VibeZ, with a special thank you to [ActiveUser435](https://github.com/ActiveUser435) and [HumanistAtypik](https://github.com/HumanistAtypik).

## Packaging and delivery

Packages: Linux x64 AppImage, DEB, RPM, Arch/Pacman and Flatpak; Windows x64 EXE, MSI and Store MSIX 3.2.0.0; signed/notarized macOS x64 and arm64 DMG/ZIP. All twelve packages are built from the same frozen source commit and passed the same package, native smoke and advisory checks as 3.1.0. Requirements are unchanged.

VibeZ 3.1.0 installations with automatic update checks enabled are offered 3.2.0 about six seconds after start; otherwise use **Check for updates** in the tray menu. Microsoft Store installations are updated by the Store, separately from this release.

## Rollback

Keep v3.1.0 assets, checksums and tag unchanged. Reinstall the matching 3.1.0 package if required; the profile is not migrated. 3.1.0 ignores the small notice marker file that 3.2.0 writes.
