# VibeZ 3.0.9 — Linux Canvas and verification navigation

> **Installed test.2 or test.3?** Uninstall the test application first, keep its saved data, then install the normal 3.0.9 release. Follow the [Linux installation steps](https://lecomputeur.github.io/vibez/linux.html#test-build-upgrade).

The [verified 3.0.9 build](https://github.com/lecomputeur/vibez/actions/runs/39643498884) passed all nine required platform/security jobs, including native regressions, advisory checks, all twelve packages and Developer ID signing, Apple notarization and stapled-ticket validation for both Mac architectures. Both Mac jobs also verified the native architecture and macOS 14 deployment minimum in Info.plist and Mach-O. Frozen source: `64dbf09e8a24b1d1859b3571cd3b83b87a39f14c`. The [release proof](tools/release-v3/release-proof-3.0.9.json) records the source and run. The files are validated for publication; the GitHub release asset list records public availability. Windows MSIX version: **3.0.9.0**. Microsoft Store submission and certification remain separate. The original heavy-conversation high-CPU issue remains open; see [release notes](RELEASE-NOTES-3.0.9.md). See [build/publication status](RELEASE-STATUS-3.0.9.md).

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

Verified packages: Linux x64 AppImage, DEB, RPM, Arch/Pacman and Flatpak; Windows x64 EXE, MSI and Store MSIX 3.0.9.0; signed/notarized macOS x64 and arm64 DMG/ZIP. All twelve packages use the same frozen source commit and passed package, native smoke and advisory checks.

Linux native/AppImage require glibc 2.39+ and WebKitGTK 4.1; Flatpak uses GNOME Platform 50. Windows requires WebView2; the MSIX targets Windows 10 build 17763+. macOS requires 14+. Linux desktop selection requires X11; Wayland/hybrid GPU coverage is limited.

MSIX creation is separate from Partner Center submission. No Store submission is authorized without confirmed access and review of existing submissions. See MICROSOFT-STORE-3.0.9.md.

## Rollback

Keep v3.0.8 assets, checksums and tag unchanged. Before installing, close the app and back up the existing app profile using the operating system's normal backup tools. Reinstall the matching 3.0.8 package if required; never delete or migrate profiles to roll back. Do not overwrite the isolated Canvas Test installation. Store rollback requires reviewing the current Partner Center submission and version ordering; never replace an existing submission blindly.

## Moving from test builds

Save any drafts and close VibeZ completely, including its tray/background instance. Uninstall the test application before installing the normal 3.0.9 release, while keeping its saved data.

- **Ordinary 3.0.9+test.2:** the DEB package is named `vibe-z-3`. Remove the test application package while preserving its profile and settings in your home directory; do not delete the saved data. Then install the normal 3.0.9 package.
- **Isolated Canvas Test 3.0.9+test.3:** remove the Canvas Test application only and keep its separate profile. For a Flatpak installation, do not use `--delete-data`. Canvas Test data is not automatically copied or migrated into the normal VibeZ profile.

Do not wait for an automatic update notification: these test builds and the normal release share the base version 3.0.9, and the isolated Canvas Test has update checks disabled. Build metadata has equal SemVer precedence; DEB ordering also treats 3.0.9 as lower than 3.0.9+test.2. Follow the [Linux installation steps](https://lecomputeur.github.io/vibez/linux.html#test-build-upgrade) to remove the test application and install the normal package without deleting saved data.
