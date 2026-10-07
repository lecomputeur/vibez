"""Commit final candidate safeguards and complete-button-path tests before compilation."""
from pathlib import Path
import os,json
if os.environ.get('GITHUB_REF')!='refs/heads/vibe/windows-real-paste-303-91c4':raise SystemExit('Candidate branch only')
d=Path('desktop');marker=d/'.candidate-303-qa2'
if marker.exists():raise SystemExit(0)
assert (d/'.candidate-303-integrated').exists()
assert json.loads((d/'package.json').read_text())['version']=='3.0.3'
p=d/'frontend/updates.js';s=p.read_text().replace("closed=false,base={}","closed=false,base={},actionError=''")
s=s.replace("$('error').textContent=s.error||'';$('error').hidden=!s.error", "$('error').textContent=s.error||actionError;$('error').hidden=!(s.error||actionError)")
s=s.replace("async function action(name){if(actionBusy)return;actionBusy=true;", "async function action(name){if(actionBusy)return;actionError='';actionBusy=true;")
s=s.replace("catch(e){$('error').hidden=false;$('error').textContent=preview.errorText(e);}finally{actionBusy=false;", "catch(e){actionError=preview.errorText(e);$('error').hidden=false;$('error').textContent=actionError;}finally{actionBusy=false;")
p.write_text(s)
p=d/'src-tauri/src/paste_composer.js';s=p.read_text().replace("if (!el?.isConnected || el.disabled || el.readOnly || el.getAttribute('aria-disabled') === 'true') return false;", "if (!el?.isConnected || el.disabled || el.readOnly || el.matches(':disabled') || el.closest('[aria-disabled=\"true\"],[inert]')) return false;")
a=s.index('  const usableUpload=');b=s.index('  const inputs=',a)
s=s[:a]+'''  const usableUpload=e=>e?.isConnected&&!e.matches(':disabled')&&!e.closest('[aria-disabled="true"],[inert]')&&
    (!e.accept||e.accept.toLowerCase().split(',').some(t=>['image/*','image/png','.png','*','*/*'].includes(t.trim())))&&!e.files?.length;
'''+s[b:];p.write_text(s)
p=d/'test/updates.test.cjs';s=p.read_text().replace("function ui(phase,lang='nl'){", "function ui(phase,lang='nl',failAction=false){").replace("calls.push([c,a]);return c===", "calls.push([c,a]);if(c==='update_action'&&failAction)throw new Error('Native opening failed');return c===")
s+='''\ntest('native action failure stays visible after status refresh',async()=>{
 const u=ui('ready','nl',true);await flush();u.el('open').listeners.click();await flush();
 assert.match(u.el('error').textContent,/Native opening failed/);assert.equal(u.el('error').hidden,false);
 await u.timers[0]();assert.match(u.el('error').textContent,/Native opening failed/);
});\n''';p.write_text(s)
p=d/'src-tauri/src/screenshot_release_probe.rs';s=p.read_text();needle='        for behaviour in ["ignore","reject","delay"]{';assert needle in s
s=s.replace(needle,'''        view.eval("document.getElementById('shot-composer').focus();").map_err(err)?;
        super::paste_composer::paste(app,&super::last()?,true).await?;
        println!("NATIVE_CLIPBOARD_ATTACHMENT_OK: focused native paste produced a visible attachment");
'''+needle);p.write_text(s)
p=d/'src-tauri/src/release_updates.rs';s=p.read_text();a=s.index('/// Explicit CI test');s=s[:a]+'''/// Explicit CI test exercises the real local button and downloads a published
/// package. It never opens, installs or announces a fake public release.
pub async fn smoke_check(app:&AppHandle)->Result<(),String>{
    if !app.state::<crate::PreviewState>().smoke{return Err("Update probe requires offline smoke mode".into());}
    show(app).await?;
    let window=app.get_webview("updates").ok_or("Update window missing")?;
    tokio::time::sleep(Duration::from_millis(400)).await;
    window.eval("window.__updateAcl='pending';window.__TAURI__.core.invoke('update_state').then(()=>window.__updateAcl='allowed').catch(()=>window.__updateAcl='denied');true").map_err(err)?;
    for _ in 0..40{tokio::time::sleep(Duration::from_millis(50)).await;if crate::screenshots::eval_value(&window,"window.__updateAcl").await?=="allowed"{break;}}
    if crate::screenshots::eval_value(&window,"window.__updateAcl").await?!="allowed"{return Err("Local update dialog ACL denied".into());}
    let remote=app.get_webview("vibe").ok_or("Missing webview")?;
    remote.eval("window.__updateAcl='pending';window.__TAURI__.core.invoke('update_state').then(()=>window.__updateAcl='allowed').catch(()=>window.__updateAcl='denied');true").map_err(err)?;
    tokio::time::sleep(Duration::from_millis(300)).await;
    if crate::screenshots::eval_value(&remote,"window.__updateAcl").await?!="denied"{return Err("Remote update command was not denied".into());}
    println!("UPDATE_ACL_OK: local dialog allowed, remote page denied");
    if std::env::args().any(|a|a=="--update-download-probe"){
        let release=update_download::discover().await?.ok_or("No published package for probe")?;
        let asset=release.assets.first().ok_or("No download")?.clone();
        {let mut s=state().lock().map_err(err)?;s.release=Some(release);s.phase="available";s.ready=None;s.error.clear();}
        for _ in 0..50{
            tokio::time::sleep(Duration::from_millis(100)).await;
            if crate::screenshots::eval_value(&window,"String(!document.getElementById('download').hidden && !document.getElementById('download').disabled && !!document.getElementById('package').value)").await?=="true"{break;}
        }
        window.eval("document.getElementById('download').click();").map_err(err)?;
        let mut ready=None;
        for _ in 0..600{
            tokio::time::sleep(Duration::from_millis(100)).await;
            let s=snapshot()?;
            if s["phase"]=="error"{return Err(format!("Update button download failed: {}",s["error"]));}
            if s["phase"]=="ready"&&!BUSY.load(Ordering::SeqCst){ready=state().lock().map_err(err)?.ready.clone();break;}
        }
        let(path,downloaded)=ready.ok_or("Update button did not produce a verified download")?;
        update_download::verify_file(&path,&downloaded)?;
        if downloaded.name!=asset.name{return Err("Update button selected the wrong artifact".into());}
        tokio::time::sleep(Duration::from_millis(500)).await;
        if crate::screenshots::eval_value(&window,"String(!document.getElementById('open').hidden && !document.getElementById('reveal').hidden)").await?!="true"{return Err("Verified download actions were not shown".into());}
        println!("UPDATE_DOWNLOAD_OK: button -> native ACL -> HTTPS -> {} bytes -> SHA-256 -> explicit Open, {} (never executed)",asset.size,asset.name);
        {let mut s=state().lock().map_err(err)?;s.ready=None;s.release=None;s.phase="latest";}
        let _=std::fs::remove_dir_all(path.parent().unwrap());
    }
    action(app,"close",None).await?;Ok(())
}
''';p.write_text(s)
p=Path('tools/release-v3/linux-smoke.sh');s=p.read_text().replace('"$PREVIEW_BINARY" --smoke-test >','"$PREVIEW_BINARY" --smoke-test --update-download-probe >');p.write_text(s)
marker.write_text('Button-path download, visible attachment, rejected upload and action-error persistence tests integrated.\n')
