from typing import Any

from pydantic import BaseModel, ConfigDict


class ConstraintCreate(BaseModel):
    school_id: int
    type: str
    parameters: dict[str, Any] = {}
    is_hard: bool = True
    weight: int = 1
    description: str | None = None


class ConstraintUpdate(BaseModel):
    type: str | None = None
    parameters: dict[str, Any] | None = None
    is_hard: bool | None = None
    weight: int | None = None
    description: str | None = None


class ConstraintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    type: str
    parameters: dict[str, Any]
    is_hard: bool
    weight: int
    description: str | None
    # What the admin typed, and which parser read it. Exposed so the
    # "which phrasings are we failing to understand" question can be
    # answered from the API rather than needing database access.
    source_text: str | None = None
    parsed_by: str | None = None
    # Whether this specific constraint row is actually applied by the
    # solver (not just "is this type supported in general" — e.g. an
    # availability constraint with no matched teacher/day is still
    # recorded but not enforced). Computed from `parameters`, not stored,
    # so the UI can be honest without a DB column to keep in sync.
    enforced: bool = False
    # Human-readable warnings about this constraint contradicting another
    # one already saved — see _find_placement_conflicts in
    # app/routers/constraints.py. Informational, not blocking: a
    # contradictory constraint is still saved (the solver will just end up
    # unable to satisfy it), so the admin can see and fix it rather than
    # the save silently succeeding with no way to know something's wrong.
    conflicts: list[str] = []


class ConstraintParseRequest(BaseModel):
    school_id: int
    text: str


class ConstraintBatchParseRequest(BaseModel):
    """See POST /api/constraints/batch — same idea as ConstraintParseRequest
    but `text` can contain several rules at once (one per line, or a
    paragraph naming multiple rules) instead of exactly one."""

    school_id: int
    text: str


class ConstraintReparseRequest(BaseModel):
    """Re-parses new text into an EXISTING constraint row (same id),
    instead of creating a new one — see PUT /api/constraints/{id}/reparse.
    Lets an admin fix a typo or reword a rule without losing its identity
    (and without a stray delete+recreate in the UI's list ordering)."""

    text: str


class ConstraintParseResponse(BaseModel):
    constraint: ConstraintOut
    # True if this constraint is actually enforced by the solver (currently
    # only workload_limit constraints with a matched teacher are). Lets the
    # UI be honest about which parsed rules actually affect generation.
    enforced: bool
