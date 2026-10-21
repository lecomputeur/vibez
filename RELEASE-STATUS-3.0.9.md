# VibeZ 3.0.9 — release status, 21 October 2026

**Stable publication is blocked.** GitHub Latest and the live website remain on 3.0.8. No v3.0.9 stable release, Store submission or Flathub listing update was performed.

Frozen build source: `e8926529989a032b8df4c19a75fd2d1fe4fff37d`. [Validation run](https://github.com/lecomputeur/vibez/actions/runs/39630746331); [release PR](https://github.com/lecomputeur/vibez/pull/50).

## Verified build outputs

- Linux x64: AppImage, DEB, RPM, Arch/Pacman and Flatpak.
- Windows x64: Setup EXE, MSI and Store-upload MSIX version **3.0.9.0**.
- macOS arm64: Developer ID signed, Apple-notarized and stapled DMG/ZIP.
- Intel macOS: compilation and native tests passed; application signing/notarization passed, but independent final ticket validation failed. Its DMG/ZIP are not released or substituted with older files.

Ten of the twelve required release files are available as build artifacts. Source versions, production app identity, dependency audit, checksum-pinned upstream Wry comparison, Linux frame/auth/chart regressions, rich-chat lifecycle/streaming/Find/resize/wheel/fullscreen, screenshot/paste/two monitors, updates and installed-package checks passed. Windows and both Mac architectures passed native integration tests. No complete successful 3.0.9 release proof exists and none was fabricated.

## Release blocker

Intel Mac ticket stapling/validation repeatedly failed with Apple CloudKit `NSURLErrorDomain -1005` (network connection lost), exit **68**. This happened across normal attempts and a fresh-runner retry, with five bounded network retries each time. The final attempt accepted app notarization and created/notarized the DMG, but could not complete the explicit independent ticket validation. Do not waive the check or call the Intel package validated.

All other platform jobs are green. The combined twelve-format gate remains skipped because Intel failed. The existing failed-run artifacts remain on GitHub; local copies/logs are retained. Automatic approval review refused deletion of an old failed validation artifact, so deletion was abandoned and the rerun preserved existing evidence.

## Next release action

After Apple connectivity recovers, rerun only the failed Intel job (including its dependent final gate) in the same frozen-source run. Require native tests, signing, Accepted notarization, stapling and explicit ticket validation to pass. Then record the genuine versioned release proof, download/reverify all twelve packages and source archive, finalize availability text, and publish/merge the prepared release work. Preserve v3.0.8 and the separate test.3 app.

## Known existing issue

The preview fix is confirmed by the openSUSE reporter; Cloudflare/Mistral loading is confirmed in the test Flatpak on openSUSE Leap. The original heavy conversation still consumes 100% CPU at idle (#42/#49). This release does not claim to fix that remaining workload.

## Store upload

The Windows upload file is `VibeZ-3.0.9-Windows-x64-Store.msix`, version **3.0.9.0**, identity `LeComputeur.VibeZDesktop`, publisher `CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95`. SHA-256: `1d6f7d3c3f6ff4fd22e1f28955a0127aa96272ccc69e926bb9fdefcc20a88cd2`.

[Partner Center steps and English/Dutch What's New](MICROSOFT-STORE-3.0.9.md). Use only the existing VibeZ Desktop product/account; inspect current package versions and submissions first. Package verification is not Windows App Certification Kit/Store certification. No Partner Center access or submission has been performed.
