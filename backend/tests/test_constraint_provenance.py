"""
Tests for recording what an admin typed and which parser read it.

The point of these columns is to answer "which phrasings do we fail to
understand" - which needs the input, not the parser's summary of it, and
needs to distinguish Claude's failures from the regex fallback's. Asserted
through the API, since that is where the values get set.

No ANTHROPIC_API_KEY is configured in the test suite, so the regex parser
is what runs here; that is itself worth asserting, because a scheduling_rule
row from the fallback means something different from one Claude produced.
"""
from tests.conftest import create_school, signup


def _setup(client, subjects=("PE",)):
    _, headers = signup(client)
    school = create_school(client, headers)
    for name in subjects:
        r = client.post("/api/subjects", json={"school_id": school["id"], "name": name}, headers=headers)
        assert r.status_code == 201, r.text
    return headers, school["id"]


def _constraints(client, headers, school_id):
    r = client.get(f"/api/constraints?school_id={school_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_parse_records_the_original_text_not_the_summary(client):
    """`description` is the parser's wording; source_text must be the admin's."""
    headers, school_id = _setup(client)
    typed = "No PE in the last period"

    r = client.post(
        "/api/constraints/parse",
        json={"school_id": school_id, "text": typed},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["constraint"]["source_text"] == typed


def test_the_parser_used_is_recorded(client):
    headers, school_id = _setup(client)
    r = client.post(
        "/api/constraints/parse",
        json={"school_id": school_id, "text": "No PE in the last period"},
        headers=headers,
    )
    assert r.json()["constraint"]["parsed_by"] == "regex"


def test_reparse_replaces_the_recorded_text(client):
    """A reword replaces the rule, so keeping the old input would attribute
    the new type to text that never produced it."""
    headers, school_id = _setup(client)
    created = client.post(
        "/api/constraints/parse",
        json={"school_id": school_id, "text": "No PE in the last period"},
        headers=headers,
    ).json()

    r = client.put(
        f"/api/constraints/{created['constraint']['id']}/reparse",
        json={"text": "No PE in the first period"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["constraint"]["source_text"] == "No PE in the first period"


def test_batch_records_each_line_separately_on_the_fallback_path(client):
    """With no LLM available each line is its own rule, so each row should
    carry its own sentence rather than the whole paste."""
    headers, school_id = _setup(client, subjects=("PE", "Math"))
    r = client.post(
        "/api/constraints/batch",
        json={
            "school_id": school_id,
            "text": "No PE in the last period\nNo Math in the first period",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text

    sources = [c["constraint"]["source_text"] for c in r.json()]
    assert "No PE in the last period" in sources
    assert all("\n" not in (s or "") for s in sources), "a row recorded the whole block"


def test_directly_created_constraints_have_no_recorded_text(client):
    """POST /api/constraints takes an already-resolved type/parameters, so
    there is no admin sentence behind it - null rather than something
    invented."""
    _, headers = signup(client)
    school = create_school(client, headers)
    r = client.post(
        "/api/constraints",
        json={
            "school_id": school["id"],
            "type": "scheduling_rule",
            "parameters": {},
            "description": "hand-made",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["source_text"] is None
    assert r.json()["parsed_by"] is None
