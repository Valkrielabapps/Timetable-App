"""
Rate limiting.

Two mechanisms, because the two things worth limiting have different keys:

  - `limiter` (slowapi) limits by client IP. Used on the unauthenticated
    endpoints, where an IP is the only identity available.
  - `check_quota` limits by whatever string the caller passes - an email
    address, a user id - for the cases where the IP is the wrong key or
    not the only one worth using. It is called inside the handler rather
    than as a decorator because the key comes from the parsed request body
    or the authenticated user, neither of which a slowapi key function can
    reach.

Every route also has a general ceiling (`general_limit`, middleware in
main.py): per signed-in user, or per IP for anonymous requests. It is its own
middleware rather than slowapi's default_limits because slowapi can't see
routes through FastAPI's included routers and so quietly exempted all of them. And every route
that calls a paid AI model goes through `check_ai_quota`, which adds a
ceiling for the whole site on top of the per-user one - so opening more
accounts doesn't buy more AI.

All of it is in-memory and therefore per-process. That is correct for a single
backend instance, which is what this app runs; with more than one, each
instance would enforce its own allowance and the effective limit would
multiply by the instance count. Moving to Redis is the fix at that point -
the same threshold at which the background solver thread in
routers/timetables.py needs a real task queue.
"""
import logging
import threading
import time

import jwt
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


def client_ip(request: Request) -> str:
    """The end user's IP, not Vercel's.

    frontend/vercel.json proxies /api/* to this backend, so in production
    every request arrives from a Vercel edge IP. Limiting on the socket
    address would put all users in one bucket and throttle everyone at
    once the moment any one of them was busy - so the left-most entry of
    X-Forwarded-For (the original client, per the proxy convention) is
    used instead.

    That header is trivially forged by anything talking to the Railway URL
    directly, and Railway offers no practical way to reject non-Vercel
    traffic on this plan. So this is a throttle on ordinary abuse, not a
    defence against a determined attacker, and the credential-stuffing
    case - the one that actually matters - is covered by the per-email
    quotas in the auth router, which hold regardless of what IP a request
    claims to come from.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return get_remote_address(request)


def caller_key(request: Request) -> str:
    """Who a request counts against: the signed-in user, or else the IP.

    By user where possible, because a school's staff often share one office
    IP, and because a user id can't be forged the way X-Forwarded-For can.
    Only the token's signature is checked here, not the database: a token
    that fails falls back to the IP, and the route itself refuses it anyway.
    """
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        try:
            sub = jwt.decode(auth[7:], settings.jwt_secret, algorithms=[settings.jwt_algorithm]).get("sub")
        except jwt.PyJWTError:
            sub = None
        if sub:
            return f"user:{sub}"
    return f"ip:{client_ip(request)}"


limiter = Limiter(key_func=caller_key, enabled=settings.rate_limit_enabled)

# Far above what anyone clicking through the app does (a page load is a few
# dozen requests; scrolling through teachers is one a teacher), low enough to
# stop a script hammering the database.
GENERAL_LIMIT_PER_MINUTE = 600
# Turned away by nothing but their own checks: Cashfree's payment notices.
_NO_GENERAL_LIMIT = {"/api/payments/webhook"}


async def general_limit(request: Request, call_next):
    """The ceiling every request counts against, whatever the route."""
    if request.url.path not in _NO_GENERAL_LIMIT:
        try:
            check_quota(f"general:{caller_key(request)}", limit=GENERAL_LIMIT_PER_MINUTE, window_seconds=60)
        except HTTPException as exc:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down and try again shortly."},
                headers=exc.headers,
            )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Keyed quotas (per email, per user)
# ---------------------------------------------------------------------------

_hits: dict[str, list[float]] = {}
_windows: dict[str, int] = {}
_lock = threading.Lock()

# Entries are pruned lazily on access, so a key nobody touches again would
# otherwise linger forever. Sweep when the table grows past this.
_MAX_KEYS = 10_000


def _prune(now: float) -> None:
    """Drop keys whose every hit has aged out, each by its own window - a
    daily quota's hits mustn't go when an hourly one's would. Caller must
    hold _lock."""
    for key in [k for k, v in _hits.items() if not v or v[-1] < now - _windows.get(k, 86400)]:
        del _hits[key]
        _windows.pop(key, None)


def check_quota(key: str, limit: int, window_seconds: int) -> None:
    """Record one hit against `key`; raise 429 if it exceeds `limit` in the
    trailing `window_seconds`.

    A sliding window rather than a fixed one: fixed windows let twice the
    limit through across a boundary, which for login attempts is exactly
    the case worth not allowing.
    """
    if not settings.rate_limit_enabled:
        return

    now = time.monotonic()
    with _lock:
        if len(_hits) > _MAX_KEYS:
            _prune(now)
        _windows[key] = max(window_seconds, _windows.get(key, 0))

        hits = [t for t in _hits.get(key, []) if t > now - window_seconds]
        if len(hits) >= limit:
            retry_after = max(1, int(window_seconds - (now - hits[0])))
            _hits[key] = hits
            logger.warning("Quota exceeded for %s (%d per %ds)", key, limit, window_seconds)
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)
        _hits[key] = hits


def check_ai_quota(kind: str, user_id: int, per_hour: int) -> None:
    """Before a request that calls a paid AI model: the user's own allowance
    for this kind of request, then the whole site's. The site-wide ceiling
    holds however many accounts someone opens, and caps what the AI bill can
    reach in an hour or a day."""
    check_quota(f"{kind}:{user_id}", limit=per_hour, window_seconds=3600)
    check_quota("ai:site:hour", limit=settings.ai_calls_per_hour, window_seconds=3600)
    check_quota("ai:site:day", limit=settings.ai_calls_per_day, window_seconds=86400)


def ai_budget_left() -> bool:
    """For an AI call that's a nice extra rather than the point of the request
    (explaining why a timetable couldn't be made): take one from the site's
    allowance if there's any left, and say whether to go ahead."""
    try:
        check_quota("ai:site:hour", limit=settings.ai_calls_per_hour, window_seconds=3600)
        check_quota("ai:site:day", limit=settings.ai_calls_per_day, window_seconds=86400)
    except HTTPException:
        return False
    return True


def reset_quotas() -> None:
    """Clear all recorded hits. For tests - each one needs a clean slate."""
    with _lock:
        _hits.clear()
        _windows.clear()


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return slowapi's 429s in the same shape as check_quota's.

    slowapi's bundled handler emits `{"error": "Rate limit exceeded: ..."}`,
    which leaks the configured limit and doesn't match the `detail` key
    every other error in this API uses - frontend/src/api.js reads `detail`.
    """
    retry_after = getattr(exc, "retry_after", None) or 60
    logger.warning("Rate limit exceeded from %s on %s", client_ip(request), request.url.path)
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down and try again shortly."},
        headers={"Retry-After": str(retry_after)},
    )
