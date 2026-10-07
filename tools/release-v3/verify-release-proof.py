#!/usr/bin/env python3
"""Require exact tested inputs and the entire all-format/security workflow before merge/publication."""
import json, os, re, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
REPO='lecomputeur/vibez'
NAMES={'Track v3 source and freeze dependencies','Dependency security gate','Linux — AppImage, DEB and RPM','Linux — Arch/Pacman','Linux — Flatpak','Windows — EXE, MSI and Store MSIX','macOS — x64 signed DMG and ZIP','macOS — arm64 signed DMG and ZIP','All formats present — prepare GitHub release draft'}
def command(*args):return subprocess.check_output(args,cwd=ROOT,text=True).strip()
def verify():
    proof=json.loads((ROOT/'tools/release-v3/release-proof.json').read_text())
    source=proof['source'];head=proof['workflow_head'];run_id=proof['run_id']
    assert proof['version']=='3.0.2'
    assert re.fullmatch(r'[0-9a-f]{40}',source) and re.fullmatch(r'[0-9a-f]{40}',head)
    assert type(run_id) is int and run_id>0
    assert os.environ.get('GITHUB_REPOSITORY',REPO)==REPO
    run=json.loads(command('gh','api',f'repos/{REPO}/actions/runs/{run_id}'))
    assert run['repository']['full_name']==REPO and run['head_sha']==head
    assert run['path']=='.github/workflows/vibez-v3.yml'
    assert run['head_branch']=='vibe/release-3.0.2-7e2b46'
    assert run['status']=='completed' and run['conclusion']=='success'
    jobs=json.loads(command('gh','api',f'repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100'))['jobs']
    assert len(jobs)==9 and {j['name'] for j in jobs}==NAMES
    assert all(j['status']=='completed' and j['conclusion']=='success' for j in jobs)
    command('git','merge-base','--is-ancestor',head,source)
    command('git','merge-base','--is-ancestor',source,'HEAD')
    command('git','diff','--exit-code',source,'HEAD','--','desktop','icon.png','shell.css','i18n.js','locales','tools/release-v3',':(exclude)tools/release-v3/release-proof.json','.github/workflows/vibez-v3.yml')
    # The source preparation job can commit its frozen lockfile after the initial
    # workflow event. Verify its actual emitted commit rather than pretending
    # the event head was necessarily the compiled source.
    with tempfile.TemporaryDirectory(prefix='vibez-release-proof-') as directory:
        command('gh','run','download',str(run_id),'--repo',REPO,'--name','v3-source','--dir',directory)
        assert (Path(directory)/'source-commit.txt').read_text().strip()==source
    print(f'RELEASE_PROOF_OK: {source}; all nine platform/security gates passed; exact frozen inputs unchanged')
if __name__=='__main__':verify()
