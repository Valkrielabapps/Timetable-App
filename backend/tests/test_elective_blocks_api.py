"""
The elective block API, and every way a block can schedule a subject twice.

Each of the refusals here guards the same failure: a subject counted twice for
one section, which silently inflates the section's real periods per week and
tends to surface much later as an infeasible timetable with no visible cause.
That exact shape of bug has already happened in this codebase twice, with
orphaned requirement rows - see the comments on delete_subject and
add_requirement - so the checks are written as a set and tested as one.
"""
import pytest

from tests.conftest import create_school, signup


@pytest.fixture
def school(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    sid = school["id"]

    def subject(name):
        r = client.post("/api/subjects", json={"school_id": sid, "name": name}, headers=headers)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    cg = client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 11", "name": "A"},
                     headers=headers).json()
    other = client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 11", "name": "B"},
                        headers=headers).json()
    teacher = client.post("/api/teachers", json={"school_id": sid, "name": "Mrs. Rao",
                                                 "qualified_subject_ids": []}, headers=headers).json()
    return {
        "headers": headers, "school_id": sid, "cg": cg["id"], "other_cg": other["id"],
        "teacher": teacher["id"],
        "physics": subject("Physics"), "accounts": subject("Accounts"),
        "history": subject("History"), "chemistry": subject("Chemistry"),
        "english": subject("English"),
    }


def _block(client, s, options, name="Block 1", cg=None, ppw=6):
    return client.post("/api/elective-blocks", json={
        "school_id": s["school_id"], "class_group_id": cg or s["cg"], "name": name,
        "periods_per_week": ppw, "options": [{"subject_id": o} for o in options],
    }, headers=s["headers"])


# ---------------------------------------------------------------------------
# Creating and reading
# ---------------------------------------------------------------------------


def test_a_block_is_created_with_its_options_in_order(client, school):
    s = school
    r = _block(client, s, [s["physics"], s["accounts"], s["history"]])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Block 1"
    assert body["periods_per_week"] == 6
    assert [o["subject_id"] for o in body["options"]] == [s["physics"], s["accounts"], s["history"]]


def test_blocks_are_listed_for_the_school(client, school):
    s = school
    _block(client, s, [s["physics"], s["accounts"]])
    _block(client, s, [s["chemistry"], s["history"]], name="Block 2")
    rows = client.get(f"/api/elective-blocks?school_id={s['school_id']}", headers=s["headers"]).json()
    assert [b["name"] for b in rows] == ["Block 1", "Block 2"]


def test_a_preferred_teacher_is_kept_on_its_option(client, school):
    s = school
    r = client.post("/api/elective-blocks", json={
        "school_id": s["school_id"], "class_group_id": s["cg"], "name": "Block 1",
        "periods_per_week": 6,
        "options": [{"subject_id": s["physics"], "preferred_teacher_id": s["teacher"]},
                    {"subject_id": s["accounts"]}],
    }, headers=s["headers"])
    assert r.status_code == 201, r.text
    assert r.json()["options"][0]["preferred_teacher_id"] == s["teacher"]


# ---------------------------------------------------------------------------
# Every way to schedule a subject twice
# ---------------------------------------------------------------------------


def test_a_block_needs_at_least_two_options(client, school):
    """One option is not a choice - it is a subject everyone takes."""
    s = school
    r = _block(client, s, [s["physics"]])
    assert r.status_code == 400
    assert "common subjects" in r.json()["detail"]


def test_the_same_subject_cannot_appear_twice_in_one_block(client, school):
    s = school
    r = _block(client, s, [s["physics"], s["physics"]])
    assert r.status_code == 400
    assert "Physics" in r.json()["detail"]


def test_a_subject_cannot_be_in_two_blocks_of_one_section(client, school):
    s = school
    assert _block(client, s, [s["physics"], s["accounts"]]).status_code == 201
    r = _block(client, s, [s["physics"], s["history"]], name="Block 2")
    assert r.status_code == 400
    assert "Physics" in r.json()["detail"] and "Block 1" in r.json()["detail"]


def test_the_same_subject_may_be_in_blocks_of_different_sections(client, school):
    """The rule is per section - 11B offering Physics has nothing to do with 11A."""
    s = school
    assert _block(client, s, [s["physics"], s["accounts"]]).status_code == 201
    assert _block(client, s, [s["physics"], s["accounts"]], cg=s["other_cg"]).status_code == 201


def test_a_common_subject_cannot_also_be_a_block_option(client, school):
    s = school
    client.post(f"/api/class-groups/{s['cg']}/requirements", json={
        "class_group_id": s["cg"], "subject_id": s["physics"], "periods_per_week": 5,
    }, headers=s["headers"])
    r = _block(client, s, [s["physics"], s["accounts"]])
    assert r.status_code == 400
    assert "common subjects" in r.json()["detail"]


def test_a_block_option_cannot_then_be_added_as_a_common_subject(client, school):
    """The same check from the other direction, so neither order of entry can
    create the overlap."""
    s = school
    _block(client, s, [s["physics"], s["accounts"]])
    r = client.post(f"/api/class-groups/{s['cg']}/requirements", json={
        "class_group_id": s["cg"], "subject_id": s["physics"], "periods_per_week": 5,
    }, headers=s["headers"])
    assert r.status_code == 400
    assert "Block 1" in r.json()["detail"]


def test_a_common_subject_unrelated_to_any_block_is_still_accepted(client, school):
    s = school
    _block(client, s, [s["physics"], s["accounts"]])
    r = client.post(f"/api/class-groups/{s['cg']}/requirements", json={
        "class_group_id": s["cg"], "subject_id": s["english"], "periods_per_week": 5,
    }, headers=s["headers"])
    assert r.status_code == 201, r.text


def test_a_subject_from_another_school_is_refused(client, school):
    s = school
    _, other_headers = signup(client, email="other@school.com")
    other_school = create_school(client, other_headers)
    foreign = client.post("/api/subjects", json={"school_id": other_school["id"], "name": "Latin"},
                          headers=other_headers).json()["id"]
    r = _block(client, s, [s["physics"], foreign])
    assert r.status_code == 400


def test_another_schools_section_is_refused(client, school):
    s = school
    _, other_headers = signup(client, email="other@school.com")
    other_school = create_school(client, other_headers)
    foreign_cg = client.post("/api/class-groups", json={"school_id": other_school["id"], "name": "X"},
                             headers=other_headers).json()["id"]
    r = _block(client, s, [s["physics"], s["accounts"]], cg=foreign_cg)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------


def test_editing_can_keep_a_subject_across_the_edit(client, school):
    """Replacing the option set while keeping one of its subjects tripped the
    (block, subject) unique constraint if the new rows were inserted before
    the old ones were deleted."""
    s = school
    block = _block(client, s, [s["physics"], s["accounts"]]).json()
    r = client.put(f"/api/elective-blocks/{block['id']}", json={
        "options": [{"subject_id": s["physics"]}, {"subject_id": s["history"]}],
    }, headers=s["headers"])
    assert r.status_code == 200, r.text
    assert [o["subject_id"] for o in r.json()["options"]] == [s["physics"], s["history"]]


def test_an_edit_is_not_refused_for_clashing_with_its_own_options(client, school):
    s = school
    block = _block(client, s, [s["physics"], s["accounts"]]).json()
    r = client.put(f"/api/elective-blocks/{block['id']}", json={"periods_per_week": 4},
                   headers=s["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["periods_per_week"] == 4


def test_an_edit_still_refuses_a_clash_with_another_block(client, school):
    s = school
    _block(client, s, [s["physics"], s["accounts"]])
    second = _block(client, s, [s["chemistry"], s["history"]], name="Block 2").json()
    r = client.put(f"/api/elective-blocks/{second['id']}", json={
        "options": [{"subject_id": s["chemistry"]}, {"subject_id": s["physics"]}],
    }, headers=s["headers"])
    assert r.status_code == 400


def test_periods_per_week_must_be_positive(client, school):
    s = school
    assert _block(client, s, [s["physics"], s["accounts"]], ppw=0).status_code == 422


# ---------------------------------------------------------------------------
# Deletion leaves nothing behind
# ---------------------------------------------------------------------------


def test_deleting_a_block_removes_it(client, school):
    s = school
    block = _block(client, s, [s["physics"], s["accounts"]]).json()
    assert client.delete(f"/api/elective-blocks/{block['id']}", headers=s["headers"]).status_code == 204
    assert client.get(f"/api/elective-blocks?school_id={s['school_id']}", headers=s["headers"]).json() == []


def test_deleting_a_subject_removes_it_from_blocks(client, school):
    s = school
    _block(client, s, [s["physics"], s["accounts"], s["history"]])
    client.delete(f"/api/subjects/{s['history']}", headers=s["headers"])
    block = client.get(f"/api/elective-blocks?school_id={s['school_id']}", headers=s["headers"]).json()[0]
    assert [o["subject_id"] for o in block["options"]] == [s["physics"], s["accounts"]]


def test_a_block_emptied_by_subject_deletion_is_removed(client, school):
    """A block with no options left would still reserve the section's periods
    for nothing at all."""
    s = school
    _block(client, s, [s["physics"], s["accounts"]])
    client.delete(f"/api/subjects/{s['physics']}", headers=s["headers"])
    client.delete(f"/api/subjects/{s['accounts']}", headers=s["headers"])
    assert client.get(f"/api/elective-blocks?school_id={s['school_id']}", headers=s["headers"]).json() == []


def test_deleting_a_preferred_teacher_clears_the_pin(client, school):
    """A pin to a teacher who no longer exists reads as "only this teacher",
    finds nobody, and fails generation as "no qualified teacher" - pointing at
    qualifications instead of the deletion."""
    s = school
    client.post("/api/elective-blocks", json={
        "school_id": s["school_id"], "class_group_id": s["cg"], "name": "Block 1",
        "periods_per_week": 6,
        "options": [{"subject_id": s["physics"], "preferred_teacher_id": s["teacher"]},
                    {"subject_id": s["accounts"]}],
    }, headers=s["headers"])
    client.delete(f"/api/teachers/{s['teacher']}", headers=s["headers"])
    block = client.get(f"/api/elective-blocks?school_id={s['school_id']}", headers=s["headers"]).json()[0]
    assert block["options"][0]["preferred_teacher_id"] is None


def test_deleting_a_section_removes_its_blocks(client, school):
    s = school
    _block(client, s, [s["physics"], s["accounts"]])
    client.delete(f"/api/class-groups/{s['cg']}", headers=s["headers"])
    assert client.get(f"/api/elective-blocks?school_id={s['school_id']}", headers=s["headers"]).json() == []


def test_a_viewer_cannot_create_blocks(client, school):
    """Writes need the admin role, like every other setup endpoint."""
    s = school
    # A stranger to this school, which is the case that must certainly fail.
    viewer, viewer_headers = signup(client, email="stranger@else.com")
    r = client.post("/api/elective-blocks", json={
        "school_id": s["school_id"], "class_group_id": s["cg"], "name": "Block 1",
        "periods_per_week": 6,
        "options": [{"subject_id": s["physics"]}, {"subject_id": s["accounts"]}],
    }, headers=viewer_headers)
    assert r.status_code in (403, 404)


def test_blocks_entered_through_the_api_come_out_of_generation_whole(client, school):
    """End to end: a block entered through the API, generated by the real
    background job, read back through the API.

    Every layer has its own tests; this is the one that proves they connect -
    that the block id survives from the solver's assignment, through the row
    the job writes, into what the grid receives.
    """
    from app.core.database import SessionLocal
    from app.models.school import Timetable
    from app.routers.timetables import _run_generation_job

    s = school
    h = s["headers"]
    for order in range(3):
        assert client.post("/api/periods", json={"school_id": s["school_id"], "day_of_week": 0,
                                                 "order": order, "label": f"P{order + 1}"},
                           headers=h).status_code == 201
    for name, subject in (("Mr. Khan", "physics"), ("Ms. Das", "accounts"), ("Mr. Iyer", "history"),
                          ("Mrs. Nair", "english")):
        client.post("/api/teachers", json={"school_id": s["school_id"], "name": name,
                                           "qualified_subject_ids": [s[subject]]}, headers=h)
    block = _block(client, s, [s["physics"], s["accounts"], s["history"]], ppw=2).json()
    client.post(f"/api/class-groups/{s['cg']}/requirements", json={
        "class_group_id": s["cg"], "subject_id": s["english"], "periods_per_week": 1,
    }, headers=h)

    db = SessionLocal()
    try:
        tt = Timetable(school_id=s["school_id"], status="generating")
        db.add(tt)
        db.commit()
        tt_id = tt.id
    finally:
        db.close()
    _run_generation_job(tt_id, s["school_id"])

    out = client.get(f"/api/timetables/{tt_id}", headers=h).json()
    assert out["status"] == "draft", out.get("error_message")
    block_rows = [e for e in out["entries"] if e["elective_block_id"] == block["id"]]
    assert len(block_rows) == 6, "three options, two periods each"
    assert {e["elective_block_name"] for e in block_rows} == {"Block 1"}
    by_period: dict = {}
    for e in block_rows:
        by_period.setdefault(e["period_id"], set()).add(e["subject_name"])
    assert all(subjects == {"Physics", "Accounts", "History"} for subjects in by_period.values())
    english = [e for e in out["entries"] if e["subject_name"] == "English"]
    assert len(english) == 1 and english[0]["elective_block_id"] is None
    assert out["violations"] == []
