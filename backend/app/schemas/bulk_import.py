from pydantic import BaseModel, Field


class BulkImportOut(BaseModel):
    """Result of one bulk-import upload - see app/services/bulk_import.py.
    Shared across the subjects/rooms/teachers/class-groups routers since
    they all report the same shape."""

    created: int
    updated: int
    errors: list[str]
    # How a school's own sheet was read (subjects and teachers - see
    # app/services/smart_import.py): which sheet, and each heading as what.
    sheet: str | None = None
    read_as: list[str] = []
    # Values read as something else: "“Maths” as Mathematics", "“IX” as Grade 9".
    matched: list[str] = []
    # Subjects a teacher sheet named that didn't exist yet, now added.
    new_subjects: list[str] = []


class BulkPreviewOut(BaseModel):
    """A school's own sheet as it would be saved - nothing saved yet. See
    app/services/smart_import.py:build_preview."""

    kind: str
    total: int
    subject_count: int
    will_update: int
    rows: list[dict[str, str]]
    # Per row: doubtful readings ("“Comp Sci” → Computer Science?") and
    # what the checks found ("No subjects").
    row_notes: list[list[str]]
    sheet: str | None = None
    read_as: list[str] = []
    matched: list[str] = []
    doubtful: list[str] = []
    checks: list[str] = []
    new_subjects: list[str] = []


class BulkCommitIn(BaseModel):
    """The previewed rows, saved as shown."""

    school_id: int
    rows: list[dict[str, str]] = Field(max_length=5000)
