"""
Turns a plain-English scheduling constraint into a structured constraint.

This is a pattern-matching parser, not an LLM call - it recognizes a fixed
set of common phrasings well enough to be useful without needing an API key
or external service. It is NOT a general NLP system: unusual phrasing falls
through to a generic "scheduling_rule" bucket that's recorded but not
enforced by the solver.

Swapping this for a real LLM-based parser (e.g. calling Claude) later is a
drop-in replacement: same input (text, known teacher/subject names), same
output shape (ParsedConstraint), so nothing else has to change.

What's actually enforced by the solver today (see app/routers/constraints.py
for how each type gets turned into something the solver reads, and
app/services/solver.py for where it's applied):
  - "workload_limit" - teacher + a period count found -> sets
    Teacher.max_periods_per_week.
  - "availability" - teacher + a day of the week found -> adds that day's
    periods to Teacher.unavailable_period_ids.
  - "no_subject_period" - subject + "first period"/"last period" +
    negation ("should not", "can't", "never", ...) found -> excludes that
    subject from the first/last period of every day.
  - "require_subject_period" - subject + "first period"/"last period"
    with NO negation ("should be", "must be", "always", ...) found ->
    restricts that subject to *only* the first/last period of every day.
  - "subject_sequence" - "<subject B> can't/shouldn't/must not
    immediately follow <subject A>" -> forbids subject B from being
    scheduled in the period right after subject A, for the same class,
    on any day.
  - "no_subject_day" / "require_subject_day" - a subject tied to (or
    banned from) a specific day of the week, e.g. "No PE on Fridays" /
    "Math should be on Mondays". Same require/exclude-by-negation
    detection as the first/last-period pattern above, but for a whole day
    instead of one position.
  - "max_consecutive_periods" - "no more than N periods in a row" /
    "N consecutive periods" / "N periods back-to-back", tied to whichever
    of a subject or a teacher is named in the sentence (subject: caps how
    many of that subject can run back-to-back for a class; teacher: caps
    how many periods that teacher can teach back-to-back, any subject).
  - "min_gap_between_subjects" - "leave at least N periods between X and
    Y" / "X and Y must be at least N periods apart" -> forbids the two
    named subjects from landing within N periods of each other on the
    same day, for the same class.
  - "scheduling_rule" - the catch-all for everything else. Recorded, shown
    in the UI, but not applied to the solve. Still a real gap: things like
    per-class-only rules phrased unusually aren't recognized yet. A
    subject/teacher name that doesn't exactly match (or substring-match)
    an existing Subject/Teacher name in the school also falls through
    here - add the subject/teacher first, then the constraint.
"""
import re
from dataclasses import dataclass


@dataclass
class ParsedConstraint:
    type: str  # "workload_limit" | "availability" | "no_subject_period" | "require_subject_period" | "no_subject_day" | "require_subject_day" | "max_consecutive_periods" | "min_gap_between_subjects" | "subject_sequence" | "scheduling_rule"
    teacher_name: str | None
    subject_name: str | None
    max_periods_per_week: int | None
    day_of_week: int | None  # 0=Monday .. 6=Sunday, matches Period.day_of_week
    position: str | None  # "first" | "last"
    description: str
    first_subject_name: str | None = None
    second_subject_name: str | None = None
    max_consecutive: int | None = None
    min_gap: int | None = None


_PERIODS_RE = re.compile(r"(\d+)\s*period", re.IGNORECASE)
_FIRST_LAST_RE = re.compile(r"\b(first|last)\s+period\b", re.IGNORECASE)
# "no more than 2 periods in a row" / "at most 3 consecutive periods" /
# "3 periods back-to-back" - either order, number first or number last.
_CONSECUTIVE_RE = re.compile(
    r"(?:no\s+more\s+than|not\s+more\s+than|at\s+most|max(?:imum)?\s+(?:of\s+)?)\s*(\d+)\s+"
    r"(?:consecutive\s+periods|periods?\s+in\s+a\s+row|back-to-back\s+periods?)"
    r"|(\d+)\s+(?:consecutive\s+periods|periods?\s+in\s+a\s+row|back-to-back\s+periods?)",
    re.IGNORECASE,
)
# "leave at least 1 period between PE and Math" / "PE and Math must be at
# least 2 periods apart" - just the gap count; which two subjects is
# resolved separately via _find_two_subjects.
_GAP_RE = re.compile(
    r"at\s+least\s+(\d+)\s+periods?\s+(?:apart|between|gap)",
    re.IGNORECASE,
)
# "Math can't immediately follow PE" / "Math should not directly follow PE" /
# "Math cannot come right after PE" - captures (second_subject, first_subject),
# since "X follows Y" means Y happens first.
_SEQUENCE_RE = re.compile(
    r"(.+?)\s+(?:can'?t|cannot|should\s+not|shouldn'?t|must\s+not|mustn'?t)\s+"
    r"(?:immediately\s+|directly\s+|right\s+)?follow\s+(.+)",
    re.IGNORECASE,
)
_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_AVAILABILITY_WORDS = [
    "morning", "afternoon", "not available", "unavailable", "can't teach", "cannot teach",
]
_NEGATION_WORDS = [
    "not ", "n't", "never", "cannot", "can't", "shouldn't", "won't", "don't", "doesn't", "no ",
]


def _is_negated(text: str) -> bool:
    """Whether the text expresses a prohibition ("should NOT be first
    period") rather than a requirement ("SHOULD be first period"). Simple
    whole-sentence keyword check - good enough for short one-clause
    constraint sentences, which is what the UI is designed for."""
    lower = f" {text.lower()} "
    return any(word in lower for word in _NEGATION_WORDS)


def _find_by_name(text: str, names: list[str]) -> str | None:
    """Match an entity by name appearing in the text. Tries the longest
    known name first so multi-word names (e.g. "Physical Education") beat
    a shorter false-positive substring, then falls back to last-word
    matching for people's names typed without a title ("Sharma" ->
    "Priya Sharma"). Uses word-boundary matching for short names (<=3
    chars, e.g. subject codes like "PE" or "PT") so they don't spuriously
    match as a substring of an unrelated longer word - "PE" inside
    "periods" being the motivating case that broke the max-consecutive
    regex path when the sentence mentioned both a teacher and the word
    "periods" but no actual subject."""
    lower = text.lower()
    for name in sorted(names, key=len, reverse=True):
        n = name.strip().lower()
        if not n:
            continue
        if len(n) <= 3:
            if re.search(rf"\b{re.escape(n)}\b", lower):
                return name
        elif n in lower:
            return name
    for name in names:
        last_word = name.strip().split(" ")[-1].lower()
        if last_word and re.search(rf"\b{re.escape(last_word)}\b", lower):
            return name
    return None


def _find_teacher(text: str, teacher_names: list[str]) -> str | None:
    return _find_by_name(text, teacher_names)


def _find_subject(text: str, subject_names: list[str]) -> str | None:
    return _find_by_name(text, subject_names)


def _find_two_subjects(text: str, subject_names: list[str]) -> tuple[str | None, str | None]:
    """For rules naming two subjects at once ("leave a gap between PE and
    Math") - finds every subject name that appears in the text and returns
    the first two, in the order they appear. Longest names are matched
    first so e.g. "Physical Education" isn't shadowed by a shorter
    coincidental substring match."""
    lower = text.lower()
    hits: list[tuple[int, str]] = []
    for name in sorted(subject_names, key=len, reverse=True):
        idx = lower.find(name.strip().lower())
        if idx != -1 and not any(name == found for _, found in hits):
            hits.append((idx, name))
    hits.sort(key=lambda pair: pair[0])
    names = [name for _, name in hits[:2]]
    if len(names) < 2:
        return None, None
    return names[0], names[1]


def _find_day(text: str) -> int | None:
    lower = text.lower()
    for i, day in enumerate(_DAY_NAMES):
        if day in lower:
            return i
    return None


def _empty(**overrides) -> dict:
    base = dict(max_periods_per_week=None, day_of_week=None, position=None)
    base.update(overrides)
    return base


def parse_constraint(text: str, teacher_names: list[str], subject_names: list[str] | None = None) -> ParsedConstraint:
    subject_names = subject_names or []
    teacher = _find_teacher(text, teacher_names)
    subject = _find_subject(text, subject_names)

    # "Math can't immediately follow PE" - cross-subject sequencing. Checked
    # before the general subject match above since it needs two subjects,
    # not one, and "follow" text would otherwise fall through unrecognized.
    sequence_match = _SEQUENCE_RE.search(text)
    if sequence_match:
        second = _find_subject(sequence_match.group(1), subject_names)
        first = _find_subject(sequence_match.group(2), subject_names)
        if first and second:
            return ParsedConstraint(
                type="subject_sequence",
                teacher_name=teacher,
                subject_name=None,
                **_empty(),
                description=f"{second} must not be scheduled immediately after {first}",
                first_subject_name=first,
                second_subject_name=second,
            )

    # "Leave at least 1 period between PE and Math" - needs two subject
    # names, so checked before the single-subject patterns below (which
    # would otherwise just grab whichever one comes first in the text).
    gap_match = _GAP_RE.search(text)
    if gap_match:
        first_gap, second_gap = _find_two_subjects(text, subject_names)
        if first_gap and second_gap:
            gap = int(gap_match.group(1))
            return ParsedConstraint(
                type="min_gap_between_subjects",
                teacher_name=None,
                subject_name=None,
                **_empty(),
                description=f"Leave at least {gap} period(s) between {first_gap} and {second_gap}",
                first_subject_name=first_gap,
                second_subject_name=second_gap,
                min_gap=gap,
            )

    # "no more than 2 periods in a row" for a subject or a teacher - checked
    # before the single first/last-period pattern since both can mention a
    # subject, but this one needs the explicit consecutive/row/back-to-back
    # phrasing to trigger.
    consecutive_match = _CONSECUTIVE_RE.search(text)
    if consecutive_match:
        raw = consecutive_match.group(1) or consecutive_match.group(2)
        max_consecutive = int(raw)
        if teacher and not subject:
            return ParsedConstraint(
                type="max_consecutive_periods",
                teacher_name=teacher,
                subject_name=None,
                **_empty(),
                description=f"{teacher} should not teach more than {max_consecutive} periods in a row",
                max_consecutive=max_consecutive,
            )
        if subject:
            return ParsedConstraint(
                type="max_consecutive_periods",
                teacher_name=None,
                subject_name=subject,
                **_empty(),
                description=f"No more than {max_consecutive} consecutive periods of {subject}",
                max_consecutive=max_consecutive,
            )

    # "Math should not be the first period" (exclude) vs.
    # "French should be the first period" (require) - same pattern,
    # opposite meaning depending on whether the sentence is negated.
    first_last_match = _FIRST_LAST_RE.search(text)
    if first_last_match and subject:
        position = first_last_match.group(1).lower()
        negated = _is_negated(text)
        if negated:
            return ParsedConstraint(
                type="no_subject_period",
                teacher_name=teacher,
                subject_name=subject,
                **_empty(position=position),
                description=f"{subject} should not be scheduled in the {position} period of the day",
            )
        return ParsedConstraint(
            type="require_subject_period",
            teacher_name=teacher,
            subject_name=subject,
            **_empty(position=position),
            description=f"{subject} should always be scheduled in the {position} period of the day",
        )

    # "No PE on Fridays" (exclude) / "Math should be on Mondays" (require) - 
    # a subject tied to a whole day, not a teacher's availability (that
    # pattern requires a teacher name, checked further below). Only
    # triggers when a subject matched and no teacher did, so it doesn't
    # shadow the teacher-availability pattern.
    day_for_subject = _find_day(text)
    if subject and not teacher and day_for_subject is not None:
        day_label = f"{_DAY_NAMES[day_for_subject].capitalize()}s"
        if _is_negated(text):
            return ParsedConstraint(
                type="no_subject_day",
                teacher_name=None,
                subject_name=subject,
                **_empty(day_of_week=day_for_subject),
                description=f"{subject} should not be scheduled on {day_label}",
            )
        return ParsedConstraint(
            type="require_subject_day",
            teacher_name=None,
            subject_name=subject,
            **_empty(day_of_week=day_for_subject),
            description=f"{subject} should only be scheduled on {day_label}",
        )

    # "Mrs. Sharma can only teach 10 periods a week"
    periods_match = _PERIODS_RE.search(text.lower())
    if periods_match:
        max_periods = int(periods_match.group(1))
        description = (
            f"Max {max_periods} periods per week for {teacher}" if teacher else text
        )
        return ParsedConstraint(
            type="workload_limit",
            teacher_name=teacher,
            subject_name=subject,
            **_empty(max_periods_per_week=max_periods),
            description=description,
        )

    # "Priya Sharma is not available on Wednesdays"
    day = _find_day(text)
    if day is not None and teacher:
        description = f"{teacher} is not available on {_DAY_NAMES[day].capitalize()}s"
        return ParsedConstraint(
            type="availability",
            teacher_name=teacher,
            subject_name=subject,
            **_empty(day_of_week=day),
            description=description,
        )

    lower = text.lower()
    if day is not None or any(word in lower for word in _AVAILABILITY_WORDS):
        return ParsedConstraint(
            type="availability",
            teacher_name=teacher,
            subject_name=subject,
            **_empty(day_of_week=day),
            description=text,
        )

    return ParsedConstraint(
        type="scheduling_rule",
        teacher_name=teacher,
        subject_name=subject,
        **_empty(),
        description=text,
    )
