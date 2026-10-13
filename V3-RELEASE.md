# VibeZ 3.0.6 — Linux scrolling improvements and consistent window titles

Linux now uses immediate wheel scrolling to reduce native animation overhead in long conversations. The adjustment applies to AppImage, DEB, RPM, Arch/Pacman and Flatpak. Page-controlled animations can still cause CPU activity.

Every platform shows **VibeZ V3.0.6** in the main window title. Settings, update, screenshot and sign-in windows also retain the current version. Windows and macOS scrolling behavior is unchanged.

All twelve download formats passed the [same-source validation build](https://github.com/lecomputeur/vibez/actions/runs/38454538226), including native tests, dependency auditing, packaging checks and macOS signing, notarization and stapling. The frozen application source is `92aa72a9224f085cc08288e3722119e6b4b11c00`. Downloads include SHA-256 checksums. Existing VibeZ 3 settings and profiles are retained. Microsoft Store installations use Store delivery; the 3.0.6.0 MSIX is prepared for separate Partner Center submission and certification.

Verified update installers continue to close VibeZ automatically after handoff. Native Linux packages require glibc 2.39+ and WebKitGTK 4.1; Linux desktop selection requires X11. macOS requires version 14 or later, and Windows requires WebView2.

The scroll improvement was measured with large synthetic offline chats. It is not a claim that every live Mistral conversation or Linux graphics configuration has been tested.
