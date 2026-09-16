# VibeZ 2.0 Test Shell

This branch is an isolated development line for the VibeZ 2.0 desktop shell.

## Safety

- Stable `main` remains on the VibeZ 1.x line.
- This branch does not publish GitHub Releases.
- VibeZ 2 Beta uses a separate app identity (`com.vibez.app.beta`), product name, executable name and user-data profile.
- The beta does not claim the stable `vibez://` protocol or alter the stable app's start-at-login registration.
- Test packages can run alongside stable VibeZ without replacing the stable app.

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

## Cross-platform beta CI

The `VibeZ 2.0 Beta Test` workflow validates the same shell on:

- Linux x64
- Windows x64
- macOS Intel and Apple Silicon

The workflow does not publish a release. It only uploads test artifacts.

Windows beta artifacts are **UNSIGNED** and can trigger SmartScreen warnings. Stable macOS packages are Developer ID signed and Apple-notarized; isolated beta artifacts may still be unsigned.

## Distribution direction for VibeZ 2.0 stable

- macOS production packages are Developer ID signed, Apple-notarized, stapled and verified in the release workflow.
- The Windows x64 installer downloaded directly from GitHub is unsigned and must be identified as such. Every public release includes SHA-256 checksums.
- A Microsoft Store listing is being prepared as the recommended Windows installation route because Store-distributed apps are validated and signed by Microsoft.
- The SignPath Foundation application was declined due to VibeZ's current level of public adoption. The manual SignPath workflow remains available for a later reapplication.
- Signing credentials and private keys stay outside the repository and are supplied only through protected CI secrets/signing services.
- See `V2-SIGNING.md` and `MICROSOFT-STORE.md` for the production gates and prepared Store submission.

## Local development

```bash
git checkout v2.0-dev
npm install
npm start
```

## Linux beta artifact

The Linux AppImage is the easiest way to test the shell without installing anything over the stable package.

```bash
chmod +x VibeZ-2-Beta-2.0.0-beta.1-Linux-x64.AppImage
./VibeZ-2-Beta-2.0.0-beta.1-Linux-x64.AppImage
```

Do not replace the stable package with beta installers during the shell evaluation phase.
