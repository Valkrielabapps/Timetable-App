"""Pydantic schemas for SubstitutionLog — see app/models/school.py's
SubstitutionLog docstring for what this feature is (a same-day manual
substitution record, not something the solver reads)."""
from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class SubstitutionChange(BaseModel):
    period_id: int
    absent_teacher_id: int
    # None when nobody was found to cover it - kept, so the summary can say
    # "not covered" instead of the lesson silently disappearing.
    substituting_teacher_id: int | None = None
    class_group_id: int
    subject_id: int | None = None
    # The part of the school the lesson is in; filled in when saved.
    category: str | None = None


class Absence(BaseModel):
    teacher_id: int
    # None = away the whole day; otherwise the periods they're away for.
    period_ids: list[int] | None = None


class SubstitutionLogCreate(BaseModel):
    # The day the cover is for. Older clients sent only the weekday.
    date: date_type | None = None
    day_of_week: int | None = None
    # "primary" etc., or None for the whole school.
    category: str | None = None
    absences: list[Absence] = []
    changes: list[SubstitutionChange]

    @model_validator(mode="after")
    def _needs_a_day(self):
        if self.date is None and self.day_of_week is None:
            raise ValueError("Say which day the substitutions are for.")
        return self


class SubstitutionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    day_of_week: int
    date: date_type | None = None
    category: str | None = None
    absences: list[Absence] | None = None
    created_at: datetime
    changes: list[SubstitutionChange]


class SummaryLeave(BaseModel):
    teacher_id: int
    teacher: str
    # None = the whole day; otherwise the period numbers they're away for.
    periods: list[str] | None = None


class SummaryRow(BaseModel):
    period: str
    class_group: str
    subject: str | None
    category: str | None
    category_label: str
    absent_teacher: str
    # None = not covered.
    substitute: str | None


class SubstitutionSummaryOut(BaseModel):
    """One day's cover, for a part of the school or all of it - what the
    screen shows, what the PDF prints and what gets copied to WhatsApp."""

    date: date_type
    weekday: str
    category: str | None
    category_label: str
    on_leave: list[SummaryLeave]
    rows: list[SummaryRow]
    uncovered: int


class GradeCategoryOut(BaseModel):
    grade: str
    category: str | None
    # What the grade's name alone would give - shown so a change can be undone.
    default: str | None


class GradeCategoriesUpdate(BaseModel):
    # {grade: category or None}; a grade left out goes back to its default.
    categories: dict[str, str | None]
