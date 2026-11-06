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
    assert names == ["Phonics", "Maths", "Art", "English Language", "Assembly", "History", "Civics", "Biology",
                     "English Literature", "Library", "Physical Education"]
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


def test_the_ai_cannot_fold_a_lab_or_skill_into_another_subject():
    # What the AI did with this sheet: tidied separate periods away.
    folded = {"Physics Lab": ["Physics"], "Chemistry Lab": ["Chemistry"], "Mental Maths": ["Mathematics"],
              "Reading": ["English"], "Cursive": ["English"], "Science Prac": ["Science"],
              "Eng Gram": ["English"], "Assembly": [], "Maths": ["Mathematics"], "Hist": ["History"],
              "Lib": ["Library"], "Phy": ["Physics"]}
    sheet = [["CLASS 2", "", "", "", "CLASS 12 Science", "", ""],
             ["Subjects", "Periods", "Teacher", "", "Subjects", "Periods", "Teacher"],
             ["Maths", "5", "Anil", "", "Phy", "6", "Vivek"],
             ["Mental Maths", "0", "", "", "Physics Lab", "2", ""],
             ["Reading", "1", "Anjali", "", "Chemistry Lab", "2", ""],
             ["Cursive", "0", "", "", "Hist", "3", "Ajay"],
             ["Eng Gram", "2", "Maya", "", "Science Prac", "1", "Akshma"],
             ["Assembly", "0", "", "", "Lib", "1", "Deepti"]]
    ai = FakeAI(subjects=folded)
    rows, _ = smart_rows("subjects", "a.xlsx", xlsx(("S", sheet)), school_subjects=["Mathematics"], ai=ai)
    names = [r["name"] for r in rows]
    for kept in ("Mental Maths", "Reading", "Cursive", "Assembly", "Physics Lab", "Chemistry Lab", "English Grammar",
                 "Science Practical"):
        assert kept in names, (kept, names)
    # Plain short forms still take the AI's (or the school's) name.
    assert {"Mathematics", "Physics", "History", "Library"} <= set(names)
    assert "Maths" not in names and "English" not in names
