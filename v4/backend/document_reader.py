"""Bounded, read-only document extraction. Never executes macros or links."""
import base64
import io
import posixpath
from pathlib import Path
import re
import struct
import json
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

MAX_BINARY = 10 * 1024 * 1024
MAX_XML = 32 * 1024 * 1024
MAX_TEXT = 256 * 1024
OFFICE = {'.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp', '.doc', '.xls'}


def bounded_text(parts):
    out = []
    size = 0
    for part in parts:
        size += len(part.encode('utf-8'))
        if size > MAX_TEXT:
            raise ValueError('Extracted document text exceeds 256 KiB. Use a smaller document.')
        out.append(part)
    return '\n'.join(out)


class TextParts(list):
    def __init__(self): super().__init__(); self.bytes = 0
    def append(self, value):
        self.bytes += len(value.encode('utf-8')) + 1
        if self.bytes > MAX_TEXT: raise ValueError('Extracted document text exceeds 256 KiB.')
        super().append(value)
    def extend(self, values):
        for value in values: self.append(value)


def xml(data):
    if len(data) > MAX_XML or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Unsupported or oversized document XML.')
    return ET.fromstring(data)


def local(tag):
    return tag.rsplit('}', 1)[-1]


def paragraph_text(node):
    # ODF encodes retained spaces/tabs as elements rather than literal text.
    # Bound them before allocation, including malicious text:c repeat counts.
    namespace = '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'
    chunks = []; size = 0; stack = [(node, False)]
    def add(value):
        nonlocal size
        size += len(value.encode('utf-8'))
        if size > MAX_TEXT: raise ValueError('Extracted document text exceeds 256 KiB.')
        chunks.append(value)
    while stack:
        current, tail = stack.pop()
        if tail:
            if current.tail: add(current.tail)
            continue
        if current.tag == namespace + 's':
            count = current.get(namespace + 'c', '1')
            if not re.fullmatch(r'[0-9]{1,6}', count) or not 1 <= int(count) <= MAX_TEXT:
                raise ValueError('Extracted document text exceeds 256 KiB.')
            add(' ' * int(count))
        elif current.tag == namespace + 'tab': add('\t')
        elif current.tag == namespace + 'line-break': add('\n')
        else:
            if current.text: add(current.text)
            for child in reversed(list(current)):
                stack.append((child, True)); stack.append((child, False))
    return ''.join(chunks)


def paragraphs(tree):
    for node in tree.iter():
        if local(node.tag) in ('p', 'h'):
            yield paragraph_text(node)


def presentation_slides(archive, names):
    """Use the presentation's explicit order; orphaned parts are not slides.

    Older small fixtures omit both package metadata parts. Their conventional
    slideN.xml names have a bounded numeric fallback, never lexical 1,10,2.
    """
    presentation = 'ppt/presentation.xml'
    relationships = 'ppt/_rels/presentation.xml.rels'
    if presentation not in names:
        if relationships in names: raise ValueError('The presentation metadata is incomplete.')
        return sorted((name for name in names if re.fullmatch(r'ppt/slides/slide[0-9]+\.xml', name)),
                      key=lambda name: int(re.search(r'slide([0-9]+)\.xml$', name)[1]))
    tree = xml(archive.read(presentation))
    slide_list = next((node for node in tree if local(node.tag) == 'sldIdLst'), None)
    if slide_list is None or not len(slide_list): return []
    if relationships not in names: raise ValueError('The presentation metadata is incomplete.')
    relation_ns = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    targets = {}
    for relationship in xml(archive.read(relationships)):
        if local(relationship.tag) != 'Relationship' or relationship.get('Type') != relation_ns[1:-1] + '/slide': continue
        identifier, target = relationship.get('Id'), relationship.get('Target')
        if not identifier or identifier in targets or not target or relationship.get('TargetMode', 'Internal') != 'Internal' or any(c in target for c in ('\\', ':', '?', '#', '\0')) or target.startswith('//'):
            raise ValueError('The presentation contains an unsupported slide relationship.')
        part = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('ppt', target))
        if part.startswith('../') or part not in names or not part.endswith('.xml'):
            raise ValueError('The presentation refers to an unavailable slide.')
        targets[identifier] = part
    ordered = []
    for slide in slide_list:
        if local(slide.tag) != 'sldId': continue
        part = targets.get(slide.get(relation_ns + 'id'))
        if part is None or part in ordered: raise ValueError('The presentation slide order is invalid.')
        ordered.append(part)
        if len(ordered) > 5000: raise ValueError('The presentation contains too many slides.')
    return ordered


def zipped(raw, extension):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        if len(infos) > 5000 or sum(i.file_size for i in infos) > MAX_XML:
            raise ValueError('The document archive is too large.')
        names = [i.filename for i in infos]
        if len(set(names)) != len(names) or any(i.flag_bits & 1 for i in infos):
            raise ValueError('Encrypted or ambiguous documents are not supported.')
        if extension == '.docx':
            wanted = ['word/document.xml'] + sorted(n for n in names if re.fullmatch(r'word/(?:header|footer)\d+\.xml', n))
            return bounded_text(part for name in wanted for part in paragraphs(xml(z.read(name))))
        if extension == '.pptx':
            wanted = presentation_slides(z, names)
            return bounded_text(part for name in wanted for part in paragraphs(xml(z.read(name))))
        if extension in ('.odt', '.odp'):
            return bounded_text(paragraphs(xml(z.read('content.xml'))))
        if extension == '.ods':
            result = TextParts()
            for table in xml(z.read('content.xml')).iter():
                if local(table.tag) != 'table':
                    continue
                result.append('Sheet: ' + next((v for k, v in table.attrib.items() if local(k) == 'name'), ''))
                for row in table:
                    if local(row.tag) != 'table-row':
                        continue
                    cells = []
                    for cell in row:
                        if local(cell.tag) not in ('table-cell', 'covered-table-cell'):
                            continue
                        value = ' '.join(paragraphs(cell))
                        repeat = int(next((v for k, v in cell.attrib.items() if local(k) == 'number-columns-repeated'), '1'))
                        if repeat > 1000:
                            if value: raise ValueError('Too many repeated spreadsheet cells.')
                            repeat = 1
                        cells.extend([value] * repeat)
                    repeat = int(next((v for k, v in row.attrib.items() if local(k) == 'number-rows-repeated'), '1'))
                    if repeat > 1000:
                        if any(cells): raise ValueError('Too many repeated spreadsheet rows.')
                        repeat = 1
                    result.extend(['\t'.join(cells)] * repeat)
                    if len(result) > 10000: raise ValueError('Too many spreadsheet rows.')
            return bounded_text(result)
        shared = []
        if 'xl/sharedStrings.xml' in names:
            shared = [''.join(n.itertext()) for n in xml(z.read('xl/sharedStrings.xml')) if local(n.tag) == 'si']
        result = TextParts()
        for name in sorted(n for n in names if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n)):
            result.append('Sheet: ' + Path(name).stem)
            for row in xml(z.read(name)).iter():
                if local(row.tag) != 'row': continue
                values = []
                for cell in row:
                    if local(cell.tag) != 'c': continue
                    value = next((n.text or '' for n in cell if local(n.tag) == 'v'), '')
                    if cell.get('t') == 's': value = shared[int(value)]
                    elif cell.get('t') == 'inlineStr': value = ''.join(cell.itertext())
                    # Include cell addresses, preserving sparse column meaning.
                    values.append(cell.get('r', '') + ': ' + value)
                result.append('\t'.join(values))
        return bounded_text(result)


def vendor(name):
    # Only shipped, signed backend modules enter Python's isolated import path.
    directory = str(Path(__file__).resolve().parent / 'vendor/python')
    if directory not in sys.path: sys.path.insert(0, directory)
    return __import__(name)


def legacy_doc(raw):
    olefile = vendor('olefile')
    with olefile.OleFileIO(io.BytesIO(raw)) as ole:
        word = ole.openstream('WordDocument').read(MAX_BINARY + 1)
        if len(word) > MAX_BINARY or len(word) < 154: raise ValueError('Invalid Word document.')
        flags = struct.unpack_from('<H', word, 10)[0]
        if flags & 0x8100: raise ValueError('Encrypted Word documents are not supported.')
        table = ole.openstream('1Table' if flags & 0x200 else '0Table').read(MAX_BINARY + 1)
        if len(table) > MAX_BINARY: raise ValueError('Word table is too large.')
        pos = 34 + 2 * struct.unpack_from('<H', word, 32)[0]
        pos += 2 + 4 * struct.unpack_from('<H', word, pos)[0]
        count = struct.unpack_from('<H', word, pos)[0]
        if count <= 33: raise ValueError('Save this older document in DOCX format.')
        offset, size = struct.unpack_from('<II', word, pos + 2 + 33 * 8)
        if offset + size > len(table): raise ValueError('Invalid Word piece table.')
        clx = table[offset:offset + size]; pos = 0
        while pos < len(clx) and clx[pos] == 1:
            pos += 3 + struct.unpack_from('<H', clx, pos + 1)[0]
        if pos >= len(clx) or clx[pos] != 2: raise ValueError('Invalid Word text table.')
        length = struct.unpack_from('<I', clx, pos + 1)[0]; plc = clx[pos + 5:pos + 5 + length]
        if length != len(plc) or length < 4 or (length - 4) % 12: raise ValueError('Invalid Word text table.')
        count = (length - 4) // 12
        if count > 100000: raise ValueError('Word document is too complex.')
        parts = []
        for i in range(count):
            start, end = struct.unpack_from('<II', plc, i * 4)
            if end < start or end - start > MAX_TEXT: raise ValueError('Word text is too large.')
            pointer = struct.unpack_from('<I', plc, 4 * (count + 1) + i * 8 + 2)[0]
            compressed = bool(pointer & 0x40000000); address = pointer & 0x3fffffff
            if compressed: address //= 2
            size = (end - start) * (1 if compressed else 2)
            if address + size > len(word): raise ValueError('Word text is outside the document.')
            parts.append(word[address:address + size].decode('cp1252' if compressed else 'utf-16-le', errors='replace'))
        return bounded_text(parts).replace('\r', '\n')


def extract_document(raw, extension):
    if len(raw) > MAX_BINARY: raise ValueError('Documents must be at most 10 MiB.')
    try:
        if extension == '.doc': text = legacy_doc(raw)
        elif extension == '.xls':
            xlrd = vendor('xlrd')
            book = xlrd.open_workbook(file_contents=raw, on_demand=True)
            try:
                parts = TextParts()
                for sheet in book.sheets():
                    if sheet.nrows * sheet.ncols > 100000: raise ValueError('Too many spreadsheet cells.')
                    parts.append('Sheet: ' + sheet.name)
                    for r in range(sheet.nrows): parts.append('\t'.join(str(v) for v in sheet.row_values(r)))
                text = bounded_text(parts)
            finally: book.release_resources()
        else: text = zipped(raw, extension)
        return {'content': text, 'format': extension.lstrip('.'), 'read_only': True,
                'note': 'Extracted text and cached cell values only; macros, formulas and external links are not executed. Use the original Office application to edit this document.'}
    except (zipfile.BadZipFile, ET.ParseError, KeyError, IndexError, struct.error, UnicodeError, OSError) as e:
        raise ValueError('This document could not be read. It may be damaged, encrypted or unsupported.') from e


def image(raw, extension):
    if len(raw) > MAX_BINARY: raise ValueError('Images must be at most 10 MiB.')
    kind = None
    if raw.startswith(b'\x89PNG\r\n\x1a\n'): kind = 'image/png'
    elif raw.startswith(b'\xff\xd8\xff'): kind = 'image/jpeg'
    elif raw.startswith((b'GIF87a', b'GIF89a')): kind = 'image/gif'
    elif raw.startswith(b'RIFF') and raw[8:12] == b'WEBP': kind = 'image/webp'
    if not kind: raise ValueError('Choose a PNG, JPEG, GIF or WebP image.')
    return {'type': 'image', 'data': base64.b64encode(raw).decode('ascii'), 'mimeType': kind}


def document(raw, extension):
    if extension not in OFFICE or len(raw) > MAX_BINARY: raise ValueError('Unsupported or oversized Office document.')
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
    try:
        result = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()), '--extract', extension],input=raw,capture_output=True,timeout=8,**options)
        if result.returncode or len(result.stdout)>2*1024*1024: raise ValueError('Office extraction failed or exceeded its limits.')
        response = json.loads(result.stdout)
        if 'error' in response: raise ValueError(response['error'])
        return response['result']
    except (subprocess.TimeoutExpired,json.JSONDecodeError) as e:
        raise ValueError('Office extraction exceeded its limits or the document could not be read.') from e


if __name__ == '__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--extract' or sys.argv[2] not in OFFICE: raise SystemExit(2)
    try:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU,(5,5))
            resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
        except (ImportError,ValueError,OSError): pass
        value=extract_document(sys.stdin.buffer.read(MAX_BINARY+1),sys.argv[2])
        response={'result':value}
    except Exception:
        response={'error':'This Office document could not be read within the supported limits. It may be damaged, encrypted or unsupported.'}
    sys.stdout.write(json.dumps(response,ensure_ascii=False))
