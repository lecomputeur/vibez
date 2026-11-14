"""Guards for destructive native update validation, not substitute update proofs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys
import subprocess
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


native = load('real_update_harness', BASE / 'tools/test-alpha-real-native-update.py')
build = load('real_update_build', BASE / 'tools/ci-alpha-build.py')


class NativeUpdateHarnessGuards(unittest.TestCase):
    def test_native_installs_refuse_the_user_desktop(self):
        with patch.dict(native.os.environ, {}, clear=True):
            with self.assertRaisesRegex(AssertionError, 'disposable'):
                native.native_ci_only('macos-x64')

    def test_existing_profile_is_rejected_before_any_new_profile_is_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); existing = root / 'data' / native.APP
            existing.mkdir(parents=True); marker = existing / 'unrelated'; marker.write_text('unchanged')
            env = {'XDG_CONFIG_HOME': str(root / 'config'), 'XDG_DATA_HOME': str(root / 'data'),
                   'XDG_CACHE_HOME': str(root / 'cache')}
            with self.assertRaisesRegex(AssertionError, 'existing Alpha profile'):
                native.seed_profile('linux-appimage', env, root)
            self.assertEqual(marker.read_text(), 'unchanged')
            self.assertFalse((root / 'config' / native.APP).exists())
            self.assertFalse((root / 'cache' / native.APP).exists())

    def test_preservation_fixture_is_explicitly_paused_and_detects_file_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = {key: str(root / folder) for key, folder in [('XDG_CONFIG_HOME','config'),
                   ('XDG_DATA_HOME','data'), ('XDG_CACHE_HOME','cache')]}
            cache, markers = native.seed_profile('linux-appimage', env, root)
            native.markers_unchanged(markers)
            self.assertEqual(cache, root / 'cache' / native.APP)
            data = json.loads((root / 'data' / native.APP / 'standalone/web-connector/web-projects.json').read_text())
            self.assertEqual(len(data['projects']), 3)
            self.assertTrue(all(value['manually_paused'] for value in data['projects'].values()))
            self.assertTrue(any(key.startswith('chat-') for key in data['projects']))
            self.assertTrue(any(key.startswith('code-') for key in data['projects']))
            real=native.check_bundled_bindings(BASE/'backend',Path(sys.executable),
                'linux-appimage',env,root,'unit-real-production-module')
            self.assertTrue(real['actual_bundled_connector_loaded_profile'])
            self.assertTrue(real['approval_fingerprints_valid'])
            (root / 'linked-workspace/unchanged.txt').write_text('changed')
            with self.assertRaisesRegex(AssertionError, 'preserved'):
                native.markers_unchanged(markers)


class ValidationRequestGuards(unittest.TestCase):
    def request(self):
        def file(name, release):
            return {'name': name, 'sha256': 'a'*64, 'size': 100,
                    'url': 'https://github.com/lecomputeur/vibez/releases/download/v'+release+'/'+name}
        targets = {}
        for target in ('macos-x64', 'macos-arm64'):
            arch = target.split('-')[1]
            targets[target] = {'files': {'from_app': file('VibeZ-4.0.0-alpha.6-macOS-'+arch+'.app.tar.gz', '4.0.0-alpha.6'),
                'to_app': file('VibeZ-4.0.0-alpha.7-macOS-'+arch+'.app.tar.gz', '4.0.0-alpha.7')}}
        return {'version':'4.0.0-alpha.7','verify_update':{'version':'4.0.0-alpha.7',
            'previous_version':'4.0.0-alpha.6','feed':{'version':'4.0.0-alpha.7','platforms':{}},'targets':targets}}

    def evaluate(self, request, target='macos-arm64'):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            (root / 'alpha-build-request.json').write_text(json.dumps(request))
            with patch.object(build, 'BASE', source), patch.object(build, 'VERSION', '4.0.0-alpha.7'):
                return build.update_validation_input(target)

    def test_matrix_selects_only_its_architecture(self):
        result = self.evaluate(self.request())
        self.assertEqual(result['target'], 'macos-arm64')
        self.assertTrue(all('-arm64.' in row['name'] for row in result['files'].values()))

    def test_foreign_download_origins_are_rejected(self):
        request = self.request()
        request['verify_update']['targets']['macos-arm64']['files']['to_app']['url'] = 'https://example.com/payload'
        with self.assertRaises(AssertionError): self.evaluate(request)

    def test_wrong_release_paths_are_rejected(self):
        request = self.request()
        request['verify_update']['targets']['macos-arm64']['files']['to_app']['url'] = request['verify_update']['targets']['macos-arm64']['files']['to_app']['url'].replace('/v4.0.0-alpha.7/', '/v4.0.0-alpha.6/')
        with self.assertRaises(AssertionError): self.evaluate(request)

    def test_exact_draft_asset_id_requires_a_digest_and_no_second_url(self):
        request = self.request(); row = request['verify_update']['targets']['macos-arm64']['files']['to_app']
        row['asset_id'] = 123
        with self.assertRaises(AssertionError): self.evaluate(request)
        row.pop('url')
        self.assertEqual(self.evaluate(request)['files']['to_app']['asset_id'], 123)
        row['sha256'] = 'not-a-digest'
        with self.assertRaises(AssertionError): self.evaluate(request)

    def test_same_version_does_not_count_as_an_update(self):
        request = self.request(); request['verify_update']['previous_version'] = '4.0.0-alpha.7'
        with self.assertRaises(AssertionError): self.evaluate(request)

    def test_ci_artifact_requires_exact_read_only_source_identity(self):
        request=self.request();record=request['verify_update']['targets']['macos-arm64']['files']['to_app']
        record.pop('url');record['ci_artifact']={'id':123,'run':456,'sha256':'b'*64}
        self.assertEqual(self.evaluate(request)['files']['to_app']['ci_artifact']['run'],456)
        record['ci_artifact']['sha256']='not-a-hash'
        with self.assertRaises(AssertionError):self.evaluate(request)

    def test_ci_artifact_does_not_allow_ambiguous_or_previous_release_sources(self):
        request=self.request();files=request['verify_update']['targets']['macos-arm64']['files']
        files['to_app']['ci_artifact']={'id':123,'run':456,'sha256':'b'*64}
        with self.assertRaises(AssertionError):self.evaluate(request)
        files['to_app'].pop('ci_artifact');files['from_app'].pop('url')
        files['from_app']['ci_artifact']={'id':123,'run':456,'sha256':'b'*64}
        with self.assertRaises(AssertionError):self.evaluate(request)


class AppleTicketRetryGuards(unittest.TestCase):
    def response(self, code, text):
        return subprocess.CompletedProcess(['xcrun'],code,stdout=text)

    def test_observed_cloudkit_connection_loss_retries_then_staples(self):
        failure=self.response(68,'NSURLErrorDomain Code=-1005 https://api.apple-cloudkit.com/ network connection lost')
        with patch.object(build.subprocess,'run',side_effect=[failure,self.response(0,'stapled')]) as calls,patch.object(build.time,'sleep') as sleep,patch('builtins.print'):
            build.apple_ticket_action(Path('fixture.app'),'staple')
        self.assertEqual(calls.call_count,2);sleep.assert_called_once_with(2)

    def test_signature_or_missing_ticket_error_is_not_retried(self):
        for response in [self.response(68,'The ticket is invalid'),self.response(65,'NSURLErrorDomain Code=-1005 https://api.apple-cloudkit.com/')]:
            with self.subTest(response=response),patch.object(build.subprocess,'run',return_value=response) as calls,patch.object(build.time,'sleep') as sleep,patch('builtins.print'):
                with self.assertRaises(subprocess.CalledProcessError):build.apple_ticket_action(Path('fixture.app'),'staple')
                self.assertEqual(calls.call_count,1);sleep.assert_not_called()

    def test_repeated_network_failure_is_bounded_and_fails_closed(self):
        failure=self.response(68,'NSURLErrorDomain Code=-1005 https://api.apple-cloudkit.com/')
        with patch.object(build.subprocess,'run',return_value=failure) as calls,patch.object(build.time,'sleep') as sleep,patch('builtins.print'):
            with self.assertRaises(subprocess.CalledProcessError):build.apple_ticket_action(Path('fixture.app'),'validate')
        self.assertEqual(calls.call_count,4);self.assertEqual([row.args for row in sleep.call_args_list],[(2,),(4,),(8,)])


if __name__ == '__main__':
    unittest.main()
