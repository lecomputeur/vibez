# Native Linux Canvas regression tools

These account-free tools run a supplied VibeZ executable with its real native
navigation handlers on a dedicated Xvfb/Openbox display, private DBus session
and disposable profile. A test-only preload replaces only the initial public
Mistral document and observes native signals. Open requests are recorded without
launching a browser. Nothing is included in the application bundle.

- `charts/`: actual 2D charts in srcdoc iframes, validated child messages and
  coloured pixels, screenshots, retry counts and a bounded idle-CPU control.
- `routing/`: Canvas-origin frame requests, a trusted popup click, related
  preview window/opener, ordinary external links and optional diagnostic probes.
  `--with-smoke` also runs the existing native OAuth/history/language suite.
- `structural/`: current policy gate with closed local HTTPS fixtures for
  unknown/nested/redirected frames, denied main documents, trusted link clicks,
  pending Canvas windows and real HTTP auth-redirect chains (no account).
- `policy-hook/`: offline native Wry callback lifecycle and fallback checks.
- `bootstrap/`: historical test.1 popup contract, retained as investigation
  evidence. Its old automatic-browser expectation is intentionally superseded
  by the structural policy; see its README.

Each directory has its own short README and standalone runner. Requires Linux,
Python 3, C compiler, pkg-config `webkit2gtk-4.1`, Xvfb/`xvfb-run`, Openbox and
`dbus-run-session`. The runners install no dependencies. Run them with local
display/DBus socket access; they never attach to the user's inherited display.
Result directories must be empty and should be outside the repository.

Pure report-oracle tests need no GUI:

```sh
python3 -m unittest discover -s desktop/test-tools/canvas/charts -p 'test_*.py'
python3 -m unittest discover -s desktop/test-tools/canvas/routing -p 'test_*.py'
python3 -m unittest discover -s desktop/test-tools/canvas/bootstrap -p 'test_*.py'
```

The old-control pass deliberately records the old failure and does not count as
a passed fixed contract. A resource start or HTTP 404 is not successful Canvas
service rendering. Synthetic chart pixels are not a real Mistral conversation.
The software virtual display's CPU figures do not prove the reporter's original
idle-CPU root cause or reproduce openSUSE/Wayland/hybrid graphics.

Optional remote IPC can remain pending and local auth diagnostics can be
unavailable. Those states are reported literally, without calling them explicit
denial or inactive authentication. The separate native smoke supplies explicit
IPC-rejection evidence for its local OAuth models.
