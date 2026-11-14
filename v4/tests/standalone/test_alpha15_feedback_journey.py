"""Combined Alpha15 journeys over real local MCP with only disposable folders.

The official Mistral account API is an in-memory fixture. No real account,
public tunnel, personal chat, workspace or physical display is accessed.
"""
import base64
import hashlib
import json
from pathlib import Path
import unittest
import zipfile
import test_alpha7_connection_journey as journey
from code_multiproject_check import Client

FORMATS=('.odt','.docx','.ods','.xlsx','.odp','.pptx')

class Alpha15FeedbackJourneyTests(unittest.TestCase):
    def setUp(self):
        self.h=journey.CompleteConnectionJourneyTests('runTest');self.h.setUp()
        for root in self.h.folders.values():(root/'Documents').mkdir()
        self.sentinels={root/'untouched.txt':hashlib.sha256((root/'untouched.txt').read_bytes()).hexdigest() for root in self.h.folders.values()}
    def tearDown(self):
        for path,digest in self.sentinels.items():self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
        self.h.tearDown()
    def test_work_code_and_new_conversation_create_deny_approve_read_and_keep_one_remote_active_scope(self):
        h=self.h;old_clients=[]
        for key in [journey.WORK,journey.CODE,journey.CHAT]:
            with self.subTest(context=key):
                h.connect(key,link=True)
                for old in old_clients:self.assertEqual(old.request('ping')[0],403)
                self.assertEqual(len(h.service.active),1,'Previous owned scopes are paused remotely as well as locally')
                client=Client(h.e.web,key).initialize();old_clients.append(client)
                code,_,catalog=client.request('tools/list');self.assertEqual(code,200)
                tool=next(t for t in catalog['result']['tools'] if t['name']=='create_document')
                self.assertFalse(tool['annotations']['readOnlyHint'])
                for ext in FORMATS:
                    path='Documents/approved'+ext
                    content='SAVE — été 中文\nSecond  line\tX' if ext not in ('.ods','.xlsx') else 'Name\tValue\nSAVE\tété 中文'
                    pending=client.tool('create_document',{'path':path,'content':content})
                    self.assertFalse(pending['written']);target=h.folders[key]/path;self.assertFalse(target.exists())
                    snapshot=h.e.web.snapshot();card=next(x for x in snapshot['pending'] if x['id']==pending['proposal_id'])
                    self.assertTrue(card['new']);self.assertEqual(card['document_format'],ext);self.assertEqual(card['after'],content)
                    h.e.dispatch({'action':'web_approve','id':pending['proposal_id'],'allow':True})
                    self.assertTrue(client.tool('change_status',{'proposal_id':pending['proposal_id']})['written'])
                    self.assertTrue(target.is_file())
                    extracted=Client(h.e.web,key).initialize().tool('read_file',{'path':path})
                    for word in ['SAVE','été','中文']:self.assertIn(word,extracted['content'])
                    before=target.read_bytes()
                    rejected=client.tool('create_document',{'path':path,'content':'overwrite forbidden'},expect_error=True)
                    self.assertTrue(rejected['isError']);self.assertEqual(target.read_bytes(),before)
                    with zipfile.ZipFile(target) as archive:
                        self.assertTrue(archive.testzip() is None)
                        self.assertFalse(any('vbaproject' in n.lower() for n in archive.namelist()))
                denied=client.tool('write_file',{'path':'Documents/denied.odt','content':'Never save this'})
                self.assertFalse((h.folders[key]/'Documents/denied.odt').exists())
                h.e.dispatch({'action':'web_approve','id':denied['proposal_id'],'allow':False})
                self.assertFalse(client.tool('change_status',{'proposal_id':denied['proposal_id']})['written'])
                self.assertFalse((h.folders[key]/'Documents/denied.odt').exists())
                client.tool('create_document',{'path':'../outside.odt','content':'No'},expect_error=True)
                self.assertFalse((h.root/'outside.odt').exists())
        self.assertEqual(h.auth.calls,0);self.assertEqual(len(h.service.connectors),3)
    def test_switch_revokes_pending_office_and_manual_pause_survives_restart(self):
        h=self.h;h.connect(journey.WORK,link=True);client=Client(h.e.web,journey.WORK).initialize()
        pending=client.tool('create_document',{'path':'Documents/must-not-save.docx','content':'Pending original project'})
        h.connect(journey.CODE,link=True)
        self.assertEqual(h.e.web.proposals[pending['proposal_id']]['status'],'revoked')
        self.assertFalse((h.folders[journey.WORK]/'Documents/must-not-save.docx').exists())
        self.assertEqual(client.request('ping')[0],403)
        h.e.dispatch({'action':'web_enable','project_id':journey.CODE,'allow':False});h.idle()
        self.assertTrue(h.e.web.projects[journey.CODE]['manually_paused']);h.e.close();h.make_engine()
        h.select(journey.CODE);h.idle();self.assertNotIn(journey.CODE,h.e.web.enabled)
        self.assertEqual(h.e.automatic.states[journey.CODE]['pause_reason'],'manual')
        h.select(journey.WORK);h.idle();self.assertEqual(h.e.automatic.states[journey.WORK]['status'],'connected')
        self.assertEqual(h.e.web.enabled,{journey.WORK});self.assertEqual(len(h.service.active),1)
        self.assertFalse((h.folders[journey.WORK]/'Documents/must-not-save.docx').exists())

if __name__=='__main__':unittest.main()
