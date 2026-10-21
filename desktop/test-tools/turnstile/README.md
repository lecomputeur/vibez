# Native Linux Turnstile routing regression

This test runs the supplied VibeZ executable in its own Xvfb/Openbox desktop,
private DBus session and disposable short `/tmp` profile. It does not use the
user's browser, profile, conversations, clipboard or display. It needs Linux,
Python 3, `cc`, `pkg-config webkit2gtk-4.1`, Xvfb/xvfb-run, Openbox and
dbus-run-session. The runner does not install dependencies.

From the repository root, with an empty output directory:

```sh
python3 desktop/test-tools/turnstile/run.py \
  --binary /absolute/path/to/old/vibez3 --expect old \
  --output /absolute/path/to/results/old
python3 desktop/test-tools/turnstile/run.py \
  --binary /absolute/path/to/candidate/vibez3 --expect fixed --with-smoke \
  --output /absolute/path/to/results/fixed
```

The runner compiles a test-only preload into the results directory. The library
replaces only the first public Mistral document with `fixture.html`, using a
Mistral base URI. It observes WebKit native signals with emission hooks and
resource listeners; it never calls a policy decision's `use`/`ignore`, changes
application callbacks or patches the executable. It intentionally uses software
rendering in this virtual desktop. This is a routing test, not a performance test.

The fixture requests a deliberately nonexistent Cloudflare challenge-platform
resource from an unnamed iframe, a named iframe, and an unnamed retry. It then
requests a Cloudflare popup through an explicit button. A native GDK button
press/release is dispatched only to this fixture's own WebKit widget in its
private display, and the DOM event must be trusted. A timer-only popup would be
blocked by WebKit before the application's native popup callback, so it cannot
test application policy. The fixture then requests an automatic external navigation from a timer. The
3.0.9 contract requires native observation and zero opener requests for that
automatic navigation. Deliberate link clicks must still open once and are
independently required by the structural navigation harness in the same CI job. A harmless PATH recorder handles
all browser-open requests without launching a browser. Only origins and known
synthetic case labels are logged, never arbitrary paths, queries or credentials.

`native-trace.jsonl` separates pre-decision NavigationAction callbacks from
actual `resource-load-started` signals and response policy events. A resource
start proves WebKit initiated a request, not that a server accepted it. Received
HTTP statuses and WebKit's `is_main_frame_main_resource` classification are
reported separately. Frame names are metadata only, not a main-frame heuristic.
An iframe `load` event is not used as a network success oracle.

The fixed contract requires zero challenge opener invocations, a resource start
for each of the three frame cases, an actual native popup-create callback followed
by a null `window.open` result, no additional own WebKit window, and zero automatic
external opener invocations. Earlier versions opening that timer navigation are
not the stronger 3.0.9 contract. The old control is expected to invoke the opener
once for each of the three frames and once for the challenge popup. Its successful
control result explicitly retains `fixedContractPassed: false`.

`--with-smoke` additionally runs the executable's existing native smoke suite,
without the preload or substituted document. It checks the real local OAuth
popup model: direct/about:blank bootstrap, nested related popups, opener and
postMessage callbacks, denied native privileges and popup cleanup. This is not
a real identity-provider sign-in.

`metadata.json` records executable/harness hashes and environment scope;
`result.json` contains the individual checks and limitations. These synthetic
results do not establish that a real Cloudflare widget solves successfully, nor
that the reported JavaScript error or openSUSE environment has been reproduced.

The report-oracle tests require no GUI:

```sh
python3 -m unittest discover -s desktop/test-tools/turnstile -p 'test_*.py'
```
