# Structural native Linux navigation regression

This runner exercises the supplied real VibeZ executable without replacing any
application navigation, popup or opener decision handler. It owns a private
Xvfb/Openbox display, DBus session and disposable profile. A preload replaces
only the initial public Mistral document and observes native WebKit signals.

```sh
python3 desktop/test-tools/canvas/structural/run.py \
  --binary /absolute/path/to/vibez3 --output /absolute/empty/result-directory
python3 -m unittest discover -s desktop/test-tools/canvas/structural -p 'test_*.py'
```

The focused additional `--scenario auth-popup-boundary` control makes an unknown
HTTPS iframe open a related known login popup after an actual native click. The
popup completes a controlled provider redirect and stays open while the main
chat tries an unknown automatic navigation. The main response must be denied
before its script executes; popup authentication must not authorize the main
chat. This scenario uses the same runner, proxy and unmodified policy handlers.

Requires Linux, Python 3, OpenSSL CLI, C compiler, pkg-config webkit2gtk-4.1
with WebKitGTK 2.40 or newer,
Xvfb/xvfb-run, Openbox and dbus-run-session. The runner installs nothing and
never connects to the user's existing display, profile or accounts. Local
display/DBus/listener socket access is required.

## Closed HTTPS fixture

An unprivileged loopback CONNECT endpoint terminates TLS for a fixed set of
logical HTTPS test origins and generates deterministic HTML/302 responses. It
never forwards a connection to the internet. The preload configures this proxy
and certificate exceptions only in the test process's private WebKit contexts.
System trust, DNS and user browser settings are untouched. Credentials in test
URLs are never logged; only controlled host/case/path-category/status fields
are recorded. Generated certificate/key files remain in the output directory.

This allows unknown origins and real HTTP redirects to be tested independently
of production domain allowlists, server availability, accounts or HTTP404 pages.

## Contract

- Unknown HTTPS iframes, including unnamed, named, nested and redirected frames,
  receive actual HTTP200, run their document scripts and produce native response
  classification `mainFrameMainResource=false`.
- Unknown automatic top navigation may request its document, but the native
  main response is rejected before commit/script execution. The fixture server
  would receive an `/executed` marker if that script ran. The same exact URL is
  tested in both main and subframe contexts.
- A native trusted `LinkClicked` action opens an unknown external target once.
  This includes a clicked named-frame target under the explicit product rule,
  `_blank`, and explicit HTTP links. Automatic external popups must not invoke
  the OS opener, including a timer during recent user activation.
- Unsafe credentials, nonstandard port, automatic HTTP, file and data targets
  never start their document resource or run their scripts.
- Known Canvas/Cloudflare frames and exact blank/srcdoc documents keep working.
- A provider iframe cannot enable main-view authentication or mutate Pending
  into a more permissive popup purpose. Direct/blank genuine OAuth top chains
  continue in related views. A main chat→302auth→302unknown-provider chain is
  allowed, returns to chat and then blocks the next automatic unknown top load.
  A trusted main link and a JavaScript popup to known `login.live.com` repeat
  this distinction for an auth entry outside the normal embedded-domain set.

The observer records native navigation type, gesture, target metadata, response
main-frame classification and stable WebKitWebResource IDs with sent-request
redirect hops. It never treats `get_frame_name()==NULL`, URI equality or gesture
alone as proof of a main frame. NavigationAction has no public main-frame flag
in WebKitGTK API4.1; the independent response classifier is required.

Official API references: [target frame name](https://webkitgtk.org/reference/webkit2gtk/2.40.1/method.NavigationAction.get_frame_name.html),
[main-frame response classification](https://www.webkitgtk.org/reference/webkit2gtk/stable/method.ResponsePolicyDecision.is_main_frame_main_resource.html)
and [resource redirect hops](https://webkitgtk.org/reference/webkit2gtk/2.40.0/signal.WebResource.sent-request.html).

An automatic popup can be blocked by WebKit before the app sees a create event.
The result explicitly records whether the native create callback was reached;
absence alone is not an application popup-gate success claim. External opener
requests go to a harmless recorder and never start a browser.

## Evidence and limits

`metadata.json` freezes binary/source hashes and engine version. `native.jsonl`
records native events, `server.jsonl` records actual controlled HTTPS requests,
and `opener.jsonl` records OS-opening requests. `result.json` retains every check
and the exact failed checks. Output directories must be empty to prevent stale
evidence from passing a rerun.

These tests validate local routing, request/commit and popup contracts. They do
not test a real Canvas service, provider sign-in, Cloudflare verification, user
conversation or openSUSE environment. Run the separate real-checker/account
validation when those claims are needed. No CPU-performance claim is made.
