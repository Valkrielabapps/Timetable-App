from pydantic import BaseModel, ConfigDict, Field


class ElectiveOptionIn(BaseModel):
    """One teaching group of a block.

    `class_group_ids`: which of the block's sections this group's students
    come from. Left out (or null) means all of them.
    `label`: tells two groups of one subject apart ("Group 1", "Group 2").
    """

    subject_id: int
    preferred_teacher_id: int | None = None
    class_group_ids: list[int] | None = None
    label: str | None = Field(default=None, max_length=40)


class ElectiveBlockCreate(BaseModel):
    """A block of subjects studied at the same time, each student taking one.

    Options are sent with the block rather than added one at a time, because
    the validity rules (no subject twice for the same students, none shared
    with a section's common subjects, every section covered) are about the set
    as a whole.

    `section_ids` makes the block span several sections - every section in it
    is free at the same moment and its students go to the groups. Left out, the
    block is for `class_group_id` alone, as blocks always used to be.
    """

    school_id: int
    class_group_id: int
    name: str = Field(min_length=1, max_length=60)
    periods_per_week: int = Field(ge=1, le=60)
    options: list[ElectiveOptionIn]
    section_ids: list[int] | None = None


class ElectiveBlockUpdate(BaseModel):
    """Replaces whatever is sent. `options`, when present, is the full new set;
    so is `section_ids`."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    periods_per_week: int | None = Field(default=None, ge=1, le=60)
    options: list[ElectiveOptionIn] | None = None
    section_ids: list[int] | None = None


class ElectiveOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    preferred_teacher_id: int | None
    class_group_ids: list[int] | None = None
    label: str | None = None


class ElectiveBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    class_group_id: int
    name: str
    periods_per_week: int
    section_ids: list[int]
    options: list[ElectiveOptionOut]
