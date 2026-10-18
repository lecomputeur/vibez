import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('release_proof', ROOT / 'tools/release-v3/verify-release-proof.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class ReleaseProofTests(unittest.TestCase):
    def ci_fixture(self, version='3.0.7'):
        proof = {'version': version, 'source': '1' * 40,
                 'workflow_head': '1' * 40, 'run_id': 123}
        workflow, branch = verifier.RELEASES[version]
        run = {'repository': {'full_name': verifier.REPO}, 'head_sha': proof['source'],
               'path': workflow, 'head_branch': branch,
               'status': 'completed', 'conclusion': 'success'}
        requirements = verifier.required_steps(version)
        jobs = [{'name': name, 'status': 'completed', 'conclusion': 'success',
                 'steps': [{'name': step, 'status': 'completed', 'conclusion': 'success'}
                           for step in requirements.get(name, [])]}
                for name in sorted(verifier.NAMES)]
        return proof, run, jobs

    def test_historical_proof_cannot_authorize_new_release(self):
        with patch.object(verifier, 'command') as command:
            with self.assertRaisesRegex(ValueError, 'Proof version'):
                verifier.verify(proof={'version': '3.0.6'}, version='3.0.7')
            command.assert_not_called()

    def test_pending_proof_without_real_run_id_rejected_before_network(self):
        with patch.object(verifier, 'command') as command:
            with self.assertRaisesRegex(ValueError, 'real positive CI run ID'):
                verifier.verify(proof={'version': '3.0.7', 'source': '1' * 40,
                                       'workflow_head': '1' * 40, 'run_id': None}, version='3.0.7')
            command.assert_not_called()

    def test_different_build_and_source_commits_rejected(self):
        with patch.object(verifier, 'command') as command:
            with self.assertRaisesRegex(ValueError, 'immutable event commit'):
                verifier.verify(proof={'version': '3.0.7', 'source': '1' * 40,
                                       'workflow_head': '2' * 40, 'run_id': 123}, version='3.0.7')
            command.assert_not_called()

    def test_in_progress_workflow_cannot_authorize_publication(self):
        proof, run, _ = self.ci_fixture()
        run.update(status='in_progress', conclusion=None)
        with patch.object(verifier, 'command', return_value=json.dumps(run)) as command:
            with self.assertRaisesRegex(ValueError, 'CI has not succeeded'):
                verifier.verify(proof, '3.0.7')
            self.assertEqual(command.call_count, 1)

    def test_failed_notarization_step_cannot_hide_behind_successful_job(self):
        proof, run, jobs = self.ci_fixture()
        mac = next(j for j in jobs if j['name'] == 'macOS — arm64 signed DMG and ZIP')
        next(s for s in mac['steps'] if s['name'] == 'Developer ID signing, notarization and DMG creation')['conclusion'] = 'failure'
        with patch.object(verifier, 'command', side_effect=[json.dumps(run), json.dumps({'jobs': jobs})]):
            with self.assertRaisesRegex(ValueError, 'Required step did not succeed: macOS'):
                verifier.verify(proof, '3.0.7')

    def test_skipped_store_packaging_cannot_authorize_msix(self):
        proof, run, jobs = self.ci_fixture()
        windows = next(j for j in jobs if j['name'] == 'Windows — EXE, MSI and Store MSIX')
        next(s for s in windows['steps'] if s['name'] == 'Build approved-identity Store package without submitting it')['conclusion'] = 'skipped'
        with patch.object(verifier, 'command', side_effect=[json.dumps(run), json.dumps({'jobs': jobs})]):
            with self.assertRaisesRegex(ValueError, 'Required step did not succeed: Windows'):
                verifier.verify(proof, '3.0.7')

    def test_missing_platform_job_rejected(self):
        proof, run, jobs = self.ci_fixture()
        jobs = [j for j in jobs if j['name'] != 'Linux — Flatpak']
        with patch.object(verifier, 'command', side_effect=[json.dumps(run), json.dumps({'jobs': jobs})]):
            with self.assertRaisesRegex(ValueError, 'All nine platform/security jobs'):
                verifier.verify(proof, '3.0.7')

    def test_308_requires_its_reviewed_workflow_and_branch(self):
        self.assertEqual(verifier.RELEASES['3.0.8'],
                         ('.github/workflows/v3.0.8-validation.yml', 'vibe/linux-turnstile-308-b46e90'))
        for field, old_value in [('path', '.github/workflows/v3.0.7-validation.yml'),
                                 ('head_branch', 'vibe/linux-rich-render-307')]:
            with self.subTest(field=field):
                proof, run, _ = self.ci_fixture('3.0.8')
                run[field] = old_value
                with patch.object(verifier, 'command', return_value=json.dumps(run)) as command:
                    with self.assertRaisesRegex(ValueError, 'Unexpected validation workflow or branch'):
                        verifier.verify(proof, '3.0.8')
                    self.assertEqual(command.call_count, 1)

    def test_307_proof_cannot_authorize_308(self):
        proof, _, _ = self.ci_fixture('3.0.7')
        with patch.object(verifier, 'command') as command:
            with self.assertRaisesRegex(ValueError, 'Proof version'):
                verifier.verify(proof, '3.0.8')
            command.assert_not_called()

    def test_308_inherits_all_prior_native_and_packaging_steps(self):
        old = verifier.required_steps('3.0.7')
        current = verifier.required_steps('3.0.8')
        for job, steps in old.items():
            with self.subTest(job=job):
                expected = [step.replace('3.0.7', '3.0.8') for step in steps]
                self.assertTrue(set(expected) <= set(current[job]))
        self.assertNotIn('Native Cloudflare frame and popup routing regression',
                         old['Linux — AppImage, DEB and RPM'])

    def test_308_missing_or_unsuccessful_challenge_step_blocks_publication(self):
        for status in ('missing', 'skipped', 'failure'):
            with self.subTest(status=status):
                proof, run, jobs = self.ci_fixture('3.0.8')
                linux = next(job for job in jobs if job['name'] == 'Linux — AppImage, DEB and RPM')
                name = 'Native Cloudflare frame and popup routing regression'
                if status == 'missing':
                    linux['steps'] = [step for step in linux['steps'] if step['name'] != name]
                else:
                    next(step for step in linux['steps'] if step['name'] == name)['conclusion'] = status
                with patch.object(verifier, 'command', side_effect=[json.dumps(run), json.dumps({'jobs': jobs})]):
                    with self.assertRaisesRegex(ValueError, 'Required step did not succeed: Linux .*Native Cloudflare'):
                        verifier.verify(proof, '3.0.8')

    def test_308_still_requires_mac_notarization_and_store_package(self):
        for job_name, step_name in [
            ('macOS — x64 signed DMG and ZIP', 'Developer ID signing, notarization and DMG creation'),
            ('macOS — arm64 signed DMG and ZIP', 'Developer ID signing, notarization and DMG creation'),
            ('Windows — EXE, MSI and Store MSIX', 'Build approved-identity Store package without submitting it'),
        ]:
            with self.subTest(job=job_name):
                proof, run, jobs = self.ci_fixture('3.0.8')
                job = next(job for job in jobs if job['name'] == job_name)
                next(step for step in job['steps'] if step['name'] == step_name)['conclusion'] = 'skipped'
                with patch.object(verifier, 'command', side_effect=[json.dumps(run), json.dumps({'jobs': jobs})]):
                    with self.assertRaisesRegex(ValueError, 'Required step did not succeed'):
                        verifier.verify(proof, '3.0.8')
