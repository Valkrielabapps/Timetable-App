"""
A school's list as a Word document: its tables read like sheets, or, with
no tables, its lines read as a list. Then the same as an Excel upload.
"""
import io
import zipfile
from xml.sax.saxutils import escape

import pytest

from app.services import smart_import
from app.services.smart_import import smart_rows
from tests.conftest import create_school, signup
from tests.test_smart_import import NoAI

NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def para(text):
    runs = "".join(
        ("<w:r><w:tab/></w:r>" if i else "") + f"<w:r><w:t xml:space=\"preserve\">{escape(part)}</w:t></w:r>"
        for i, part in enumerate(text.split("\t"))
    )
    return f"<w:p>{runs}</w:p>"


def cell(text, span=1, merge=None):
    pr = ""
    if span > 1 or merge:
        pr = "<w:tcPr>" + (f'<w:gridSpan w:val="{span}"/>' if span > 1 else "") + (
            '<w:vMerge w:val="restart"/>' if merge == "restart" else "<w:vMerge/>" if merge else "") + "</w:tcPr>"
    return f"<w:tc>{pr}{''.join(para(p) for p in text.split(chr(10)))}</w:tc>"


def table(rows):
    return "<w:tbl>" + "".join("<w:tr>" + "".join(c if c.startswith("<w:tc>") else cell(c) for c in r) + "</w:tr>"
                               for r in rows) + "</w:tbl>"


def docx(*body):
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document {NS}><w:body>{"".join(body)}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def read(content, kind="teachers", **kw):
    return smart_rows(kind, "staff.docx", content, ai=NoAI(), **kw)


def test_a_table_in_a_word_document_reads_like_a_sheet():
    doc = docx(
        para("Riverside Public School"), para("Staff list 2026-27"),
        table([
            ["S.No", "Name of Teacher", "Subjects", "Classes"],
            ["1", cell("Priya Sharma", merge="restart"), "Maths", "IX"],
            ["", cell("", merge="continue"), "Physics", "X"],
            ["2", "Rahul Mehta", "Eng\nHindi", "6-8"],
        ]),
    )
    rows, info = read(doc, school_subjects=["Mathematics"], school_grades=["Grade 6", "Grade 7", "Grade 8", "Grade 9", "Grade 10"])
    assert info["sheet"] == "table 1 of the document"
    # The merged name cell covers both of Priya's rows.
    assert [r["name"] for r in rows] == ["Priya Sharma", "Priya Sharma", "Rahul Mehta"]
    assert rows[0]["qualified_subjects"] == "Mathematics" and rows[1]["qualified_subjects"] == "Physics"
    assert rows[2]["qualified_subjects"] == "English;Hindi"  # two lines in one cell are two subjects
    assert rows[2]["qualified_grades"] == "Grade 6;Grade 7;Grade 8"


def test_a_cell_spanning_two_columns_keeps_the_rest_in_line():
    doc = docx(table([[cell("Teacher details", span=2), "Subjects"], ["Name", "Email", "Subjects"],
                      ["Anita Rao", "anita@school.in", "Biology"]]))
    rows, _ = read(doc)
    assert rows == [{"name": "Anita Rao", "email": "anita@school.in", "qualified_subjects": "Biology"}]


def test_one_table_per_department_is_one_list():
    head = ["Name", "Subjects"]
    doc = docx(para("Science"), table([head, ["Anita Rao", "Biology"]]),
               para("Languages"), table([head, ["Meena Iyer", "English"]]))
    rows, info = read(doc)
    assert [r["name"] for r in rows] == ["Anita Rao", "Meena Iyer"]


def test_a_typed_list_without_a_table():
    doc = docx(para("Our teachers"), para("1. Priya Sharma - Maths, Physics"), para("2. Rahul Mehta: English"),
               para("3. Anita Rao (Biology)"), para("4. Mary-Ann Joseph – Hindi"))
    rows, info = read(doc)
    assert info["sheet"] == "the document's text"
    assert [(r["name"], r["qualified_subjects"]) for r in rows] == [
        ("Priya Sharma", "Maths;Physics"), ("Rahul Mehta", "English"), ("Anita Rao", "Biology"),
        ("Mary-Ann Joseph", "Hindi")]


def test_tab_separated_lines():
    doc = docx(para("Name\tSubjects\tWorkload"), para("Priya Sharma\tMaths\t28"))
    rows, _ = read(doc)
    assert rows == [{"name": "Priya Sharma", "qualified_subjects": "Maths", "max_periods_per_week": "28"}]


def test_a_plain_list_of_subjects():
    doc = docx(para("Subjects"), para("Mathematics"), para("Chemistry"), para("Physical Education"))
    rows, _ = read(doc, kind="subjects")
    assert [r["name"] for r in rows] == ["Mathematics", "Chemistry", "Physical Education"]


def test_an_old_doc_file_and_a_broken_docx_say_what_to_do():
    with pytest.raises(ValueError, match="Save As > Word Document"):
        smart_rows("teachers", "staff.doc", b"x", ai=NoAI())
    with pytest.raises(ValueError, match="valid .docx"):
        smart_rows("teachers", "staff.docx", b"not a zip", ai=NoAI())


def test_uploading_a_word_document_previews_then_imports(client, monkeypatch):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    monkeypatch.setattr(smart_import, "LiveAI", NoAI)
    doc = docx(table([["Name", "Subjects"], ["Priya Sharma", "Maths"], ["Anil Kumar", ""]]))
    p = client.post("/api/teachers/bulk-import/preview", data={"school_id": sid},
                    files={"file": ("staff.docx", doc, "application/octet-stream")}, headers=h)
    assert p.status_code == 200, p.text
    p = p.json()
    assert p["total"] == 2 and p["sheet"] == "table 1 of the document"
    assert any("no subjects (Anil Kumar)" in c for c in p["checks"])
    r = client.post("/api/teachers/bulk-import/commit", json={"school_id": sid, "rows": p["rows"]}, headers=h)
    assert r.json()["created"] == 2
