"""
Transactional email — invite emails and password-reset emails, both sent
via Resend's HTTP API
(https://resend.com/docs/api-reference/emails/send-email). Plain
`requests` calls rather than Resend's SDK, since `requests` is already a
dependency and the API is a handful of simple POSTs — not worth a new
package for that.

Design choices (mirrors app/services/llm_constraint_parser.py):
  - Every send_* function returns False (never raises) on ANY failure —
    no API key configured, network error, Resend rejecting the request,
    whatever.
      - For invites specifically: sending is a nice-to-have on top of
        invite creation, not a precondition for it — the invite is
        already created and its link already returned to the admin
        before this is even called, so a flaky email API must never turn
        a successful invite into a failed request.
      - For password resets: app/routers/auth.py's forgot_password
        endpoint always returns the same generic response regardless of
        what this returns, specifically so a caller can't distinguish
        "no account with that email" from "email failed to send" from
        "email sent" — see that endpoint's docstring for why (user
        enumeration).
  - No retry logic in either case. For invites, the admin still has the
    copyable link in the UI as a fallback (see TeamTab.jsx). For password
    resets, the user can just request another one.
"""
import html as _html
import logging

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"


def _send(to_email: str, subject: str, html: str, log_context: str, reply_to: str | None = None) -> bool:
    """Shared send path for every email this service sends — the part
    that's identical regardless of which template/recipient is involved:
    no-op if unconfigured, POST to Resend, swallow every failure mode into
    False. `log_context` is just a short label (e.g. "invite email",
    "password reset email") so log lines are distinguishable."""
    if not settings.resend_api_key:
        logger.info("RESEND_API_KEY not set; skipping %s to %s", log_context, to_email)
        return False

    payload = {
        "from": settings.email_from_address,
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        response = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json=payload,
            timeout=10,
        )
        if response.status_code >= 400:
            logger.warning(
                "Resend rejected %s to %s: %s %s",
                log_context, to_email, response.status_code, response.text,
            )
            return False
        return True
    except Exception:
        logger.exception("Failed to send %s to %s", log_context, to_email)
        return False


def send_invite_email(
    to_email: str,
    school_name: str,
    inviter_name: str,
    role: str,
    invite_token: str,
) -> bool:
    """Returns True if Resend accepted the email, False otherwise (including
    when no API key is configured at all — that's a silent no-op, not an
    error, since email is optional infrastructure)."""
    invite_link = f"{settings.frontend_base_url}/?invite={invite_token}"
    role_label = "admin" if role == "admin" else "viewer"

    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <p>{inviter_name} invited you to join <strong>{school_name}</strong>
      on Timetable App as {'an' if role_label == 'admin' else 'a'} {role_label}.</p>
      <p>
        <a href="{invite_link}"
           style="display: inline-block; padding: 10px 20px; background: #0f172a;
                  color: #fff; text-decoration: none; border-radius: 6px;">
          Accept invite
        </a>
      </p>
      <p style="color: #64748b; font-size: 13px;">
        Or copy this link: <br />{invite_link}
      </p>
    </div>
    """.strip()

    return _send(
        to_email=to_email,
        subject=f"You've been invited to {school_name}",
        html=html,
        log_context="invite email",
    )


def send_password_reset_email(to_email: str, reset_token: str) -> bool:
    """Returns True if Resend accepted the email, False otherwise
    (including when no API key is configured). Never raises — see the
    module docstring for why app/routers/auth.py's forgot_password
    endpoint deliberately ignores this return value in its response."""
    reset_link = f"{settings.frontend_base_url}/?reset={reset_token}"
    expire_minutes = settings.password_reset_expire_minutes

    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <p>Someone requested a password reset for this Timetable App account.
      If that was you, click below to set a new password:</p>
      <p>
        <a href="{reset_link}"
           style="display: inline-block; padding: 10px 20px; background: #0f172a;
                  color: #fff; text-decoration: none; border-radius: 6px;">
          Reset password
        </a>
      </p>
      <p style="color: #64748b; font-size: 13px;">
        This link expires in {expire_minutes} minutes. If you didn't request
        this, you can safely ignore this email — your password won't change.
      </p>
      <p style="color: #64748b; font-size: 13px;">
        Or copy this link: <br />{reset_link}
      </p>
    </div>
    """.strip()

    return _send(
        to_email=to_email,
        subject="Reset your Timetable App password",
        html=html,
        log_context="password reset email",
    )


def send_support_ticket(
    from_email: str,
    from_name: str | None,
    school_name: str | None,
    category: str,
    subject: str,
    message: str,
) -> bool:
    """Forwards a ticket from the in-app support button to the support
    inbox (settings.support_email). Reply-To is the user's own address, so
    hitting Reply in the support inbox answers them directly.

    Everything the user typed is HTML-escaped: it lands in our own inbox,
    and an unescaped message is an easy way to make a support email render
    something misleading. Same never-raises contract as the other senders;
    app/routers/support.py tells the user to email directly when this
    returns False rather than pretending the ticket went through."""
    esc = _html.escape
    body = esc(message).replace("\n", "<br />")
    html = f"""
    <div style="font-family: sans-serif; max-width: 560px;">
      <p style="color: #64748b; font-size: 13px; margin: 0 0 12px;">
        From {esc(from_name or "")} &lt;{esc(from_email)}&gt;<br />
        School: {esc(school_name or "-")}<br />
        Category: {esc(category)}
      </p>
      <p style="font-weight: 600; margin: 0 0 8px;">{esc(subject)}</p>
      <p style="margin: 0; line-height: 1.5;">{body}</p>
    </div>
    """.strip()

    return _send(
        to_email=settings.support_email,
        subject=f"[Support] {subject}",
        html=html,
        log_context="support ticket",
        reply_to=from_email,
    )
