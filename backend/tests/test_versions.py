"""Timetable versions: open any version, rename, delete, freeze from a chosen
version, and keep the newest five."""
from app.core.database import SessionLocal
from app.models.school import Timetable
from app.services import versions
from tests.test_freezing import freeze, generate, lessons, world  # noqa: F401


def listed(client, w, h):
    rows = client.get(f"/api/timetables?school_id={w['school']}", headers=h).json()
    return {r["id"]: r for r in rows}


def test_each_new_version_is_numbered_and_becomes_current(client, world):  # noqa: F811
    w, h = world
    first, second = generate(w), generate(w)
    rows = listed(client, w, h)
    assert rows[first]["version_number"] == 1 and rows[second]["version_number"] == 2
    assert rows[second]["is_current"] and not rows[first]["is_current"]
    assert client.get(f"/api/timetables/{second}", headers=h).json()["is_current"] is True


def test_an_older_version_can_be_opened_and_edited(client, world):  # noqa: F811
    w, h = world
    first = generate(w)
    generate(w)
    r = client.post(f"/api/timetables/{first}/make-current", headers=h)
    assert r.status_code == 200 and r.json()["is_current"]
    assert listed(client, w, h)[first]["is_current"]
    # Edits work on it: lock one of its lessons.
    entry = client.get(f"/api/timetables/{first}", headers=h).json()["entries"][0]
    r = client.patch(f"/api/timetables/entries/{entry['id']}", headers=h, json={"locked": True})
    assert r.status_code == 200, r.text


def test_a_version_can_be_renamed(client, world):  # noqa: F811
    w, h = world
    first = generate(w)
    r = client.patch(f"/api/timetables/{first}", headers=h, json={"name": "Grades 1-5 approved"})
    assert r.json()["name"] == "Grades 1-5 approved"
    assert client.patch(f"/api/timetables/{first}", headers=h, json={"name": "  "}).json()["name"] is None


def test_deleting_versions(client, world):  # noqa: F811
    w, h = world
    first, second = generate(w), generate(w)
    assert client.delete(f"/api/timetables/{first}", headers=h).status_code == 204
    assert first not in listed(client, w, h)
    # Deleting the current one hands "current" to the newest left.
    third = generate(w)
    client.post(f"/api/timetables/{second}/make-current", headers=h)
    assert client.delete(f"/api/timetables/{second}", headers=h).status_code == 204
    assert listed(client, w, h)[third]["is_current"]


def test_a_version_sections_are_frozen_from_cannot_be_deleted(client, world):  # noqa: F811
    w, h = world
    first = generate(w)
    freeze(client, w, h, "eleven")
    r = client.delete(f"/api/timetables/{first}", headers=h)
    assert r.status_code == 409 and "Grade 11 - A" in r.json()["detail"]


def test_a_section_stays_as_it_was_in_the_version_it_was_frozen_from(client, world):  # noqa: F811
    """Approve 11A in Version 1, carry on generating; Version 1's 11A comes
    through every time, even though Version 2 is newer."""
    w, h = world
    v1 = generate(w)
    approved = [row[1:] for row in lessons(v1, w["eleven"])]
    v2 = generate(w)
    client.post(f"/api/timetables/{v1}/make-current", headers=h)
    freeze(client, w, h, "eleven")
    status = {s["class_group_id"]: s for s in
              client.get(f"/api/class-groups/frozen-status?school_id={w['school']}", headers=h).json()}
    assert status[w["eleven"]]["frozen_from"] == "Version 1"
    client.post(f"/api/timetables/{v2}/make-current", headers=h)
    v3 = generate(w)
    assert [row[1:] for row in lessons(v3, w["eleven"])] == approved
    body = client.get(f"/api/timetables/{v3}", headers=h).json()
    assert body["frozen_kept"] == ["Grade 11 - A"] and body["is_current"]


def test_the_newest_five_are_kept_plus_current_and_frozen_sources(client, world):  # noqa: F811
    w, h = world
    first = generate(w)
    freeze(client, w, h, "eleven")          # Version 1 is now a freeze source
    made = [generate(w) for _ in range(7)]  # prune runs after each
    left = set(listed(client, w, h))
    assert first in left                     # kept: 11A is frozen from it
    assert set(made[-versions.KEEP_VERSIONS:]) <= left
    assert len(left) == versions.KEEP_VERSIONS + 1


def test_a_viewer_cannot_change_versions(client, world):  # noqa: F811
    from tests.conftest import signup
    w, h = world
    first = generate(w)
    _, stranger = signup(client, email="someone@else.com")
    assert client.delete(f"/api/timetables/{first}", headers=stranger).status_code in (403, 404)
    assert client.post(f"/api/timetables/{first}/make-current", headers=stranger).status_code in (403, 404)
