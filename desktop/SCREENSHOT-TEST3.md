# VibeZ 3.0.2 — screenshot test 3 (Linux DEB only)

Not a release. Keep main, public download pages and Partner Center unchanged.

- One ordinary toolbar button opens a separate, local 580 × 620 chooser with three clearly labelled cards and explanations.
- Linux captures actual WebKitGTK-rendered pixels. No SnapDOM, SVG conversion, proxy, image re-fetch or browser CORS relaxation on this path.
- Visible page, expanded loaded full page and rectangular selection, with page restoration and Escape cancellation.
- Show the actual PNG preview and dimensions, automatic clipboard copy with truthful error reporting, explicit Copy and native Save PNG actions.
- Only trusted local screenshot controls can request capture/copy/save. Remote pages still have no native command capabilities.
- Build stays version 3.0.2 with an explicit test 3 identifier in the window/toolbar. Reinstall the test DEB explicitly when replacing another 3.0.2 build.
- Native Linux regression probes and actual mouse-driven chooser-to-PNG tests at normal and HiDPI display scale. Synthetic fixtures only, including an additional strict CSP and a canvas.

Full page captures content that is already loaded, not unavailable or virtualized chat history. Live authenticated Mistral behaviour still needs the maintainer's own test. Windows/macOS publication is out of scope; their existing engine remains unchanged.
