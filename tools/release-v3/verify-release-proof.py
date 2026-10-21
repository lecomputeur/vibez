#!/usr/bin/env python3
"""Verify immutable, successful all-format CI before merge or publication."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
REPO = 'lecomputeur/vibez'
RELEASES = {
    '3.0.6': ('.github/workflows/v3.0.6-validation.yml', 'vibe/linux-scroll-306-7c3e91'),
    '3.0.7': ('.github/workflows/v3.0.7-validation.yml', 'vibe/linux-rich-render-307'),
    '3.0.9': ('.github/workflows/v3.0.9-validation.yml', 'release/v3.0.9-20261021'),
    '3.0.8': ('.github/workflows/v3.0.8-validation.yml', 'vibe/linux-turnstile-308-b46e90'),
}
NAMES = {
    'Track v3 source and freeze dependencies', 'Dependency security gate',
    'Linux — AppImage, DEB and RPM', 'Linux — Arch/Pacman', 'Linux — Flatpak',
    'Windows — EXE, MSI and Store MSIX', 'macOS — x64 signed DMG and ZIP',
    'macOS — arm64 signed DMG and ZIP', 'All twelve formats and checksums verified',
}
REQUIRED_STEPS = {
    'Dependency security gate': ['JavaScript and Rust advisories'],
    'Windows — EXE, MSI and Store MSIX': [
        'Test and build native Windows app',
        'Actual WebView2 capture, image paste, history and popup tests',
        'Build approved-identity Store package without submitting it',
    ],
    'macOS — x64 signed DMG and ZIP': [
        'Actual WKWebView capture, paste, history, language and window tests',
        'Developer ID signing, notarization and DMG creation',
    ],
    'macOS — arm64 signed DMG and ZIP': [
        'Actual WKWebView capture, paste, history, language and window tests',
        'Developer ID signing, notarization and DMG creation',
    ],
    'All twelve formats and checksums verified': ['Collect all twelve required deliverables'],
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def expected_version():
    return os.environ.get('VIBEZ_RELEASE_VERSION') or json.loads(
        (ROOT / 'desktop/package.json').read_text())['version']


def proof_path(version):
    # Separate proof files prevent old publication workflows from retriggering.
    return ROOT / 'tools/release-v3' / f'release-proof-{version}.json'


def required_steps(version):
    required = {name: list(steps) for name, steps in REQUIRED_STEPS.items()}
    if version in ('3.0.7', '3.0.8', '3.0.9'):
        required.update({
            'Track v3 source and freeze dependencies': [f'Verify immutable {version} build inputs'],
            'Linux — AppImage, DEB and RPM': [
                'Frontend and Rust tests',
                'Rich-chat streaming, Find, resize, wheel and fullscreen regressions',
                'Installer shutdown and AppImage replacement regression',
                'Native history, language, layout and installed icon tests',
                'Screenshot, actual paste and two-monitor regression',
                'Package standalone AppImage', 'Inspect and name installable packages',
            ],
            'Linux — Arch/Pacman': ['Build and verify Arch/Pacman package'],
            'Linux — Flatpak': ['Build and verify Flatpak package'],
        })
    if version in ('3.0.8', '3.0.9'):
        required['Linux — AppImage, DEB and RPM'].append('Native Cloudflare frame and popup routing regression')
    if version == '3.0.9':
        required['Linux — AppImage, DEB and RPM'].append('Native structural navigation, auth boundary, chart pixels and Wry lifecycle')
        for arch in ('x64', 'arm64'):
            required[f'macOS — {arch} signed DMG and ZIP'].append('Verify native Mac architecture and macOS 14 deployment minimum')
    return required


def verify(proof=None, version=None):
    version = version or expected_version()
    require(version in RELEASES, f'No reviewed workflow mapping for release {version}')
    if proof is None:
        path = proof_path(version)
        require(path.is_file(), f'No verified {version} proof yet: {path.name}; record it only after successful CI')
        proof = json.loads(path.read_text())
    source, head, run_id = proof.get('source'), proof.get('workflow_head'), proof.get('run_id')
    require(proof.get('version') == version, 'Proof version does not match the requested release')
    require(isinstance(source, str) and re.fullmatch(r'[0-9a-f]{40}', source), 'Invalid proof source SHA')
    require(head == source, 'Validation must build its immutable event commit')
    require(type(run_id) is int and run_id > 0, 'Proof requires a real positive CI run ID')
    require(os.environ.get('GITHUB_REPOSITORY', REPO) == REPO, 'Wrong repository')
    workflow, branch = RELEASES[version]
    run = json.loads(command('gh', 'api', f'repos/{REPO}/actions/runs/{run_id}'))
    require(run['repository']['full_name'] == REPO and run['head_sha'] == head, 'CI source/repository mismatch')
    require(run['path'] == workflow and run['head_branch'] == branch, 'Unexpected validation workflow or branch')
    require(run['status'] == 'completed' and run['conclusion'] == 'success', 'All-format CI has not succeeded')
    jobs = json.loads(command('gh', 'api', f'repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100&filter=latest'))['jobs']
    require(len(jobs) == 9 and {j['name'] for j in jobs} == NAMES, 'All nine platform/security jobs are required')
    require(all(j['status'] == 'completed' and j['conclusion'] == 'success' for j in jobs), 'A required CI job is incomplete or failed')
    required = required_steps(version)
    for job in jobs:
        for name in required.get(job['name'], []):
            matches = [s for s in job.get('steps', []) if s['name'] == name]
            require(len(matches) == 1 and matches[0]['status'] == 'completed' and matches[0]['conclusion'] == 'success',
                    f'Required step did not succeed: {job["name"]} / {name}')
    command('git', 'merge-base', '--is-ancestor', source, 'HEAD')
    # Post-build publication checks and text may change. Every application,
    # dependency, packaging/signing input and the validation workflow stay frozen.
    exceptions = [
        'desktop/README.md', 'tools/release-v3/release-proof.json',
        f'tools/release-v3/release-proof-{version}.json',
        'tools/release-v3/verify-release-proof.py', 'tools/release-v3/record-release-proof.py',
        'tools/release-v3/verify-msix.py', 'tools/release-v3/legacy-feed.cjs',
        'tools/release-v3/tests',
    ]
    command('git', 'diff', '--exit-code', source, 'HEAD', '--',
            'desktop', 'icon.png', 'shell.css', 'i18n.js', 'locales',
            'tools/release-v3', workflow, *[':(exclude)' + p for p in exceptions])
    # Check the independently uploaded Git archive, not only a text label.
    with tempfile.TemporaryDirectory(prefix='vibez-release-proof-') as directory:
        command('gh', 'run', 'download', str(run_id), '--repo', REPO, '--name', 'v3-source', '--dir', directory)
        require((Path(directory) / 'source-commit.txt').read_text().strip() == source, 'Source artifact label mismatch')
        archive = gzip.decompress((Path(directory) / 'v3-source.tar.gz').read_bytes())
        archived_commit = subprocess.check_output(['git', 'get-tar-commit-id'], input=archive, cwd=ROOT).decode().strip()
        require(archived_commit == source, 'Uploaded source archive is not the validated Git commit')
    print(f'RELEASE_PROOF_OK: {version}; {source}; all nine jobs and required native/signing/packaging steps succeeded')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version')
    args = parser.parse_args()
    try:
        verify(version=args.version)
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
