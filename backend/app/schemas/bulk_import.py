from pydantic import BaseModel


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
