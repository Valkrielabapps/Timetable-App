"""
Which part of the school - pre-primary, primary, middle, high school - each
grade belongs to, for arranging substitutions a block at a time. The
defaults come from the grade's name (app/services/school_categories.py);
a school changes them here, in Settings.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.school import ClassGroup, School
from app.models.user import User
from app.schemas.substitutions import GradeCategoriesUpdate, GradeCategoryOut
from app.services.naming import name_sort_key
from app.services.school_categories import CATEGORY_KEYS, category_of, default_category

router = APIRouter(prefix="/api/schools", tags=["grade-categories"])


def _grade_categories(db: Session, school_id: int) -> list[dict]:
    school = db.get(School, school_id)
    overrides = school.grade_categories or {}
    grades = {
        cg.grade for cg in db.query(ClassGroup).filter(ClassGroup.school_id == school_id) if cg.grade
    }
    return [
        {"grade": g, "category": category_of(g, overrides), "default": default_category(g)}
        for g in sorted(grades, key=name_sort_key)
    ]


@router.get("/{school_id}/grade-categories", response_model=List[GradeCategoryOut])
def get_grade_categories(
    school_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every grade the school has, with its part of the school."""
    require_school_access(db, current_user, school_id)
    return _grade_categories(db, school_id)


@router.put("/{school_id}/grade-categories", response_model=List[GradeCategoryOut])
def save_grade_categories(
    school_id: int,
    data: GradeCategoriesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set the part of the school for each grade. Only the grades that
    differ from their default are stored, so a grade put back to its default
    follows the defaults again."""
    require_school_access(db, current_user, school_id, min_role="admin")
    for grade, category in data.categories.items():
        if category is not None and category not in CATEGORY_KEYS:
            raise HTTPException(status_code=422, detail=f"Unknown part of the school for {grade}: {category!r}.")
    school = db.get(School, school_id)
    school.grade_categories = {
        grade: category for grade, category in data.categories.items() if category != default_category(grade)
    } or None
    db.commit()
    return _grade_categories(db, school_id)
