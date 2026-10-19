# Native Wry policy-hook lifecycle

This standalone fixture tests the vendored Wry library through a real
`WebViewBuilder::with_navigation_handler(...).build_gtk(...)` connection. It
loads only its own inline HTML, without a remote server or account. The runner
creates a private virtual display, session bus and disposable XDG profile.

The checks exercise an unhooked view, `false` fallback, `true` handled/ignored
navigation, callback replacement during invocation, re-entry through the actual
GTK `decide-policy` signal, old-callback lifetime until return, the replacement
on a subsequent real navigation, and callback release when the native view is
finalized. Re-entry deliberately reuses the live decision object as a synthetic
stress case; it is not a natural service flow.
The separate creation gate is exercised through the real Wry `create` connection
using a copied native action: unhooked/allow must reach the old URL creator,
deny must bypass it, and replacing/releasing gates must run their destructors.
These create-only signal emissions are synthetic; they do not simulate a real
user click or claim to prove WebKit's gesture classification.

Run with cached dependencies and the required local Xvfb/DBus tools available:

```sh
python3 run.py --output /absolute/empty/evidence-directory \
  --target-dir /absolute/shared/cargo-target
```

`Cargo.toml` is an independent workspace and points directly to the vendored
Wry package. `--locked --offline` prevents network dependency resolution. The
runner does not install system packages. Local socket restrictions may require
running the private display outside a command sandbox.

`result.json` reports each check; `metadata.json` records executable/source
hashes and the exact environment/commands. This is library lifecycle evidence.
It does not verify VibeZ's service login, real Canvas charts, Cloudflare solves,
CPU usage or platform behavior outside this Linux runtime.
