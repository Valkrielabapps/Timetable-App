"""A section's subject can have a shortlist of teachers ("Priya or Joseph"):
the solver picks one of them, never anyone else qualified."""
import pytest

from app.core.config import settings
from app.models.school import SubjectRequirement
from app.services.solver import generate_school_timetable
from tests.conftest import create_school, signup
from tests.test_ir_end_to_end import _class_group, _require, _school, _subject, _teacher, db  # noqa: F401


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_solver_only_uses_the_shortlist(db, monkeypatch, seed):  # noqa: F811
    monkeypatch.setattr(settings, "solver_random_seed", seed)
    school = _school(db, days=2, per_day=3)
    eng = _subject(db, school, "English")
    priya, joseph, anita = (_teacher(db, school, n, [eng.id]) for n in ("Priya", "Joseph", "Anita"))
    cg = _class_group(db, school)
    _require(db, cg, eng, 3)
    row = db.query(SubjectRequirement).filter_by(class_group_id=cg.id, subject_id=eng.id).one()
    row.allowed_teacher_ids = [priya.id, joseph.id]
    db.commit()

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    used = {a["teacher_id"] for a in result.assignments}
    assert len(used) == 1 and used <= {priya.id, joseph.id}


def test_saving_a_shortlist_keeps_it_tidy(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    subj = client.post("/api/subjects", json={"school_id": sid, "name": "English"}, headers=h).json()
    a, b = (client.post("/api/teachers", headers=h, json={"school_id": sid, "name": n, "qualified_subject_ids": [subj["id"]]}).json() for n in "AB")
    cg = client.post("/api/class-groups", json={"school_id": sid, "grade": "9", "name": "A"}, headers=h).json()
    req = client.post(f"/api/class-groups/{cg['id']}/requirements", headers=h,
                      json={"class_group_id": cg["id"], "subject_id": subj["id"], "periods_per_week": 4}).json()
    url = f"/api/class-groups/requirements/{req['id']}"

    # Duplicates and an unknown id are dropped.
    r = client.put(url, headers=h, json={"allowed_teacher_ids": [a["id"], b["id"], a["id"], 99999]})
    assert r.status_code == 200 and r.json()["allowed_teacher_ids"] == [a["id"], b["id"]]
    # One teacher is not a shortlist.
    r = client.put(url, headers=h, json={"allowed_teacher_ids": [a["id"]]})
    assert r.json()["allowed_teacher_ids"] is None
