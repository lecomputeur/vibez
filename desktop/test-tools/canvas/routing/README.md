# Canvas-origin native routing regression

Run the supplied old/candidate executable on its own Xvfb/Openbox display,
private DBus session and disposable profile. A preload replaces only the first
Mistral document and observes native signals; it never changes policy handlers.
Open commands are recorded without launching a browser.

```
python3 run.py --binary /absolute/old/vibez3 --expect old --output /absolute/empty-results
python3 run.py --binary /absolute/candidate/vibez3 --expect fixed --with-smoke --output /absolute/empty-results
python3 -m unittest discover -s . -p 'test_*.py'
```

Requires Python 3, C compiler, pkg-config webkit2gtk-4.1, Xvfb/xvfb-run,
Openbox and dbus-run-session. It installs nothing and never uses the inherited
user display or account. Run outside a sandbox that prohibits local sockets.

The old control must show four unwanted preview opener calls and no Canvas
frame request starts. The fixed build must start the three actual frame requests,
retain a Canvas popup as one related window with its opener and open a normal
external URL once through the normal opener. Optional remote get_state and
local auth-mode probes preserve their exact observations. A pending remote
request is not explicit denial, and missing diagnostics do not prove inactive
authentication. Any actually returned native state or active-auth result fails
the report. The separate native smoke checks explicit privilege rejection.

The popup trigger is a trusted GDK click scoped to the fixture's own WebKit
widget. Navigation callbacks are not counted as successful loads. Resource
starts, received responses and native subframe classification are separate.
The remote endpoint is deliberately nonexistent: a 404 is not chart-rendering
or service-authentication evidence.

--with-smoke runs the existing standalone local OAuth model and privilege,
history, language, popup and cleanup checks without the preload. No real
identity-provider login or openSUSE reproduction is claimed.
