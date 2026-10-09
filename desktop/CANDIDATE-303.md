# 3.0.3 test 1 — NOT a public release

Do not change main, live website, 3.0.2 release assets or Partner Center until acceptance.

## Scope
- Fix false screenshot success: delivery of a paste event is not confirmation. Wait for the application to render a new attachment; ignored/rejected transfers preserve the PNG for Copy or Save.
- Windows/macOS can attach through the existing enabled composer image-upload input. Mint keeps the approved native clipboard path. No message submission or bypass of disabled controls/account restrictions.
- Generate the missing check-for-updates permission and test local/remote command isolation.
- Compact translated update dialog, package choice, direct download, progress/cancel, size and SHA-256 verification, explicit Open installer or Show file. Store packages remain on Store delivery.
- Never install silently, elevate privileges, force-close an app or discard a draft. Normal Windows/Apple security prompts remain in place.

## Acceptance and test limits
The public Mistral probe encountered human verification, not a usable guest composer. This is NOT a passing live Mistral test. An actual attachment in an authenticated Windows/macOS session remains to be confirmed. Offline native browser tests are labelled as such, including rejection/ignore/delay cases and pixel comparisons.

One manual installation is needed to replace 3.0.2; its old code cannot receive the new downloader retroactively. The new dialog checks automatically and downloads after consent, then the user opens the normal installer. Checksums are received over GitHub HTTPS, not an independent application signature. No claim of faultlessness or fully automatic installation.
