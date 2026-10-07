'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../src-tauri/src/screenshot_dialog.rs'),'utf8');
test('Linux positions the hidden screenshot chooser on its transient parent before mapping',()=>{
 assert.match(source,/#\[cfg\(target_os="linux"\)\]\s*let builder=builder\.visible\(false\)/);
 assert.match(source,/#\[cfg\(not\(target_os="linux"\)\)\]\s*let builder=builder\.center\(\)/);
 const body=source.slice(source.indexOf('async fn show_on_parent'));
 assert.ok(body.indexOf('child.set_transient_for(Some(&parent))')<body.indexOf('child.set_position(gtk::WindowPosition::CenterOnParent)'));
 assert.ok(body.indexOf('child.set_position(gtk::WindowPosition::CenterOnParent)')<body.indexOf('child.show()'));
 assert.doesNotMatch(source,/CenterAlways|primary_monitor\(|connect_configure_event/);
});
test('an existing screenshot window is only shown/focused, not snapped back after manual movement',()=>{
 assert.match(source,/if let Some\(window\)=app\.get_webview_window\("screenshot"\) \{window\.show\(\).*return window\.set_focus\(\)/);
 assert.equal((source.match(/show_on_parent\(app,&window\)\.await/g)||[]).length,1);
});
