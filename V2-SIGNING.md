# VibeZ 2.0 Signing Plan

This document describes the production signing path for VibeZ 2.0. Stable VibeZ 1.4.1 remains unchanged while the signing pipeline is prepared and tested.

## Goal

Production VibeZ 2.0 releases should ship as:

- **Windows x64:** unsigned NSIS installer for direct GitHub distribution, plus a separate Microsoft Store MSIX as the recommended trusted route.
- **macOS Intel and Apple Silicon:** Developer ID signed and Apple-notarized DMG/ZIP packages.
- **Linux x64:** AppImage, DEB, RPM, Pacman and Flatpak packages with SHA-256 checksums.

Windows builds must be presented as unsigned unless Authenticode verification succeeds in CI. macOS production artifacts must remain Developer ID signed and Apple-notarized.

## Public package policy

VibeZ 2.0 deliberately keeps broad x86_64 Linux packaging as an ode to the Linux community while avoiding rarely used ARM64 desktop packages:

- Windows x64 direct download: NSIS `.exe`.
- Windows x64 Microsoft Store: MSIX using the reserved `LeComputeur.VibeZDesktop` identity.
- macOS Apple Silicon: notarized `.dmg` plus ZIP for update compatibility.
- macOS Intel: notarized `.dmg` plus ZIP for update compatibility.
- Linux x64: AppImage, DEB, RPM, Pacman and Flatpak.

Windows ARM64 and Linux ARM64 are not part of the VibeZ 2.0 public release set. They can be reconsidered later if actual user demand justifies them.

## Windows — current distribution decision

The SignPath Foundation application was declined on 16 September 2026 because VibeZ does not yet have enough external adoption signals, such as stars, forks, contributors and independent references. SignPath explicitly stated that this was not a judgment on the quality or potential of VibeZ.

Until VibeZ qualifies for sponsored signing:

1. The Windows x64 installer downloaded directly from GitHub is published **unsigned**.
2. Every GitHub release clearly displays the unsigned status and includes `SHA256SUMS`.
3. The release workflow verifies that the direct Windows installer is unsigned, preventing it from being presented as signed by mistake.
4. A separate Microsoft Store MSIX is built with the reserved Store identity and validated in CI. Microsoft re-signs the MSIX after certification; an unsigned EXE/MSI is not submitted to the Store.
5. The manual SignPath test workflow is retained but is not part of the production release gate.
6. VibeZ can reapply to the SignPath Foundation after it gains broader public adoption.

The Microsoft Security Intelligence submission portal may be used to resolve an actual Defender false positive. It is not a manual SmartScreen reputation or allow-list mechanism for consumer devices.

See `MICROSOFT-STORE.md` for the Partner Center submission data and release procedure.

## macOS — Apple Developer ID + notarization

Required external setup:

1. Join the Apple Developer Program.
2. Create a **Developer ID Application** certificate.
3. Export the certificate/private key from Keychain as a password-protected `.p12`.
4. Create an App Store Connect API key for notarization and download the `.p8` file.
5. Record:
   - Apple Team ID
   - App Store Connect Key ID
   - App Store Connect Issuer ID

The following GitHub secrets are configured and used:

- `MAC_CERTIFICATE_P12_BASE64` — base64 of the exported `.p12`
- `MAC_CERTIFICATE_PASSWORD` — password protecting the `.p12`
- `APPLE_API_KEY_P8_BASE64` — base64 of the App Store Connect `.p8`
- `APPLE_API_KEY_ID`
- `APPLE_API_ISSUER`
- `APPLE_TEAM_ID`

CI will decode both files into the runner temporary directory. `CSC_LINK` will point to the decoded `.p12` and `APPLE_API_KEY` will point to the decoded `.p8`.

VibeZ 2.0 already contains:

- Hardened Runtime configuration.
- `build/entitlements.mac.plist`.
- `build/entitlements.mac.inherit.plist`.

The signed macOS release job must:

1. Build on a GitHub-hosted macOS runner.
2. Import/use the Developer ID Application certificate through electron-builder.
3. Notarize with Apple's notary service.
4. Verify `codesign`.
5. Verify Gatekeeper acceptance with `spctl` where applicable.
6. Verify notarization/stapling for the distributed artifact.
7. Publish only after all checks pass.

## Verified macOS release pipeline

The macOS signing and notarization path was verified end to end on 15 September 2026:

- Intel app: Developer ID signed, accepted by Apple, stapled and Gatekeeper verified.
- Intel DMG: accepted by Apple, stapled and validated.
- Apple Silicon app: Developer ID signed, accepted by Apple, stapled and Gatekeeper verified.
- Apple Silicon DMG: accepted by Apple, stapled and validated.
- Final ZIP and DMG artifacts were produced successfully for both architectures.

The permanent implementation is split between:

- `.github/workflows/release.yml` — calls the signed macOS builds and publishes only final `release-*` artifacts.
- `.github/workflows/macos-signed-release.yml` — reusable Intel/Apple Silicon build, signing, notarization, stapling and validation workflow.

For resilience, the workflow stores the exact signed app, the pre-notarization DMG and both Apple submission IDs as recovery artifacts for 90 days. Recovery artifacts use the `recovery-*` or `internal-*` prefix and are excluded from GitHub Releases.

## Production identity

The isolated beta currently uses a beta-specific app ID, executable name, protocol and profile so it can coexist with VibeZ 1.4.1.

Before VibeZ 2.0 stable, production builds must switch back to the stable identity:

- App ID: `com.vibez.app`
- Product name: `VibeZ`
- Executable: `vibez`
- Protocol: `vibez://`
- Normal VibeZ user-data profile

This identity switch must happen only in the production release path, not in the isolated beta build.

## Release gate for VibeZ 2.0 stable

VibeZ 2.0 must not be published as stable until all of these are true:

- Linux x64 AppImage, DEB, RPM, Pacman and Flatpak builds pass.
- Windows x64 NSIS build passes.
- The Microsoft Store MSIX builds, unpacks, installs, reports the expected package family and registers the expected executable on a clean Windows runner.
- macOS Intel and Apple Silicon builds pass.
- The direct GitHub Windows installer is explicitly identified and verified as unsigned; `SHA256SUMS` is published with it.
- macOS apps are Developer ID signed and notarized.
- Automatic/update metadata is generated from the final published artifacts.
- Upgrade from VibeZ 1.4.1 to VibeZ 2.0 is tested.
- A clean install is tested on Windows and macOS.
- Screenshot, Settings, login/session persistence and tray/menu-bar behavior are tested on all three platforms.
- SHA-256 checksums are generated after signing/notarization.

## Security rules

- Private keys and API credentials are never committed to the repository.
- Signing secrets exist only in GitHub Secrets or the signing provider.
- Production signing runs only from GitHub-hosted runners and the official repository.
- Signed artifacts are never modified after signing; if a file changes, it must be signed again.
- An unsigned Windows artifact must never be presented as signed. An unsigned macOS artifact must never replace a signed and notarized production artifact with the same release version.
