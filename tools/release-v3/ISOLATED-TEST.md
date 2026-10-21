# Isolated Linux test packages (issues #49 and #45)

The normal desktop source retains the production app identity. Do not distribute
its ordinary DEB/RPM as a side-by-side test. This generator copies that source
into a new directory, renames the app/package/binary/profile identity, removes
installer hooks, and disables both manual and scheduled updates and autostart.

```sh
python3 tools/release-v3/prepare-isolated-test.py --source desktop --output /tmp/vibez-isolated
cd /tmp/vibez-isolated/source/desktop
npm ci
npm run build -- --bundles deb,rpm
```

The test app is **VibeZ Canvas Test**, identifier
`nl.lecomputeur.vibez3.CanvasTest`, executable `vibez3-canvas-test`, native package
`vibe-z-canvas-test`. No normal VibeZ launcher, process, or profile is migrated.
Fresh sign-in is intentional. Updates and autostart remain disabled even when
the corresponding settings are requested.

`build-isolated-test-flatpak.py` reuses the libraries/licenses and GNOME 50 runtime
of the checksum-pinned published 3.0.8 Flatpak. It replaces the application binary
and exports with the independent test identity. It never installs or starts an
app. Prepare the original bundle checkout in a private OSTree repository:

```sh
ostree --repo=/tmp/vibez-base-repo init --mode=archive-z2
flatpak build-import-bundle /tmp/vibez-base-repo VibeZ-3.0.8-Linux-x64.flatpak
ostree --repo=/tmp/vibez-base-repo checkout 39aac7756b1be2ffe5d528aeed69315045f72898cc7ebdbf29e8dec7f4f115b6 /tmp/vibez-base-checkout
python3 tools/release-v3/build-isolated-test-flatpak.py --base-bundle VibeZ-3.0.8-Linux-x64.flatpak --base-checkout /tmp/vibez-base-checkout --binary /path/to/extracted-deb/usr/bin/vibez3-canvas-test --binary-sha256 SHA256 --work /tmp/vibez-test-flatpak --build
```

Use the executable extracted from the built DEB: Tauri adjusts bundle markers
between packaging formats. Record package and executable checksums separately.
The native regression runners in `desktop/test-tools/canvas/` accept this binary.
Verify package file ownership, no installer scripts/conflicts/obsoletes, separate
DBus owners/profiles, and Flatpak metadata/exports before publication.
