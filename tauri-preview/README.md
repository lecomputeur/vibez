# VibeZ Tauri Preview — Linux/Windows prototype

## 0.1.14 — fixed Linux webview geometry and launcher identity

The Linux window now places the toolbar and Vibe webviews on one explicit GtkFixed canvas instead of relying on GtkBox natural-size negotiation. The toolbar is pinned to 54px and the Vibe page is positioned immediately below it on every resize, maximize, restore and show event.

The preview also enables Tauri's GTK application ID so GNOME/KDE can associate the running window and shortcuts with the installed VibeZ Tauri Preview desktop entry and icon.

## 0.1.13 — Linux layout and browser-language handoff

Linux now reapplies the GTK toolbar/content packing immediately after the bundled toolbar completes its first IPC handshake. This keeps the toolbar webview at its intended 54px height after its HTML loads and prevents the large black band above Vibe.

The remote Vibe page now receives the same language in both Mistral's NEXT_LOCALE preference and WebKitGTK's preferred-language list. On Linux that preferred-language list controls the Accept-Language request header, navigator.language(s) and JavaScript Intl locale. Exact existing NEXT_LOCALE cookies are removed before the replacement is written, and diagnostics now show the native cookie-store value separately from document.cookie and navigator.language.

System language follows the operating-system UI locale, not the user's physical country or IP location.

## 0.1.12 — confirmed Mistral language handoff

Language changes are now applied in a strict sequence: the native webview cookie store is updated first, the active Mistral document is given time to observe and confirm NEXT_LOCALE, and only then is the Mistral page navigated. Startup also performs one deliberate post-cookie navigation so the initial Vibe request can no longer race ahead of the saved language.

The preview now writes the same NEXT_LOCALE value for the Vibe host, Chat host and shared Mistral parent domain after removing stale variants. After a language switch, the status is verified against the loaded page instead of merely reporting the requested locale.

## 0.1.11 — Windows display language and stronger Mistral language switching

Windows System language now uses the actual Windows UI/display language (GetUserDefaultUILanguage) instead of relying only on the regional locale. The toolbar shows the resolved automatic language, for example AUTO·NL.

Mistral language switching now removes stale NEXT_LOCALE variants, writes the documented preference both through the webview cookie store and the active Mistral page, then performs a full navigation of the current Mistral URL so the next server request receives the new language. Startup only preloads the saved preference and no longer races the initial page load.

Diagnostics now show the Windows/Linux resolved locale plus only the non-sensitive NEXT_LOCALE/html-language state, never authentication cookies or OAuth tokens. This lets a live test distinguish a cookie write failure from Mistral overriding the language at account level.

## 0.1.10 — VibeZ language also changes the Mistral website

Changing the preview language now writes Mistral's documented `NEXT_LOCALE` language-preference cookie inside the same isolated Vibe webview profile and reloads the site. The saved language is applied again on startup. This affects only the preview profile; no authentication cookies are read or exported.

The preview supports more shell languages than Mistral currently exposes for its web interface. Known Mistral UI locales are mapped directly (English, French, German, Spanish, Polish, Italian, Portuguese, Arabic, Dutch and Ukrainian); other preview languages keep the VibeZ shell translation but use English for the Mistral website instead of sending an invalid locale.

Experimental Rust/Tauri implementation alongside Electron VibeZ. **Not a production replacement.** Changes stay on the preview branch: the Electron app, main branch, stable releases, website and existing Microsoft Store submission are unchanged.

## 0.1.9 — stateful provider-neutral authentication routing

The Google and Microsoft failures showed that treating OAuth as a permanent domain allowlist was the wrong abstraction. The main Vibe webview now enters an explicit authentication-routing mode when navigation reaches Mistral's auth service or a known provider entry point. While that mode is active, safe HTTPS redirects remain inside the same webview/profile regardless of provider domain. Authentication mode ends only when the main view returns to the actual Vibe/Chat content origins, or when the user presses Home.

This removes the 0.1.8 one-off accounts.youtube.com exception. Google, Microsoft and Apple share the same redirect-chain rule after auth starts. HTTP, nonstandard ports, file/data/javascript URLs and credential-bearing URLs remain blocked from the auth chain. Remote pages and login popups still receive no native Tauri commands. The existing profile is preserved; no cookies or tokens are copied, inspected or rewritten.

Automated tests cover provider-neutral state transitions and the existing popup/link/IPC boundaries. They still do not perform a real third-party login, so successful CI is not a claim that live Google/Microsoft authentication has been user-validated.

## 0.1.8 — retain the observed Google account handoff in the main webview

The 0.1.7 routing trace identifies a concrete handoff: after loading `accounts.google.com`, the MAIN webview logs `main-open-external: https://accounts.youtube.com`. The earlier popup changes did not affect this main-window decision.

This build adds only the exact HTTPS origin `https://accounts.youtube.com` (default port 443, no URL credentials) to the embedded navigation policy. It does not allow all YouTube subdomains or arbitrary websites. The request stays in its original webview/profile; no URL, cookie, token or provider request is rewritten or exported. Native command capabilities remain restricted to bundled controls.

Rust regressions cover the observed origin sequence, lookalike/HTTP/credential-bearing URL rejection, and denial of native commands to the account page. Existing link-interception, popup and layout checks remain enabled. **This fixes the demonstrated routing decision; it is not yet a claim of successful real Google/Mistral first-login testing.** See [the 0.1.8 test notes](TESTING-0.1.8.md).

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
| Version | 0.1.14 |
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
sudo apt install ./vibez-tauri-preview_0.1.14_amd64.deb
vibez-tauri-preview
```

To uninstall only the preview, disable its autostart setting and quit it, then use `sudo apt remove vibe-z-tauri-preview`.

### Windows x64

Use `VibeZ-Tauri-Preview-0.1.14-Windows-x64-Setup.exe` for normal installation. A plain executable is also built for testing. Fully quit the existing preview before upgrading. WebView2 is required; the Tauri installer handles its configured runtime installation when needed.

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
