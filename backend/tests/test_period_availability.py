"""
Tests for availability constraints that name specific periods rather than a
whole day.

The catalogue (docs/research/constraint-catalogue.tsv, R003/R004/R005/R009)
puts "can't take the first period on Tuesdays" among the most common rules a
school gives. Before period_orders existed the parser had no field for "the
first period", so that sentence could only become availability + day_of_week
- which blocks the teacher's entire Tuesday. Over-constraining while the UI
says "enforced" is worse than not enforcing: the timetable silently loses
seven periods of a teacher nobody agreed to free up.

Teacher.unavailable_period_ids has always been a list of period ids, and the
solver has always honoured it at that granularity. The gap was only ever
between the parser and the router.
"""
from app.core.database import SessionLocal
from app.models.school import Period, Teacher
from app.routers.constraints import _apply_parsed_constraint, _load_resolution_data
from app.services.llm_constraint_parser import ParsedConstraint
from tests.conftest import create_school, signup

DAYS = 5
PER_DAY = 8


def _school_with_a_week(client, headers):
    """One teacher and a full 5x8 week, which is what makes "the whole of
    Tuesday" and "period 1 on Tuesday" tell each other apart."""
    school = create_school(client, headers)
    client.post(
        "/api/teachers",
        json={"school_id": school["id"], "name": "Mr. Khan", "qualified_subject_ids": []},
        headers=headers,
    )
    for day in range(DAYS):
        for order in range(1, PER_DAY + 1):
            r = client.post(
                "/api/periods",
                json={"school_id": school["id"], "day_of_week": day, "order": order,
                      "label": f"Period {order}"},
                headers=headers,
            )
            assert r.status_code == 201, r.text
    return school


def _apply(school_id, parsed):
    """Run one parsed constraint through the router's resolution step and
    return the teacher's resulting unavailable periods as (day, order)."""
    db = SessionLocal()
    try:
        data = _load_resolution_data(db, school_id)
        resolved = _apply_parsed_constraint(db, school_id, parsed, data)
        db.commit()
        teacher = db.query(Teacher).filter(Teacher.school_id == school_id).one()
        blocked = (
            db.query(Period)
            .filter(Period.id.in_(teacher.unavailable_period_ids or [-1]))
            .all()
        )
        return resolved, {(p.day_of_week, p.order) for p in blocked}
    finally:
        db.close()


def test_a_whole_day_off_still_blocks_the_whole_day(client):
    """The existing behaviour, pinned: "doesn't come on Tuesdays" means every
    period of Tuesday, and nothing on any other day."""
    _, headers = signup(client)
    school = _school_with_a_week(client, headers)

    resolved, blocked = _apply(
        school["id"],
        ParsedConstraint(type="availability", description="Mr. Khan doesn't come on Tuesdays",
                         teacher_name="Mr. Khan", day_of_week=1),
    )

    assert blocked == {(1, order) for order in range(1, PER_DAY + 1)}
    assert resolved.parameters["day_of_week"] == 1


def test_one_period_on_one_day_does_not_cost_the_teacher_the_day(client):
    """R005: "Mr. Khan can't take the first period on Tuesdays". Exactly one
    slot goes, and his other seven Tuesday periods stay available."""
    _, headers = signup(client)
    school = _school_with_a_week(client, headers)

    _, blocked = _apply(
        school["id"],
        ParsedConstraint(type="availability", description="Mr. Khan can't take the first period on Tuesdays",
                         teacher_name="Mr. Khan", day_of_week=1, period_orders=[1]),
    )

    assert blocked == {(1, 1)}


def test_a_period_with_no_day_named_blocks_that_period_every_day(client):
    """R004-shaped: "Priya leaves before the last two periods" names periods
    but no day, which means every working day - not "no day, so ignore it",
    which is what a day_of_week-only field forced."""
    _, headers = signup(client)
    school = _school_with_a_week(client, headers)

    _, blocked = _apply(
        school["id"],
        ParsedConstraint(type="availability", description="Mr. Khan never takes the last two periods",
                         teacher_name="Mr. Khan", period_orders=[7, 8]),
    )

    assert blocked == {(day, order) for day in range(DAYS) for order in (7, 8)}


def test_period_orders_that_do_not_exist_are_ignored_not_invented(client):
    """A model that answers "period 9" for an 8-period school must not
    silently widen the rule to something else. Only real periods block."""
    _, headers = signup(client)
    school = _school_with_a_week(client, headers)

    _, blocked = _apply(
        school["id"],
        ParsedConstraint(type="availability", description="nonsense",
                         teacher_name="Mr. Khan", day_of_week=1, period_orders=[9, 99]),
    )

    assert blocked == set()


def test_period_scoped_availability_reports_as_enforced(client):
    """The badge has to track what the solver actually reads, or it goes back
    to claiming rules are applied when they aren't."""
    _, headers = signup(client)
    school = _school_with_a_week(client, headers)

    resolved, _ = _apply(
        school["id"],
        ParsedConstraint(type="availability", description="Mr. Khan can't take the first period on Tuesdays",
                         teacher_name="Mr. Khan", day_of_week=1, period_orders=[1]),
    )

    assert resolved.db_type == "availability"
    assert resolved.parameters["period_numbers"] == [1]


def test_malformed_period_orders_from_the_model_do_not_reach_the_query():
    """period_orders lands in a SQL IN clause, so the tool-call field is
    coerced rather than trusted. A bare int, numeric strings and junk all have
    a defined answer; nothing here should raise."""
    from app.services.llm_constraint_parser import _int_list

    assert _int_list([1, 2]) == [1, 2]
    assert _int_list(3) == [3]            # a single period sent unwrapped
    assert _int_list(["5", "6"]) == [5, 6]
    assert _int_list([1, "x", 2.5]) == [1]
    assert _int_list([]) is None          # "no scoping", not "no periods"
    assert _int_list("abc") is None
    assert _int_list({"a": 1}) is None


def test_period_numbers_count_lessons_not_rows(client):
    """With a class teacher period first and lunch after period 2, "period 3"
    is the lesson after lunch - the timetable's "Period 3" - not the third row."""
    _, headers = signup(client)
    school = create_school(client, headers)
    client.post("/api/teachers", json={"school_id": school["id"], "name": "Mr. Khan",
                                       "qualified_subject_ids": []}, headers=headers)
    client.put(f"/api/schools/{school['id']}/timetable-structure", json={
        "days": [0], "periods_per_day": 4, "breaks": [{"after": 2, "label": "Lunch"}],
        "class_teacher_period": {"enabled": True}}, headers=headers)
    db = SessionLocal()
    try:
        lunch = db.query(Period).filter(Period.kind == "break").one()
        after_lunch = db.query(Period).filter(Period.order == lunch.order + 1).one()
    finally:
        db.close()
    _, blocked = _apply(
        school["id"],
        ParsedConstraint(type="availability", description="Mr. Khan can't take period 3",
                         teacher_name="Mr. Khan", period_orders=[3]),
    )
    assert blocked == {(0, after_lunch.order)}


def test_an_older_rule_frees_exactly_what_it_took(client):
    """Rules saved before numbering counted lessons matched the raw row; when
    one is deleted it must give back those same periods."""
    from app.routers.constraints import _availability_period_ids
    _, headers = signup(client)
    school = _school_with_a_week(client, headers)
    db = SessionLocal()
    try:
        ids = _availability_period_ids(db, school["id"], {"day_of_week": 1, "period_orders": [2]})
        rows = db.query(Period).filter(Period.id.in_(ids)).all()
        assert [(p.day_of_week, p.order) for p in rows] == [(1, 2)]
    finally:
        db.close()


def test_a_rule_frees_its_periods_when_deleted(client):
    """What a rule blocked is rebuilt from what it stored, so deleting it
    gives back exactly those periods - and not the whole day."""
    from app.routers.constraints import _availability_period_ids
    _, headers = signup(client)
    school = _school_with_a_week(client, headers)
    resolved, blocked = _apply(
        school["id"],
        ParsedConstraint(type="availability", description="Mr. Khan can't take period 3 on Tuesdays",
                         teacher_name="Mr. Khan", day_of_week=1, period_orders=[3]),
    )
    db = SessionLocal()
    try:
        ids = _availability_period_ids(db, school["id"], resolved.parameters)
        assert {(p.day_of_week, p.order) for p in db.query(Period).filter(Period.id.in_(ids))} == blocked
        assert len(blocked) == 1
    finally:
        db.close()
