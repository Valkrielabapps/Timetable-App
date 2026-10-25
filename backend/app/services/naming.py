"""
Sorting people by name, never by title.

Mirrors frontend/src/sorting.js, so a teacher is in the same place in an
export as on screen: "Mrs. Rao" under R, not in a block with every other
"Mrs." at M. Titles arrive however a school typed them, so all of these are
ignored, with or without a full stop, and more than one in a row.
"""
import re

_TITLE = re.compile(r"^\s*(mr|mrs|ms|miss|mx|dr|prof|professor)\.?(\s+|$)", re.IGNORECASE)


def without_title(name: str | None) -> str:
    original = (name or "").strip()
    rest = original
    while True:
        stripped = _TITLE.sub("", rest, count=1)
        if stripped == rest:
            break
        rest = stripped
    # A name that is nothing but a title is still a name.
    return rest.strip() or original


def name_sort_key(name: str | None) -> list:
    """Alphabetical, titles ignored, capitals ignored, numbers as numbers."""
    bare = without_title(name)
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", bare)]
