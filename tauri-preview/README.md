# VibeZ Tauri Preview — Linux/Windows prototype

Experimental Rust/Tauri implementation alongside Electron VibeZ. **Not a production replacement.** The Electron app, main branch, stable releases, website and Microsoft Store submission are unchanged.

## 0.1.4 — complete preview translations and remembered language button

All preview-specific explanatory text is now available in the same 34 languages as VibeZ. The top toolbar has a globe/language button for immediate manual selection. Choosing a language calls the same native settings save path as the Settings window, writes it to the isolated preview profile and rebuilds the tray menu, so the choice survives app restarts. Choosing **System** returns to automatic operating-system language detection.

## 0.1.3 — Linux package plus Windows Store preview build

Version 0.1.3 keeps the working Linux preview and adds a separate Windows x64 build based on Microsoft WebView2. The Windows Store preview uses its own package identity, `LeComputeur.VibeZTauriPreview`, and is deliberately not compatible with the existing VibeZ Desktop Store product. Do not upload it to the current VibeZ Desktop listing. A new Partner Center product must be reserved before final Store submission so its assigned identity can be inserted and rebuilt.

On Windows the Screenshot button opens the built-in Windows screen-capture UI (`ms-screenclip:`); the result can then be pasted into Vibe with Ctrl+V. Linux continues to use the XDG screenshot portal.

## 0.1.2 — translated tray and separate preview update checks

The tray menu now uses the same saved language or operating-system language as the toolbar. Existing translations are reused for all 34 menu languages. Saving a language change rebuilds the native menu immediately, without signing out or restarting. Dutch screenshot/status messages, navigation tooltips, settings title and explanatory text are included. New update-dialog text is Dutch/English; technical diagnostic details and some low-level library errors remain English.

Right-click the preview tray icon and choose **Controleren op updates…** / **Check for updates**. This performs a manual, read-only check of successful Linux preview builds on `vibe/tauri-linux-preview-7c4e90`. It ignores failed builds, unrelated workflows, different platforms and expired artifacts. Version numbers are compared as semantic versions; an older artifact never produces a downgrade offer. A connection error or missing artifact is reported, not presented as an up-to-date result.

When a newer tested preview exists, **Download openen / Open download** opens that exact GitHub Actions artifact in your browser. GitHub requires you to sign in to download it. Extract the ZIP and install the contained `.deb` manually. This is **update discovery, not automatic installation**. It does not use the Electron Releases feed or change the regular VibeZ app. No GitHub token or credentials are stored in the preview. Checks have a 25-second overall timeout and bounded response sizes; nothing is checked automatically at startup.

The previous 0.1.1 candidate had a compile error in its load-error reporting (`glib::Error::code` is not available in the selected binding). The diagnostic path now records only the error category and origin, never the raw error text or login URL.

## Sign-in handling

The 0.1.0 handler moved a popup URL into the main view and denied the new window. The new handler returns a related WebKit window using Tauri's `window_features` and `NewWindowResponse::Create`. It preserves the opener and original request. Blank popup bootstraps are supported; closing a popup leaves the main page alone. Popup creation is capped at four windows.

A Home button returns to Vibe without clearing cookies or settings. Load failures and terminated web processes are reported in the toolbar. Diagnostics contain recent navigation origins, not paths, query strings, credentials or tokens.

Google can still reject embedded browsers. This update does not bypass provider restrictions, spoof the user agent, intercept credentials or transfer cookies. Offline popup tests are not a claim that a complete real Google/Mistral sign-in has been verified in this build.

## Independent installation

| Item | Preview |
| --- | --- |
| Name | VibeZ Tauri Preview |
| Version | 0.1.4 |
| Executable | `vibez-tauri-preview` |
| Debian package | `vibe-z-tauri-preview` |
| Application ID | `nl.lecomputeur.vibez.tauri.preview` |
| Settings | `~/.config/nl.lecomputeur.vibez.tauri.preview/settings.json` |
| Webview data | `~/.local/share/nl.lecomputeur.vibez.tauri.preview/` |

XDG directory overrides are respected. The preview never imports Electron cookies, changes the existing `vibez://` protocol, registers Electron's shortcut or uses its update feed. Autostart and close-to-tray are opt-in. Both apps may run at once. Upgrading replaces only the preview and preserves its own profile.

## Install / update on Ubuntu 24.04 amd64

Close the running preview through its tray menu (**Quit preview / Afsluiten**), then run from the download directory:

```bash
sudo apt install ./vibez-tauri-preview_0.1.4_amd64.deb
vibez-tauri-preview
```

For Dutch menus choose **Instellingen → Taal → Nederlands → Opslaan**, or choose the system language on a Dutch desktop. This controls the preview shell, not the separate language preference of the Mistral website.

To uninstall only the preview, first disable its autostart setting and quit it:

```bash
sudo apt remove vibe-z-tauri-preview
```

## Features and limitations

Separate WebKitGTK views render the local toolbar and Mistral Vibe website. Only local toolbar/settings views can call native commands. Neither the website nor sign-in popups receive native permissions. Update checks can be triggered only by the native tray menu.

The original logo, toolbar CSS and existing translations are read-only build inputs. Back, Forward, Reload, Home, zoom/language settings, screenshot-button visibility, opt-in autostart and an independent tray are included. GTK packs a fixed 54-logical-pixel toolbar and expanding content.

Screenshots use the interactive XDG portal and are copied to the clipboard; paste with Ctrl+V. Portal failure or cancellation never causes an unrestricted fallback screenshot. Microphone/camera, automatic screenshot paste, global shortcuts, automatic installation and Windows/macOS packages are not yet implemented. Keep the stable app installed.

## Tests and distribution

The branch-only workflow checks that production files are unchanged. It runs frontend/isolation checks, Rust policy/translation/update-discovery tests, verifies the .deb identity and executes offline native GTK/WebKit tests. Native tests cover the translated tray/update menu, popup opener/callback handling, denial of native IPC to web content, title, resizing/maximizing/restoring and hide/show. Installable artifacts are uploaded only when these checks pass. They are not published to the stable Releases feed.

Tauri is pinned; its multi-webview API uses the unstable feature. The resolved Cargo/npm lockfiles are preserved in build artifacts. A real desktop login, screenshot attachment flow, downloads, microphone requirements and Linux desktop integration still need user validation.
