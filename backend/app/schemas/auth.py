from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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
    email: EmailStr
    password: str
    name: str | None = Field(default=None, max_length=100)

    _password = field_validator("password")(classmethod(lambda cls, v: check_new_password(v)))


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    # The ID token Google's Sign-In button returns via its `credential`
    # field (a JWT) — verified server-side in routers/auth.py rather than
    # trusted as-is, since anything from the client could be forged.
    credential: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str | None
    # Timetablz staff: sees the admin page. Read off User.is_platform_admin.
    is_platform_admin: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    _password = field_validator("new_password")(classmethod(lambda cls, v: check_new_password(v)))


class UserProfileUpdate(BaseModel):
    name: str
