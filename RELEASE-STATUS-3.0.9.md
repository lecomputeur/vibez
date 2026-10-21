# VibeZ 3.0.9 — release status, 21 October 2026

**Published on GitHub as Latest.** [VibeZ 3.0.9](https://github.com/lecomputeur/vibez/releases/tag/v3.0.9) was published at `2026-10-21T17:58:11Z` on 21 October 2026. All twelve packages passed the exact-source nine-job validation and the uploaded files were downloaded again and matched byte-for-byte. The three legacy update feeds also matched the verified originals adapted for this release. No Microsoft Store submission or Flathub listing update was performed. README and website/installation updates are included in [release PR #50](https://github.com/lecomputeur/vibez/pull/50).

Frozen build source: `64dbf09e8a24b1d1859b3571cd3b83b87a39f14c`. [Release proof](tools/release-v3/release-proof-3.0.9.json); [release PR](https://github.com/lecomputeur/vibez/pull/50).

## Verified build outputs

- Linux x64: AppImage, DEB, RPM, Arch/Pacman and Flatpak.
- Windows x64: Setup EXE, MSI and Store-upload MSIX version **3.0.9.0**.
- macOS arm64 and Intel x64: Developer ID signed, Apple-notarized and stapled DMG/ZIP, with explicit ticket validation passing on both architectures. Both jobs verified their native architecture and the macOS 14 minimum in Info.plist and Mach-O.

All twelve required release files passed the combined package/checksum gate. Source versions, production app identity, dependency audit, checksum-pinned upstream Wry comparison, Linux frame/auth/chart regressions, rich-chat lifecycle/streaming/Find/resize/wheel/fullscreen, screenshot/paste/two monitors, updates and installed-package checks passed. Windows and both Mac architectures passed native integration tests. The genuine versioned release proof records the source and successful run; no proof was fabricated.

The previous Intel Apple-ticket validation failure was retried without waiving signing, notarization, stapling or explicit ticket validation. The complete rebuild uses a native Intel macOS 26 runner for Intel outputs. Runtime, dependency locks and app build configuration remain identical to the earlier e892 source. CI/proof changes add architecture/macOS-minimum checks and exclude non-release recovery artifacts from collection. The final successful platform jobs and combined gate supersede the earlier failed attempts, whose logs/artifacts remain historical evidence.

## Publication and rollback

GitHub release `419877438` contains the verified twelve-package build artifact, its source label and checksums, plus three compatibility feeds. The public Latest release and `v3.0.9` tag were checked against frozen source `64dbf09e8a24b1d1859b3571cd3b83b87a39f14c`; all 17 uploaded files matched the verified package/feed set. Preserve the unchanged v3.0.8 release assets, checksums and tag as rollback. For test.2 or test.3, first close and uninstall the test application, then install the regular 3.0.9 package; see the [installation steps](https://lecomputeur.github.io/vibez/linux.html#test-build-upgrade). Keep saved data from ordinary test.2, which can otherwise be treated as newer by the installer. The separate Canvas Test app is no longer needed and can be removed; keeping its test data is optional.

## Known existing issue

The openSUSE Tumbleweed reporter confirmed fresh Canvas/chart previews without blank external tabs. The openSUSE Leap 16/GNOME reporter confirmed Cloudflare verification and Mistral loading in the test.3 Flatpak; that reporter did not test RPM. The original heavy conversation still consumes 100% CPU at idle and has typing/scrolling stutter (#42/#49). This release does not claim to fix that remaining workload. The routing hooks apply only to Linux; TLS trust dependency updates apply to all platforms.

## Store upload

The Windows upload file is `VibeZ-3.0.9-Windows-x64-Store.msix`, version **3.0.9.0**, identity `LeComputeur.VibeZDesktop`, publisher `CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95`. SHA-256: `7e0a6808f3e83030f47448045497285938cf6bdea82553e1a66f8db9f458a9b6`.

[Partner Center steps and English/Dutch What's New](MICROSOFT-STORE-3.0.9.md). Use only the existing VibeZ Desktop product/account; inspect current package versions and submissions first. Package verification is separate from Windows App Certification Kit/Store certification. No Partner Center access, submission or Store publication has been performed.
