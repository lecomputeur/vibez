import base64
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('alpha9_web', ROOT/'backend/web_connector.py')
web = importlib.util.module_from_spec(spec); spec.loader.exec_module(web)
A = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'
B = 'bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb'


class FilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        self.a=self.root/'Alpha'; self.b=self.root/'Beta'; self.a.mkdir(); self.b.mkdir()
        (self.a/'sentinel.txt').write_text('untouched'); (self.b/'other.txt').write_text('beta')
        self.c=web.Connector(lambda event:None,self.root/'private',approval_wait=0)
        self.c.select({'id':A,'name':'Fixture'}); self.c.link(A,str(self.a))

    def tearDown(self): self.c.close(); self.tmp.cleanup()

    def test_multiple_scopes_mcp_routing_selected_import_and_reload(self):
        self.c.add_folder(A,str(self.b),self.c.workspace_binding(A))
        roots=self.c.snapshot()['folders']; self.assertEqual(len(roots),2)
        ws=self.c.project_workspace(A)
        self.assertEqual(len(ws.listing()['entries']),2)
        alias=next(r['alias'] for r in roots if r['path']==str(self.b))
        self.assertEqual(ws.read(alias+'/other.txt')['content'],'beta')
        with self.assertRaises(ValueError):ws.read('../sentinel.txt')
        src=self.root/'new.txt';src.write_text('copy')
        self.c.import_files(A,self.c.snapshot()['import_binding'],[str(src)])
        self.assertEqual((self.b/'new.txt').read_text(),'copy');self.assertFalse((self.a/'new.txt').exists())
        self.c.pause(A); self.c.close();self.c=web.Connector(lambda event:None,self.root/'private',approval_wait=0)
        self.assertEqual(len(self.c.projects[A]['folders']),2);self.assertTrue(self.c.projects[A]['manually_paused'])

    def test_local_browser_moves_without_clobber_and_rejects_escape_links_stale_context(self):
        rev=self.c.workspace_binding(A); (self.a/'child').mkdir()
        self.c.local_files(A,rev,'move','sentinel.txt','child')
        self.assertEqual((self.a/'child/sentinel.txt').read_text(),'untouched')
        (self.a/'sentinel.txt').write_text('second')
        with self.assertRaises(OSError):self.c.local_files(A,rev,'move','sentinel.txt','child')
        self.assertEqual((self.a/'sentinel.txt').read_text(),'second')
        for path in ['../Beta','/tmp','.private']:
            with self.assertRaises((ValueError,OSError)):self.c.local_files(A,rev,'list',path)
        self.c.local_files(A,rev,'mkdir','child',name='Nested')
        self.assertTrue((self.a/'child/Nested').is_dir())
        self.c.add_folder(A,str(self.b),rev)
        with self.assertRaises(ValueError):self.c.local_files(A,rev,'list')
        self.c.select({'id':B,'name':'Other'})
        with self.assertRaises(ValueError):self.c.local_files(A,self.c.workspace_binding(A),'list')

    def test_real_office_files_are_readable_but_never_editable_as_plain_text(self):
        ws=self.c.project_workspace(A)
        try:
            for name,word in [('notes.doc','München'),('notes.docx','München'),('numbers.xls','Amsterdam')]:
                shutil.copy2(ROOT/'tests/standalone/fixtures/office'/name,self.a/name)
                read=ws.read(name);self.assertIn(word,read['content']);self.assertTrue(read['read_only'])
                with self.assertRaises(ValueError):ws.proposal(name,'replace original')
            self.assertEqual((self.a/'sentinel.txt').read_text(),'untouched')
        finally: ws.close()

    def test_xml_formats_and_malformed_archives_are_bounded_and_read_only(self):
        cases={'.odt':('content.xml','<document><p>City trip</p></document>'),
               '.ods':('content.xml','<document><table><table-row><table-cell><p>42</p></table-cell></table-row></table></document>'),
               '.odp':('content.xml','<document><p>Slide proof</p></document>'),
               '.pptx':('ppt/slides/slide1.xml','<slide><p><t>Slide proof</t></p></slide>'),
               '.xlsx':('xl/worksheets/sheet1.xml','<worksheet><row><c r="A1" t="inlineStr"><is><t>Sheet proof</t></is></c></row></worksheet>')}
        ws=self.c.project_workspace(A)
        try:
            for ext,(part,content) in cases.items():
                with zipfile.ZipFile(self.a/('sample'+ext),'w') as z:z.writestr(part,content)
                self.assertTrue(ws.read('sample'+ext)['content'])
            (self.a/'bad.docx').write_bytes(b'not a zip')
            with self.assertRaises(ValueError):ws.read('bad.docx')
            with zipfile.ZipFile(self.a/'entity.odt','w') as z:z.writestr('content.xml','<!DOCTYPE x [<!ENTITY a "no">]><x><p>&a;</p></x>')
            with self.assertRaises(ValueError):ws.read('entity.odt')
        finally: ws.close()

    def test_mcp_image_is_an_actual_image_content_block_and_cross_root_paths_are_denied(self):
        raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9e0AAAAASUVORK5CYII=')
        (self.a/'pixel.png').write_bytes(raw);self.c.enable(A,True)
        _,headers,_=self.c.rpc(A,None,{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}}})
        sid=headers['Mcp-Session-Id']
        _,_,result=self.c.rpc(A,sid,{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'read_image','arguments':{'path':'pixel.png'}}})
        value=result['result'];self.assertFalse(value['isError']);image=value['content'][0]
        self.assertEqual(image['type'],'image');self.assertEqual(image['mimeType'],'image/png');self.assertEqual(base64.b64decode(image['data']),raw)
        with self.assertRaises(ValueError):self.c.project_workspace(A).read_image('../Beta/other.txt')


if __name__=='__main__':unittest.main()
