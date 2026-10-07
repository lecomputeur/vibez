# Screenshot test 4 — Mint first, no rollout

A compact 340 × 290 logical-pixel chooser replaces the oversized test-3 window. Three rows: visible page, full loaded page and desktop selection. All inherited native capture modes remain intact.

The visible, checked “Meteen in Vibe plakken” option transfers the captured PNG into the message composer. It never submits the message. Mistral may process/upload an attachment just as with a manual paste. Uncheck to copy/save only.

## Linux paste compatibility

WebKitGTK 2.52.6 explicitly disables native clipboard file access in WebCore DataTransfer::allowsFileAccess. This was reproduced in VibeZ and standalone WebKit: native paste and Ctrl+V arrived but exposed no image files. Changing JavaScript clipboard permission did not fix it. No security settings have been relaxed in VibeZ.

VibeZ tries ordinary native Paste first. Only after receiving a confirmed empty native paste does it pass its own captured PNG as an in-memory File through a clearly identified compatibility ClipboardEvent to the same composer. This compatibility event is not a trusted OS event; native event support is used when available. No clipboard file paths, temporary files or arbitrary file reads are involved.

Actual Ctrl+V and Shift+Insert get this same compatibility handling only while the system clipboard still belongs to a VibeZ screenshot. GTK ownership loss drops that association immediately: replacing the clipboard restores ordinary browser paste and cannot attach the old screenshot. Manual paste never chooses a different editor. Code, disabled editors and authentication pages are excluded. Ambiguous timeouts never trigger automatic duplicate retries.

## Validation and scope

The real browser composer receives image/png files, whose decoded pixels are compared with the capture. Tests distinguish native events from the memory-only compatibility path, preserve draft text and verify no submit occurs. They cover all three captures, actual Ctrl+V, content from another native application, copy-only/save, unavailable composer, Escape/retry and external clipboard replacement at 100% and 200% scale. Offline fixtures are not the maintainer's authenticated Mistral session.

Linux x64 DEB only on the isolated screenshot branch. Main, public releases, website and Partner Center stay unchanged. Package version 3.0.2, visible test 4 label; explicitly reinstall over earlier 3.0.2 tests. Desktop area selection is X11-only in this Mint candidate. The maintainer must test on Mint before any broader rollout.
