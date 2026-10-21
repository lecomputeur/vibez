# Linux CPU comparison

`measure-linux-cpu.py` measures an already running VibeZ process and its descendants. It does not launch the app. Use it to compare the **same original heavy conversation from issue #49** in stable VibeZ 3.0.9, first normally and then with the rich-render helper disabled.

You can download just `measure-linux-cpu.py` using GitHub's **Download raw file** button; no repository checkout or app rebuild is required. For a standalone download, run commands from its download folder and replace `tools/diagnostics/measure-linux-cpu.py` below with `./measure-linux-cpu.py`.

## Prepare both runs

Save any drafts before restarting. Keep the saved conversation, viewport, window size, scroll position and idle conditions the same for both runs. Let loading and streaming finish, then leave the app untouched during each measurement. Do not reinstall VibeZ or delete a profile.

Confirm the installed version in VibeZ itself. The collector checks that the selected PID belongs to your user and that its executable basename is `vibez3` or `vibez3-canvas-test`; it records the root executable's SHA-256. Neither the name nor that hash establishes a version, and no expected hash is built in.

Use the PID of the existing main VibeZ process, not a WebKit child. `pgrep -x vibez3` lists matching PIDs without command lines; if several are present, identify the intended instance before continuing. The isolated Canvas Test app has a separate identity and profile, so do not substitute it for one half of a stable-versus-stable comparison.

## 1. Normal run

Open stable 3.0.9 normally, with `VIBEZ_DISABLE_RICH_RENDER` unset. Load the original heavy conversation and note the counters shown in the existing **Settings diagnostics**: `matched`, `optimized`, `working` and `pauses`. Those counters contain no conversation text.

From the repository root, replace `PID` with the numeric main-process PID:

```sh
python3 tools/diagnostics/measure-linux-cpu.py --pid PID --output cpu-normal.json --duration 90
```

The default duration is 90 seconds **in total**, including a fixed 10-second warm-up. Allowed durations are 20–180 seconds, sampled every second. The reported CPU averages use elapsed-time weighting over complete intervals after the warm-up.

## 2. Helper-disabled run

Save drafts, quit VibeZ completely, and check that no instance remains in the tray or background. Launch it manually with the helper disabled:

```sh
VIBEZ_DISABLE_RICH_RENDER=1 vibez3
```

For Flatpak, use this exact launch command instead:

```sh
flatpak run --env=VIBEZ_DISABLE_RICH_RENDER=1 nl.lecomputeur.vibez3
```

Restore the same conversation, viewport and idle conditions. Note the Settings diagnostics status (`disabled by environment` is expected instead of helper counters), obtain the new main-process PID, and collect a separate file:

```sh
python3 tools/diagnostics/measure-linux-cpu.py --pid PID --output cpu-helper-disabled.json --duration 90
```

Quit completely again before returning to an ordinary launch with the variable unset. These steps do not require reinstalling or removing saved app data.

## Read and share the results

- Compare the whole VibeZ process family as well as the `WebKitWebProcess` subset. **100% CPU means one logical CPU core**, so totals may exceed 100%.
- RSS is resident-set size, not unique memory; summing processes can count shared pages more than once.
- Processes that start and exit between samples can escape observation. CPU totals are therefore a lower bound when short-lived processes churn. The measurements do not attribute CPU use to a particular chart, conversation element or helper, and do not establish that issue #49 is fixed.

Each output must be a new file: the collector refuses to overwrite an existing path and creates it with owner-only permissions (`0600`). Choose another filename for a repeat run. Reports contain process metadata and counters only; they do not collect profiles, cookies, command lines, environment contents, conversation text or network traffic. Share both JSON files, the text-free Settings counters, and a short description of the matching test conditions when reporting the comparison.

## Controlled active-frame experiment

`active-frames/run.py` fills a gap in the older regressions: the rich-chat fixture has long formatted answers without live iframes, while the chart routing fixture has static charts. This additional diagnostic uses eight continuously animated synthetic `srcdoc` charts, independent timer counters and synthetic unsaved input state. It does not load a private conversation or the hosted Canvas service.

Requirements: the ordinary Linux app binary and its GTK/WebKitGTK runtime; Python 3; a C compiler and `pkg-config` for WebKitGTK 4.1; Xvfb, xauth, Openbox and `dbus-run-session`. Run the two cases sequentially on the same otherwise idle machine:

```sh
python3 tools/diagnostics/active-frames/run.py --binary /absolute/path/to/vibez3 --output /tmp/vibez-active-normal
python3 tools/diagnostics/active-frames/run.py --binary /absolute/path/to/vibez3 --output /tmp/vibez-active-helper-disabled --disable-rich-render
```

Each run owns a separate virtual X11 display, session bus and disposable profile. Existing output directories must be empty. The unchanged binary runs for about 57 seconds, with only its first hosted document replaced by the local fixture through the existing test-only native observer. The observer library is compiled into the evidence directory and is never packaged into VibeZ. The launcher terminates only its own test process group.

Phases are all eight previews visible, seven moved outside the viewport, seven hidden with CSS, and all eight visible again. One preview remains a visible control. No iframe is removed or reloaded. A successful result requires the requested helper state, expected viewport counts, valid WebKit CPU samples, fresh frame progress, preserved document identities and synthetic drafts, and a stop acknowledgement from every frame. The one-off screenshot around second five is excluded from the visible CPU window. CPU phase windows use monotonic native-query timestamps and exclude transitions; frame reports are sampled, rather than continuous observations.

Raw native events, CPU samples, binary/fixture/runner hashes, a visible snapshot and phase results stay in the selected output directory. Software rendering and inherited driver overrides are recorded. CPU is the sum of this test tree's observed `WebKitWebProcess` deltas; a process that exits between samples can escape observation.

This measures **the VibeZ helper enabled versus disabled**, not iframe containment enabled versus disabled: all eight answer wrappers contain iframes, which the current helper deliberately excludes. Animation/timer activity in this fixture is intentional. Its CPU figures do not reproduce or prove the cause of the reporter's original heavy conversation, cross-origin Canvas application or Wayland/GPU environment. Browsers may also throttle offscreen callbacks differently; missing fresh progress makes the diagnostic fail instead of claiming that a frame was preserved.
