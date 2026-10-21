from typing import Literal

from pydantic import BaseModel, ConfigDict

PeriodKind = Literal["lesson", "break", "class_teacher", "zero"]


class PeriodCreate(BaseModel):
    school_id: int
    day_of_week: int  # 0 = Monday ... 6 = Sunday
    order: int  # position within the day, e.g. 1st period, 2nd period
    label: str | None = None  # e.g. "9:00-9:45", "Lunch"
    kind: PeriodKind | None = None
    # Older form of kind="break", still accepted.
    is_break: bool = False


class PeriodUpdate(BaseModel):
    day_of_week: int | None = None
    order: int | None = None
    label: str | None = None
    kind: PeriodKind | None = None
    is_break: bool | None = None


class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    day_of_week: int
    order: int
    label: str | None
    kind: str = "lesson"
    # True for every kind that is not a lesson: nothing is timetabled there.
    is_break: bool
    # "Period 3" - the lesson's number in its day. None for breaks, the class
    # teacher period and a school-wide zero period, which sit between numbers.
    number: int | None = None
    # Zero periods kept on this lesson slot: for the whole school, and/or for
    # these grades. Sections in them have no lesson here.
    zero_all: bool = False
    zero_grades: list[str] = []
    # Grades whose school day has ended by this slot (School.grade_day_limits).
    off_grades: list[str] = []
