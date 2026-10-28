"""
Tests for app/services/bulk_import.py — the two design choices that carry
the whole feature (see its module docstring): best-effort per-row error
handling (one bad row doesn't block the rest of the file) and upsert-by-
name (re-uploading after fixing a typo updates rather than duplicates).

Exercises the service functions directly rather than through the
multipart-upload HTTP endpoint — the parsing/import logic is what this
feature is actually about; the endpoint itself is a thin wrapper (see
app/routers/subjects.py's bulk_import_subjects) that just calls
parse_rows() then the matching import_* function.
"""
from app.models.school import ClassGroup, School, Subject, Teacher
from app.services.bulk_import import import_class_groups, import_subjects, import_teachers, parse_rows


def _make_school(db):
    school = School(name="Test School")
    db.add(school)
    db.commit()
    db.refresh(school)
    return school


def test_parse_rows_csv_normalizes_headers_and_drops_blank_rows():
    csv_bytes = b"Name,Required_Room_Type\nMath,\n\nPhysics,lab\n"
    rows = parse_rows("subjects.csv", csv_bytes)
    assert rows == [
        {"name": "Math", "required_room_type": ""},
        {"name": "Physics", "required_room_type": "lab"},
    ]


def test_parse_rows_rejects_unknown_extension():
    try:
        parse_rows("subjects.txt", b"whatever")
        assert False, "expected a ValueError for an unsupported file type"
    except ValueError:
        pass


def test_import_subjects_partial_failure_does_not_block_good_rows(orm_db):
    db = orm_db
    school = _make_school(db)
    rows = [
        {"name": "Math", "required_room_type": ""},
        {"name": "", "required_room_type": "lab"},  # missing required name — should be skipped, not fatal
        {"name": "Chemistry", "required_room_type": "lab"},
    ]

    result = import_subjects(db, school.id, rows)

    assert result.created == 2
    assert result.updated == 0
    assert len(result.errors) == 1
    assert "missing required 'name'" in result.errors[0]

    names = {s.name for s in db.query(Subject).filter(Subject.school_id == school.id).all()}
    assert names == {"Math", "Chemistry"}


def test_import_subjects_upserts_by_name_case_insensitively(orm_db):
    db = orm_db
    school = _make_school(db)

    import_subjects(db, school.id, [{"name": "Math", "required_room_type": ""}])
    result = import_subjects(db, school.id, [{"name": "MATH", "required_room_type": "lab"}])

    assert result.created == 0
    assert result.updated == 1
    subjects = db.query(Subject).filter(Subject.school_id == school.id).all()
    assert len(subjects) == 1  # re-uploading updated the existing row, didn't create a duplicate
    assert subjects[0].required_room_type == "lab"


def test_import_teachers_resolves_qualified_subjects_and_reports_unresolved(orm_db):
    db = orm_db
    school = _make_school(db)
    math = Subject(school_id=school.id, name="Math")
    db.add(math)
    db.commit()
    db.refresh(math)

    rows = [
        {
            "name": "Mr. Rao",
            "email": "rao@school.edu",
            "max_periods_per_week": "20",
            "qualified_subjects": "Math; Physics",  # Physics doesn't exist yet
        }
    ]
    result = import_teachers(db, school.id, rows)

    assert result.created == 1
    assert len(result.errors) == 1
    assert "Physics" in result.errors[0]

    teacher = db.query(Teacher).filter(Teacher.school_id == school.id).first()
    assert teacher.name == "Mr. Rao"
    assert teacher.max_periods_per_week == 20
    assert teacher.qualified_subject_ids == [math.id]  # Math resolved, Physics silently skipped (not blocking)


def test_import_class_groups_upserts_by_grade_and_name(orm_db):
    db = orm_db
    school = _make_school(db)

    result = import_class_groups(
        db, school.id, [{"name": "A", "grade": "Grade 8", "student_count": "30"}]
    )
    assert result.created == 1

    # Same (grade, name) pair, different student_count — should update, not duplicate.
    result = import_class_groups(
        db, school.id, [{"name": "A", "grade": "Grade 8", "student_count": "35"}]
    )
    assert result.created == 0
    assert result.updated == 1

    groups = db.query(ClassGroup).filter(ClassGroup.school_id == school.id).all()
    assert len(groups) == 1
    assert groups[0].student_count == 35


def test_reimporting_a_teacher_adds_subjects_and_keeps_details(orm_db):
    """A second sheet (say Classes 9-12) adds to a teacher's subjects; it
    never drops the ones from an earlier sheet, and empty cells change nothing."""
    db = orm_db
    school = _make_school(db)
    maths = Subject(school_id=school.id, name="Maths")
    physics = Subject(school_id=school.id, name="Physics")
    db.add_all([maths, physics])
    db.commit()

    import_teachers(db, school.id, [{"name": "Aman", "email": "aman@school.edu",
                                     "max_periods_per_week": "30", "qualified_subjects": "Physics"}])
    result = import_teachers(db, school.id, [{"name": "Aman", "email": "", "max_periods_per_week": "",
                                              "qualified_subjects": "Maths; Physics"}])
    assert result.updated == 1
    aman = db.query(Teacher).filter(Teacher.school_id == school.id).one()
    assert aman.qualified_subject_ids == [physics.id, maths.id]
    assert aman.email == "aman@school.edu"
    assert aman.max_periods_per_week == 30
