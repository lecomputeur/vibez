# VibeZ Tauri Preview — Linux/Windows prototype

Experimental Rust/Tauri implementation alongside Electron VibeZ. **Not a production replacement.** Changes stay on the preview branch: the Electron app, main branch, stable releases, website and existing Microsoft Store submission are unchanged.

## 0.1.7 — controlled first-login investigation

The tester reports: first Google sign-in fails with HTTP 400 in Edge; Home does not fix it; fully restarting and then pressing Sign in succeeds without repeating credentials. This does not prove that Mistral had completed the first sign-in.

This build disables the opener plugin's injected automatic click handler with `open_js_links_on_click(false)`, leaving link handling to the native navigation/popup code. It adds bounded, in-memory, origin-only main-window routing diagnostics. It does not clear the user's profile, copy cookies, change provider restrictions or broaden the existing navigation allowlist.

A new offline probe checks actual webview click handling for `_blank`, Ctrl-click and Shift-click. Windows CI runs this focused probe in WebView2; Linux runs it before the existing GTK/WebKit smoke tests. **Neither this probe nor a successful build is proof that real Google/Mistral sign-in is fixed.** See [the test notes](TESTING-0.1.7.md).

## Earlier preview changes

- **0.1.6:** allowed HTTPS redirects within an already-created auth popup. This did not remove main-window external routing or the opener's injected handler; the user's 400 error persisted.
- **0.1.5:** preserved nested related login popups, with opener/callback and native-IPC isolation tests.
- **0.1.4:** added all 34 preview-specific translation bundles and an immediately saved toolbar language picker. Native tray labels follow the same selection. System uses the OS locale. These are technically complete translations, not a claim of native-speaker review.
- **0.1.3:** added Windows x64 WebView2 builds and a separate candidate Store package.
- **0.1.2:** added translated tray menus and manual discovery of successful preview builds.

## Independent installation

| Item | Preview |
| --- | --- |
| Name | VibeZ Tauri Preview |
| Version | 0.1.7 |
| Executable | `vibez-tauri-preview` |
| Debian package | `vibe-z-tauri-preview` |
| Application ID | `nl.lecomputeur.vibez.tauri.preview` |
| Candidate Store identity | `LeComputeur.VibeZTauriPreview` |
| Linux settings | `~/.config/nl.lecomputeur.vibez.tauri.preview/settings.json` |
| Linux webview data | `~/.local/share/nl.lecomputeur.vibez.tauri.preview/` |

XDG directory overrides are respected. The preview never imports Electron cookies, changes the existing `vibez://` protocol, registers Electron's shortcut or uses its update feed. Autostart and close-to-tray are opt-in. Both apps may run at once. Upgrading replaces only the preview and preserves its own profile.

### Ubuntu 24.04 amd64

Fully quit the running preview through its tray menu before installing from Downloads:

```bash
sudo apt install ./vibez-tauri-preview_0.1.7_amd64.deb
vibez-tauri-preview
```

To uninstall only the preview, disable its autostart setting and quit it, then use `sudo apt remove vibe-z-tauri-preview`.

### Windows x64

Use `VibeZ-Tauri-Preview-0.1.7-Windows-x64-Setup.exe` for normal installation. A plain executable is also built for testing. Fully quit the existing preview before upgrading. WebView2 is required; the Tauri installer handles its configured runtime installation when needed.

The unsigned candidate MSIX is not the recommended local test installer. **Do not upload it to the existing VibeZ Desktop Store product.** A separate Partner Center product and matching assigned identity are required before any separate Store submission. Store certification and a real installed-app test are separate from MSIX structural validation.

## Features and limitations

The local toolbar and remote website are separate webviews. Linux uses WebKitGTK; Windows uses WebView2. Only bundled shell/settings views can call native commands. Neither website content nor auth popups receive native capabilities. Authentication uses a separate profile from Electron, related popups, a four-window cap, and the platform's normal HTTPS handling. No user-agent spoofing, token extraction or certificate-check bypass is used.

Back, Forward, Reload, Home, zoom, language selection, screenshot-button visibility, opt-in autostart and an independent tray are included. The original logo, toolbar CSS and base translations are read-only inputs. The language setting controls the preview controls, not Mistral's own language preference.

Linux screenshots use the interactive XDG portal and are copied to the clipboard. Windows opens its built-in screen capture. Paste the captured image with Ctrl+V. No silent fallback capture is performed. Automatic screenshot paste, global shortcuts, automatic update installation and microphone/camera permissions are not enabled. macOS packaging is not implemented in this preview. Keep the stable Electron app installed.

## Manual preview updates

The tray update action checks successful preview workflow artifacts separately from stable Releases. Installation is manual: open the GitHub artifact download while signed in, extract it and install the appropriate package. This is not an automatic updater. GitHub tokens are not stored by the preview. No update check is scheduled at startup.

## Diagnostics and tests

Settings > Diagnostic information contains version/platform information, recent auth origins and the new `Link routing` block. Main routing distinguishes allowed navigation, blocked navigation, external-browser requests, page loads and main popup creation. URL paths, queries, fragments, account tokens and cookies are excluded. Logs are in memory only; restarting discards them.

The branch workflows check production-file isolation, frontend translation/security assertions, Rust tests and package identity. Linux additionally runs the full offline GTK/WebKit popup/IPC/layout smoke suite. Windows runs a focused offline WebView2 link-interception probe and builds the NSIS installer and candidate MSIX. Neither CI workflow performs real Google two-factor authentication or Store certification. First-login behavior still needs manual validation with an appropriately isolated fresh test profile; do not erase the user's working profile to force this.

Tauri is pinned and its multi-webview API currently requires its `unstable` feature. The opener dependency is pinned to 2.7.0, the version already resolved by the 0.1.6 build.
