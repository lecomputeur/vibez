# VibeZ 3.0.2 screenshot candidate — not yet a public release

The Screenshot control offers Full page, Visible page and Selection. These three modes capture the page loaded **inside VibeZ**, not a page in another program. Full page captures loaded document content, including substantial nested scroll areas. It cannot fetch unloaded chat history or defeat protected/cross-origin media restrictions.

The chooser is a native select popup. A CSS dropdown below the toolbar would be clipped by its separate 54px webview; this implementation does not resize that webview or move the Vibe page.

Capture uses the bundled, version-locked SnapDOM library, without a third-party screenshot service or CORS proxy. The produced PNG is checked for file and pixel limits before copying to the system clipboard. No automatic message sending or upload is performed. Escape cancels selection. Cancellation, errors and timeouts restore temporary page changes and leave the button reusable. Large pages produce a clear error rather than silent truncation.

Validation requires actual PNG pixel markers, viewport/crop dimensions, bottom-of-page and sidebar presence, page restoration, clipboard round-trips, and cancellation on WebKitGTK, WebView2 and WKWebView. Test artifacts contain synthetic offline content only. Passing these tests does not establish that every authenticated Mistral page, CSS feature, virtualized chat or desktop configuration works.

Do not describe this candidate as released or replace Store 3.0.1 until validation and a real-user screenshot test have succeeded.
