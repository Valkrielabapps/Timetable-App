"""
Plan purchases through Cashfree's hosted web checkout.

Flow (https://www.cashfree.com/docs/payments/online/web/redirect):

  1. POST /api/payments/create-order   (school admin, signed in)
     Saves a PENDING PaymentOrder, creates the order at Cashfree, and returns
     only {order_id, payment_session_id} - the browser needs nothing else to
     open checkout, and never sees the amount as something it can change.
  2. The frontend opens Cashfree checkout with that session id. When the
     customer finishes, Cashfree sends them to
     FRONTEND_BASE_URL/?page=payment-status&order_id=...
  3. GET /api/payments/orders/{order_id}  (that page polls this)
     Asks Cashfree for the order (Get Order API) and applies the result.
  4. POST /api/payments/webhook  (Cashfree -> us, server to server)
     Signature-checked, then the order is re-fetched from Cashfree and the
     same update applied - so a customer who closes the tab before the
     redirect still gets their plan.

The plan is granted in exactly one place, _apply_cashfree_status, and only
when Cashfree's own order_status is PAID and the amount matches what we
charged. PAID is terminal and the grant happens inside the same transaction
as the PENDING -> PAID transition, so the verify poll and the webhook racing
each other (or a webhook delivered twice) grant the plan once.
"""
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import check_quota
from app.models.payment import PaymentOrder
from app.models.school import School
from app.models.user import User
from app.services import cashfree_service as cashfree
from app.services import plans

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])

# Plan -> (price in rupees, how long one payment lasts). Only Pro is sold
# online; Business is "talk to us".
PLAN_DAYS = {"pro": 365}

# Cashfree order_status -> ours. ACTIVE means "no successful payment yet",
# which is still pending from the customer's point of view.
_STATUS_MAP = {
    "PAID": "PAID",
    "ACTIVE": "PENDING",
    "EXPIRED": "EXPIRED",
    "TERMINATED": "FAILED",
    "TERMINATION_REQUESTED": "FAILED",
}


def _price_rupees(plan: str) -> int:
    p = plans.get_plan(plan)
    if p.id != plan or not p.sold_online or not p.price_inr:
        raise HTTPException(status_code=422, detail="That plan can't be bought online.")
    return p.price_inr


def _require_configured():
    if not cashfree.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Online payments aren't set up yet. Please contact support@timetablz.com to upgrade.",
        )


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateOrderIn(BaseModel):
    school_id: int
    plan: str = "pro"
    # Cashfree requires a phone number for every order. Ten digits, Indian
    # mobile, optionally written with +91 / 0 / spaces / dashes.
    phone: str = Field(min_length=10, max_length=20)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        digits = re.sub(r"[\s\-()]", "", value)
        if digits.startswith("+91"):
            digits = digits[3:]
        elif digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        elif digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            raise ValueError("Enter a valid 10-digit Indian mobile number.")
        return digits

    @field_validator("plan")
    @classmethod
    def _plan(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if value not in PLAN_DAYS:
            raise ValueError("Unknown plan.")
        return value


class CreateOrderOut(BaseModel):
    order_id: str
    payment_session_id: str


class OrderStatusOut(BaseModel):
    order_id: str
    status: str  # PENDING | PAID | FAILED | EXPIRED
    plan: str
    amount: float
    currency: str
    school_id: int
    plan_valid_until: datetime | None = None


# ---------------------------------------------------------------------------
# The one place a plan is granted
# ---------------------------------------------------------------------------


def _locked_order(db: Session, order_id: str) -> PaymentOrder | None:
    # FOR UPDATE on Postgres serialises the verify poll and the webhook for
    # the same order; SQLite (tests, local dev) ignores it harmlessly.
    return db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).with_for_update().first()


def _apply_cashfree_status(db: Session, order: PaymentOrder, fetched: cashfree.FetchedOrder) -> PaymentOrder:
    """Move `order` to the status Cashfree reports. Idempotent: PAID never
    changes again, and the plan is granted only on the transition into PAID."""
    if order.status == "PAID":
        return order

    new_status = _STATUS_MAP.get(fetched.order_status, "PENDING")

    if new_status == "PAID":
        paid_paise = round(float(fetched.order_amount or 0) * 100)
        if paid_paise != order.amount_paise or (fetched.order_currency or "INR") != order.currency:
            # Should be impossible (the amount is set server-side), but a
            # mismatch must never grant anything. Leave it for a human.
            logger.error("Payment amount mismatch on order %s; plan not granted", order.order_id)
            order.status = "FAILED"
            db.commit()
            return order

        now = datetime.now(timezone.utc)
        order.status = "PAID"
        order.paid_at = _naive_utc(now)

        school = db.get(School, order.school_id)
        if school is not None:
            current = school.plan_valid_until
            if current is not None and current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            start = current if (current and current > now and school.plan == order.plan) else now
            school.plan = order.plan
            school.plan_valid_until = _naive_utc(start + timedelta(days=PLAN_DAYS[order.plan]))
        logger.info("Order %s paid; plan %s granted to school %s", order.order_id, order.plan, order.school_id)
    elif new_status != order.status:
        order.status = new_status

    db.commit()
    db.refresh(order)
    return order


def _status_out(db: Session, order: PaymentOrder) -> OrderStatusOut:
    school = db.get(School, order.school_id)
    return OrderStatusOut(
        order_id=order.order_id,
        status=order.status,
        plan=order.plan,
        amount=order.amount_paise / 100,
        currency=order.currency,
        school_id=order.school_id,
        plan_valid_until=school.plan_valid_until if (school and order.status == "PAID") else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/create-order", response_model=CreateOrderOut, status_code=201)
def create_order(
    payload: CreateOrderIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    _require_configured()
    check_quota(f"payment-order:{current_user.id}", limit=10, window_seconds=3600)

    price = _price_rupees(payload.plan)
    # Alphanumeric plus '_'; Cashfree allows 3-45 characters. Random part so
    # the id in the return URL can't be guessed to probe other orders.
    order_id = f"tz_{payload.school_id}_{secrets.token_hex(8)}"
    order = PaymentOrder(
        order_id=order_id,
        school_id=payload.school_id,
        user_id=current_user.id,
        plan=payload.plan,
        amount_paise=price * 100,
        currency="INR",
        status="PENDING",
    )
    db.add(order)
    db.commit()

    return_url = f"{settings.frontend_base_url.rstrip('/')}/?page=payment-status&order_id={{order_id}}"
    try:
        created = cashfree.create_order(
            order_id=order_id,
            amount_rupees=price,
            customer_id=f"user_{current_user.id}",
            customer_name=current_user.name,
            customer_email=current_user.email,
            customer_phone=payload.phone,
            return_url=return_url,
            note=f"Timetablz {payload.plan.title()} plan, 1 year",
        )
    except cashfree.PaymentsNotConfigured:
        order.status = "FAILED"
        db.commit()
        raise HTTPException(status_code=503, detail="Online payments aren't set up yet.")
    except cashfree.PaymentProviderError as exc:
        order.status = "FAILED"
        db.commit()
        raise HTTPException(status_code=502, detail=f"Couldn't start the payment: {exc}") from exc

    order.cf_order_id = created.cf_order_id
    db.commit()
    return CreateOrderOut(order_id=order_id, payment_session_id=created.payment_session_id)


@router.get("/orders/{order_id}", response_model=OrderStatusOut)
def get_order_status(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Called by the return page. Confirms the status with Cashfree (never
    trusting the redirect itself) and applies it."""
    if not re.fullmatch(r"[A-Za-z0-9_\-]{3,45}", order_id or ""):
        raise HTTPException(status_code=404, detail="Order not found")
    order = db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    # Anyone in the school may look; this also hides other schools' orders.
    require_school_access(db, current_user, order.school_id)

    if order.status in ("PAID", "FAILED", "EXPIRED") or not cashfree.is_configured():
        return _status_out(db, order)

    try:
        fetched = cashfree.fetch_order(order_id)
    except cashfree.PaymentProviderError:
        # Couldn't reach Cashfree: report what we know (PENDING) and let the
        # page poll again rather than show a scary error.
        return _status_out(db, order)

    order = _locked_order(db, order_id)
    return _status_out(db, _apply_cashfree_status(db, order, fetched))


@router.post("/webhook")
async def cashfree_webhook(request: Request, db: Session = Depends(get_db)):
    """Server-to-server notification from Cashfree.

    The signature is checked against the raw body first. Even then the
    payload is used only to find the order id: the status itself is
    re-fetched from Cashfree's Get Order API, so this endpoint can never be
    the thing that decides a payment succeeded.

    Returns 200 for anything validly signed - including events for orders we
    don't know or event types we don't use - so Cashfree doesn't keep
    retrying them. Returns 400 only for a bad signature."""
    if not cashfree.is_configured():
        raise HTTPException(status_code=503, detail="Payments not configured")

    raw_body = (await request.body()).decode("utf-8")
    try:
        event = cashfree.verify_webhook(
            request.headers.get("x-webhook-signature"),
            raw_body,
            request.headers.get("x-webhook-timestamp"),
        )
    except ValueError:
        logger.warning("Rejected Cashfree webhook with an invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    order_id = ((event.get("data") or {}).get("order") or {}).get("order_id")
    if not order_id:
        return {"ok": True, "ignored": "no order"}

    order = db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()
    if order is None:
        return {"ok": True, "ignored": "unknown order"}
    if order.status == "PAID":
        return {"ok": True}

    try:
        fetched = cashfree.fetch_order(order_id)
    except cashfree.PaymentProviderError:
        # Let Cashfree retry the webhook later.
        raise HTTPException(status_code=503, detail="Could not confirm order status")

    _apply_cashfree_status(db, _locked_order(db, order_id), fetched)
    return {"ok": True}
