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

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

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
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)
    paid_at = Column(DateTime, nullable=True)
