from pydantic import BaseModel, ConfigDict, Field


class TeacherCreate(BaseModel):
    school_id: int
    name: str = Field(max_length=100)
    email: str | None = Field(default=None, max_length=200)
    qualified_subject_ids: list[int] = []
    # Empty = teaches every grade (no restriction) — see the model's
    # docstring for why this is the default rather than "qualifies for
    # nothing", unlike qualified_subject_ids.
    qualified_grades: list[str] = []
    unavailable_period_ids: list[int] = []
    max_periods_per_week: int | None = None
    is_assistant_eligible: bool = False


class TeacherUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    qualified_subject_ids: list[int] | None = None
    qualified_grades: list[str] | None = None
    unavailable_period_ids: list[int] | None = None
    max_periods_per_week: int | None = None
    is_assistant_eligible: bool | None = None


class TeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    name: str
    email: str | None
    qualified_subject_ids: list[int]
    # `| None` purely to tolerate existing rows from before this column
    # existed, whose value is NULL until the migration's ALTER TABLE ...
    # DEFAULT backfills them (see docs/GETTING_STARTED.md) — the frontend
    # already treats a missing/None value the same as an empty list.
    qualified_grades: list[str] | None = None
    unavailable_period_ids: list[int]
    max_periods_per_week: int | None
    is_assistant_eligible: bool
