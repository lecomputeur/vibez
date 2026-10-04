# Preview 0.1.8: observed main-window account handoff

## Evidence

The 0.1.7 origin-only trace shows main navigation through Mistral authentication and accounts.google.com, followed by `main-open-external: https://accounts.youtube.com`. This is a native main-view handoff, not evidence of a nested popup failure. The user's external browser then shows Google HTTP 400. The trace establishes the handoff, not that it is the only possible cause of a failed account login.

## Change

The same `policy::embedded_url` predicate used first by the main navigation callback now permits precisely HTTPS accounts.youtube.com on port 443 without URL credentials. All other YouTube hosts, lookalikes, HTTP and nonstandard ports remain excluded from this exception. Do not export cookies, replay consent URLs, spoof the user agent, or weaken TLS/native capabilities.

The 0.1.7 injected click handler remains disabled and origin-only diagnostics remain available. Popup handling, storage identity and production Electron/Store code are unchanged.

## Automated checks

Run the standard Linux and Windows workflows, including Rust tests named `observed_google_main_view_chain_stays_embedded`, `youtube_account_exception_is_exact_https_origin_only`, and `youtube_account_page_never_gains_native_commands`. The first uses synthetic origin-only URLs. The original 0.1.7 predicate rejects the accounts.youtube.com step; the updated predicate accepts it before any external-open branch.

The WebView2 offline link probe and GTK/WebKit window tests remain release gates. A passing check is not a real Google/Mistral login test. If the Linux window suite fails, investigate it rather than describing that build as fully tested.

## Manual acceptance

Quit the old preview completely, install 0.1.8 over it and verify the running version. Keep the existing profile. Attempt the normal Google login and complete any account challenge. Confirm that the main app reaches the signed-in Mistral page without opening Edge, pressing Home, restarting or starting a second login.

If the account handoff appears in diagnostics, expect `main-allow: https://accounts.youtube.com`, not `main-open-external` for that origin. If failure recurs, capture Link routing before restarting. Never request or share a full consent URL, password or two-factor code.

An already authenticated provider session can skip first-login steps. Use a separate test OS account or a pre-login VM snapshot for genuine first-login regression testing; do not erase the user's working profile to force it.
