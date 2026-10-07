# VibeZ 3.0.2 — screenshot test 3 (Mint/X11 DEB only)

Not a release. Keep main, public download pages, release tags and Partner Center unchanged. Maintainer tests on Mint before any further rollout.

- One ordinary toolbar button opens a separate, light local chooser with three clearly labelled cards and explanations.
- Linux page captures actual WebKitGTK-rendered pixels. No SnapDOM, SVG conversion, proxy, image re-fetch or browser CORS relaxation on this path.
- Visible page and expanded loaded full page restore original layout and scroll position.
- Area selection freezes real desktop pixels, including other applications, using native GTK on Mint/X11, restoring the scope of the Electron v2 feature. Escape or right click cancels.
- Show the actual PNG preview and dimensions, automatic clipboard copy with truthful error reporting, explicit Copy and native Save PNG actions. No automatic message or upload.
- Only trusted local screenshot controls can request capture/copy/save. Remote pages still have no native command capabilities.
- Package stays 3.0.2 with a test 3 identifier in the window/toolbar. Reinstall this specific DEB explicitly when replacing another 3.0.2 build.
- Native Linux regression probes and actual mouse/keyboard chooser-to-PNG tests at normal and HiDPI scale. Synthetic fixtures only, including strict CSP, a canvas, and a second native application outside VibeZ.

Full page captures content that is already loaded, not unavailable/virtualized chat history. Desktop selection on Wayland is not enabled in this Mint/X11 candidate; page capture remains available. Live authenticated Mistral behaviour and the maintainer's actual Mint session still need a test before release. Windows/macOS publication is out of scope.
