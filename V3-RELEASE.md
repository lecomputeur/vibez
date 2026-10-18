# VibeZ 3.0.8 — Linux Cloudflare verification routing fix

VibeZ 3.0.8 fixes Linux navigation routing that treated embedded Cloudflare verification frames as external browser links. Required Cloudflare/Turnstile frame requests remain inside the app's webview. Ordinary external links retain their normal browser behavior.

The fix applies to Linux AppImage, DEB, RPM, Arch/Pacman and Flatpak. Windows and macOS receive the version/title update only; their navigation and rendering behavior is unchanged. Every platform shows **VibeZ V3.0.8** in its window titles.

## What changes on Linux

Cloudflare can request a verification frame while the Mistral page is loading. Previously, VibeZ's URL routing could send such a frame request to the system browser and cancel it inside the app. Retried frame requests could therefore request repeated external browser opens. The Linux routing fix keeps the required frame navigation embedded.

Normal Mistral startup, app identity `nl.lecomputeur.vibez3`, executable `vibez3`, settings, profiles and the published-release update flow are retained. The Linux rich-chat rendering, scrolling and resize improvements from 3.0.7 are also retained. No new scrolling or CPU benchmark result is claimed for 3.0.8.

## Validation and limits

The original routing defect was reproduced on Mint using the unchanged, published 3.0.7 Linux executable. Test-only instrumentation supplied a clearly labeled synthetic page with a Mistral base URI. Three Cloudflare-origin iframe assignments, including a named frame and a retry, produced three calls through the app's actual native external-opener path without a user gesture. A harmless recorder captured those requests; no real browser was launched. The app's native navigation handlers were unchanged in that reproduction.

A separate 45-second observation of ordinary public startup used a fresh profile without replacing HTML, injecting JavaScript or evaluating page content. The public Mistral page finished loading; no Cloudflare navigation or external-opener request was observed. That observation does not prove that Cloudflare performed no checks, nor that a genuine verification can complete.

The reporter uses openSUSE Leap 16 with GNOME and reported both RPM and Flatpak. Their exact WebKitGTK version is unknown. The complete openSUSE failure, the reported JavaScript error and a genuine hosted Turnstile solve have not been reproduced. The controlled test establishes the app's routing defect; it is not a full reproduction of Cloudflare's production verification. No login, private conversation or challenge bypass was used.

Cloudflare's [WebView integration guidance](https://developers.cloudflare.com/turnstile/get-started/mobile-implementation/) requires access to its challenge resources and frames. Its [browser support documentation](https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/) also notes limitations for embedded browsers. This release repairs VibeZ's routing; it does not guarantee every hosted challenge or authentication provider will work in every webview environment.

## Packages and verification

The [3.0.8 validation workflow](.github/workflows/v3.0.8-validation.yml) builds all twelve required package formats from one frozen source commit. Publication requires successful dependency audits, frontend/Rust tests, Linux frame-routing regressions, rich-chat and native regressions, installer/update tests, package checks, and macOS signing/notarization. The published release's `SHA256SUMS`, `source-commit.txt` and version-specific proof identify the actual packages and build. No successful 3.0.8 run is asserted here before those gates complete; [3.0.7 proof](tools/release-v3/release-proof-3.0.7.json) remains historical.

Native Linux packages and AppImage require glibc 2.39+ and WebKitGTK 4.1; desktop-area screenshot selection on Linux requires X11. Flatpak uses its declared GNOME runtime. macOS requires version 14 or later, and Windows requires WebView2. Microsoft Store package version is `3.0.8.0`; creating the MSIX is separate from Store submission, certification and delivery.

For the preceding rich-chat measurements and rustls dependency update, see the [3.0.7 notes](https://github.com/lecomputeur/vibez/blob/v3.0.7/V3-RELEASE.md).
