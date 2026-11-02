"""
The setup check: problems found before generating, each with what to open.

Every error it reports must be one the solver would fail on too - the
checks are only worth showing if they are certain - so several tests below
also run the solver on the same school and expect it to fail.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.school import (
    ClassGroup, Constraint, ElectiveBlock, ElectiveOption, Period, Room, School, Subject,
    SubjectRequirement, Teacher,
)
from app.models.user import User  # noqa: F401 - registers the users table
from app.services.constraint_ir import Run, Rule, Selector, rule_to_dict
from app.services.setup_check import check_setup
from app.services.solver import generate_school_timetable
from tests.conftest import create_school, signup


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


class S:
    def __init__(self, db, days=2, per_day=4, breaks=()):
        self.db = db
        self.school = School(name="Test School")
        db.add(self.school)
        db.commit()
        for day in range(days):
            for order in range(per_day):
                db.add(Period(school_id=self.school.id, day_of_week=day, order=order,
                              is_break=order in breaks))
        db.commit()
        self.sections, self.subjects, self.teachers = {}, {}, {}

    def section(self, label, students=None):
        grade, name = label.rsplit(" ", 1)
        cg = ClassGroup(school_id=self.school.id, grade=grade, name=name, student_count=students)
        self.db.add(cg)
        self.db.commit()
        self.sections[label] = cg
        return cg

    def subject(self, name, room_type=None, batches=None):
        s = Subject(school_id=self.school.id, name=name, required_room_type=room_type, lab_batch_count=batches)
        self.db.add(s)
        self.db.commit()
        self.subjects[name] = s

    def teacher(self, name, *subjects, cap=None, unavailable=None):
        t = Teacher(school_id=self.school.id, name=name,
                    qualified_subject_ids=[self.subjects[n].id for n in subjects],
                    qualified_grades=[], max_periods_per_week=cap, unavailable_period_ids=unavailable or [])
        self.db.add(t)
        self.db.commit()
        self.teachers[name] = t
        return t

    def lessons(self, section, subject, ppw):
        self.db.add(SubjectRequirement(class_group_id=self.sections[section].id,
                                       subject_id=self.subjects[subject].id, periods_per_week=ppw))
        self.db.commit()

    def block(self, sections, ppw, subjects, name="Block"):
        cgs = [self.sections[x] for x in sections]
        b = ElectiveBlock(school_id=self.school.id, class_group_id=cgs[0].id, name=name,
                          periods_per_week=ppw, linked_sections=cgs[1:],
                          options=[ElectiveOption(subject_id=self.subjects[n].id) for n in subjects])
        self.db.add(b)
        self.db.commit()
        return b

    def check(self):
        return check_setup(self.db, self.school.id)

    def solves(self) -> bool:
        return generate_school_timetable(self.db, self.school.id).status in ("optimal", "feasible")


def kinds(result, severity="errors"):
    return [i["kind"] for i in result[severity]]


def test_a_school_that_fits_has_nothing_to_say(db):
    s = S(db)
    s.section("Grade 9 A")
    s.subject("Maths")
    s.teacher("Asha", "Maths")
    s.lessons("Grade 9 A", "Maths", 4)
    r = s.check()
    assert r == {"ok": True, "errors": [], "warnings": []}
    assert s.solves()


def test_a_section_asking_for_more_periods_than_its_week_has(db):
    s = S(db)  # 8 periods a week
    cg = s.section("Grade 9 A")
    s.subject("Maths")
    s.subject("English")
    s.teacher("Asha", "Maths")
    s.teacher("Ben", "English")
    s.lessons("Grade 9 A", "Maths", 5)
    s.lessons("Grade 9 A", "English", 4)
    r = s.check()
    assert kinds(r) == ["section_overfull"]
    issue = r["errors"][0]
    assert "needs 9 periods a week but its week has only 8" in issue["message"]
    assert issue["fix"] == {"type": "section", "id": cg.id, "label": "Open Grade 9 A"}
    assert not s.solves()


def test_a_teacher_who_alone_must_take_more_than_their_limit(db):
    s = S(db)
    s.section("Grade 9 A")
    s.section("Grade 9 B")
    s.subject("Maths")
    t = s.teacher("Asha", "Maths", cap=6)
    s.lessons("Grade 9 A", "Maths", 4)
    s.lessons("Grade 9 B", "Maths", 4)
    r = s.check()
    assert kinds(r) == ["teacher_overloaded"]
    issue = r["errors"][0]
    assert "Asha is the only teacher for" in issue["message"] and "8 periods a week" in issue["message"]
    assert "limited to 6" in issue["message"]
    assert issue["fix"]["type"] == "teacher" and issue["fix"]["id"] == t.id
    assert not s.solves()


def test_a_teacher_whose_free_periods_are_too_few(db):
    s = S(db)
    s.section("Grade 9 A")
    s.subject("Maths")
    periods = db.query(Period).all()
    s.teacher("Asha", "Maths", unavailable=[p.id for p in periods[:5]])
    s.lessons("Grade 9 A", "Maths", 4)
    r = s.check()
    assert kinds(r) == ["teacher_overloaded"] and "free for only 3 periods" in r["errors"][0]["message"]
    assert not s.solves()


def test_sections_that_cant_be_shared_out_between_teachers(db):
    # Two teachers, each limited to 5; three sections of 3 periods. Neither is
    # anyone's only option, but no split works: whole sections, one teacher each.
    s = S(db)
    s.subject("Maths")
    for x in "ABC":
        s.section(f"Grade 9 {x}")
        s.lessons(f"Grade 9 {x}", "Maths", 3)
    s.teacher("Asha", "Maths", cap=4)
    s.teacher("Ben", "Maths", cap=4)
    r = s.check()
    assert kinds(r) == ["staffing"] and r["errors"][0]["fix"]["type"] == "teachers"
    assert not s.solves()


def test_a_shared_block_needing_one_teacher_in_two_groups(db):
    s = S(db)
    s.section("Grade 11 A")
    s.section("Grade 11 B")
    s.subject("Maths")
    s.subject("Physics")
    s.teacher("Aman", "Maths", "Physics")
    b = s.block(["Grade 11 A", "Grade 11 B"], 2, ["Maths", "Physics"], name="Maths/Physics")
    r = s.check()
    assert kinds(r) == ["block_teacher_clash"]
    issue = r["errors"][0]
    assert "can only be taught by Aman" in issue["message"]
    assert issue["fix"] == {"type": "block", "id": b.id, "class_group_id": s.sections["Grade 11 A"].id,
                            "label": "Open Maths/Physics"}
    assert not s.solves()


def test_a_split_lab_with_fewer_teachers_than_batches(db):
    s = S(db)
    s.section("Grade 11 A")
    s.subject("CS Lab", batches=3)
    s.teacher("Asha", "CS Lab")
    s.teacher("Ben", "CS Lab")
    s.lessons("Grade 11 A", "CS Lab", 2)
    r = s.check()
    assert kinds(r) == ["lab_batches"] and "3 batches" in r["errors"][0]["message"]
    assert not s.solves()


def _double_rule(db, s, subject, k=2, scope=None):
    rule = Rule(form=Run(scope=("class_group", "day"), selector=Selector(subjects=(subject,), class_groups=scope),
                         block_size=k), description=f"{subject} in doubles")
    c = Constraint(school_id=s.school.id, type="ir", parameters=rule_to_dict(rule), description=f"{subject} in doubles")
    db.add(c)
    db.commit()
    return c


def test_double_periods_the_day_cant_fit(db):
    s = S(db, per_day=3, breaks=(1,))  # P1, break, P3: never two in a row
    s.section("Grade 11 A")
    s.subject("Chem Lab")
    s.teacher("Asha", "Chem Lab")
    s.lessons("Grade 11 A", "Chem Lab", 2)
    c = _double_rule(db, s, "Chem Lab")
    r = s.check()
    assert kinds(r) == ["double_periods"]
    assert "never has 2 lesson periods in a row" in r["errors"][0]["message"]
    assert r["errors"][0]["fix"] == {"type": "rule", "id": c.id, "label": "Open the rule"}
    assert not s.solves()


def test_too_few_periods_for_a_double(db):
    s = S(db)
    s.section("Grade 11 A")
    s.subject("Chem Lab")
    s.teacher("Asha", "Chem Lab")
    s.lessons("Grade 11 A", "Chem Lab", 1)
    _double_rule(db, s, "Chem Lab")
    r = s.check()
    assert kinds(r) == ["double_periods"] and "too few for a block of 2" in r["errors"][0]["message"]
    assert not s.solves()


def test_an_odd_number_of_periods_in_doubles_is_fine(db):
    # The rule forbids a lesson on its own; three in a row is allowed.
    s = S(db)
    s.section("Grade 11 A")
    s.subject("Chem Lab")
    s.teacher("Asha", "Chem Lab")
    s.lessons("Grade 11 A", "Chem Lab", 3)
    _double_rule(db, s, "Chem Lab")
    assert s.check()["ok"] and s.solves()


def test_rooms_short_of_a_type_are_warnings_not_errors(db):
    s = S(db)
    s.section("Grade 11 A", students=40)
    s.subject("Physics Lab", room_type="lab", batches=2)
    s.subject("Chem Lab", room_type="chem")
    s.teacher("Asha", "Physics Lab")
    s.teacher("Ben", "Physics Lab")
    s.teacher("Cara", "Chem Lab")
    s.lessons("Grade 11 A", "Physics Lab", 2)
    s.lessons("Grade 11 A", "Chem Lab", 1)
    db.add(Room(school_id=s.school.id, name="Lab 1", room_type="lab", capacity=30))
    db.commit()
    r = s.check()
    assert r["ok"] is True
    warned = kinds(r, "warnings")
    assert "rooms_at_once" in warned and "no_room_type" in warned
    assert all(i["fix"]["type"] == "rooms" for i in r["warnings"])
    assert s.solves()


def test_a_subject_nobody_can_teach_is_a_warning(db):
    s = S(db)
    s.section("Grade 9 A")
    s.subject("Music")
    s.lessons("Grade 9 A", "Music", 1)
    r = s.check()
    assert r["ok"] and kinds(r, "warnings") == ["no_teacher"]


def test_frozen_sections_are_left_out_of_the_section_check(db):
    s = S(db)
    cg = s.section("Grade 9 A")
    s.subject("Maths")
    s.teacher("Asha", "Maths")
    s.lessons("Grade 9 A", "Maths", 12)
    cg.frozen = True
    db.commit()
    assert "section_overfull" not in kinds(s.check())


def test_the_endpoint(client):
    _, headers = signup(client)
    sid = create_school(client, headers)["id"]
    r = client.get(f"/api/schools/{sid}/setup-check", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["errors"][0]["kind"] == "no_periods"
    other_headers = signup(client, email="other@example.com")[1]
    assert client.get(f"/api/schools/{sid}/setup-check", headers=other_headers).status_code in (403, 404)
