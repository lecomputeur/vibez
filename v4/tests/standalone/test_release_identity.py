"""Every distributed service must announce the release actually installed."""
import ast
import json
from pathlib import Path
import re
import unittest

BASE = Path(__file__).resolve().parents[2]


class ReleaseIdentityTests(unittest.TestCase):
    def test_native_frontend_backend_and_mcp_versions_agree(self):
        expected = json.loads((BASE/'desktop/package.json').read_text())['version']
        self.assertRegex(expected, r'^4\.\d+\.\d+-(alpha|beta)\.[1-9]\d*$')
        native = json.loads((BASE/'desktop/src-tauri/tauri.conf.json').read_text())
        self.assertEqual(native['version'], expected)
        cargo = (BASE/'desktop/src-tauri/Cargo.toml').read_text()
        self.assertEqual(re.search(r'^version = "([^"]+)"$', cargo, re.M)[1], expected)
        for name in ['standalone_engine.py', 'workspace_engine.py', 'web_connector.py']:
            with self.subTest(service=name):
                declarations = [ast.literal_eval(statement.value)
                    for statement in ast.parse((BASE/'backend'/name).read_text()).body
                    if isinstance(statement, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'VERSION'
                            for target in statement.targets)]
                self.assertEqual(declarations, [expected],
                    'The packaged service would announce a different release')


if __name__ == '__main__':
    unittest.main()
