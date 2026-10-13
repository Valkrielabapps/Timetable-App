"""
GET /api/plans                          public catalogue (pricing page)
GET /api/schools/{school_id}/entitlements  the school's plan, status and usage

Both read app/services/plans.py, which is the only place limits are defined.
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.school import School
from app.models.user import User
from app.services import plans

router = APIRouter(tags=["plans"])


@router.get("/api/plans")
def list_plans():
    return {
        "grace_days": plans.GRACE_DAYS,
        "plans": [asdict(p) for p in plans.catalogue().values()],
    }


@router.get("/api/schools/{school_id}/entitlements")
def school_entitlements(
    school_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_school_access(db, current_user, school_id)
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    ent = plans.entitlements(db, school)
    pro = plans.get_plan("pro")
    return {**ent.as_dict(), "pro_price_inr": pro.price_inr, "grace_days": plans.GRACE_DAYS}
