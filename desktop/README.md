# VibeZ 3

Rust/Tauri 3.0.2 source for Linux AppImage/DEB/RPM/Arch/Flatpak, Windows EXE/MSI/MSIX and macOS Intel/Apple Silicon app/DMG/ZIP.

App identity: `nl.lecomputeur.vibez3`. Existing Electron and earlier Tauri profiles are not silently copied or deleted. See ../V3-RELEASE.md for compatibility and release gates.

Build: `npm ci`, `npm test`, `npm run build -- -- --locked`. Resolved lockfiles are committed before native builds.
