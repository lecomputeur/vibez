# VibeZ Desktop — Microsoft Store package 3.0.3

## Existing product identity — do not create a new Store app

- Product: VibeZ Desktop
- Product ID: 9NR7L2G4MS08
- Identity: LeComputeur.VibeZDesktop
- Publisher: CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95
- Package version: 3.0.3.0, x64
- Application executable: vibez3.exe (Rust/Tauri, not the archived Electron executable)

## Build and validate

Use the all-desktop workflow `.github/workflows/release-approved-303.yml`. It builds the exact frozen source for every platform. The Windows job invokes `desktop/scripts/build-store.ps1`, packs the MSIX with MakeAppx and unpacks it to verify identity, display name and version. The output is `VibeZ-3.0.3-Windows-x64-Store.msix`.

The Store upload package is intentionally unsigned; Microsoft signs delivered Store packages. Use the EXE or MSI for ordinary direct installation. Building the MSIX does not submit or certify the update.

## Submission

Open the existing product in Partner Center, create an update submission, and add the new MSIX under Packages. Retain the existing product identity, pricing and age-rating declarations. Review supported languages and the listing text below, then submit for certification. Do not claim the Store is running 3.0.3 until Partner Center confirms the submission is published.

Retain the product declaration that the app allows purchases without using Microsoft Store commerce when the embedded Mistral service offers its own paid upgrade. VibeZ is independent and is not affiliated with or supported by Mistral AI.

## English update text

VibeZ 3.0.3 improves screenshots with a compact 34-language menu. Paste into Chat and Work drafts without sending the message. In Code, save the screenshot as PNG and share it separately. A sign-in notice appears only when guest sign-in controls are visible; copying and saving remain available. Direct installations gain in-app update downloads with progress and integrity checks. Microsoft Store installations continue to update through the Store. This independent client is not affiliated with Mistral AI.

## Nederlandse updatebeschrijving

VibeZ 3.0.3 verbetert screenshots met een compact menu in 34 talen. Plak in Chat- en Work-concepten zonder het bericht te versturen. In Code sla je de screenshot op als PNG en deel je het bestand apart. Een inlogmelding verschijnt alleen wanneer de inlogknoppen zichtbaar zijn; kopiëren en opslaan blijven beschikbaar. Directe installaties krijgen downloads binnen VibeZ, met voortgang en bestandscontrole. Microsoft Store-installaties blijven via de Store bijwerken. Deze onafhankelijke client is niet verbonden aan Mistral AI.
