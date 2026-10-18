# VibeZ Desktop — Microsoft Store update 3.0.8

## Existing product identity — do not create a new Store app

- Product: VibeZ Desktop
- Product ID: 9NR7L2G4MS08
- Identity: LeComputeur.VibeZDesktop
- Publisher: CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95
- Package version: 3.0.8.0, x64
- Application executable: vibez3.exe (Rust/Tauri, not the archived Electron executable)

## Build and validate

Use the validation-only all-desktop workflow `.github/workflows/v3.0.8-validation.yml`. It builds the exact frozen source for every platform. The Windows job invokes `desktop/scripts/build-store.ps1`, packs the MSIX with MakeAppx and unpacks it to verify identity, display name and version. The output is `VibeZ-3.0.8-Windows-x64-Store.msix`. Require a successful Windows job and package validation before using that output; this document is not a build or certification record.

Validate the actual 3.0.8.0 package for the identity, publisher, x64 architecture and `vibez3.exe` entry point. A successful previous-version build is not proof for this update. Record the new validation run and checksums only after they exist.

The Store upload package is intentionally unsigned; Microsoft signs delivered Store packages. Use the EXE or MSI for ordinary direct installation. Building the MSIX does not submit or certify the update.

## Submission

After the package passes its validation gates, open the existing product in Partner Center, create an update submission, and add the new MSIX under Packages. Retain the existing product identity, pricing and age-rating declarations. Review supported languages and the listing text below, then submit for certification when Store submission is authorized. GitHub publication and Store delivery are separate: do not claim the Store is running 3.0.8 until Partner Center confirms the submission is published.

Retain the product declaration that the app allows purchases without using Microsoft Store commerce when the embedded Mistral service offers its own paid upgrade. VibeZ is independent and is not affiliated with or supported by Mistral AI.

## English update text

VibeZ 3.0.8 updates the app version and the version shown in its window titles. Windows navigation, rendering, settings and profiles are unchanged. The Cloudflare navigation fix in this release applies only to Linux. Microsoft Store installations update through the Store. This independent client is not affiliated with Mistral AI.

## Nederlandse updatebeschrijving

VibeZ 3.0.8 werkt de appversie en de versie in de titelbalken bij. Navigatie, weergave, instellingen en profielen op Windows blijven ongewijzigd. De Cloudflare-navigatiereparatie in deze versie geldt alleen voor Linux. Microsoft Store-installaties worden via de Store bijgewerkt. Deze onafhankelijke client is niet verbonden aan Mistral AI.
