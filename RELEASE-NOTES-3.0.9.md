# VibeZ 3.0.9 — Linux Canvas and verification navigation

Release candidate; stable publication is blocked by repeated Apple CloudKit ticket-validation failures on Intel Mac. Ten package formats passed, including Windows Store MSIX 3.0.9.0. No stable 3.0.9 or Store publication was performed. See [exact build/publication status](RELEASE-STATUS-3.0.9.md) and the [validation run](https://github.com/lecomputeur/vibez/actions/runs/39630746331).

## Changes

- Linux distinguishes embedded documents from main-window navigation using WebKit navigation and response metadata. Canvas/chart previews load inside the app instead of opening blank external tabs.
- Automatic unknown popups are blocked; deliberate external hyperlinks retain browser delivery. Authentication windows have separate navigation state, including Microsoft sign-in redirects.
- Production app identity, profiles and installer behavior are retained. This promotes the routing source tested as 3.0.9+test.2 and in the isolated Canvas Test 3.0.9+test.3, without promoting the test app's separate identity or disabled updates.
- Update rustls-webpki to 0.103.16 and webpki-roots to 1.0.10 for the newly published certificate-trust advisories RUSTSEC-2026-0382 and RUSTSEC-2026-0381.
- Windows/macOS receive version 3.0.9 and window title VibeZ V3.0.9. The routing hooks are Linux-only.

## Validation and limits

The openSUSE Leap 16/GNOME reporter confirmed successful Cloudflare verification and Mistral loading in the test.3 Flatpak on 21 October. RPM was not tested by that reporter. The openSUSE Tumbleweed reporter confirmed fresh table/chart previews and no blank Firefox tabs on 19 October.

**The original heavy conversation still consumes 100% CPU at idle and has typing/scrolling stutter.** Issue #42's remaining workload is tracked in #49. Preview routing is improved; the original performance problem is not resolved. Do not close or advertise it as fixed. No eager scanning, iframe suspension or Canvas version lifecycle change is included.

Sources: https://github.com/lecomputeur/vibez/issues/49#issuecomment-6273090635 and https://github.com/lecomputeur/vibez/issues/45#issuecomment-6315695230.

## Packaging and delivery

Required: Linux x64 AppImage, DEB, RPM, Arch/Pacman and Flatpak; Windows x64 EXE, MSI and Store MSIX 3.0.9.0; signed/notarized macOS x64 and arm64 DMG/ZIP. Every package must use the same frozen source commit and pass package, native smoke and advisory checks.

Linux native/AppImage require glibc 2.39+ and WebKitGTK 4.1; Flatpak uses GNOME Platform 50. Windows requires WebView2; the MSIX targets Windows 10 build 17763+. macOS requires 14+. Linux desktop selection requires X11; Wayland/hybrid GPU coverage is limited.

MSIX creation is separate from Partner Center submission. No Store submission is authorized without confirmed access and review of existing submissions. See MICROSOFT-STORE-3.0.9.md.

## Rollback

Keep v3.0.8 assets, checksums and tag unchanged. Before installing, close the app and back up the existing app profile using the operating system's normal backup tools. Reinstall the matching 3.0.8 package if required; never delete or migrate profiles to roll back. Do not overwrite the isolated Canvas Test installation. Store rollback requires reviewing the current Partner Center submission and version ordering; never replace an existing submission blindly.

## Moving from test builds

The isolated Canvas Test remains a separate app/profile with updates disabled. Install the ordinary package separately when the stable release is cleared. For an installed ordinary 3.0.9+test.2, use the stable installer directly: build metadata has equal SemVer precedence, while DEB ordering treats 3.0.9 as lower. This is a version-ordering issue, not older release code. Do not delete or migrate profiles.
