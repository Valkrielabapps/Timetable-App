"""
No school can reach another school's records by changing an id.

Every route is called by the admin of one school with the ids of another
school's records - in the path, the query and the body - and must refuse.
A second pass sends the caller's own school_id with the other school's
records named alongside it, which is how one school could point its own data
at another's. Routes are read from the app itself, so a new route is covered
the day it's added; one that takes an id this file doesn't know fails until
it's taught here.
"""
import re

import pytest
from fastapi.testclient import TestClient

from sqlalchemy import select

from app.core.database import Base, SessionLocal
from app.main import app
from app.models.outreach import OutreachMessage, OutreachSchool
from app.models.payment import Invoice, PaymentOrder, PlanOffer
from app.models.problems import ProblemEvent
from app.models.school import (
    ClassGroup, Constraint, ElectiveBlock, ElectiveOption, Period, Room, RuleReadEvent, SchoolInvite,
    SchoolMembership, Subject, SubjectFreeze, SubjectRequirement, SubstitutionLog, Teacher, Timetable,
    TimetableEntry,
)
from tests.conftest import create_school, signup

# Open to anyone by design: signing in, blank import templates, the plan list,
# the payment provider's webhook (it checks its own signature), invite links
# (the secret token is the permission) and OAuth returns (signed state).
PUBLIC = {
    "/health", "/api/version", "/api/plans",
    "/api/auth/signup", "/api/auth/login", "/api/auth/google", "/api/auth/forgot-password", "/api/auth/reset-password",
    "/api/invites/{token}", "/api/invites/{token}/accept",
    "/api/payments/webhook",
    "/api/admin/outreach/gmail/callback", "/api/admin/outreach/zoho/callback",
    "/api/subjects/bulk-import/template", "/api/teachers/bulk-import/template",
    "/api/rooms/bulk-import/template", "/api/class-groups/bulk-import/template",
}
# Only about the caller themselves, so there is nobody else's id to send.
OWN_ACCOUNT = {"/api/auth/me", "/api/solver/test"}

REFUSED = {401, 403, 404}


def seed(db, sid, owner_id, staff_id, tag, teacher_name):
    """One of everything, for school `sid`. Names carry `tag` so a reply that
    shows them is easy to spot."""
    period = Period(school_id=sid, day_of_week=0, order=0, label="P1")
    period2 = Period(school_id=sid, day_of_week=0, order=1, label="P2")
    subject = Subject(school_id=sid, name=f"{tag} Physics")
    room = Room(school_id=sid, name=f"{tag} Lab")
    teacher = Teacher(school_id=sid, name=teacher_name, qualified_subject_ids=[])
    # Frozen, so a reply that says "... is frozen" would give its name away.
    section = ClassGroup(school_id=sid, grade=f"{tag} Grade 9", name="A", frozen=True)
    tt = Timetable(school_id=sid, status="draft", solver_status="manual", version_number=1)
    constraint = Constraint(school_id=sid, type="custom", description=f"{tag} rule")
    db.add_all([period, period2, subject, room, teacher, section, tt, constraint])
    db.flush()
    requirement = SubjectRequirement(class_group_id=section.id, subject_id=subject.id, periods_per_week=1)
    block = ElectiveBlock(school_id=sid, class_group_id=section.id, name=f"{tag} Block", periods_per_week=1,
                          options=[ElectiveOption(subject_id=subject.id)])
    entry = TimetableEntry(timetable_id=tt.id, class_group_id=section.id, subject_id=subject.id,
                           teacher_id=teacher.id, period_id=period.id)
    entry2 = TimetableEntry(timetable_id=tt.id, class_group_id=section.id, subject_id=subject.id,
                            teacher_id=teacher.id, period_id=period2.id)
    freeze = SubjectFreeze(school_id=sid, subject_id=subject.id, from_timetable_id=tt.id)
    log = SubstitutionLog(school_id=sid, day_of_week=0)
    invite = SchoolInvite(school_id=sid, email=f"staff-{sid}@example.com", token=f"{tag}-invite-token")
    order = PaymentOrder(order_id=f"{tag}-order-1", plan="pro", amount_paise=100, school_id=sid, user_id=owner_id)
    invoice = Invoice(number=f"INV-{tag}-1", description="Pro", amount_paise=100, method="card", school_id=sid)
    offer = PlanOffer(school_id=sid, name=f"{tag} offer", price_inr=1)
    problem = ProblemEvent(kind="error", summary=f"{tag} problem", school_id=sid)
    rule_event = RuleReadEvent(kind="read", text=f"{tag} rule text", school_id=sid)
    prospect = OutreachSchool(name=f"{tag} prospect")
    membership = SchoolMembership(school_id=sid, user_id=staff_id, role="viewer")
    db.add_all([requirement, block, entry, entry2, freeze, log, invite, order, invoice, offer, problem, rule_event,
                prospect, membership])
    db.flush()
    message = OutreachMessage(school_id=prospect.id, to_email="p@example.com", subject="Hi", body="Hi")
    db.add(message)
    db.flush()
    return {
        "school_id": sid, "class_group_id": section.id, "teacher_id": teacher.id, "subject_id": subject.id,
        "room_id": room.id, "period_id": period.id, "timetable_id": tt.id, "entry_id": entry.id,
        "other_entry_id": entry2.id, "block_id": block.id, "constraint_id": constraint.id,
        "requirement_id": requirement.id, "freeze_id": freeze.id, "invite_id": invite.id,
        "invoice_id": invoice.id, "order_id": order.order_id, "offer_id": offer.id, "problem_id": problem.id,
        "event_id": rule_event.id, "message_id": message.id, "user_id": staff_id,
        "elective_block_id": block.id, "elective_option_id": block.options[0].id, "log_id": log.id,
    }


@pytest.fixture
def two_schools(client):
    owner, owner_headers = signup(client, email="victim@example.com")
    victim = create_school(client, owner_headers, name="Victim School")["id"]
    intruder, headers = signup(client, email="intruder@example.com")
    own = create_school(client, headers, name="Intruder School")["id"]
    staff_user, viewer_headers = signup(client, email="staff-member@example.com")
    db = SessionLocal()
    try:
        ids = seed(db, victim, owner["id"], staff_user["id"], "Victim", "Susan")
        own_ids = seed(db, own, intruder["id"], staff_user["id"], "Intruder", "Ian")
        db.commit()
    finally:
        db.close()
    return {"ids": ids, "own_ids": own_ids, "headers": headers, "own_school": own, "viewer_headers": viewer_headers}


# Body fields that name a record, by the record they name.
ALIASES = {
    "absent_teacher_id": "teacher_id", "substituting_teacher_id": "teacher_id", "assistant_teacher_id": "teacher_id",
    "preferred_teacher_id": "teacher_id", "class_teacher_id": "teacher_id", "allowed_teacher_ids": "teacher_id",
    "from_period_id": "period_id", "to_period_id": "period_id", "period_ids": "period_id",
    "unavailable_period_ids": "period_id", "qualified_subject_ids": "subject_id", "subject_ids": "subject_id",
    "class_group_ids": "class_group_id", "section_ids": "class_group_id", "block_ids": "block_id",
    "school_ids": "school_id", "target_ids": "class_group_id",
}


def id_for(name, ids):
    key = ALIASES.get(name, name)
    if key.endswith("_ids"):
        key = key[:-1]
    return ids.get(key)


def example(schema, spec, ids, name="", depth=0):
    """A value for `schema` that names the other school's record wherever an id is asked for."""
    if "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].split("/")[-1]]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [s for s in schema[key] if s.get("type") != "null"]
            return example(options[0], spec, ids, name, depth) if options else None
    if "allOf" in schema:
        return example(schema["allOf"][0], spec, ids, name, depth)
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    kind = schema.get("type")
    if kind == "array":
        item = example(schema.get("items", {}), spec, ids, name, depth + 1)
        return [] if item is None else [item]
    if kind == "object" or "properties" in schema:
        if depth > 4:
            return {}
        return {k: example(v, spec, ids, k, depth + 1) for k, v in schema.get("properties", {}).items()}
    if re.search(r"(_id|_ids)$", name) and id_for(name, ids) is not None:
        return id_for(name, ids)
    if kind == "integer":
        return max(1, schema.get("minimum", 1))
    if kind == "number":
        return 1
    if kind == "boolean":
        return False
    if kind == "string":
        if schema.get("format") == "binary" or "contentMediaType" in schema:
            return b"x"
        if schema.get("format") == "date":
            return "2026-11-10"
        if "email" in name:
            return "someone@example.com"
        return "x" * max(1, schema.get("minLength", 1))
    return None


def routes():
    return [
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if path not in PUBLIC and path not in OWN_ACCOUNT
        for method in ops
    ]


def call(client, method, path, s, own_school=False):
    spec = app.openapi()
    op = spec["paths"][path][method.lower()]
    # Records named in the body and query are the other school's. The ones in
    # the path are too - unless acting on the caller's own school, when the
    # path names the caller's own records and only the rest are the other's.
    ids = dict(s["ids"])
    path_ids = s["own_ids"] if own_school else ids
    if own_school:
        ids["school_id"] = s["own_school"]
    url = path
    for name in re.findall(r"{(\w+)}", path):
        assert name in path_ids, f"{method} {path}: this test doesn't know which record a {name} is - add it to seed"
        url = url.replace("{" + name + "}", str(path_ids[name]))
    params = {}
    for prm in op.get("parameters", []):
        if prm["in"] != "query":
            continue
        value = id_for(prm["name"], ids) if prm["name"].endswith("id") else None
        if value is None and prm.get("required"):
            value = example(prm["schema"], spec, ids, prm["name"])
        if value is not None:
            params[prm["name"]] = value
    kwargs = {"params": params, "headers": s["headers"]}
    content = op.get("requestBody", {}).get("content", {})
    if "application/json" in content:
        kwargs["json"] = example(content["application/json"]["schema"], spec, ids)
    elif "multipart/form-data" in content:
        form = example(content["multipart/form-data"]["schema"], spec, ids)
        files = {k: ("upload.csv", b"name\nx\n") for k, v in form.items() if v == b"x"}
        kwargs["files"] = files
        kwargs["data"] = {k: v for k, v in form.items() if k not in files}
    return TestClient(app, raise_server_exceptions=False).request(method, url, **kwargs)


ROUTES = routes()
WRITES = {"POST", "PUT", "PATCH", "DELETE"}


def test_every_route_is_covered():
    assert len(ROUTES) > 140


def test_no_school_reaches_another_schools_records(client, two_schools):
    """One pass over every route - building the two schools once, not per
    route. Deletes go last, so a delete that wrongly works can't hide what the
    routes after it would have done."""
    spec = app.openapi()
    victim = two_schools["ids"]["school_id"]
    before = victim_rows(victim)
    leaks, accepted, crashes = [], [], []
    # Any reply, an error's included, that shows the other school's names.
    shows_victim = lambda r: "Victim" in r.text or "Susan" in r.text  # noqa: E731
    for method, path in sorted(ROUTES, key=lambda r: r[0] == "DELETE"):
        names_a_record = bool(re.search(r"{\w+}", path)) or "school_id" in str(spec["paths"][path][method.lower()])
        r = call(client, method, path, two_schools)
        if shows_victim(r) or (names_a_record and r.status_code not in REFUSED):
            leaks.append(f"{method} {path}: {r.status_code} {r.text[:160]}")
        # The caller's own records, naming the other school's alongside them.
        r = call(client, method, path, two_schools, own_school=True)
        if shows_victim(r):
            leaks.append(f"{method} {path} (own school): {r.status_code} {r.text[:160]}")
        elif r.status_code >= 500:
            crashes.append(f"{method} {path} (own school): {r.status_code}")
        elif r.status_code in range(200, 300) and method in WRITES:
            accepted.append(f"{method} {path}")
        crossed = crossed_links()
        if crossed:
            leaks.append(f"{method} {path} (own school): saved a link to the other school's records: {crossed}")
            break
    print("\nWrites accepted on the caller's own records:\n  " + "\n  ".join(accepted))
    print("\nServer errors (not access control):\n  " + "\n  ".join(crashes))
    assert not leaks, "\n".join(leaks)
    assert victim_rows(victim) == before, "the other school's records changed"


def victim_rows(school_id):
    """Every row of the school's, in every table that names its school."""
    db = SessionLocal()
    try:
        return {
            t.name: sorted(map(tuple, db.execute(t.select().where(t.c.school_id == school_id)).fetchall()), key=str)
            for t in Base.metadata.sorted_tables if "school_id" in t.c
        }
    finally:
        db.close()


# Lists of ids kept in one column, by the table they point into.
ID_LISTS = {
    "qualified_subject_ids": "subjects", "unavailable_period_ids": "periods", "allowed_teacher_ids": "teachers",
    "class_group_ids": "class_groups", "section_ids": "class_groups",
}


def crossed_links():
    """Rows of one school's that point at a row of another school's, through a
    foreign key or a list of ids."""
    db = SessionLocal()
    found = []
    try:
        school_of = {
            t.name: dict(db.execute(select(t.c.id, t.c.school_id)).fetchall())
            for t in Base.metadata.sorted_tables if "school_id" in t.c and "id" in t.c
        }
        for t in Base.metadata.sorted_tables:
            if "school_id" not in t.c or "id" not in t.c:
                continue
            for row in db.execute(t.select()).mappings():
                for col in t.c:
                    targets = [(fk.column.table.name, row[col.name]) for fk in col.foreign_keys]
                    if col.name in ID_LISTS and row[col.name]:
                        targets += [(ID_LISTS[col.name], i) for i in row[col.name]]
                    for table, ref in targets:
                        owner = school_of.get(table, {}).get(ref)
                        if table != "schools" and ref is not None and owner is not None and owner != row["school_id"]:
                            found.append(f"{t.name} {row['id']}.{col.name} -> {table} {ref}")
        return found
    finally:
        db.close()


# Writes a read-only member may still make: about themselves, not the school.
VIEWER_MAY = {
    ("POST", "/api/schools"),  # starting a school of their own
    ("POST", "/api/schools/{school_id}/support-snapshot"),  # asking support for help; changes nothing
}


def test_a_read_only_member_cant_change_the_school(client, two_schools):
    """A viewer of a school can read it but change nothing in it."""
    viewer = dict(two_schools, headers=two_schools["viewer_headers"])
    allowed = []
    for method, path in sorted(ROUTES, key=lambda r: r[0] == "DELETE"):
        if method not in WRITES or path.startswith("/api/admin") or (method, path) in VIEWER_MAY:
            continue
        r = call(client, method, path, viewer)
        if r.status_code in range(200, 300):
            allowed.append(f"{method} {path}: {r.status_code} {r.text[:120]}")
    assert not allowed, "\n".join(allowed)
