# VibeZ Tauri Preview — Linux prototype

An experimental Rust/Tauri implementation alongside the existing Electron VibeZ. **Not a production replacement.** The current Electron application, main branch, GitHub releases, website and Microsoft Store submission must remain unchanged.

## Isolation

| Item | Preview |
| --- | --- |
| Display name | VibeZ Tauri Preview |
| Version | 0.1.0 (separate version sequence) |
| Executable | `vibez-tauri-preview` |
| Application ID | `nl.lecomputeur.vibez.tauri.preview` |
| Config | `$XDG_CONFIG_HOME/nl.lecomputeur.vibez.tauri.preview` (normally `~/.config/...`) |
| Website/session data | `$XDG_DATA_HOME/nl.lecomputeur.vibez.tauri.preview` (normally `~/.local/share/...`) |
| Automatic updates | Not enabled; never uses Electron release feeds |
| Global shortcut | Not registered; does not steal Electron's Ctrl+Shift+S |
| URL protocol | Not registered; existing `vibez://` is untouched |
| Autostart | Off by default; opt-in entry named VibeZ Tauri Preview |

You may run both applications at once. Sign in separately in the preview: it does not copy the Electron cookies or session. Uninstalling the preview package does not remove Electron VibeZ.

## First implemented slice

- Native Linux window hosting two independent WebKitGTK webviews: bundled local toolbar and remote Mistral Vibe content. No iframe, no Chromium or Node.js runtime shipped in the app.
- Reuses the existing VibeZ icon and exact toolbar CSS at build time, without editing the source assets.
- Back, Forward, Reload; native history state; native title includes the complete preview version.
- Layout recalculates in logical pixels on resizing and scale changes. Includes native offline maximize/restore checks.
- Settings for zoom, language, screenshot-button visibility, opt-in start at login and opt-in close to tray.
- Existing 34-language strings reused for applicable toolbar/settings labels; preview explanations are Dutch/English and tray/error text is initially English. This is not yet a fully localized replacement.
- Screenshot button uses the XDG desktop screenshot portal with interactive consent. Captures are copied to the clipboard; paste manually into Vibe with Ctrl+V. Available selection modes depend on the desktop portal.
- Independent tray menu with Open, Screenshot, Settings and Quit.
- External HTTP(S) links go to the normal browser. Remote website content has no native command capabilities; only bundled toolbar/settings views can invoke commands. No shell execution bridge or arbitrary file access is exposed.

## What still needs validation / implementation

The automated test page is deliberately offline and is not a mock claim that the live service was tested. Validate your real Mistral login, Work/Code, conversation persistence, uploads, downloads and clipboard attachment workflow on your desktop. The preview keeps trusted authentication navigation inside the content view; popup/opener-dependent SSO may not work yet. It does not disable provider protections or request account passwords outside the official website.

Microphone/camera permissions, the Electron region-selection overlay, automatic screenshot paste, global shortcuts (including Wayland portals), automatic updates, full feature parity and macOS/Windows packaging are not part of this first Linux build. Browser media permission requests are denied for now. Do not use this preview as a reason to remove the stable app.

Tauri's multi-webview API currently requires its `unstable` feature. Tauri is therefore pinned to an exact release, and the build preserves resolved Rust/npm lockfiles in its artifacts. This prototype is intended to test suitability, not promise that WebKitGTK behaves identically to Chromium.

## Install the Linux test package

Built on Ubuntu 24.04 for x86_64/amd64. Download the DEB from the **VibeZ Tauri Preview - Linux only** workflow artifact on the prototype branch. It is not published to the normal Releases feed.

From the directory containing the downloaded package:

```bash
sudo apt install ./vibez-tauri-preview_0.1.0_amd64.deb
vibez-tauri-preview
```

Use the actual filename if the bundler changes capitalization. Search your application menu for **VibeZ Tauri Preview**, not VibeZ.

The DEB depends on system WebKitGTK 4.1 and GTK. Keep those runtime libraries updated through your Linux distribution. Screenshots need a working XDG portal backend for your desktop, such as `xdg-desktop-portal-gnome`, `xdg-desktop-portal-gtk` or `xdg-desktop-portal-kde`. Portal cancellation or absence returns an error; it never triggers an unrestricted fallback screenshot.

To remove only the preview, first disable its Start at login setting and quit it, then:

```bash
sudo apt remove vibez-tauri-preview
```

The isolated preview profile remains for a future reinstall. Do not delete your existing VibeZ profile.

## Build from source in a separate checkout

```bash
git clone --branch vibe/tauri-linux-preview-7c4e90 --single-branch https://github.com/lecomputeur/vibez.git vibez-tauri-preview-source
cd vibez-tauri-preview-source/tauri-preview
# Install Rust and the Linux dependencies documented by Tauri first.
npm install
npm test
npm run dev
# Build only the preview DEB:
npm run build -- --bundles deb
```

Source assets in the parent repository are read-only inputs. Do not run the Electron project's release script or switch your existing Electron working directory to this branch.

## Testing

The dedicated read-only workflow checks that no production files differ from the base commit. It runs frontend/security configuration tests and Rust policy tests, builds a Linux DEB, verifies its independent package identity and starts the extracted binary under GTK/WebKit with Xvfb and Openbox. Native smoke tests check the toolbar's IPC handshake, denial of native IPC from content, title, resizing, maximize/restore and hide/show. A failed smoke test prevents publishing the installable artifact.

Real desktop testing checklist:

1. Start stable VibeZ and VibeZ Tauri Preview side by side; confirm separate logins/settings.
2. Sign in via the official website; open Work and Code; create a harmless test conversation.
3. Resize repeatedly, maximize/restore, and move between monitors/scales.
4. Exercise Back/Forward/Reload, upload/download and copy/paste.
5. Capture a screenshot, cancel a second capture, and check clipboard attachment manually.
6. Test tray only when its icon is visible; verify relaunch restores the window.
7. Verify removing the preview leaves Electron VibeZ and its stored login intact.

## Privacy and attribution

VibeZ is independent and is not affiliated with or supported by Mistral AI. The official service handles chats and account information. This preview stores its own settings and WebKit profile locally and adds no telemetry or automatic update requests. Screenshot image access is only initiated by the toolbar/tray action and goes through the desktop portal. It does not read the current clipboard. Diagnostics exclude chat messages, authentication tokens and cookies.

Original logo, toolbar CSS and translations are reused under the project's MIT license. See the repository LICENSE.
