# VibeZ Desktop — Microsoft Store candidate package 3.0.7

## Existing product identity — do not create a new Store app

- Product: VibeZ Desktop
- Product ID: 9NR7L2G4MS08
- Identity: LeComputeur.VibeZDesktop
- Publisher: CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95
- Candidate package version: 3.0.7.0, x64 (not submitted or certified)
- Application executable: vibez3.exe (Rust/Tauri, not the archived Electron executable)

## Build and validate

Use the validation-only all-desktop workflow `.github/workflows/v3.0.7-validation.yml`. It builds the exact frozen source for every platform. The Windows job invokes `desktop/scripts/build-store.ps1`, packs the MSIX with MakeAppx and unpacks it to verify identity, display name and version. The expected output is `VibeZ-3.0.7-Windows-x64-Store.msix`; this document does not certify that it has been built.

The Store upload package is intentionally unsigned; Microsoft signs delivered Store packages. Use the EXE or MSI for ordinary direct installation. Building the MSIX does not submit or certify the update.

## Submission

After the package passes its validation gates and a submission is authorized, open the existing product in Partner Center, create an update submission, and add the new MSIX under Packages. Retain the existing product identity, pricing and age-rating declarations. Review supported languages and the listing text below, then submit for certification. Do not claim the Store is running 3.0.7 until Partner Center confirms the submission is published.

Retain the product declaration that the app allows purchases without using Microsoft Store commerce when the embedded Mistral service offers its own paid upgrade. VibeZ is independent and is not affiliated with or supported by Mistral AI.

## English update text

VibeZ 3.0.7 updates the version shown in the app's window titles. Existing Windows behavior, settings and profiles are retained. Microsoft Store installations update through the Store. The Linux rendering improvements in this release do not change Windows rendering. This independent client is not affiliated with Mistral AI.

## Nederlandse updatebeschrijving

VibeZ 3.0.7 werkt de versie in de titelbalken bij. De bestaande Windows-werking, instellingen en profielen blijven behouden. Microsoft Store-installaties worden via de Store bijgewerkt. De Linux-renderverbeteringen in deze versie veranderen de Windows-rendering niet. Deze onafhankelijke client is niet verbonden aan Mistral AI.
