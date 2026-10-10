# VibeZ 3

Rust/Tauri 3.0.4 candidate source for Linux AppImage/DEB/RPM/Arch/Flatpak, Windows EXE/MSI/MSIX and macOS Intel/Apple Silicon app/DMG/ZIP.

The `release/v3.0.4-validation` branch runs `.github/workflows/v3.0.4-validation.yml` against one immutable source commit. It requires all platform tests, dependency auditing, all twelve packages and macOS signing/notarization. Successful packages are uploaded as CI artifacts; this workflow does not publish a GitHub release or submit to Microsoft Store. The current public release remains 3.0.3.

App identity: `nl.lecomputeur.vibez3`. Existing Electron and preview profiles are not silently copied or deleted. See ../V3-RELEASE.md for compatibility and release gates.

Build: `npm ci`, `npm test`, `npm run build -- -- --locked`. Resolved lockfiles are committed before native builds.
