# VibeZ 3.0.2 screenshots

Production source promoted from maintainer-approved Mint test 6.

The compact chooser has three labels (Visible page, Full page, Selection) and the immediate-paste checkbox, translated in all 34 UI languages. It opens on VibeZ's monitor; manual repositioning remains possible.

Native WebKitGTK, WebView2 and WKWebView snapshots capture rendered page pixels. Full page expands loaded scroll areas and restores the original layout; unloaded or virtualized history is not available. macOS joins native viewport captures to include the loaded bottom of the document. Desktop selection uses native OS capture; Linux currently requires X11 and macOS may request Screen Recording permission.

Copy, Save PNG and immediate paste are separate user actions. Immediate paste preserves the draft and never presses Send. Attaching an image may cause the embedded Mistral service to upload it before a message is sent. Linux's own-PNG memory bridge repairs WebKitGTK image-paste limitations without giving remote pages native commands or arbitrary clipboard access.

All formats are built from one committed source with locked dependencies. Native tests check actual pixels, received PNGs, draft preservation and cancellation. The maintainer has tested Mint; automated Windows/macOS tests are not a claim of manual testing on every computer.
