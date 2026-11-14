"""The public download texts follow release.json, and nothing else changes."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('refresh_downloads', BASE / 'tools/refresh-alpha-downloads.py')
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)

README = """<h1>VibeZ 3</h1>
<a href="https://github.com/lecomputeur/vibez/releases/tag/v3.0.9"><strong>Explore VibeZ 3.0.9</strong></a>

> Alpha 26 is available for Linux, Windows, Intel and Apple Silicon Macs. Old highlights here. Updates use the separate V4 Alpha channels.
>
> [Download V4 Alpha 26](https://github.com/lecomputeur/vibez/releases/tag/v4.0.0-alpha.26) · [Share feedback](https://github.com/lecomputeur/vibez/discussions/56)
"""
LINUX = """<p class="alpha-feedback">Alpha 26 is available for Linux, Windows, Intel and Apple Silicon Macs. Old highlights here.</p>
<div class="actions"><a class="button button-primary" href="https://github.com/lecomputeur/vibez/releases/tag/v4.0.0-alpha.26">Download Linux Alpha 26</a></div>
<div class="actions"><a href="https://github.com/lecomputeur/vibez/releases/download/v4.0.0-alpha.26/VibeZ-4.0.0-alpha.26-Linux-x64.flatpak">Alpha 26 · Flatpak</a><a href="https://github.com/lecomputeur/vibez/releases/download/v3.0.9/VibeZ-3.0.9-Linux-x64.deb">3.0.9 DEB</a></div>
<p>VibeZ 3.0.9 improves Linux routing.</p>
"""


class RefreshDownloadsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vibez-downloads-')
        self.site = Path(self.temp.name) / 'site'
        (self.site / 'docs').mkdir(parents=True)
        (self.site / 'README.md').write_text(README)
        for name in ('index', 'linux', 'macos', 'windows'):
            (self.site / 'docs' / (name + '.html')).write_text(LINUX)
        self.release = Path(self.temp.name) / 'release.json'
        self.release.write_text(json.dumps({'version': '4.0.0-alpha.27', 'download_highlights': 'In Mistral Work, linking keeps working after a restart, and the title chip is hidden in sent messages'}))

    def tearDown(self):
        self.temp.cleanup()

    def test_versions_buttons_and_paragraph_follow_release_json(self):
        self.assertEqual(tool.main(['--site', str(self.site), '--release', str(self.release)]), 0)
        readme = (self.site / 'README.md').read_text()
        self.assertIn('> Alpha 27 is available for Linux, Windows, Intel and Apple Silicon Macs. In Mistral Work, linking keeps working after a restart, and the title chip is hidden in sent messages.', readme)
        self.assertNotIn('Old highlights', readme)
        self.assertIn('[Download V4 Alpha 27](https://github.com/lecomputeur/vibez/releases/tag/v4.0.0-alpha.27)', readme)
        self.assertIn('Explore VibeZ 3.0.9', readme)
        linux = (self.site / 'docs/linux.html').read_text()
        self.assertIn('<p class="alpha-feedback">Alpha 27 is available for Linux, Windows, Intel and Apple Silicon Macs. In Mistral Work', linux)
        self.assertIn('VibeZ-4.0.0-alpha.27-Linux-x64.flatpak">Alpha 27 · Flatpak', linux)
        self.assertIn('VibeZ-3.0.9-Linux-x64.deb">3.0.9 DEB', linux, 'the stable release is untouched')
        self.assertIn('VibeZ 3.0.9 improves Linux routing.', linux)
        self.assertNotIn('alpha.26', linux)
        # Running it again changes nothing.
        before = {p: p.read_text() for p in self.site.rglob('*') if p.is_file()}
        self.assertEqual(tool.main(['--site', str(self.site), '--release', str(self.release)]), 0)
        self.assertEqual(before, {p: p.read_text() for p in self.site.rglob('*') if p.is_file()})

    def test_the_first_beta_replaces_the_last_alpha_and_never_goes_back(self):
        self.release.write_text(json.dumps({'version': '4.0.0-beta.1', 'download_highlights': 'The open Beta of VibeZ 4, with Mistral Work and local project folders'}))
        self.assertEqual(tool.main(['--site', str(self.site), '--release', str(self.release)]), 0)
        readme = (self.site / 'README.md').read_text()
        self.assertIn('> Beta 1 is available for Linux, Windows, Intel and Apple Silicon Macs. The open Beta', readme)
        self.assertIn('[Download V4 Beta 1](https://github.com/lecomputeur/vibez/releases/tag/v4.0.0-beta.1)', readme)
        linux = (self.site / 'docs/linux.html').read_text()
        self.assertIn('VibeZ-4.0.0-beta.1-Linux-x64.flatpak">Beta 1 · Flatpak', linux)
        self.assertNotIn('alpha.26', linux); self.assertIn('3.0.9 DEB', linux)
        with self.assertRaises(ValueError):
            tool.refresh_text('README.md', readme, '4.0.0-alpha.40', 'Going back from a Beta to an Alpha is never right')

    def test_dry_run_and_guards(self):
        self.assertEqual(tool.main(['--site', str(self.site), '--release', str(self.release), '--dry-run']), 0)
        self.assertIn('Alpha 26 is available', (self.site / 'README.md').read_text())
        with self.assertRaises(ValueError):
            tool.refresh_text('README.md', README, 25, 'Going back is never right and this text is long enough')
        with self.assertRaises(ValueError):
            tool.clean_highlights('too short')
        with self.assertRaises(ValueError):
            tool.clean_highlights('No <markup> allowed in the highlights paragraph of the public site, ever')
        with self.assertRaises(ValueError):
            tool.refresh_text('docs/x.html', '<p>no paragraph</p> 4.0.0-alpha.26', 27, 'A valid highlights paragraph with enough characters in it')
        self.release.write_text(json.dumps({'version': '4.0.0-alpha.27'}))
        with self.assertRaises(SystemExit):
            tool.main(['--site', str(self.site), '--release', str(self.release)])


if __name__ == '__main__':
    unittest.main(verbosity=2)
