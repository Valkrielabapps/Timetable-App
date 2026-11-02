"""
Where schools get stuck - for the Timetablz admin page, not for schools.

One row per moment a school hit a wall: a generation that found no
timetable, a move that couldn't be made, a setup-check problem, or a school
pressing "Send to Timetablz support". The admin page lists them so the
product can be fixed where many schools trip, not one school at a time. See
app/services/problem_log.py.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base

KINDS = ("generation_failed", "move_blocked", "setup_error", "support_request")
STATUSES = ("open", "fixed", "wont_fix", "school_setup")


class ProblemEvent(Base):
    __tablename__ = "problem_events"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(32), nullable=False, index=True)
    # One line, what the school saw ("Verma teaches Grade 11 B then").
    summary = Column(Text, nullable=False)
    detail = Column(JSON, nullable=True)
    timetable_id = Column(Integer, nullable=True)
    # The school's whole setup at that moment - periods, sections, subjects,
    # teachers, blocks, rules - so the problem can be reproduced after the
    # school has changed things. Kept for failed generations and support
    # requests, where that is the point.
    snapshot = Column(JSON, nullable=True)
    # open -> fixed (the product), school_setup (nothing wrong with the
    # product: the school's setup can't work), wont_fix.
    status = Column(String(16), nullable=False, default="open", index=True)
    note = Column(Text, nullable=True)
