"""
Importing which grades each teacher may teach.

A grades column on the teachers sheet fills Teacher.qualified_grades, which
the solver compares against each section's grade exactly - so whatever the
sheet says has to land as the school's own grade labels. An empty cell means
every grade.
"""
from app.models.school import ClassGroup, School, Teacher
from app.services.bulk_import import TEMPLATES, import_teachers, parse_rows


def _school(db, grades=("Grade 6", "Grade 7", "Grade 8", "Grade 11", "Pre-KG")):
    school = School(name="Test School")
    db.add(school)
    db.commit()
    for g in grades:
        db.add(ClassGroup(school_id=school.id, grade=g, name="A"))
    db.commit()
    return school


def _grades_of(db, school, name):
    db.expire_all()
    return db.query(Teacher).filter(Teacher.school_id == school.id, Teacher.name == name).one().qualified_grades


def _import(db, school, **row):
    return import_teachers(db, school.id, [{"name": "Mrs. Rao", **row}])


def test_grades_are_stored_as_the_schools_own_labels(orm_db):
    school = _school(orm_db)
    result = _import(orm_db, school, qualified_grades="Grade 6; Grade 7")
    assert result.errors == []
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Grade 6", "Grade 7"]


def test_an_empty_cell_means_every_grade(orm_db):
    school = _school(orm_db)
    _import(orm_db, school, qualified_grades="")
    assert _grades_of(orm_db, school, "Mrs. Rao") == []


def test_loose_spellings_match(orm_db):
    """"6", "Class 7", "8th" and "Std. 11" are how people write grades."""
    school = _school(orm_db)
    result = _import(orm_db, school, qualified_grades="6, Class 7, 8th, Std. 11")
    assert result.errors == []
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Grade 6", "Grade 7", "Grade 8", "Grade 11"]


def test_roman_numerals_match(orm_db):
    school = _school(orm_db)
    _import(orm_db, school, qualified_grades="Class VI; XI")
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Grade 6", "Grade 11"]


def test_a_range_covers_every_grade_in_it(orm_db):
    school = _school(orm_db)
    _import(orm_db, school, qualified_grades="6-8")
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Grade 6", "Grade 7", "Grade 8"]


def test_a_range_can_be_written_in_words(orm_db):
    school = _school(orm_db)
    _import(orm_db, school, qualified_grades="Grade 7 to Grade 11")
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Grade 7", "Grade 8", "Grade 11"]


def test_a_grade_with_a_hyphen_is_not_read_as_a_range(orm_db):
    school = _school(orm_db)
    result = _import(orm_db, school, qualified_grades="Pre-KG")
    assert result.errors == []
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Pre-KG"]


def test_an_unknown_grade_is_reported_and_the_rest_applied(orm_db):
    school = _school(orm_db)
    result = _import(orm_db, school, qualified_grades="Grade 6; Grade 13")
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Grade 6"]
    assert len(result.errors) == 1
    assert "Grade 13" in result.errors[0]
    assert "Grade 6, Grade 7" in result.errors[0]  # says what the grades are


def test_a_typo_does_not_widen_an_existing_teacher_to_every_grade(orm_db):
    """An empty list means every grade, so "nothing matched" must not become one."""
    school = _school(orm_db)
    _import(orm_db, school, qualified_grades="Grade 11")
    result = _import(orm_db, school, qualified_grades="Grade Eleven")
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Grade 11"]
    assert "left unchanged" in result.errors[0]


def test_a_school_without_graded_sections_is_told_to_add_them(orm_db):
    school = _school(orm_db, grades=())
    result = _import(orm_db, school, qualified_grades="Grade 6")
    assert "add them first" in result.errors[0]


def test_reimporting_updates_grades(orm_db):
    school = _school(orm_db)
    _import(orm_db, school, qualified_grades="Grade 6")
    result = _import(orm_db, school, qualified_grades="Grade 7; Grade 8")
    assert result.updated == 1
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Grade 7", "Grade 8"]


def test_reimporting_with_an_empty_cell_opens_every_grade(orm_db):
    school = _school(orm_db)
    _import(orm_db, school, qualified_grades="Grade 6")
    _import(orm_db, school, qualified_grades="")
    assert _grades_of(orm_db, school, "Mrs. Rao") == []


def test_a_sheet_without_a_grades_column_leaves_grades_alone(orm_db):
    """A roster re-uploaded without the column - or the AI setup extraction,
    which never sends one - must not wipe what was set."""
    school = _school(orm_db)
    _import(orm_db, school, qualified_grades="Grade 6")
    _import(orm_db, school, max_periods_per_week="20")
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Grade 6"]


def test_the_column_can_be_headed_grades(orm_db):
    school = _school(orm_db)
    rows = parse_rows("teachers.csv", b"Name,Grades\nMrs. Rao,6;7\n")
    import_teachers(orm_db, school.id, rows)
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Grade 6", "Grade 7"]


def test_a_whole_number_cell_from_excel_matches(orm_db):
    school = _school(orm_db)
    _import(orm_db, school, qualified_grades="8.0")
    assert _grades_of(orm_db, school, "Mrs. Rao") == ["Grade 8"]


def test_the_template_has_the_column(orm_db):
    school = _school(orm_db)
    rows = parse_rows("teachers.csv", TEMPLATES["teachers"].encode())
    assert "qualified_grades" in rows[0]
    import_teachers(orm_db, school.id, rows)
    assert _grades_of(orm_db, school, "Priya Sharma") == ["Grade 6", "Grade 7"]
    assert _grades_of(orm_db, school, "Rahul Mehta") == []
