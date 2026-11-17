"""The release tool's pure parts: Linux-only asset lists, release text, dry runs."""
import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('release_alpha', BASE / 'tools/release-alpha.py')
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)

class ReleaseToolTests(unittest.TestCase):
    def test_versions_follow_each_other_and_the_first_beta_follows_the_last_alpha(self):
        self.assertEqual(tool.previous_of('4.0.0-beta.1'), tool.LAST_ALPHA)
        self.assertEqual(tool.previous_of('4.0.0-beta.5'), '4.0.0-beta.4')
        self.assertEqual((tool.tag('4.0.0-beta.5'), tool.label('4.0.0-beta.5')), ('beta5', 'Beta 5'))
        with self.assertRaises(tool.StepError): tool.stage_of('4.0.0-rc.1')

    def test_releases_are_linux_only_after_the_wind_down(self):
        assets = tool.asset_names('4.0.0-beta.5')
        self.assertEqual(assets, ['VibeZ-4.0.0-beta.5-Linux-x64.%s' % s for s in ('AppImage', 'deb', 'flatpak', 'pkg.tar.zst', 'rpm')])
        self.assertEqual(tool.feed_names('4.0.0-beta.5'), assets)
        self.assertFalse([a for a in assets if 'Windows' in a or 'macOS' in a or 'msix' in a.lower()])

    def test_release_body_points_windows_and_mac_to_the_official_app(self):
        body = tool.release_body({'version': '4.0.0-beta.5', 'changes': ['First change.', 'Second change.']}, '4.0.0-beta.4')
        self.assertIn('## VibeZ V4 Beta 5\n\n**Available for Linux.**', body)
        self.assertIn('### Changes since Beta 4\n\n- First change.\n- Second change.\n', body)
        self.assertIn('https://mistral.ai/products/vibe/', body)
        self.assertIn('ActiveUser435', body); self.assertIn('HumanistAtypik', body)
        self.assertIn('No MSIX is included', body)
        self.assertNotIn('Microsoft Store', body); self.assertNotIn('DMG', body)

    def test_bump_puts_the_changes_on_top_of_the_in_app_changelog_and_a_rerun_replaces_them(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            changelog = Path(temp) / 'changelog.json'
            changelog.write_text(json.dumps({'versions': [{'version': '4.0.0-beta.3', 'date': '2026-11-14', 'changes': ['Old.']}]}))
            with patch.object(tool, 'CHANGELOG', changelog):
                tool.record_changelog('4.0.0-beta.4', ['First.'], today='2026-11-20')
                tool.record_changelog('4.0.0-beta.4', ['First.', 'Second.'], today='2026-11-21')
            versions = json.loads(changelog.read_text())['versions']
            self.assertEqual([v['version'] for v in versions], ['4.0.0-beta.4', '4.0.0-beta.3'])
            self.assertEqual(versions[0], {'version': '4.0.0-beta.4', 'date': '2026-11-21', 'changes': ['First.', 'Second.']})
        bundled = json.loads(tool.CHANGELOG.read_text())['versions']
        self.assertTrue(all(v['changes'] and all(isinstance(c, str) and c for c in v['changes']) for v in bundled))

    def test_dry_run_prints_commands_and_runs_nothing(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(tool.main(['collect', '--version', '4.0.0-alpha.99', '--dry-run']), 0)
            self.assertEqual(tool.main(['draft', '--version', '4.0.0-alpha.99', '--dry-run']), 0)
            self.assertEqual(tool.main(['publish', '--version', '4.0.0-alpha.99', '--dry-run']), 0)
        text = out.getvalue()
        self.assertIn('gh release create v4.0.0-alpha.99 --repo lecomputeur/vibez --draft --prerelease', text)
        self.assertIn('Linux-x64.AppImage', text); self.assertNotIn('Windows-x64', text); self.assertNotIn('macOS-', text)
        self.assertIn("git add README.md docs/index.html docs/linux.html", text); self.assertNotIn('docs/windows.html', text)
        self.assertNotIn('gh workflow run', text)
        self.assertFalse((tool.BUILD / 'release-alpha99').exists())
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            tool.main(['ci-start', '--version', '4.0.0-alpha.99', '--dry-run'])

    def test_steps_stop_with_a_message_when_prerequisites_are_missing(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(tool.main(['feeds', '--version', '4.0.0-alpha.99']), 2)
            self.assertEqual(tool.main(['freeze', '--version', '4.0.0-alpha.99']), 2)
            self.assertEqual(tool.main(['collect', '--version', '4.0.0-alpha.99']), 2)
            self.assertEqual(tool.main(['bump', '--version', '4.0.0-alpha.99']), 2)
        self.assertEqual(out.getvalue().count('STOP:'), 4)
        self.assertIn('--minisign-key', out.getvalue())
        self.assertIn('release-meta.json (run freeze first)', out.getvalue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
