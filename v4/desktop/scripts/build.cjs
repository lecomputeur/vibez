'use strict';
// AppImage reuses Tauri's Debian desktop template. Its icon must be an AppDir
// themed name, not the absolute installed DEB pixmap. Keep the builds separate.
const {spawnSync} = require('node:child_process');
const cli = require.resolve('@tauri-apps/cli/tauri.js');
const original = process.argv.slice(2);
function run(args) {
  const result = spawnSync(process.execPath, [cli, 'build', ...args], {stdio: 'inherit'});
  if (result.error) { console.error(result.error.message); process.exit(1); }
  if (result.status !== 0) process.exit(result.status || 1);
}
const at = original.indexOf('--bundles');
const bundles = at >= 0 ? original[at+1].split(',') : [];
if (process.platform !== 'linux' || (!bundles.includes('appimage') && bundles.length && !bundles.includes('all'))) {
  run(original);
} else {
  const base = [...original];
  if (at >= 0) base.splice(at,2);
  const add = (options) => { const args=[...base]; const tail=args.indexOf('--'); args.splice(tail<0?args.length:tail,0,...options); return args; };
  const others = !bundles.length || bundles.includes('all') ? ['deb','rpm'] : bundles.filter(b=>b!=='appimage');
  if (others.length) run(add(['--bundles',others.join(',')]));
  run(add(['--bundles','appimage','--config','src-tauri/tauri.appimage.conf.json']));
}
