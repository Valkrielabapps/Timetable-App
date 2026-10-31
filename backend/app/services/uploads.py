"""
Limits on uploaded spreadsheets (bulk import, AI setup extraction).

Without them an upload was read whole into memory, and an .xlsx - a zip
file - could unpack to many times its size: one request could exhaust the
server's memory and take every school offline with it. The limits are far
beyond any real staff list or timetable: a school's whole setup is a few
hundred rows.
"""
from __future__ import annotations

import io
import zipfile

from fastapi import HTTPException, UploadFile

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# What an .xlsx may unpack to, all its parts together.
MAX_UNZIPPED_BYTES = 50 * 1024 * 1024
# Rows read from any spreadsheet; anything past this is refused, not cut.
MAX_ROWS = 5000


async def read_upload(file: UploadFile) -> bytes:
    """The uploaded file's bytes, refusing anything over MAX_UPLOAD_BYTES
    without reading the rest of it."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is too big - upload one under 5 MB.")
    return content


def check_xlsx(content: bytes) -> None:
    """Raise ValueError if an .xlsx isn't a real one, or would unpack to
    more than MAX_UNZIPPED_BYTES. Read from the zip's own directory, before
    anything is decompressed."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            total = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile:
        raise ValueError("That file isn't a valid .xlsx spreadsheet.") from None
    if total > MAX_UNZIPPED_BYTES:
        raise ValueError("That spreadsheet is too big to read - split it into smaller files.")


def capped(rows, limit: int = MAX_ROWS):
    """The rows of a sheet, refusing one with more than `limit`."""
    out = []
    for row in rows:
        if len(out) >= limit + 1:  # the header row plus `limit` rows of data
            raise ValueError(f"That file has more than {limit} rows - split it into smaller files.")
        out.append(row)
    return out
