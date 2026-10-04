# Preview 0.1.10 language synchronization

Changing the VibeZ preview language now also changes the Mistral website language in the same isolated webview profile.

Implementation:
- Resolve the selected VibeZ language (or OS language when set to System).
- Map it to a locale currently supported by Mistral's web interface.
- Set Mistral's documented NEXT_LOCALE cookie for chat.mistral.ai and vibe.mistral.ai.
- Reload the Vibe webview immediately after a saved language change.
- Reapply the saved language on startup.

No authentication cookies are read, copied or exported.

Mistral supports fewer UI languages than the 34 translated VibeZ shell languages. Unsupported website locales fall back to English while the VibeZ controls remain in the user's selected language.

Manual acceptance:
1. Sign in to Vibe.
2. Change VibeZ language to Nederlands.
3. Confirm both toolbar/settings and the Mistral website become Dutch after reload.
4. Restart VibeZ and confirm Dutch remains.
5. Change to Deutsch and confirm both become German.
6. Choose an unsupported Mistral UI language such as Japanese; VibeZ controls stay Japanese while the Mistral site falls back to English.
