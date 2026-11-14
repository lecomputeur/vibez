"""The MCP version check compares what VibeZ speaks with the published specification."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('check_mcp_versions', BASE / 'tools/check-mcp-versions.py')
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)

LISTING = json.dumps([{'name': n, 'type': 'dir'} for n in ['2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25', '2026-07-28', 'draft']] + [{'name': 'index.mdx', 'type': 'file'}])


class McpVersionCheckTests(unittest.TestCase):
    def test_known_versions_come_from_the_engine(self):
        known = tool.known_versions()
        self.assertIn('2025-06-18', known)
        self.assertTrue(all(tool.DATE.match(v) for v in known))

    def test_repository_listing_wins_and_drafts_never_count(self):
        versions, source = tool.published_versions(lambda url: LISTING if 'api.github.com' in url else '<html></html>')
        self.assertEqual(source, 'repository')
        self.assertEqual(versions[0], '2026-07-28')
        self.assertNotIn('draft', versions)

    def test_page_fallback_only_keeps_linked_specification_versions(self):
        page = '<a href="/specification/2025-06-18">2025-06-18</a> posted 2026-11-09 <a href="/specification/2026-07-28/changelog">x</a>'
        def fetcher(url):
            if 'api.github.com' in url: raise OSError('offline')
            return page
        versions, source = tool.published_versions(fetcher)
        self.assertEqual((versions, source), (['2026-07-28', '2025-06-18'], 'page'))

    def test_compare_reports_newer_and_older_unknown_versions(self):
        report = tool.compare(['2025-06-18', '2025-03-26'], ['2026-07-28', '2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05'])
        self.assertEqual(report['newer_than_known'], ['2026-07-28', '2025-11-25'])
        self.assertEqual(report['unknown_older'], ['2024-11-05'])
        self.assertFalse(report['up_to_date'])
        self.assertTrue(tool.compare(['2026-07-28', '2025-06-18'], ['2026-07-28', '2025-06-18'])['up_to_date'])

    def test_main_records_the_check_and_exits_one_when_behind(self):
        with tempfile.TemporaryDirectory() as temp:
            record = Path(temp) / 'mcp-versions.json'
            with patch.object(tool, 'fetch', lambda url, timeout=20: LISTING), redirect_stdout(io.StringIO()) as out:
                code = tool.main(['--record', str(record)])
            saved = json.loads(record.read_text())
            self.assertEqual(saved['published'][0], '2026-07-28')
            self.assertIn('checked_at', saved)
            self.assertEqual(code, 0 if '2026-07-28' in tool.known_versions() else 1)
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(tool.main(['--record', str(record), '--offline', '--json']), code)
            self.assertEqual(json.loads(out.getvalue())['source'], 'repository')


if __name__ == '__main__':
    unittest.main(verbosity=2)
