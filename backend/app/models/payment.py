"""
Payment orders for plan purchases (Cashfree hosted checkout).

One row per checkout attempt. The row is created as PENDING before the
customer ever sees the payment page, and only ever moves to PAID after the
server has confirmed it with Cashfree itself (the Get Order API, called from
the verify endpoint or after a signature-checked webhook) - never because the
browser said so. See app/routers/payments.py.

The amount is stored as integer paise rather than a float of rupees, so a
comparison against what Cashfree reports can't be thrown off by rounding.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


def _now():
    return datetime.now(timezone.utc)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True)
    # Our id, also sent to Cashfree as its order_id. Unique and unguessable
    # enough that it can sit in the return URL.
    order_id = Column(String(45), nullable=False, unique=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    plan = Column(String(20), nullable=False)
    amount_paise = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    # PENDING -> PAID, or PENDING -> FAILED / EXPIRED. PAID is terminal: once
    # set it is never downgraded, whatever a later webhook or poll says.
    status = Column(String(16), nullable=False, default="PENDING")
    cf_order_id = Column(String(64), nullable=True)
    # Set when this order pays for a custom offer (PlanOffer); the offer's
    # limits and length are applied when it's paid.
    offer_id = Column(Integer, ForeignKey("plan_offers.id"), nullable=True)
    period_days = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)
    paid_at = Column(DateTime, nullable=True)


class PlanOffer(Base):
    """A custom plan agreed with one school (Settings > Plan & billing shows it
    to that school's admins, who pay it through the normal checkout).

    Limits left null mean unlimited. Only one offer per school is open at a
    time; creating a new one cancels the old.
    """

    __tablename__ = "plan_offers"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    price_inr = Column(Integer, nullable=False)
    period_days = Column(Integer, nullable=False, default=365)
    max_sections = Column(Integer, nullable=True)
    max_members = Column(Integer, nullable=True)
    max_owned_schools = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)
    status = Column(String(12), nullable=False, default="open")  # open | paid | cancelled
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    paid_at = Column(DateTime, nullable=True)


class Invoice(Base):
    """One per payment received, online or by bank transfer. Numbers are
    sequential (TZ-2026-0001) and never reused. The billed-to details are a
    snapshot taken when the invoice is issued, so a later profile edit
    doesn't rewrite an issued invoice."""

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    number = Column(String(20), nullable=False, unique=True, index=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_order_id = Column(Integer, ForeignKey("payment_orders.id"), nullable=True)
    description = Column(String(200), nullable=False)
    amount_paise = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    method = Column(String(20), nullable=False)  # online | bank_transfer | other
    reference = Column(String(100), nullable=True)
    billed_to = Column(JSON, nullable=True)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    issued_at = Column(DateTime, default=_now, nullable=False)
