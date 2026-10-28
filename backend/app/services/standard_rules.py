"""
The tick-box rules on the Constraints page.

Three rules nearly every school wants, offered as tick boxes instead of
sentences the admin has to type and the parser has to read:

  teacher_week_max  No teacher over N periods a week (default 30).
  teacher_day_max   No teacher over N periods a day (default 6).
  teacher_spread    Spread each teacher's periods out over the day and the
                    week: not three in a row, not two back to back when it
                    can be helped, and a similar number of periods each day.
  core_morning      Demanding subjects (Maths, the sciences, Social Science,
                    ...) in the first N periods of the day (default 5), while
                    students are fresh; lighter ones (PE, Art, Library) later.
                    Which subjects count is guessed from their names - see
                    is_demanding - and the school can add or remove any.

The two caps are firm rules. A teacher whose own "max periods/week" is set
(on the Teachers page, or by a typed rule) keeps their own number - the more
specific setting wins - so the weekly cap is the default for everyone else.

Spreading and demanding-subjects-first are preferences: they shape the
timetable but can never make one impossible. They are on unless the school
turns them off; the two caps are off
until the school ticks them, so a school that never visits the page gets
the same timetables it got before.

Stored on School.standard_rules as only what the school changed, e.g.
{"teacher_day_max": {"on": true, "value": 7}}.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DEFAULTS: dict[str, dict] = {
    "teacher_week_max": {"on": False, "value": 30},
    "teacher_day_max": {"on": False, "value": 6},
    "teacher_spread": {"on": True},
    # include/exclude: subject ids added to, or taken out of, the ones
    # is_demanding picks - so a subject added later is still recognised.
    "core_morning": {"on": True, "value": 5, "include": [], "exclude": []},
}
LIMITS = {"teacher_week_max": (1, 80), "teacher_day_max": (1, 16), "core_morning": (1, 12)}

# Subjects that take the most concentration. Matched against the subject's
# name, so "Maths", "Mathematics - Core", "Physics", "Social Science" and
# "SST" all count. Practicals and labs are hands-on and don't. Mirrored in
# frontend/src/components/StandardRules.jsx (DEMANDING) for the tick-box list.
_DEMANDING = re.compile(
    r"math|science|physics|chemistry|biology|\bsst\b|social|history|geograph|civics|political|"
    r"economics|accountancy|accounts|business stud|statistics|\bevs\b|environmental",
    re.IGNORECASE,
)
_NOT_DEMANDING = re.compile(r"\blab\b|practical|activity|club", re.IGNORECASE)


def is_demanding(name: str) -> bool:
    return bool(_DEMANDING.search(name or "")) and not _NOT_DEMANDING.search(name or "")


@dataclass(frozen=True)
class StandardRules:
    week_max: int | None   # None = off
    day_max: int | None
    spread: bool
    core_by: int | None = None          # None = off; else "within the first N periods"
    core_include: frozenset = field(default_factory=frozenset)
    core_exclude: frozenset = field(default_factory=frozenset)

    def demanding_ids(self, subjects) -> set[int]:
        """Which of these subjects should go early in the day."""
        return {
            s.id for s in subjects
            if s.id not in self.core_exclude and (s.id in self.core_include or is_demanding(s.name))
        }

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
            for k in ("include", "exclude"):
                if k in out[key] and isinstance(val.get(k), list):
                    out[key][k] = sorted({i for i in val[k] if isinstance(i, int)})
    return out


def for_school(school) -> StandardRules:
    m = merged(getattr(school, "standard_rules", None) if school is not None else None)
    return StandardRules(
        week_max=m["teacher_week_max"]["value"] if m["teacher_week_max"]["on"] else None,
        day_max=m["teacher_day_max"]["value"] if m["teacher_day_max"]["on"] else None,
        spread=m["teacher_spread"]["on"],
        core_by=m["core_morning"]["value"] if m["core_morning"]["on"] else None,
        core_include=frozenset(m["core_morning"]["include"]),
        core_exclude=frozenset(m["core_morning"]["exclude"]),
    )


def to_store(settings: dict[str, dict]) -> dict | None:
    """Keep only what differs from the defaults."""
    out = {}
    for key, val in merged(settings).items():
        if val != DEFAULTS[key]:
            out[key] = val
    return out or None
