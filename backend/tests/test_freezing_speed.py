"""
Freezing has to stay quick as a school grows. Every query is a trip to the
database, and reading plans one section at a time made freezing take seconds, so
the number of queries must not grow with the number of sections.
"""
import pytest
from sqlalchemy import event

from app.core.database import SessionLocal, engine
from app.models.school import (
    ClassGroup, ElectiveBlock, ElectiveBlockSection, ElectiveOption, Period, Subject, SubjectRequirement, Teacher,
    Timetable, TimetableEntry,
)
from app.services.freezing import blocks_by_section, plan_signature
from app.services.elective_sections import blocks_for_sections
from tests.conftest import create_school, signup

SECTIONS = 12


@pytest.fixture
def school(client):
    _, headers = signup(client)
    sid = create_school(client, headers)["id"]
    db = SessionLocal()
    try:
        period = Period(school_id=sid, day_of_week=0, order=0, label="P1")
        subject = Subject(school_id=sid, name="Physics")
        accounts = Subject(school_id=sid, name="Accounts")
        teacher = Teacher(school_id=sid, name="Susan", qualified_subject_ids=[])
        tt = Timetable(school_id=sid, status="draft", solver_status="manual", version_number=1)
        sections = [ClassGroup(school_id=sid, grade=f"Grade {n}", name="A") for n in range(SECTIONS)]
        db.add_all([period, subject, accounts, teacher, tt, *sections])
        db.flush()
        for cg in sections:
            db.add(SubjectRequirement(class_group_id=cg.id, subject_id=subject.id, periods_per_week=1))
            db.add(TimetableEntry(timetable_id=tt.id, class_group_id=cg.id, subject_id=subject.id, teacher_id=teacher.id, period_id=period.id))
            db.add(ElectiveBlock(school_id=sid, class_group_id=cg.id, name="Own block", periods_per_week=1,
                                 options=[ElectiveOption(subject_id=accounts.id)]))
        shared = ElectiveBlock(school_id=sid, class_group_id=sections[0].id, name="Shared", periods_per_week=2,
                               options=[ElectiveOption(subject_id=accounts.id)])
        db.add(shared)
        db.flush()
        db.add(ElectiveBlockSection(block_id=shared.id, class_group_id=sections[1].id))
        db.commit()
        yield {"sid": sid, "headers": headers, "ids": [cg.id for cg in sections], "subject": subject.id}
    finally:
        db.close()


class Queries:
    def __enter__(self):
        self.count = 0
        event.listen(engine, "before_cursor_execute", self._seen)
        return self

    def __exit__(self, *exc):
        event.remove(engine, "before_cursor_execute", self._seen)

    def _seen(self, *args):
        self.count += 1


def freeze(client, s, ids, frozen=True):
    return client.post("/api/class-groups/freeze", headers=s["headers"],
                       json={"school_id": s["sid"], "class_group_ids": ids, "frozen": frozen})


def test_freezing_many_costs_no_more_than_freezing_one(client, school):
    with Queries() as one:
        assert freeze(client, school, school["ids"][:1]).status_code == 200
    with Queries() as many:
        assert freeze(client, school, school["ids"][1:]).status_code == 200
    assert many.count <= one.count + 3, f"{one.count} for one section, {many.count} for {SECTIONS - 1}"
    assert many.count < 30


def test_status_doesnt_grow_with_frozen_sections(client, school):
    url = f"/api/class-groups/frozen-status?school_id={school['sid']}"
    freeze(client, school, school["ids"][:1])
    with Queries() as one:
        client.get(url, headers=school["headers"])
    freeze(client, school, school["ids"][1:])
    with Queries() as many:
        got = client.get(url, headers=school["headers"]).json()
    assert all(row["frozen"] and row["stale_reason"] is None for row in got), "the check still finds nothing wrong"
    assert many.count <= one.count + 2, f"{one.count} with one frozen, {many.count} with all"


def test_unfreezing_is_just_as_quick(client, school):
    freeze(client, school, school["ids"])
    with Queries() as q:
        res = freeze(client, school, school["ids"][:1], frozen=False)
    assert res.status_code == 200
    assert next(r for r in res.json() if r["class_group_id"] == school["ids"][0])["frozen"] is False
    assert q.count < 30


def test_freezing_a_subject_doesnt_grow_with_sections(client, school):
    with Queries() as q:
        res = client.post("/api/subject-freezes", headers=school["headers"],
                          json={"school_id": school["sid"], "subject_id": school["subject"], "scope": "school"})
    assert res.status_code == 201, res.text
    assert res.json()[0]["section_count"] == SECTIONS
    assert q.count < 35, f"{q.count} queries"
    with Queries() as listing:
        client.get(f"/api/subject-freezes?school_id={school['sid']}", headers=school["headers"])
    assert listing.count < 20, f"{listing.count} queries"


def test_the_signature_is_the_same_either_way(client, school):
    """Freezes saved before this change must still match, or every frozen section
    would suddenly say it was out of date."""
    db = SessionLocal()
    try:
        all_blocks = blocks_by_section(db, school["sid"])
        for section_id in school["ids"]:
            cg = db.get(ClassGroup, section_id)
            assert plan_signature(cg, all_blocks) == plan_signature(cg)
            assert [b.id for b in all_blocks.get(section_id, [])] == [b.id for b in blocks_for_sections(db, [section_id])]
    finally:
        db.close()


def test_a_changed_plan_still_shows_as_out_of_date(client, school):
    freeze(client, school, school["ids"])
    db = SessionLocal()
    req = db.query(SubjectRequirement).filter(SubjectRequirement.class_group_id == school["ids"][3]).first()
    req.periods_per_week = 4
    db.commit()
    db.close()
    got = client.get(f"/api/class-groups/frozen-status?school_id={school['sid']}", headers=school["headers"]).json()
    stale = [r["class_group_id"] for r in got if r["stale_reason"]]
    assert stale == [school["ids"][3]]
