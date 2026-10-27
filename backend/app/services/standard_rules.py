"""
The tick-box rules on the Constraints page.

Three rules nearly every school wants, offered as tick boxes instead of
sentences the admin has to type and the parser has to read:

  teacher_week_max  No teacher over N periods a week (default 30).
  teacher_day_max   No teacher over N periods a day (default 6).
  teacher_spread    Spread each teacher's periods out over the day and the
                    week: not three in a row, not two back to back when it
                    can be helped, and a similar number of periods each day.

The two caps are firm rules. A teacher whose own "max periods/week" is set
(on the Teachers page, or by a typed rule) keeps their own number - the more
specific setting wins - so the weekly cap is the default for everyone else.

Spreading is a preference: it shapes the timetable but can never make one
impossible. It is on unless the school turns it off; the two caps are off
until the school ticks them, so a school that never visits the page gets
the same timetables it got before.

Stored on School.standard_rules as only what the school changed, e.g.
{"teacher_day_max": {"on": true, "value": 7}}.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULTS: dict[str, dict] = {
    "teacher_week_max": {"on": False, "value": 30},
    "teacher_day_max": {"on": False, "value": 6},
    "teacher_spread": {"on": True},
}
LIMITS = {"teacher_week_max": (1, 80), "teacher_day_max": (1, 16)}


@dataclass(frozen=True)
class StandardRules:
    week_max: int | None   # None = off
    day_max: int | None
    spread: bool

    def weekly_cap_for(self, teacher) -> int | None:
        """The teacher's own limit if they have one, else the school's."""
        own = getattr(teacher, "max_periods_per_week", None)
        return own if own is not None else self.week_max


def merged(stored: dict | None) -> dict[str, dict]:
    """Every rule with its current settings, defaults filled in."""
    out = {k: dict(v) for k, v in DEFAULTS.items()}
    for key, val in (stored or {}).items():
        if key in out and isinstance(val, dict):
            if isinstance(val.get("on"), bool):
                out[key]["on"] = val["on"]
            if "value" in out[key] and isinstance(val.get("value"), int):
                lo, hi = LIMITS[key]
                out[key]["value"] = min(hi, max(lo, val["value"]))
    return out


def for_school(school) -> StandardRules:
    m = merged(getattr(school, "standard_rules", None) if school is not None else None)
    return StandardRules(
        week_max=m["teacher_week_max"]["value"] if m["teacher_week_max"]["on"] else None,
        day_max=m["teacher_day_max"]["value"] if m["teacher_day_max"]["on"] else None,
        spread=m["teacher_spread"]["on"],
    )


def to_store(settings: dict[str, dict]) -> dict | None:
    """Keep only what differs from the defaults."""
    out = {}
    for key, val in merged(settings).items():
        if val != DEFAULTS[key]:
            out[key] = val
    return out or None
