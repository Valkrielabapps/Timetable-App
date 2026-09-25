"""
Error tracking (Sentry).

Kept out of main.py so the configuration - particularly what gets scrubbed
before an event leaves the process - sits in one reviewable place rather
than inline next to route registration.

Sentry is entirely optional: with no SENTRY_DSN set, `init_sentry()` returns
without initialising anything and every `sentry_sdk.capture_*` call in the
codebase becomes a no-op. That is the normal state for local development,
the test suite and CI, so nothing here needs mocking or disabling in tests.
"""
import logging

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.core.config import settings

logger = logging.getLogger(__name__)

# Request headers that must never reach Sentry. Authorization carries the JWT
# that authenticates a user for the next week (see jwt_expire_minutes), and
# Cookie can carry the same by proxy - a captured error report is not a place
# for credentials that are still valid.
_SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key"}


def _scrub(event, _hint):
    """Strip credentials from the outgoing event.

    send_default_pii=False already keeps Sentry from attaching bodies, cookies
    and client IPs of its own accord. This is the belt-and-braces pass over
    headers, which are collected regardless of that flag.
    """
    request = event.get("request")
    if request:
        headers = request.get("headers")
        if headers:
            request["headers"] = {
                k: ("[scrubbed]" if k.lower() in _SENSITIVE_HEADERS else v)
                for k, v in headers.items()
            }
        # Belt and braces: max_request_body_size="never" should mean this is
        # never populated, but dropping it unconditionally costs nothing and
        # this app's request bodies carry emails, names and school data.
        request.pop("data", None)
    return event


def log_llm_availability() -> None:
    """Say at startup whether Claude is actually wired up.

    Every LLM call site falls back to a regex parser (or a 503) when no key
    is configured, and does so silently by design - a flaky API shouldn't
    block constraint entry. The cost is that "the key never reached the
    container" and "the model misread the sentence" look identical from the
    outside: constraints just quietly come back worse.

    One line in the deploy log removes that ambiguity.
    """
    if settings.anthropic_api_key:
        logger.info("ANTHROPIC_API_KEY configured; LLM parsing enabled (model=%s)", settings.llm_model)
    else:
        logger.warning(
            "ANTHROPIC_API_KEY not set - constraint parsing, edit commands, setup "
            "extraction and infeasibility explanations will all use their non-LLM "
            "fallbacks. This is a supported state, not an error, but it is almost "
            "never what is wanted in production."
        )


def init_sentry() -> bool:
    """Initialise Sentry if a DSN is configured. Returns whether it did.

    Safe to call exactly once at startup; calling it without a DSN is the
    supported no-op path, not an error.
    """
    if not settings.sentry_dsn:
        logger.info("SENTRY_DSN not set; error tracking disabled")
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # Never attach user identifiers, IP addresses or cookies. This app
        # holds school staff data; an error report should say what broke, not
        # who was logged in when it broke.
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_scrub,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            # Route logger.error()/logger.exception() calls into Sentry as
            # events, while leaving lower levels as breadcrumbs for context.
            # app/services/email_service.py and the LLM services already log
            # this way, so their failures start being reported without either
            # of them needing to know Sentry exists.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    logger.info("Sentry initialised (environment=%s)", settings.sentry_environment)
    return True
