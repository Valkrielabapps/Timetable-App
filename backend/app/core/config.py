"""
Application configuration.

Settings are loaded from environment variables (or a local .env file, see
backend/.env.example). Using pydantic-settings means every setting is
validated and typed instead of read ad-hoc with os.environ.get().
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL connection string, e.g.
    # postgresql://user:password@localhost:5432/timetable
    database_url: str = "sqlite:///./dev.db"

    # Comma-separated list of allowed frontend origins for CORS.
    cors_origins: str = "http://localhost:5173"

    app_name: str = "Timetable Generator API"
    debug: bool = True

    # JWT signing secret. MUST be overridden (via .env) for anything beyond
    # local development — this default is intentionally not secret.
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Hard cap on how long the CP-SAT solver searches before giving up and
    # reporting "unknown" instead of a definite answer. Generation runs as
    # a background job (see app/routers/timetables.py), so this can be
    # generous without risking an HTTP timeout — the frontend polls for
    # the result instead of waiting on one long request.
    solver_time_limit_seconds: int = 60

    # Used by app/services/llm_constraint_parser.py. If unset, constraint
    # parsing silently falls back to the regex-based parser
    # (app/services/constraint_parser.py) — the app works either way, the
    # LLM parser just understands a much wider range of phrasing and
    # constraint types.
    anthropic_api_key: str | None = None

    # Overridable via the LLM_MODEL env var, so a model can be swapped (e.g.
    # to claude-sonnet-5 if Haiku's parsing turns out too shallow for real
    # constraint phrasing) without a deploy. Unversioned alias on purpose:
    # it tracks the current Haiku 4.5 snapshot rather than pinning one.
    llm_model: str = "claude-haiku-4-5"

    # Rate limiting, on by default. Turned off in the test suite (see
    # tests/conftest.py), which signs up dozens of users from one client and
    # would otherwise spend most of its run being throttled. Also an operational
    # escape hatch: if a limit turns out to be set too low for a real school,
    # this buys time to retune it without a rollback.
    rate_limit_enabled: bool = True

    # Sentry DSN for error tracking. Unset by default, which disables Sentry
    # entirely (see app/core/observability.py) - so local dev, tests and CI
    # never report anything, and a missing DSN is a supported state rather
    # than a misconfiguration.
    sentry_dsn: str | None = None

    # Tags every event so production errors are distinguishable from anything
    # reported by a developer machine that happens to have a DSN set.
    sentry_environment: str = "development"

    # Fraction of requests traced for performance monitoring, 0.0-1.0.
    # Defaults to 0 (errors only): traces consume the same quota as errors on
    # Sentry's free tier, and this app's slow path (timetable generation) is
    # already a deliberate background job rather than something a trace would
    # explain.
    sentry_traces_sample_rate: float = 0.0

    # Google Cloud OAuth 2.0 Client ID (Web application type), used to
    # verify the ID token Google's Sign-In button hands back to the
    # frontend. Must match the client ID configured in the frontend
    # (VITE_GOOGLE_CLIENT_ID) — Google's library rejects a token whose
    # audience doesn't match what we verify against. Unset by default:
    # the "Sign in with Google" button hides itself on the frontend and
    # the backend endpoint returns a clear error if this is missing.
    google_client_id: str | None = None

    # Used by app/services/email_service.py to actually send invite emails
    # via Resend's HTTP API (https://resend.com). If unset, invite creation
    # silently skips sending — the invite is still created and its link is
    # still returned in the API response, so the admin can copy/send it
    # manually (same behavior as before this was wired up). Get a key at
    # resend.com/api-keys.
    resend_api_key: str | None = None
    # Resend requires "Name <email>" format. The default is Resend's shared
    # onboarding@resend.dev sender, which works out of the box with no
    # domain setup but is best for testing only — verify your own sending
    # domain in Resend and set this to something like
    # "Timetable App <notifications@yourdomain.com>" before relying on this
    # for real users (unverified-domain mail is more likely to land in spam
    # and can only send to the Resend account's own verified address).
    email_from_address: str = "Timetable App <onboarding@resend.dev>"
    # Base URL of the deployed frontend (no trailing slash), used to build
    # the invite link included in the email — e.g. "https://app.example.com".
    # Defaults to the local Vite dev server so invite emails work out of the
    # box in development; MUST be set to the real deployed frontend URL in
    # production or invite links will point at localhost.
    frontend_base_url: str = "http://localhost:5173"

    # How long a forgot-password link stays valid before it's rejected as
    # expired (see PasswordResetToken / app/routers/auth.py). Short on
    # purpose — this is a bearer link that could leak via a forwarded
    # email or shared inbox, so it shouldn't stay usable indefinitely.
    password_reset_expire_minutes: int = 60


    @field_validator(
        "anthropic_api_key",
        "sentry_dsn",
        "google_client_id",
        "resend_api_key",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, value):
        """Treat an empty env var as unset rather than as an empty string.

        .env.example ships each of these as `KEY=` so it is obvious they
        exist, which means anyone who copies it gets "" rather than None.
        Every consumer of these settings tests them for falsiness so the
        behaviour was already correct, but "" is not None, and code (and
        tests) that reasonably check `is None` would disagree with code that
        checks `if not ...` about whether the feature is configured.

        Normalising here means there is exactly one representation of
        "not configured" regardless of whether the variable is absent,
        empty, or whitespace.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value


settings = Settings()
