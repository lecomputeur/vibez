VibeZ 3.0.8 fixes Linux routing of embedded Cloudflare verification frames.

- Keep required Cloudflare/Turnstile frame requests inside the app instead of opening them as external browser links. Ordinary external links retain their normal behavior.
- Apply the routing fix to all five Linux package formats, retaining the rich-chat scrolling and resize improvements from 3.0.7.
- Show **VibeZ V3.0.8** in window titles on every platform. Windows and macOS receive the version/title update only; their navigation and rendering behavior is unchanged.

The routing defect was reproduced with controlled synthetic frames in the unchanged published Linux executable. A genuine Turnstile solve and the complete reported openSUSE failure remain unverified. No login, private conversation or challenge bypass was used. See [the full notes and limits](https://github.com/lecomputeur/vibez/blob/v3.0.8/V3-RELEASE.md).

Verify downloads with `SHA256SUMS`; `source-commit.txt` identifies their source. The MSIX is for Microsoft Store submission; creating it does not mean the Store update has been certified or published.
