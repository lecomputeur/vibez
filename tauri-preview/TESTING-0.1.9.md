# Preview 0.1.9: stateful authentication routing

## Why this replaces the domain patches

Manual testing showed both Google and Microsoft sign-in can leave the Tauri preview and fail in the external browser. The 0.1.7 routing trace proved one Google handoff to accounts.youtube.com, but adding that single origin in 0.1.8 did not solve the general problem. OAuth is a redirect chain whose intermediate origins can vary by provider, account state, consent state and verification method.

## New routing model

The MAIN Vibe webview enters authentication mode when it reaches Mistral's auth service or a known provider entry point. During that mode, safe HTTPS redirects stay in the same WebView2/WebKitGTK profile. The rule is provider-neutral: it does not enumerate every Google or Microsoft intermediate service.

Authentication mode ends only when the MAIN webview reaches https://vibe.mistral.ai or https://chat.mistral.ai, or when the user explicitly presses Home.

The auth-chain predicate accepts only HTTPS on the normal TLS port with a host and without URL credentials. It continues to reject HTTP, nonstandard ports, file:, data:, javascript: and credential-bearing URLs. Remote content and auth windows still have no native capabilities. No cookie/token reading, replay, user-agent spoofing or TLS bypass is added.

## Tests

Rust tests cover:
- auth entry via Mistral, Google, Microsoft and Apple entry origins;
- arbitrary safe HTTPS intermediates while auth mode is active;
- exact termination on Vibe/Chat content origins;
- rejection of unsafe schemes, ports and URL credentials;
- denial of native commands to auth pages.

Existing Windows WebView2 link-interception checks, Linux GTK/WebKit popup/IPC/layout tests and package-isolation gates remain enabled.

These tests do not log in to real providers. Manual live sign-in remains required.

## Manual acceptance

Fully quit the old preview and install 0.1.9 over it without deleting the preview profile. For a genuine first-login regression test, use a separate Windows account or a VM snapshot from before provider login rather than deleting a working profile.

Expected behavior:
1. Open the Mistral sign-in page.
2. Choose Google or Microsoft.
3. Complete account/consent/verification steps.
4. No provider intermediate page should be handed to Edge merely because its domain was not pre-listed.
5. The main view should return to Vibe/Chat and diagnostics should show auth-mode-end.

If it fails, capture Link routing before restarting. Do not share full OAuth URLs, passwords or verification codes.

Stable Electron VibeZ, stable releases and the existing Microsoft Store submission remain untouched.
