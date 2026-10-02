# Preview 0.1.7: first-login investigation

## Observation, not a diagnosis

A tester reports that first Google sign-in ends at HTTP 400 in Edge. Returning Home does not complete sign-in. After fully restarting the preview and clicking Sign in again, sign-in succeeds without repeating the credentials. This suggests some provider/session state persists, but does not establish that Mistral had completed sign-in before the restart.

## Narrow change

Disable tauri-plugin-opener's default injected click handler with `open_js_links_on_click(false)`. It normally intercepts `_blank` / Ctrl-click / Shift-click anchors before the app's native navigation handlers. Keep explicit native external-link handling, the existing domain policy, related-popup handling, account profile and local-only capabilities unchanged.

Add a bounded, in-memory, origin-only trace of main navigation allow/block decisions, requests to the external browser, main page loads and main popup creation. The trace excludes URL paths, queries, fragments, user info, cookies and tokens. It is not persisted after process exit. No account data is read, copied or reset.

## Verification

`--link-probe-only` loads only the bundled offline page. Synthetic anchor clicks in the actual webview observe whether an injected handler cancelled the click. The probe cancels the clicks itself before any navigation. It covers `_blank`, Ctrl-click and Shift-click and runs on the Windows CI runner using WebView2. The Linux `--smoke-test` runs this probe before the existing GTK/WebKit popup, IPC and layout tests.

These tests do not log in to a real Google/Mistral account and do not prove that the user's 400 error is fixed. Do not describe this as a verified OAuth fix.

## Manual use

Install the corresponding 0.1.7 DEB or Windows Setup over the existing preview only after fully quitting the old process. Do not delete the working profile. Check the running title reports v0.1.7.

If the issue recurs, open Settings > Diagnostic information without restarting the preview, and capture the `Link routing` block. `main-open-external` identifies an explicit main-window browser handoff. No such entry does not by itself prove why a browser opened. Do not copy the full Google consent URL.

Testing an actually fresh profile requires a separate test OS account or a VM snapshot from before login; do not erase the user's normal profile just to force a reproduction. Existing signed-in state is not a first-login regression test.

Stable Electron VibeZ, its release feed and existing Microsoft Store submission are untouched.
