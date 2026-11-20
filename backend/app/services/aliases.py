"""
Short forms a school has confirmed once, read by every importer.

A school writes "MAT", "BEAUL" and "2LN" in its sheets. The first time an
importer has to ask what one means, the answer is kept here (per school),
and from then on the timetable import, the subject and teacher imports and
the rules page all read it without asking again.

Kept apart from the built-in short forms in smart_import (SST, EVS, SUPW,
...), which every school shares: only what this school confirmed, and that
the built-in list doesn't already know, is stored.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.school import SchoolAlias, Subject, Teacher

KINDS = ("subject", "teacher")


def _key(text: str) -> str:
    from app.services.smart_import import _key as k
    return k(text or "")[:100]


def _built_in_knows(text: str, meaning: str) -> bool:
    """The shared list already reads `text` as `meaning` ("Maths" as
    Mathematics), so storing it would only clutter the school's list."""
    from app.services.smart_import import _SUBJECT_ALIASES, _concept
    return _key(text) in _SUBJECT_ALIASES and _concept(text) == _concept(meaning)


def remember(db: Session, school_id: int, kind: str, text: str, meaning: str,
             target_id: int | None = None, source: str | None = None) -> SchoolAlias | None:
    """Keep "text means meaning" for this school. The latest confirmation
    wins. Nothing is kept for a text that is the name itself, or that the
    built-in list already reads the same way. The caller commits."""
    text, meaning = (text or "").strip()[:100], (meaning or "").strip()[:100]
    key = _key(text)
    if kind not in KINDS or not key or not meaning or key == _key(meaning):
        return None
    if kind == "subject" and _built_in_knows(text, meaning):
        return None
    row = (db.query(SchoolAlias)
           .filter(SchoolAlias.school_id == school_id, SchoolAlias.kind == kind, SchoolAlias.key == key).first())
    if row is None:
        # Pending in this session (two answers about one short form): reuse it.
        row = next((o for o in db.new if isinstance(o, SchoolAlias) and o.school_id == school_id
                    and o.kind == kind and o.key == key), None)
    if row is None:
        row = SchoolAlias(school_id=school_id, kind=kind, key=key)
        db.add(row)
    row.text, row.meaning, row.target_id, row.source = text, meaning, target_id, source or row.source
    return row


def remember_many(db: Session, school_id: int, items: list[dict], source: str | None = None) -> int:
    """[{kind, text, meaning}] from an import's confirmed answers."""
    ids = {k: {n.strip().lower(): i for i, n in _current_names(db, school_id, k).items()} for k in KINDS}
    n = 0
    for it in (items or [])[:500]:
        if not isinstance(it, dict):
            continue
        kind, meaning = str(it.get("kind") or ""), str(it.get("meaning") or "")
        target = ids.get(kind, {}).get(meaning.strip().lower())
        if remember(db, school_id, kind, str(it.get("text") or ""), meaning, target_id=target, source=source):
            n += 1
    return n


def for_school(db: Session, school_id: int) -> dict[str, dict[str, str]]:
    """Both kinds at once, as smart_import.smart_rows takes them."""
    return {k: lookup(db, school_id, k) for k in KINDS}


def _current_names(db: Session, school_id: int, kind: str) -> dict[int, str]:
    model = Subject if kind == "subject" else Teacher
    return {i: n for i, n in db.query(model.id, model.name).filter(model.school_id == school_id)}


def lookup(db: Session | None, school_id: int | None, kind: str) -> dict[str, str]:
    """{key: name} for one kind. A confirmed target that was renamed gives
    its new name; one that was deleted gives the name as confirmed."""
    if db is None or not school_id:
        return {}
    rows = db.query(SchoolAlias).filter(SchoolAlias.school_id == school_id, SchoolAlias.kind == kind).all()
    if not rows:
        return {}
    names = _current_names(db, school_id, kind) if any(r.target_id for r in rows) else {}
    return {r.key: names.get(r.target_id, r.meaning) for r in rows}


def meaning_of(aliases: dict[str, str], text: str) -> str | None:
    return aliases.get(_key(text)) if aliases else None


def listing(db: Session, school_id: int) -> list[dict]:
    rows = (db.query(SchoolAlias).filter(SchoolAlias.school_id == school_id)
            .order_by(SchoolAlias.kind, SchoolAlias.text).all())
    names = {k: _current_names(db, school_id, k) for k in KINDS}
    return [{"id": r.id, "kind": r.kind, "text": r.text, "meaning": names[r.kind].get(r.target_id, r.meaning),
             "source": r.source} for r in rows]


def forget(db: Session, school_id: int, alias_id: int) -> bool:
    row = db.query(SchoolAlias).filter(SchoolAlias.id == alias_id, SchoolAlias.school_id == school_id).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
