# VibeZ Desktop V4 — first Partner Center submission (Beta 1)

New product **VibeZ Desktop V4**, Store ID **9NS3RGF0ZMZW**, next to the separate product VibeZ Desktop (9NR7L2G4MS08, VibeZ 3.0.9). Nothing about VibeZ Desktop 3.0.9 changes.

- Upload file: `VibeZ-4.0.0-beta.1-Windows-x64-Store.msix`, built and checked in the frozen-source Windows build of [v4.0.0-beta.1](https://github.com/lecomputeur/vibez/releases/tag/v4.0.0-beta.1). It is not a release asset.
- SHA-256: `bda0ae812c5743c1968fe88c77bde3348066225a36a0172ee58aebd3eb8e2e64`
- Identity `LeComputeur.VibezDesktopV4`, publisher `CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95`, version **4.0.101.0** (Beta N is 4.0.(100+N)), x64, display name `VibeZ Desktop V4`.
- Unsigned upload package: the Store signs it. A Store installation leaves updates to the Store.

## Submission

1. Apps and games → VibeZ Desktop V4 → Start submission.
2. **Pricing and availability:** free, all markets. Visibility: public (or hidden first, to test the Store install yourself).
3. **Properties:** category Developer tools. Privacy policy URL: https://github.com/lecomputeur/vibez/blob/main/PRIVACY-V4.md. Support: https://github.com/lecomputeur/vibez/issues. Website: https://lecomputeur.github.io/vibez/ . Declarations: the app depends on a Mistral account; purchases on the Mistral website are outside Microsoft commerce.
4. **Age ratings:** no violence, sexual content, gambling or drugs; users can communicate with an AI service and share content (the Mistral website). Location is not shared.
5. **Packages:** upload the MSIX above; check identity, version 4.0.101.0 and x64 after validation.
6. **Store listing (English):** texts below; at least one screenshot (1366×768 or larger) of VibeZ with the Files or Advanced tab open.
7. **Submission options → restricted capabilities:** paste the runFullTrust note below.
8. Submit for certification and record the submission ID.

## Store listing — description

VibeZ Desktop V4 is an independent desktop client for Mistral. It opens the official Mistral website in its own window and lets you connect a folder on your computer to a Mistral project or conversation, so Mistral Work and Code can read and write the files you choose.

• Keep your existing Mistral conversations, projects and sign-in.
• Link one local folder per project or conversation; nothing else on your computer is offered.
• See the files and the changes the assistant made in the side panel.
• Pause or stop a connection at any time.
• A Diagnostics window with a copyable report for bug reports, without keys.
• Available in 33 languages.

This is the open Beta of VibeZ 4. It installs next to VibeZ Desktop (VibeZ 3) and keeps its own settings. VibeZ is open source and not affiliated with Mistral AI. A Mistral account is required.

## Short description

Mistral on your desktop, connected to the project folders you choose.

## What's new in this version

The first Store release of VibeZ 4, the open Beta: Mistral Work and Code with your local project folders, a Files and an Advanced tab, a Diagnostics window and 33 languages. Store installations are updated through the Microsoft Store.

## Restricted capability: runFullTrust

VibeZ Desktop V4 is a desktop application (Tauri/WebView2) that needs full trust to run its bundled local components: a local file server that serves only the folder the user linked, a bundled Python runtime for that server, and Cloudflare's tunnel helper that lets Mistral reach the server over HTTPS while the user keeps a project connected. These components cannot run in an AppContainer. The app does not install drivers or services and does not update itself in the Store version.
