"""
Auth building blocks: password hashing and JWT issuance/verification.

Kept separate from app/routers/auth.py so the actual crypto/token logic can
be unit tested or swapped (e.g. adding Google sign-in) without touching the
HTTP layer.
"""
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import PyJWTError as JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# tokenUrl points at the login endpoint purely for the /docs "Authorize"
# button's benefit — this API takes JSON, not a form, so that endpoint
# won't actually work from the docs UI, but the header-based flow does.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_token(token: str) -> str:
    """How one-time link tokens (password reset) are stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user.id), "exp": expire, "ver": user.token_version or 0}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def sign_out_everywhere(user: User) -> None:
    """Refuse every login token issued so far. The caller commits."""
    user.token_version = (user.token_version or 0) + 1


def get_current_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthorized
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub"))
        # Tokens from before versions existed carry none: they count as 0.
        version = int(payload.get("ver", 0))
    except (JWTError, TypeError, ValueError):
        raise unauthorized

    user = db.get(User, user_id)
    if not user or version != (user.token_version or 0):
        raise unauthorized
    return user
