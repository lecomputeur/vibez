# VibeZ on Windows and macOS

VibeZ provides native desktop packages for Windows and macOS alongside the Linux packages. Public releases are built automatically from this GitHub repository by GitHub Actions and include SHA-256 checksums.

## Windows

### Recommended installation route

Install **[VibeZ Desktop from the Microsoft Store](https://apps.microsoft.com/detail/9NR7L2G4MS08)** for the recommended Windows installation. The Store version uses a separate MSIX package validated and signed by Microsoft. Alternatively, use the direct GitHub download described below.

### Direct GitHub download

- Windows x64: `VibeZ-<version>-Windows-x64.exe`

Download the installer and `SHA256SUMS` from the [official GitHub Releases page](https://github.com/lecomputeur/vibez/releases).

The direct GitHub Windows installer is currently unsigned. Windows may therefore show **Windows protected your PC** or **Unknown publisher**.

If you downloaded VibeZ from this official repository:

1. Verify the installer's SHA-256 against `SHA256SUMS`.
2. Open the VibeZ installer.
3. If SmartScreen appears, choose **More info**.
4. Confirm that the displayed app name and downloaded filename match the official release.
5. Choose **Run anyway** and continue through the installer.

On managed work or school PCs, administrator policy may block unsigned applications completely. VibeZ cannot bypass that policy.

Submitting a file to Microsoft for malware analysis is appropriate only when Defender incorrectly detects it as malware or potentially unwanted software. It is not a manual consumer SmartScreen allow-list.

## macOS

### Which download?

- Apple Silicon (M1, M2, M3, M4 and newer): `VibeZ-<version>-macOS-arm64.dmg`
- Intel Mac: `VibeZ-<version>-macOS-x64.dmg`

A ZIP build is also supplied for each architecture. For most users, the DMG is the easiest option.

VibeZ 2 macOS packages are signed with an Apple Developer ID certificate and notarized by Apple. The release workflow verifies the signature, Gatekeeper acceptance, notarization and stapling before publication.

Download VibeZ from the [official GitHub Releases page](https://github.com/lecomputeur/vibez/releases), open the DMG and drag **VibeZ** to **Applications**.

### Screenshot permission on macOS

The VibeZ Screenshot feature needs macOS screen-capture permission.

The first time macOS blocks screen capture, open **System Settings → Privacy & Security → Screen & System Audio Recording** (called **Screen Recording** on some macOS versions), enable VibeZ, then restart VibeZ if macOS requests it.

VibeZ only captures the screen when you explicitly start its Screenshot tool.

## Verify a download

Every VibeZ release publishes a `SHA256SUMS` file. Compare the checksum of your downloaded file with the value in that file.

### Windows PowerShell

```powershell
Get-FileHash .\VibeZ-<version>-Windows-x64.exe -Algorithm SHA256
```

### macOS Terminal

```bash
shasum -a 256 VibeZ-<version>-macOS-arm64.dmg
```

The calculated value must exactly match the corresponding line in `SHA256SUMS` on the GitHub release.

## Updates

**Windows:** direct GitHub installations can use VibeZ's update flow where supported. A new unsigned installer can trigger SmartScreen again because each version starts with a new file reputation. The Microsoft Store manages updates for Store installations.

**macOS:** starting with VibeZ 2.0.1, signed and notarized installations can download verified updates in the app. VibeZ selects the ZIP matching the Mac's processor and offers **Restart & update** or **Later**. Users of 2.0.0 must install 2.0.1 manually once to enable this update path.

Only download VibeZ from **https://github.com/lecomputeur/vibez**, the project website linked from that repository, or the [official Microsoft Store listing](https://apps.microsoft.com/detail/9NR7L2G4MS08).

See the public [code signing policy](https://lecomputeur.github.io/vibez/code-signing-policy.html) for the current Windows and macOS signing status.
