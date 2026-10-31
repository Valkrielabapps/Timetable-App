from pydantic import BaseModel, ConfigDict, Field


class SubjectCreate(BaseModel):
    school_id: int
    name: str = Field(max_length=100)
    required_room_type: str | None = None
    credits: int | None = None
    lab_batch_count: int | None = None


class SubjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    required_room_type: str | None = None
    credits: int | None = None
    lab_batch_count: int | None = None


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    name: str
    required_room_type: str | None
    credits: int | None = None
    lab_batch_count: int | None = None
