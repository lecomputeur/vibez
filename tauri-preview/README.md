# VibeZ Tauri Preview

## 0.1.17 — Linux desktop icon identity

Before creating windows, the preview aligns GLib program name and GDK program class with its existing GTK application ID and StartupWMClass. The DEB launcher uses an installed absolute pixmap (also kept as a themed icon); GTK has an embedded-pixel fallback. Tray image files are isolated per application/process. Installation/removal refresh system desktop caches without changing user data or pinned launchers.

The new installed-package icon test reads actual X11 WM_CLASS, _GTK_APPLICATION_ID and _NET_WM_ICON, checks launcher image bytes and the exported StatusNotifier icon, and repeats cold/warm/direct launches plus a late-starting tray host. This is an X11 integration check, not a claim to have run Cinnamon or every desktop environment.

## 0.1.16 — startup language recovery

This candidate retries browser-language preparation at most three times before reporting a real failure. Successful recovery clears only its own stale language warning, not newer unrelated messages. Recovered operation errors remain in a bounded diagnostic history. Error reporting is serialized with the operation, obsolete requests do not publish results, and failed navigation submission is not marked complete.

The native Linux smoke test now exercises real nl/en/nl cookie preparation on a fresh neutral WebKit profile without contacting Mistral, in addition to the existing exact-size, popup/isolation and hidden-window checks. This is not a claim that the user's original intermittent failure has been reproduced or that real account login has been retested.

See `RELEASE-GATE.md` before public distribution. No stable release, Electron replacement or Store submission is performed by these build workflows.

## 0.1.15 — stability update

The separate Rust/Tauri preview runs beside the stable Electron VibeZ application. This version addresses the highest-priority findings of the 0.1.14 code review, not every item in that review.

### Changes

- Linux uses a GtkLayout viewport instead of a GtkFixed that propagated child minimum sizes. The toolbar remains 54 logical pixels high; enlarging the window no longer increases its minimum size. Layout never shows a hidden window.
- Preference edits are field-level patches with compare-and-set conflict detection. A stale settings form cannot overwrite a newer toolbar language while changing only zoom. Backend preference transactions are serialized; failed persistence rolls back changed runtime options.
- Both control windows ignore obsolete asynchronous responses and synchronize untouched fields. Diagnostics failures no longer disable Save. Diagnostic information can be refreshed or copied independently.
- Language is configured on a neutral bootstrap view before the first remote navigation. Subsequent language requests are serialized and generation-numbered; navigation waits for loaded Vibe/Chat content instead of forcing a timed redirect during authentication. The Linux WebKit language handoff from 0.1.13 is retained.
- The incorrect cookie diagnostic parser was replaced. Normal status messages are short, translated and temporary; detailed language information is only in Diagnostic information.
- Settings now have a versioned schema. Existing preview preferences are read without clearing the webview profile. Invalid preferences are backed up before defaults are used; unknown future schemas are not overwritten.
- Authentication routing has a ten-minute limit and Linux popup cleanup clears finished/cancelled auth mode when the main page is already Vibe/Chat.
- The DEB declares libc6 >= 2.39 and retains the identifier-named desktop entry and VibeZ icon.

### Tests and limitations

Frontend tests include real execution of the control JavaScript against delayed responses, stale forms, conflicting edits, diagnostic failures and multiple cookie positions. Rust tests cover patch merging, persistence/migration/recovery, status expiration, URL boundaries and language navigation eligibility. Native Linux tests assert requested window dimensions after shrink/grow and restore, not just child geometry relative to whatever window size was obtained. Related popup/opener and native-capability rejection checks remain enabled. Test-only layout repair was removed.

A successful build is not a claim of a real Google/Microsoft/Mistral login test. Native CI uses an isolated X11/Openbox desktop. Wayland, fractional scaling, installed-desktop tray availability and every live website behavior still require platform validation. Windows navigation/loading reporting and update-validation parity remain follow-up audit items. Comprehensive reproducible dependency locking and a dedicated Rust advisory audit are also follow-up work; build-specific resolved lockfiles are included in the artifact.

Automatic update installation, global shortcuts, microphone/camera permissions and macOS packages are not enabled. Preview updates are manual and separate from stable Electron releases.

## Independent identity

| Item | Preview |
| --- | --- |
| Version | 0.1.17 |
| Name | VibeZ Tauri Preview |
| Executable | `vibez-tauri-preview` |
| Debian package | `vibe-z-tauri-preview` |
| App ID | `nl.lecomputeur.vibez.tauri.preview` |
| Candidate Store identity | `LeComputeur.VibeZTauriPreview` |
| Linux settings | `~/.config/nl.lecomputeur.vibez.tauri.preview/settings.json` |
| Linux webview data | `~/.local/share/nl.lecomputeur.vibez.tauri.preview/` |

XDG directory overrides are respected. The preview never imports Electron cookies, registers its URL protocol/global shortcut or changes its release feed. Autostart and close-to-tray are opt-in. Both apps may run simultaneously.

## Install Linux amd64

Fully quit the previous preview through its tray menu, then install from the directory containing the download:

```sh
sudo apt install ./vibez-tauri-preview_0.1.17_amd64.deb
vibez-tauri-preview
```

This package targets Ubuntu 24.04-class systems with libc6 >= 2.39 and WebKitGTK 4.1. It upgrades only the separate preview and preserves its browser profile. To remove it, first disable its autostart setting and quit it, then run `sudo apt remove vibe-z-tauri-preview`.

## Windows preview

Use the separately built NSIS Setup.exe for local installation when available. The candidate MSIX is not signed for local testing. Do not upload it to the existing VibeZ Desktop Store product; a separate matching Partner Center identity is required. This workflow does not submit anything to the Store.

## Security boundaries

Only bundled shell/settings webviews have native command capabilities. Remote Vibe content and OAuth popups do not. Login popups use related webviews and the preview profile without user-agent spoofing or certificate bypasses. Navigation diagnostics retain origins, not URL queries, fragments, tokens or chat content. The language diagnostic shows only a sanitized language preference, not account cookies. The screenshot action uses the interactive system dialog and clipboard; cancelling never triggers a hidden capture.

## Development

Run `npm install --ignore-scripts`, `npm test`, then `npm run build -- --bundles deb` in `tauri-preview`. Tests prepare assets before Rust compilation. The original Electron logo, toolbar stylesheet and translation bundles are read-only build inputs. Only `tauri-preview/**` and the two preview workflows may differ from the preview base commit. Review `TESTING-0.1.17.md` for release validation scope.
