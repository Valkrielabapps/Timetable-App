"""
A staff sheet laid out the way many schools keep it: a small table per
class (label, then Subjects | Periods | Teacher, then a Total), several side
by side and several stacked.
"""
from app.services.smart_import import check_rows, is_label, smart_rows
from tests.test_smart_import import FakeAI, NoAI, xlsx

GRADES = ["Grade 1", "Grade 6", "Grade 7", "Grade 11"]

SHEET = [
    ["CLASS 1-AB", "", "", "", "CLASS 7-AB", "", ""],
    ["Subjects", "Periods", "Teacher", "", "Subjects", "Periods", "Teacher"],
    ["Phonics", "4", "Meghna", "", "English Lang", "3", "Deepti/Shobana"],
    ["Maths", "5", "Zareena/Shallu", "", "Maths", "6", "Ashutosh"],
    ["Art", "1", "Zareena/Shallu", "", "Assembly", "0", "Class teacher"],
    ["Total", "20", "", "", "TOTAL", "40", ""],
    [],
    ["CLASS 6-AB", "", "", "", "CLASS 11 Science", "", ""],
    ["Subjects", "Periods", "Teacher", "", "Subjects", "Periods", "Teacher"],
    ["English Lang", "3", "Deepti", "", "Maths/Bio", "7", "Aman/Deepak"],
    ["Hist/civ", "3", "Usha", "", "English Lit + Lib", "4", "Anjana"],
    ["Science Practical periods should be together", "", "", "", "P.T", "1", "Lakhan"],
    ["TOTAL", "40", "", "", "Total", "40", ""],
]


def test_labels_totals_and_notes_are_never_names():
    for junk in ("Total", "TOTAL", "Subjects", "CLASS 6-AB", "CLASS 10 (Sci)", "Class 12 commerce",
                 "Science Practical periods should be together", "40", "School Year:", "School Term:",
                 "Term: 1", "Session", "Prepared by", "Remarks", "Academic Year 2026-27:"):
        assert is_label(junk), junk
    for real in ("Maths", "English Lang", "Life skill", "SUPW/PT", "Music", "Yearbook", "Ratio: Maths"[7:]):
        assert not is_label(real), real


def test_every_class_table_gives_its_subjects():
    rows, info = smart_rows("subjects", "alloc.xlsx", xlsx(("2026", SHEET)), ai=NoAI())
    names = [r["name"] for r in rows]
    assert info["layout"] == "class_tables"
    assert names == ["Phonics", "Maths", "Art", "English Lang", "Assembly", "Hist", "civ", "Bio", "English Lit",
                     "Lib", "P.T"]
    assert not {"Total", "TOTAL", "Subjects", "CLASS 6-AB"} & set(names)
    assert "a table for each class (4: CLASS 1-AB, CLASS 7-AB, CLASS 6-AB, CLASS 11 Science)" in info["read_as"][0]


def test_teachers_get_their_subjects_and_classes_from_the_tables():
    rows, info = smart_rows("teachers", "alloc.xlsx", xlsx(("2026", SHEET)),
                            school_subjects=["Mathematics", "Biology", "English Language"], school_grades=GRADES,
                            ai=NoAI())
    by = {r["name"]: r for r in rows}
    assert "Class teacher" not in by
    assert by["Zareena"]["qualified_subjects"] == "Mathematics;Art"
    assert by["Shallu"]["qualified_grades"] == "Grade 1"
    assert by["Deepti"]["qualified_grades"] == "Grade 7;Grade 6"
    # "Maths/Bio" taught by "Aman/Deepak": one each.
    assert by["Aman"]["qualified_subjects"] == "Mathematics" and by["Deepak"]["qualified_subjects"] == "Biology"
    assert by["Aman"]["qualified_grades"] == "Grade 11"


def test_the_ai_is_not_asked_to_guess_columns_for_class_tables():
    ai = FakeAI()
    smart_rows("subjects", "alloc.xlsx", xlsx(("2026", SHEET)), ai=ai)
    assert "columns" not in ai.seen and "values" in ai.seen


def test_one_ordinary_table_is_still_read_as_before():
    rows, info = smart_rows("subjects", "s.csv", b"Subjects,Periods,Teacher\nMaths,5,Anil\nTotal,5,\n", ai=NoAI())
    assert info["layout"] == "rows" and [r["name"] for r in rows] == ["Maths"]


def test_names_that_may_be_one_teacher_are_flagged():
    checks, _ = check_rows("teachers", [{"name": "Kavita K", "qualified_subjects": "Hindi"},
                                        {"name": "Kavita Khana", "qualified_subjects": "Hindi"},
                                        {"name": "Kavita Singh", "qualified_subjects": "Hindi"}])
    assert any("“Kavita K” and “Kavita Khana” may be the same teacher" in c for c in checks)
    assert not any("Kavita Singh" in c for c in checks)


def test_form_fields_above_a_plain_list_are_skipped():
    csv = b"School Year:,2026-27\nSchool Term:,1\n\nSubject,Room\nMaths,\nChemistry,lab\nPrepared by,Anil\n"
    rows, _ = smart_rows("subjects", "s.csv", csv, ai=NoAI())
    assert [r["name"] for r in rows] == ["Maths", "Chemistry"]
