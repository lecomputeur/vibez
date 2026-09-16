# Microsoft Store submission plan

This file contains the prepared Partner Center information for publishing VibeZ 2 on the Microsoft Store. Do not submit a beta artifact as the stable Store release.

## Distribution decision

- The Microsoft Store is the recommended Windows installation route.
- The direct GitHub Windows x64 installer remains available and is explicitly labeled unsigned.
- Store-distributed apps are validated and signed by Microsoft.
- Microsoft Defender false-positive submission is only used when Defender actually classifies a VibeZ file as malware or potentially unwanted software. It is not used as a SmartScreen reputation shortcut.

## Prepared listing

| Field | Value |
| --- | --- |
| Product name | VibeZ |
| App type | Desktop app / Win32 |
| Architecture | x64 |
| Category | Developer tools |
| Price | Free |
| Website | https://lecomputeur.github.io/vibez/ |
| Support | https://github.com/lecomputeur/vibez/discussions/categories/q-a |
| Privacy policy | https://github.com/lecomputeur/vibez/blob/main/PRIVACY.md |
| Source code | https://github.com/lecomputeur/vibez |
| License | MIT |

### Short description

A free cross-platform desktop client for Mistral Vibe with screenshot tools, desktop integration and 34 interface languages.

### Full description

VibeZ opens the official Mistral Vibe web app in a dedicated desktop window and adds native desktop integration.

Features include a global screenshot shortcut, multi-monitor screenshot selection, system-tray access, start-at-login support, configurable update checks, hardware-acceleration controls and a VibeZ interface that follows the operating-system language. VibeZ includes 34 interface languages and right-to-left support.

VibeZ is free and open source. It is an independent desktop client and is not affiliated with or supported by Mistral AI. A Mistral account may be required to use the embedded service.

### Search terms

Mistral Vibe, Mistral AI, developer tools, AI assistant, desktop client, screenshot

## Installer data for VibeZ 2.0.0

Complete these values only after the final VibeZ 2.0.0 GitHub release exists:

- Installer URL: `https://github.com/lecomputeur/vibez/releases/download/v2.0.0/VibeZ-2.0.0-Windows-x64.exe`
- Installer type: EXE
- Architecture: x64
- Silent install parameter: `/S`
- Scope: per-user
- Version: `2.0.0`
- SHA-256: copy the exact value from the release's `SHA256SUMS`
- Upgrade behavior: installs over the previous per-user VibeZ installation
- Offline installation: supported after download

The exact installer filename must be verified against the final release before submission. Never submit an Actions artifact URL because those artifacts expire and may require authentication.

## Required manual Partner Center steps

These steps require the repository owner's Microsoft account and identity verification:

1. Enroll as an individual Microsoft Store developer.
2. Reserve the product name **VibeZ**.
3. Create the Store listing using the prepared text above.
4. Add the final public VibeZ 2.0.0 installer URL and its SHA-256.
5. Complete the age rating and declarations accurately.
6. Submit the app for Microsoft certification.
7. After approval, add the official Store URL to `README.md`, `docs/windows.html` and the GitHub release notes.

## Pre-submission release gate

- The final VibeZ 2.0.0 Windows x64 installer exists on a public GitHub release.
- CI tests and the Windows packaged-app smoke test pass.
- The filename, version and SHA-256 match the Store submission exactly.
- Silent installation with `/S` is tested on a clean Windows environment.
- Upgrade from VibeZ 1.4.1 is tested.
- Uninstall is tested.
- The privacy, support and website URLs are publicly reachable.
- Screenshots used in the Store listing show the final VibeZ 2 interface.
- The Store listing does not claim affiliation with Mistral AI.
