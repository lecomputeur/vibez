# Icon regression: 3.0.0

- Install the built DEB in the disposable Linux runner, not just extract it.
- The real desktop entry must resolve to an existing pixmap with the source PNG bytes.
- Start offline using the installed desktop command with a clean preview profile, then twice with the same profile.
- Start once directly by executable; read actual X11 metadata after mapping and again after a delay.
- Both WM_CLASS strings and _GTK_APPLICATION_ID must equal the installed desktop ID.
- _NET_WM_ICON must contain the expected embedded 128px PNG pixels, not merely a nonempty property.
- A D-Bus StatusNotifier test host must receive the tray registration and read a valid matching image from the app's private cache directory, including when the host starts after the app.
- Existing 100%/200% layout and language regression tests must remain green.
- Windows build remains separate; no Electron or production Store changes.
