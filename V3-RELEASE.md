# VibeZ 3.0.6 — Linux scrolling improvements and consistent window titles

Linux now uses immediate wheel scrolling to reduce native animation overhead in long conversations. The adjustment applies to AppImage, DEB, RPM, Arch/Pacman and Flatpak. Page-controlled animations can still cause CPU activity.

Every platform shows **VibeZ V3.0.6** in the main window title. Settings, update, screenshot and sign-in windows also retain the current version. Windows and macOS scrolling behavior is unchanged.

Publication is pending the complete all-platform build. All twelve download formats must pass their tests and packaging checks, including macOS signing, notarization and stapling. Downloads include SHA-256 checksums. Existing VibeZ 3 settings and profiles are retained. Microsoft Store installations use Store delivery; the 3.0.6.0 MSIX is prepared for separate Partner Center submission and certification.

Verified update installers continue to close VibeZ automatically after handoff. Native Linux packages require glibc 2.39+ and WebKitGTK 4.1; Linux desktop selection requires X11. macOS requires version 14 or later, and Windows requires WebView2.

The scroll improvement was measured with large synthetic offline chats. It is not a claim that every live Mistral conversation or Linux graphics configuration has been tested.
