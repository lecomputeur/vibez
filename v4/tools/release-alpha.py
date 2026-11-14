#!/usr/bin/python3
"""Release a VibeZ V4 Alpha in fixed, checked steps.

Alpha 25, 26 and 27 were released with the same twenty commands typed by hand.
This tool holds that sequence. Every step checks what the previous steps left
behind in `_claude-build/release-alphaNN/` and stops with a clear message when
something is missing. Nothing here publishes without the explicit `publish`
step, and `--dry-run` prints the commands instead of running them.

  bump        next version in the source tree, changes and highlights in release.json
  freeze      private git repo, snapshot, encrypted source, CI workflow and branch
  ci-start    upload the encrypted source, push the branch, start the workflow
  linux       deb, rpm, Arch, Flatpak and AppImage from this source tree
  ci-collect  wait for the workflow, verify the frozen-source proofs, gather 13 packages
  feeds       signed update feeds for all 13 formats
  draft       the English release text and a draft prerelease with 11 assets
  publish     publish the prerelease, update the channels and the Flatpak branch,
              record published_version, open the downloads pull request
  status      what exists for this release

Secrets are used in place only: the GPG passphrase file and the minisign key
are passed as paths to gpg and the feed tool, never read or printed here.
VibeZ 3.0.9 and its channel are never touched; every release is a prerelease.
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
BUNDLE = BUILD / 'release-alpha23/ci/vibez-alpha-private.bundle'
APPIMAGE_TOOLS = BUILD / 'release-alpha24/appimage-tools'
AUTHOR = ['-c', 'user.name=lecomputeur', '-c', 'user.email=121440176+lecomputeur@users.noreply.github.com']
VERSION_RE = re.compile(r'^4\.0\.0-(alpha|beta)\.([1-9]\d*)$')
# The Beta follows the last Alpha; Alpha 31 taught every Alpha install to accept it.
LAST_ALPHA = '4.0.0-alpha.31'
VERSION_FILES = ['backend/standalone_engine.py', 'backend/web_connector.py', 'backend/workspace_engine.py', 'desktop/package-lock.json',
                 'desktop/package.json', 'desktop/src-tauri/Cargo.lock', 'desktop/src-tauri/Cargo.toml', 'desktop/src-tauri/tauri.conf.json']
LINUX_FORMATS = ['AppImage', 'deb', 'flatpak', 'pkg.tar.zst', 'rpm']
RELEASE_ASSETS = ['Linux-x64.AppImage', 'Linux-x64.deb', 'Linux-x64.flatpak', 'Linux-x64.pkg.tar.zst', 'Linux-x64.rpm',
                  'macOS-arm64.app.tar.gz', 'macOS-arm64.dmg', 'macOS-x64.app.tar.gz', 'macOS-x64.dmg',
                  'Windows-x64-Setup.exe', 'Windows-x64.msi']
FEED_ONLY = ['macOS-arm64.zip', 'macOS-x64.zip']


class StepError(Exception):
    pass


def stage_of(version):
    match = VERSION_RE.match(version or '')
    if not match:
        raise StepError('Not a V4 Alpha or Beta version: %r' % (version,))
    return match.group(1), int(match.group(2))


def alpha_number(version):
    return stage_of(version)[1]


def tag(version):
    """alpha31, beta1: used in folder and branch names."""
    stage, number = stage_of(version)
    return '%s%d' % (stage, number)


def label(version):
    """Alpha 31, Beta 1: used in titles and messages."""
    stage, number = stage_of(version)
    return '%s %d' % (stage.capitalize(), number)


def previous_of(version):
    stage, number = stage_of(version)
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


def asset_names(version):
    return ['VibeZ-%s-%s' % (version, suffix) for suffix in RELEASE_ASSETS]


def feed_names(version):
    return ['VibeZ-%s-%s' % (version, suffix) for suffix in RELEASE_ASSETS + FEED_ONLY]


def workflow_for(previous_text, previous, version, file_count):
    """The CI workflow of the previous Alpha, retargeted at this one."""
    text = previous_text.replace(previous, version)
    old_label, new_label = label(previous).replace(' ', ''), label(version).replace(' ', '')
    text = re.sub(r"\['4\.0\.0-alpha\.14','4\.0\.0-(?:alpha|beta)\.\d+'\]", "['4.0.0-alpha.14','%s']" % previous, text)
    text = re.sub(r'==\d+ and len\(set\(names\)\)', '==%d and len(set(names))' % file_count, text)
    text = text.replace('frozen %s' % old_label, 'frozen %s' % new_label)
    # The source asset name check accepts Beta archives as well as Alpha ones.
    text = text.replace(r"VibeZ-4\.0\.0-alpha\.\d+-native-source-", r"VibeZ-4\.0\.0-(?:alpha|beta)\.\d+-native-source-")
    # Windows also leaves a Store package (MSIX) for Partner Center, outside the release assets.
    if 'alpha-source/artifacts/ci-store/*' not in text:
        text = text.replace("            alpha-source/artifacts/ci-packages/*\n", "            alpha-source/artifacts/ci-packages/*\n            alpha-source/artifacts/ci-store/*\n")
    needles = [version, "'%s'" % previous, '==%d and' % file_count, 'frozen %s' % new_label]
    if 'native-source-' in previous_text: needles.append(r'(?:alpha|beta)\.\d+-native-source-')
    if 'ci-packages/*' in previous_text: needles.append('ci-store/*')
    for needle in needles:
        if needle not in text:
            raise StepError('Workflow retargeting failed at ' + needle)
    return text


def release_body(spec, previous):
    changes = ''.join('- %s\n' % line for line in spec['changes'])
    store = ('The Microsoft Store version (VibeZ Desktop V4) follows separately and is updated by the Store.' if stage_of(spec['version'])[0] == 'beta'
             else 'No MSIX is included.')
    return ('## VibeZ V4 %s\n\n**Available for Linux, Windows, Intel Mac and Apple Silicon.**\n\n'
            'The main difference from VibeZ 3 is local-folder access: keep your existing Mistral web conversations and link folders on your computer to a project or conversation. '
            'Browse those files in the right-hand panel and review proposed changes before saving them.\n\n'
            'V4 installs separately from VibeZ 3.0.9 and keeps its own profile and settings. It does not overwrite or remove 3.0.9.\n\n'
            '### Changes since %s\n\n%s\n### Please help test V4\n\n'
            'Try it with copies of test files. Feedback on automatic folder linking in Mistral Work, especially how long a link takes after restarting VibeZ, is very welcome. '
            'The Diagnostics window (Settings → Diagnostics) has a **Copy report** button with the step timing and connection facts, without keys or full addresses; pasting that report helps a lot.\n\n'
            '[Share feedback](https://github.com/lecomputeur/vibez/discussions/56) or [report a bug](https://github.com/lecomputeur/vibez/issues/new/choose), '
            'including your operating system, package format and exact version.\n\n'
            'Automatic updates use the separate V4 channels, apart from VibeZ 3. Use an installer for the first installation. On macOS, choose the DMG for your processor; '
            '`.app.tar.gz` files are used by automatic updates. %s\n') % (label(spec['version']), label(previous), changes, store)


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
        shutil.rmtree(output)
        result = m.check(BASE)
        self.say('manage.py check: version %s, passed %s' % (result['version'], result['passed']))
        # Not a gate: Mistral tolerates a server that negotiates down, but the
        # maintainer should know when the published specification moved on.
        check = subprocess.run([sys.executable, str(BASE / 'tools/check-mcp-versions.py')], capture_output=True, text=True)
        self.say('MCP versions: ' + (check.stdout.strip().splitlines() or ['no report'])[-1])

    def freeze(self):
        passphrase = self.args.passphrase_file or os.environ.get('VIBEZ_ALPHA_PASSPHRASE_FILE')
        if not passphrase:
            raise StepError('freeze needs --passphrase-file (or VIBEZ_ALPHA_PASSPHRASE_FILE)')
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
        ci = self.dir / 'ci'; ci.mkdir(exist_ok=True)
        for old in ci.glob('VibeZ-%s-native-source-*.tar.gz.gpg' % self.version):
            (ci / 'superseded').mkdir(exist_ok=True); shutil.move(str(old), ci / 'superseded' / old.name)
        encrypted = ci / 'source.tar.gz.gpg'
        self.run(['gpg', '--batch', '--yes', '--no-symkey-cache', '--pinentry-mode', 'loopback', '--passphrase-file', passphrase,
                  '--cipher-algo', 'AES256', '--symmetric', '--output', encrypted, archive], quiet=True)
        if self.dry:
            return
        digest = hashlib.sha256(encrypted.read_bytes()).hexdigest()
        name = 'VibeZ-%s-native-source-%s.tar.gz.gpg' % (self.version, digest[:16])
        encrypted.rename(ci / name)
        # Binary round trip: the decrypted archive must be the snapshot, byte for byte.
        raw = subprocess.run(['gpg', '--batch', '--no-symkey-cache', '--pinentry-mode', 'loopback', '--passphrase-file', passphrase, '--decrypt', str(ci / name)],
                             capture_output=True).stdout
        if hashlib.sha256(raw).hexdigest() != hashlib.sha256(archive.read_bytes()).hexdigest():
            raise StepError('Encrypted source does not decrypt to the snapshot')
        count, manifest = source_manifest(archive)
        request = {'version': self.version, 'source_version': self.version,
                   'url': 'https://github.com/%s/releases/download/%s/%s' % (REPO, CHANNEL_TAG, name), 'sha256': digest,
                   'source_manifest_sha256': manifest, 'file_count': count, 'targets': ['windows-x64', 'macos-x64', 'macos-arm64']}
        (ci / 'alpha-build-request.json').write_text(json.dumps(request, indent=2) + '\n')
        previous_yml = self.need(self.previous_dir / 'ci/v4-alpha-build.yml', 'previous workflow')
        (ci / 'v4-alpha-build.yml').write_text(workflow_for(previous_yml.read_text(), self.previous, self.version, count))
        self.say('frozen source: %d files, manifest %s' % (count, manifest[:16]))
        gh_repo = self.dir / 'gh-repo'
        branch = 'vibe/%s-release-%s' % (self.tag, self.date)
        if not gh_repo.exists():
            self.run(['git', 'clone', '-q', '--filter=blob:none', 'https://github.com/%s.git' % REPO, gh_repo])
            self.run(['git', 'checkout', '-q', '-b', branch, 'origin/main'], cwd=gh_repo)
        (gh_repo / '.github/workflows').mkdir(parents=True, exist_ok=True)
        shutil.copy2(ci / 'v4-alpha-build.yml', gh_repo / '.github/workflows/v4-alpha-build.yml')
        shutil.copy2(ci / 'alpha-build-request.json', gh_repo / 'alpha-build-request.json')
        self.run(['git', 'add', '.github/workflows/v4-alpha-build.yml', 'alpha-build-request.json'], cwd=gh_repo)
        if self.run(['git', 'status', '--porcelain'], cwd=gh_repo, capture=True).stdout.strip():
            self.run(['git'] + AUTHOR + ['commit', '-q', '-m', 'Build frozen V4 %s native packages' % self.label], cwd=gh_repo)
        (self.dir / 'release-meta.json').write_text(json.dumps({'version': self.version, 'previous': self.previous, 'branch': branch, 'source': name}, indent=1) + '\n')
        self.say('CI branch %s ready in %s' % (branch, gh_repo))

    def meta(self):
        path = self.need(self.dir / 'release-meta.json', 'release-meta.json (run freeze first)')
        return json.loads(path.read_text()) if not self.dry else {'branch': 'vibe/%s-release-%s' % (self.tag, self.date), 'source': 'SOURCE.gpg'}

    def ci_start(self):
        meta = self.meta(); gh_repo = self.dir / 'gh-repo'
        source = self.need(self.dir / 'ci' / meta['source'], 'encrypted source')
        self.run(['gh', 'release', 'upload', CHANNEL_TAG, '--repo', REPO, source])
        self.run(['git', '-C', gh_repo, 'push', 'origin', meta['branch']])
        self.run(['gh', 'workflow', 'run', 'v4-alpha-build.yml', '--repo', REPO, '--ref', meta['branch']])
        if self.dry:
            return
        time.sleep(20)
        run_id = self.run(['gh', 'run', 'list', '--repo', REPO, '--workflow', 'v4-alpha-build.yml', '--branch', meta['branch'], '--limit', '1',
                           '--json', 'databaseId', '-q', '.[0].databaseId'], capture=True).stdout.strip()
        (self.dir / 'ci/run-id.txt').write_text(run_id + '\n')
        self.say('workflow run %s started' % run_id)

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

    def ci_collect(self):
        run_id = self.need(self.dir / 'ci/run-id.txt', 'run-id.txt (run ci-start first)').read_text().strip() if not self.dry else 'RUN'
        self.run(['gh', 'run', 'watch', run_id, '--repo', REPO, '--exit-status', '--interval', '30'], timeout=7200)
        artifacts = self.dir / 'ci-artifacts'
        shutil.rmtree(artifacts, ignore_errors=True)
        if not self.dry: artifacts.mkdir()
        self.run(['gh', 'run', 'download', run_id, '--repo', REPO, '--dir', artifacts])
        if self.dry:
            return
        # A rerun of a failed job (Apple refused notarization four times on
        # 13 Nov 2026) leaves one artifact per attempt: alpha-<target>-<attempt>.
        # Only the last attempt of each target counts.
        latest = {}
        for folder in sorted(artifacts.iterdir()):
            target, _, attempt = folder.name.rpartition('-')
            if folder.is_dir() and target and attempt.isdigit():
                latest[target] = max(latest.get(target, 0), int(attempt))
        for folder in list(artifacts.iterdir()):
            target, _, attempt = folder.name.rpartition('-')
            if folder.is_dir() and attempt.isdigit() and int(attempt) < latest.get(target, 0):
                shutil.rmtree(folder)
                self.say('ignored earlier attempt ' + folder.name) if hasattr(self, 'say') else print('* ignored earlier attempt ' + folder.name)
        want = json.loads((self.dir / 'ci/alpha-build-request.json').read_text())['source_manifest_sha256']
        proofs = 0
        for proof in artifacts.glob('*/vibez/vibez/alpha-source/artifacts/ci-proof/frozen-source-*.json'):
            data = json.loads(proof.read_text())
            if not (data.get('passed') and data.get('source_manifest_sha256') == want):
                raise StepError('Frozen-source proof failed: ' + proof.name)
            proofs += 1
        if proofs != 3:
            raise StepError('Expected 3 frozen-source proofs, found %d' % proofs)
        for sums in artifacts.glob('*/vibez/vibez/alpha-source/artifacts/ci-packages/SHA256SUMS'):
            self.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS'], cwd=sums.parent)
        packages = self.dir / 'packages-13'
        shutil.rmtree(packages, ignore_errors=True); packages.mkdir()
        for item in artifacts.glob('*/vibez/vibez/alpha-source/artifacts/ci-packages/VibeZ-*'):
            shutil.copy2(item, packages / item.name)
        for suffix in LINUX_FORMATS:
            shutil.copy2(self.need(self.dir / ('VibeZ-%s-Linux-x64.%s' % (self.version, suffix)), 'Linux package (run linux first)'), packages)
        names = sorted(p.name for p in packages.iterdir())
        if names != sorted(feed_names(self.version)):
            raise StepError('packages-13 differs from the 13 expected files: %s' % names)
        self.say('13 packages verified in %s' % packages)
        # The Beta's Windows build also leaves the Microsoft Store package. It is
        # never a release asset: the maintainer uploads it in Partner Center.
        if stage_of(self.version)[0] == 'beta':
            store = self.dir / 'store'
            shutil.rmtree(store, ignore_errors=True); store.mkdir()
            found = list(artifacts.glob('*/vibez/vibez/alpha-source/artifacts/ci-store/VibeZ-*.msix'))
            if len(found) != 1 or found[0].name != 'VibeZ-%s-Windows-x64-Store.msix' % self.version:
                raise StepError('Expected one Store MSIX from the Windows build, found %s' % [p.name for p in found])
            shutil.copy2(found[0], store / found[0].name)
            self.say('Store package for Partner Center in %s' % store)

    def feeds(self):
        key = self.args.minisign_key or os.environ.get('VIBEZ_ALPHA_MINISIGN_KEY')
        if not key:
            raise StepError('feeds needs --minisign-key (or VIBEZ_ALPHA_MINISIGN_KEY)')
        packages = self.need(self.dir / 'packages-13', 'packages-13 (run ci-collect first)')
        notes = self.dir / 'feed-notes.txt'
        if not notes.exists() and not self.dry:
            notes.write_text('V4 %s: %s VibeZ 3.0.9 stays separate.' % (self.label, self.spec['changes'][0].split('. ')[0] + '.'))
        out = self.dir / 'feeds-out'
        shutil.rmtree(out, ignore_errors=True)
        with self.logfile('feeds.log') as log:
            command = [sys.executable, 'tools/prepare-alpha-update-feeds.py', '--artifacts', packages, '--output', out, '--version', self.version,
                       '--previous-version', self.previous, '--minisign-private-key', key, '--gpg-homedir', Path.home() / '.vibez4-alpha-signing', '--notes-file', notes]
            if self.dry:
                self.run(command)
            else:
                subprocess.run([str(c) for c in command], cwd=str(BASE), stdout=log, stderr=subprocess.STDOUT, timeout=1200, check=True)
        if self.dry:
            return
        proof = json.loads((out / 'feed-proof.json').read_text())
        if not (proof.get('passed') and proof.get('all_artifact_signatures_verified') and proof.get('all_gpg_signatures_verified') and proof.get('complete_format_count') == 13):
            raise StepError('Feed proof failed: %s' % {k: proof.get(k) for k in ('passed', 'complete_format_count')})
        upload = out / 'upload'; upload.mkdir()
        for item in (out / 'channel').iterdir():
            shutil.copy2(item, upload / item.name)
        for name in ('alpha', 'alpha-linux'):
            shutil.copy2(out / 'channel' / (name + '.json'), upload / ('%s-%s.json' % (name, self.version)))
            shutil.copy2(out / 'channel' / (name + '.json.asc'), upload / ('%s-%s.json.asc' % (name, self.version)))
        self.say('feeds for 13 formats signed; upload set in %s' % upload)

    def draft(self):
        packages = self.need(self.dir / 'packages-13', 'packages-13')
        body = self.dir / 'release-body.md'
        if not body.exists() and not self.dry:
            body.write_text(release_body(self.spec, self.previous))
        title = self.args.title or 'VibeZ V4 %s' % self.label
        assets = [packages / name for name in asset_names(self.version)]
        self.run(['gh', 'release', 'create', 'v' + self.version, '--repo', REPO, '--draft', '--prerelease', '--latest=false', '--title', title, '--notes-file', body] + assets)
        if self.dry:
            return
        remote = json.loads(self.run(['gh', 'release', 'view', 'v' + self.version, '--repo', REPO, '--json', 'isDraft,isPrerelease,assets'], capture=True).stdout)
        sizes = {a['name']: a['size'] for a in remote['assets']}
        if not remote['isDraft'] or not remote['isPrerelease'] or len(sizes) != 11:
            raise StepError('Draft release is not a draft prerelease with 11 assets')
        for asset in assets:
            if sizes.get(asset.name) != asset.stat().st_size:
                raise StepError('Asset size differs: ' + asset.name)
        self.say('draft v%s: 11 assets, sizes verified' % self.version)

    def publish(self):
        upload = self.need(self.dir / 'feeds-out/upload', 'feed upload set (run feeds first)')
        self.run(['gh', 'release', 'edit', 'v' + self.version, '--repo', REPO, '--draft=false', '--prerelease', '--latest=false'])
        if not self.dry:
            latest = self.run(['gh', 'api', 'repos/%s/releases/latest' % REPO, '-q', '.tag_name'], capture=True).stdout.strip()
            if latest != 'v3.0.9':
                raise StepError('Latest release changed to %s; stop and check' % latest)
        before = self.dir / 'channel-before'
        if not self.dry: before.mkdir(exist_ok=True)
        for name in ('alpha.json', 'alpha.json.asc', 'alpha-linux.json', 'alpha-linux.json.asc'):
            self.run(['gh', 'release', 'download', CHANNEL_TAG, '--repo', REPO, '--pattern', name, '--dir', before, '--clobber'], check=False)
        versioned = ['%s-%s.json%s' % (name, self.version, ext) for name in ('alpha', 'alpha-linux') for ext in ('', '.asc')]
        self.run(['gh', 'release', 'upload', CHANNEL_TAG, '--repo', REPO] + [upload / n for n in versioned])
        self.run(['gh', 'release', 'upload', CHANNEL_TAG, '--repo', REPO, '--clobber'] + [upload / n for n in ('alpha.json', 'alpha.json.asc', 'alpha-linux.json', 'alpha-linux.json.asc')])
        publication = self.need(self.dir / ('flatpak-publication-%s' % self.version), 'Flatpak publication (run linux first)')
        worktree = self.dir / 'flatpak-wt'; gh_repo = self.dir / 'gh-repo'
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
        self.run(['git', 'add', 'README.md', 'docs/index.html', 'docs/linux.html', 'docs/macos.html', 'docs/windows.html'], cwd=gh_repo)
        self.run(['git'] + AUTHOR + ['commit', '-q', '-m', 'Refresh V4 %s downloads and highlights' % self.label], cwd=gh_repo)
        self.run(['git', '-C', gh_repo, 'push', 'origin', branch])
        self.run(['gh', 'pr', 'create', '--repo', REPO, '--base', 'main', '--head', branch, '--title', 'Refresh V4 %s downloads and highlights' % self.label,
                  '--body', 'Points the V4 Alpha download buttons in README.md and docs/ to the published v%s prerelease and refreshes the highlights. '
                            'VibeZ 3.0.9 remains the stable release; its downloads and links are unchanged.' % self.version])
        self.say('published v%s; channels and Flatpak branch updated; downloads PR opened (merge after review)' % self.version)

    def status(self):
        checks = {'release dir': self.dir, 'private repo': self.dir / 'repo', 'snapshot': self.dir / 'snapshot/private-source.tar.gz',
                  'encrypted source': self.dir / 'ci', 'run id': self.dir / 'ci/run-id.txt', 'packages-13': self.dir / 'packages-13',
                  'feeds': self.dir / 'feeds-out/feed-proof.json', 'release body': self.dir / 'release-body.md', 'flatpak worktree': self.dir / 'flatpak-wt'}
        for label, path in checks.items():
            print('%-18s %s %s' % (label, 'ok ' if path.exists() else '-- ', path))
        for suffix in LINUX_FORMATS:
            path = self.dir / ('VibeZ-%s-Linux-x64.%s' % (self.version, suffix))
            print('%-18s %s %s' % (suffix, 'ok ' if path.exists() else '-- ', path.name))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('step', choices=['bump', 'freeze', 'ci-start', 'linux', 'ci-collect', 'feeds', 'draft', 'publish', 'status'])
    parser.add_argument('--version', help='release version (default: management/release.json)')
    parser.add_argument('--next', help='bump: the next version')
    parser.add_argument('--changes-file', help='bump: one release change per line')
    parser.add_argument('--highlights', help='bump: download_highlights for the public site')
    parser.add_argument('--message', help='freeze: commit message for the private repo')
    parser.add_argument('--passphrase-file', help='freeze: GPG passphrase file (read by gpg only)')
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
