'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
test('Mint selection captures the desktop without involving web page reconstruction',()=>{
 const native=read('src-tauri/src/screenshot_screen_linux.rs');
 assert.match(native,/gdk_pixbuf_get_from_window/);assert.match(native,/Escape/);
 assert.doesNotMatch(native,/snapdom|invoke\(|execute_script/);
 assert.match(read('src-tauri/src/screenshot_dialog.rs'),/mode=="selection" \{capture_desktop/);
});
