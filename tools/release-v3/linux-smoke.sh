#!/usr/bin/env bash
set -euo pipefail
cd desktop
mkdir -p artifacts
export LIBGL_ALWAYS_SOFTWARE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1
export PREVIEW_ARTIFACTS="$PWD/artifacts"
export PREVIEW_BINARY="$PWD/src-tauri/target/release/vibez3"
for scale in 1 2; do
  export GDK_SCALE="$scale" XDG_CONFIG_HOME="$RUNNER_TEMP/v3-smoke/$scale/config" XDG_DATA_HOME="$RUNNER_TEMP/v3-smoke/$scale/data" XDG_CACHE_HOME="$RUNNER_TEMP/v3-smoke/$scale/cache"
  mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME"
  timeout 240s dbus-run-session -- xvfb-run -a -s "-screen 0 $((1600*scale))x$((1000*scale))x24" bash -c '
    openbox --sm-disable > "$PREVIEW_ARTIFACTS/openbox-$GDK_SCALE.log" 2>&1 &
    "$PREVIEW_BINARY" --smoke-test --update-download-probe > "$PREVIEW_ARTIFACTS/native-$GDK_SCALE.log" 2>&1 &
    pid=$!; sleep 6; import -window root "$PREVIEW_ARTIFACTS/native-$GDK_SCALE.png" || true; wait "$pid"
  ' || { cat "artifacts/native-$scale.log"; exit 1; }
  cat "artifacts/native-$scale.log"
  for mark in SMOKE_OK: LANGUAGE_BOOTSTRAP_OK: HISTORY_OK: HIDDEN_OK: RELEASE_SCREENSHOT_OK: UPDATE_DOWNLOAD_OK:; do grep -F "$mark" "artifacts/native-$scale.log"; done
  test "$(grep -c RESIZE_OK: "artifacts/native-$scale.log")" -ge 8
done
unset GDK_SCALE XDG_CONFIG_HOME XDG_DATA_HOME XDG_CACHE_HOME
deb="$(find src-tauri/target/release/bundle/deb -name '*.deb' -print -quit)"
sudo apt-get install -y --no-install-recommends "$(realpath "$deb")"
timeout 100s dbus-run-session -- xvfb-run -a -s '-screen 0 1600x1000x24' bash -c '
  openbox --sm-disable > "$PREVIEW_ARTIFACTS/icon-openbox.log" 2>&1 &
  /usr/bin/python3 scripts/test-linux-icons.py --binary /usr/bin/vibez3 --source-icon ../icon.png --window-icon src-tauri/icons/128x128.png --output "$PREVIEW_ARTIFACTS"
' 2>&1 | tee artifacts/icon-smoke.log
grep -F ICON_SMOKE_OK: artifacts/icon-smoke.log
