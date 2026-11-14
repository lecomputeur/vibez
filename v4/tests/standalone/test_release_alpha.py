"""The release tool's pure parts: workflow retargeting, asset lists, release text, dry runs."""
import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('release_alpha', BASE / 'tools/release-alpha.py')
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)

WORKFLOW = """name: V4 Alpha build
              assert update_verification['previous_version'] in ['4.0.0-alpha.14','4.0.0-alpha.26']
          assert spec['version']=='4.0.0-alpha.27' and spec['source_version']==spec['version']
              assert len(names)==spec['file_count']==453 and len(set(names))==len(names)
          assert actual==spec['source_manifest_sha256'],'Source does not match approved frozen Alpha27'
          name=spec['url'].rsplit('/',1)[1];assert re.fullmatch(r'VibeZ-4\.0\.0-alpha\.\d+-native-source-[0-9a-f]{16}\.tar\.gz\.gpg',name)
          path: |
            alpha-source/artifacts/ci-packages/*
            alpha-source/artifacts/ci-proof/**/*.json
"""


class ReleaseToolTests(unittest.TestCase):
    def test_workflow_is_retargeted_at_the_next_alpha(self):
        text = tool.workflow_for(WORKFLOW, '4.0.0-alpha.27', '4.0.0-alpha.28', 460)
        self.assertIn("['4.0.0-alpha.14','4.0.0-alpha.27']", text)
        self.assertIn("spec['version']=='4.0.0-alpha.28'", text)
        self.assertIn('==460 and len(set(names))', text)
        self.assertIn('frozen Alpha28', text)
        self.assertNotIn('alpha.27' + "'" + ' and', text)
        with self.assertRaises(tool.StepError):
            tool.workflow_for('nothing to retarget', '4.0.0-alpha.27', '4.0.0-alpha.28', 1)

    def test_the_first_beta_follows_the_last_alpha_and_ships_a_store_package(self):
        self.assertEqual(tool.previous_of('4.0.0-beta.1'), tool.LAST_ALPHA)
        self.assertEqual(tool.previous_of('4.0.0-beta.2'), '4.0.0-beta.1')
        self.assertEqual((tool.tag('4.0.0-beta.1'), tool.label('4.0.0-beta.1')), ('beta1', 'Beta 1'))
        text = tool.workflow_for(WORKFLOW.replace('alpha.27', 'alpha.31').replace('Alpha27', 'Alpha31'), '4.0.0-alpha.31', '4.0.0-beta.1', 480)
        self.assertIn("spec['version']=='4.0.0-beta.1'", text)
        self.assertIn("['4.0.0-alpha.14','4.0.0-alpha.31']", text)
        self.assertIn('frozen Beta1', text)
        self.assertIn(r'VibeZ-4\.0\.0-(?:alpha|beta)\.\d+-native-source-', text)
        self.assertIn('alpha-source/artifacts/ci-store/*', text)
        body = tool.release_body({'version': '4.0.0-beta.1', 'changes': ['A change.']}, '4.0.0-alpha.31')
        self.assertIn('## VibeZ V4 Beta 1', body); self.assertIn('### Changes since Alpha 31', body)
        self.assertIn('Microsoft Store', body); self.assertNotIn('No MSIX', body)
        with self.assertRaises(tool.StepError): tool.stage_of('4.0.0-rc.1')

    def test_asset_lists_match_the_published_shape(self):
        assets = tool.asset_names('4.0.0-alpha.28')
        self.assertEqual(len(assets), 11)
        self.assertNotIn('VibeZ-4.0.0-alpha.28-Linux-x64-Personal.deb', assets)
        self.assertEqual(len(tool.feed_names('4.0.0-alpha.28')), 13)
        self.assertIn('VibeZ-4.0.0-alpha.28-macOS-x64.zip', tool.feed_names('4.0.0-alpha.28'))
        self.assertTrue(all(a.startswith('VibeZ-4.0.0-alpha.28-') for a in assets))

    def test_release_body_lists_the_changes_and_keeps_309_apart(self):
        body = tool.release_body({'version': '4.0.0-alpha.28', 'changes': ['First change.', 'Second change.']}, '4.0.0-alpha.27')
        self.assertIn('## VibeZ V4 Alpha 28', body)
        self.assertIn('### Changes since Alpha 27\n\n- First change.\n- Second change.\n', body)
        self.assertIn('does not overwrite or remove 3.0.9', body)
        self.assertIn('No MSIX is included', body)

    def test_dry_run_prints_commands_and_runs_nothing(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = tool.main(['ci-start', '--version', '4.0.0-alpha.99', '--dry-run'])
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn('gh release upload v4-alpha-channel --repo lecomputeur/vibez', text)
        self.assertIn('gh workflow run v4-alpha-build.yml --repo lecomputeur/vibez --ref vibe/alpha99-release-', text)
        self.assertFalse((tool.BUILD / 'release-alpha99').exists())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main(['draft', '--version', '4.0.0-alpha.99', '--dry-run']), 0)
            self.assertEqual(tool.main(['publish', '--version', '4.0.0-alpha.99', '--dry-run']), 0)

    def test_steps_stop_with_a_message_when_prerequisites_are_missing(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(tool.main(['feeds', '--version', '4.0.0-alpha.99']), 2)
            self.assertEqual(tool.main(['freeze', '--version', '4.0.0-alpha.99']), 2)
            self.assertEqual(tool.main(['bump', '--version', '4.0.0-alpha.99']), 2)
        self.assertEqual(out.getvalue().count('STOP:'), 3)
        self.assertIn('--minisign-key', out.getvalue())
        self.assertIn('--passphrase-file', out.getvalue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
