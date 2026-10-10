# VibeZ 3

Rust/Tauri 3.0.4 source for Linux AppImage/DEB/RPM/Arch/Flatpak, Windows EXE/MSI/MSIX and macOS Intel/Apple Silicon app/DMG/ZIP.

The `release/v3.0.4-validation` branch runs `.github/workflows/v3.0.4-validation.yml` against one immutable source commit. It requires all platform tests, dependency auditing, all twelve packages and macOS signing/notarization. The verified packages are published in the [VibeZ 3.0.4 release](https://github.com/lecomputeur/vibez/releases/tag/v3.0.4). Publication checks the exact tested source and package checksums. Microsoft Store submission and certification remain separate.

App identity: `nl.lecomputeur.vibez3`. Existing Electron and preview profiles are not silently copied or deleted. See ../V3-RELEASE.md for compatibility and release gates.

Build: `npm ci`, `npm test`, `npm run build -- -- --locked`. Resolved lockfiles are committed before native builds.
