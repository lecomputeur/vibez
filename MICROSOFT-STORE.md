# Microsoft Store submission plan

This file contains the prepared Partner Center information for publishing VibeZ 2 on the Microsoft Store. Do not submit a beta artifact as the stable Store release.

## Distribution decision

- The Microsoft Store is the recommended Windows installation route.
- The Store product is **VibeZ Desktop** and uses a separate x64 MSIX package.
- Microsoft validates and re-signs the Store MSIX after certification.
- The direct GitHub Windows x64 NSIS installer remains available and is explicitly labeled unsigned.
- An unsigned EXE/MSI is not submitted to the Store because that route requires a CA-trusted Authenticode signature.
- Microsoft Defender false-positive submission is only used when Defender actually classifies a VibeZ file as malware or potentially unwanted software. It is not used as a SmartScreen reputation shortcut.

## Reserved Partner Center identity

| Field | Value |
| --- | --- |
| Product name | VibeZ Desktop |
| Package identity name | `LeComputeur.VibeZDesktop` |
| Publisher | `CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95` |
| Publisher display name | Le Computeur |
| Package family name | `LeComputeur.VibeZDesktop_dpqfg82bz4ywg` |
| Store ID | `9NR7L2G4MS08` |
| Store URL | https://apps.microsoft.com/detail/9NR7L2G4MS08 |

These are public package identifiers, not secrets. The manifest values must match Partner Center exactly.

## Prepared listing

| Field | Value |
| --- | --- |
| App type | MSIX or PWA app |
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

## MSIX build and validation

The Store build is produced with:

```powershell
npm run build:store:msix
```

The build script:

1. Creates the Windows x64 unpacked Electron application.
2. Generates Store logo assets from the VibeZ icon.
3. Writes the MSIX manifest with the reserved Partner Center identity.
4. Packages the application with the Windows SDK `makeappx.exe`.
5. Unpacks the result and verifies its identity, publisher, version and executable.

CI additionally copies the unsigned Store artifact, signs that disposable copy with an ephemeral test certificate, installs it, verifies the package family and registered executable, uninstalls it and deletes the test certificate. The ephemeral test-signed copy is never uploaded or published.

The artifact intended for Partner Center remains unsigned so Microsoft can re-sign it during certification.

## Required manual Partner Center steps

1. Keep the reserved **VibeZ Desktop** product in draft until the final VibeZ 2.0.0 build is ready.
2. Start the submission and upload the final x64 MSIX artifact.
3. Complete the Store listing using the prepared text above.
4. Complete the age rating and declarations accurately.
5. Submit the app for Microsoft certification.
6. After approval, add the official Store URL to `README.md`, `docs/windows.html` and the GitHub release notes.

## Pre-submission release gate

- The final VibeZ 2.0.0 Store MSIX was produced by the official GitHub Actions workflow.
- The package identity, publisher, package family, architecture and four-part version match Partner Center.
- CI successfully built, unpacked, locally signed, installed, registered and uninstalled a disposable copy.
- The normal unit, security and Windows packaged-app smoke tests pass.
- The final Store MSIX does not contain beta product names or test text.
- Upgrade from the previous Store submission is tested when an earlier Store version exists.
- The privacy, support and website URLs are publicly reachable.
- Screenshots used in the Store listing show the final VibeZ 2 interface.
- The Store listing does not claim affiliation with Mistral AI.
