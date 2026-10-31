"""
Sales outreach to schools - Timetablz's own pipeline, run from the admin page.

Nothing here belongs to a customer school. These are schools Timetablz wants
to sell to: who they are, who to write to, every email drafted and sent, and
where each one stands. Only platform admins can see any of it (see
app/routers/outreach.py).

  OutreachSchool    a school on the list, with its contacts and status
  OutreachMessage   one email to one school - a draft, approved, sent, ...
  OutreachSettings  one row: templates, sending limits, the connected mailbox
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


def _now():
    return datetime.now(timezone.utc)


# Where a school is in the pipeline. The first four move on their own as
# emails go out and replies come in; the rest are set by hand.
STATUSES = (
    "not_contacted", "emailed", "replied", "bounced", "opted_out",
    "demo_booked", "trial", "paid", "not_interested",
)


class OutreachSchool(Base):
    __tablename__ = "outreach_schools"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    district = Column(String, nullable=True)
    area = Column(String, nullable=True)
    board = Column(String, nullable=True)
    classes_up_to = Column(String, nullable=True)
    school_type = Column(String, nullable=True)
    priority = Column(String, nullable=True)
    group_name = Column(String, nullable=True)
    website = Column(String, nullable=True)
    # Published addresses, best first. The one emails go to is `to_email`
    # when set, otherwise the first of these.
    emails = Column(JSON, nullable=True)
    to_email = Column(String, nullable=True)
    email_source = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    principal_name = Column(String, nullable=True)
    contact_name = Column(String, nullable=True)
    contact_role = Column(String, nullable=True)
    contact_source = Column(String, nullable=True)
    contacts_checked_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="not_contacted")
    notes = Column(Text, nullable=True)
    next_step = Column(String, nullable=True)
    next_date = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    @property
    def recipient(self) -> str | None:
        if self.to_email:
            return self.to_email
        return (self.emails or [None])[0]


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("outreach_schools.id", ondelete="CASCADE"), nullable=False, index=True)
    # 1 = the first email, 2 and 3 = follow-ups in the same thread.
    step = Column(Integer, nullable=False, default=1)
    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    # draft -> approved -> sent; or cancelled (a reply came, the school opted
    # out, a follow-up's email bounced) or failed (the mailbox refused it).
    status = Column(String, nullable=False, default="draft", index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    # Follow-ups wait until this time; the first email can go any time.
    not_before = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    provider_message_id = Column(String, nullable=True)
    provider_thread_id = Column(String, nullable=True)
    rfc_message_id = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)


class OutreachSettings(Base):
    __tablename__ = "outreach_settings"

    id = Column(Integer, primary_key=True)
    sender_name = Column(String, nullable=True)
    signature = Column(Text, nullable=True)
    # {"1": {"subject": ..., "body": ...}, "2": {...}, "3": {...}}
    templates = Column(JSON, nullable=True)
    daily_limit = Column(Integer, nullable=False, default=15)
    # Days after the previous email that each follow-up waits.
    follow_up_days = Column(JSON, nullable=True)
    # Sending only happens when this is on - off until someone turns it on.
    sending_enabled = Column(Boolean, nullable=False, default=False)
    # Gmail connection (OAuth). The refresh token is the mailbox's key.
    gmail_address = Column(String, nullable=True)
    gmail_refresh_token = Column(Text, nullable=True)
    last_reply_check_at = Column(DateTime(timezone=True), nullable=True)
    first_sent_at = Column(DateTime(timezone=True), nullable=True)
