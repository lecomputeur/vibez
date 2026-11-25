#!/usr/bin/python3
"""Release a VibeZ V4 Alpha in fixed, checked steps.

Alpha 25, 26 and 27 were released with the same twenty commands typed by hand.
This tool holds that sequence. Every step checks what the previous steps left
behind in `_claude-build/release-alphaNN/` and stops with a clear message when
something is missing. Nothing here publishes without the explicit `publish`
step, and `--dry-run` prints the commands instead of running them.

Since 17 November 2026 VibeZ is winding down: Mistral released the official
Vibe Desktop for macOS and Windows. Releases are Linux-only until the official
Linux app is available. There is no native CI for Windows or macOS and no
Microsoft Store package any more; Beta 5 was the last version for them.

  bump        next version in the source tree, changes and highlights in release.json
  freeze      private git repo and source snapshot of this release
  linux       deb, rpm, Arch, Flatpak and AppImage from this source tree
  collect     gather and check the five Linux packages
  feeds       signed Linux-only update feeds for the five formats
  draft       the English release text and a draft prerelease with 5 assets
  publish     publish the prerelease, update the channels and the Flatpak branch,
              record published_version, open the downloads pull request
  migration   prepare the Linux packages that take existing 3.x clients to VibeZ 4
  migration-draft
              create a separate draft for the 3.x updater without changing Latest
  migration-publish
              publish the verified 3.x updater entry after testing the draft
  status      what exists for this release

Secrets are used in place only: the minisign key is passed as a path to the
feed tool, never read or printed here.
The separate 3.x migration is opt-in for the maintainer. Alpha and Beta versions are prereleases;
a final 4.x.y (4.0.0 on 18 Nov 2026) is published as Latest, with the legacy
Electron feed files copied from the previous Latest so VibeZ 2.x stays quiet.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
BUILD = BASE / '_claude-build'
REPO = 'lecomputeur/vibez'
CHANNEL_TAG = 'v4-alpha-channel'
FLATPAK_BRANCH = 'v4-alpha-flatpak'
MIGRATION_TAG = 'v3.2.1'
MIGRATION_VERSION = '4.0.1'
MIGRATION_FORMATS = ('AppImage', 'deb', 'rpm', 'pkg.tar.zst')
BUNDLE = BUILD / 'release-alpha23/ci/vibez-alpha-private.bundle'
APPIMAGE_TOOLS = BUILD / 'release-alpha24/appimage-tools'
AUTHOR = ['-c', 'user.name=lecomputeur', '-c', 'user.email=121440176+lecomputeur@users.noreply.github.com']
VERSION_RE = re.compile(r'^4\.0\.0-(alpha|beta)\.([1-9]\d*)$')
FINAL_RE = re.compile(r'^4\.0\.(0|[1-9]\d*)$')
# The final 4.0.0 follows the last Beta; 4.0.1 and later fix Linux only.
LAST_BETA = '4.0.0-beta.5'
LEGACY_FEEDS = ['latest.yml', 'latest-linux.yml', 'latest-mac.yml']
# The Beta follows the last Alpha; Alpha 31 taught every Alpha install to accept it.
LAST_ALPHA = '4.0.0-alpha.31'
VERSION_FILES = ['backend/standalone_engine.py', 'backend/web_connector.py', 'backend/workspace_engine.py', 'desktop/package-lock.json',
                 'desktop/package.json', 'desktop/src-tauri/Cargo.lock', 'desktop/src-tauri/Cargo.toml', 'desktop/src-tauri/tauri.conf.json']
LINUX_FORMATS = ['AppImage', 'deb', 'flatpak', 'pkg.tar.zst', 'rpm']
# Linux only since the wind-down (17 Nov 2026): the official Vibe Desktop serves Windows and macOS.
RELEASE_ASSETS = ['Linux-x64.AppImage', 'Linux-x64.deb', 'Linux-x64.flatpak', 'Linux-x64.pkg.tar.zst', 'Linux-x64.rpm']
OFFICIAL_APP = 'https://mistral.ai/products/vibe/'


class StepError(Exception):
    pass


def stage_of(version):
    final = FINAL_RE.match(version or '')
    if final:
        return 'final', int(final.group(1))
    match = VERSION_RE.match(version or '')
    if not match:
        raise StepError('Not a V4 Alpha, Beta or final 4.0.x version: %r' % (version,))
    return match.group(1), int(match.group(2))


def is_final(version):
    return stage_of(version)[0] == 'final'


def alpha_number(version):
    return stage_of(version)[1]


def tag(version):
    """alpha31, beta1, 4.0.0: used in folder and branch names."""
    stage, number = stage_of(version)
    return version if stage == 'final' else '%s%d' % (stage, number)


def label(version):
    """Alpha 31, Beta 1, 4.0.0: used in titles and messages."""
    stage, number = stage_of(version)
    return version if stage == 'final' else '%s %d' % (stage.capitalize(), number)


def previous_of(version):
    stage, number = stage_of(version)
    if stage == 'final':
        return LAST_BETA if number == 0 else '4.0.%d' % (number - 1)
    if stage == 'beta' and number == 1:
        return LAST_ALPHA
    return '4.0.0-%s.%d' % (stage, number - 1)


def manage():
    spec = importlib.util.spec_from_file_location('alpha_release_manage', BASE / 'management/manage.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def load_release():
    return json.loads((BASE / 'management/release.json').read_text())


def save_release(spec):
    (BASE / 'management/release.json').write_text(json.dumps(spec, indent=2, ensure_ascii=False) + '\n')


CHANGELOG = BASE / 'desktop/src-tauri/src/changelog.json'


def record_changelog(version, changes, today=None):
    """Put this version's changes at the top of the changelog the app shows after an update (a rerun replaces them)."""
    data = json.loads(CHANGELOG.read_text())
    versions = [entry for entry in data.get('versions', []) if entry.get('version') != version]
    versions.insert(0, {'version': version, 'date': today or time.strftime('%Y-%m-%d'), 'changes': list(changes)})
    data['versions'] = versions
    CHANGELOG.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n')


def asset_names(version):
    return ['VibeZ-%s-%s' % (version, suffix) for suffix in RELEASE_ASSETS]


def feed_names(version):
    return asset_names(version)


def final_body(spec, previous):
    changes = ''.join('- %s\n' % line for line in spec['changes'])
    return ('## VibeZ %s for Linux\n\n'
            'VibeZ 4 brings Mistral Work and Code to your own folders on Linux. Keep the familiar Mistral web interface, '
            'link a local folder to a project or conversation, browse its files beside the chat, and let Mistral search, read and propose changes. '
            'Every edit, move or deletion is a proposal you approve in VibeZ; nothing on your disk changes without you.\n\n'
            '### Changes since %s\n\n%s\n'
            '### Thank you\n\n'
            'VibeZ 4 grew through more than thirty Alphas and five Betas. Thank you to [ActiveUser435](https://github.com/ActiveUser435), '
            'who tested nearly every Alpha in depth, to [HumanistAtypik](https://github.com/HumanistAtypik), whose careful reports made VibeZ work on '
            'non-standard Linux systems, and to everyone who tested, starred and shared feedback.\n\n'
            '### Installing\n\n'
            'Choose the AppImage, DEB, RPM, Arch package or Flatpak for your distribution; the [Linux installation guide]'
            '(https://lecomputeur.github.io/vibez/linux.html#v4-alpha) explains each one. VibeZ 4 installs separately from VibeZ 3 and keeps its own '
            'profile and settings. Installs of the Alphas and Betas update to %s automatically.\n\n'
            'Mistral released the official [Vibe Desktop](%s) for macOS and Windows; VibeZ for Linux stays supported until the official Linux app is available. '
            '[Report a Linux problem](https://github.com/lecomputeur/vibez/issues/new/choose) with your distribution, package format and exact version.\n'
            ) % (spec['version'], label(previous), changes, spec['version'], OFFICIAL_APP)


def release_body(spec, previous):
    if is_final(spec['version']):
        return final_body(spec, previous)
    changes = ''.join('- %s\n' % line for line in spec['changes'])
    # The tester agreed to be thanked by username only (issue 49, 2026-11-13).
    thanks = ('### Thanks\n\nThank you to [ActiveUser435](https://github.com/ActiveUser435) and [HumanistAtypik](https://github.com/HumanistAtypik) '
              'for their detailed testing and reports.\n\n')
    return ('## VibeZ V4 %s\n\n**Available for Linux.**\n\n'
            'Mistral released the official [Vibe Desktop](%s) for macOS and Windows, so VibeZ is winding down. '
            'Until the official Linux app is available, VibeZ keeps supporting Linux with fixes. '
            'On Windows and macOS, please use the official app; V4 Beta 5 was the last VibeZ version for them.\n\n'
            'V4 lets Mistral Work and Code use local folders you choose, with every file change shown for your approval. '
            'It installs separately from VibeZ 3 and keeps its own profile and settings.\n\n'
            '### Changes since %s\n\n%s\n%s'
            '[Report a Linux problem](https://github.com/lecomputeur/vibez/issues/new/choose) with your distribution, package format and exact version.\n\n'
            'Automatic updates use the separate V4 channels, apart from VibeZ 3. Use an installer for the first installation. No MSIX is included.\n'
            ) % (label(spec['version']), OFFICIAL_APP, label(previous), changes, thanks)


def source_manifest(archive):
    with tarfile.open(archive) as stream:
        names = sorted(member.name for member in stream.getmembers())
        records = [{'path': name, 'sha256': hashlib.sha256(stream.extractfile(name).read()).hexdigest()} for name in names]
    return len(names), hashlib.sha256(json.dumps(records, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Release:
    def __init__(self, args):
        self.args = args
        self.spec = load_release()
        self.version = args.version or self.spec['version']
        self.number = alpha_number(self.version)
        self.tag, self.label = tag(self.version), label(self.version)
        self.previous = previous_of(self.version)
        self.dir = BUILD / ('release-' + self.tag)
        self.previous_dir = BUILD / ('release-' + tag(self.previous))
        self.dry = args.dry_run
        self.date = time.strftime('%Y%m%d')

    # ---- running things ---------------------------------------------------
    def run(self, command, *, cwd=None, check=True, capture=False, env=None, timeout=None, quiet=False):
        shown = ' '.join(shlex.quote(str(part)) for part in command)
        if self.dry:
            print('  $ ' + shown)
            return subprocess.CompletedProcess(command, 0, '', '')
        if not quiet:
            print('  $ ' + shown[:160])
        result = subprocess.run([str(part) for part in command], cwd=str(cwd) if cwd else None, text=True,
                                capture_output=capture, env=env, timeout=timeout)
        if check and result.returncode != 0:
            raise StepError('Command failed (%d): %s' % (result.returncode, shown[:200]))
        return result

    def logfile(self, name):
        """A log file in the release directory; nothing is opened in a dry run."""
        return contextlib.nullcontext(None) if self.dry else (self.dir / name).open('w')

    def need(self, path, what):
        if not self.dry and not Path(path).exists():
            raise StepError('Missing %s: %s' % (what, path))
        return Path(path)

    def say(self, text):
        print('* ' + text)

    def private_repo(self, release_dir, previous_dir):
        """The release's private git checkout: the bundle, fast-forwarded to the previous release."""
        self.need(BUNDLE, 'private git bundle'); self.need(previous_dir / 'repo', 'previous private repo')
        repo = release_dir / 'repo'
        release_dir.mkdir(exist_ok=True)
        if not repo.exists():
            self.run(['git', 'clone', '-q', BUNDLE, repo])
            self.run(['git', 'fetch', '-q', previous_dir / 'repo', 'main:previous'], cwd=repo)
            self.run(['git', 'merge', '-q', '--ff-only', 'previous'], cwd=repo)
        return repo

    def copy_sources(self, repo):
        if self.dry:
            return
        files = json.loads((BASE / 'management/source-files.json').read_text())['files']
        # The maintainer guides live in the private repository too; keep them current.
        guides = [name for name in ('README.md', 'management/README.md') if (BASE / name).is_file()]
        # Maintainer tools outside the build source (the snapshot runs manage.py
        # from this repo) must not lag behind: Beta 1 stopped on an old copy.
        guides += [name for name in ('management/manage.py', 'management/test_manage.py', 'tools/prepare-alpha-update-feeds.py') if (BASE / name).is_file()]
        for name in files + ['management/release.json', 'management/source-files.json', '.gitignore'] + guides:
            target = repo / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(BASE / name, target)
        # Approved files win over nested ignore rules (desktop/.gitignore hides the
        # autogenerated Tauri permission files that the manifest approves).
        self.run(['git', 'add', '-f', '--'] + files + guides, cwd=repo, quiet=True)
        self.say('copied %d source files into the private repo' % len(files))

    # ---- steps ------------------------------------------------------------
    def bump(self):
        m = manage()
        current = self.spec['version']
        if not self.args.next:
            raise StepError('bump needs --next 4.0.0-alpha.N or 4.0.0-beta.N')
        changes = [line.strip() for line in Path(self.args.changes_file).read_text().splitlines() if line.strip()] if self.args.changes_file else []
        if not changes:
            raise StepError('bump needs --changes-file with one change per line')
        output = BUILD / ('plan-%s' % self.args.next)
        if output.exists():
            shutil.rmtree(output)
        self.say('planning %s from %s' % (self.args.next, current))
        if self.dry:
            return
        # The V4 source is public; a release must contain what was merged there.
        sync = subprocess.run([sys.executable, str(BASE / 'tools/sync-public-v4.py'), 'check'], capture_output=True, text=True)
        if sync.returncode:
            raise StepError('public v4/ is ahead of this tree or conflicts with it:\n' + sync.stdout.strip())
        self.say('public v4/: ' + (sync.stdout.strip().splitlines() or ['checked'])[0].lstrip('* '))
        # The source folder has no .git; the plan needs a committed checkout,
        # so the next release's private repo starts here with today's sources.
        repo = self.private_repo(BUILD / ('release-' + tag(self.args.next)), self.dir)
        self.copy_sources(repo)
        self.run(['git', 'add', '-A'], cwd=repo)
        if self.run(['git', 'status', '--porcelain'], cwd=repo, capture=True).stdout.strip():
            self.run(['git'] + AUTHOR + ['commit', '-q', '-m', 'Sources before V4 %s' % label(self.args.next)], cwd=repo)
        m.plan(repo, self.args.next, output)
        for name in VERSION_FILES:
            shutil.copy2(output / 'files' / name, BASE / name)
        spec = json.loads((output / 'files/management/release.json').read_text())
        spec['installed_version'] = self.spec.get('installed_version')
        spec['changes'] = changes
        if self.args.highlights:
            spec['download_highlights'] = ' '.join(self.args.highlights.split())
        save_release(spec)
        record_changelog(self.args.next, changes)
        shutil.rmtree(output)
        result = m.check(BASE)
        self.say('manage.py check: version %s, passed %s' % (result['version'], result['passed']))
        # Not a gate: Mistral tolerates a server that negotiates down, but the
        # maintainer should know when the published specification moved on.
        check = subprocess.run([sys.executable, str(BASE / 'tools/check-mcp-versions.py')], capture_output=True, text=True)
        self.say('MCP versions: ' + (check.stdout.strip().splitlines() or ['no report'])[-1])

    def freeze(self):
        """Commit this release's sources in the private repo and keep a source snapshot; no CI is needed for Linux."""
        repo = self.private_repo(self.dir, self.previous_dir)
        self.copy_sources(repo)
        self.run(['git', 'add', '-A'], cwd=repo)
        status = self.run(['git', 'status', '--porcelain'], cwd=repo, capture=True).stdout
        if status.strip() or self.dry:
            message = self.args.message or 'V4 %s: %s' % (self.label, self.spec['changes'][0][:60])
            self.run(['git'] + AUTHOR + ['commit', '-q', '-m', message], cwd=repo)
        snapshot = self.dir / 'snapshot'
        if snapshot.exists():
            shutil.rmtree(snapshot)
        self.run([sys.executable, 'management/manage.py', 'snapshot', '--output', snapshot], cwd=repo)
        archive = self.need(snapshot / 'private-source.tar.gz', 'snapshot archive')
        if self.dry:
            return
        count, manifest = source_manifest(archive)
        (self.dir / 'release-meta.json').write_text(json.dumps({'version': self.version, 'previous': self.previous, 'file_count': count,
                                                                 'source_manifest_sha256': manifest}, indent=1) + '\n')
        self.say('frozen source: %d files, manifest %s' % (count, manifest[:16]))

    def gh_repo(self):
        """A clone of the public repository for the Flatpak branch and the downloads pull request."""
        gh_repo = self.dir / 'gh-repo'
        if not gh_repo.exists():
            self.run(['git', 'clone', '-q', '--filter=blob:none', 'https://github.com/%s.git' % REPO, gh_repo])
        return gh_repo

    def linux(self):
        tools = self.need(APPIMAGE_TOOLS, 'AppImage tools')
        desktop = BASE / 'desktop'
        self.run(['node', 'scripts/prepare.cjs'], cwd=desktop)
        with self.logfile('tauri-build.log') as log:
            self.run(['npx', 'tauri', 'build', '--bundles', 'deb', '--config', '{"bundle":{"createUpdaterArtifacts":false}}', '--', '--offline', '--locked'],
                     cwd=desktop, timeout=1800, env=dict(os.environ)) if self.dry else subprocess.run(
                ['npx', 'tauri', 'build', '--bundles', 'deb', '--config', '{"bundle":{"createUpdaterArtifacts":false}}', '--', '--offline', '--locked'],
                cwd=str(desktop), stdout=log, stderr=subprocess.STDOUT, timeout=1800, check=True)
        # Every package tool refuses to replace an existing package, so a rerun
        # after a failure only builds what is still missing.
        def missing(suffix):
            return self.dry or not (self.dir / ('VibeZ-%s-Linux-x64.%s' % (self.version, suffix))).exists()
        deb = desktop / ('src-tauri/target/release/bundle/deb/VibeZ V4 Alpha_%s_amd64.deb' % self.version)
        if missing('deb'):
            self.run([sys.executable, 'tools/package-alpha-linux.py', '--deb', deb, '--output-dir', self.dir, '--payload', self.dir / 'payload'], cwd=BASE)
        if missing('rpm'):
            self.run([sys.executable, 'tools/alpha-rpm.py', '--payload', self.dir / 'payload', '--output', self.dir / ('VibeZ-%s-Linux-x64.rpm' % self.version)], cwd=BASE)
        if missing('pkg.tar.zst'):
            self.run([sys.executable, 'tools/alpha-arch.py', '--payload', self.dir / 'payload', '--output', self.dir / ('VibeZ-%s-Linux-x64.pkg.tar.zst' % self.version)], cwd=BASE)
        env = dict(os.environ, VIBEZ_GPG_HOME=str(Path.home() / '.vibez4-alpha-signing'))
        if missing('flatpak'):
            with self.logfile('flatpak-build.log') as log:
                if self.dry:
                    self.run(['bash', BUILD / 'bouw-flatpak.sh'])
                else:
                    subprocess.run(['bash', str(BUILD / 'bouw-flatpak.sh')], env=env, stdout=log, stderr=subprocess.STDOUT, timeout=3000, check=True)
        if not missing('AppImage'):
            self.say('five Linux packages in %s' % self.dir)
            return
        shutil.rmtree(desktop / 'src-tauri/target/release/bundle/appimage', ignore_errors=True)
        env = dict(os.environ, PATH=str(tools / 'squashfs-root/usr/bin') + ':' + os.environ.get('PATH', ''))
        with self.logfile('appimage-deploy.log') as log:
            if self.dry:
                self.run(['npx', 'tauri', 'build', '-v', '--bundles', 'appimage'], cwd=desktop)
            else:
                # linuxdeploy stops at a known icon error after deploying everything;
                # finish-alpha-appimage.py checks the log for exactly that failure and completes the AppDir.
                subprocess.run(['npx', 'tauri', 'build', '-v', '--bundles', 'appimage', '--config', '{"bundle":{"createUpdaterArtifacts":false}}', '--', '--offline', '--locked'],
                               cwd=str(desktop), env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800, check=False)
        appimage = self.dir / ('VibeZ-%s-Linux-x64.AppImage' % self.version)
        with self.logfile(appimage.name + '.json') as out, self.logfile('appimage-finish.err') as err:
            command = [sys.executable, 'tools/finish-alpha-appimage.py', '--appdir', desktop / 'src-tauri/target/release/bundle/appimage/VibeZ V4 Alpha.AppDir',
                       '--deployment-log', self.dir / 'appimage-deploy.log', '--gstreamer-plugin', Path.home() / '.cache/tauri/linuxdeploy-plugin-gstreamer.sh',
                       '--patchelf', tools / 'squashfs-root/usr/bin/patchelf', '--appimage-tool', tools / 'appimagetool-x86_64.AppImage',
                       '--runtime-file', tools / 'runtime-x86_64', '--output', appimage]
            if self.dry:
                self.run(command)
            else:
                subprocess.run([str(c) for c in command], cwd=str(BASE), stdout=out, stderr=err, timeout=1200, check=True)
        if not self.dry:
            proof = json.loads(appimage.with_suffix('.AppImage.json').read_text())
            if not proof.get('passed'):
                raise StepError('AppImage proof failed')
            for suffix in LINUX_FORMATS:
                self.need(self.dir / ('VibeZ-%s-Linux-x64.%s' % (self.version, suffix)), 'Linux package')
        self.say('five Linux packages in %s' % self.dir)

    def collect(self):
        """The five Linux packages of this release, side by side, ready for signing."""
        self.need(self.dir / 'release-meta.json', 'release-meta.json (run freeze first)')
        packages = self.dir / 'packages'
        if not self.dry:
            shutil.rmtree(packages, ignore_errors=True); packages.mkdir()
        for suffix in LINUX_FORMATS:
            source = self.need(self.dir / ('VibeZ-%s-Linux-x64.%s' % (self.version, suffix)), 'Linux package (run linux first)')
            if not self.dry:
                shutil.copy2(source, packages)
        if self.dry:
            return
        names = sorted(p.name for p in packages.iterdir())
        if names != sorted(feed_names(self.version)):
            raise StepError('packages differs from the 5 expected Linux files: %s' % names)
        self.say('5 Linux packages in %s' % packages)

    def feeds(self):
        key = self.args.minisign_key or os.environ.get('VIBEZ_ALPHA_MINISIGN_KEY')
        if not key:
            raise StepError('feeds needs --minisign-key (or VIBEZ_ALPHA_MINISIGN_KEY)')
        packages = self.need(self.dir / 'packages', 'packages (run collect first)')
        notes = self.dir / 'feed-notes.txt'
        if not notes.exists() and not self.dry:
            notes.write_text('V4 %s for Linux: %s VibeZ 3 stays separate.' % (self.label, self.spec['changes'][0].split('. ')[0] + '.'))
        out = self.dir / 'feeds-out'
        shutil.rmtree(out, ignore_errors=True)
        with self.logfile('feeds.log') as log:
            command = [sys.executable, 'tools/prepare-alpha-update-feeds.py', '--artifacts', packages, '--output', out, '--version', self.version,
                       '--previous-version', self.previous, '--minisign-private-key', key, '--gpg-homedir', Path.home() / '.vibez4-alpha-signing', '--notes-file', notes,
                       '--linux-only']
            if self.dry:
                self.run(command)
            else:
                subprocess.run([str(c) for c in command], cwd=str(BASE), stdout=log, stderr=subprocess.STDOUT, timeout=1200, check=True)
        if self.dry:
            return
        proof = json.loads((out / 'feed-proof.json').read_text())
        if not (proof.get('passed') and proof.get('all_artifact_signatures_verified') and proof.get('all_gpg_signatures_verified') and proof.get('complete_format_count') == len(LINUX_FORMATS) and proof.get('scope') == 'linux-only'):
            raise StepError('Feed proof failed: %s' % {k: proof.get(k) for k in ('passed', 'complete_format_count')})
        upload = out / 'upload'; upload.mkdir()
        for item in (out / 'channel').iterdir():
            shutil.copy2(item, upload / item.name)
        for name in ('alpha', 'alpha-linux'):
            shutil.copy2(out / 'channel' / (name + '.json'), upload / ('%s-%s.json' % (name, self.version)))
            shutil.copy2(out / 'channel' / (name + '.json.asc'), upload / ('%s-%s.json.asc' % (name, self.version)))
        self.say('Linux-only feeds for 5 formats signed; upload set in %s' % upload)

    def draft(self):
        packages = self.need(self.dir / 'packages', 'packages (run collect first)')
        body = self.dir / 'release-body.md'
        if not body.exists() and not self.dry:
            body.write_text(release_body(self.spec, self.previous))
        final = is_final(self.version)
        title = self.args.title or ('VibeZ %s for Linux' % self.version if final else 'VibeZ V4 %s' % self.label)
        assets = [packages / name for name in asset_names(self.version)]
        if final:
            # VibeZ 2.x (Electron) reads latest*.yml from whatever release is Latest; carry over the
            # files that keep it on 2.0.2, exactly as every VibeZ 3 release did.
            legacy = self.dir / 'legacy-feed'
            if not self.dry: legacy.mkdir(exist_ok=True)
            current = self.run(['gh', 'api', 'repos/%s/releases/latest' % REPO, '-q', '.tag_name'], capture=True).stdout.strip() if not self.dry else 'v3.2.0'
            self.run(['gh', 'release', 'download', current, '--repo', REPO, '--dir', legacy, '--clobber'] + sum((['--pattern', n] for n in LEGACY_FEEDS), []))
            assets += [legacy / n for n in LEGACY_FEEDS]
        kind = [] if final else ['--prerelease', '--latest=false']
        self.run(['gh', 'release', 'create', 'v' + self.version, '--repo', REPO, '--draft'] + kind + ['--title', title, '--notes-file', body] + assets)
        if self.dry:
            return
        remote = json.loads(self.run(['gh', 'release', 'view', 'v' + self.version, '--repo', REPO, '--json', 'isDraft,isPrerelease,assets'], capture=True).stdout)
        sizes = {a['name']: a['size'] for a in remote['assets']}
        if not remote['isDraft'] or remote['isPrerelease'] == final or len(sizes) != len(assets):
            raise StepError('Draft release is not a draft %s with %d assets' % ('release' if final else 'prerelease', len(assets)))
        for asset in assets:
            if sizes.get(asset.name) != asset.stat().st_size:
                raise StepError('Asset size differs: ' + asset.name)
        self.say('draft v%s: %d assets, sizes verified' % (self.version, len(assets)))

    def publish(self):
        upload = self.need(self.dir / 'feeds-out/upload', 'feed upload set (run feeds first)')
        final = is_final(self.version)
        if not self.dry:
            latest = self.run(['gh', 'api', 'repos/%s/releases/latest' % REPO, '-q', '.tag_name'], capture=True).stdout.strip()
            # Before 4.0.0, Latest was the VibeZ 3 line; a final 4.0.x replaces it, an Alpha or Beta never does.
            if not re.fullmatch(r'v3\.\d+\.\d+|v4\.0\.\d+', latest) or (not final and not latest.startswith('v3.')):
                raise StepError('Latest release is %s; stop and check' % latest)
        self.run(['gh', 'release', 'edit', 'v' + self.version, '--repo', REPO, '--draft=false'] + (['--prerelease=false', '--latest'] if final else ['--prerelease', '--latest=false']))
        if final and not self.dry:
            latest = self.run(['gh', 'api', 'repos/%s/releases/latest' % REPO, '-q', '.tag_name'], capture=True).stdout.strip()
            if latest != 'v' + self.version:
                raise StepError('v%s did not become Latest (Latest is %s)' % (self.version, latest))
        before = self.dir / 'channel-before'
        if not self.dry: before.mkdir(exist_ok=True)
        for name in ('alpha.json', 'alpha.json.asc', 'alpha-linux.json', 'alpha-linux.json.asc'):
            self.run(['gh', 'release', 'download', CHANNEL_TAG, '--repo', REPO, '--pattern', name, '--dir', before, '--clobber'], check=False)
        versioned = ['%s-%s.json%s' % (name, self.version, ext) for name in ('alpha', 'alpha-linux') for ext in ('', '.asc')]
        self.run(['gh', 'release', 'upload', CHANNEL_TAG, '--repo', REPO] + [upload / n for n in versioned])
        self.run(['gh', 'release', 'upload', CHANNEL_TAG, '--repo', REPO, '--clobber'] + [upload / n for n in ('alpha.json', 'alpha.json.asc', 'alpha-linux.json', 'alpha-linux.json.asc')])
        publication = self.need(self.dir / ('flatpak-publication-%s' % self.version), 'Flatpak publication (run linux first)')
        worktree = self.dir / 'flatpak-wt'; gh_repo = self.gh_repo()
        if not worktree.exists():
            self.run(['git', 'fetch', '-q', 'origin', FLATPAK_BRANCH], cwd=gh_repo)
            self.run(['git', 'worktree', 'add', '-q', worktree, 'FETCH_HEAD', '-b', 'v4-alpha-flatpak-update-%s' % self.tag], cwd=gh_repo)
            if not self.dry:
                shutil.copytree(publication, worktree, dirs_exist_ok=True)
            self.run(['git', 'add', '-A'], cwd=worktree)
            self.run(['git'] + AUTHOR + ['commit', '-q', '-m', 'Publish signed V4 %s Flatpak update' % self.label], cwd=worktree)
        self.run(['git', 'push', 'origin', 'HEAD:' + FLATPAK_BRANCH], cwd=worktree)
        if not self.dry:
            spec = load_release(); spec['published_version'] = self.version; save_release(spec)
            repo = self.dir / 'repo'
            shutil.copy2(BASE / 'management/release.json', repo / 'management/release.json')
            self.run(['git', 'add', 'management/release.json'], cwd=repo)
            self.run(['git'] + AUTHOR + ['commit', '-q', '-m', 'Record V4 %s as published' % self.label], cwd=repo)
        branch = 'vibe/%s-release-downloads-%s' % (self.tag, self.date)
        self.run(['git', 'fetch', '-q', 'origin', 'main'], cwd=gh_repo)
        self.run(['git', 'checkout', '-q', '-B', branch, 'origin/main'], cwd=gh_repo)
        self.run([sys.executable, 'tools/refresh-alpha-downloads.py', '--site', gh_repo, '--check-links'], cwd=BASE)
        # Windows and macOS pages are a fixed archive since the wind-down.
        self.run(['git', 'add', 'README.md', 'docs/index.html', 'docs/linux.html'], cwd=gh_repo)
        self.run(['git'] + AUTHOR + ['commit', '-q', '-m', 'Refresh V4 %s downloads and highlights' % self.label], cwd=gh_repo)
        # The site check wants each sitemap date to be the page's last change: today's commit.
        if (gh_repo / 'tools/site/sitemap-lastmod.py').exists():
            self.run([sys.executable, 'tools/site/sitemap-lastmod.py'], cwd=gh_repo)
            self.run(['git', 'add', 'docs/sitemap.xml'], cwd=gh_repo)
            self.run(['git'] + AUTHOR + ['commit', '-q', '--amend', '--no-edit'], cwd=gh_repo)
        self.run(['git', '-C', gh_repo, 'push', 'origin', branch])
        self.run(['gh', 'pr', 'create', '--repo', REPO, '--base', 'main', '--head', branch, '--title', 'Refresh V4 %s downloads and highlights' % self.label,
                  '--body', 'Points the V4 Linux download buttons in README.md, docs/index.html and docs/linux.html to the published v%s release and refreshes the highlights. '
                            'The Windows and macOS archive pages and the VibeZ 3 downloads are unchanged.' % self.version])
        self.say('published v%s; channels and Flatpak branch updated; downloads PR opened (merge after review)' % self.version)

    def migration(self):
        """The installed V3 updater requires a 3.x tag and 3.x asset names."""
        if self.version != MIGRATION_VERSION:
            raise StepError('The one-time VibeZ 3 migration installs VibeZ ' + MIGRATION_VERSION)
        output = self.dir / 'migration-v3'
        packages = self.need(self.dir / 'packages', 'packages (run collect first)')
        payload = self.need(self.dir / 'payload', 'native package payload')
        self.migration_assets(packages, payload, output)

    def migration_assets(self, packages, payload, output):
        targets = {ext: output / ('VibeZ-%s-Linux-x64.%s' % (MIGRATION_TAG[1:], ext))
                   for ext in MIGRATION_FORMATS}
        if self.dry:
            self.say('prepare %s with VibeZ %s packages in %s' % (MIGRATION_TAG, self.version, output))
            return
        import tempfile
        from alpha_linux_payload import updater
        helper = updater()
        if output.exists():
            raise StepError('Migration staging already exists: %s' % output)
        self.need(packages / ('VibeZ-%s-Linux-x64.AppImage' % self.version), 'verified V4 AppImage')
        with tempfile.TemporaryDirectory(prefix='migration-', dir=output.parent) as stage:
            stage = Path(stage)
            artifacts = stage / 'assets'
            artifacts.mkdir()
            assets = {ext: artifacts / path.name for ext, path in targets.items()}
            old = {ext: packages / ('VibeZ-%s-Linux-x64.%s' % (self.version, ext))
                   for ext in MIGRATION_FORMATS}
            shutil.copy2(old['AppImage'], assets['AppImage'])
            helper.validate_deb(old['deb'], self.version)
            deb = stage / 'deb'
            self.run(['dpkg-deb', '-R', old['deb'], deb])
            control = deb / 'DEBIAN/control'
            contents = control.read_text()
            contents = contents.replace(f'Version: {self.version}\n', f'Version: {self.version}+v3migration1\n', 1)
            # Insert within the first control paragraph, before the description.
            control.write_text(contents.replace('Description:', 'Conflicts: vibe-z-3\nReplaces: vibe-z-3\nDescription:', 1))
            self.run(['dpkg-deb', '--root-owner-group', '-Zxz', '--build', deb, assets['deb']])
            helper.validate_deb(assets['deb'], self.version, migrate_v3=True)
            for ext, tool in [('rpm', 'alpha-rpm.py'), ('pkg.tar.zst', 'alpha-arch.py')]:
                self.run([sys.executable, BASE / 'tools' / tool, '--payload', payload,
                          '--output', assets[ext], '--migrate-v3'])
            checksums = []
            for path in assets.values():
                with path.open('rb') as package:
                    checksum = hashlib.file_digest(package, 'sha256').hexdigest()
                checksums.append(f'{checksum}  {path.name}\n')
            (artifacts / 'SHA256SUMS').write_text(''.join(checksums))
            artifacts.rename(output)
        self.say('prepared %s Linux migration packages in %s' % (MIGRATION_TAG, output))

    def migration_draft(self):
        if self.version != MIGRATION_VERSION:
            raise StepError('The one-time VibeZ 3 migration installs VibeZ ' + MIGRATION_VERSION)
        output = self.need(self.dir / 'migration-v3', 'migration assets (run migration first)')
        if not self.dry:
            target = json.loads(self.run(
                ['gh', 'release', 'view', 'v' + self.version, '--repo', REPO,
                 '--json', 'isDraft,isPrerelease'], capture=True).stdout)
            if target['isDraft'] or target['isPrerelease']:
                raise StepError('Publish stable VibeZ 4 before staging the 3.x migration')
            self.run(['sha256sum', '--strict', '--check', 'SHA256SUMS'], cwd=output)
        assets = [output / ('VibeZ-%s-Linux-x64.%s' % (MIGRATION_TAG[1:], ext))
                  for ext in MIGRATION_FORMATS]
        notes = ('One-time Linux update for existing VibeZ 3 installations. '
                 f'The DEB, RPM, Arch and AppImage assets install VibeZ {MIGRATION_VERSION}. '
                 'Use the package matching your existing installation. '
                 'For Flatpak, use the [VibeZ 4 Linux download]'
                 f'(https://github.com/{REPO}/releases/tag/v{MIGRATION_VERSION}).')
        self.run(['gh', 'release', 'create', MIGRATION_TAG, '--repo', REPO, '--draft',
                  '--latest=false', '--title', 'VibeZ 3 to VibeZ 4 migration for Linux',
                  '--notes', notes, *assets, output / 'SHA256SUMS'])

    def migration_publish(self):
        if self.version != MIGRATION_VERSION:
            raise StepError('Publish the migration from the VibeZ ' + MIGRATION_VERSION + ' release')
        output = self.need(self.dir / 'migration-v3', 'migration assets (run migration first)')
        if not self.dry:
            latest = self.run(['gh', 'api', f'repos/{REPO}/releases/latest', '-q', '.tag_name'],
                              capture=True).stdout.strip()
            if latest != 'v' + MIGRATION_VERSION:
                raise StepError('Expected the migration target to be the current V4 Latest release')
            self.run(['sha256sum', '--strict', '--check', 'SHA256SUMS'], cwd=output)
            draft = json.loads(self.run(
                ['gh', 'api', '--paginate', f'repos/{REPO}/releases?per_page=100',
                 '--jq', f'.[] | select(.tag_name == "{MIGRATION_TAG}")'], capture=True).stdout)
            checksums = {(name, 'sha256:' + checksum)
                         for checksum, name in (line.split() for line in (output / 'SHA256SUMS').read_text().splitlines())}
            uploaded = {(asset['name'], asset.get('digest')) for asset in draft['assets']
                        if asset['name'] != 'SHA256SUMS'}
            if not draft['draft'] or draft['prerelease'] or uploaded != checksums:
                raise StepError('Migration draft status or uploaded checksums differ')
        self.run(['gh', 'release', 'edit', MIGRATION_TAG, '--repo', REPO, '--draft=false', '--latest=false'])

    def status(self):
        checks = {'release dir': self.dir, 'private repo': self.dir / 'repo', 'snapshot': self.dir / 'snapshot/private-source.tar.gz',
                  'release meta': self.dir / 'release-meta.json', 'packages': self.dir / 'packages',
                  'feeds': self.dir / 'feeds-out/feed-proof.json', 'release body': self.dir / 'release-body.md', 'flatpak worktree': self.dir / 'flatpak-wt'}
        for label, path in checks.items():
            print('%-18s %s %s' % (label, 'ok ' if path.exists() else '-- ', path))
        for suffix in LINUX_FORMATS:
            path = self.dir / ('VibeZ-%s-Linux-x64.%s' % (self.version, suffix))
            print('%-18s %s %s' % (suffix, 'ok ' if path.exists() else '-- ', path.name))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('step', choices=['bump', 'freeze', 'linux', 'collect', 'feeds', 'draft', 'publish',
                                        'migration', 'migration-draft', 'migration-publish', 'status'])
    parser.add_argument('--version', help='release version (default: management/release.json)')
    parser.add_argument('--next', help='bump: the next version')
    parser.add_argument('--changes-file', help='bump: one release change per line')
    parser.add_argument('--highlights', help='bump: download_highlights for the public site')
    parser.add_argument('--message', help='freeze: commit message for the private repo')
    parser.add_argument('--minisign-key', help='feeds: minisign private key file (read by the feed tool only)')
    parser.add_argument('--title', help='draft: release title')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    release = Release(args)
    try:
        getattr(release, args.step.replace('-', '_'))()
    except StepError as error:
        print('STOP: %s' % error)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
