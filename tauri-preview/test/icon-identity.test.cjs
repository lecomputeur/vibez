"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const read = f => fs.readFileSync(path.join(root, f), "utf8");
const config = JSON.parse(read("src-tauri/tauri.conf.json"));
const id = config.identifier;

test("desktop launcher resolves the packaged pixmap without a theme-cache dependency", () => {
  const desktop = read("src-tauri/linux/" + id + ".desktop");
  const icon = desktop.match(/^Icon=(.+)$/m)[1];
  assert.equal(icon, "/usr/share/pixmaps/" + id + ".png");
  assert.equal(config.bundle.linux.deb.files[icon], "icons/icon.png");
  assert.equal(desktop.match(/^StartupWMClass=(.+)$/m)[1], id);
  assert.match(read("src-tauri/linux/hidden-generated.desktop.hbs"), /^NoDisplay=true$/m);
});
test("native identity is configured before any app windows are created", () => {
  const main = read("src-tauri/src/main.rs");
  assert.ok(main.indexOf("linux_identity::initialize()") < main.indexOf('WindowBuilder::new(app, "main")'));
  const identity = read("src-tauri/src/linux_identity.rs");
  assert.match(identity, /set_prgname\(Some\(APP_ID\)\)/);
  assert.match(identity, /set_program_class\(APP_ID\)/);
  assert.match(identity, /set_default_icon_list/);
});
test("tray icon has required embedded pixels and a process-specific directory", () => {
  assert.match(read("src-tauri/src/desktop_ui.rs"), /temp_dir_path/);
  assert.match(read("src-tauri/src/linux_identity.rs"), /std::process::id\(\)/);
  assert.doesNotMatch(read("src-tauri/src/desktop_ui.rs"), /if let Some\(icon\) = app.default_window_icon/);
});
