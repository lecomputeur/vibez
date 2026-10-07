#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export LIBGL_ALWAYS_SOFTWARE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1
for scale in 1 2; do
  export GDK_SCALE="$scale" XDG_CONFIG_HOME="$RUNNER_TEMP/screenshot-e2e/$scale/config" XDG_DATA_HOME="$RUNNER_TEMP/screenshot-e2e/$scale/data" XDG_CACHE_HOME="$RUNNER_TEMP/screenshot-e2e/$scale/cache"
  mkdir -p "$XDG_CONFIG_HOME/nl.lecomputeur.vibez3" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "artifacts/e2e-$scale"
  printf '{"language":"nl","zoom_factor":1,"auto_updates":false}' > "$XDG_CONFIG_HOME/nl.lecomputeur.vibez3/settings.json"
  export SHOT_OUTPUT="$PWD/artifacts/e2e-$scale"
  timeout 180s dbus-run-session -- xvfb-run -a -s "-screen 0 $((1600*scale))x$((1000*scale))x24" bash -c '
    openbox --sm-disable > "$SHOT_OUTPUT/openbox.log" 2>&1 &
    src-tauri/target/release/vibez3 --screenshot-ui-test > "$SHOT_OUTPUT/app.log" 2>&1 &
    pid=$!; trap "kill $pid 2>/dev/null || true" EXIT
    /usr/bin/python3 tests/screenshot-e2e.py
  '
done
