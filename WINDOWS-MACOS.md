# VibeZ Windows/macOS release candidate 3.0.9

Stable downloads remain [3.0.8](https://github.com/lecomputeur/vibez/releases/tag/v3.0.8). [3.0.9 status](RELEASE-STATUS-3.0.9.md): Intel Mac Apple-ticket validation is blocked; no stable 3.0.9 publication or Store submission performed.

Windows x64 build outputs: `VibeZ-3.0.9-Windows-x64-Setup.exe`, `VibeZ-3.0.9-Windows-x64.msi`, and `VibeZ-3.0.9-Windows-x64-Store.msix`. Direct installers are unsigned. MSIX 3.0.9.0 is an unsigned upload file for the existing Partner Center product, not a recommended direct installer or proof of Store publication. Windows requires WebView2; the Store manifest targets Windows 10 build 17763+. See [Store steps and What's New](MICROSOFT-STORE-3.0.9.md).

macOS requires 14+. Apple Silicon candidate DMG/ZIP passed Developer ID signing, notarization and stapling. Intel compilation/native tests passed; its final ticket-validation failure blocks release of the Intel DMG/ZIP and stable all-platform publication.

Ordinary 3.x profiles/settings are preserved. Isolated Canvas Test, Electron and preview profiles remain separate. Do not delete or migrate profiles. Linux Canvas/verification routing improves; the original high-CPU heavy conversation remains open. TLS trust dependencies are refreshed on all platforms. Direct VibeZ 3 updates remain user-confirmed; Store installations use Store delivery.
