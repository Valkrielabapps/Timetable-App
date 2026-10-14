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
from fastapi.responses import Response

from app.models.payment import Invoice, PlanOffer
from app.models.school import School
from app.models.user import User
from app.services import billing, plans

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
    offer = (
        db.query(PlanOffer)
        .filter(PlanOffer.school_id == school_id, PlanOffer.status == "open")
        .order_by(PlanOffer.id.desc())
        .first()
    )
    return {
        **ent.as_dict(),
        "pro_price_inr": pro.price_inr,
        "grace_days": plans.GRACE_DAYS,
        "offer": offer_out(offer) if offer else None,
    }


def offer_out(o: PlanOffer) -> dict:
    return {
        "id": o.id, "school_id": o.school_id, "name": o.name, "price_inr": o.price_inr,
        "period_days": o.period_days, "max_sections": o.max_sections, "max_members": o.max_members,
        "max_owned_schools": o.max_owned_schools, "note": o.note, "status": o.status,
        "created_at": o.created_at, "paid_at": o.paid_at,
    }


def invoice_out(i: Invoice) -> dict:
    return {
        "id": i.id, "number": i.number, "school_id": i.school_id, "description": i.description,
        "amount": i.amount_paise / 100, "currency": i.currency, "method": i.method,
        "reference": i.reference, "issued_at": i.issued_at,
        "period_start": i.period_start, "period_end": i.period_end,
    }


@router.get("/api/schools/{school_id}/invoices")
def school_invoices(
    school_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_school_access(db, current_user, school_id)
    rows = db.query(Invoice).filter(Invoice.school_id == school_id).order_by(Invoice.id.desc()).all()
    return [invoice_out(i) for i in rows]


@router.get("/api/invoices/{invoice_id}/pdf")
def invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if not current_user.is_platform_admin:
        require_school_access(db, current_user, invoice.school_id)
    return Response(
        content=billing.invoice_pdf(invoice),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{invoice.number}.pdf"'},
    )
