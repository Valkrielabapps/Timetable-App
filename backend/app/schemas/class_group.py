from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ClassGroupCreate(BaseModel):
    school_id: int
    grade: str | None = None
    name: str
    student_count: int | None = None


class ClassGroupUpdate(BaseModel):
    grade: str | None = None
    name: str | None = None
    student_count: int | None = None
    # Sent as null to clear it.
    class_teacher_id: int | None = None


class ClassGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    grade: str | None
    name: str
    student_count: int | None
    class_teacher_id: int | None = None
    frozen: bool = False


class FreezeRequest(BaseModel):
    school_id: int
    class_group_ids: list[int]
    frozen: bool


class FrozenStatusOut(BaseModel):
    """Whether a section is frozen and, if so, whether it is out of date - see
    app/services/freezing.py."""

    class_group_id: int
    frozen: bool
    frozen_at: datetime | None = None
    # Why a frozen section no longer matches what it was built from; None
    # when it is fine or not frozen.
    stale_reason: str | None = None


class SubjectRequirementCreate(BaseModel):
    class_group_id: int
    subject_id: int
    periods_per_week: int
    preferred_teacher_id: int | None = None
    assistant_teacher_id: int | None = None
    allowed_teacher_ids: list[int] | None = None


class SubjectRequirementUpdate(BaseModel):
    periods_per_week: int | None = None
    preferred_teacher_id: int | None = None
    assistant_teacher_id: int | None = None
    allowed_teacher_ids: list[int] | None = None


class SubjectRequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    class_group_id: int
    subject_id: int
    periods_per_week: int
    preferred_teacher_id: int | None
    assistant_teacher_id: int | None
    allowed_teacher_ids: list[int] | None = None
