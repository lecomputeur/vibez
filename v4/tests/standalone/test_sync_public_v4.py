import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('sync_public_v4', ROOT / 'tools/sync-public-v4.py')


def load(base):
    tool = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(tool)
    tool.BASE, tool.BUILD = base, base / '_claude-build'
    tool.CLONE, tool.STATE = tool.BUILD / 'v4-public', tool.BUILD / 'public-sync.json'
    tool.EXTRAS = []
    return tool


def run(cwd, *args):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *args], cwd=cwd, check=True, capture_output=True)


class SyncPublicV4Test(unittest.TestCase):
    """Three-way comparison of the release tree with the public v4/ folder."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vibez-sync-test-')
        self.base = Path(self.temp.name) / 'tree'
        (self.base / 'management').mkdir(parents=True)
        self.files = ['a.txt', 'b.txt', 'c.txt']
        (self.base / 'management/source-files.json').write_text(json.dumps({'files': self.files}))
        (self.base / 'management/maintainer-files.json').write_text(json.dumps({'files': []}))
        for name in self.files:
            (self.base / name).write_text('one ' + name)
        # The "public clone": a repository whose main has v4/ with the same files.
        self.clone = self.base / '_claude-build/v4-public'
        (self.clone / 'v4').mkdir(parents=True)
        run(self.clone, 'init', '-q', '-b', 'main')
        for name in self.files:
            (self.clone / 'v4' / name).write_text('one ' + name)
        run(self.clone, 'add', '-A'); run(self.clone, 'commit', '-q', '-m', 'base')
        run(self.clone, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.tool = load(self.base)
        self.tool.prepare_clone = lambda: self.tool.git('rev-parse', 'origin/main')
        self.first = self.tool.git('rev-parse', 'HEAD')
        self.tool.save_base(self.first)

    def tearDown(self):
        self.temp.cleanup()

    def public_change(self, name, text):
        if text is None:
            (self.clone / 'v4' / name).unlink()
        else:
            (self.clone / 'v4' / name).write_text(text)
        run(self.clone, 'add', '-A'); run(self.clone, 'commit', '-q', '-m', 'public')
        run(self.clone, 'update-ref', 'refs/remotes/origin/main', 'HEAD')

    def step(self, *args):
        with redirect_stdout(io.StringIO()) as out:
            code = self.tool.main(list(args))
        return code, out.getvalue()

    def test_equal_trees_need_nothing(self):
        self.assertEqual(self.step('check')[0], 0)

    def test_a_merged_public_change_is_pulled_and_blocks_a_release_until_then(self):
        self.public_change('a.txt', 'two a')
        code, out = self.step('check')
        self.assertEqual(code, 1); self.assertIn('STOP', out)
        self.assertEqual(self.step('pull')[0], 0)
        self.assertEqual((self.base / 'a.txt').read_text(), 'two a')
        self.assertEqual(self.step('check')[0], 0)

    def test_a_public_deletion_is_pulled(self):
        self.public_change('c.txt', None)
        self.assertEqual(self.step('pull')[0], 0)
        self.assertFalse((self.base / 'c.txt').exists())

    def test_a_change_on_both_sides_copies_nothing(self):
        self.public_change('a.txt', 'public a')
        self.public_change('b.txt', 'public b')
        (self.base / 'a.txt').write_text('local a')
        code, out = self.step('pull')
        self.assertEqual(code, 1); self.assertIn('CONFLICT', out)
        self.assertEqual((self.base / 'a.txt').read_text(), 'local a')
        self.assertEqual((self.base / 'b.txt').read_text(), 'one b.txt')

    def test_a_local_change_does_not_block_and_is_committed_by_push(self):
        (self.base / 'b.txt').write_text('local b')
        code, out = self.step('check')
        self.assertEqual(code, 0); self.assertIn('changed only here', out)
        self.assertEqual(self.step('push', '--branch', 'v4/test')[0], 0)
        self.assertEqual(self.tool.git('show', 'v4/test:v4/b.txt'), 'local b')
        self.assertEqual(self.tool.git('rev-parse', 'origin/main'), self.tool.git('rev-parse', 'v4/test~1'))

    def test_unexpected_paths_are_refused(self):
        for name in ('../x', '/etc/passwd', '_claude-build/x', '.git/config'):
            with self.assertRaises(self.tool.SyncError):
                self.tool.safe_name(name)


if __name__ == '__main__':
    unittest.main()
