# VibeZ 3.1.0 — VibeZ V4 Beta is out

VibeZ 3.1.0 is a small update to the stable VibeZ 3. Its only change is a pointer to the next version: **VibeZ V4 is now available as an open beta.**

## Changes

- **One-time notice.** On the first visible start after updating, VibeZ 3 shows a short window: VibeZ V4 Beta is out, VibeZ 3 remains the stable version, and V4 installs separately with its own settings. The notice appears once per profile. A start hidden in the tray (start at login) postpones it to the next visible start.
- **Links in the tray menu and in the notice:** Try VibeZ V4 Beta ([v4.0.0-beta.3](https://github.com/lecomputeur/vibez/releases/tag/v4.0.0-beta.3)), [Discussions](https://github.com/lecomputeur/vibez/discussions), Report a problem ([new issue](https://github.com/lecomputeur/vibez/issues/new/choose)) and [VibeZ on GitHub](https://github.com/lecomputeur/vibez). The links open in your default browser. Only these four fixed addresses can be opened.
- The notice and the menu links are translated into all 34 interface languages.
- Windows/macOS/Linux receive version 3.1.0 and window title VibeZ V3.1.0.

Nothing else changed: app identity, profile, settings, sign-in, screenshots, link routing and the update check are the same as in 3.0.9. VibeZ 3 does not install or update VibeZ V4; V4 releases are prereleases and are never offered by the VibeZ 3 updater.

## VibeZ V4 Beta

VibeZ V4 is a separate app next to VibeZ 3, with its own identity, profile and update channel. Installing it does not replace or change VibeZ 3. See the [V4 Beta release](https://github.com/lecomputeur/vibez/releases/tag/v4.0.0-beta.3) for downloads, changes and known limits. Feedback is welcome in [Discussions](https://github.com/lecomputeur/vibez/discussions) or as an [issue](https://github.com/lecomputeur/vibez/issues/new/choose).

## Packaging and delivery

Packages: Linux x64 AppImage, DEB, RPM, Arch/Pacman and Flatpak; Windows x64 EXE, MSI and Store MSIX 3.1.0.0; signed/notarized macOS x64 and arm64 DMG/ZIP. All twelve packages are built from the same frozen source commit and passed the same package, native smoke and advisory checks as 3.0.9. Requirements are unchanged from 3.0.9.

VibeZ 3.0.9 installations with automatic update checks enabled are offered 3.1.0 about six seconds after start; otherwise use **Check for updates** in the tray menu. Microsoft Store installations are updated by the Store, separately from this release.

## Rollback

Keep v3.0.9 assets, checksums and tag unchanged. Reinstall the matching 3.0.9 package if required; the profile is not migrated. 3.0.9 ignores the small notice marker file that 3.1.0 writes.
