# VibeZ 3 release gate

All required packaging jobs must succeed for one exact source commit. Native integration tests and dependency advisory audit are required. macOS deliverables require Developer ID signing and accepted notarization. Store MSIX creation is not Store submission. Failed or missing platforms block stable all-platform publication.

## 3.0.7 validation and publication

Use `.github/workflows/v3.0.7-validation.yml` for the frozen 3.0.7 source. It is validation-only and has read-only repository permissions. It must produce AppImage, DEB, RPM, Arch/Pacman and Flatpak for Linux; EXE, MSI and Store MSIX for Windows; and signed/notarized DMG and ZIP for both Mac architectures, all from the same frozen commit. Publication must use the assets and proof from that successful run.

- Check the production identity, all version manifests/locks and installer hooks with `python3 tools/release-v3/check-inputs.py --version 3.0.7` from the repository root.
- Require the Linux rich-chat regression harness against the built ordinary `vibez3` binary, alongside existing native window, screenshot, paste, update and installed-package tests. Synthetic tests must cover streaming, resize recovery, Find and simultaneous invalidations without touching a private chat or requiring login.
- Check the current anonymous Mistral page separately. Public-source confirmation of assistant wrappers and synthetic messages under the public page provide selector evidence, but do not establish a genuine conversation's full runtime structure, streaming or performance. Report that coverage gap; never label it a successful live-chat performance test or proof that the original private-chat report is resolved.
- Preserve normal live startup, app/profile identity, published-update behavior and the selected code-header appearance. Linux-specific rendering/GTK changes must not alter Windows or macOS behavior.
- Verify actual 3.0.7 assets and `source-commit.txt` with freshly generated `SHA256SUMS` and version-specific release proof. Keep 3.0.6 proof/signing records historical. No successful 3.0.7 proof exists until its exact build and required gates succeed.
- Release documentation may prepare versioned download links, but those links must resolve to the corresponding published assets before release availability is announced. Store availability requires confirmation from Partner Center. Publication is separate from validation; this workflow performs none.

The rich-chat workflow runs `desktop/test-tools/rich-chat/run.py` sequentially with modes `lifecycle`, `resize`, `wheel --baseline`, `wheel`, and `fullscreen --sections 2`. The launcher creates fresh profiles and a private session bus; CI supplies Xvfb and Openbox. The default rich fixture remains 40 replies with 16 sections each; only the fullscreen visual case uses two sections per reply to bound memory. Each case writes its raw evidence under `desktop/artifacts/rich/`. CI software-rendering measurements must be identified as such and cannot be presented as universal hardware performance results.
