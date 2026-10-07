# VibeZ 3.0.2 — Mint test 5

Test candidate only. Do not merge to main, tag, publish downloads, or submit to Partner Center before the maintainer approves testing on Mint.

- Smaller screenshot chooser: 280 × 200 logical pixels on GTK (requests 280 × 184; GTK enforces a 200-pixel minimum). Test 4 was 340 × 290.
- Three short option labels and the automatic-paste checkbox. No explanations below the options or checkbox.
- Screenshot-menu text uses the same 34 bundled language selections as the toolbar. System follows the OS locale; an explicit language overrides it. An already open menu also refreshes its language without changing the checkbox or result.
- Native Save labels follow the selected language too. Unexpected low-level native errors may still contain untranslated technical details.
- Screenshot capture, automatic paste, Ctrl+V compatibility, clipboard ownership and message-sending behaviour are unchanged from test 4. The full native screenshot/paste regression is rerun at 100% and 200% scale.
- Version stays 3.0.2, now identified as test 5. Installing over an earlier 3.0.2 test requires an explicit reinstall.

The automated runtime is Ubuntu 24.04/X11, not the maintainer's Mint/Mistral session. Desktop selection remains X11-only. Full page captures loaded content, not unloaded or virtualized history. No Windows/macOS/Store rollout is part of this change.
