"""
The Timetablz admin page's API - for Timetablz staff (PLATFORM_ADMIN_EMAILS),
not for school admins.

    GET    /api/admin/schools                     every school, its plan and status
    POST   /api/admin/schools/{id}/offers         make a custom offer to a school
    DELETE /api/admin/offers/{id}                 withdraw an open offer
    POST   /api/admin/schools/{id}/mark-paid      record a bank transfer / cheque
    POST   /api/admin/schools/{id}/extend-free    add days to the free period
    POST   /api/admin/schools/{id}/downgrade      end a paid plan (after a refund)
    GET    /api/admin/invoices                    recent invoices
    GET    /api/admin/stats                       dashboard totals
    GET    /api/admin/rule-events                 rules the parser struggled with
    PATCH  /api/admin/rule-events/{id}            file one into what needs fixing

Granting a plan and issuing the invoice go through app/services/billing.py,
the same functions a Cashfree payment uses.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.payment import Invoice, PlanOffer
from app.models.school import School
from app.models.user import User
from app.routers.plans import invoice_out, offer_out
from app.services import billing, plans

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_platform_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_platform_admin:
        # 404 rather than 403: the admin API shouldn't advertise itself.
        raise HTTPException(status_code=404, detail="Not found")
    return current_user


def _school_or_404(db: Session, school_id: int) -> School:
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    return school


def _naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------


@router.get("/schools")
def list_schools(
    q: str | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    query = db.query(School)
    if q:
        query = query.filter(School.name.ilike(f"%{q.strip()}%"))
    schools = query.order_by(School.id.desc()).limit(200).all()
    owners = {u.id: u for u in db.query(User).filter(User.id.in_([s.owner_id for s in schools if s.owner_id])).all()}
    offers = {
        o.school_id: o
        for o in db.query(PlanOffer).filter(PlanOffer.status == "open", PlanOffer.school_id.in_([s.id for s in schools])).all()
    }
    out = []
    for s in schools:
        ent = plans.entitlements(db, s)
        owner = owners.get(s.owner_id)
        out.append({
            "id": s.id,
            "name": s.name,
            "owner_email": owner.email if owner else None,
            "owner_name": owner.name if owner else None,
            "plan": ent.plan,
            "plan_name": ent.plan_name,
            "paid_plan": ent.paid_plan,
            "status": ent.status,
            "plan_valid_until": ent.plan_valid_until,
            "free_trial_ends_at": ent.free_trial_ends_at,
            "free_days_left": ent.free_days_left,
            "sections": ent.usage["sections"],
            "members": ent.usage["members"],
            "limits": ent.limits,
            "open_offer": offer_out(offers[s.id]) if s.id in offers else None,
        })
    return out


class OfferIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    price_inr: int = Field(ge=1, le=10_000_000)
    period_days: int = Field(default=365, ge=1, le=1830)
    # null = unlimited
    max_sections: int | None = Field(default=None, ge=1, le=100_000)
    max_members: int | None = Field(default=None, ge=1, le=10_000)
    max_owned_schools: int | None = Field(default=None, ge=1, le=1_000)
    note: str | None = Field(default=None, max_length=2000)


@router.post("/schools/{school_id}/offers", status_code=201)
def create_offer(
    school_id: int,
    payload: OfferIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    _school_or_404(db, school_id)
    # One open offer per school: a new one replaces the old.
    for old in db.query(PlanOffer).filter(PlanOffer.school_id == school_id, PlanOffer.status == "open").all():
        old.status = "cancelled"
    offer = PlanOffer(school_id=school_id, created_by_user_id=admin.id, status="open", **payload.model_dump())
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer_out(offer)


@router.delete("/offers/{offer_id}", status_code=204)
def cancel_offer(offer_id: int, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    offer = db.get(PlanOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.status != "open":
        raise HTTPException(status_code=409, detail="Only an open offer can be withdrawn.")
    offer.status = "cancelled"
    db.commit()


class MarkPaidIn(BaseModel):
    # "pro" for a Pro year, or "offer" to settle the school's open custom offer.
    kind: str = Field(pattern="^(pro|offer)$")
    amount_inr: int = Field(ge=1, le=10_000_000)
    method: str = Field(default="bank_transfer", pattern="^(bank_transfer|other)$")
    reference: str | None = Field(default=None, max_length=100)


@router.post("/schools/{school_id}/mark-paid")
def mark_paid(
    school_id: int,
    payload: MarkPaidIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    """Record money received outside Cashfree. Grants the plan and issues the
    invoice exactly as an online payment would."""
    school = _school_or_404(db, school_id)
    offer = None
    if payload.kind == "offer":
        offer = (
            db.query(PlanOffer)
            .filter(PlanOffer.school_id == school_id, PlanOffer.status == "open")
            .order_by(PlanOffer.id.desc())
            .first()
        )
        if offer is None:
            raise HTTPException(status_code=409, detail="This school has no open offer.")
        plan_id, period_days = "business", offer.period_days
    else:
        plan_id, period_days = "pro", 365

    period = billing.grant_plan(db, school, plan_id, period_days, offer=offer)
    db.commit()
    invoice = billing.issue_invoice(
        db, school,
        description=f"{billing.plan_label(plan_id, offer)}, {period_days} days",
        amount_paise=payload.amount_inr * 100,
        method=payload.method,
        reference=payload.reference,
        period=period,
    )
    return {"plan_valid_until": school.plan_valid_until, "invoice": invoice_out(invoice)}


class ExtendFreeIn(BaseModel):
    days: int = Field(ge=1, le=365)


@router.post("/schools/{school_id}/extend-free")
def extend_free(
    school_id: int,
    payload: ExtendFreeIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    """Add days to the free period, counted from whichever is later: today or
    the current end (so it also unlocks a school whose free days ran out)."""
    school = _school_or_404(db, school_id)
    now = _naive_now()
    base = school.free_trial_ends_at if school.free_trial_ends_at and school.free_trial_ends_at > now else now
    school.free_trial_ends_at = base + timedelta(days=payload.days)
    db.commit()
    return {"free_trial_ends_at": school.free_trial_ends_at}


@router.post("/schools/{school_id}/downgrade")
def downgrade(school_id: int, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    """End the paid plan now, e.g. after a refund. The school goes back to its
    free period if any is left, otherwise it's locked. Nothing is deleted;
    issued invoices stay."""
    school = _school_or_404(db, school_id)
    school.plan = None
    school.plan_valid_until = None
    school.custom_limits = None
    school.custom_plan_name = None
    db.commit()
    return {"status": plans.effective_plan(school)[1]}


@router.get("/invoices")
def recent_invoices(db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    rows = db.query(Invoice).order_by(Invoice.id.desc()).limit(100).all()
    names = {s.id: s.name for s in db.query(School).filter(School.id.in_([i.school_id for i in rows])).all()}
    return [{**invoice_out(i), "school_name": names.get(i.school_id)} for i in rows]


@router.get("/stats")
def stats(db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    """Headline numbers for the admin dashboard."""
    from sqlalchemy import func

    now = datetime.now(timezone.utc)
    by_status = {"free": 0, "active": 0, "grace": 0, "locked": 0}
    by_plan = {"pro": 0, "business": 0}
    ending_soon = 0
    for s in db.query(School).all():
        plan, status, _ = plans.effective_plan(s, now)
        by_status[status] = by_status.get(status, 0) + 1
        if status in ("active", "grace") and s.plan in by_plan:
            by_plan[s.plan] += 1
        if status == "free":
            left = plans.entitlements(db, s, now).free_days_left
            if left is not None and left <= 3:
                ending_soon += 1
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    total = db.query(func.coalesce(func.sum(Invoice.amount_paise), 0)).scalar() or 0
    this_month = (
        db.query(func.coalesce(func.sum(Invoice.amount_paise), 0)).filter(Invoice.issued_at >= month_start).scalar() or 0
    )
    return {
        "schools": sum(by_status.values()),
        "accounts": db.query(User).count(),
        "by_status": by_status,
        "paying": by_plan,
        "free_ending_within_3_days": ending_soon,
        "open_offers": db.query(PlanOffer).filter(PlanOffer.status == "open").count(),
        "revenue_total_inr": total / 100,
        "revenue_this_month_inr": this_month / 100,
        "invoices": db.query(Invoice).count(),
    }


@router.get("/accounts")
def accounts(
    q: str | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    """Every user account and the schools it can open (owned or invited)."""
    from app.models.school import SchoolMembership

    query = db.query(User)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((User.email.ilike(like)) | (User.name.ilike(like)))
    users = query.order_by(User.id.desc()).limit(300).all()
    ids = [u.id for u in users]
    owned: dict[int, list[str]] = {}
    for s in db.query(School).filter(School.owner_id.in_(ids)).all():
        owned.setdefault(s.owner_id, []).append(s.name)
    member: dict[int, list[str]] = {}
    rows = (
        db.query(SchoolMembership.user_id, SchoolMembership.role, School.name)
        .join(School, School.id == SchoolMembership.school_id)
        .filter(SchoolMembership.user_id.in_(ids))
        .all()
    )
    for user_id, role, name in rows:
        member.setdefault(user_id, []).append(f"{name} ({role})")
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "google": bool(u.google_sub),
            "owns": owned.get(u.id, []),
            "member_of": member.get(u.id, []),
        }
        for u in users
    ]


# ---------------------------------------------------------------------------
# How well rules are being read (see app/services/rule_events.py)
# ---------------------------------------------------------------------------

# The moments that point at something to fix. "interpreted" and "confirmed"
# are the successes, counted in the summary but not listed by default.
_PROBLEM_KINDS = ("unclear", "invalid", "cancelled", "reworded", "batch_unread", "not_applied", "quick_delete")


@router.get("/rule-events")
def rule_events_list(
    kind: str | None = None,
    triage: str | None = None,
    q: str | None = None,
    days: int = 30,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    """Rule-reading moments worth looking at, newest first, plus totals.

    `kind=all` includes the successes too. `triage=none` is what hasn't been
    looked at yet."""
    from app.models.school import RuleReadEvent

    since = _naive_now() - timedelta(days=max(1, min(days, 365)))
    base = db.query(RuleReadEvent).filter(RuleReadEvent.created_at >= since)
    counts: dict[str, int] = {}
    for k, n in (
        db.query(RuleReadEvent.kind, func.count(RuleReadEvent.id))
        .filter(RuleReadEvent.created_at >= since)
        .group_by(RuleReadEvent.kind)
        .all()
    ):
        counts[k] = n

    query = base
    if kind and kind != "all":
        query = query.filter(RuleReadEvent.kind == kind)
    elif not kind:
        query = query.filter(RuleReadEvent.kind.in_(_PROBLEM_KINDS))
    if triage == "none":
        query = query.filter(RuleReadEvent.triage.is_(None))
    elif triage:
        query = query.filter(RuleReadEvent.triage == triage)
    if q:
        query = query.filter(RuleReadEvent.text.ilike(f"%{q.strip()}%"))
    rows = query.order_by(RuleReadEvent.id.desc()).limit(300).all()
    names = {s.id: s.name for s in db.query(School).filter(School.id.in_({r.school_id for r in rows if r.school_id})).all()}

    interpreted = counts.get("interpreted", 0)
    return {
        "counts": counts,
        # Of the sentences the parser read into a rule, how many the admin kept.
        "confirmed_share": round(counts.get("confirmed", 0) / interpreted, 3) if interpreted else None,
        "events": [
            {
                "id": r.id, "created_at": r.created_at.isoformat() if r.created_at else None,
                "kind": r.kind, "text": r.text, "detail": r.detail or {},
                "school_id": r.school_id, "school_name": names.get(r.school_id),
                "constraint_id": r.constraint_id, "triage": r.triage,
            }
            for r in rows
        ],
    }


class _TriageIn(BaseModel):
    # None clears it.
    triage: str | None = Field(default=None, pattern="^(misread|checker|unsupported|ambiguous|fine)$")


@router.patch("/rule-events/{event_id}")
def rule_event_triage(
    event_id: int, payload: _TriageIn,
    db: Session = Depends(get_db), admin: User = Depends(require_platform_admin),
):
    """File one moment into what needs fixing - the prompt (misread), the rule
    checker, a new kind of rule (unsupported), a better question (ambiguous) -
    or mark it as nothing wrong."""
    from app.models.school import RuleReadEvent

    row = db.get(RuleReadEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    row.triage = payload.triage
    db.commit()
    return {"id": row.id, "triage": row.triage}
