"""
CRUD endpoints for schools — the first vertical slice through the stack
(router -> schema -> model -> database). Later routers for teachers,
class groups, subjects, rooms, and constraints follow this same pattern.

Schools are owned by a user (see owner_id on the School model): creating
one attaches the logged-in user as owner. Beyond the owner, a school can
now have additional admins/viewers via SchoolMembership (see
app/core/access.py and app/routers/invites.py for how those rows get
created) — list_schools and get_school both include schools the current
user has a membership in, not just ones they own. Every OTHER router
(subjects, teachers, timetables, etc.) now goes through
app.core.access.require_school_access too — this file used to be the only
one that checked ownership at all; that gap is closed as of this feature,
see docs/ARCHITECTURE.md for the full writeup.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.access import get_membership_role, require_school_access
from app.core.auth import get_current_user
from app.core.rate_limit import check_quota
from app.core.database import get_db
from app.models.school import ClassGroup, Period, School, SchoolInvite, SchoolMembership, Subject
from app.models.user import User
from app.schemas.membership import InviteCreate, InviteOut, MemberOut, MemberRoleUpdate
from app.schemas.school import (
    SchoolCreate,
    SchoolGradeDayLimitsUpdate,
    SchoolGradeOrderUpdate,
    SchoolInstitutionTypeUpdate,
    SchoolNameUpdate,
    SchoolOut,
    SchoolProfile,
    SchoolStandardRulesUpdate,
)
from app.services.email_service import send_invite_email
from app.services import plans, standard_rules

router = APIRouter(prefix="/api/schools", tags=["schools"])


def _school_out(school: School, role: str) -> SchoolOut:
    return SchoolOut(
        id=school.id, name=school.name, institution_type=school.institution_type,
        grade_order=school.grade_order, profile=school.profile, role=role,
        grade_day_limits=school.grade_day_limits,
        standard_rules=standard_rules.merged(school.standard_rules),
        plan=school.plan, plan_valid_until=school.plan_valid_until,
    )


@router.post("", response_model=SchoolOut, status_code=201)
def create_school(
    payload: SchoolCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plans.require_school_capacity(db, current_user.id)
    school = School(
        name=payload.name, owner_id=current_user.id, institution_type=payload.institution_type,
        free_trial_ends_at=plans.new_school_trial_end(),
    )
    db.add(school)
    db.commit()
    db.refresh(school)
    return _school_out(school, "admin")


@router.get("", response_model=list[SchoolOut])
def list_schools(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    owned = db.query(School).filter(School.owner_id == current_user.id).all()
    member_school_ids = [
        m.school_id
        for m in db.query(SchoolMembership).filter(SchoolMembership.user_id == current_user.id).all()
    ]
    member_schools = (
        db.query(School).filter(School.id.in_(member_school_ids)).all() if member_school_ids else []
    )
    # A user could in theory own AND have a stray membership row for the
    # same school; de-dupe by id rather than assume that can't happen.
    by_id = {s.id: s for s in owned + member_schools}
    return [
        _school_out(s, get_membership_role(db, current_user, s.id) or "viewer")
        for s in by_id.values()
    ]


@router.get("/{school_id}", response_model=SchoolOut)
def get_school(
    school_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = require_school_access(db, current_user, school_id)
    school = db.get(School, school_id)
    return _school_out(school, role)


@router.put("/{school_id}/grade-order", response_model=SchoolOut)
def update_grade_order(
    school_id: int, payload: SchoolGradeOrderUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Persists the sidebar's admin-customized grade display order — see
    School.grade_order's docstring. Full-replace (not a patch/reorder-one
    operation): the frontend always sends the complete new ordering, since
    that's simpler and less error-prone than the server reasoning about a
    partial move."""
    role = require_school_access(db, current_user, school_id, min_role="admin")
    school = db.get(School, school_id)
    school.grade_order = payload.grade_order
    db.commit()
    db.refresh(school)
    return _school_out(school, role)


@router.put("/{school_id}/grade-day-limits", response_model=SchoolOut)
def update_grade_day_limits(
    school_id: int, payload: SchoolGradeDayLimitsUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Shorter school days for some grades - see School.grade_day_limits.
    Full replace: the Setup editor always sends every rule."""
    role = require_school_access(db, current_user, school_id, min_role="admin")
    school = db.get(School, school_id)
    known = {g for (g,) in db.query(ClassGroup.grade).filter(ClassGroup.school_id == school_id).distinct() if g}
    lessons_per_day: dict[int, int] = {}
    for p in db.query(Period).filter(Period.school_id == school_id).all():
        if not p.is_break:
            lessons_per_day[p.day_of_week] = lessons_per_day.get(p.day_of_week, 0) + 1
    longest = max(lessons_per_day.values(), default=0)

    seen: set[str] = set()
    out = []
    for rule in payload.limits:
        grades = list(dict.fromkeys(g for g in rule.grades if g))
        if not grades:
            raise HTTPException(status_code=400, detail="Choose at least one grade for each shorter day.")
        unknown = [g for g in grades if g not in known]
        if unknown:
            raise HTTPException(status_code=400, detail=f"This school has no {', '.join(unknown)}.")
        twice = [g for g in grades if g in seen]
        if twice:
            raise HTTPException(status_code=400, detail=f"{', '.join(twice)} is in two shorter-day rules. Keep each grade in one.")
        seen.update(grades)
        counts = [rule.periods_per_day, *rule.by_day.values()]
        if any(n < 0 for n in counts) or rule.periods_per_day < 1:
            raise HTTPException(status_code=400, detail="A grade needs at least 1 period a day.")
        if longest and rule.periods_per_day >= longest and not rule.by_day:
            raise HTTPException(
                status_code=400,
                detail=f"The school day already has {longest} periods, so {rule.periods_per_day} isn't shorter.",
            )
        bad_days = [d for d in rule.by_day if d not in lessons_per_day]
        if bad_days:
            raise HTTPException(status_code=400, detail="A day was chosen that isn't a school day.")
        out.append({
            "grades": grades,
            "periods_per_day": rule.periods_per_day,
            "by_day": {str(d): n for d, n in sorted(rule.by_day.items())},
        })
    school.grade_day_limits = out or None
    db.commit()
    db.refresh(school)
    return _school_out(school, role)


@router.put("/{school_id}/standard-rules", response_model=SchoolOut)
def update_standard_rules(
    school_id: int, payload: SchoolStandardRulesUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Tick or untick the standard rules on the Constraints page, or change
    their numbers - see app/services/standard_rules.py."""
    role = require_school_access(db, current_user, school_id, min_role="admin")
    school = db.get(School, school_id)
    current = standard_rules.merged(school.standard_rules)
    for key, setting in payload.model_dump(exclude_none=True).items():
        if key in standard_rules.LIMITS and setting.get("value") is not None:
            lo, hi = standard_rules.LIMITS[key]
            if not lo <= setting["value"] <= hi:
                what = {"teacher_week_max": "periods a week", "teacher_day_max": "periods a day"}.get(key, "periods")
                raise HTTPException(status_code=400, detail=f"Choose between {lo} and {hi} {what}.")
            current[key]["value"] = setting["value"]
        current[key]["on"] = setting["on"]
        for k in ("include", "exclude"):
            if k in current[key] and setting.get(k) is not None:
                ids = set(setting[k])
                known = {i for (i,) in db.query(Subject.id).filter(Subject.school_id == school_id, Subject.id.in_(ids))}
                if ids - known:
                    raise HTTPException(status_code=400, detail="One of those subjects isn't in this school.")
                current[key][k] = sorted(ids)
    school.standard_rules = standard_rules.to_store(current)
    db.commit()
    db.refresh(school)
    return _school_out(school, role)


@router.put("/{school_id}/institution-type", response_model=SchoolOut)
def update_institution_type(
    school_id: int, payload: SchoolInstitutionTypeUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """
    Lets an admin fix a school's school-vs-college label after creation —
    previously this was only ever set once, in the create-school modal,
    with no way to change it (see docs/ARCHITECTURE.md's "School vs.
    college" section). Purely cosmetic, same as at creation time: this
    never gates or removes any existing data (class groups, lab-batch
    settings, credits) — it only changes which placeholder wording and
    which college-only fields the frontend shows going forward.
    """
    role = require_school_access(db, current_user, school_id, min_role="admin")
    school = db.get(School, school_id)
    school.institution_type = payload.institution_type
    db.commit()
    db.refresh(school)
    return _school_out(school, role)


@router.put("/{school_id}/name", response_model=SchoolOut)
def update_school_name(
    school_id: int, payload: SchoolNameUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Admin-only rename, from Settings > School profile. Before this the
    name could only be set once, in the create-school modal."""
    role = require_school_access(db, current_user, school_id, min_role="admin")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="School name can't be empty.")
    if len(name) > 120:
        raise HTTPException(status_code=422, detail="School name is too long (120 characters max).")
    school = db.get(School, school_id)
    school.name = name
    db.commit()
    db.refresh(school)
    return _school_out(school, role)


@router.put("/{school_id}/profile", response_model=SchoolOut)
def update_school_profile(
    school_id: int, payload: SchoolProfile,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Admin-only: replaces the descriptive profile (board, codes, head of
    institution, contact details, address...) from Settings > School
    profile. The form always sends every field, so this replaces the whole
    profile; blank strings are stored as missing rather than as "".
    """
    role = require_school_access(db, current_user, school_id, min_role="admin")
    cleaned = {}
    for key, value in payload.model_dump().items():
        if isinstance(value, str):
            value = value.strip() or None
        if value is not None:
            cleaned[key] = value
    school = db.get(School, school_id)
    school.profile = cleaned
    db.commit()
    db.refresh(school)
    return _school_out(school, role)


@router.get("/{school_id}/members", response_model=list[MemberOut])
def list_members(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Admin-only: the owner (synthesized — never has its own
    SchoolMembership row) plus every SchoolMembership row for this
    school."""
    require_school_access(db, current_user, school_id, min_role="admin")
    school = db.get(School, school_id)
    members = [MemberOut(user_id=school.owner.id, email=school.owner.email, name=school.owner.name, role="admin", is_owner=True)] if school.owner else []
    rows = db.query(SchoolMembership).filter(SchoolMembership.school_id == school_id).all()
    for m in rows:
        members.append(MemberOut(user_id=m.user.id, email=m.user.email, name=m.user.name, role=m.role, is_owner=False))
    return members


@router.patch("/{school_id}/members/{user_id}", response_model=MemberOut)
def update_member_role(
    school_id: int, user_id: int, payload: MemberRoleUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    require_school_access(db, current_user, school_id, min_role="admin")
    if payload.role not in ("admin", "viewer"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'viewer'")
    school = db.get(School, school_id)
    if school.owner_id == user_id:
        raise HTTPException(status_code=400, detail="The school owner's role can't be changed.")
    membership = (
        db.query(SchoolMembership)
        .filter(SchoolMembership.school_id == school_id, SchoolMembership.user_id == user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="This user isn't a member of this school.")
    membership.role = payload.role
    db.commit()
    db.refresh(membership)
    return MemberOut(user_id=membership.user.id, email=membership.user.email, name=membership.user.name, role=membership.role, is_owner=False)


@router.delete("/{school_id}/members/{user_id}", status_code=204)
def remove_member(
    school_id: int, user_id: int,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    require_school_access(db, current_user, school_id, min_role="admin")
    school = db.get(School, school_id)
    if school.owner_id == user_id:
        raise HTTPException(status_code=400, detail="The school owner can't be removed.")
    membership = (
        db.query(SchoolMembership)
        .filter(SchoolMembership.school_id == school_id, SchoolMembership.user_id == user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="This user isn't a member of this school.")
    db.delete(membership)
    db.commit()


@router.get("/{school_id}/invites", response_model=list[InviteOut])
def list_invites(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id, min_role="admin")
    return (
        db.query(SchoolInvite)
        .filter(SchoolInvite.school_id == school_id, SchoolInvite.status == "pending")
        .all()
    )


@router.post("/{school_id}/invites", response_model=InviteOut, status_code=201)
def create_invite(
    school_id: int, payload: InviteCreate,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """
    Admin-only. Attempts to send the invite by email via Resend (see
    app/services/email_service.py) if RESEND_API_KEY is configured;
    otherwise, and on any send failure, this silently no-ops on the email
    side — the invite is still created and its link is still included in
    the response (see api.js / TeamTab.jsx), so the admin always has a
    copyable fallback regardless of whether the email went out.
    """
    require_school_access(db, current_user, school_id, min_role="admin")
    if payload.role not in ("admin", "viewer"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'viewer'")
    # Each invite is an email from our sender to an address someone typed, so
    # it is capped like any other way of sending mail: a school adds a few
    # colleagues, not hundreds.
    check_quota(f"invite:{current_user.id}", limit=20, window_seconds=3600)
    check_quota(f"invite-school:{school_id}", limit=50, window_seconds=86400)
    plans.require_member_capacity(db, db.get(School, school_id))
    existing_pending = (
        db.query(SchoolInvite)
        .filter(SchoolInvite.school_id == school_id, SchoolInvite.email == payload.email, SchoolInvite.status == "pending")
        .first()
    )
    if existing_pending:
        raise HTTPException(status_code=400, detail="There's already a pending invite for this email.")
    invite = SchoolInvite(
        school_id=school_id,
        email=payload.email,
        role=payload.role,
        token=secrets.token_urlsafe(32),
        invited_by_user_id=current_user.id,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    school = db.get(School, school_id)
    invite.email_sent = send_invite_email(
        to_email=invite.email,
        school_name=school.name if school else "your school",
        inviter_name=current_user.name or current_user.email,
        role=invite.role,
        invite_token=invite.token,
    )
    return invite


@router.delete("/{school_id}/invites/{invite_id}", status_code=204)
def revoke_invite(
    school_id: int, invite_id: int,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    require_school_access(db, current_user, school_id, min_role="admin")
    invite = db.get(SchoolInvite, invite_id)
    if not invite or invite.school_id != school_id:
        raise HTTPException(status_code=404, detail="Invite not found")
    invite.status = "revoked"
    db.commit()
