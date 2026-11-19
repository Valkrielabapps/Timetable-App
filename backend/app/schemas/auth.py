from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

def _lowercase(email: str) -> str:
    return email.strip().lower()


def _plain_new_email(email: str) -> str:
    """An address someone is giving us for a new account or invite.

    Lowercased, so Allen@school.in and allen@school.in are one account, as
    every mail server treats them. And plain ASCII only: an address may
    legally use other scripts, which lets two look-alike addresses (a Cyrillic 'а' for a Latin 'a') name two accounts - nothing a
    school's staff address needs."""
    email = _lowercase(email)
    if not email.isascii():
        raise ValueError("Use an email address made of plain letters (a-z), numbers and . _ - + only.")
    return email


# Every email that reaches the API, lowercased: stored and compared in one form.
# Signing in or resetting only lowercases - an older account keeps working
# whatever its address looks like.
Email = Annotated[EmailStr, AfterValidator(_lowercase)]
# Signing up, or inviting someone: lowercased and plain ASCII.
NewEmail = Annotated[EmailStr, AfterValidator(_plain_new_email)]

MIN_PASSWORD_LENGTH = 8
# bcrypt only reads the first 72 bytes; anything past that would be silently
# ignored, so a longer password is refused rather than quietly shortened.
MAX_PASSWORD_BYTES = 72


def check_new_password(password: str) -> str:
    """A password someone is choosing now. Raises ValueError with a message
    meant for them. Not applied at login: accounts made before this rule
    keep working with the password they have."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Use at least {MIN_PASSWORD_LENGTH} characters for your password.")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError("That password is too long - use at most 72 characters.")
    return password


class SignupRequest(BaseModel):
    email: NewEmail
    password: str
    name: str | None = Field(default=None, max_length=100)

    _password = field_validator("password")(classmethod(lambda cls, v: check_new_password(v)))


class LoginRequest(BaseModel):
    email: Email
    password: str


class GoogleLoginRequest(BaseModel):
    # The ID token Google's Sign-In button returns via its `credential`
    # field (a JWT) - verified server-side in routers/auth.py rather than
    # trusted as-is, since anything from the client could be forged.
    credential: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str | None
    # Timetablz staff: sees the admin page. Read off User.is_platform_admin.
    is_platform_admin: bool = False
    # Must accept the current Terms before using the app (first sign-in, or
    # the terms changed). Read off User.needs_terms.
    needs_terms: bool = False
    terms_version: str = ""
    has_accepted_before: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ForgotPasswordRequest(BaseModel):
    email: Email


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    _password = field_validator("new_password")(classmethod(lambda cls, v: check_new_password(v)))


class UserProfileUpdate(BaseModel):
    name: str


class AcceptTermsRequest(BaseModel):
    # The version the person was shown, so an old page can't accept new terms.
    version: str
