"""One linked workspace and local child directories, using disposable fixtures."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[2]
def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, BASE/'backend'/filename)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value
web = module('single_web57', 'web_connector.py')
engine = module('single_engine57', 'standalone_engine.py')
A = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'
B = 'bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb'
CHAT = 'chat-' + A


class SingleWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='vibez-single-workspace-')
        self.root = Path(self.tmp.name); self.events=[]
        self.alpha=self.root/'Alpha'; self.beta=self.root/'Beta'; self.alpha.mkdir(); self.beta.mkdir()
        (self.alpha/'marker.txt').write_text('alpha'); (self.beta/'marker.txt').write_text('beta')
        self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
        self.c.select({'id':A,'name':'Fixture'}); self.c.link(A,str(self.alpha))

    def tearDown(self):
        self.c.close(); self.tmp.cleanup()

    def approve(self):
        p=self.c.projects[A]; self.c.enabled.add(A)
        self.assertTrue(self.c.approve_auto(A,(p['folder'],p['token'])))

    def restart(self):
        self.c.close(); self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)

    def write_modern(self, *, paths=None, target=None, approved=True, paused=False, context=None):
        self.c.close(); data=json.loads(self.c.file.read_text()); key=context['id'] if context else A
        p=copy.deepcopy(data['projects'].pop(A)); p.update(context or {'id':A})
        p['folders']=[web.multi.entry(str(path)) for path in (paths or [self.alpha,self.beta])]
        p['target_folder_id']=web.multi.entry(str(target or p['folders'][-1]['path']))['id']
        p['manually_paused']=paused
        p['auto_approved']=web.Connector.auto_fingerprint(key,p['folder'],p['token'],p['folders']) if approved else ''
        data['projects'][key]=p; self.c.file.write_text(json.dumps(data))
        self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
        return p

    def test_legacy_single_binding_and_valid_auto_approval_are_byte_compatible(self):
        self.approve(); old=copy.deepcopy(self.c.projects[A]); binding=self.c.workspace_binding(A)
        self.restart(); self.assertEqual(self.c.projects[A],old); self.assertTrue(self.c.auto_approved(A))
        self.assertEqual(self.c.workspace_binding(A),binding)
        self.c.select({'id':A,'name':'Fixture'}); self.assertEqual(len(self.c.snapshot()['folders']),1)
        self.assertFalse(self.c.enabled)

    def test_multi_root_restart_preserves_all_roots_selected_target_token_and_approval(self):
        old=self.write_modern(target=self.beta)
        p=self.c.projects[A]
        self.assertEqual(p['folder'],str(self.beta));self.assertEqual(len(p['folders']),2)
        self.assertEqual(p['token'],old['token']);self.assertTrue(self.c.auto_approved(A))
        self.restart();self.assertTrue(self.c.auto_approved(A))
        self.assertEqual((self.alpha/'marker.txt').read_text(),'alpha');self.assertEqual((self.beta/'marker.txt').read_text(),'beta')

    def test_modern_single_root_preserves_token_and_only_verified_approval(self):
        old=self.write_modern(paths=[self.alpha],target=self.alpha)
        self.assertEqual(self.c.projects[A]['token'],old['token']); self.assertTrue(self.c.auto_approved(A))
        self.assertEqual(len(self.c.projects[A]['folders']),1)
        self.restart(); self.assertTrue(self.c.auto_approved(A))

    def test_modern_invalid_or_missing_proof_never_gains_approval(self):
        for proof in ['','f'*64]:
            old=self.write_modern(paths=[self.alpha],target=self.alpha,approved=False)
            self.c.close(); data=json.loads(self.c.file.read_text()); data['projects'][A]=old; data['projects'][A]['auto_approved']=proof
            self.c.file.write_text(json.dumps(data)); self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)
            self.assertFalse(self.c.auto_approved(A)); self.assertEqual(self.c.projects[A]['token'],old['token'])

    def test_manual_pause_is_retained_after_modern_migration(self):
        self.write_modern(target=self.beta,paused=True)
        self.assertTrue(self.c.projects[A]['manually_paused']); self.assertFalse(self.c.can_auto_connect(A))
        self.c.select({'id':A,'name':'Fixture'}); self.c.select_folder(A,web.multi.entry(str(self.alpha))['id'],self.c.workspace_binding(A))
        self.assertTrue(self.c.projects[A]['manually_paused'])

    def test_chat_identity_and_draft_promotion_survive_single_target_migration(self):
        context={'id':CHAT,'kind':'conversation','name':'Draft','draft':True,'conversation_id':None,'url':'https://chat.mistral.ai/work'}
        self.write_modern(target=self.beta,context=context)
        self.assertEqual(self.c.projects[CHAT]['folder'],str(self.beta)); self.assertTrue(self.c.projects[CHAT]['draft'])
        # Orphan draft may not reactivate after restart; its identity metadata is not widened.
        with self.assertRaises(ValueError):self.c.select(context)
        saved={**context,'draft':False,'conversation_id':B,'url':'https://chat.mistral.ai/work/'+B}
        with self.assertRaises(ValueError):self.c.select(saved)

    def test_multiple_roots_require_fresh_scope_and_new_approval(self):
        self.approve();rev=self.c.workspace_binding(A);self.c.add_folder(A,str(self.beta),rev)
        self.assertEqual(len(self.c.snapshot()['folders']),2);self.assertFalse(self.c.auto_approved(A))
        with self.assertRaises(ValueError):self.c.select_folder(A,web.multi.entry(str(self.alpha))['id'],rev)
        self.c.select_folder(A,web.multi.entry(str(self.alpha))['id'],self.c.workspace_binding(A))
        self.assertEqual(self.c.import_folder(A),str(self.alpha))

    def test_replace_workspace_has_exactly_one_root_and_revokes_old_scope(self):
        self.approve(); old_token=self.c.projects[A]['token']; rev=self.c.workspace_binding(A)
        self.c.link(A,str(self.beta),revision=rev,folder_id=web.multi.entry(str(self.alpha))['id'])
        self.assertEqual(self.c.projects[A]['folder'],str(self.beta)); self.assertEqual(len(self.c.snapshot()['folders']),1)
        self.assertNotEqual(self.c.projects[A]['token'],old_token); self.assertFalse(self.c.auto_approved(A))
        self.assertEqual((self.alpha/'marker.txt').read_text(),'alpha')

    def test_duplicate_selection_keeps_approval_and_workspace_sessions(self):
        self.approve(); before=copy.deepcopy(self.c.projects[A]); ws=self.c.project_workspace(A)
        self.c.link(A,str(self.alpha),revision=self.c.workspace_binding(A))
        self.assertEqual(self.c.projects[A],before); self.assertTrue(self.c.auto_approved(A)); self.assertIs(self.c.project_workspace(A),ws)

    def test_single_mcp_root_uses_relative_paths_and_never_another_root(self):
        ws=self.c.project_workspace(A)
        self.assertEqual(ws.read('marker.txt')['content'],'alpha')
        for path in ['../Beta/marker.txt',str(self.beta/'marker.txt')]:
            with self.assertRaises(ValueError):ws.read(path)

    def test_create_folder_is_local_and_does_not_change_scope_or_permission(self):
        self.approve(); before=copy.deepcopy(self.c.projects[A]); rev=self.c.workspace_binding(A); binding=self.c.snapshot()['import_binding']; ws=self.c.project_workspace(A)
        value=self.c.create_folder(A,rev,'Nieuwe map')
        self.assertEqual(value,{'name':'Nieuwe map','created':True}); self.assertTrue((self.alpha/'Nieuwe map').is_dir())
        self.assertEqual(self.c.projects[A],before); self.assertTrue(self.c.auto_approved(A)); self.assertEqual(self.c.workspace_binding(A),rev)
        self.assertEqual(self.c.snapshot()['import_binding'],binding); self.assertIs(self.c.project_workspace(A),ws)
        self.assertEqual(self.c.snapshot()['recent_activity'][-1]['action'],'create_folder')
        self.assertNotIn('create_folder',{t['name'] for t in web.TOOLS})

    def test_create_folder_can_work_while_mistral_is_paused(self):
        self.c.pause(A); self.c.create_folder(A,self.c.workspace_binding(A),'Offline')
        self.assertTrue((self.alpha/'Offline').is_dir()); self.assertTrue(self.c.projects[A]['manually_paused']); self.assertFalse(self.c.enabled)

    def test_create_folder_rejects_foreign_context_or_stale_binding(self):
        rev=self.c.workspace_binding(A); self.c.link(A,str(self.beta),revision=rev)
        with self.assertRaises(ValueError):self.c.create_folder(A,rev,'Old scope')
        self.assertFalse((self.alpha/'Old scope').exists()); self.assertFalse((self.beta/'Old scope').exists())
        self.c.select({'id':B,'name':'Other'})
        with self.assertRaises(ValueError):self.c.create_folder(A,self.c.workspace_binding(A),'Wrong context')
        self.assertFalse((self.beta/'Wrong context').exists())

    def test_create_folder_rejects_paths_hidden_names_controls_and_oversized_names(self):
        bad=['','.','..','.hidden','a/b',r'a\b',' /escape','trailing ','line\nname','x\0z','a\u202eb', 'x\ud800', 'é'*128, 'x'*256]
        before=set(self.alpha.iterdir())
        for name in bad:
            with self.subTest(name=repr(name)),self.assertRaises(ValueError):self.c.create_folder(A,self.c.workspace_binding(A),name)
        self.assertEqual(set(self.alpha.iterdir()),before)

    def test_create_folder_supports_visible_unicode_and_maximum_component_length(self):
        for name in ['Reis München','旅行','Папка','é'*127+'x']:
            self.c.create_folder(A,self.c.workspace_binding(A),name); self.assertTrue((self.alpha/name).is_dir())

    def test_create_folder_never_overwrites_files_directories_or_links(self):
        (self.alpha/'Existing').mkdir(); (self.alpha/'link').symlink_to(self.beta,target_is_directory=True)
        for name in ['marker.txt','Existing','link']:
            with self.subTest(name=name),self.assertRaises(ValueError):self.c.create_folder(A,self.c.workspace_binding(A),name)
        self.assertEqual((self.alpha/'marker.txt').read_text(),'alpha'); self.assertEqual((self.beta/'marker.txt').read_text(),'beta')

    def test_create_folder_rejects_replaced_or_symlinked_workspace(self):
        self.c.project_workspace(A); self.alpha.rename(self.root/'old-alpha'); self.alpha.mkdir()
        with self.assertRaises(ValueError):self.c.create_folder(A,self.c.workspace_binding(A),'Not in replacement')
        self.assertFalse((self.alpha/'Not in replacement').exists())
        self.alpha.rmdir(); self.alpha.symlink_to(self.beta,target_is_directory=True)
        with self.assertRaises((OSError,ValueError)):self.c.create_folder(A,self.c.workspace_binding(A),'Not through link')
        self.assertFalse((self.beta/'Not through link').exists())

    def test_directory_creation_failure_does_not_record_success(self):
        with patch.object(web.imports.os,'mkdir',side_effect=PermissionError('fixture')):
            with self.assertRaises(PermissionError):self.c.create_folder(A,self.c.workspace_binding(A),'Denied')
        self.assertFalse((self.alpha/'Denied').exists()); self.assertFalse(self.c.snapshot()['recent_activity'])

    def test_folder_drop_still_copies_nested_contents_inside_the_workspace(self):
        source=self.root/'Source folder'; (source/'nested').mkdir(parents=True); (source/'nested'/'file.txt').write_text('copied')
        result=self.c.import_files(A,self.c.snapshot()['import_binding'],[str(source)])
        self.assertEqual(result['status'],'done'); self.assertEqual((self.alpha/'Source folder'/'nested'/'file.txt').read_text(),'copied')
        self.assertEqual((source/'nested'/'file.txt').read_text(),'copied'); self.assertEqual(len(self.c.snapshot()['folders']),1)

    def test_engine_create_folder_success_correlates_only_after_creation(self):
        events=[];host=SimpleNamespace(web=self.c,external_output=events.append)
        revision=self.c.workspace_binding(A)
        engine.StandaloneEngine.dispatch(host,{'action':'web_create_folder','project_id':A,'workspace_binding':revision,'request_id':'folder-request-57','name':'Engine folder'})
        self.assertTrue((self.alpha/'Engine folder').is_dir())
        self.assertEqual(events,[{'type':'web_create_folder_result','project_id':A,'workspace_binding':revision,'request_id':'folder-request-57','name':'Engine folder','created':True}])
        self.assertEqual(self.c.snapshot()['workspace_binding'],revision)

    def test_engine_create_folder_error_is_scoped_correlated_and_never_success(self):
        events=[];host=SimpleNamespace(web=self.c,external_output=events.append);revision=self.c.workspace_binding(A)
        engine.StandaloneEngine.dispatch(host,{'action':'web_create_folder','project_id':A,'workspace_binding':revision,'request_id':'folder-error-57','name':'marker.txt'})
        self.assertEqual(len(events),1);value=events[0]
        self.assertEqual(value['type'],'web_create_folder_result');self.assertEqual(value['project_id'],A);self.assertEqual(value['workspace_binding'],revision);self.assertEqual(value['request_id'],'folder-error-57')
        self.assertIn('error',value);self.assertNotIn('created',value);self.assertEqual((self.alpha/'marker.txt').read_text(),'alpha')
        self.assertFalse(self.c.snapshot()['recent_activity'])

    def test_directory_migration_storage_failure_preserves_existing_file(self):
        self.c.close(); old=json.loads(self.c.file.read_text()); p=old['projects'][A]
        p['folders']=[web.multi.entry(str(self.alpha)),web.multi.entry(str(self.beta))]; p['target_folder_id']=p['folders'][1]['id']; self.c.file.write_text(json.dumps(old)); raw=self.c.file.read_bytes()
        with patch.object(web.Connector,'save',side_effect=OSError('persistence fixture')):
            with self.assertRaises(OSError):web.Connector(self.events.append,self.root/'private',approval_wait=0)
        self.assertEqual(self.c.file.read_bytes(),raw)
        self.c=web.Connector(self.events.append,self.root/'private',approval_wait=0)


if __name__=='__main__':unittest.main()
