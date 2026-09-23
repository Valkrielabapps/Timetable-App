"""
Auth endpoints: email/password signup and login, plus Google sign-in.

Google sign-in verifies the ID token Google's Sign-In button hands the
frontend (a JWT signed by Google, not something we issue) against Google's
public keys and our configured client ID, then finds-or-creates a User by
email. No password is ever involved for that path — `hashed_password` stays
null for Google-only accounts (the User model already allows this).
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.orm import Session

from app.core.rate_limit import check_quota, limiter
from app.core.auth import create_access_token, get_current_user, hash_password, verify_password
from app.core.config import settings
from app.core.database import get_db
from app.models.user import PasswordResetToken, User
from app.schemas.auth import (
    ForgotPasswordRequest,
    GoogleLoginRequest,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
)
from app.services.email_service import send_password_reset_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=201)
@limiter.limit("5/hour")
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        name=payload.name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    # Keyed on the email as well as the IP: rotating IPs is the whole point
    # of credential stuffing, and an IP limit alone does nothing against it.
    check_quota(f"login:{payload.email.lower()}", limit=10, window_seconds=3600)
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=user)


@router.post("/google", response_model=TokenResponse)
@limiter.limit("20/minute")
def google_login(request: Request, payload: GoogleLoginRequest, db: Session = Depends(get_db)):
    if not settings.google_client_id:
        # Fails loudly rather than silently accepting an unverifiable
        # token — better than pretending Google sign-in works when the
        # server has no client ID to check the token's audience against.
        raise HTTPException(
            status_code=503,
            detail="Google sign-in isn't configured on this server yet.",
        )

    try:
        claims = google_id_token.verify_oauth2_token(
            payload.credential, google_requests.Request(), settings.google_client_id
        )
    except ValueError as exc:
        # verify_oauth2_token collapses every failure mode (audience
        # mismatch, expired token, bad signature, clock skew, ...) into a
        # generic ValueError — logging the real message here is the only
        # way to tell which one it actually was, since the client only
        # ever sees the generic 401 below (a client shouldn't learn
        # *why* a token was rejected, e.g. clock skew details).
        logger.warning("Google sign-in token verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid Google sign-in token")

    email = claims.get("email")
    if not email or not claims.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google account has no verified email")
    google_sub = claims["sub"]
    name = claims.get("name")

    # Match on google_sub first (a returning Google-sign-in user), then
    # fall back to email (an existing email/password account signing in
    # with Google for the first time — link it rather than creating a
    # duplicate account with the same email).
    user = db.query(User).filter(User.google_sub == google_sub).first()
    if not user:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.google_sub = google_sub
        else:
            user = User(email=email, name=name, google_sub=google_sub)
            db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/forgot-password", status_code=202)
@limiter.limit("10/hour")
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Always returns the same generic response whether or not an account
    with this email exists, and regardless of whether the email actually
    sent — deliberately, to avoid leaking which emails have accounts on
    this app (a classic account-enumeration hole: if this returned 404
    for "no such user" and 200 for "reset sent", an attacker could use it
    to check which email addresses are registered). The frontend should
    just always show "if that email exists, we've sent a reset link."

    A Google-only account (hashed_password is null) can still request and
    complete a reset — see PasswordResetToken's docstring for why that's
    intentional rather than an edge case to reject.
    """
    # Per-email as well as per-IP: without this, someone can flood one
    # person's inbox from rotating IPs, on our Resend quota and our
    # sending reputation.
    check_quota(f"forgot:{payload.email.lower()}", limit=3, window_seconds=3600)

    user = db.query(User).filter(User.email == payload.email).first()
    if user:
        token = PasswordResetToken(
            user_id=user.id,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_expire_minutes),
        )
        db.add(token)
        db.commit()
        send_password_reset_email(to_email=user.email, reset_token=token.token)
    return {"detail": "If an account with that email exists, we've sent a password reset link."}


@router.post("/reset-password", response_model=TokenResponse)
@limiter.limit("10/hour")
def reset_password(request: Request, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Unlike forgot_password, this endpoint's response DOES reveal whether
    the token was valid — that's fine here (unlike the email-enumeration
    concern above) because a reset token is an unguessable random value,
    not something an attacker can iterate over like an email address, so
    confirming "this specific token is invalid" doesn't leak anything
    about which accounts exist.

    Logs the user in on success (returns a TokenResponse, same as
    login/signup) since they've just proven control of the account's
    email by clicking the link — making them re-enter the new password
    on a separate login screen right after setting it would be friction
    with no real security benefit.
    """
    reset_token = db.query(PasswordResetToken).filter(PasswordResetToken.token == payload.token).first()
    now = datetime.now(timezone.utc)
    if (
        not reset_token
        or reset_token.used
        or reset_token.expires_at.replace(tzinfo=timezone.utc) < now
    ):
        raise HTTPException(status_code=400, detail="This password reset link is invalid or has expired.")

    user = db.get(User, reset_token.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="This password reset link is invalid or has expired.")

    user.hashed_password = hash_password(payload.new_password)
    reset_token.used = True
    db.commit()

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=user)
