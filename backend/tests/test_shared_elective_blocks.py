"""
Elective blocks shared between sections.

Grade 9 A and B both break up for the Maths / History period; everyone who
chose Maths, from either section, goes to one Maths class with one teacher.
Each option of a block is a teaching group drawn from some or all of the
block's sections, so one structure has to cover every arrangement a school
uses. Each test below is one of them, set up so it only passes if the groups
are really modelled as one lesson:

  - two sections pooling every option
  - a combined class with a single subject (PE for 9 A and 9 B together)
  - a subject split into two groups taught at once
  - a subject one section takes on its own while the others pool
  - sections of different grades sharing a period
  - and the things around it: teacher qualification across grades, a teacher
    counted once, rooms, locks, freezing, manual moves, exports.
"""
from collections import defaultdict

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.school import (
    ClassGroup, ElectiveBlock, ElectiveOption, Period, Room, School, Subject,
    SubjectRequirement, Teacher,
)
from app.models.user import User  # noqa: F401 - registers the users table
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
    def __init__(self, db, days=1, per_day=4):
        self.db = db
        self.school = School(name="Test School")
        db.add(self.school)
        db.commit()
        self.periods = []
        for day in range(days):
            for order in range(per_day):
                p = Period(school_id=self.school.id, day_of_week=day, order=order)
                db.add(p)
                self.periods.append(p)
        db.commit()
        self.sections, self.subjects, self.teachers = {}, {}, {}

    def section(self, grade, name, students=None):
        cg = ClassGroup(school_id=self.school.id, grade=grade, name=name, student_count=students)
        self.db.add(cg)
        self.db.commit()
        self.sections[f"{grade} {name}"] = cg
        return cg

    def subject(self, *names):
        for n in names:
            s = Subject(school_id=self.school.id, name=n)
            self.db.add(s)
            self.db.commit()
            self.subjects[n] = s

    def teacher(self, name, *subjects, grades=None, cap=None):
        t = Teacher(
            school_id=self.school.id, name=name,
            qualified_subject_ids=[self.subjects[n].id for n in subjects],
            qualified_grades=grades or [], max_periods_per_week=cap,
        )
        self.db.add(t)
        self.db.commit()
        self.teachers[name] = t
        return t

    def common(self, section, subject, ppw):
        self.db.add(SubjectRequirement(class_group_id=self.sections[section].id,
                                       subject_id=self.subjects[subject].id, periods_per_week=ppw))
        self.db.commit()

    def block(self, sections, ppw, groups, name="Block"):
        """groups: (subject, [sections] or None, label, teacher name or None)."""
        cgs = [self.sections[x] for x in sections]
        b = ElectiveBlock(
            school_id=self.school.id, class_group_id=cgs[0].id, name=name, periods_per_week=ppw,
            linked_sections=cgs[1:],
            options=[
                ElectiveOption(
                    subject_id=self.subjects[subj].id,
                    class_group_ids=[self.sections[x].id for x in secs] if secs else None,
                    label=label,
                    preferred_teacher_id=self.teachers[t].id if t else None,
                )
                for subj, secs, label, t in groups
            ],
        )
        self.db.add(b)
        self.db.commit()
        return b

    def solve(self):
        r = generate_school_timetable(self.db, self.school.id)
        assert r.status in ("optimal", "feasible"), r.errors
        return r


def _rows(result, **match):
    return [a for a in result.assignments if all(a.get(k) == v for k, v in match.items())]


def _grade9(db, per_day=4):
    s = S(db, per_day=per_day)
    s.section("Grade 9", "A")
    s.section("Grade 9", "B")
    s.subject("Maths", "History", "English", "PE", "CS", "French")
    return s


# ---------------------------------------------------------------------------
# Every arrangement
# ---------------------------------------------------------------------------


def test_two_sections_pool_their_students_into_one_class_per_subject(db):
    s = _grade9(db)
    s.teacher("Mr. Maths", "Maths")
    s.teacher("Ms. History", "History")
    s.teacher("Mr. English A", "English")
    s.teacher("Ms. English B", "English")
    s.common("Grade 9 A", "English", 2)
    s.common("Grade 9 B", "English", 2)
    s.block(["Grade 9 A", "Grade 9 B"], 2, [("Maths", None, None, None), ("History", None, None, None)])
    r = s.solve()

    a, b = s.sections["Grade 9 A"].id, s.sections["Grade 9 B"].id
    maths = s.subjects["Maths"].id
    maths_a = {x["period_id"] for x in _rows(r, class_group_id=a, subject_id=maths)}
    maths_b = {x["period_id"] for x in _rows(r, class_group_id=b, subject_id=maths)}
    assert len(maths_a) == 2 and maths_a == maths_b, "both sections' Maths students meet together"
    teachers = {x["teacher_id"] for x in _rows(r, subject_id=maths)}
    assert teachers == {s.teachers["Mr. Maths"].id}, "one Maths class, one teacher"
    # Neither section has anything else in those periods.
    for cg in (a, b):
        others = [x for x in _rows(r, class_group_id=cg) if x["period_id"] in maths_a and x.get("elective_block_id") is None]
        assert not others


def test_a_pooled_class_counts_once_towards_its_teachers_week(db):
    """With Maths counted per section the teacher would need 4 periods for 2,
    over a limit of 2 - so this only solves if the group is one lesson."""
    s = _grade9(db)
    s.teacher("Mr. Maths", "Maths", cap=2)
    s.teacher("Ms. History", "History", cap=2)
    s.block(["Grade 9 A", "Grade 9 B"], 2, [("Maths", None, None, None), ("History", None, None, None)])
    r = s.solve()
    assert len({x["period_id"] for x in _rows(r, teacher_id=s.teachers["Mr. Maths"].id)}) == 2


def test_a_combined_class_with_one_subject(db):
    s = _grade9(db)
    s.teacher("Coach", "PE", cap=1)
    s.block(["Grade 9 A", "Grade 9 B"], 1, [("PE", None, None, None)], name="Games")
    r = s.solve()
    rows = _rows(r, subject_id=s.subjects["PE"].id)
    assert {x["class_group_id"] for x in rows} == {s.sections["Grade 9 A"].id, s.sections["Grade 9 B"].id}
    assert len({x["period_id"] for x in rows}) == 1


def test_a_big_subject_split_into_two_groups_taught_at_once(db):
    s = _grade9(db)
    s.teacher("Mr. Maths", "Maths")
    s.teacher("Mrs. Maths", "Maths")
    s.teacher("Ms. History", "History")
    s.block(["Grade 9 A", "Grade 9 B"], 2, [
        ("Maths", None, "Group 1", None), ("Maths", None, "Group 2", None), ("History", None, None, None),
    ])
    r = s.solve()
    for period, rows in defaultdict(list, {p: _rows(r, period_id=p) for p in {x["period_id"] for x in r.assignments}}).items():
        maths = [x for x in rows if x["subject_id"] == s.subjects["Maths"].id]
        if maths:
            assert len({x["teacher_id"] for x in maths}) == 2, "two Maths groups, two teachers, same time"
            assert len({x["elective_option_id"] for x in maths}) == 2


def test_a_subject_one_section_takes_on_its_own_while_others_pool(db):
    s = _grade9(db)
    s.teacher("Ms. French", "French")
    s.teacher("Mr. CS A", "CS")
    s.teacher("Mrs. CS B", "CS")
    s.block(["Grade 9 A", "Grade 9 B"], 1, [
        ("French", None, None, None),
        ("CS", ["Grade 9 A"], "9 A", "Mr. CS A"),
        ("CS", ["Grade 9 B"], "9 B", "Mrs. CS B"),
    ])
    r = s.solve()
    a, b = s.sections["Grade 9 A"].id, s.sections["Grade 9 B"].id
    cs = s.subjects["CS"].id
    assert [x["teacher_id"] for x in _rows(r, class_group_id=a, subject_id=cs)] == [s.teachers["Mr. CS A"].id]
    assert [x["teacher_id"] for x in _rows(r, class_group_id=b, subject_id=cs)] == [s.teachers["Mrs. CS B"].id]
    french = _rows(r, subject_id=s.subjects["French"].id)
    assert {x["class_group_id"] for x in french} == {a, b} and len({x["teacher_id"] for x in french}) == 1


def test_sections_of_different_grades_can_share_a_period(db):
    s = S(db)
    s.section("Grade 11", "A")
    s.section("Grade 12", "A")
    s.subject("Hindi", "French", "English")
    s.teacher("Mrs. Hindi", "Hindi")
    s.teacher("M. French", "French")
    s.teacher("Mr. English", "English")
    s.common("Grade 11 A", "English", 1)
    s.common("Grade 12 A", "English", 1)
    s.block(["Grade 11 A", "Grade 12 A"], 2, [("Hindi", None, None, None), ("French", None, None, None)],
            name="Second language")
    r = s.solve()
    p11 = {x["period_id"] for x in _rows(r, class_group_id=s.sections["Grade 11 A"].id, subject_id=s.subjects["Hindi"].id)}
    p12 = {x["period_id"] for x in _rows(r, class_group_id=s.sections["Grade 12 A"].id, subject_id=s.subjects["Hindi"].id)}
    assert len(p11) == 2 and p11 == p12


def test_a_pooled_group_needs_a_teacher_qualified_for_every_section_in_it(db):
    s = S(db)
    s.section("Grade 11", "A")
    s.section("Grade 12", "A")
    s.subject("Hindi", "French")
    s.teacher("Junior Hindi", "Hindi", grades=["Grade 11"])
    s.teacher("Senior Hindi", "Hindi", grades=["Grade 11", "Grade 12"])
    s.teacher("M. French", "French")
    s.block(["Grade 11 A", "Grade 12 A"], 2, [("Hindi", None, None, None), ("French", None, None, None)])
    r = s.solve()
    assert {x["teacher_id"] for x in _rows(r, subject_id=s.subjects["Hindi"].id)} == {s.teachers["Senior Hindi"].id}


def test_a_section_in_a_shared_block_is_free_for_nothing_else_then(db):
    """9 B joins a block but also has its own subjects: they must avoid the block."""
    s = _grade9(db, per_day=3)
    s.teacher("Mr. Maths", "Maths")
    s.teacher("Ms. History", "History")
    s.teacher("Mr. English", "English")
    s.common("Grade 9 B", "English", 1)
    s.block(["Grade 9 A", "Grade 9 B"], 2, [("Maths", None, None, None), ("History", None, None, None)])
    r = s.solve()
    b = s.sections["Grade 9 B"].id
    block_periods = {x["period_id"] for x in _rows(r, class_group_id=b) if x.get("elective_block_id")}
    english = {x["period_id"] for x in _rows(r, class_group_id=b, subject_id=s.subjects["English"].id)}
    assert len(block_periods) == 2 and not (block_periods & english)


def test_one_teacher_for_two_groups_at_once_is_explained(db):
    s = _grade9(db)
    s.teacher("Only teacher", "Maths", "History")
    s.block(["Grade 9 A", "Grade 9 B"], 1, [("Maths", None, None, None), ("History", None, None, None)])
    r = generate_school_timetable(db, s.school.id)
    assert r.status == "infeasible"
    assert any("Only teacher" in e for e in r.errors), r.errors


def test_a_pooled_group_gets_one_room_for_everyone(db):
    s = _grade9(db)
    s.sections["Grade 9 A"].student_count = 30
    s.sections["Grade 9 B"].student_count = 35
    db.add_all([Room(school_id=s.school.id, name="Small", capacity=32),
                Room(school_id=s.school.id, name="Big", capacity=40),
                Room(school_id=s.school.id, name="Bigger", capacity=40)])
    db.commit()
    s.teacher("Mr. Maths", "Maths")
    s.teacher("Ms. History", "History")
    s.block(["Grade 9 A", "Grade 9 B"], 1, [("Maths", None, None, None), ("History", None, None, None)])
    r = s.solve()
    small = db.query(Room).filter(Room.name == "Small").one().id
    for subject in ("Maths", "History"):
        rooms = {x["room_id"] for x in _rows(r, subject_id=s.subjects[subject].id)}
        assert len(rooms) == 1 and None not in rooms and small not in rooms, (subject, rooms)


# ---------------------------------------------------------------------------
# Through the API: setting it up, generating, editing, exporting
# ---------------------------------------------------------------------------


@pytest.fixture
def api(client):
    _, headers = signup(client)
    sid = create_school(client, headers)["id"]

    def post(url, body):
        r = client.post(url, json=body, headers=headers)
        assert r.status_code in (200, 201), r.text
        return r.json()

    subjects = {n: post("/api/subjects", {"school_id": sid, "name": n})["id"]
                for n in ("Maths", "History", "English", "CS")}
    a = post("/api/class-groups", {"school_id": sid, "grade": "Grade 9", "name": "A"})["id"]
    b = post("/api/class-groups", {"school_id": sid, "grade": "Grade 9", "name": "B"})["id"]
    c = post("/api/class-groups", {"school_id": sid, "grade": "Grade 9", "name": "C"})["id"]
    teachers = {
        n: post("/api/teachers", {"school_id": sid, "name": n, "qualified_subject_ids": [subjects[subj]]})["id"]
        for n, subj in (("Mr. Maths", "Maths"), ("Mrs. Maths", "Maths"), ("Ms. History", "History"),
                        ("Mr. English", "English"), ("Mr. CS", "CS"))
    }
    for day in range(2):
        for order in range(3):
            post("/api/periods", {"school_id": sid, "day_of_week": day, "order": order, "label": f"P{order + 1}"})
    return {"client": client, "headers": headers, "sid": sid, "s": subjects, "a": a, "b": b, "c": c, "t": teachers}


def _create(api, options, sections=None, ppw=2, home=None, name="Block 1"):
    return api["client"].post("/api/elective-blocks", json={
        "school_id": api["sid"], "class_group_id": home or api["a"], "name": name, "periods_per_week": ppw,
        "section_ids": sections, "options": options,
    }, headers=api["headers"])


def test_a_shared_block_is_saved_with_its_sections_and_groups(api):
    r = _create(api, [{"subject_id": api["s"]["Maths"]}, {"subject_id": api["s"]["History"]}],
                sections=[api["a"], api["b"]])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["section_ids"] == [api["a"], api["b"]]
    assert all(o["class_group_ids"] is None for o in body["options"])


def test_a_section_with_nowhere_to_go_is_refused(api):
    r = _create(api, [
        {"subject_id": api["s"]["Maths"], "class_group_ids": [api["a"]]},
        {"subject_id": api["s"]["History"], "class_group_ids": [api["a"]]},
    ], sections=[api["a"], api["b"]])
    assert r.status_code == 400 and "9 B" in r.json()["detail"]


def test_a_subject_twice_for_one_section_needs_named_groups(api):
    maths = api["s"]["Maths"]
    r = _create(api, [{"subject_id": maths}, {"subject_id": maths}, {"subject_id": api["s"]["History"]}],
                sections=[api["a"], api["b"]])
    assert r.status_code == 400 and "Group 1" in r.json()["detail"]
    r = _create(api, [{"subject_id": maths, "label": "Group 1"}, {"subject_id": maths, "label": "Group 2"},
                      {"subject_id": api["s"]["History"]}], sections=[api["a"], api["b"]])
    assert r.status_code == 201, r.text


def test_one_subject_per_section_alone_is_not_a_duplicate(api):
    cs = api["s"]["CS"]
    r = _create(api, [
        {"subject_id": api["s"]["Maths"]},
        {"subject_id": cs, "class_group_ids": [api["a"]]},
        {"subject_id": cs, "class_group_ids": [api["b"]]},
    ], sections=[api["a"], api["b"]])
    assert r.status_code == 201, r.text


def test_a_common_subject_of_a_joined_section_cannot_be_an_option(api):
    c = api["client"]
    c.post(f"/api/class-groups/{api['b']}/requirements",
           json={"class_group_id": api["b"], "subject_id": api["s"]["Maths"], "periods_per_week": 2}, headers=api["headers"])
    r = _create(api, [{"subject_id": api["s"]["Maths"]}, {"subject_id": api["s"]["History"]}],
                sections=[api["a"], api["b"]])
    assert r.status_code == 400 and "common" in r.json()["detail"]


def test_a_joined_section_cannot_then_take_the_subject_as_common(api):
    assert _create(api, [{"subject_id": api["s"]["Maths"]}, {"subject_id": api["s"]["History"]}],
                   sections=[api["a"], api["b"]]).status_code == 201
    r = api["client"].post(f"/api/class-groups/{api['b']}/requirements",
                           json={"class_group_id": api["b"], "subject_id": api["s"]["Maths"], "periods_per_week": 2}, headers=api["headers"])
    assert r.status_code == 400


def test_a_subject_cannot_be_in_two_blocks_a_section_shares(api):
    assert _create(api, [{"subject_id": api["s"]["Maths"]}, {"subject_id": api["s"]["History"]}],
                   sections=[api["a"], api["b"]]).status_code == 201
    r = _create(api, [{"subject_id": api["s"]["Maths"]}, {"subject_id": api["s"]["CS"]}],
                home=api["b"], sections=[api["b"], api["c"]], name="Block 2")
    assert r.status_code == 400 and "already an option" in r.json()["detail"]


def test_one_teacher_on_two_groups_is_refused(api):
    t = api["t"]["Mr. Maths"]
    r = _create(api, [{"subject_id": api["s"]["Maths"], "preferred_teacher_id": t},
                      {"subject_id": api["s"]["History"], "preferred_teacher_id": t}],
                sections=[api["a"], api["b"]])
    assert r.status_code == 400 and "two groups" in r.json()["detail"]


def test_deleting_the_section_a_block_was_made_in_keeps_it_for_the_others(api):
    c = api["client"]
    block = _create(api, [{"subject_id": api["s"]["Maths"]}, {"subject_id": api["s"]["History"]}],
                    sections=[api["a"], api["b"], api["c"]]).json()
    assert c.delete(f"/api/class-groups/{api['a']}", headers=api["headers"]).status_code in (200, 204)
    blocks = c.get(f"/api/elective-blocks?school_id={api['sid']}", headers=api["headers"]).json()
    assert [b["id"] for b in blocks] == [block["id"]]
    assert blocks[0]["section_ids"] == [api["b"], api["c"]]


def _generate(api):
    from app.core.database import SessionLocal
    from app.models.school import Timetable
    from app.routers.timetables import _run_generation_job

    db = SessionLocal()
    try:
        tt = Timetable(school_id=api["sid"], status="generating")
        db.add(tt)
        db.commit()
        tt_id = tt.id
    finally:
        db.close()
    _run_generation_job(tt_id, api["sid"])
    t = api["client"].get(f"/api/timetables/{tt_id}", headers=api["headers"]).json()
    assert t["status"] == "draft", t.get("error_message")
    return t


def test_generated_entries_name_the_other_sections_in_the_lesson(api):
    _create(api, [{"subject_id": api["s"]["Maths"]}, {"subject_id": api["s"]["History"]}],
            sections=[api["a"], api["b"]])
    t = _generate(api)
    maths_a = [e for e in t["entries"] if e["class_group_id"] == api["a"] and e["subject_id"] == api["s"]["Maths"]]
    assert maths_a and all(e["shared_with_ids"] == [api["b"]] for e in maths_a)
    assert all(e["shared_with_names"] == ["Grade 9 B"] for e in maths_a)


def test_moving_a_shared_block_moves_it_for_every_section(api):
    c = api["client"]
    _create(api, [{"subject_id": api["s"]["Maths"]}, {"subject_id": api["s"]["History"]}],
            sections=[api["a"], api["b"]], ppw=1)
    t = _generate(api)
    block_entry = next(e for e in t["entries"] if e["class_group_id"] == api["a"] and e["elective_block_id"])
    periods = sorted({e["period_id"] for e in t["entries"]} | set(
        p["id"] for p in c.get(f"/api/periods?school_id={api['sid']}", headers=api["headers"]).json()
    ))
    to = next(p for p in periods if p != block_entry["period_id"])
    r = c.post(f"/api/timetables/{t['id']}/move-slot", json={
        "class_group_id": api["a"], "from_period_id": block_entry["period_id"], "to_period_id": to,
    }, headers=api["headers"])
    assert r.status_code == 200, r.text
    t2 = c.get(f"/api/timetables/{t['id']}", headers=api["headers"]).json()
    for cg in (api["a"], api["b"]):
        assert {e["period_id"] for e in t2["entries"] if e["class_group_id"] == cg and e["elective_block_id"]} == {to}


def test_changing_a_pooled_groups_teacher_changes_it_in_every_section(api):
    c = api["client"]
    _create(api, [{"subject_id": api["s"]["Maths"], "preferred_teacher_id": api["t"]["Mr. Maths"]},
                  {"subject_id": api["s"]["History"]}], sections=[api["a"], api["b"]], ppw=1)
    t = _generate(api)
    entry = next(e for e in t["entries"] if e["class_group_id"] == api["a"] and e["subject_id"] == api["s"]["Maths"])
    r = c.patch(f"/api/timetables/entries/{entry['id']}", json={"teacher_id": api["t"]["Mrs. Maths"]},
                headers=api["headers"])
    assert r.status_code == 200, r.text
    t2 = c.get(f"/api/timetables/{t['id']}", headers=api["headers"]).json()
    maths = [e for e in t2["entries"] if e["subject_id"] == api["s"]["Maths"]]
    assert {e["teacher_id"] for e in maths} == {api["t"]["Mrs. Maths"]} and len(maths) == 2


def test_a_lock_on_a_shared_block_survives_regenerating(api):
    c = api["client"]
    _create(api, [{"subject_id": api["s"]["Maths"]}, {"subject_id": api["s"]["History"]}],
            sections=[api["a"], api["b"]], ppw=1)
    t = _generate(api)
    entry = next(e for e in t["entries"] if e["class_group_id"] == api["b"] and e["elective_block_id"])
    r = c.post(f"/api/timetables/{t['id']}/lock-slot", json={
        "class_group_id": api["b"], "period_id": entry["period_id"], "locked": True,
    }, headers=api["headers"])
    assert r.status_code == 200, r.text
    t2 = _generate(api)
    for cg in (api["a"], api["b"]):
        rows = [e for e in t2["entries"] if e["class_group_id"] == cg and e["elective_block_id"]]
        assert {e["period_id"] for e in rows} == {entry["period_id"]} and all(e["locked"] for e in rows)


def test_freezing_one_section_keeps_the_shared_block_for_the_other(api):
    c = api["client"]
    _create(api, [{"subject_id": api["s"]["Maths"]}, {"subject_id": api["s"]["History"]}],
            sections=[api["a"], api["b"]], ppw=1)
    c.post(f"/api/class-groups/{api['b']}/requirements",
           json={"class_group_id": api["b"], "subject_id": api["s"]["English"], "periods_per_week": 2}, headers=api["headers"])
    t = _generate(api)
    slot = next(e["period_id"] for e in t["entries"] if e["class_group_id"] == api["a"] and e["elective_block_id"])
    r = c.post(f"/api/class-groups/freeze", json={"school_id": api["sid"], "class_group_ids": [api["a"]], "frozen": True},
               headers=api["headers"])
    assert r.status_code == 200, r.text
    t2 = _generate(api)
    for cg in (api["a"], api["b"]):
        rows = [e for e in t2["entries"] if e["class_group_id"] == cg and e["elective_block_id"]]
        assert {e["period_id"] for e in rows} == {slot}, cg
    english = [e for e in t2["entries"] if e["class_group_id"] == api["b"] and e["subject_id"] == api["s"]["English"]]
    assert len(english) == 2 and slot not in {e["period_id"] for e in english}


def test_a_teachers_export_shows_a_pooled_class_once_with_both_sections(api):
    from app.core.database import SessionLocal
    from app.models.school import Timetable
    from app.services import export as ex

    _create(api, [{"subject_id": api["s"]["Maths"], "preferred_teacher_id": api["t"]["Mr. Maths"]},
                  {"subject_id": api["s"]["History"]}], sections=[api["a"], api["b"]], ppw=1)
    t = _generate(api)
    session = SessionLocal()
    try:
        data = ex._load_grid_data(session, session.get(Timetable, t["id"]))
        rows = ex._grid_rows(data, data["entries_by_teacher_period"], api["t"]["Mr. Maths"], mode="teacher")
    finally:
        session.close()
    cells = [cell for row in rows[1:] for cell in row[1:] if "Maths" in cell]
    assert len(cells) == 1 and "A" in cells[0] and "B" in cells[0], cells


def test_a_joined_sections_students_choose_only_from_their_own_groups(db):
    from app.services.student_combinations import combinations_for

    s = _grade9(db)
    s.block(["Grade 9 A", "Grade 9 B"], 1, [
        ("Maths", None, "Group 1", None), ("Maths", None, "Group 2", None),
        ("CS", ["Grade 9 A"], None, None), ("History", ["Grade 9 B"], None, None),
    ])
    labels_b = sorted(c.label for c in combinations_for(db, s.sections["Grade 9 B"].id))
    assert labels_b == ["History", "Maths (Group 1)", "Maths (Group 2)"]
    labels_a = sorted(c.label for c in combinations_for(db, s.sections["Grade 9 A"].id))
    assert labels_a == ["CS", "Maths (Group 1)", "Maths (Group 2)"]
