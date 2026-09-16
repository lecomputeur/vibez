# VibeZ 2.0 Production Verification

This document describes the final verification path for the VibeZ 2.0 desktop shell.

## Release safety

- Pull requests into `v2.0-dev` do not publish GitHub Releases.
- VibeZ 2.0 uses the production app identity `com.vibez.app`, executable `vibez`, protocol `vibez://` and normal VibeZ profile.
- Publishing remains a separate, explicit release action after cross-platform verification.

## What changed

VibeZ 2.0 introduces a local VibeZ toolbar and places the official Mistral Vibe website in an Electron `WebContentsView` below it.

The toolbar contains:

- Back
- Forward
- Reload
- Screenshot
- Settings

The browser-style service/hostname pill has intentionally been removed. The shell should feel like a desktop application, not a browser chrome around a website.

The former floating always-on-top Screenshot window is not used by `main-v2.js`.

## Cross-platform CI

The `VibeZ 2.0 CI` workflow validates the same shell on:

- Linux x64
- Windows x64
- macOS Intel and Apple Silicon

The workflow does not publish a release. It only uploads verification artifacts.

Windows direct-download artifacts are **UNSIGNED** and can trigger SmartScreen warnings. Production macOS packages are Developer ID signed and Apple-notarized by the release workflow.

## Distribution direction for VibeZ 2.0 stable

- macOS production packages are Developer ID signed, Apple-notarized, stapled and verified in the release workflow.
- The Windows x64 installer downloaded directly from GitHub is unsigned and must be identified as such. Every public release includes SHA-256 checksums.
- A Microsoft Store listing is being prepared as the recommended Windows installation route because Store-distributed apps are validated and signed by Microsoft.
- The SignPath Foundation application was declined due to VibeZ's current level of public adoption. Its obsolete manual workflow has been removed.
- Signing credentials and private keys stay outside the repository and are supplied only through protected CI secrets/signing services.
- See `V2-SIGNING.md` and `MICROSOFT-STORE.md` for the production gates and prepared Store submission.

## Local development

```bash
git checkout v2.0-dev
npm install
npm start
```

## Linux verification artifact

The Linux AppImage is the easiest way to verify the shell without installing a system package.

```bash
chmod +x VibeZ-2.0.0-Linux-x86_64.AppImage
./VibeZ-2.0.0-Linux-x86_64.AppImage
```
