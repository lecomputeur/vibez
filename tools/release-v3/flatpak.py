#!/usr/bin/env python3
from pathlib import Path
import json,subprocess
root=Path.cwd();out=root/'release-assets';stage=root/'flatpak-stage';stage.mkdir(exist_ok=True)
deb=next(out.glob('*Linux-x64.deb'));subprocess.run(['dpkg-deb','-x',str(deb),str(stage/'payload')],check=True)
subprocess.run(['git','clone','https://github.com/flathub/shared-modules',str(stage/'shared-modules')],check=True)
subprocess.run(['git','checkout','cb9ec602a1ece1c76d5a4f8aa1d87c4a6bf99c3e'],cwd=stage/'shared-modules',check=True)
app='nl.lecomputeur.vibez3'
(stage/'vibez3.desktop').write_text(f'[Desktop Entry]\nName=VibeZ 3\nType=Application\nExec=vibez3\nIcon={app}\nTerminal=false\nCategories=Development;\nStartupWMClass={app}\n')
(stage/'metainfo.xml').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application"><id>{app}</id><metadata_license>CC0-1.0</metadata_license><project_license>MIT</project_license><name>VibeZ 3</name><summary>Desktop client for Mistral Vibe</summary><description><p>A dedicated Rust/Tauri desktop window for Mistral Vibe, with language selection and screenshot tools.</p></description><launchable type="desktop-id">{app}.desktop</launchable><url type="homepage">https://github.com/lecomputeur/vibez</url><releases><release version="3.0.0" date="2026-10-04"/></releases><content_rating type="oars-1.1"/></component>''')
manifest={'app-id':app,'runtime':'org.gnome.Platform','runtime-version':'50','sdk':'org.gnome.Sdk','command':'vibez3','finish-args':['--share=network','--share=ipc','--socket=fallback-x11','--socket=wayland','--device=dri','--socket=pulseaudio','--talk-name=org.kde.StatusNotifierWatcher'], 'modules':['shared-modules/libayatana-appindicator/libayatana-appindicator-gtk3.json', {'name':'vibez3','buildsystem':'simple','build-commands':['install -Dm755 payload/usr/bin/vibez3 /app/bin/vibez3',f'install -Dm644 payload/usr/share/pixmaps/{app}.png /app/share/icons/hicolor/512x512/apps/{app}.png',f'install -Dm644 vibez3.desktop /app/share/applications/{app}.desktop',f'install -Dm644 metainfo.xml /app/share/metainfo/{app}.metainfo.xml'], 'sources':[{'type':'dir','path':'payload','dest':'payload'},{'type':'file','path':'vibez3.desktop'},{'type':'file','path':'metainfo.xml'}]}]}
(stage/f'{app}.json').write_text(json.dumps(manifest,indent=2))
subprocess.run(['flatpak-builder','--user','--install','--force-clean','--repo=repo','build',f'{app}.json'],cwd=stage,check=True)
subprocess.run(['flatpak','run',app,'--version'],check=True)
subprocess.run(['flatpak','build-bundle','repo',str(out/'VibeZ-3.0.0-Linux-x64.flatpak'),app,'--runtime-repo=https://flathub.org/repo/flathub.flatpakrepo'],cwd=stage,check=True)
