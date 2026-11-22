"""
Last year's timetable in any of the shapes schools print it - a grid per
section either way round, every section on one sheet, a grid per teacher, a
PDF or a photo - read into each section's plan, every lesson where it was,
the week's bell times and breaks, the blocks and the fixed periods.
"""
from app.core.database import SessionLocal
from app.models.school import ElectiveBlock, Period, School, Teacher, Timetable, TimetableEntry
from app.services import smart_import
from app.services.smart_import import _split_cell, read_sheets
from app.services.timetable_reader import day_of, find_grids, period_no, read_timetable, time_of
from tests.conftest import create_school, signup
from tests.test_smart_import import xlsx

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def test_small_readers():
    assert [day_of(x) for x in ("MONDAY", "Tues", "Th", "Frid", "Day 3", "Maths")] == [0, 1, 3, 4, 2, None]
    assert [period_no(x) for x in ("3", "3.0", "III", "P3", "PERIOD III", "3rd", "Period 3", "Lunch")] == \
        [3, 3, 3, 3, 3, 3, 3, None]
    assert time_of("8.40 to 9.20") == "8:40-9:20" and time_of("08:40 AM - 09:20 AM") == "8:40-9:20"


def test_a_cell_with_its_teacher_any_way_it_is_written():
    assert _split_cell("Maths (Mrs. Kavitha Rao)") == ("Maths", ["Kavitha Rao"])
    assert _split_cell("Maths\nK. Rao") == ("Maths", ["K. Rao"])
    assert _split_cell("Maths/K. Rao") == ("Maths", ["K. Rao"])
    assert _split_cell("History (Theory)") == ("", ["History (Theory)"])
    # A block's options stay one value.
    assert _split_cell("Tamil/Hindi") == ("", ["Tamil/Hindi"])
    assert _split_cell("Bio/M") == ("", ["Bio/M"])


def grid(section, rows, teacher="", times=True, breaks="letters"):
    """A section's week as Aditya Birla prints it: the section, the class
    teacher, period numbers, a row of bell times, a break column."""
    head = ["Day / Period", "1", "2", "", "3", "4", "5"]
    bell = ["Time", "8:40-9:20", "9:20-10:00", "", "10:20-11:00", "11:00-11:40", "11:40-12:20"]
    out = [[section]] + ([[f"CLASS TEACHER – {teacher}"]] if teacher else []) + [head] + ([bell] if times else [])
    for d, r in enumerate(rows):
        out.append([DAYS[d]] + r[:2] + [("BREAK"[d] if breaks == "letters" else "")] + r[2:])
    return out + [[]]


WEEK_6A = [["ENG-PRIYA", "MAT-RAVI", "VI L1", "SCI-ANU", "CT-PRIYA"]] * 5
WEEK_6B = [["MAT-RAVI", "ENG-PRIYA", "VI L1", "SST-JOHN", "CT-MEENA"]] * 5
LEGEND = [["(VI L1- TAM/HIN)"]]


def test_class_grids_with_bells_breaks_a_legend_a_block_and_a_fixed_period():
    rows = LEGEND + grid("VI A", WEEK_6A, "MRS. PRIYA") + grid("VI B", WEEK_6B, "MEENA")
    r = read_timetable(read_sheets("t.xlsx", xlsx(("Sheet1", rows))))
    assert [s["label"] for s in r["sections"]] == ["Class VI A", "Class VI B"]
    assert r["week"]["bell_times"][1] == "8:40-9:20" and r["week"]["breaks"] == [{"after": 2, "name": "Break"}]
    les = {(l["day"], l["period"]): l for l in r["sections"][0]["lessons"]}
    assert les[(0, 3)]["subject"] == "TAM/HIN" and les[(0, 1)]["teachers"] == ["Priya"]
    # TAM/HIN at period 3 in both sections, every day: one block.
    (b,) = [b for b in r["blocks"] if not b.get("together")]
    assert b["sections"] == ["Class VI A", "Class VI B"] and b["periods"] == 5
    assert [o["subject"] for o in b["options"]] == ["TAM", "HIN"]
    # The class teacher's period: period 5 every day in every section.
    assert {(f["subject"], f["period"], f["days"]) for f in r["fixed"]} >= {("CT", 5, None)}
    by = {t["label"]: dict((s, n) for s, n, _ in t["block_items"]) for t in r["tables"]}
    assert "TAM/HIN" not in by["Class VI A"] and by["Class VI A"]["ENG"] == "5"


def test_periods_down_and_days_across_with_breaks_as_rows():
    rows = [["Time Table - VII B"], ["Time", *DAYS]]
    rows += [["8:40 to 9:20", "ENG", "MAT", "SCI", "ENG", "MAT"], ["9:20 to 10:00", "MAT", "ENG", "ENG", "SCI", "SST"],
             ["SHORT BREAK", "", "", "", "", ""], ["10:20 to 11:00", "SCI", "SST", "MAT", "MAT", "ENG"]]
    r = read_timetable(read_sheets("t.xlsx", xlsx(("VII B", rows))))
    assert r["sections"][0]["label"] == "Class VII B"
    assert r["week"]["periods"] == 3 and r["week"]["bell_times"][3] == "10:20-11:00"
    assert r["week"]["breaks"] == [{"after": 2, "name": "Short Break"}]


def test_every_section_on_one_master_sheet():
    head1, head2 = ["Class"], [""]
    for d in DAYS:
        head1 += [d, "", ""]
        head2 += ["1", "2", "3"]
    rows = [["MASTER TIME TABLE"], head1, head2,
            ["Class 6 A"] + ["ENG", "MAT", "SCI"] * 5, ["Class 6 B"] + ["MAT", "SCI", "ENG"] * 5]
    r = read_timetable(read_sheets("m.csv", "\n".join(",".join(x) for x in rows).encode()))
    assert [s["label"] for s in r["sections"]] == ["Class VI A", "Class VI B"]
    assert {(l["day"], l["period"], l["subject"]) for l in r["sections"][1]["lessons"]} >= {(4, 3, "ENG")}


def test_a_grid_per_teacher_is_turned_into_each_sections_week():
    def tgrid(title, rows):
        return [[title], ["DAY/PERIODS", "1", "2", "3"]] + [[DAYS[d]] + r for d, r in enumerate(rows)] + [[]]

    rows = tgrid("Mrs. Kavitha Rao (TGT Maths)", [["VI A", "VI B", ""]] * 5) \
        + tgrid("TGT: ENGLISH 1", [["VI B", "", "VI A"]] * 5) \
        + tgrid("Anu", [["", "VI A/SCI", "VI B/SCI"]] * 5)
    r = read_timetable(read_sheets("t.xlsx", xlsx(("Sheet1", rows))))
    assert r["view"] == "teacher"
    by = {t["label"]: {s: (n, w) for s, n, w in t["items"]} for t in r["tables"]}
    assert by["Class VI A"]["Maths"] == ("5", "Kavitha Rao") and by["Class VI A"]["SCI"] == ("5", "Anu")
    assert by["Class VI B"]["ENGLISH"] == ("5", "Tgt: English 1")


def test_one_name_for_two_teachers_is_found_and_asked_about():
    rows = grid("VI A", [["ENG-PRIYA", "MAT-RAVI", "SCI-ANU", "SST-JOHN", "ART-RAVI"]] * 5, breaks="") \
        + grid("VII A", [["MUS-LATA", "MAT-RAVI", "ENG-PRIYA", "SCI-ANU", "SST-JOHN"]] * 5, breaks="")
    r = read_timetable(read_sheets("t.xlsx", xlsx(("Sheet1", rows))))
    (x,) = r["same_names"]
    assert x["name"] == "Ravi" and len(x["people"]) == 2 and "VI A" in x["example"]


def _school(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    return sid, h


def _preview(client, sid, h, name, content):
    r = client.post("/api/class-plan/preview", data={"school_id": sid},
                    files={"file": (name, content, "application/octet-stream")}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_starting_from_it_keeps_blocks_fixed_periods_breaks_and_the_timetable_itself(client):
    sid, h = _school(client)
    rows = LEGEND + grid("VI A", WEEK_6A, "MRS. PRIYA") + grid("VI B", WEEK_6B, "MEENA")
    p = _preview(client, sid, h, "t.xlsx", xlsx(("Sheet1", rows)))
    ids = {q["id"] for q in p["questions"]}
    assert {"blocks:all", "fixed:all", "asis"} <= ids
    assert any("Breaks: Break after period 2" in f for f in p["found"])
    answers = {q["id"]: q["suggested"] for q in p["questions"]}
    r = client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": answers}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kept_as_version"] == {"version": 1, "lessons": 50, "not_placed": 0}
    db = SessionLocal()
    try:
        # The week: 5 lessons and the break after period 2, labelled with the bell times.
        mon = db.query(Period).filter_by(school_id=sid, day_of_week=0).order_by(Period.order).all()
        assert [(p.kind, p.label) for p in mon][:3] == [("lesson", "Period 1 (8:40-9:20)"),
                                                        ("lesson", "Period 2 (9:20-10:00)"), ("break", "Break")]
        (block,) = db.query(ElectiveBlock).filter_by(school_id=sid).all()
        assert len(block.section_ids) == 2 and block.periods_per_week == 5
        school = db.get(School, sid)
        assert [(f["period"], f["days"]) for f in school.fixed_periods] == [(5, None)]
        tt = db.query(Timetable).filter_by(school_id=sid).one()
        assert tt.solver_status == "manual" and tt.name == "Last year's, as it was"
        entries = db.query(TimetableEntry).filter_by(timetable_id=tt.id).all()
        assert sum(1 for e in entries if e.elective_block_id) == 2 * 5 * 2  # two options, two sections, five days
    finally:
        db.close()


def test_a_name_split_in_two_becomes_two_teachers(client):
    sid, h = _school(client)
    rows = grid("VI A", [["ENG-PRIYA", "MAT-RAVI", "SCI-ANU", "SST-JOHN", "ART-RAVI"]] * 5, breaks="") \
        + grid("VII A", [["MUS-LATA", "MAT-RAVI", "ENG-PRIYA", "SCI-ANU", "SST-JOHN"]] * 5, breaks="")
    p = _preview(client, sid, h, "t.xlsx", xlsx(("Sheet1", rows)))
    answers = {q["id"]: q["suggested"] for q in p["questions"]}
    assert answers["same:Ravi"] == "split"
    r = client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": answers}, headers=h)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        names = {t.name for t in db.query(Teacher).filter_by(school_id=sid)}
        assert len([n for n in names if n.startswith("Ravi (")]) == 2 and "Ravi" not in names
    finally:
        db.close()


def test_a_pdf_or_photo_is_written_out_by_the_ai_then_read_the_same_way(client, monkeypatch):
    sid, h = _school(client)
    rows = LEGEND + grid("VI A", WEEK_6A, "MRS. PRIYA") + grid("VI B", WEEK_6B, "MEENA")
    sent = []

    def fake(self, content, media_type):
        sent.append(media_type)
        return [{"title": "page 1", "lines_above": [], "rows": [[str(c) for c in r] for r in rows]}]

    monkeypatch.setattr(smart_import.LiveAI, "transcribe", fake)
    smart_import._TRANSCRIBED.clear()
    p = _preview(client, sid, h, "last year.pdf", b"%PDF-1.4 pretend")
    assert p["from_timetable"] and p["summary"]["classes"] == 2
    assert sent == ["application/pdf"]  # once, however many ways the file is read
    assert [g["sheet"] for g in find_grids(read_sheets("x.jpg", b"%PDF-1.4 pretend"))] == ["page 1", "page 1"]


def test_without_the_ai_a_pdf_says_so(client, monkeypatch):
    sid, h = _school(client)
    monkeypatch.setattr(smart_import.LiveAI, "transcribe", lambda self, c, m: None)
    smart_import._TRANSCRIBED.clear()
    r = client.post("/api/class-plan/preview", data={"school_id": sid},
                    files={"file": ("t.png", b"\x89PNG not really", "image/png")}, headers=h)
    assert r.status_code == 400 and "read by the AI" in r.json()["detail"]


def test_a_short_code_nobody_knows_is_asked_once_and_remembered(client):
    """Seen in Keren's real timetable: ESK, CUET, H.W, COM, SUBW."""
    sid, h = _school(client)
    rows = grid("VI A", [["ENG-PRIYA", "SUBW-RAVI", "ESK-ANU", "SST-JOHN", "COM-RAVI"]] * 5, breaks="") \
        + grid("VI B", [["ESK-ANU", "ENG-PRIYA", "SUBW-RAVI", "COM-RAVI", "SST-JOHN"]] * 5, breaks="")
    p = _preview(client, sid, h, "t.xlsx", xlsx(("Sheet1", rows)))
    qs = {q["id"]: q for q in p["questions"]}
    assert "It's SUPW" in [o["label"] for o in qs["code:SUBW"]["options"]]
    assert {"It's Computer Science", "It's Commerce"} <= {o["label"] for o in qs["code:COM"]["options"]}
    answers = {q["id"]: q["suggested"] for q in p["questions"]}
    answers.update({"code:SUBW": "is:SUPW", "code:COM": "is:Computer Science"})
    r = client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": answers}, headers=h)
    assert r.status_code == 200, r.text
    names = set(r.json()["subjects"])
    assert {"SUPW", "Computer Science", "ESK"} <= names and "SUBW" not in names and "COM" not in names
    forms = {(x["text"], x["meaning"]) for x in client.get(f"/api/schools/{sid}/short-forms", headers=h).json()["items"]}
    assert ("SUBW", "SUPW") in forms
    # Next time: not asked.
    p = _preview(client, sid, h, "t.xlsx", xlsx(("Sheet1", rows)))
    assert "code:SUBW" not in {q["id"] for q in p["questions"]}


def test_a_name_that_is_one_person_on_the_staff_list_is_not_offered_as_two():
    rows = grid("VI A", [["ENG-PRIYA", "MAT-RAVI", "SCI-ANU", "SST-JOHN", "ART-RAVI"]] * 5, breaks="") \
        + grid("VII A", [["MUS-LATA", "MAT-RAVI", "ENG-PRIYA", "SCI-ANU", "SST-JOHN"]] * 5, breaks="")
    staff = [{"name": "Ravi", "subjects": ["Maths"]}, {"name": "Priya", "subjects": ["English"]}]
    r = read_timetable(read_sheets("t.xlsx", xlsx(("Sheet1", rows))), staff)
    assert r["same_names"] == []
    assert any(c.startswith("Ravi is down for two classes at once") and "Taught together, or a slip" in c
               for c in r["checks"])


def test_twice_a_week_at_one_period_is_not_a_fixed_period():
    week = [["ENG-PRIYA", "MAT-RAVI", "AI-ANU", "SST-JOHN", "CT-PRIYA"],
            ["ENG-PRIYA", "MAT-RAVI", "AI-ANU", "SST-JOHN", "CT-PRIYA"],
            ["ENG-PRIYA", "MAT-RAVI", "SCI-ANU", "SST-JOHN", "CT-PRIYA"],
            ["ENG-PRIYA", "MAT-RAVI", "SCI-ANU", "SST-JOHN", "CT-PRIYA"],
            ["ENG-PRIYA", "MAT-RAVI", "SCI-ANU", "SST-JOHN", "CT-PRIYA"]]
    rows = grid("XI A", week, breaks="") + grid("XI B", [[c.replace("PRIYA", "MEENA") for c in r] for r in week], breaks="")
    r = read_timetable(read_sheets("t.xlsx", xlsx(("Sheet1", rows))))
    subjects = {f["subject"] for f in r["fixed"]}
    assert "AI" not in subjects and "CT" in subjects


def test_a_pdf_made_by_software_is_read_off_the_page_without_the_ai(monkeypatch, tmp_path):
    """A timetable exported as PDF (Excel, aSc, Rivelle itself) has its text
    in it: read in seconds, exactly, and the AI is never asked."""
    import pytest
    pytest.importorskip("pdfplumber")
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors

    story, st = [], getSampleStyleSheet()
    for sec, week in (("VI A", WEEK_6A), ("VI B", WEEK_6B)):
        story.append(Paragraph(sec, st["Heading4"]))
        data = [["Day", "1", "2", "3", "4", "5"]] + [[DAYS[d]] + r for d, r in enumerate(week)]
        t = Table(data)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
        story.append(t)
    path = tmp_path / "t.pdf"
    SimpleDocTemplate(str(path), pagesize=landscape(A4)).build(story)
    monkeypatch.setattr(smart_import.LiveAI, "transcribe", lambda *a: (_ for _ in ()).throw(AssertionError("AI asked")))
    smart_import._TRANSCRIBED.clear()
    r = read_timetable(read_sheets("t.pdf", path.read_bytes(), "timetable"))
    assert [s["label"] for s in r["sections"]] == ["Class VI A", "Class VI B"]
    assert {(l["day"], l["period"], l["subject"]) for l in r["sections"][0]["lessons"]} >= {(0, 1, "ENG")}


def test_a_long_scanned_pdf_is_refused_with_what_to_do(monkeypatch):
    monkeypatch.setattr(smart_import, "pdf_tables", lambda content: None)
    smart_import._TRANSCRIBED.clear()
    pdf = b"%PDF-1.4 " + b"<< /Type /Page >> " * 12 + b"<< /Type /Pages >>"
    import pytest
    with pytest.raises(ValueError, match="12 pages of scanned images"):
        read_sheets("scan.pdf", pdf)


def test_cells_of_a_timetable_exported_as_pdf():
    """How Rivelle's own PDF (and most printed grids) lay out a cell: the
    subject on its line(s), the teacher on the last; a block as its name then
    each group's subject and teacher; "No teacher yet"."""
    cases = {
        "H.W\nPersis": ("H.W", ["Persis"]),
        "Environmental\nScience\nKrithika": ("Environmental Science", ["Krithika"]),
        "Games\nKalkath/Joseph": ("Games", ["Kalkath", "Joseph"]),
        "Hindi (3rd language)\nParameshwari": ("Hindi (3rd language)", ["Parameshwari"]),
        "ELECTIVES\nNo teacher yet": ("ELECTIVES", []),
        "SECOND LANGUAGE\nTamil\nBeaula\nTamil\nAbirami\nHindi\nSabina": ("Tamil/Tamil/Hindi", ["Beaula", "Abirami", "Sabina"]),
        "BIO/CS\nComputer Science\nVignesh\nBiology\nRosee": ("Computer Science/Biology", ["Vignesh", "Rosee"]),
        "Math Deepa": ("Math", ["Deepa"]),
        "MATHEMATICS-Mrs.\nSangeetha Nair": ("MATHEMATICS", ["Sangeetha Nair"]),
    }
    for cell, want in cases.items():
        assert _split_cell(cell) == want, cell
    for whole in ["Environmental\nScience", "Physical\nEducation", "Class Teacher Period", "English Literature", "Hindi I"]:
        assert _split_cell(whole)[0] in ("",), whole
