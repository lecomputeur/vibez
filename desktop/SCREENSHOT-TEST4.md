# Screenshot test 4 — Mint first, no rollout

This candidate replaces the oversized test-3 chooser with a 340 × 290 logical-pixel window. Three compact rows: visible page, full loaded page and desktop selection. All inherited native capture modes remain intact.

Test 3 copied the PNG but omitted the v2 focus-and-paste step. Test 4 restores it through WebKit's native Paste command. The checked, visible 'Meteen in Vibe plakken' option pastes into the composer after capture. It never submits a message; Mistral may process/upload an attachment just as with a manual paste. Uncheck to copy/save only. Clipboard is still available for Ctrl+V.

Actual image-paste receipt is verified, not inferred from a successful clipboard write. Missing/disabled composers, Code and authentication pages do not receive automatic pastes. The captured PNG stays available in a compact fallback with Copy, Save and an explicit Paste action. No automatic duplicate paste retries.

Validation uses a real WebKit editor receiving trusted clipboard PNG files, comparing their decoded pixels with the captured images and verifying the draft stays intact and no submit occurs. It covers each capture mode, manual Ctrl+V, desktop content outside VibeZ, copy-only, Save, unavailable composer, Escape and retry at 100% and 200% scale. Offline synthetic content, not the maintainer's authenticated Mistral session.

Build only Linux x64 DEB from this isolated branch; main, release tags, website and Partner Center unchanged. Package version 3.0.2, visible test 4 label. Reinstall explicitly over earlier 3.0.2 test builds. Desktop area selection is X11-only in this Mint candidate. Maintainer must test on Mint before any broader rollout.
