"""Record what happens when a sentence is read into a rule.

Everything the rule parser gets wrong in real use shows up as one of these:
a line handed back unread, a reading the admin cancelled or reworded, a rule
deleted minutes after it was saved, a saved rule the timetable can't apply.
The Timetablz admin page lists them (GET /api/admin/rule-events) so each can be
sorted into what needs fixing - the prompt, the rule checker, a new kind of
rule, or a better question.

Strictly on the side. Written in its own database session, so a failure here
can't roll back or block the rule being saved, and every error is swallowed
after being logged. Nothing in the app reads these rows back.
"""
import logging

from app.core.database import SessionLocal
from app.models.school import RuleReadEvent

logger = logging.getLogger(__name__)

KINDS = (
    "interpreted", "unclear", "invalid", "confirmed", "cancelled", "reworded",
    "batch_unread", "not_applied", "quick_delete",
)
TRIAGE = ("misread", "checker", "unsupported", "ambiguous", "fine")
# A rule deleted this soon after it was saved was most likely not what the
# admin meant.
QUICK_DELETE_MINUTES = 30
_MAX_TEXT = 2000


def record(kind: str, text: str | None, *, school_id: int | None = None, user_id: int | None = None,
           detail: dict | None = None, constraint_id: int | None = None) -> None:
    if kind not in KINDS or not (text or "").strip():
        return
    db = None
    try:
        db = SessionLocal()
        db.add(RuleReadEvent(
            kind=kind, text=text.strip()[:_MAX_TEXT], school_id=school_id, user_id=user_id,
            detail=detail or None, constraint_id=constraint_id,
        ))
        db.commit()
    except Exception:  # noqa: BLE001 - never let logging break the real request
        logger.exception("could not record rule event %s", kind)
        if db is not None:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
    finally:
        if db is not None:
            db.close()
