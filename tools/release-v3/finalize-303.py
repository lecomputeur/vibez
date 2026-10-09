"""Promote approved test 7 using contents-only CI permissions; never edit workflows."""
from pathlib import Path
import os,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
os.chdir(ROOT)
APPROVED='7ab2bbc8e03b07ca0389e2f809a8f1d8805c4217'
BRANCH='vibe/release-3.0.3-a73d19'
assert os.environ.get('GITHUB_REF')=='refs/heads/'+BRANCH
subprocess.run(['git','merge-base','--is-ancestor',APPROVED,'HEAD'],check=True)
def replace(path,old,new,required=True):
 p=Path(path);s=p.read_text()
 if required:assert old in s,path+': expected text missing'
 p.write_text(s.replace(old,new))
marker=Path('desktop/.release-303-approved')
if not marker.exists():
 replace('desktop/src-tauri/src/main.rs',' · test 7','')
 replace('desktop/src-tauri/src/main.rs','"build_label": "test 7"','"build_label": ""')
 for name in ['collect.py','arch.sh','flatpak.py','legacy-feed.cjs','verify-published-assets.py','verify-release-proof.py']:
  replace('tools/release-v3/'+name,'3.0.2','3.0.3')
 replace('tools/release-v3/flatpak.py','2026-10-07','2026-10-09')
 replace('tools/release-v3/verify-release-proof.py','vibe/release-3.0.3-7e2b46',BRANCH)
 replace('tools/release-v3/verify-release-proof.py','.github/workflows/vibez-v3.yml','.github/workflows/release-approved-303.yml')
 # The CI token cannot edit workflows. The existing publication workflow is
 # deliberately left unchanged; no permission expansion or rejected retry.
 for p in [Path('README.md'),Path('MICROSOFT-STORE.md'),*Path('docs').glob('*.html')]:
  s=p.read_text().replace('3.0.2','3.0.3').replace('screenshots-302','screenshots-303').replace('actions/workflows/vibez-v3.yml','actions/workflows/release-approved-303.yml')
  p.write_text(s)
 replace('MICROSOFT-STORE.md','.github/workflows/vibez-v3.yml','.github/workflows/release-approved-303.yml')
 for p in Path('docs').glob('sitemap.*'):
  s=p.read_text().replace('2026-10-07','2026-10-09');p.write_text(s)
 update='VibeZ checks for published updates automatically at startup. Download the matching package inside VibeZ, with progress, cancellation and SHA-256 verification, then explicitly open the installer. VibeZ does not install silently or force a restart. Microsoft Store installations use Store delivery.'
 screenshot='Visible page, Full page and Selection remain in a compact menu. Paste directly into Chat and Work drafts without sending a message. In Code, choose Screenshot as file, save as PNG and share the file separately. The short Code explanation and conditional sign-in notice are translated into all 34 interface languages. Copying and saving are available without signing in.'
 replace('README.md','A manual **Check for updates** action remains available.','A manual **Check for updates** action remains available. '+update)
 replace('README.md','Updates are installed manually.','Downloaded updates are installed only after your confirmation.')
 p=Path('README.md');s=p.read_text();start=s.index('## Screenshots in 3.0.3');p.write_text(s[:start]+'## Screenshots in 3.0.3\n\n'+screenshot+'\n\nThe macOS toolbar now uses the actual area below the native titlebar. Existing Chat/Work paste, settings, language selection and the new downloader are preserved from maintainer-approved test 7.\n')
 for name in ['index.html','linux.html','windows.html','macos.html']:
  p=Path('docs')/name;s=p.read_text()
  s=s.replace('<h2>Screenshots in VibeZ 3.0.3</h2>','<h2>Screenshots in VibeZ 3.0.3</h2><p>'+screenshot+'</p>')
  pos=s.rfind('</main>');assert pos>=0
  s=s[:pos]+'<section class="details" id="updates-303"><h2>Updates from inside VibeZ</h2><p>'+update+'</p><p>Version 3.0.3 also fixes the macOS toolbar being partly hidden behind the titlebar. The Store version follows Microsoft certification and may become available later than the direct downloads.</p></section>'+s[pos:]
  p.write_text(s)
 p=Path('MICROSOFT-STORE.md');s=p.read_text();start=s.index('## English update text')
 p.write_text(s[:start]+'''## English update text

VibeZ 3.0.3 improves screenshots with a compact 34-language menu. Paste into Chat and Work drafts without sending the message. In Code, save the screenshot as PNG and share it separately. A sign-in notice appears only when guest sign-in controls are visible; copying and saving remain available. Direct installations gain in-app update downloads with progress and integrity checks. Microsoft Store installations continue to update through the Store. This independent client is not affiliated with Mistral AI.

## Nederlandse updatebeschrijving

VibeZ 3.0.3 verbetert screenshots met een compact menu in 34 talen. Plak in Chat- en Work-concepten zonder het bericht te versturen. In Code sla je de screenshot op als PNG en deel je het bestand apart. Een inlogmelding verschijnt alleen wanneer de inlogknoppen zichtbaar zijn; kopiëren en opslaan blijven beschikbaar. Directe installaties krijgen downloads binnen VibeZ, met voortgang en bestandscontrole. Microsoft Store-installaties blijven via de Store bijwerken. Deze onafhankelijke client is niet verbonden aan Mistral AI.
''')
 Path('V3-RELEASE.md').write_text('''# VibeZ 3.0.3 — Screenshots, in-app downloads and macOS layout

Stable promotion of maintainer-approved **3.0.3 test 7**, source `7ab2bbc8e03b07ca0389e2f809a8f1d8805c4217`. The maintainer confirmed that test 7 works and authorized release on all platforms. Functional code is preserved; the test display labels are removed.

## Screenshots

Visible page, Full page and Selection remain compact. Paste directly into Chat and Work drafts without sending a message. In Code, choose **Screenshot as file**, save as PNG and share the file separately. The explanation explicitly says that Chat and Work support direct pasting. A conditional sign-in notice appears when guest sign-in controls are visible; copying and saving remain available without signing in. All notices follow the 34 interface-language bundles.

## Updates

Direct installs check for published releases at startup and offer an in-app download, with progress, cancellation, size and SHA-256 verification. Opening the installer is explicit; VibeZ does not silently install or restart. Store installations keep Microsoft Store delivery. Existing 3.0.2 installations need one manual installation to acquire this new downloader.

## macOS

The toolbar and content are placed below the actual native titlebar area. The approved correction is included in both Intel and Apple Silicon packages, with Developer ID signing, notarization and stapled tickets. Windows and Linux keep their accepted layout and paste implementation.

## Downloads and requirements

Linux x64: DEB, RPM, AppImage, Arch/Pacman and Flatpak. Windows x64: EXE, MSI and Store submission MSIX. macOS Intel and Apple Silicon: DMG and ZIP. All twelve files are required before publication, from one frozen source commit, with a matching SHA256SUMS file.

Native Linux: Ubuntu 24.04 / Mint 22-class systems with glibc 2.39+ and WebKitGTK 4.1. Linux desktop selection requires X11. macOS 14 or later; Screen Recording permission may be required. Windows 10/11 with WebView2. Full-page screenshots cover loaded content, not unloaded history.

## Installation and release checks

Quit VibeZ completely before replacing a previous installation. Test packages also used version 3.0.3; on Mint install the final DEB with `sudo apt install --reinstall ./VibeZ-3.0.3-Linux-x64.deb`. The final app no longer displays a test label. Existing VibeZ 3 profiles are retained; archived Electron and preview profiles stay separate.

The complete all-format workflow requires dependency auditing, frontend/Rust tests, native browser/window/screenshot checks, Linux UI and monitor checks, package integrity and Apple signing/notarization. Automated fixtures are not a claim of testing every current website, machine, permission state or completed installer-driven upgrade.

The MSIX retains LeComputeur.VibeZDesktop, product 9NR7L2G4MS08, version 3.0.3.0. Package creation is not Microsoft Store submission, certification or publication. Historical Electron feeds keep their original Electron packages, not an incompatible Tauri executable.
''')
 p=Path('CHANGELOG.md');s=p.read_text();at=s.find('\n')+1
 s=s[:at]+'''\n## 3.0.3 — 2026-10-09

Promote maintainer-approved test 7 without changing its functional code. Add the screenshot-as-PNG route for Code, concise Chat/Work clarification and conditional sign-in notice in all 34 languages; preserve direct Chat/Work paste. Include in-app update downloads with progress and integrity checks, and the macOS native-titlebar layout correction. Ship all Linux formats, Windows EXE/MSI/Store MSIX, and signed/notarized Intel and Apple Silicon Mac packages. Store certification is separate from package creation.
'''+s[at:];p.write_text(s)
 marker.write_text('Approved test 7: '+APPROVED+'\nMaintainer authorized stable all-platform rollout on 2026-10-09.\n')
protected=['desktop/frontend','desktop/src-tauri/src','desktop/src-tauri/Cargo.toml','desktop/src-tauri/Cargo.lock','desktop/src-tauri/tauri.conf.json','desktop/src-tauri/capabilities','desktop/src-tauri/permissions','desktop/preview-i18n.json','desktop/screenshot-hints-i18n.json','desktop/updates-i18n.json','tauri-preview','main.js','main-v2.js','package.json','package-lock.json']
subprocess.run(['git','diff','--exit-code',APPROVED,'--',*protected,':(exclude)desktop/src-tauri/src/main.rs'],check=True)
subprocess.run(['git','diff','--exit-code','HEAD','--','.github/workflows'],check=True)
main=Path('desktop/src-tauri/src/main.rs').read_text()
old=subprocess.check_output(['git','show',APPROVED+':desktop/src-tauri/src/main.rs'],text=True)
assert main==old.replace(' · test 7','').replace('"build_label": "test 7"','"build_label": ""')
assert json.loads(Path('desktop/package.json').read_text())['version']=='3.0.3'
print('APPROVED_TEST7_PRESERVED: functional native/frontend code unchanged; release display labels only')
