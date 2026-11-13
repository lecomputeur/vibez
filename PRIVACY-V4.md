# Privacy Policy — VibeZ 4

Last updated: 13 November 2026

This policy covers VibeZ 4 (VibeZ V4 Beta, and VibeZ Desktop V4 in the Microsoft Store). VibeZ 3 has its own [privacy policy](PRIVACY.md).

## Overview

VibeZ 4 is an independent, open-source desktop client for Linux, Windows and macOS. It opens the official Mistral website in the operating system's browser engine and can connect folders on your computer to a Mistral project or conversation. VibeZ does not operate its own backend and does not include analytics, advertising trackers or telemetry. VibeZ is not affiliated with Mistral AI.

## Mistral data

Messages, account information, attachments and other information you enter on the Mistral website are processed by Mistral under Mistral's terms and privacy policy. VibeZ does not receive a copy on a Le Computeur server.

## Local folders

You choose which folder, if any, is linked to a Mistral project or conversation. Only that folder is offered to Mistral. When the assistant in that project or conversation uses a VibeZ file tool, VibeZ reads or writes files in that folder on your computer and sends the requested file contents to Mistral as the tool's answer. Changes proposed by the assistant are shown in VibeZ. You can pause or stop a connection at any time; while paused, no file can be read or changed.

## The secure connection

To let Mistral reach the local file server on your computer, VibeZ starts a temporary connection through Cloudflare's free quick-tunnel service while a project is connected. Tool requests from Mistral and their answers, including the file contents the assistant asked for, travel through Cloudflare's network over HTTPS. Each connected project has its own secret address; requests without it are refused. When you pause a project or close VibeZ, VibeZ no longer answers for it. After closing, the tunnel helper may stay ready in the background so the next start can reuse the same address; Stop all connections ends it. Cloudflare processes this traffic under its own policies.

To set the link up, VibeZ adds a connector for your project to your Mistral account, using the Mistral website as you are signed in. You can remove these connectors in Mistral at any time.

## Local data

The embedded browser stores cookies, cache and website data locally, including information needed to retain sign-in. VibeZ stores its settings, linked folders, per-project connection keys and a short history of recent file actions locally in your user profile.

## Diagnostics

The Diagnostics window shows connection details and recent file actions on your own computer. Its report leaves out keys and full addresses and is only shared if you copy and paste it yourself, for example into a GitHub issue.

## Updates and network access

Direct installations check GitHub Releases for updates. Such requests disclose ordinary connection information, including the IP address, to GitHub under its policies. Microsoft Store installations are updated by the Microsoft Store and do not check GitHub. VibeZ requires network access for the Mistral website, the secure connection described above, update checks and links you open.

## Contact and changes

This policy is updated when data handling changes materially. Contact Le Computeur at [info@lecomputeur.nl](mailto:info@lecomputeur.nl) with privacy questions.
