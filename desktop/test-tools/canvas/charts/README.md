# Visible srcdoc chart and bounded idle-CPU control

```
python3 run_chart.py --binary /absolute/old/vibez3 --expect old --count 8 --output /absolute/empty-results
python3 run_chart.py --binary /absolute/candidate/vibez3 --expect fixed --count 8 --output /absolute/empty-results
python3 -m unittest discover -s . -p 'test_*.py'
```

Count is 1 or 8. Requires Linux, Python 3, C compiler, pkg-config
webkit2gtk-4.1, Xvfb/xvfb-run, Openbox and dbus-run-session. Uses its own virtual
display, private DBus, disposable profile and harmless opener recorder. It never
uses user accounts or the inherited display and installs nothing.

The real supplied application binary retains all navigation handlers. A preload
replaces just its initial Mistral document with a four-row table and real 2D
canvas charts in srcdoc iframes. Readiness requires a postMessage from the exact
child window with a validated coloured pixel. Load events alone cannot pass.
Unready frames retry every 1.2 seconds; ready frames stop. No CPU-burn or
animation loop is added.

A screenshot is taken at approximately 5 seconds. WebKitWebProcess CPU/RSS are
sampled every half-second, with the default reported idle window at seconds 8–20.
`--duration` defaults to 26 seconds; `--idle-end` defaults to 20 and must be
greater than 8 and less than the duration. The observer's 1 Hz query budget is
compiled for the requested duration, so a longer run keeps the same query
activity throughout its idle window. For example, `--duration 90 --idle-end 85`
provides a single idle window of approximately 77 seconds. One
native state query per second is common to both builds. 100% is one CPU core.

An old control pass confirms failure to render; fixedContractPassed stays false.
Synthetic chart/pixel success is not a real Mistral Canvas-service test. The
Xvfb/software-renderer CPU figures cannot establish the reporter's original
sustained 50–90% CPU root cause or performance on openSUSE.
