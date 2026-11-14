"""Office creation uses plain text, real ZIP formats and existing local approval.

Only disposable folders are used. No external account, tunnel or installed app.
"""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('office_create_web', BASE/'backend/web_connector.py')
web = importlib.util.module_from_spec(spec); spec.loader.exec_module(web)
base = web.base
writer = base.document_writer
A = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'
B = 'bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb'
SAMPLE = 'SAVE\nMünchen & <City> "notes" 🧳\n  keep  spaces\tand tabs'


class WriterTests(unittest.TestCase):
    def test_six_modern_formats_are_deterministic_real_passive_zip_documents(self):
        for ext in sorted(writer.FORMATS):
            with self.subTest(ext=ext):
                text, fmt, raw = writer.render('new'+ext, SAMPLE)
                self.assertEqual(fmt, ext); self.assertEqual(text, SAMPLE)
                self.assertEqual(raw, writer.render('new'+ext, SAMPLE)[2])
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    self.assertIsNone(archive.testzip()); names=archive.namelist()
                    self.assertEqual(len(names),len(set(names)))
                    for name in names:
                        self.assertFalse(name.startswith('/')); self.assertNotIn('..',name.split('/'))
                        if name.endswith(('.xml','.rels')):
                            tree=ET.fromstring(archive.read(name))
                            self.assertFalse(any(node.tag.rsplit('}',1)[-1] in ('f','hyperlink','script') for node in tree.iter()))
                            self.assertFalse(any(node.get('TargetMode') == 'External' for node in tree.iter()))
                    if ext in writer.ODF_MIME:
                        self.assertEqual(names[0],'mimetype'); self.assertEqual(archive.infolist()[0].compress_type,zipfile.ZIP_STORED)
                        self.assertEqual(archive.read('mimetype').decode(),writer.ODF_MIME[ext])
                    self.assertFalse(any('vba' in name.lower() or 'macro' in name.lower() for name in names))
                extracted=base.documents.document(raw,ext)['content']
                self.assertIn('SAVE',extracted);self.assertIn('München & <City> "notes" 🧳',extracted)
                if ext in ('.odt','.docx'):self.assertEqual(extracted,SAMPLE)

    def test_spreadsheet_formula_like_text_and_xml_stay_inert(self):
        text='=WEBSERVICE("https://example.invalid")\t+SUM(A1:A3)\n@SUM(2)\t<script>&literal'
        for ext in ('.ods','.xlsx'):
            raw=writer.render('safe'+ext,text)[2]
            self.assertIn('=WEBSERVICE',base.documents.document(raw,ext)['content'])
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                payload=archive.read('content.xml' if ext=='.ods' else 'xl/worksheets/sheet1.xml')
                self.assertNotIn(b'table:formula=',payload);self.assertNotIn(b'<f>',payload)
                self.assertIn(b'&lt;script&gt;',payload)
                self.assertNotIn(b'TargetMode=',payload)

    def test_supported_input_is_normalized_and_unsupported_or_oversized_input_rejected(self):
        self.assertEqual(writer.render('FILE.ODT','line\r\nsecond\rthird')[0],'line\nsecond\nthird')
        for path in ('sample.doc','sample.xls','sample.pdf','sample.zip','sample.docm','sample.txt'):
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'Choose ODT'):writer.render(path,'text')
        for text in [None,b'bytes','\0','\x0b','\x1f','\ud800','x'*(writer.MAX_CONTENT+1)]:
            with self.subTest(text_type=type(text).__name__),self.assertRaises(ValueError):writer.render('sample.odt',text)
        for text in ['x\t'*100,'x\n'*1000,'x'*32768]:
            with self.assertRaisesRegex(ValueError,'1000 rows'):writer.render('sample.xlsx',text)
        with self.assertRaisesRegex(ValueError,'100 slides'):writer.render('sample.pptx','slide\n\n'*100)

    def test_pptx_uses_presentation_relationship_order_for_twelve_slides(self):
        lines = ['Slide '+str(number) for number in range(1,13)]
        raw = writer.render('ordered.pptx','\n\n'.join(lines))[2]
        self.assertEqual(base.documents.document(raw,'.pptx')['content'].splitlines(),lines)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            parts={name:archive.read(name) for name in archive.namelist()}
        tree=ET.fromstring(parts['ppt/presentation.xml'])
        sequence=next(node for node in tree if node.tag.rsplit('}',1)[-1]=='sldIdLst')
        items=list(sequence);reordered=[items[11],items[4],*items[:4],*items[5:11]]
        sequence[:]=reordered;parts['ppt/presentation.xml']=ET.tostring(tree)
        # An unreferenced slide part must not appear in the extracted deck.
        parts['ppt/slides/slide99.xml']=b'<slide><p>ORPHANED SLIDE</p></slide>'
        changed=io.BytesIO()
        with zipfile.ZipFile(changed,'w') as archive:
            for name,content in parts.items():archive.writestr(name,content)
        self.assertEqual(base.documents.document(changed.getvalue(),'.pptx')['content'].splitlines(),
                         [lines[11],lines[4],*lines[:4],*lines[5:11]])

    def test_pptx_without_package_metadata_uses_numeric_slide_names(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as archive:
            for number in reversed(range(1,13)):
                archive.writestr('ppt/slides/slide'+str(number)+'.xml','<slide><p>Slide '+str(number)+'</p></slide>')
        self.assertEqual(base.documents.document(out.getvalue(),'.pptx')['content'].splitlines(),
                         ['Slide '+str(number) for number in range(1,13)])

    def test_odf_whitespace_decoder_is_bounded_and_handles_spaces_tabs_and_linebreaks(self):
        xml='<office xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><text:p>Hello<text:s text:c="2"/>world<text:tab/>x<text:line-break/>Y</text:p></office>'
        self.assertEqual(list(base.documents.paragraphs(base.documents.xml(xml.encode()))),['Hello  world\tx\nY'])
        for count in ['9999999999','-1','999999','x']:
            xml='<office xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><text:p><text:s text:c="'+count+'"/></text:p></office>'
            with self.assertRaises(ValueError):list(base.documents.paragraphs(base.documents.xml(xml.encode())))


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='vibez-office-create-');self.root=Path(self.temp.name)
        self.folder=self.root/'Workspace';self.folder.mkdir();(self.folder/'subfolder').mkdir()
        self.original=self.folder/'sentinel.txt';self.original.write_text('Untouched existing file.')
        self.events=[];self.c=web.Connector(self.events.append,self.root/'profile',approval_wait=0)
        self.c.select({'id':A,'name':'Project'});self.c.link(A,self.folder);self.c.enabled.add(A)
        self.init()
    def init(self):
        with self.c.lock:
            _,headers,_=self.c.rpc(A,None,{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}})
        self.sid=headers['Mcp-Session-Id']
    def tearDown(self):
        self.assertEqual(self.original.read_text(),'Untouched existing file.')
        self.c.close();self.temp.cleanup()
    def tool(self,name,args):
        with self.c.lock:
            status,_,response=self.c.rpc(A,self.sid,{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':name,'arguments':args}})
        self.assertEqual(status,200);result=response['result'];return result,json.loads(result['content'][0]['text'])
    def propose(self,path='subfolder/saved.odt',content='SAVE',tool='create_document'):
        result,value=self.tool(tool,{'path':path,'content':content});self.assertFalse(result['isError'],value)
        self.assertEqual(value['status'],'pending');self.assertFalse(value['written']);self.assertFalse((self.folder/path).exists());self.assertEqual(value['destination'],'linked_local_folder');self.assertEqual(value['path'],path)
        pending=self.c.proposals[value['proposal_id']]['data'];self.assertEqual(pending['document_format'],Path(path).suffix.lower());self.assertEqual(pending['after'],content);self.assertNotIn('raw',pending)
        self.assertEqual(self.c.snapshot()['pending'][0]['document_format'],Path(path).suffix.lower())
        return value['proposal_id']

    def test_all_six_formats_require_local_approval_then_roundtrip_through_read_file(self):
        for ext in sorted(writer.FORMATS):
            path='subfolder/new'+ext;pid=self.propose(path);self.c.resolve(pid,True)
            status,value=self.tool('change_status',{'proposal_id':pid});self.assertFalse(status['isError']);self.assertEqual(value['status'],'saved');self.assertTrue(value['written']);self.assertEqual(value['destination'],'linked_local_folder');self.assertEqual(value['path'],path)
            result,value=self.tool('read_file',{'path':path});self.assertFalse(result['isError']);self.assertIn('SAVE',value['content']);self.assertTrue(value['read_only'])
            self.assertTrue(zipfile.is_zipfile(self.folder/path))
        self.assertEqual([v['action'] for v in self.c.activity].count('save_file'),6)

    def test_rejection_and_project_switch_never_create_any_document(self):
        pid=self.propose();self.c.resolve(pid,False);self.assertFalse((self.folder/'subfolder/saved.odt').exists())
        pid=self.propose();self.c.select({'id':B,'name':'Other'});self.assertEqual(self.c.proposals[pid]['status'],'revoked')
        with self.assertRaises(ValueError):self.c.resolve(pid,True)
        self.assertFalse((self.folder/'subfolder/saved.odt').exists())

    def test_workspace_replacement_revokes_pending_office_and_keeps_replacement_untouched(self):
        pid=self.propose();replacement=self.root/'Replacement';replacement.mkdir();(replacement/'keep.txt').write_text('replacement')
        self.c.link(A,replacement)
        with self.assertRaises(ValueError):self.c.resolve(pid,True)
        self.assertEqual(list(replacement.iterdir()),[replacement/'keep.txt']);self.assertFalse((self.folder/'subfolder/saved.odt').exists())

    def test_existing_office_files_never_get_overwritten_including_races(self):
        path=self.folder/'existing.odt';path.write_bytes(writer.render('existing.odt','Keep formatting')[2]);before=path.read_bytes()
        for tool in ['create_document','write_file']:
            result,value=self.tool(tool,{'path':'existing.odt','content':'overwrite'})
            self.assertTrue(result['isError']);self.assertEqual(value['error_code'],'document_exists');self.assertEqual(path.read_bytes(),before)
        pid=self.propose('race.odt');raced=self.folder/'race.odt';raced.write_bytes(b'Arrived after review')
        with self.assertRaises(ValueError):self.c.resolve(pid,True)
        self.assertEqual(raced.read_bytes(),b'Arrived after review');self.assertFalse(list(self.folder.glob('.vibez-*')))

    def test_atomic_publish_does_not_overwrite_a_file_created_at_the_last_moment(self):
        pid=self.propose('race.odt');original=base.os.rename_noreplace
        def competing(fd,source,target,*args):
            (self.folder/'race.odt').write_bytes(b'Concurrent file')
            return original(fd,source,target,*args)
        with patch.object(base.os,'rename_noreplace',competing):
            with self.assertRaises(FileExistsError):self.c.resolve(pid,True)
        self.assertEqual((self.folder/'race.odt').read_bytes(),b'Concurrent file');self.assertFalse(list(self.folder.glob('.vibez-*')))

    def test_create_document_rejects_escape_symlink_hidden_and_bad_arguments(self):
        outside=self.root/'Outside';outside.mkdir();(outside/'safe.odt').write_bytes(b'Keep')
        (self.folder/'linked').symlink_to(outside,target_is_directory=True)
        for path in ['../Outside/new.odt','/tmp/new.odt','.hidden/new.odt','linked/new.odt','linked/missing/new.odt']:
            result,value=self.tool('create_document',{'path':path,'content':'NO'})
            self.assertTrue(result['isError']);self.assertFalse((outside/'new.odt').exists())
        for args in [{'path':'new.odt','content':'SAVE','binary':'aGVsbG8='},{'path':'new.odt','content':3},{'path':'new.odt'}]:
            result,value=self.tool('create_document',args);self.assertTrue(result['isError']);self.assertEqual(value['error_code'],'invalid_arguments')
        self.assertEqual((outside/'safe.odt').read_bytes(),b'Keep')
        # A folder that does not exist yet is made when the new document is approved.
        result,value=self.tool('create_document',{'path':'missing/new.odt','content':'NEW'});self.assertEqual(value['status'],'pending')
        self.assertFalse((self.folder/'missing').exists());self.c.resolve(value['proposal_id'],True);self.assertTrue(zipfile.is_zipfile(self.folder/'missing/new.odt'))

    def test_new_office_files_also_work_for_a_cached_write_file_tool_without_changing_plain_text_writes(self):
        pid=self.propose(tool='write_file');self.c.resolve(pid,True);self.assertTrue(zipfile.is_zipfile(self.folder/'subfolder/saved.odt'))
        result,value=self.tool('write_file',{'path':'normal.txt','content':'text'});self.assertEqual(value['status'],'pending');self.c.resolve(value['proposal_id'],True);self.assertEqual((self.folder/'normal.txt').read_text(),'text')

    def test_multiple_roots_require_prefix_and_commit_only_the_selected_root(self):
        other=self.root/'Second';other.mkdir();self.c.add_folder(A,other,self.c.workspace_binding(A));self.c.enabled.add(A);self.init()
        alias=next(row['alias'] for row in self.c.snapshot()['folders'] if row['path']==str(other))
        result,value=self.tool('create_document',{'path':'new.odt','content':'SAVE'});self.assertTrue(result['isError']);self.assertEqual(value['error_code'],'workspace_prefix_required')
        result,value=self.tool('create_document',{'path':alias+'/new.odt','content':'SAVE'});self.assertFalse(result['isError']);self.assertEqual(value['status'],'pending')
        self.c.resolve(value['proposal_id'],True);self.assertTrue(zipfile.is_zipfile(other/'new.odt'));self.assertFalse((self.folder/'new.odt').exists())

    def test_dense_xlsx_is_rejected_before_review_when_cell_addresses_exceed_read_budget(self):
        content='\n'.join(['\t'.join(['x']*100)]*1000)
        self.assertEqual(len(content.encode()),199999)
        self.assertLess(len(content.encode()),writer.MAX_CONTENT)
        # The input is legal Office data, but its extracted cell addresses add
        # overhead. Do not save an unreadable file or widen extraction bounds.
        raw=writer.render('dense.xlsx',content)[2]
        with self.assertRaises(ValueError):base.documents.document(raw,'.xlsx')
        result,value=self.tool('create_document',{'path':'dense.xlsx','content':content})
        self.assertTrue(result['isError']);self.assertEqual(value['error_code'],'document_limit')
        self.assertIn('readable-text limit',value['message']);self.assertFalse((self.folder/'dense.xlsx').exists())
        self.assertEqual(self.c.proposals,{})
        smaller='\n'.join(['\t'.join(['x']*10)]*20)
        pid=self.propose('smaller.xlsx',smaller);self.c.resolve(pid,True)
        result,value=self.tool('read_file',{'path':'smaller.xlsx'});self.assertFalse(result['isError']);self.assertIn('J20: x',value['content'])

    def test_stdio_mcp_advertises_creation_and_keeps_approval_host_only(self):
        client=base.MCPClient(str(self.folder))
        try:
            self.assertIn('create_document',{tool['name'] for tool in client.tools})
            proposal=client.tool('create_document',{'path':'stdio.docx','content':'SAVE'})
            self.assertFalse((self.folder/'stdio.docx').exists());self.assertEqual(proposal['document_format'],'.docx')
            result=client.call('vibez/resolve',{'proposal_id':proposal['proposal_id'],'allow':True});self.assertTrue(result['written'])
            self.assertIn('SAVE',client.tool('read_file',{'path':'stdio.docx'})['content'])
        finally:client.close()


if __name__=='__main__':unittest.main()
