"""
Subject and staff lists the way schools keep them: a KV-style staff table
with posts like "TGT (Maths)" and the office staff in it, a typed list with
"Eng & SST" and "6 to 8", departments as headings, a teacher-by-teacher
allotment, a subject list per class, a grid of periods with the classes as
bare numbers, and plain text files.
"""
from app.services.class_plan import plan_tables
from app.services.smart_import import _entry, is_label, look_alike_people, read_sheets, smart_rows
from tests.test_smart_import import NoAI, xlsx


def csv(rows):
    return "\n".join(",".join(r) for r in rows).encode()


def test_a_kv_staff_table_posts_office_staff_and_honorifics():
    rows = [["STAFF DETAILS"], ["S.No", "Name", "Designation", "Date of joining", "Employee Code"],
            ["1", "Shri. Anand Raj", "Principal", "01/06/2019", "9985"],
            ["2", "Mrs. Priya Menon", "TGT - Social Science", "21/07/2024", "68847"],
            ["3", "MS.SANGEETHA", "PGT (Mathematics)", "13/03/2018", "36581"],
            ["4", "|Mary Thomas", "TGT(English)", "", ""],
            ["5", "Sh. Mani", "Sub Staff", "", ""], ["6", "Smt. Rani", "Office Assistant", "", ""],
            ["7", "VIDYA DAS", "PRT", "", ""]]
    out, _ = smart_rows("teachers", "staff.csv", csv(rows), ai=NoAI())
    by = {r["name"]: r.get("qualified_subjects", "") for r in out}
    assert set(by) == {"Priya Menon", "Sangeetha", "Mary Thomas", "Vidya Das"}  # no principal, office or sub staff
    assert by["Sangeetha"] == "Mathematics" and by["Mary Thomas"] == "English"
    assert by["Vidya Das"] == ""  # a PRT with no subject named: not "Class VI"


def test_a_typed_staff_list_with_a_classes_column_is_a_staff_list():
    rows = [["Name", "Subjects Handled", "Classes", "Mobile"],
            ["Lavanya", "Art & Craft", "6 to 8", "9215565814"], ["Mrs. Sarah", "English", "7 & 10", ""],
            ["Imran George", "Computer Science", "6 to 10", ""]]
    out, _ = smart_rows("teachers", "t.csv", csv(rows), ai=NoAI())
    by = {r["name"]: r for r in out}
    assert by["Sarah"]["qualified_grades"] == "7;10" and by["Lavanya"]["qualified_subjects"] == "Art"


def test_departments_as_headings_give_their_subject():
    rows = [["Sl", "Name of the Teacher", "Designation", "Classes"], ["", "ENGLISH DEPARTMENT", "", ""],
            ["1", "Mrs. Beula Reddy", "TGT", "6 to 8"], ["2", "Mr. Ganesh", "PGT", "11, 12"],
            ["", "Dept. of Social Science", "", ""], ["3", "Ms. Rekha", "TGT", "9"]]
    out, _ = smart_rows("teachers", "t.xlsx", xlsx(("Staff", rows)), ai=NoAI())
    by = {r["name"]: (r.get("qualified_subjects"), r.get("qualified_grades")) for r in out}
    assert by == {"Beula Reddy": ("English", "6 to 8"), "Ganesh": ("English", "11;12"),
                  "Rekha": ("Social Studies", "9")}


def test_a_teacher_by_teacher_allotment_with_the_post_after_the_name():
    rows = [["WORK ALLOTMENT 2025-26"], ["IMRAN GEORGE (TGT)"], ["X A - COMP - 3"], ["VI A - COMP - 2"], [""],
            ["MRS.LAVANYA (TGT)"], ["VI A - ART - 1"], ["VII A - ART - 1"], [""],
            ["RAVI KUMAR (PGT)"], ["XI A - PHY - 6"], ["XII A - PHY - 6"]]
    out, _ = smart_rows("teachers", "a.xlsx", xlsx(("Allotment", rows)), ai=NoAI())
    by = {r["name"]: r["qualified_subjects"] for r in out}
    assert by == {"Imran George": "Computer Science", "Lavanya": "Art", "Ravi Kumar": "Physics"}
    assert _entry("VI A - ART - 1") == ("VI", ["A"], 1, "ART")
    assert _entry("VIDYA DAS") is None and _entry("IVABCD-8") == ("IV", ["A", "B", "C", "D"], 8, "")


def test_plain_text_files():
    text = b"WORK ALLOTMENT\nMRS.LAVANYA (TGT)\nVI A - ART - 1\nVII A - ART - 1\n\nIMRAN GEORGE (TGT)\n" \
           b"X A - COMP - 3\nVI A - COMP - 2\nVII A - COMP - 2\n"
    out, _ = smart_rows("teachers", "a.txt", text, ai=NoAI())
    assert {r["name"] for r in out} == {"Lavanya", "Imran George"}
    subjects, _ = smart_rows("subjects", "s.txt", b"Subjects offered\nClass VI: Eng, Maths, Sci, Hindi\n"
                                                    b"Class VII: English, Maths, Science, Hindi, SUPW\n", ai=NoAI())
    names = [r["name"] for r in subjects]
    assert "SUPW" in names and names.count("English") == 1 and "Eng" not in names
    staff, _ = smart_rows("teachers", "s.txt", b"Priya Sharma - Maths\nRahul Mehta - English\nAnu - Science\n",
                          ai=NoAI())
    assert {r["name"]: r["qualified_subjects"] for r in staff}["Rahul Mehta"] == "English"


def test_a_subject_list_per_class_and_a_single_letter_short_form():
    rows = [["Class VI", "E, Maths, Science, Hindi"], ["Class VII", "English, Maths, Science, Hindi"],
            ["Class VIII", "English, M, Science, Sanskrit, C.T"]]
    out, _ = smart_rows("subjects", "s.xlsx", xlsx(("Subjects", rows)), ai=NoAI())
    names = [r["name"] for r in out]
    assert sorted(names) == sorted(["English", "Maths", "Science", "Hindi", "Sanskrit", "Class Teacher Period"])


def test_a_periods_grid_with_classes_as_bare_numbers():
    rows = [["Subject", "3", "4", "5", "6"], ["English", "9", "9", "9", "7"], ["EVS", "7", "7", "7", ""],
            ["Science", "", "", "", "7"], ["Robotics", "", "", "", "1"], ["TOTAL", "16", "16", "16", "15"]]
    sheets = read_sheets("a.xlsx", xlsx(("Allotment", rows)), "subjects")
    _, tables = plan_tables(sheets)
    by = {t["label"]: {s: n for s, n, _ in t["items"]} for t in tables}
    assert by["Class 6"] == {"English": "7", "Science": "7", "Robotics": "1"} and by["Class 3"]["EVS"] == "7"
    out, _ = smart_rows("subjects", "a.xlsx", xlsx(("Allotment", rows)), ai=NoAI())
    assert [r["name"] for r in out] == ["English", "Environmental Studies", "Science", "Robotics"]


def test_names_written_short_are_asked_about():
    pairs = look_alike_people(["K. Rao", "Kavitha Rao", "Priya", "Priya Sharma", "Arun", "Meena"])
    assert ("K. Rao", "Kavitha Rao") in pairs and ("Priya", "Priya Sharma") in pairs
    assert not any("Arun" in p for p in pairs)


def test_the_class_teacher_period_is_a_subject_not_a_label():
    assert not is_label("Class Teacher Period") and not is_label("Class Teacher")
    assert is_label("Class VII") and is_label("Class 7 A")
