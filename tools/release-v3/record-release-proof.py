#!/usr/bin/env python3
"""Record a versioned proof only after successful immutable CI and asset checks.

This reads GitHub artifacts and writes one local proof file. It does not commit,
push, create a release, publish packages or submit an MSIX to the Store.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main(run_id):
    spec = importlib.util.spec_from_file_location('release_proof', Path(__file__).with_name('verify-release-proof.py'))
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    version = json.loads((ROOT / 'desktop/package.json').read_text())['version']
    run = json.loads(verifier.command('gh', 'api', f'repos/{verifier.REPO}/actions/runs/{run_id}'))
    proof = {'version': version, 'source': run['head_sha'], 'workflow_head': run['head_sha'], 'run_id': run_id}
    verifier.verify(proof=proof, version=version)
    with tempfile.TemporaryDirectory(prefix='vibez-release-assets-') as directory:
        verifier.command('gh', 'run', 'download', str(run_id), '--repo', verifier.REPO,
                         '--name', 'v3-complete-release', '--dir', directory)
        env = {**os.environ, 'VIBEZ_RELEASE_VERSION': version, 'VIBEZ_RELEASE_SOURCE': proof['source']}
        subprocess.run(['python3', str(Path(__file__).with_name('verify-published-assets.py')), directory],
                       env=env, cwd=ROOT, check=True)
        subprocess.run(['python3', str(Path(__file__).with_name('verify-msix.py')),
                        str(Path(directory) / f'VibeZ-{version}-Windows-x64-Store.msix'), '--version', version],
                       cwd=ROOT, check=True)
    path = verifier.proof_path(version)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(proof, indent=2) + '\n')
    temporary.replace(path)
    print(f'RELEASE_PROOF_RECORDED: {path.name}; CI and actual twelve-asset/MSIX checks succeeded; no publication performed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id', type=int)
    args = parser.parse_args()
    if args.run_id <= 0:
        parser.error('A real positive CI run ID is required')
    main(args.run_id)
