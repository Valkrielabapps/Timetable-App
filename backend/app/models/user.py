from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, false
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    """
    A school admin account. Auth is email/password for now (hashed_password
    is set); the `google_sub` column is reserved for when Google sign-in is
    wired up (storing Google's stable subject ID), so no migration is needed
    to add it later.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=True)  # null once Google-only signup exists
    name = Column(String, nullable=True)
    google_sub = Column(String, unique=True, nullable=True)
    # Whether the person has shown they own this email: signed in with Google
    # (which verifies it), opened an invite sent to it, or reset the password
    # through a link sent to it. A plain signup proves nothing - anyone can
    # type anyone's address - so it starts unverified. See google_login for
    # why it matters.
    email_verified = Column(Boolean, nullable=False, default=False, server_default=false())
    # Stamped into every login token. Raising it signs the account out
    # everywhere: tokens carrying an older number are refused. Raised when the
    # password changes, and when a Google sign-in takes over an account whose
    # password was set by someone who never proved they own the email.
    token_version = Column(Integer, nullable=False, default=0, server_default="0")

    schools = relationship("School", back_populates="owner")
    terms_acceptances = relationship("TermsAcceptance", back_populates="user", lazy="selectin")

    @property
    def needs_terms(self) -> bool:
        """Hasn't accepted the current Terms of Service yet (first sign-in, or
        the terms changed since) - see app/core/terms.py."""
        from app.core.terms import CURRENT_TERMS_VERSION

        return not any(a.version == CURRENT_TERMS_VERSION for a in self.terms_acceptances)

    @property
    def has_accepted_before(self) -> bool:
        """Accepted an earlier version: told "we've updated our terms"."""
        return bool(self.terms_acceptances)

    @property
    def terms_version(self) -> str:
        from app.core.terms import CURRENT_TERMS_VERSION

        return CURRENT_TERMS_VERSION

    @property
    def is_platform_admin(self) -> bool:
        """Timetablz staff (PLATFORM_ADMIN_EMAILS), not a school admin."""
        from app.core.config import settings

        allowed = {e.strip().lower() for e in (settings.platform_admin_emails or "").split(",") if e.strip()}
        # Verified only: otherwise whoever signs up first with an admin address
        # that has no account yet would get the admin page.
        return bool(self.email) and self.email.lower() in allowed and bool(self.email_verified)


class PasswordResetToken(Base):
    """
    A one-time, short-lived token for the forgot-password flow (see
    app/routers/auth.py's forgot_password/reset_password endpoints). Kept
    as its own table rather than columns on User (the pattern SchoolInvite
    uses for the same reason): a user can request multiple resets over
    time, and this way old ones just pile up as harmless rows instead of
    needing to be overwritten in place.

    `used` is set True the moment a token is redeemed, so a leaked/reused
    reset link (e.g. from an email forwarded or left open in a browser
    tab) can't reset the password a second time even before `expires_at`.
    Works for Google-only accounts too (hashed_password null) - resetting
    just sets a password, giving that account an email/password login
    option alongside Google sign-in, rather than requiring one to exist
    already.
    """
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # SHA-256 of the token in the emailed link, never the token itself, so a
    # copy of the database can't be used to reset anyone's password.
    token = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")


class TermsAcceptance(Base):
    """
    One person accepting one version of the Terms of Service and Privacy
    Policy: the record that shows, if it is ever needed, who agreed to what
    and when. Never edited. Kept if the account is deleted (user_id is then
    cleared; the email stays), since that is when it may be needed most.
    """
    __tablename__ = "terms_acceptances"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    email = Column(String, nullable=False)
    version = Column(String(32), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(400), nullable=True)

    user = relationship("User", back_populates="terms_acceptances")
