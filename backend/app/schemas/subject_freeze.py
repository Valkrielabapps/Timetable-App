"""Freezing a subject's lessons - see app/services/subject_freezing.py."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SubjectFreezeCreate(BaseModel):
    school_id: int
    subject_id: int
    # The whole school, some grades (`grades`) or some sections (`class_group_ids`).
    scope: Literal["school", "grades", "sections"] = "school"
    grades: list[str] | None = None
    class_group_ids: list[int] | None = None
    # In an elective block: just this subject, or every subject in the block.
    block_mode: Literal["subject", "block"] = "subject"


class SubjectFreezeOut(BaseModel):
    id: int
    subject_id: int
    subject: str
    scope: str
    # "Whole school", "Grade 9, Grade 10", "Grade 11 - A, Grade 11 - B"
    scope_label: str
    grades: list[str] | None = None
    class_group_ids: list[int]
    section_count: int
    block_mode: str
    # Whether the subject is in an elective block anywhere it's frozen - only
    # then does block_mode mean anything.
    in_blocks: bool
    frozen_at: datetime
    # "Version 3 (Grades 1-5 approved)"
    frozen_from: str | None = None
    frozen_from_timetable_id: int
    # Why it no longer matches the plan; empty when it's fine. Generating
    # stops until an out-of-date subject is unfrozen.
    stale_reasons: list[str]
    # Fine, but worth knowing - extra periods placed around the frozen ones.
    notes: list[str]
