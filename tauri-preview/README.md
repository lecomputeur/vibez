# VibeZ Tauri Preview — Linux prototype

Experimental Rust/Tauri implementation alongside Electron VibeZ. **Not a production replacement.** The Electron app, main branch, stable releases, website and Microsoft Store submission are unchanged.

## 0.1.1 — sign-in popup repair

The 0.1.0 handler moved a popup URL into the main view and denied the new window. Version 0.1.1 instead returns a related WebKit window using Tauri's `window_features` and `NewWindowResponse::Create`. This preserves `window.opener`, the original request and the preview's WebContext. Blank popup bootstraps are supported. Closing a popup does not close or reload the main page, and popup creation is capped at four windows.

A Home button returns to Vibe without clearing cookies or settings. Load failures and terminated web processes are reported in the toolbar. Settings diagnostics include only recent navigation origins and numeric load error codes: no URL paths, queries, fragments, credentials, cookies or tokens.

**This repairs the popup implementation, not Google's restrictions on embedded browsers.** A complete real Google/Mistral sign-in has not been verified. Google can reject embedded user agents (`disallowed_useragent` / browser not supported). No user-agent spoofing, certificate bypass, credential interception or cookie transfer is implemented. Opening Vibe in your normal browser does not automatically sign the preview in. A browser-based return flow requires a supported service-side integration; this preview does not invent one.

References:
- https://developers.google.com/identity/protocols/oauth2/native-app#disallowed_useragent
- https://docs.rs/tauri/latest/tauri/webview/enum.NewWindowResponse.html

## Independent installation

| Item | Preview |
| --- | --- |
| Name | VibeZ Tauri Preview |
| Version | 0.1.1 |
| Executable | `vibez-tauri-preview` |
| Debian package | `vibe-z-tauri-preview` |
| Application ID | `nl.lecomputeur.vibez.tauri.preview` |
| Settings | `~/.config/nl.lecomputeur.vibez.tauri.preview/settings.json` |
| Webview data | `~/.local/share/nl.lecomputeur.vibez.tauri.preview/` |

XDG directory overrides are respected. The preview never imports Electron cookies, changes the existing `vibez://` protocol, registers Electron's shortcut or uses its update feed. Start-at-login and close-to-tray are opt-in. Both apps may run at once. Upgrading this package replaces only the preview, preserving its own profile.

## Features and limitations

Separate WebKitGTK views render the local toolbar and Mistral Vibe website. Only local toolbar/settings views can call native commands. The website and all sign-in popups have no native command capabilities. No shell-command bridge or arbitrary file access is exposed.

The original logo, toolbar CSS and applicable 34-language translations are reused read-only. Back, Forward, Reload, Home, zoom/language settings, screenshot-button visibility, opt-in autostart and an independent tray are included. Preview explanations are English/Dutch; some status/tray text is English.

GTK packs a fixed 54-logical-pixel toolbar and expanding content. Screenshots use the interactive desktop XDG portal and are copied to the clipboard; paste manually into Vibe with Ctrl+V. Portal failure or cancellation never triggers an unrestricted screenshot fallback.

Microphone/camera permissions, the Electron selection overlay, automatic screenshot paste, global shortcuts, automatic updates and Windows/macOS packaging are not enabled. Real Mistral login, Work/Code, uploads/downloads and session persistence still require desktop validation. Keep the stable app installed.

## Install or upgrade (Ubuntu 24.04 / compatible amd64 Linux)

Quit **VibeZ Tauri Preview** first, including its tray process. Download the DEB from the preview workflow artifact, not the stable Releases feed.

With the filename provided in the chat:

```bash
sudo apt install ./vibez-tauri-preview_0.1.1_amd64.deb
vibez-tauri-preview
```

The original bundler filename is `VibeZ Tauri Preview_0.1.1_amd64.deb`; quote it when using that filename. `apt` installs the system WebKitGTK/GTK and desktop portal dependencies. Keep those system packages updated.

Check the window title or `vibez-tauri-preview --version`: it must say 0.1.1. Click the Home icon to return from a previously failed login, then try your existing sign-in method. Do not share passwords, verification codes or complete OAuth URLs when reporting a failure.

To remove only the preview, first disable its Start-at-login setting and quit it:

```bash
sudo apt remove vibe-z-tauri-preview
```

## Build and tests

Use a separate checkout of branch `vibe/tauri-linux-preview-7c4e90`. Install Rust and the Tauri Linux build dependencies, then run in `tauri-preview`:

```bash
npm install
npm test
npm run build -- --bundles deb
```

The dedicated read-only workflow refuses changes outside the preview and its own workflow. It runs frontend/isolation and Rust tests, verifies the generated package identity/version, and starts the actual binary under Xvfb/Openbox. Offline integration checks cover direct and initially-blank popups, `window.opener`, callback delivery, popup close, denied native IPC and an unchanged main page, followed by resize/maximize/restore tests. Failed integration tests prevent publishing the installable artifact. These are offline tests, **not a successful live Google login**.

Tauri's multi-webview API uses its unstable feature. Its exact version is pinned; resolved Rust/npm lockfiles are included in validation artifacts. No production release is created by this workflow.
