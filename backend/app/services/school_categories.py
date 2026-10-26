"""
The parts of a school - pre-primary, primary, middle, high school - that
substitutions are arranged by.

Many schools run each part from its own building or block, so cover is
arranged a part at a time: the teacher covering a Grade 3 lesson should
ideally be someone already working in the primary block.

Each grade belongs to one part. By default that is read from the grade's
name - "Nursery", "LKG", "UKG" are pre-primary; Grades 1-5 primary; 6-8
middle; 9-12 high school (secondary and senior secondary together) - and a
school can change any of them in Settings, which is stored as an override
per grade. A grade the defaults can't place ("Foundation", say) has no part
until the school gives it one; it still appears in whole-school summaries.
"""
from __future__ import annotations

import re

CATEGORIES: list[tuple[str, str]] = [
    ("pre_primary", "Pre-primary"),
    ("primary", "Primary"),
    ("middle", "Middle"),
    ("high", "High school"),
]
CATEGORY_KEYS = {key for key, _ in CATEGORIES}
CATEGORY_LABELS = dict(CATEGORIES)

_PRE_PRIMARY = re.compile(
    r"\b(nursery|pre[\s-]?(primary|nursery|school|kg|k)|lkg|ukg|kg|kindergarten|play\s*group|playgroup|pg|"
    r"montessori|toddler)\b",
    re.IGNORECASE,
)
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
          "xi": 11, "xii": 12}


def _grade_number(grade: str) -> int | None:
    """The number in a grade's name: "Grade 6", "Class VI", "6th", "Std 6"."""
    text = grade.strip().lower()
    digits = re.search(r"\d+", text)
    if digits:
        return int(digits.group())
    for word in re.split(r"[\s\-_.]+", text):
        if word in _ROMAN:
            return _ROMAN[word]
    return None


def default_category(grade: str | None) -> str | None:
    """Which part a grade belongs to, read from its name. None if unclear."""
    if not grade:
        return None
    if _PRE_PRIMARY.search(grade):
        return "pre_primary"
    n = _grade_number(grade)
    if n is None:
        return None
    if 1 <= n <= 5:
        return "primary"
    if 6 <= n <= 8:
        return "middle"
    if 9 <= n <= 12:
        return "high"
    return None


def category_of(grade: str | None, overrides: dict | None) -> str | None:
    """The school's choice for a grade if it made one, else the default."""
    if grade and overrides and grade in overrides:
        value = overrides[grade]
        return value if value in CATEGORY_KEYS else None
    return default_category(grade)
