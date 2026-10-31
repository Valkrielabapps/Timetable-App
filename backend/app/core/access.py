"""
School-membership access control — the fix for a real gap that existed
until now: every router except schools.py took a bare `school_id` (or a
resource id it belongs to) and trusted it completely, with no check that
the logged-in user actually had anything to do with that school. Any
authenticated user could read or write any other school's data just by
changing an id in the request.

This module is deliberately plain functions called explicitly inside each
endpoint, not a single FastAPI `Depends()` — because school_id shows up in
three different shapes across the existing routers (a query param on list
endpoints, a body field on create endpoints, or not at all on
get/update/delete endpoints that only take a resource id and need it
looked up from the fetched row first). A single dependency can't cleanly
cover all three without a bigger refactor of every endpoint's signature,
so `require_school_access` takes school_id as a plain argument and each
router calls it wherever it already has that id in hand.

Role model: two tiers. "admin" can do everything a school's owner could;
"viewer" can only read. The school's owner (School.owner_id) is always an
implicit admin, so a freshly created school with no SchoolMembership rows
at all still works exactly as before this feature existed — memberships
only matter for *additional* users beyond the owner.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.school import School, SchoolMembership
from app.models.user import User

_ROLE_RANK = {"viewer": 0, "admin": 1}


def get_membership_role(db: Session, user: User, school_id: int) -> str | None:
    """None if the user has no access to this school at all; otherwise
    "admin" or "viewer".

    One query, not two: this used to be `db.get(School, ...)` followed by
    a separate `SchoolMembership` query when the user wasn't the owner —
    correct, but every request pays that as a sequential extra round trip
    to the database purely for an access check, on top of whatever the
    endpoint itself needs to do. The outer join resolves both the school's
    owner_id and (if any) this user's membership role in a single round
    trip; which one wins is then just a Python comparison.
    """
    row = (
        db.query(School.owner_id, SchoolMembership.role)
        .outerjoin(
            SchoolMembership,
            (SchoolMembership.school_id == School.id) & (SchoolMembership.user_id == user.id),
        )
        .filter(School.id == school_id)
        .first()
    )
    if row is None:
        return None
    owner_id, membership_role = row
    if owner_id == user.id:
        return "admin"
    return membership_role


def require_school_access(
    db: Session, user: User, school_id: int, min_role: str = "viewer", allow_locked: bool = False,
) -> str:
    """
    Raises 404 (not 403) when the user has no access at all — same
    reasoning as schools.py's existing get_school check: a school you
    can't see shouldn't even reveal that it exists via a different error
    code. Raises 403 when the user has *some* access but not enough (a
    viewer hitting a write endpoint) — that one *should* say "you don't
    have permission" rather than pretend the school doesn't exist, since
    the user can already see it elsewhere in the UI.

    Returns the resolved role so a caller can use it further (e.g. to
    decide whether to include admin-only fields in a response).
    """
    role = get_membership_role(db, user, school_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    if _ROLE_RANK[role] < _ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You have read-only access to this school — an admin can make this change.",
        )
    # A school whose free days (or paid plan's grace period) are over is
    # locked: it can still be read, but nothing can be changed until it pays
    # (app/services/plans.py). Every write goes through here as min_role
    # "admin", which makes this the one place to enforce it. The payment
    # endpoint passes allow_locked=True, since paying is how a school unlocks.
    if min_role == "admin" and not allow_locked:
        from app.services import plans

        school = db.get(School, school_id)
        if school is not None and plans.is_locked(school):
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=plans.LOCKED_MESSAGE)
    return role


def require_in_school(db: Session, model, ids, school_id: int, what: str) -> None:
    """Every id given must be a row of this school's.

    Checking that the user may act on a school isn't enough on its own when
    the request also names other rows - a teacher for a lesson, a subject for
    a section. Without this, an admin of one school could point their own
    records at another school's teacher and read that teacher's name back in
    the response. Raises 404 (not 403), so an id from another school looks
    exactly like one that doesn't exist.

    `ids` may be one id, a list, or None; Nones are skipped.
    """
    if ids is None:
        return
    wanted = {i for i in (ids if isinstance(ids, (list, tuple, set)) else [ids]) if i is not None}
    if not wanted:
        return
    found = {i for (i,) in db.query(model.id).filter(model.id.in_(wanted), model.school_id == school_id)}
    if found != wanted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")
