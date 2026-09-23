"""
Public, token-based invite endpoints — deliberately separate from
schools.py's admin-only member/invite management, since the person
using these two endpoints (someone who just clicked an invite link) isn't
authenticated yet and shouldn't need to be to find out what the invite is
for. The token itself (a 32-byte random string, see
SchoolInvite.token / schools.create_invite) is the only credential these
need; anyone without it can't look anything up, and it's long enough that
guessing one isn't practical.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.core.auth import create_access_token, hash_password, verify_password
from app.core.database import get_db
from app.models.school import School, SchoolInvite, SchoolMembership
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.membership import AcceptInviteRequest, InvitePreviewOut

router = APIRouter(prefix="/api/invites", tags=["invites"])


@router.get("/{token}", response_model=InvitePreviewOut)
@limiter.limit("30/hour")
def preview_invite(request: Request, token: str, db: Session = Depends(get_db)):
    invite = db.query(SchoolInvite).filter(SchoolInvite.token == token).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    school = db.get(School, invite.school_id)
    return InvitePreviewOut(
        email=invite.email,
        role=invite.role,
        school_name=school.name if school else "Unknown school",
        status=invite.status,
    )


@router.post("/{token}/accept", response_model=TokenResponse)
# An invite token is unguessable, but this endpoint also verifies a password
# for an existing account - so without a limit it is a second login endpoint
# with no throttling on it.
@limiter.limit("20/hour")
def accept_invite(request: Request, token: str, payload: AcceptInviteRequest, db: Session = Depends(get_db)):
    """
    Accepting always requires a password — either to set one for a
    brand-new account (invite.email has never signed up: `name` and
    `password` create the account) or to confirm an existing account's
    password (invite.email already has a User row: `password` must match
    it). This is what stops the invite link alone — which could leak via
    a forwarded email, a screenshot, etc. — from being enough to log into
    somebody's existing account; see AcceptInviteRequest's docstring.

    Returns a real access token either way, so the frontend can drop the
    invitee straight into the app instead of making them log in again
    right after.
    """
    invite = db.query(SchoolInvite).filter(SchoolInvite.token == token, SchoolInvite.status == "pending").first()
    if not invite:
        raise HTTPException(status_code=404, detail="This invite is invalid or has already been used.")

    existing = db.query(User).filter(User.email == invite.email).first()
    if existing:
        if not existing.hashed_password or not verify_password(payload.password, existing.hashed_password):
            raise HTTPException(
                status_code=401,
                detail="An account with this email already exists — enter its password to accept.",
            )
        user = existing
    else:
        if not payload.name or not payload.password:
            raise HTTPException(status_code=400, detail="name and password are required to create your account.")
        user = User(email=invite.email, hashed_password=hash_password(payload.password), name=payload.name)
        db.add(user)
        db.commit()
        db.refresh(user)

    membership = (
        db.query(SchoolMembership)
        .filter(SchoolMembership.school_id == invite.school_id, SchoolMembership.user_id == user.id)
        .first()
    )
    if membership:
        membership.role = invite.role  # re-accepting a fresh invite upgrades/downgrades to its role
    else:
        db.add(SchoolMembership(school_id=invite.school_id, user_id=user.id, role=invite.role))

    invite.status = "accepted"
    db.commit()

    token_str = create_access_token(user.id)
    return TokenResponse(access_token=token_str, user=user)
