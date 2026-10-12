"""
Thin wrapper around Cashfree's official Python server SDK (cashfree-pg).

Kept in one place so the router never touches the SDK directly: the router
deals in plain values (order id, amount, status), and this module deals in
SDK request/response models, environment selection and error translation.
That also makes the payment endpoints testable without network access - the
tests replace these three functions.

Secrets: the secret key is only ever handed to the SDK client. It is never
logged, and SDK errors are logged by status code and Cashfree's message only,
never with request bodies (which contain customer contact details).
"""
import logging
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)


class PaymentsNotConfigured(Exception):
    """CASHFREE_APP_ID / CASHFREE_SECRET_KEY are not set."""


class PaymentProviderError(Exception):
    """Cashfree rejected the request or could not be reached."""


@dataclass
class CreatedOrder:
    cf_order_id: str | None
    payment_session_id: str


@dataclass
class FetchedOrder:
    order_status: str  # ACTIVE | PAID | EXPIRED | TERMINATED | TERMINATION_REQUESTED
    order_amount: float | None
    order_currency: str | None


def is_configured() -> bool:
    return bool(settings.cashfree_app_id and settings.cashfree_secret_key)


def is_production() -> bool:
    return (settings.cashfree_env or "").strip().lower() == "production"


def _client():
    if not is_configured():
        raise PaymentsNotConfigured()
    # Imported lazily so the app (and the test suite) start without the SDK
    # doing anything at import time.
    from cashfree_pg.api_client import Cashfree, CFEnvironment

    env = CFEnvironment.PRODUCTION if is_production() else CFEnvironment.SANDBOX
    return Cashfree(
        XEnvironment=env,
        XClientId=settings.cashfree_app_id,
        XClientSecret=settings.cashfree_secret_key,
    )


def _provider_error(action: str, exc: Exception) -> PaymentProviderError:
    status = getattr(exc, "status", None)
    message = None
    body = getattr(exc, "body", None)
    if body:
        try:
            import json

            message = json.loads(body).get("message")
        except Exception:
            message = None
    logger.warning("Cashfree %s failed (status=%s): %s", action, status, message or type(exc).__name__)
    return PaymentProviderError(message or "The payment provider could not process this request.")


def create_order(
    *,
    order_id: str,
    amount_rupees: float,
    customer_id: str,
    customer_name: str | None,
    customer_email: str | None,
    customer_phone: str,
    return_url: str,
    note: str | None = None,
) -> CreatedOrder:
    from cashfree_pg.models.create_order_request import CreateOrderRequest
    from cashfree_pg.models.customer_details import CustomerDetails
    from cashfree_pg.models.order_meta import OrderMeta

    client = _client()
    meta = {"return_url": return_url}
    if settings.cashfree_notify_url:
        meta["notify_url"] = settings.cashfree_notify_url
    request = CreateOrderRequest(
        order_id=order_id,
        order_amount=float(amount_rupees),
        order_currency="INR",
        customer_details=CustomerDetails(
            customer_id=customer_id,
            customer_name=customer_name if customer_name and len(customer_name) >= 3 else None,
            customer_email=customer_email,
            customer_phone=customer_phone,
        ),
        order_meta=OrderMeta(**meta),
        order_note=note,
    )
    try:
        # order_id doubles as the idempotency key: retrying the same create
        # can never produce a second order at Cashfree.
        response = client.PGCreateOrder(request, None, order_id)
    except Exception as exc:  # SDK raises ApiException and friends
        raise _provider_error("create order", exc) from exc

    data = response.data
    if not data or not data.payment_session_id:
        logger.warning("Cashfree create order returned no payment_session_id")
        raise PaymentProviderError("The payment provider did not return a checkout session.")
    return CreatedOrder(cf_order_id=data.cf_order_id, payment_session_id=data.payment_session_id)


def fetch_order(order_id: str) -> FetchedOrder:
    client = _client()
    try:
        response = client.PGFetchOrder(order_id)
    except Exception as exc:
        raise _provider_error("fetch order", exc) from exc
    data = response.data
    if not data or not data.order_status:
        raise PaymentProviderError("The payment provider returned no status for this order.")
    return FetchedOrder(
        order_status=data.order_status,
        order_amount=data.order_amount,
        order_currency=data.order_currency,
    )


def verify_webhook(signature: str | None, raw_body: str, timestamp: str | None) -> dict:
    """Return the parsed webhook payload if its signature is valid, else raise
    ValueError. Uses the SDK's PGVerifyWebhookSignature, which implements
    Base64(HMAC-SHA256(timestamp + rawBody, secret)) exactly as documented."""
    if not signature or not timestamp:
        raise ValueError("Missing webhook signature headers")
    client = _client()
    try:
        event = client.PGVerifyWebhookSignature(signature, raw_body, timestamp)
    except Exception as exc:
        raise ValueError("Webhook signature did not match") from exc
    return event.object
