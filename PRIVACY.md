# Privacy Policy

Last updated: 7 October 2026

## Overview

VibeZ 3 is an independent, open-source desktop client for Linux, Windows and macOS. It opens the official Mistral Vibe web application in the operating system's browser engine, using Rust and Tauri for its desktop controls. VibeZ does not operate its own backend and does not include analytics, advertising trackers or telemetry. The archived Electron v2 client is a separate historical application.

## Mistral Vibe data

Messages, account information, attachments and other information you enter in the embedded Mistral service are processed by that service under Mistral's terms and privacy policy. VibeZ does not receive a separate copy on a Le Computeur server. External links can open the normal system browser.

## Local data

The embedded browser stores cookies, cache and website data locally, including information needed to retain sign-in. VibeZ stores desktop settings such as language, zoom, tray behaviour, start-at-login and update-check preferences locally. Native desktop command access belongs only to bundled controls, not arbitrary remote pages or login popups.

## Screenshots and clipboard

The screenshot menu offers the visible VibeZ page, the full loaded page and a user-selected desktop area. Full-page capture cannot include unloaded history. The desktop selector temporarily captures screen pixels to let you choose a rectangle; the resulting PNG contains the selected area. Linux desktop selection requires X11. The system may require screen-capture permission on macOS.

The resulting image can be copied, saved to a user-selected PNG path, or pasted into a Chat or Work draft. The checkbox for immediate paste is enabled by default and can be turned off. VibeZ does not press Send or submit the message. **Adding an attachment may nevertheless upload it to Mistral before the message is sent, according to the website's own behaviour.** Review the selected area before using immediate paste for sensitive information.

On Linux, a compatibility path transfers only VibeZ's own captured PNG to the focused composer when WebKitGTK does not expose the clipboard image. Clipboard ownership is checked so that copying something else restores ordinary paste behaviour. This does not scrape other applications' clipboard contents. Screenshot pixels normally remain in memory until Save; macOS's native interactive capture can use a temporary PNG in a private directory that is removed after capture. Files explicitly saved by the user remain on disk.

VibeZ has no separate screenshot upload server. Global screenshot shortcuts are not enabled in VibeZ 3.0.2. Code workflows can save the PNG in the project rather than attach it to a chat.

## Start at login and tray

When enabled, start-at-login registers VibeZ with the operating system. Tray/menu-bar and hide-on-close preferences are handled locally.

## Updates and network access

Direct installations can check GitHub Releases for updates. Such requests disclose ordinary connection information, including the IP address, to GitHub under its policies. Automatic checking can be disabled in Settings. Download and installation remain user-confirmed. Microsoft Store installations follow Store delivery.

VibeZ requires network access for Mistral Vibe, optional GitHub update checks and user-opened external links. There is no VibeZ backend receiving application or screenshot data.

## Contact and changes

This policy is updated when data handling changes materially. Contact Le Computeur at [info@lecomputeur.nl](mailto:info@lecomputeur.nl) with privacy questions.
