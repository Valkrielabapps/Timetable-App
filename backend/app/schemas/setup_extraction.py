from pydantic import BaseModel


class ExtractedTeacher(BaseModel):
    name: str
    email: str | None = None
    subject_names: list[str] = []


class ExtractedSubject(BaseModel):
    name: str


class ExtractedClassGroup(BaseModel):
    name: str
    grade: str | None = None


class SetupExtractionPreview(BaseModel):
    """
    Result of POST /schools/{id}/setup-extraction — nothing has been
    created in the database yet. The admin reviews this (deselecting or
    editing items in the frontend) and POSTs the reviewed version to
    /commit to actually create rows. See app/services/setup_extractor.py
    for why this is a separate, freeform-input path from bulk_import.py.
    """

    teachers: list[ExtractedTeacher]
    subjects: list[ExtractedSubject]
    class_groups: list[ExtractedClassGroup]
    notes: str = ""


class SetupExtractionCommit(BaseModel):
    """
    The admin-reviewed subset of a SetupExtractionPreview to actually
    create. Same shape as the preview minus `notes` — the frontend
    starts from the preview response, lets the admin remove/edit items,
    and posts back what's left.
    """

    teachers: list[ExtractedTeacher] = []
    subjects: list[ExtractedSubject] = []
    class_groups: list[ExtractedClassGroup] = []


class SetupExtractionCommitOut(BaseModel):
    """Mirrors BulkImportOut but summed across all three entity types,
    since one commit can create/update a mix of teachers, subjects, and
    class groups at once."""

    subjects_created: int
    subjects_updated: int
    teachers_created: int
    teachers_updated: int
    class_groups_created: int
    class_groups_updated: int
    errors: list[str]
