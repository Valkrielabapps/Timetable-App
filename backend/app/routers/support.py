"""
Support tickets from the floating help button in the app.

There is no ticket table: a ticket is an email to the support inbox
(settings.support_email) with the user's address as Reply-To, so it is
answered from the inbox like any other email. That is enough for the
number of schools this serves today; a table and an admin view can come
later if tickets ever need tracking.

If the email can't be sent (no RESEND_API_KEY, or Resend rejects it) this
returns 503 and the frontend shows the support address to write to
directly. Saying "sent" when nothing went out would leave a school waiting
on a reply that is never coming.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import check_quota
from app.models.school import School
from app.models.user import User
from app.services.email_service import send_support_ticket

router = APIRouter(prefix="/api/support", tags=["support"])

CATEGORIES = {"question", "problem", "feature", "billing", "other"}


class SupportTicketIn(BaseModel):
    category: str = "question"
    subject: str = Field(min_length=1, max_length=150)
    message: str = Field(min_length=1, max_length=5000)
    # Optional: which school the user was looking at, so the ticket says so.
    school_id: int | None = None


@router.post("/tickets", status_code=202)
def create_ticket(
    payload: SupportTicketIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Each ticket is a real email to a human inbox; this keeps a stuck
    # form or a script from flooding it.
    check_quota(f"support-ticket:{current_user.id}", limit=5, window_seconds=3600)

    subject = payload.subject.strip()
    message = payload.message.strip()
    if not subject or not message:
        raise HTTPException(status_code=422, detail="Please add a subject and a message.")
    category = payload.category if payload.category in CATEGORIES else "other"

    school_name = None
    if payload.school_id is not None:
        # Only name a school the user actually belongs to; anything else
        # is ignored rather than rejected, since it's just context.
        try:
            require_school_access(db, current_user, payload.school_id, min_role="viewer")
            school = db.get(School, payload.school_id)
            school_name = school.name if school else None
        except HTTPException:
            school_name = None

    sent = send_support_ticket(
        from_email=current_user.email,
        from_name=current_user.name,
        school_name=school_name,
        category=category,
        subject=subject,
        message=message,
    )
    if not sent:
        raise HTTPException(
            status_code=503,
            detail=f"We couldn't send your ticket right now. Please email {settings.support_email} directly.",
        )
    return {"sent": True}
