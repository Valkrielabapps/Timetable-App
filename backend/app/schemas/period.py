from pydantic import BaseModel, ConfigDict


class PeriodCreate(BaseModel):
    school_id: int
    day_of_week: int  # 0 = Monday ... 6 = Sunday
    order: int  # position within the day, e.g. 1st period, 2nd period
    label: str | None = None  # e.g. "9:00-9:45", "Lunch"
    # True for a slot nothing is ever scheduled into (lunch, assembly).
    is_break: bool = False


class PeriodUpdate(BaseModel):
    day_of_week: int | None = None
    order: int | None = None
    label: str | None = None
    is_break: bool | None = None


class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    day_of_week: int
    order: int
    label: str | None
    is_break: bool
