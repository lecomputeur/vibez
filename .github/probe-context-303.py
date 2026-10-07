"""Validate remote isolation and wait for the full attachment operation in UI tests."""
from pathlib import Path
p=Path('desktop/src-tauri/src/release_updates.rs');s=p.read_text()
old='remote.eval("window.__updateAcl=\'pending\';window.__TAURI__.core.invoke(\'update_state\').then(()=>window.__updateAcl=\'allowed\').catch(()=>window.__updateAcl=\'denied\');true").map_err(err)?;'
new='remote.eval("(() => {window.__updateAcl=\'pending\';if(typeof window.__TAURI__?.core?.invoke!==\'function\'){window.__updateAcl=\'no-bridge\';return true;}window.__TAURI__.core.invoke(\'update_state\').then(()=>window.__updateAcl=\'allowed\').catch(()=>window.__updateAcl=\'denied\');return true;})()").map_err(err)?;'
if old in s:s=s.replace(old,new)
s=s.replace('if crate::screenshots::eval_value(&remote,"window.__updateAcl").await?!="denied"{return Err("Remote update command was not denied".into());}', 'let remote_state=crate::screenshots::eval_value(&remote,"window.__updateAcl").await?;\n    if !matches!(remote_state.as_str(),"denied"|"no-bridge"){return Err(format!("Remote update isolation failed: {remote_state}"));}')
p.write_text(s)
p=Path('desktop/tests/screenshot-e2e.py');s=p.read_text()
s=s.replace("            sleep(.3);assert len(events())==number,'Duplicate paste event'", "            # The application requires 700 ms of stable attachment UI after\n            # delivery. Do not launch the next action on mere FileReader receipt.\n            sleep(1.2);assert len(events())==number,'Duplicate paste event'")
p.write_text(s)
