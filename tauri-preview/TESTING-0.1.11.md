# Preview 0.1.11 language acceptance

Reported live issues in 0.1.10:
- System language could resolve to English on a Dutch Windows UI because the preview used the regional locale instead of the Windows display language.
- Changing VibeZ language did not change the already-loaded Mistral site; the site stayed Dutch.

Changes:
- Windows System uses GetUserDefaultUILanguage + LCIDToLocaleName.
- System mode is shown as AUTO plus its resolved code (for example AUTO·NL).
- Before writing NEXT_LOCALE, stale variants for chat/vibe hosts are removed.
- The preference is written in the isolated webview cookie store and, when already on a Mistral page, through document.cookie as the site itself would.
- Saving a changed language performs a full navigation to the current Mistral URL rather than a simple reload.
- Startup only preloads the cookie and does not race the initial webview navigation.
- Diagnostics report only the requested locale, NEXT_LOCALE value, html lang and host; auth cookies/tokens are never exposed.

Manual Windows acceptance:
1. With Windows display language Dutch and VibeZ language System, confirm shell shows AUTO·NL and Dutch labels.
2. While signed in, switch to English. Confirm both VibeZ and the Mistral page become English without signing out.
3. Switch back to System. Confirm both return to Dutch.
4. Fully quit and reopen. Confirm System/Dutch remains.
5. If Mistral still refuses to switch, capture Settings > Diagnostic information. The Mistral site language line tells us whether the cookie itself changed or whether Mistral's signed-in account preference overwrote it.

Automated tests do not claim live account-language validation.
