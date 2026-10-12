from typing import Literal

from pydantic import BaseModel, Field


class BreakSlot(BaseModel):
    # After which numbered period the break falls.
    after: int = Field(ge=1)
    label: str = Field(default="Break", min_length=1, max_length=40)


class ClassTeacherPeriodConfig(BaseModel):
    enabled: bool = False
    # 0 = start of the day; k = straight after period k.
    after: int = Field(default=0, ge=0)


class ZeroPlacement(BaseModel):
    """Where one grade's zero period falls (grade None = the whole school).

    Exactly one of the two: the same period every day, or a period per day.
    """

    grade: str | None = None
    every_day: int | None = Field(default=None, ge=1)
    by_day: dict[int, int] | None = None


class ZeroPeriodConfig(BaseModel):
    enabled: bool = False
    scope: Literal["school", "grade"] = "school"
    placements: list[ZeroPlacement] = []


class TimetableStructure(BaseModel):
    """A school's week, described once instead of period by period.

    Every working day gets `periods_per_day` periods, except any listed in
    `short_days`. Breaks, the class teacher period and the zero period are
    laid over that. See app/services/timetable_structure.py.
    """

    days: list[int]
    periods_per_day: int = Field(ge=1, le=16)
    short_days: dict[int, int] = {}
    breaks: list[BreakSlot] = []
    class_teacher_period: ClassTeacherPeriodConfig = ClassTeacherPeriodConfig()
    zero_period: ZeroPeriodConfig = ZeroPeriodConfig()


class StructureReport(BaseModel):
    """What applying a structure did, beyond the periods themselves - the
    things someone would otherwise discover later by surprise."""

    changed: bool
    periods_added: int = 0
    periods_removed: int = 0
    timetable_entries_removed: int = 0
    # "Mrs. Rao: 2 unavailable periods no longer exist"
    unavailability_removed: list[str] = []
    # Rules naming a period number no day has any more.
    rules_out_of_range: list[str] = []
    # Labels of sections with no class teacher, when the period is on.
    sections_without_class_teacher: list[str] = []
    # True when the structure changed after a timetable was generated for it.
    timetable_outdated: bool = False


class StructureOut(BaseModel):
    structure: TimetableStructure | None
    # The school's periods don't all follow one pattern (set up by hand before
    # this existed); saving will make every day follow the structure shown.
    irregular: bool = False


class StructureSaveOut(BaseModel):
    structure: TimetableStructure
    report: StructureReport
