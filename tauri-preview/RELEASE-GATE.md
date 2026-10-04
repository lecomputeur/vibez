# Public release gate — Tauri 0.1.16 candidate

Publication is conditional on no demonstrable issues. Do not publish all-platform stable releases merely because the Linux candidate builds.

## Candidate scope

Linux amd64 DEB and Windows x64 NSIS/EXE/MSIX are the configured build targets. Electron 2.x and its existing Store product are outside this change. The Tauri source has Linux/Windows platform modules but no macOS implementation or workflow, and no validated Tauri AppImage/RPM/Arch/Flatpak deliverables.

## Known blockers / missing release evidence

- Windows `get_state` still returns fixed history/loading values `(true, true, false)` instead of actual WebView2 state.
- Windows website language preference and confirmation functions are still no-ops; the Linux native-language probe must not be presented as Windows validation.
- Windows update discovery has weaker artifact/commit validation and conflates no matching downloadable artifact with being up to date. This remains an audit item.
- Build-specific Cargo/npm lockfiles are archived but not committed; reproducible locking and a dedicated Rust advisory audit remain open.
- Native CI covers X11/Openbox at integer scale factors; it is not live OAuth, Wayland/fractional scaling or installed desktop/tray validation.
- The Linux cold-start fix requires existing-profile acceptance on the reporting user's machine. Automated fresh-profile and recovery-policy tests supplement, not replace, this.

No public stable release, automatic update promotion, replacement of Electron or Store upload is authorized by a failed or incomplete gate. Keep this candidate downloadable for testing and report the remaining blockers explicitly.
