"""The Linux system updater moves an Alpha installation on to Beta, RC and final 4.x."""
import importlib.util
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('linux_updater_versions', BASE / 'packaging/alpha-updater/update.py')
updater = importlib.util.module_from_spec(spec); spec.loader.exec_module(updater)


class LinuxUpdaterVersionTests(unittest.TestCase):
    def test_alpha_beta_rc_and_final_sort_in_release_order(self):
        order = ['4.0.0-alpha.30', '4.0.0-alpha.31', '4.0.0-beta.1', '4.0.0-beta.2', '4.0.0-beta.10', '4.0.0-rc.1', '4.0.0', '4.0.1-alpha.1', '4.0.1', '4.1.0-beta.1']
        keys = [updater.version(value) for value in order]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(set(keys)), len(keys))

    def test_other_shapes_are_refused(self):
        for wrong in ['3.0.10', '5.0.0-beta.1', '4.0.0-beta.0', '4.0.0-beta.01', '4.0.0-gamma.1', '4.0.0-beta', '4.0.0-beta.1+x', '4.0.0-alpha.1234567', '', None, 4]:
            with self.assertRaises(ValueError, msg=repr(wrong)): updater.version(wrong)

    def test_rpm_and_arch_package_versions_match_the_release(self):
        self.assertEqual(updater.rpm_form('4.0.0-alpha.31'), '4.0.0-0.alpha.31')
        self.assertEqual(updater.rpm_form('4.0.0-beta.1'), '4.0.0-0.beta.1')
        self.assertEqual(updater.rpm_form('4.0.0'), '4.0.0-1')
        self.assertEqual(updater.arch_form('4.0.0-alpha.31'), '4.0.0_alpha.31-1')
        self.assertEqual(updater.arch_form('4.0.0-beta.1'), '4.0.0_beta.1-1')
        self.assertEqual(updater.arch_form('4.0.0'), '4.0.0-1')

    def test_a_beta_manifest_is_accepted_on_the_same_channel(self):
        release = '4.0.0-beta.1'; name = f'VibeZ-{release}-Linux-x64.deb'
        data = {'schema': 1, 'channel': 'v4-alpha', 'version': release, 'assets': {'linux-x86_64-deb': {
            'name': name, 'url': f'https://github.com/lecomputeur/vibez/releases/download/v{release}/{name}', 'size': 10, 'sha256': 'a' * 64}}}
        self.assertEqual(updater.manifest(data, 'deb')[0], release)
        data['version'] = '5.0.0-beta.1'
        with self.assertRaises(ValueError): updater.manifest(data, 'deb')


if __name__ == '__main__':
    unittest.main()
