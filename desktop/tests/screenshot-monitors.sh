#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export DISPLAY=:92 GDK_SCALE=1 LIBGL_ALWAYS_SOFTWARE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1
export SHOT_OUTPUT="$PWD/artifacts/two-monitors"
export XDG_CONFIG_HOME="$RUNNER_TEMP/screenshot-monitors/config" XDG_DATA_HOME="$RUNNER_TEMP/screenshot-monitors/data" XDG_CACHE_HOME="$RUNNER_TEMP/screenshot-monitors/cache"
mkdir -p "$SHOT_OUTPUT" "$XDG_CONFIG_HOME/nl.lecomputeur.vibez3" "$XDG_DATA_HOME" "$XDG_CACHE_HOME"
printf '{"language":"nl","zoom_factor":1,"auto_updates":false}' > "$XDG_CONFIG_HOME/nl.lecomputeur.vibez3/settings.json"
# A single root with two genuine RandR outputs, not two overlapping Xvfb screens.
sudo Xorg "$DISPLAY" -config "$PWD/tests/dual-monitor-xorg.conf" -noreset -nolisten tcp -ac -logfile "$SHOT_OUTPUT/xorg.log" > "$SHOT_OUTPUT/xorg-stdout.log" 2>&1 &
xpid=$!
trap 'sudo kill "$xpid" 2>/dev/null || true' EXIT
ready=false
for i in $(seq 1 50); do
  if xrandr --query > "$SHOT_OUTPUT/outputs-before.txt" 2>&1; then ready=true;break;fi
  sleep .1
done
$ready || { cat "$SHOT_OUTPUT/xorg-stdout.log"; exit 1; }
xrandr --addmode DUMMY1 1280x900
xrandr --output DUMMY0 --mode 1280x900 --pos 0x0 --primary --output DUMMY1 --mode 1280x900 --pos 1280x0
xrandr --listmonitors > "$SHOT_OUTPUT/monitors.txt"
xrandr --query > "$SHOT_OUTPUT/outputs.txt"
cat "$SHOT_OUTPUT/monitors.txt"
timeout 150s dbus-run-session -- bash -c '
  openbox --sm-disable > "$SHOT_OUTPUT/openbox.log" 2>&1 &
  wm=$!
  src-tauri/target/release/vibez3 --screenshot-ui-test > "$SHOT_OUTPUT/app.log" 2>&1 &
  app=$!
  trap "kill $app $wm 2>/dev/null || true" EXIT
  /usr/bin/python3 tests/screenshot-monitors.py
'
