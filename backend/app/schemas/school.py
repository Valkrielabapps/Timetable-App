"""Pydantic schemas for School — what the API accepts/returns, separate from
the SQLAlchemy model that defines what the database stores."""
from pydantic import BaseModel, ConfigDict, Field


class SchoolCreate(BaseModel):
    name: str
    # "school" or "college", chosen in the create-school modal. Not
    # validated against a strict enum here — the frontend only ever sends
    # one of the two, and treating anything else as "school" (see
    # institution_type's docstring on the model) is a safer default than
    # a 422 on a typo'd value from some future caller.
    institution_type: str | None = None


class SchoolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    institution_type: str | None = None
    # `| None` purely to tolerate rows from before this column existed,
    # same reasoning as Teacher.qualified_grades — the frontend already
    # treats a missing/None value the same as an empty list.
    grade_order: list[str] | None = None
    profile: dict | None = None
    # The current user's role for THIS school specifically ("admin" or
    # "viewer") — not a column on the School model, computed per-request
    # by whichever router endpoint builds this (see app/core/access.py).
    # Lets the frontend gate write UI (hide "Add", "Generate", etc. for a
    # viewer) without a separate round-trip to find out.
    role: str = "admin"


class SchoolGradeOrderUpdate(BaseModel):
    grade_order: list[str]


class SchoolInstitutionTypeUpdate(BaseModel):
    # Same "not a strict enum" reasoning as SchoolCreate.institution_type —
    # the frontend only ever sends "school" or "college".
    institution_type: str | None = None


class SchoolNameUpdate(BaseModel):
    name: str


class SchoolProfile(BaseModel):
    """Everything in Settings > School profile apart from name and type.

    All optional, all free text with length caps (plus a month number), so
    a school can fill in as much or as little as it likes. Unknown keys are
    dropped rather than stored, so the JSON column can't fill up with junk.
    """

    model_config = ConfigDict(extra="ignore")

    board: str | None = Field(default=None, max_length=80)
    affiliation_number: str | None = Field(default=None, max_length=60)
    udise_code: str | None = Field(default=None, max_length=30)
    established_year: int | None = Field(default=None, ge=1800, le=2100)
    head_name: str | None = Field(default=None, max_length=100)
    head_title: str | None = Field(default=None, max_length=60)
    medium: str | None = Field(default=None, max_length=60)
    academic_year_start_month: int | None = Field(default=None, ge=1, le=12)
    student_count: int | None = Field(default=None, ge=0, le=100000)
    website: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, max_length=80)
    postal_code: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=1000)
