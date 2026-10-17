VibeZ 3.0.7 improves Linux scrolling and window resizing in long, richly formatted chats.

- Reduce offscreen rendering work for recognized assistant replies, with bounded height updates during resizing. Streaming, Find and page screenshots expand content when needed.
- Fix the transient 1×1 Linux webview size during resizing and restore rendering reliably after Find and screenshot operations.
- Show **VibeZ V3.0.7** in window titles on every platform. Windows and macOS rendering behavior is unchanged.
- Update the shared TLS dependency to **rustls 0.23.46** for its [upstream security fixes](https://github.com/rustls/rustls/releases/tag/v/0.23.46).

The Linux improvement was tested with large synthetic chats without login or private conversation data. The original reported private conversation was not reproduced, and CPU usage still depends on the content and system. Existing settings, profiles and app identity are retained.

See [the full notes and measured limits](https://github.com/lecomputeur/vibez/blob/v3.0.7/V3-RELEASE.md). Verify downloads with `SHA256SUMS`; `source-commit.txt` identifies their source. The MSIX is for Microsoft Store submission; creating it does not mean the Store update has been certified or published.
