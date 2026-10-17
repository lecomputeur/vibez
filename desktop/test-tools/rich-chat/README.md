# Linux rich-chat acceptance tests

These tests run the **ordinary Linux client binary**, with its production rendering helper, GTK layout, native FindController and capture error handling. The synthetic page is created only with the explicit test argument and environment guard. Ordinary startup continues to load the hosted app. No account or private conversation is required.

Use an existing Linux X11 display and a window manager. In CI, supply Xvfb and Openbox before invoking the launcher. The launcher itself needs Python 3 standard library, `/proc`, and `dbus-run-session`. The binary still needs its normal GTK/WebKitGTK runtime dependencies. PNG decoding is performed by the existing GTK GdkPixbuf dependency.

From the repository root, after preparing assets and building the binary:

```sh
python3 desktop/test-tools/rich-chat/run.py --binary /absolute/path/to/vibez3 --mode lifecycle --output /tmp/vibez-rich-lifecycle
python3 desktop/test-tools/rich-chat/run.py --binary /absolute/path/to/vibez3 --mode resize --output /tmp/vibez-rich-resize
python3 desktop/test-tools/rich-chat/run.py --binary /absolute/path/to/vibez3 --mode wheel --baseline --output /tmp/vibez-rich-wheel-baseline
python3 desktop/test-tools/rich-chat/run.py --binary /absolute/path/to/vibez3 --mode wheel --output /tmp/vibez-rich-wheel-optimized
python3 desktop/test-tools/rich-chat/run.py --binary /absolute/path/to/vibez3 --mode fullscreen --sections 2 --output /tmp/vibez-rich-fullscreen
```

Each output directory must be empty. Run one graphical test at a time. The launcher creates and removes a separate temporary profile, provides config/data/cache paths under it, starts a private session bus, and passes `--rich-offline-test`. The private bus matters because changing the profile alone does not isolate D-Bus single-instance names. It requests placement on the left screen without keyboard focus; no desktop-wide keyboard, wheel or screenshot operation is used. Fullscreen is requested explicitly on the monitor whose x coordinate is zero, with a checked x=0..2560 window boundary. CI must provide that monitor area and a working window manager.

The default memory guard refuses startup below 600 MiB available RAM and stops only the launched process group after three consecutive samples below that threshold or above 2400 MiB summed RSS. Limits are configurable through `--min-available-mib` and `--max-own-rss-mib`. The launcher does not close other clients or free their memory. All modes have a configurable 600-second wall-clock bound.

## Coverage

`lifecycle` retains the original 52 functional checks, adds two explicitly simulated persisted page lifecycle checks, and then verifies real native resizes, native search matches, the native Find dialog and failed capture cleanup. It covers streamed appends and updates, historical expansion, geometry against a full-render oracle, selection, content retention, stylesheet invalidation, hidden-message ownership, replacement/removal, overlapping exact refreshes and programmatic scroll persistence during a pending batch. The simulated `PageTransitionEvent` checks are not a real back-forward cache hit. Native Find uses unique first/middle/last synthetic markers and an absent marker. The capture regression queues a six-second busy loop only in this own synthetic WebKit view; the five-second pause IPC deadline must fail, and helper containment must resume afterward. The intended failure occurs before screenshot generation or clipboard copying.

`resize` sends 36 intermediate native window sizes at approximately 60 ms intervals, then returns to 1280×840. It records native allocations and JavaScript viewport events, rAF/heartbeat gaps, helper queue completion, trusted native wheel reception, scrolling and final wheel persistence. A small canvas updates a frame ID without DOM mutations; decoded visible-WebKit PNG pixels must contain the fresh frame marker, distributed chat content and the final viewport dimensions. Observation continues through at least five seconds of recovery, so an early cached frame cannot hide a later blocking layout. The helper must actually remeasure its optimized records and drain its queue. The one-second responsiveness target includes callback gaps and input/content checks. Exact full-page height oracles are separate functional checks, not resize latency measurements.

`wheel` sends native wheel input every 100 ms for 30 seconds, changing direction every four seconds. It measures five seconds of idle and 20 seconds after scrolling. At least 95% of sent native wheel events must be received as trusted events, and the viewport must remain visible at 1280×786. `--baseline` pauses only the rendering containment helper in the same binary and fixture. It does not select an alternate renderer, GTK layout or build. Both runs must use the same machine/display and settings for a controlled comparison; hardware and scheduler differences still affect the measurements.

`fullscreen` checks normal, maximized, true fullscreen, exit-fullscreen and unmaximized states. It validates the 54 px shell and complete content allocation against the actual native inner dimensions, JavaScript viewport and decoded own-WebKit PNG dimensions. It records the known synthetic codebox and sticky header geometry without changing the sticky behavior. `--sections 2` reduces this visual-only case to 40 replies with two rich sections each. Other modes always retain 40 replies with 16 rich sections; recorded node counts, not a nominal memory claim, identify the fixture.

## Measurements and evidence

The launcher writes `metadata.json` (binary and harness hashes, explicit overrides and limits), `app.log`, structured `events.json`, `cpu-samples.jsonl` and `summary.json`. Resize and fullscreen modes also write their native result JSON and own-WebKit PNGs. A successful launcher exit requires both process exit zero and a completion event; a missing result cannot silently pass.

CPU is summed only for `WebKitWebProcess` descendants of this test process. **100% means one logical CPU core**, so multiple threads/processes may exceed 100%. Sampling is approximately every 0.5 seconds. The mean is weighted by measured interval duration, and intervals crossing a named phase are excluded. `samplesAbove100Percent` counts sample intervals, not instantaneous peaks. RSS is summed resident memory and can double-count shared pages; it is neither DOM size nor proportional memory.

PNG snapshots verify pixels rendered by this WebKit view. They do **not** establish when the OS compositor physically presented those pixels. First fresh content, first successful input protocol time and elapsed time from a particular native input are distinct fields. Use their actual labels rather than treating the whole recovery protocol as pure wheel input latency. Tiny native/JS viewports are discrete observations, not proof that every intervening moment had that size.

The fixture models long formatted replies, tables, code blocks and sticky elements. It is not captured Mistral markup. Passing these tests establishes the synthetic and native-client contracts, not authenticated hosted-chat compatibility or GPU-driver causation.

For controlled environment comparisons, add `--disable-compositing` or `--disable-dmabuf`. The launcher clears inherited VIBEZ_ and WEBKIT_ test settings, explicitly uses X11 at GDK scale 1, and records cleared key names and the tested overrides. Any inherited Mesa/GL driver overrides are reported separately.

## Optional anonymous hosted smoke

```sh
python3 desktop/test-tools/rich-chat/run.py --binary /absolute/path/to/vibez3 --mode mistral --output /tmp/vibez-rich-anonymous
```

This mode uses the ordinary site-language bootstrap to navigate to the public hosted page in the fresh profile and observes it for approximately 20 seconds. It records allowed public origins, title, readiness, visibility, helper status and selector **counts**. It never signs in, interacts with a challenge, sends a message, reads cookies/input values or inspects conversation content. A challenge page or missing matching markup is classified explicitly. A zero exit means the observation protocol completed, not that a genuine long hosted conversation was reproduced. This network-dependent observation is intentionally not a required offline CI gate.
