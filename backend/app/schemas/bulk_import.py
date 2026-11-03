from pydantic import BaseModel


class BulkImportOut(BaseModel):
    """Result of one bulk-import upload - see app/services/bulk_import.py.
    Shared across the subjects/rooms/teachers/class-groups routers since
    they all report the same shape."""

    created: int
    updated: int
    errors: list[str]
