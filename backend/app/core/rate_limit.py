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

Both are in-memory and therefore per-process. That is correct for a single
backend instance, which is what this app runs; with more than one, each
instance would enforce its own allowance and the effective limit would
multiply by the instance count. Moving to Redis is the fix at that point -
the same threshold at which the background solver thread in
routers/timetables.py needs a real task queue.
"""
import logging
import threading
import time

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


limiter = Limiter(key_func=client_ip, enabled=settings.rate_limit_enabled)


# ---------------------------------------------------------------------------
# Keyed quotas (per email, per user)
# ---------------------------------------------------------------------------

_hits: dict[str, list[float]] = {}
_lock = threading.Lock()

# Entries are pruned lazily on access, so a key nobody touches again would
# otherwise linger forever. Sweep when the table grows past this.
_MAX_KEYS = 10_000


def _prune(now: float, window_seconds: int) -> None:
    """Drop keys whose every hit has aged out. Caller must hold _lock."""
    cutoff = now - window_seconds
    for key in [k for k, v in _hits.items() if not v or v[-1] < cutoff]:
        del _hits[key]


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
            _prune(now, window_seconds)

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


def reset_quotas() -> None:
    """Clear all recorded hits. For tests - each one needs a clean slate."""
    with _lock:
        _hits.clear()


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
