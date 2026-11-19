"""
Uploaded .xlsx and .docx files are zips of XML. A real one never declares a
DTD or entities; one that does could expand a few kilobytes into gigabytes
when read ("billion laughs"), or point at files on the server (XXE). Both are
refused - in any text encoding - with the usual message for a bad upload.
"""
import io
import zipfile

import openpyxl
import pytest

from app.services import bulk_import, setup_extractor, smart_import

_LAUGHS = (
    '<!DOCTYPE lolz [<!ENTITY lol "lol">'
    '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
    '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>'
)
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(document_xml: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def _document(text: str, prolog: str = "") -> str:
    return (f'<?xml version="1.0" encoding="UTF-8"?>{prolog}'
            f'<w:document xmlns:w="{_W}"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')


def test_a_plain_word_document_is_still_read():
    sheets = smart_import.docx_sheets(_docx(_document("Anita Rao").encode()))
    assert any("Anita Rao" in cell for _, rows in sheets for row in rows for cell in row)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_a_word_document_with_entities_is_refused(encoding):
    xml = _document("&lol3;", _LAUGHS).replace('encoding="UTF-8"', f'encoding="{encoding.upper()}"')
    with pytest.raises(ValueError, match="valid Word document"):
        smart_import.docx_sheets(_docx(xml.encode(encoding)))


def test_a_word_document_pointing_at_a_server_file_is_refused():
    xml = _document("&x;", '<!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>')
    with pytest.raises(ValueError, match="valid Word document"):
        smart_import.docx_sheets(_docx(xml.encode()))


def _xlsx(prolog: str = "") -> bytes:
    """A real workbook from openpyxl, with `prolog` put before its sheet's XML."""
    wb = openpyxl.Workbook()
    wb.active["A1"] = "Name"
    wb.active["A2"] = "Anita Rao"
    src = io.BytesIO()
    wb.save(src)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(src.getvalue())) as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml" and prolog:
                # After the XML declaration if there is one, else at the very start.
                head, sep, rest = data.partition(b"?>")
                data = head + sep + prolog.encode() + rest if sep else prolog.encode() + data
            zout.writestr(item, data)
    return out.getvalue()


def test_a_plain_spreadsheet_is_still_read():
    sheets = smart_import.read_sheets("staff.xlsx", _xlsx())
    assert ["Name"] in sheets[0][1] and ["Anita Rao"] in sheets[0][1]


@pytest.mark.parametrize("reader", [
    lambda c: smart_import.read_sheets("staff.xlsx", c),
    lambda c: bulk_import.parse_rows("staff.xlsx", c),
    lambda c: setup_extractor.read_spreadsheet_rows("staff.xlsx", c),
], ids=["smart import", "bulk import", "setup extraction"])
def test_a_spreadsheet_with_entities_is_refused(reader):
    content = _xlsx(_LAUGHS)
    with pytest.raises(ValueError, match="Excel files never have"):
        reader(content)
