from pydantic import BaseModel, ConfigDict, Field


class ElectiveOptionIn(BaseModel):
    subject_id: int
    preferred_teacher_id: int | None = None


class ElectiveBlockCreate(BaseModel):
    """A block of subjects one section studies simultaneously.

    Options are sent with the block rather than added one at a time, because a
    block with one option is not a block - it is a normal subject - and the
    validity rules (no subject twice, none shared with the section's common
    subjects) are about the set as a whole.
    """

    school_id: int
    class_group_id: int
    name: str = Field(min_length=1, max_length=60)
    periods_per_week: int = Field(ge=1, le=60)
    options: list[ElectiveOptionIn]


class ElectiveBlockUpdate(BaseModel):
    """Replaces whatever is sent. `options`, when present, is the full new set."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    periods_per_week: int | None = Field(default=None, ge=1, le=60)
    options: list[ElectiveOptionIn] | None = None


class ElectiveOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    preferred_teacher_id: int | None


class ElectiveBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    class_group_id: int
    name: str
    periods_per_week: int
    options: list[ElectiveOptionOut]
