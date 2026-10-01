# VibeZ Tauri Preview — Linux prototype

Experimental Rust/Tauri implementation alongside the existing Electron VibeZ. **Not a production replacement.** No changes to the Electron application, main branch, stable releases, public website or Microsoft Store submission.

## Independent installation

| Item | Preview |
| --- | --- |
| Display name | VibeZ Tauri Preview |
| Version | 0.1.0 (independent version sequence) |
| Executable | `vibez-tauri-preview` |
| Debian package name | `vibe-z-tauri-preview` |
| Application ID | `nl.lecomputeur.vibez.tauri.preview` |
| Settings | `~/.config/nl.lecomputeur.vibez.tauri.preview/settings.json` by default |
| Webview data | `~/.local/share/nl.lecomputeur.vibez.tauri.preview/` by default |

XDG directory overrides are respected. The preview does not copy the Electron cookies, change the existing `vibez://` protocol, register Electron's shortcut or use its update feed. Start-at-login and close-to-tray are off by default. Opt-in autostart uses the separate name **VibeZ Tauri Preview**. Both apps may run at once; log into the preview separately.

## First implemented slice

The native Linux window contains separate WebKitGTK views for the bundled toolbar and the official Mistral Vibe website. The remote page gets no native command capabilities. Only the bundled toolbar/settings pages can invoke the restricted application commands; there is no shell-command or arbitrary-file-access bridge.

The logo, existing toolbar CSS and applicable 34-language translations are copied read-only from the existing VibeZ source during build. The preview provides Back, Forward, Reload, a versioned title, zoom/language settings, screenshot-button visibility, opt-in autostart, and a separate tray with Open, Screenshot, Settings and Quit. Preview explanations are English/Dutch; tray/status text is initially English, so localization is not yet complete in every language.

Linux layout uses GTK's actual container packing: a fixed 54-logical-pixel toolbar and expanding website. This avoids treating a GtkBox as an absolute-positioned surface. The native tests inspect real GTK allocations while resizing/maximizing/restoring.

Screenshots use the desktop's interactive XDG portal and are copied to the clipboard. Paste manually into Vibe with **Ctrl+V**. Selection modes depend on the desktop portal. Cancelling or a missing portal returns an error; no silent unrestricted screenshot fallback is attempted.

## Not yet equivalent to the stable app

This is the first Linux preview, not a claim of complete parity. Microphone/camera permissions, the Electron region-selection overlay, automatic screenshot paste, global shortcuts (including Wayland portals), automatic updates, and Windows/macOS packaging are not enabled. Remote media permission requests are denied for now.

Actual Mistral sign-in, Work/Code, conversation persistence, uploads, downloads and pasted attachments need testing on your desktop. Trusted authentication navigation stays inside the content view; popup/opener-dependent SSO may not work yet. The app does not bypass provider protections or ask for passwords outside the official website.

The automated integration page is explicitly offline and is **not** a claim that a logged-in Mistral session has been tested. Tauri's multi-webview API currently uses its `unstable` feature; the exact Tauri release is pinned. Resolved Rust/npm lockfiles are preserved in build artifacts.

## Install on Ubuntu 24.04 / compatible amd64 Linux

The installable DEB is provided only after tests pass in the **VibeZ Tauri Preview - Linux only** workflow. It is not published to the stable GitHub Releases feed.

For the original filename produced by the bundler:

```bash
sudo apt install "./VibeZ Tauri Preview_0.1.0_amd64.deb"
vibez-tauri-preview
```

If the downloaded file was renamed to `vibez-tauri-preview_0.1.0_amd64.deb`, use that filename instead. Search the application menu for **VibeZ Tauri Preview**, not VibeZ. The binary is `vibez-tauri-preview`, while the Debian package identifier is `vibe-z-tauri-preview`.

System dependencies include GTK, WebKitGTK 4.1, Ayatana AppIndicator and xdg-desktop-portal. Keep them updated through your distribution. Screenshot interaction also needs a working portal backend appropriate to your desktop. Enable close-to-tray only when its icon is actually visible; relaunching the preview restores its main window.

To uninstall only this preview: disable its Start at login option, quit it, then run:

```bash
sudo apt remove vibe-z-tauri-preview
```

The separate preview profile is retained for a later reinstall. Your existing VibeZ profile is never removed.

## Source build in a separate checkout

```bash
git clone --branch vibe/tauri-linux-preview-7c4e90 --single-branch https://github.com/lecomputeur/vibez.git vibez-tauri-preview-source
cd vibez-tauri-preview-source/tauri-preview
# Install Rust and Tauri's Linux prerequisites first.
npm install
npm test
npm run dev
npm run build -- --bundles deb
```

The npm development/build scripts prepare assets from the preview's own directory. Do not switch your current Electron checkout to this branch or invoke the production release workflow.

## Validation

The read-only Linux workflow refuses changes outside `tauri-preview/` and its own workflow file. It runs six frontend/isolation tests, seven Rust policy tests, npm security auditing, the DEB build and package identity checks. Under Xvfb/Openbox it launches the extracted binary and checks the toolbar IPC handshake, denial of native IPC from the content view, the versioned title, actual GTK toolbar/content allocations across repeated resize/maximize/restore transitions, and hide/show.

A failed native test prevents upload of the installable artifact. Validation logs and the clearly labelled offline screenshot remain available for debugging. Live Mistral functionality and desktop portal interaction must be verified separately.

## Privacy and attribution

Independent project, not affiliated with or supported by Mistral AI. The official service handles account information and chats. The preview stores its own settings/WebKit profile locally, adds no telemetry or update requests, and only reads screenshot images after a user-initiated portal request. It does not read existing clipboard contents. Diagnostics exclude chats, passwords, cookies and authentication tokens.

Original icon, toolbar CSS and translations are reused under the repository's MIT license. See the repository LICENSE.
