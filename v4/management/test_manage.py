"""Disposable release-management regressions; no real repository is mutated."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('private_release_manage',Path(__file__).with_name('manage.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='vibez-management-test-')
        self.base=Path(self.temp.name);self.root=self.base/'source';self.root.mkdir()
        self.release=json.loads(Path(__file__).with_name('release.json').read_text())
        self.current=self.release['version'];self.next=min(m.next_versions(self.current),key=m.alpha_number)
        files={
            'desktop/package.json':json.dumps({'name':'vibez4-alpha','version':self.current}),
            'desktop/package-lock.json':json.dumps({'name':'vibez4-alpha','version':self.current,'packages':{'':{'name':'vibez4-alpha','version':self.current},'node_modules/unchanged':{'version':'1.0.0'}}}),
            'desktop/src-tauri/Cargo.toml':'[package]\nname = "vibez4-alpha"\nversion = "'+self.current+'"\n[dependencies]\nunrelated = "1.0.0"\n',
            'desktop/src-tauri/Cargo.lock':'version = 4\n[[package]]\nname = "unrelated"\nversion = "1.0.0"\n[[package]]\nname = "vibez4-alpha"\nversion = "'+self.current+'"\n',
            'desktop/src-tauri/tauri.conf.json':json.dumps({'identifier':'nl.lecomputeur.vibez4.alpha','mainBinaryName':'vibez4-alpha','version':self.current}),
            'LICENSE':'Fixture license\n',
        }
        for name in m.VERSION_FILES[5:]:files[name]="VERSION = '"+self.current+"'\nOLD_FIXTURE = '4.0.0-alpha.1'\n"
        self.names=sorted(files)
        files['management/release.json']=json.dumps(self.release)
        files['management/source-files.json']=json.dumps({'schema_version':1,'files':self.names})
        for name,text in files.items():
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
        (self.root/'desktop/package.json').chmod(0o755)
        self.run_git('init','--initial-branch=main')
        self.run_git('add','--',*files)
        self.commit()
    def tearDown(self):self.temp.cleanup()
    def run_git(self,*args):
        r=subprocess.run(['git','-C',str(self.root),*args],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);return r.stdout
    def commit(self):self.run_git('-c','user.name=Release fixture','-c','user.email=fixture@example.invalid','commit','-m','Fixture source')
    def save_release(self,value):
        (self.root/'management/release.json').write_text(json.dumps(value))
    def test_check_separates_source_installed_published_stable(self):
        result=m.check(self.root)
        self.assertEqual(result['version_fields_checked'],9)
        self.assertEqual(result['version'],self.current)
        self.assertEqual(result['published_version'],self.release['published_version'])
        self.assertEqual(result['stable_version'],'3.0.9')
        self.assertEqual(len(result['package_names']['linux-x64']),5)
        self.assertFalse(any('msix' in x.lower() for v in result['package_names'].values() for x in v))
    def test_inconsistent_source_version_stops_check(self):
        p=self.root/'backend/web_connector.py';p.write_text("VERSION='4.0.0-alpha.1'\n")
        with self.assertRaisesRegex(m.ReleaseError,'differs'):m.check(self.root)
    def test_stable_and_identity_cannot_be_reused(self):
        value=copy.deepcopy(self.release);value['stable_version']='4.0.0';self.save_release(value)
        with self.assertRaises(m.ReleaseError):m.check(self.root)
        self.save_release(self.release)
        p=self.root/'desktop/src-tauri/tauri.conf.json';value=json.loads(p.read_text());value['identifier']='nl.lecomputeur.vibez3';p.write_text(json.dumps(value))
        with self.assertRaisesRegex(m.ReleaseError,'identity'):m.check(self.root)
    def test_future_version_is_strictly_next_alpha(self):
        for version in [self.current,'4.0.0-alpha.14','4.0.0-alpha.17','4.0.0','4.0.0-alpha.016','3.0.10']:
            with self.subTest(version=version):
                with self.assertRaises(m.ReleaseError):m.plan(self.root,version,self.base/'invalid')
                self.assertFalse((self.base/'invalid').exists())
    def test_plan_does_not_change_source_or_mark_future_as_installed(self):
        before={n:(self.root/n).read_bytes() for n in self.names+['management/release.json']}
        output=self.base/'plan';result=m.plan(self.root,self.next,output)
        self.assertFalse(result['applied']);self.assertFalse(result['published']);self.assertFalse(result['built'])
        self.assertEqual(before,{n:(self.root/n).read_bytes() for n in before})
        changed=json.loads((output/'files/management/release.json').read_text())
        self.assertEqual(changed['version'],self.next);self.assertEqual(changed['installed_version'],self.release['installed_version']);self.assertNotEqual(changed['installed_version'],self.next)
        self.assertEqual(changed['published_version'],self.release['published_version'])
        self.assertEqual(changed['changes'],[]);self.assertEqual(changed['related_issues'],[])
        for name in m.VERSION_FILES:
            (self.root/name).write_bytes((output/'files'/name).read_bytes())
        self.save_release(changed)
        self.assertEqual(m.check(self.root)['version'],self.next)
        self.assertIn('OLD_FIXTURE', (self.root/'backend/web_connector.py').read_text())
        self.assertIn('4.0.0-alpha.1',(self.root/'backend/web_connector.py').read_text())
        self.assertEqual(json.loads((self.root/'desktop/package-lock.json').read_text())['packages']['node_modules/unchanged']['version'],'1.0.0')
    def test_preexisting_outputs_are_never_replaced(self):
        path=self.base/'output';path.mkdir();(path/'kept.txt').write_text('Keep')
        for function in [lambda:m.plan(self.root,self.next,path),lambda:m.snapshot(self.root,path)]:
            with self.assertRaisesRegex(m.ReleaseError,'already exists'):function()
            self.assertEqual((path/'kept.txt').read_text(),'Keep')
    def test_output_symlink_and_source_tree_are_rejected(self):
        destination=self.base/'real';destination.mkdir();link=self.base/'linked';link.symlink_to(destination,target_is_directory=True)
        for output in [link/'plan',self.root/'new-plan']:
            with self.assertRaises(m.ReleaseError):m.plan(self.root,self.next,output)
    def test_dirty_or_untracked_source_cannot_freeze(self):
        (self.root/'LICENSE').write_text('Changed')
        with self.assertRaisesRegex(m.ReleaseError,'Commit tracked changes'):m.snapshot(self.root,self.base/'snapshot')
        self.run_git('checkout','--','LICENSE')
        self.run_git('rm','--cached','LICENSE');self.commit()
        with self.assertRaisesRegex(m.ReleaseError,'not all tracked'):m.snapshot(self.root,self.base/'snapshot')
    def test_snapshot_is_exact_head_bytes_and_deterministic(self):
        first=m.snapshot(self.root,self.base/'one');second=m.snapshot(self.root,self.base/'two')
        self.assertEqual(first['archive_sha256'],second['archive_sha256'])
        self.assertEqual(first['source_manifest_sha256'],second['source_manifest_sha256'])
        self.assertEqual(first['source_commit'],self.run_git('rev-parse','HEAD').strip())
        with tarfile.open(self.base/'one/private-source.tar.gz') as archive:
            self.assertEqual(archive.getnames(),self.names)
            for entry in first['files']:
                raw=archive.extractfile(entry['path']).read()
                self.assertEqual(raw,(self.root/entry['path']).read_bytes())
                self.assertEqual(m.digest(raw),entry['sha256'])
            self.assertEqual(archive.getmember('desktop/package.json').mode,0o755)
        self.assertFalse(first['built']);self.assertFalse(first['published'])
        self.assertEqual(first['release'],self.release)
    def test_snapshot_notes_are_draft_and_driven_by_release_metadata(self):
        result=m.snapshot(self.root,self.base/'snapshot')
        notes=(self.base/'snapshot/RELEASE-NOTES.md').read_text()
        self.assertIn('DRAFT',notes);self.assertIn('NOT PUBLISHED',notes)
        self.assertIn(self.current,notes);self.assertIn('stable VibeZ 3.0.9',notes)
        self.assertIn('MSIX is excluded',notes)
        self.assertIn('not download availability',notes)
        for names in result['package_names'].values():
            for name in names:self.assertIn(name,notes)
        for change in self.release['changes']:self.assertIn(change,notes)
        for issue in self.release['related_issues']:self.assertIn('https://github.com/lecomputeur/vibez/issues/'+str(issue),notes)
        self.assertNotIn(str(self.root),notes);self.assertNotIn('/home/',notes)
        self.assertNotIn('source_commit',notes);self.assertNotIn('HEAD',notes)
        self.assertNotIn('tests passed',notes);self.assertNotIn('now available',notes)
        with tarfile.open(self.base/'snapshot/private-source.tar.gz') as archive:
            self.assertEqual(archive.getnames(),self.names)
            self.assertNotIn('RELEASE-NOTES.md',archive.getnames())
    def test_untracked_secret_is_not_snapshotted(self):
        (self.root/'.env').write_text('fixture only, never source')
        (self.root/'private.key').write_text('fixture only')
        result=m.snapshot(self.root,self.base/'snapshot')
        self.assertNotIn('.env',[x['path'] for x in result['files']])
        self.assertNotIn('private.key',[x['path'] for x in result['files']])
    def test_allowlist_rejects_paths_and_secret_material(self):
        for name in ['../outside.txt','/tmp/outside.txt','a/../b','a\\b','artifacts/data.json','.git/config','backend/.env','private.key','secret.json']:
            with self.subTest(name=name):
                with self.assertRaises(m.ReleaseError):m.safe_relative(name)
        p=self.root/'LICENSE';p.write_text('-----BEGIN PGP PRIVATE KEY BLOCK-----\nfixture')
        with self.assertRaisesRegex(m.ReleaseError,'Private key material'):m.check(self.root)
    def test_allowlist_source_symlinks_are_rejected(self):
        p=self.root/'LICENSE';p.unlink();p.symlink_to(self.root/'desktop/package.json')
        with self.assertRaisesRegex(m.ReleaseError,'Symlink'):m.check(self.root)
    def test_json_write_never_clobbers_existing_file(self):
        target=self.base/'existing.json';target.write_text('{"keep":true}')
        with self.assertRaises(FileExistsError):m.json_write(target,{'keep':False})
        self.assertEqual(target.read_text(),'{"keep":true}')
        self.assertEqual(sorted(x.name for x in self.base.iterdir()),['existing.json','source'])
    def test_failed_output_is_removed(self):
        output=self.base/'failed'
        def fail(path):
            (path/'partial').write_text('partial');raise RuntimeError('fixture')
        with self.assertRaises(RuntimeError):m.atomic_directory(output,fail)
        self.assertFalse(output.exists())
    def test_required_formats_and_gates_cannot_silently_change(self):
        for mutate in [lambda d:d['formats']['windows-x64'].append('msix'),lambda d:d['gates'].remove('maintainer_approval'),lambda d:d.update(source_private=True),lambda d:d.update(replace_published_assets=True)]:
            value=copy.deepcopy(self.release);mutate(value);self.save_release(value)
            with self.assertRaises(m.ReleaseError):m.check(self.root)

if __name__=='__main__':unittest.main(verbosity=2)
