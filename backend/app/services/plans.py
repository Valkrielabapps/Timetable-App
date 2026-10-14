"""
Plans, what each one includes, and which one a school is actually on.

This is the one place plan limits live. Every enforcement point (adding a
section, inviting someone, creating a school, using an AI feature, exports)
asks `entitlements()` for the school's *effective* plan and limits, so
changing a number here changes it everywhere. The public catalogue
(GET /api/plans) and Settings > Plan & billing read from here too.

Lifecycle:

    free     a new school: Free limits for FREE_DAYS (School.free_trial_ends_at)
    active   paid, now < plan_valid_until               -> that plan's limits
    grace    plan_valid_until <= now < +GRACE_DAYS      -> still that plan's
             limits, with "renew by ..." shown everywhere
    locked   the free days are over and nothing is paid, or a paid plan's
             grace period is over -> nothing can be changed until the school
             pays (see is_locked; enforced in app/core/access.py). Data is
             kept and can still be viewed by signing in.

A Business plan with no plan_valid_until never expires (set by hand for a
school on custom terms). Nothing is ever deleted.
"""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.school import ClassGroup, School, SchoolInvite, SchoolMembership

GRACE_DAYS = 15
FREE_DAYS = 14

# None = unlimited.
@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    price_inr: int | None  # None = priced individually ("contact us")
    period_days: int | None
    sold_online: bool
    max_sections: int | None
    max_members: int | None  # people with access, including the owner
    ai_actions_per_month: int | None
    clean_exports: bool
    max_owned_schools: int | None
    description: str


def _pro_price() -> int:
    return settings.pro_plan_price_inr


def catalogue() -> dict[str, Plan]:
    return {
        "free": Plan(
            id="free", name="Free", price_inr=0, period_days=None, sold_online=False,
            max_sections=5, max_members=1, ai_actions_per_month=10, clean_exports=False,
            max_owned_schools=1,
            description="Try Timetablz with a small school or a few sections.",
        ),
        "pro": Plan(
            id="pro", name="Pro", price_inr=_pro_price(), period_days=365, sold_online=True,
            max_sections=60, max_members=5, ai_actions_per_month=None, clean_exports=True,
            max_owned_schools=1,
            description="For a whole school: up to 60 sections, a small team, and every AI feature.",
        ),
        "business": Plan(
            id="business", name="Business", price_inr=None, period_days=None, sold_online=False,
            max_sections=None, max_members=None, ai_actions_per_month=None, clean_exports=True,
            max_owned_schools=None,
            description="For groups running several schools, on custom terms.",
        ),
    }


def get_plan(plan_id: str | None) -> Plan:
    return catalogue().get(plan_id or "free", catalogue()["free"])


def plan_for_school(school: School, plan_id: str) -> Plan:
    """The catalogue plan, with a paid custom offer's limits laid over the
    Business plan (School.custom_limits; a missing key means unlimited)."""
    plan = get_plan(plan_id)
    if plan_id == "business" and school.custom_limits:
        lim = school.custom_limits
        plan = replace(
            plan,
            name=school.custom_plan_name or plan.name,
            max_sections=lim.get("max_sections"),
            max_members=lim.get("max_members"),
            max_owned_schools=lim.get("max_owned_schools"),
        )
    return plan


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _days_left(end: datetime | None, now: datetime) -> int | None:
    end = _aware(end)
    if end is None:
        return None
    seconds = (end - now).total_seconds()
    # Rounded up: with 13.2 days to go the countdown says 14, and it shows
    # 1 on the last day rather than 0.
    return max(0, -int(-seconds // 86400))


def _month(now: datetime) -> str:
    return now.strftime("%Y-%m")


@dataclass
class Entitlements:
    plan: str             # the plan whose limits apply right now
    paid_plan: str | None  # what the school bought (may differ when expired)
    status: str           # free | active | grace | expired
    plan_valid_until: datetime | None
    grace_ends_at: datetime | None
    free_trial_ends_at: datetime | None
    free_days_left: int | None
    plan_name: str
    limits: dict
    usage: dict

    def as_dict(self) -> dict:
        return asdict(self)


def effective_plan(school: School, now: datetime | None = None) -> tuple[Plan, str, datetime | None]:
    """(plan whose limits apply, status, grace end)."""
    now = now or datetime.now(timezone.utc)
    paid = school.plan if school.plan in ("pro", "business") else None
    if paid is None:
        trial_end = _aware(school.free_trial_ends_at)
        # No end date recorded = treated as still free; every school gets one
        # on creation (and the migration gave existing schools one).
        if trial_end is None or now < trial_end:
            return get_plan("free"), "free", None
        return get_plan("free"), "locked", None
    valid_until = _aware(school.plan_valid_until)
    if valid_until is None:
        # Only Business is ever set without an end date.
        return (plan_for_school(school, paid), "active", None) if paid == "business" else (get_plan("free"), "locked", None)
    grace_end = valid_until + timedelta(days=GRACE_DAYS)
    if now < valid_until:
        return plan_for_school(school, paid), "active", grace_end
    if now < grace_end:
        return plan_for_school(school, paid), "grace", grace_end
    return get_plan("free"), "locked", grace_end


def is_locked(school: School, now: datetime | None = None) -> bool:
    if not settings.plan_limits_enabled:
        return False
    return effective_plan(school, now)[1] == "locked"


def new_school_trial_end(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(days=FREE_DAYS)).replace(tzinfo=None)


LOCKED_MESSAGE = (
    "This school's free period has ended. Upgrade to Pro to keep building and editing timetables. "
    "Nothing has been deleted."
)


def _member_count(db: Session, school: School) -> int:
    members = db.query(SchoolMembership).filter(SchoolMembership.school_id == school.id).count()
    pending = (
        db.query(SchoolInvite)
        .filter(SchoolInvite.school_id == school.id, SchoolInvite.status == "pending")
        .count()
    )
    owner = 1 if school.owner_id else 0
    return owner + members + pending


def _ai_used(school: School, now: datetime) -> int:
    return (school.ai_usage_count or 0) if school.ai_usage_month == _month(now) else 0


def entitlements(db: Session, school: School, now: datetime | None = None) -> Entitlements:
    now = now or datetime.now(timezone.utc)
    plan, status, grace_end = effective_plan(school, now)
    return Entitlements(
        plan=plan.id,
        paid_plan=school.plan if school.plan in ("pro", "business") else None,
        status=status,
        plan_valid_until=school.plan_valid_until,
        grace_ends_at=grace_end.replace(tzinfo=None) if grace_end else None,
        free_trial_ends_at=school.free_trial_ends_at,
        free_days_left=_days_left(school.free_trial_ends_at, now) if status == "free" else None,
        plan_name=plan.name,
        limits={
            "max_sections": plan.max_sections,
            "max_members": plan.max_members,
            "ai_actions_per_month": plan.ai_actions_per_month,
            "clean_exports": plan.clean_exports,
            "max_owned_schools": plan.max_owned_schools,
        },
        usage={
            "sections": db.query(ClassGroup).filter(ClassGroup.school_id == school.id).count(),
            "members": _member_count(db, school),
            "ai_actions_this_month": _ai_used(school, now),
        },
    )


# ---------------------------------------------------------------------------
# Enforcement helpers. Each raises 402 with a message the frontend shows as-is
# next to an "Upgrade" button (see api.js / UpgradePrompt).
# ---------------------------------------------------------------------------


def _upgrade_hint(plan: Plan) -> str:
    if plan.id == "free":
        pro = get_plan("pro")
        return f" Upgrade to Pro (₹{pro.price_inr:,} a year) for more."
    return " Contact support@timetablz.com about the Business plan."


def plan_limit(message: str) -> HTTPException:
    return HTTPException(status_code=402, detail=message)


def sections_remaining(db: Session, school: School) -> int | None:
    if not settings.plan_limits_enabled:
        return None
    plan, _, _ = effective_plan(school)
    if plan.max_sections is None:
        return None
    used = db.query(ClassGroup).filter(ClassGroup.school_id == school.id).count()
    return max(plan.max_sections - used, 0)


def sections_limit_message(school: School) -> str:
    plan, _, _ = effective_plan(school)
    return f"The {plan.name} plan includes up to {plan.max_sections} sections.{_upgrade_hint(plan)}"


def require_section_capacity(db: Session, school: School, adding: int = 1) -> None:
    if not settings.plan_limits_enabled:
        return
    remaining = sections_remaining(db, school)
    if remaining is not None and adding > remaining:
        raise plan_limit(sections_limit_message(school))


def require_member_capacity(db: Session, school: School) -> None:
    if not settings.plan_limits_enabled:
        return
    plan, _, _ = effective_plan(school)
    if plan.max_members is None:
        return
    if _member_count(db, school) >= plan.max_members:
        if plan.max_members <= 1:
            msg = f"The {plan.name} plan is for one admin only, so you can't invite others.{_upgrade_hint(plan)}"
        else:
            msg = f"The {plan.name} plan includes up to {plan.max_members} people (including pending invites).{_upgrade_hint(plan)}"
        raise plan_limit(msg)


def require_school_capacity(db: Session, user_id: int) -> None:
    """A user may own one school, unless one of their schools is on a plan
    that allows more (Business)."""
    if not settings.plan_limits_enabled:
        return
    owned = db.query(School).filter(School.owner_id == user_id).all()
    allowed = 1
    for s in owned:
        plan, _, _ = effective_plan(s)
        if plan.max_owned_schools is None:
            return
        allowed = max(allowed, plan.max_owned_schools)
    if len(owned) >= allowed:
        raise plan_limit(
            "Each account can run one school. To manage several schools from one account, "
            "contact support@timetablz.com about the Business plan."
        )


def use_ai(db: Session, school: School) -> bool:
    """Count one AI action against the school's monthly allowance.

    Returns False (and counts nothing) when the allowance is used up, so the
    caller can fall back to the non-AI path or refuse. Plans with no limit
    always return True and aren't counted. When no AI key is configured the
    AI path isn't used at all, so nothing is counted either.
    """
    if not settings.anthropic_api_key or not settings.plan_limits_enabled:
        return True
    plan, _, _ = effective_plan(school)
    if plan.ai_actions_per_month is None:
        return True
    now = datetime.now(timezone.utc)
    month = _month(now)
    if school.ai_usage_month != month:
        school.ai_usage_month = month
        school.ai_usage_count = 0
    if (school.ai_usage_count or 0) >= plan.ai_actions_per_month:
        return False
    school.ai_usage_count = (school.ai_usage_count or 0) + 1
    db.commit()
    return True


def ai_limit_message(school: School) -> str:
    plan, _, _ = effective_plan(school)
    return (
        f"You've used this month's {plan.ai_actions_per_month} AI actions on the {plan.name} plan."
        f"{_upgrade_hint(plan)}"
    )


def require_ai(db: Session, school: School) -> None:
    if not use_ai(db, school):
        raise plan_limit(ai_limit_message(school))


def clean_exports(school: School) -> bool:
    if not settings.plan_limits_enabled:
        return True
    plan, _, _ = effective_plan(school)
    return plan.clean_exports
