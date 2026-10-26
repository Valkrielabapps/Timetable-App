"""
Substitutions arranged by date and by part of the school, and the day's
summary built from them.

The properties under test:
  - grades fall into pre-primary / primary / middle / high school by name,
    and a school's own choice in Settings wins;
  - saving a date's cover for one part again replaces the earlier save,
    while other parts and dates are left alone;
  - the summary for a part shows only that part's lessons and the teachers
    whose absence matters there; for the whole school, everything;
  - a lesson nobody covers is kept and counted as not covered;
  - partial leave is reported by period number, whole-day leave as such.
"""
from datetime import date

import pytest

from app.core.database import SessionLocal
from app.models.school import ClassGroup, Subject, SubstitutionLog, Teacher
from app.schemas.timetable_structure import TimetableStructure
from app.services.school_categories import category_of, default_category
from app.services.substitution_summary import summary_pdf
from app.services.timetable_structure import apply
from app.models.school import Period
from tests.conftest import create_school, signup
from tests.test_access_control import _invite_and_accept

MONDAY = date(2026, 10, 26)


@pytest.mark.parametrize("grade,expected", [
    ("Nursery", "pre_primary"), ("LKG", "pre_primary"), ("UKG", "pre_primary"), ("KG 2", "pre_primary"),
    ("Pre-KG", "pre_primary"), ("Pre-primary", "pre_primary"), ("Playgroup", "pre_primary"),
    ("Grade 1", "primary"), ("Class V", "primary"), ("5th", "primary"),
    ("Grade 6", "middle"), ("Class VIII", "middle"), ("Std 8", "middle"),
    ("Grade 9", "high"), ("Class XII", "high"), ("11", "high"),
    ("Foundation", None), ("Grade 13", None), (None, None),
])
def test_default_categories(grade, expected):
    assert default_category(grade) == expected


def test_school_choice_wins_over_the_default():
    assert category_of("Grade 6", {"Grade 6": "primary"}) == "primary"
    assert category_of("Grade 6", {"Grade 5": "middle"}) == "middle"
    assert category_of("Grade 6", {"Grade 6": None}) is None
    assert category_of("Grade 6", {"Grade 6": "nonsense"}) is None


@pytest.fixture
def world(client):
    """Monday, three lessons. Mrs. Rao teaches Grade 3 A; Mr. Khan Grade 7 A."""
    _, headers = signup(client)
    sid = create_school(client, headers)["id"]
    db = SessionLocal()
    try:
        apply(db, sid, TimetableStructure(days=[0], periods_per_day=3))
        periods = sorted(db.query(Period).filter(Period.school_id == sid), key=lambda p: p.order)
        maths = Subject(school_id=sid, name="Maths")
        rao, khan, iyer = (Teacher(school_id=sid, name=n) for n in ("Mrs. Rao", "Mr. Khan", "Ms. Iyer"))
        three = ClassGroup(school_id=sid, grade="Grade 3", name="A")
        seven = ClassGroup(school_id=sid, grade="Grade 7", name="A")
        db.add_all([maths, rao, khan, iyer, three, seven])
        db.commit()
        ids = {"school": sid, "p": [p.id for p in periods], "maths": maths.id, "rao": rao.id, "khan": khan.id,
               "iyer": iyer.id, "three": three.id, "seven": seven.id}
    finally:
        db.close()
    return ids, headers


def change(w, period, cls, absent, sub):
    return {"period_id": w["p"][period], "class_group_id": w[cls], "absent_teacher_id": w[absent],
            "substituting_teacher_id": w[sub] if sub else None, "subject_id": w["maths"]}


def save(client, headers, w, body):
    r = client.post(f"/api/schools/{w['school']}/substitutions", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def summary(client, headers, w, category=None, day=MONDAY):
    params = {"date": day.isoformat()}
    if category:
        params["category"] = category
    r = client.get(f"/api/schools/{w['school']}/substitutions/summary", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_save_derives_weekday_and_each_lessons_part(client, world):
    w, headers = world
    log = save(client, headers, w, {
        "date": MONDAY.isoformat(), "category": "primary",
        "absences": [{"teacher_id": w["rao"], "period_ids": None}],
        "changes": [change(w, 0, "three", "rao", "iyer")],
    })
    assert log["day_of_week"] == 0
    assert log["date"] == MONDAY.isoformat()
    assert log["changes"][0]["category"] == "primary"


def test_saving_a_part_again_replaces_only_that_parts_save(client, world):
    w, headers = world
    base = {"date": MONDAY.isoformat(), "absences": []}
    first = save(client, headers, w, {**base, "category": "primary", "changes": [change(w, 0, "three", "rao", "iyer")]})
    middle = save(client, headers, w, {**base, "category": "middle", "changes": [change(w, 1, "seven", "khan", "iyer")]})
    other_day = save(client, headers, w, {**base, "date": "2026-10-27", "category": "primary",
                                          "changes": [change(w, 0, "three", "rao", "iyer")]})
    again = save(client, headers, w, {**base, "category": "primary", "changes": [change(w, 0, "three", "rao", None)]})
    assert again["id"] == first["id"]
    db = SessionLocal()
    try:
        ids = {log.id for log in db.query(SubstitutionLog)}
    finally:
        db.close()
    assert ids == {first["id"], middle["id"], other_day["id"]}
    rows = summary(client, headers, w, "primary")["rows"]
    assert [r["substitute"] for r in rows] == [None]


def test_summary_for_a_part_and_for_the_whole_school(client, world):
    w, headers = world
    save(client, headers, w, {
        "date": MONDAY.isoformat(), "category": "primary",
        "absences": [{"teacher_id": w["rao"], "period_ids": [w["p"][2], w["p"][0]]}],
        "changes": [change(w, 2, "three", "rao", None), change(w, 0, "three", "rao", "iyer")],
    })
    save(client, headers, w, {
        "date": MONDAY.isoformat(), "category": "middle",
        "absences": [{"teacher_id": w["khan"], "period_ids": None}],
        "changes": [change(w, 1, "seven", "khan", "iyer")],
    })

    primary = summary(client, headers, w, "primary")
    assert primary["weekday"] == "Monday"
    assert primary["category_label"] == "Primary"
    assert primary["on_leave"] == [{"teacher_id": w["rao"], "teacher": "Mrs. Rao", "periods": ["Period 1", "Period 3"]}]
    assert [(r["period"], r["class_group"], r["absent_teacher"], r["substitute"]) for r in primary["rows"]] == [
        ("Period 1", "Grade 3 - A", "Mrs. Rao", "Ms. Iyer"),
        ("Period 3", "Grade 3 - A", "Mrs. Rao", None),
    ]
    assert primary["uncovered"] == 1

    middle = summary(client, headers, w, "middle")
    assert [p["teacher"] for p in middle["on_leave"]] == ["Mr. Khan"]
    assert middle["on_leave"][0]["periods"] is None
    assert middle["uncovered"] == 0

    whole = summary(client, headers, w)
    assert whole["category_label"] == "Whole school"
    # Sorted by first name, titles ignored: Khan before Rao.
    assert [p["teacher"] for p in whole["on_leave"]] == ["Mr. Khan", "Mrs. Rao"]
    assert [(r["period"], r["category"]) for r in whole["rows"]] == [
        ("Period 1", "primary"), ("Period 2", "middle"), ("Period 3", "primary"),
    ]
    assert whole["uncovered"] == 1

    assert summary(client, headers, w, "primary", day=date(2026, 10, 27))["rows"] == []


def test_a_whole_school_save_is_split_by_part(client, world):
    w, headers = world
    save(client, headers, w, {
        "date": MONDAY.isoformat(),
        "absences": [{"teacher_id": w["rao"]}, {"teacher_id": w["khan"]}],
        "changes": [change(w, 0, "three", "rao", "iyer"), change(w, 1, "seven", "khan", None)],
    })
    primary = summary(client, headers, w, "primary")
    assert [p["teacher"] for p in primary["on_leave"]] == ["Mrs. Rao"]
    assert [r["class_group"] for r in primary["rows"]] == ["Grade 3 - A"]
    assert primary["uncovered"] == 0
    assert summary(client, headers, w, "middle")["uncovered"] == 1


def test_older_records_without_dates_still_summarise(client, world):
    w, headers = world
    r = client.post(f"/api/schools/{w['school']}/substitutions", headers=headers,
                    json={"day_of_week": 0, "changes": [change(w, 0, "three", "rao", "iyer")]})
    assert r.status_code == 201
    created = date.fromisoformat(r.json()["created_at"][:10])
    out = summary(client, headers, w, day=created)
    assert [r["substitute"] for r in out["rows"]] == ["Ms. Iyer"]
    # No absences were kept: the periods they were covered for stand in.
    assert out["on_leave"][0]["periods"] == ["Period 1"]


def test_regrouping_a_grade_moves_its_lessons(client, world):
    w, headers = world
    r = client.put(f"/api/schools/{w['school']}/grade-categories", headers=headers,
                   json={"categories": {"Grade 7": "high", "Grade 3": "primary"}})
    assert r.status_code == 200
    assert r.json() == [
        {"grade": "Grade 3", "category": "primary", "default": "primary"},
        {"grade": "Grade 7", "category": "high", "default": "middle"},
    ]
    db = SessionLocal()
    try:
        from app.models.school import School
        # Only the change from the default is stored.
        assert db.get(School, w["school"]).grade_categories == {"Grade 7": "high"}
    finally:
        db.close()
    save(client, headers, w, {"date": MONDAY.isoformat(), "absences": [],
                              "changes": [change(w, 1, "seven", "khan", "iyer")]})
    assert len(summary(client, headers, w, "high")["rows"]) == 1
    assert summary(client, headers, w, "middle")["rows"] == []


def test_unknown_parts_are_refused(client, world):
    w, headers = world
    r = client.post(f"/api/schools/{w['school']}/substitutions", headers=headers,
                    json={"date": MONDAY.isoformat(), "category": "upper", "changes": []})
    assert r.status_code == 422
    r = client.put(f"/api/schools/{w['school']}/grade-categories", headers=headers,
                   json={"categories": {"Grade 7": "upper"}})
    assert r.status_code == 422
    r = client.post(f"/api/schools/{w['school']}/substitutions", headers=headers, json={"changes": []})
    assert r.status_code == 422


def test_viewers_can_read_but_not_save(client, world):
    w, headers = world
    _, viewer = _invite_and_accept(client, headers, w["school"], "viewer@a.com", "viewer")
    assert summary(client, viewer, w)["rows"] == []
    assert client.get(f"/api/schools/{w['school']}/grade-categories", headers=viewer).status_code == 200
    r = client.post(f"/api/schools/{w['school']}/substitutions", headers=viewer,
                    json={"date": MONDAY.isoformat(), "changes": []})
    assert r.status_code == 403
    r = client.put(f"/api/schools/{w['school']}/grade-categories", headers=viewer, json={"categories": {}})
    assert r.status_code == 403
    _, stranger = signup(client, email="b@b.com")
    r = client.get(f"/api/schools/{w['school']}/substitutions/summary", params={"date": MONDAY.isoformat()},
                   headers=stranger)
    assert r.status_code == 404


def test_pdf(client, world):
    w, headers = world
    save(client, headers, w, {
        "date": MONDAY.isoformat(), "absences": [{"teacher_id": w["rao"]}],
        "changes": [change(w, 0, "three", "rao", None)],
    })
    r = client.get(f"/api/schools/{w['school']}/substitutions/summary.pdf",
                   params={"date": MONDAY.isoformat()}, headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert "substitutions-2026-10-26-whole-school.pdf" in r.headers["content-disposition"]


def test_pdf_text(monkeypatch):
    """What the PDF says, read off what goes onto the page."""
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table

    texts = []

    def collect(flowable):
        if isinstance(flowable, Paragraph):
            texts.append(flowable.getPlainText())
        elif isinstance(flowable, Table):
            for row in flowable._cellvalues:
                for cell in row:
                    collect(cell) if not isinstance(cell, str) else texts.append(cell)

    original = SimpleDocTemplate.build

    def build(self, story, *a, **kw):
        for f in story:
            collect(f)
        return original(self, story, *a, **kw)

    monkeypatch.setattr(SimpleDocTemplate, "build", build)
    pdf = summary_pdf({
        "date": MONDAY, "weekday": "Monday", "category": None, "category_label": "Whole school",
        "on_leave": [{"teacher_id": 1, "teacher": "Mrs. Rao", "periods": ["Period 2"]},
                     {"teacher_id": 2, "teacher": "Mr. Khan", "periods": None}],
        "rows": [
            {"period": "Period 2", "class_group": "Grade 3 - A", "subject": "Maths", "category": "primary",
             "category_label": "Primary", "absent_teacher": "Mrs. Rao", "substitute": None},
            {"period": "Period 1", "class_group": "Grade 7 - A", "subject": "Science & Tech", "category": "middle",
             "category_label": "Middle", "absent_teacher": "Mr. Khan", "substitute": "Ms. Iyer"},
        ],
        "uncovered": 1,
    }, "Greenfield")
    assert pdf.startswith(b"%PDF")
    text = " | ".join(texts)
    for expected in ("Monday, 26 October 2026", "Greenfield", "Whole school", "Mrs. Rao (Period 2)",
                     "Mr. Khan (whole day)", "Primary", "Middle", "Not covered", "Science & Tech", "Ms. Iyer",
                     "1 period still needs cover"):
        assert expected in text, expected
    assert text.index("Primary") < text.index("Middle")


def test_later_saves_win_and_whole_day_beats_some_periods(client, world):
    w, headers = world
    save(client, headers, w, {
        "date": MONDAY.isoformat(), "absences": [{"teacher_id": w["rao"]}],
        "changes": [change(w, 0, "three", "rao", "iyer")],
    })
    # Arranged again from the primary block: nobody free after all.
    save(client, headers, w, {
        "date": MONDAY.isoformat(), "category": "primary",
        "absences": [{"teacher_id": w["rao"], "period_ids": [w["p"][0]]}],
        "changes": [change(w, 0, "three", "rao", None)],
    })
    out = summary(client, headers, w)
    assert [r["substitute"] for r in out["rows"]] == [None]
    assert out["on_leave"][0]["periods"] is None


def test_a_saved_lesson_keeps_the_part_it_was_arranged_in(client, world):
    w, headers = world
    save(client, headers, w, {"date": MONDAY.isoformat(), "absences": [],
                              "changes": [change(w, 1, "seven", "khan", "iyer")]})
    client.put(f"/api/schools/{w['school']}/grade-categories", headers=headers,
               json={"categories": {"Grade 7": "high"}})
    assert len(summary(client, headers, w, "middle")["rows"]) == 1
    assert summary(client, headers, w, "high")["rows"] == []
