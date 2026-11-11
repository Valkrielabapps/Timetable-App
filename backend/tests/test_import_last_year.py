"""
Last year's timetable as the starting point: each section's printed week
(class teacher and class on top, period numbers, then "SUBJECT-TEACHER" in
every cell) read into the sections, subjects, teachers, class teachers,
periods of each subject and who taught them - and the shape of the week.
Modelled on a real school's file.
"""
from app.core.database import SessionLocal
from app.models.school import ClassGroup, Period, Subject, SubjectRequirement, Teacher
from app.services.smart_import import _split_cell, plan_tables, read_sheets, smart_rows
from tests.conftest import create_school, signup
from tests.test_smart_import import NoAI, xlsx

DAYS = ["Mon", "Tues", "Wed", "Thurs", "Frid"]


def week(header, rows, number_row=True):
    out = [header]
    if number_row:
        out.append(["Days", 1, 2, 3, 4, 5])
    for d, r in zip(DAYS, rows):
        out.append([d] + r)
    return out


SENIOR = week(["Tr's Name :  MRS.ROSEE-   XI A"], [
    ["BIO-ROS,BHAG", "BHAGYA", "MAT-DEVA", "ENG-V'G", "GAME-KALKATH,JOSEPH"],
    ["BIO-ROS,BHAG", "BHAGYA", "MAT-DEVA", "ENG-V'G", "PHY-KARTHIGAI"],
    ["MAT-DEVA", "PHY-KARTHIGAI", "BIP-ROSEE", "ENG-V'G", "CHEM-VAHINI"],
    ["MAT-DEVA", "PHY-KARTHI", "CHEM-VAHINI", "MAT-DEV", "CHEM-VAHINI"],
    ["PHY-KARTHIGAI", "CHEM-VAHINI", "MAT-DEVA", "ENG-V'G", "ELECTIVES"],
]) + week(["Teacher's Name  :      11 C", None, "MRS.VIJAYA GEETHA", None, None, "X  A"], [
    ["ENG-V'G", "MAT-JEROM", "ENG-2-SOFIA", "GAME-KAL,JO", "SOC-VINO"],
    ["ENG-V'G", "MAT-JEROM", "EN-2-SOFIA", "SOC-VINOTHINI", "MAT-JEROM"],
    ["ENG-V'G", "MAT-JEROM", "SOC-VINO", "SOC-VINOTHINI", "MAT-JEROM"],
    ["2LN-LAVANYA", "MAT-JEROM", "ENG-2-SOFIA", "SOC-VINO", "ELECTIVES"],
    ["2LN-LAVANYA", "MAT-JEROM", "MAT-LEKAREAD-JENITA", "SOC-VINO", "ENG-V'G"],
])
PRIMARY = week(["TEACHERS NAME-MS.PERSIS                    I A"], [
    ["ENG-PERSIS", "MAT-SWATHY", "EVS-KRITHIKA", "C.T-PERSIS", "H.W-PERSIS"],
    ["ENG-PERSIS", "MAT-SWATHI", "EVS-KRITHI", "C.T-PERSIS", "H.W-PER"],
    ["ENG-PERSIS", "MAT-SWATHY", "EVS-KRITHI", "C.T-PERSIS", "H.W-PER"],
    ["READ-PER", "MAT-SWATHY", "EVS-KRITHIKA", "C.T-PERSIS", "H.W-PER"],
    ["ENG-PERSIS", "MAT-SWATHY", "EVS-KRITHIKA", "C.T-PERSIS", "H.W-PERSIS"],
]) + week(["TEACHERS NAME :   BLESSY                   II B"], [
    ["ENG-BLESSY", "MAT-SWATHY", "HIN-PARAM", "C.T-BLESSY", "H.W-BLESSY"],
    ["ENG-BLESSY", "MAT-SWATHY", "HIN-PARAMESHWARI", "C.T-BLESSY", "H.W-BLESSY"],
    ["ENG-BLESSY", "MAT-SWATHY", "HIN-PARAM", "C.T-BLESSY", "H.W-BLESSY"],
    ["ENG-BLESSY", "MAT-SWATHY", "EVS-KRITHI", "C.T-BLESSY", "H.W-BLESSY"],
    ["ENG-BLESSY", "MAT-SWATHY", "EVS-KRITHIKA", "C.T-BLESSY", "H.W-BLESSY"],
])
FILE = xlsx(("XI AND XII", SENIOR), ("I TO V", PRIMARY))


def test_reading_a_cell():
    assert _split_cell("BIO-ROS,BHAG") == ("BIO", ["ROS", "BHAG"])
    assert _split_cell("BIO-ROS/VIGN") == ("BIO", ["ROS", "VIGN"])
    assert _split_cell("ENG-2-SOFIA") == ("ENG 2", ["SOFIA"])
    assert _split_cell("BHAGYA") == ("", ["BHAGYA"])
    assert _split_cell("MAT-LEKAREAD-JENITA")[0] == "?"


def test_every_section_its_periods_teachers_and_class_teacher():
    _, tables = plan_tables(read_sheets("t.xlsx", FILE))
    by = {t["label"]: t for t in tables}
    assert set(by) == {"Class XI A", "Class X A", "Class I A", "Class II B"}
    xi = {s: (n, w) for s, n, w in by["Class XI A"]["items"]}
    assert by["Class XI A"]["class_teacher"] == "Rosee"
    assert xi["BIO"][0] == "5" and set(xi["BIO"][1].split("/")) == {"Rosee", "Bhagya"}  # "BHAGYA" alone continues the lab; "BIP" is BIO
    assert xi["MAT"] == ("6", "Deva")  # "DEV" is Deva
    assert xi["PHY"] == ("4", "Karthigai")  # "KARTHI" too
    assert xi["ENG"] == ("4", "Vijaya Geetha")  # "V'G": her initials
    assert xi["ELECTIVES"] == ("1", "")  # a subject alone, not a teacher
    xa = {s: (n, w) for s, n, w in by["Class X A"]["items"]}
    assert by["Class X A"]["class_teacher"] == "Vijaya Geetha"
    assert xa["ENG 2"] == ("3", "Sofia")  # "EN-2" is "ENG-2"
    assert xa["SOC"] == ("6", "Vinothini")
    assert xa["GAME"][1] == "Kalkath/Joseph"  # "KAL,JO" from the same subject elsewhere
    assert sum(int(n) for n, _ in xa.values()) == 24  # the unreadable cell is left out
    ia = {s: (n, w) for s, n, w in by["Class I A"]["items"]}
    assert ia["MAT"] == ("5", "Swathy") and ia["EVS"] == ("5", "Krithika") and ia["H.W"] == ("5", "Persis")
    assert by["Class II B"]["class_teacher"] == "Blessy"
    assert {s: w for s, _, w in by["Class II B"]["items"]}["HIN"] == "Parameshwari"
    assert by["Class I A"]["week"] == {"days": [0, 1, 2, 3, 4], "periods": 5}


def test_the_teachers_import_reads_it_too():
    rows, _ = smart_rows("teachers", "t.xlsx", FILE, ai=NoAI())
    by = {r["name"]: r["qualified_subjects"].split(";") for r in rows}
    assert "Maths" in by["Swathy"] and "Swathi" not in by
    assert "Biology" in by["Bhagya"]


def test_starting_from_it_sets_up_the_school(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    r = client.post("/api/class-plan/preview", data={"school_id": sid},
                    files={"file": ("last year.xlsx", FILE, "application/octet-stream")}, headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["from_timetable"] and p["week"] == {"days": [0, 1, 2, 3, 4], "periods": 5}
    assert "Deva" in p["new_teachers"] and p["questions"] == []  # nobody it could be confused with
    r = client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": {}}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["periods"] == 25
    db = SessionLocal()
    try:
        assert db.query(Period).filter_by(school_id=sid).count() == 25
        subs = {s.id: s.name for s in db.query(Subject).filter_by(school_id=sid)}
        names = {t.id: t.name for t in db.query(Teacher).filter_by(school_id=sid)}
        g = db.query(ClassGroup).filter_by(school_id=sid, grade="Grade 11", name="A").one()
        assert names[g.class_teacher_id] == "Rosee"
        plan = {subs[x.subject_id]: (x.periods_per_week, names.get(x.preferred_teacher_id))
                for x in db.query(SubjectRequirement).filter_by(class_group_id=g.id)}
        assert plan["Maths"] == (6, "Deva") and plan["English"] == (4, "Vijaya Geetha")
        ia = db.query(ClassGroup).filter_by(school_id=sid, grade="Grade 1", name="A").one()
        assert names[ia.class_teacher_id] == "Persis"
        # Everyone is qualified for what they taught.
        deva = db.query(Teacher).filter_by(school_id=sid, name="Deva").one()
        assert "Maths" in {subs[i] for i in deva.qualified_subject_ids}
    finally:
        db.close()
