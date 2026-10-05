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
from app.core.database import get_db
from app.models.school import School, SchoolInvite, SchoolMembership
from app.models.user import User
from app.schemas.membership import InviteCreate, InviteOut, MemberOut, MemberRoleUpdate
from app.schemas.school import (
    SchoolCreate,
    SchoolGradeOrderUpdate,
    SchoolInstitutionTypeUpdate,
    SchoolNameUpdate,
    SchoolOut,
    SchoolProfile,
)
from app.services.email_service import send_invite_email

router = APIRouter(prefix="/api/schools", tags=["schools"])


def _school_out(school: School, role: str) -> SchoolOut:
    return SchoolOut(
        id=school.id, name=school.name, institution_type=school.institution_type,
        grade_order=school.grade_order, profile=school.profile, role=role,
    )


@router.post("", response_model=SchoolOut, status_code=201)
def create_school(
    payload: SchoolCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    school = School(name=payload.name, owner_id=current_user.id, institution_type=payload.institution_type)
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
