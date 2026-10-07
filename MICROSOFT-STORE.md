# VibeZ Desktop — Microsoft Store package 3.0.2

## Existing product identity — do not create a new Store app

- Product: VibeZ Desktop
- Product ID: 9NR7L2G4MS08
- Identity: LeComputeur.VibeZDesktop
- Publisher: CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95
- Package version: 3.0.2.0, x64
- Application executable: vibez3.exe (Rust/Tauri, not the archived Electron executable)

## Build and validate

Use the all-desktop workflow `.github/workflows/vibez-v3.yml`. It builds the exact frozen source for every platform. The Windows job invokes `desktop/scripts/build-store.ps1`, packs the MSIX with MakeAppx and unpacks it to verify identity, display name and version. The output is `VibeZ-3.0.2-Windows-x64-Store.msix`.

The Store upload package is intentionally unsigned; Microsoft signs delivered Store packages. Use the EXE or MSI for ordinary direct installation. Building the MSIX does not submit or certify the update.

## Submission

Open the existing product in Partner Center, create an update submission, and add the new MSIX under Packages. Retain the existing product identity, pricing and age-rating declarations. Review supported languages and the listing text below, then submit for certification. Do not claim the Store is running 3.0.2 until Partner Center confirms the submission is published.

Retain the product declaration that the app allows purchases without using Microsoft Store commerce when the embedded Mistral service offers its own paid upgrade. VibeZ is independent and is not affiliated with or supported by Mistral AI.

## English update text

VibeZ 3.0.2 adds a compact, translated screenshot menu with Visible page, Full page and Selection. Copy, save PNG or paste directly into a Chat or Work draft without sending the message. Screenshot controls open on the same monitor as VibeZ. Full-page capture includes loaded content, not unloaded history. This independent desktop client opens the official Mistral Vibe service; a Mistral account and service-specific paid plan may be required for some features.

## Nederlandse updatebeschrijving

VibeZ 3.0.2 heeft een compact, vertaald screenshotmenu met Zichtbare pagina, Hele pagina en Selectie. Kopieer de opname, sla hem op als PNG of plak hem meteen in een Chat- of Work-concept, zonder het bericht te versturen. Het screenshotvenster opent op hetzelfde scherm als VibeZ. Hele pagina omvat geladen inhoud, niet nog niet geladen geschiedenis. Deze onafhankelijke desktopclient opent de officiële Mistral Vibe-dienst; voor sommige functies kan een Mistral-account of betaald abonnement nodig zijn.
