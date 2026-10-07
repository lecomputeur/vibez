# VibeZ 3.0.2 — Compact screenshots, direct paste, correct monitor

VibeZ 3 is the independent Mistral Vibe desktop client rebuilt in Rust with Tauri.

## New in 3.0.2

The compact screenshot chooser offers Visible page, Full page and Selection. It opens beside VibeZ on the same monitor and follows the selected interface language in all 34 supported languages. Explanatory paragraphs have been removed from the menu.

Screenshots can be pasted directly into the current Chat or Work draft, copied, or saved as PNG. Existing draft text is preserved. VibeZ never sends your message automatically. Linux includes a memory-only compatibility fix for WebKitGTK image pasting and ownership-aware Ctrl+V handling.

Page screenshots use native browser pixels instead of reconstructing website images. Full page captures loaded content, including expanded scroll areas; it cannot capture unloaded or virtualized history. Desktop area selection uses native OS capture. Linux desktop selection currently requires X11; macOS may request Screen Recording permission. Code workflows can save the PNG into the project rather than attach it to a chat.

## Downloads

Linux x64: AppImage, DEB, RPM, Arch/Pacman and Flatpak. Windows x64: EXE installer, MSI and Microsoft Store MSIX. macOS Intel and Apple Silicon: signed and notarized DMG and ZIP packages. All required packages must pass the release gate before publication.

Linux: Ubuntu 24.04 / Linux Mint 22 or compatible glibc 2.39+ systems with WebKitGTK 4.1. macOS: 14 or later. Windows: Windows 10/11 with WebView2.

The Mint build was approved by the maintainer after screenshot, paste, small-menu and two-monitor testing. Automated checks additionally exercise native page capture, actual image receipt, draft preservation, cancellation and package integrity. A successful build is not a claim of manual testing of every hardware combination.

## Updating

Quit VibeZ completely before replacing a previous installation. Reinstall explicitly when replacing a 3.0.2 Mint test package; the production title no longer includes a test marker. Direct installations use GitHub release update checks. Store delivery is separate: the MSIX is an upload package, not evidence of Microsoft submission or approval.

Electron v2 and the separate Tauri preview remain archived and unchanged. Historical Electron update feeds continue to reference their original packages, never an incompatible Tauri executable.
