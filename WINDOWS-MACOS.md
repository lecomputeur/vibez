# VibeZ 3.0.9 on Windows and macOS

The [verified 3.0.9 build](https://github.com/lecomputeur/vibez/actions/runs/39643498884) passed all nine required platform/security jobs. All twelve packages use frozen source `64dbf09e8a24b1d1859b3571cd3b83b87a39f14c`; the [release proof](tools/release-v3/release-proof-3.0.9.json) records the build. The packages are validated for GitHub publication. The [3.0.9 release asset list](https://github.com/lecomputeur/vibez/releases/tag/v3.0.9) records actual download availability; compare downloads with its `SHA256SUMS` and `source-commit.txt`.

## Windows x64

Use `VibeZ-3.0.9-Windows-x64-Setup.exe` or `VibeZ-3.0.9-Windows-x64.msi`. Direct installers are unsigned and may trigger SmartScreen or managed-device restrictions. Windows requires WebView2. The Store package targets Windows 10 build 17763 or newer.

`VibeZ-3.0.9-Windows-x64-Store.msix`, version 3.0.9.0, is an unsigned Partner Center upload package for the existing VibeZ Desktop product. Use EXE/MSI for direct installation. The [Store listing](https://apps.microsoft.com/detail/9NR7L2G4MS08) has its own certification/delivery schedule; do not assume its current version is 3.0.9. See [upload steps and What's New](MICROSOFT-STORE-3.0.9.md). No Store submission was performed as part of this work.

## macOS 14 or newer

Apple Silicon: `VibeZ-3.0.9-macOS-arm64.dmg` or `.zip`. Intel: `VibeZ-3.0.9-macOS-x64.dmg` or `.zip`. Both architectures passed Developer ID signing, Apple notarization and stapled-ticket validation in the exact-source build. Both native architectures, Info.plist requirements and Mach-O deployment targets were verified with a macOS 14 minimum. Open the matching DMG and copy VibeZ 3 to Applications.

## Updates and profiles

Direct VibeZ 3 installations use the app's published-release update flow with SHA-256 checks and user-confirmed installation. Store installations use Store delivery. Ordinary 3.x profiles/settings are retained; isolated Canvas Test, older Electron and preview profiles remain separate. No automatic profile migration or deletion is included.

This release adds TLS certificate-trust dependency updates on all platforms. The frame-aware Canvas/verification routing fix applies to Linux. The original heavy-conversation high-CPU report remains open in #49 and is not claimed fixed. Preserve the v3.0.8 assets and tag for rollback; close VibeZ, back up the ordinary profile and reinstall the matching 3.0.8 installer if needed. Do not delete or migrate profiles.

Installation guides: [Windows](https://lecomputeur.github.io/vibez/windows.html) · [macOS](https://lecomputeur.github.io/vibez/macos.html). [Code signing policy](https://lecomputeur.github.io/vibez/code-signing-policy.html).
