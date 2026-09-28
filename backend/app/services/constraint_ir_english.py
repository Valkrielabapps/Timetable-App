"""
Render an IR rule back into a sentence a school admin can check.

This is the echo-back. Once rules go through the IR, the parser almost always
produces *something* well-formed - the "doesn't fit any type" escape hatch that
used to make a misreading visible is gone. A model that misreads "Arjun only
comes on Monday" as an availability rule *for* Monday emits a perfectly valid
rule, and the solver enforces it faithfully, and the timetable is wrong with no
error anywhere. The only party who can catch that is the person who wrote the
sentence, and they can only catch it if they are shown what was understood.

So this module is not a debugging aid. It is the safety mechanism, and the
sentences it produces are read by people who will not be reading the JSON.

Principles, in the order they win:

  1. Unambiguous. Two different rules must never render the same way. If a
     phrasing reads well but blurs a distinction, the distinction wins.
  2. Complete. Every field that changes the meaning appears in the sentence. A
     scope or a filter left out of the English is a misreading the admin cannot
     see.
  3. Natural. Only after the first two - and the fallback for an odd
     combination is stilted English, never a silently dropped clause.

Wording here is meant to be reviewed and revised by someone who knows how their
schools actually talk; the structure is the part that should stay.
"""
from __future__ import annotations

from .constraint_ir import (
    DAY_NAMES,
    Adjacency,
    Bucket,
    Conditional,
    Count,
    Form,
    Rule,
    Run,
    Selector,
)

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _join(items, conjunction: str = "and") -> str:
    """Oxford-comma-free list: "a", "a and b", "a, b and c"."""
    items = [str(i) for i in items]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} {conjunction} {items[-1]}"


def _days(days) -> str:
    return _join([DAY_NAMES[d] if 0 <= d < len(DAY_NAMES) else f"day {d}" for d in days], "or")


def _periods(orders) -> str:
    if len(orders) == 1:
        return f"period {orders[0]}"
    return f"periods {_join(orders, 'or')}"


def _plural(n: int, singular: str, plural: str | None = None) -> str:
    return singular if n == 1 else (plural or f"{singular}s")


# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------


def _lesson_noun(sel: Selector) -> str:
    """What is being counted - "Maths periods", "periods", "PE or Art periods".

    Deliberately says "periods" rather than "lessons" throughout: a timetable
    is discussed in periods, and mixing the two words would make two renderings
    of the same rule look like different rules.
    """
    if sel.subjects:
        return f"{_join(sel.subjects, 'or')} periods"
    if sel.not_subjects:
        return f"periods other than {_join(sel.not_subjects, 'or')}"
    return "periods"


def _whose(sel: Selector, skip: frozenset[str] = frozenset()) -> str:
    """The possessive part - "Mrs. Rao's", "Grade 8's", or both."""
    parts = []
    if sel.teachers and "teachers" not in skip:
        parts.append(_join([f"{t}'s" for t in sel.teachers], "or"))
    if sel.class_groups and "class_groups" not in skip:
        # Attributive, not possessive: "at least 1 Grade 12 period" rather than
        # "at least 1 Grade 12's period", which a count makes unreadable.
        parts.append(_join(sel.class_groups, "or"))
    return " ".join(parts)


def _when(sel: Selector) -> str:
    """The time filter - "in period 1 on Tuesday"."""
    parts = []
    if sel.period_orders:
        parts.append(f"in {_periods(sel.period_orders)}")
    if sel.days:
        parts.append(f"on {_days(sel.days)}")
    return " ".join(parts)


def _describe_lessons(sel: Selector, skip: frozenset[str] = frozenset()) -> str:
    """A full noun phrase for the lessons a selector picks out.

    `skip` names selector fields the sentence has already used elsewhere - the
    scope subject consumes "teachers" or "class_groups" when it groups by them,
    and repeating those gives "For Grade 11, Grade 11's Biology periods".
    Anything not skipped must appear, because a filter missing from the English
    is a misreading the admin cannot see.
    """
    whose = _whose(sel, skip)
    noun = _lesson_noun(sel)
    when = _when(sel)
    phrase = f"{whose} {noun}".strip() if whose else noun
    return f"{phrase} {when}".strip() if when else phrase


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


def _scope_subject(scope: tuple[str, ...], sel: Selector) -> tuple[str, frozenset[str]]:
    """The grammatical subject of the sentence, and which selector fields it used.

    When the scope groups by teacher or class group, that is what the sentence
    is about. When it doesn't, the selector names who - and if neither does,
    the rule is about the school as a whole.

    The second return value is what the caller must NOT repeat: naming Grade 11
    as the subject and again as a possessive reads as two different things.
    Anything not in that set still has to appear somewhere in the sentence.
    """
    parts: list[str] = []
    used: set[str] = set()
    if "teacher" in scope:
        parts.append(_join(sel.teachers, "or") if sel.teachers else "every teacher")
        used.add("teachers")
    if "class_group" in scope:
        parts.append(_join(sel.class_groups, "or") if sel.class_groups else "every class")
        used.add("class_groups")
    if "subject" in scope:
        parts.append("each subject")
    if parts:
        return _join(parts), frozenset(used)
    # No grouping by who: the selector's own names carry it.
    if sel.teachers:
        return _join(sel.teachers, "or"), frozenset({"teachers"})
    if sel.class_groups:
        return _join(sel.class_groups, "or"), frozenset({"class_groups"})
    return "the school", frozenset()


def _scope_time(scope: tuple[str, ...], sel: Selector) -> str:
    """The time framing a scope implies.

    Suppressed when the selector already names days, so "Mrs. Rao has no
    periods on Saturday" doesn't become "...in the week on Saturday".
    """
    if sel.days or sel.period_orders:
        return ""
    if "period" in scope:
        return "in every period"
    if "day" in scope:
        return "on any day"
    return "in the week"


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


def _amount(relation: str, value: int, noun: str) -> str:
    """"no periods", "at most 6 periods", "at least 1 Maths period"."""
    if relation == "==" and value == 0:
        return f"no {noun}"
    singular = noun.endswith("s") and value == 1
    shown = noun[:-1] if singular else noun
    if relation == "<=":
        return f"at most {value} {shown}"
    if relation == ">=":
        return f"at least {value} {shown}"
    return f"exactly {value} {shown}"


def _render_count(form: Count, suppress_time: bool = False) -> str:
    sel = form.selector
    subject, used = _scope_subject(form.scope, sel)
    time = "" if suppress_time else _scope_time(form.scope, sel)

    if form.distinct:
        unit = {"subject": "different subjects", "teacher": "different teachers",
                "class_group": "different classes"}[form.distinct]
        amount = _amount(form.relation, form.value, unit)
        # "different subjects" already reads as a count, so the lesson noun is
        # dropped - but any filter narrowing *which* lessons are counted still
        # has to be said.
        narrowing = " ".join(p for p in (_whose(sel, used), _when(sel)) if p)
        tail = f" among {narrowing}" if _whose(sel, used) else (f" {_when(sel)}" if sel.days or sel.period_orders else "")
        sentence = f"{subject} has {amount}{tail}"
    else:
        whose = _whose(sel, used)
        noun = _lesson_noun(sel)
        noun = f"{whose} {noun}" if whose else noun
        amount = _amount(form.relation, form.value, noun)
        when = _when(sel)
        tail = f" {when}" if when else ""
        sentence = f"{subject} has {amount}{tail}"

    if time:
        sentence = f"{sentence} {time}"

    # "Every class has no PE periods" is grammatical and horrible. The negative
    # belongs on the subject when the subject is a universal.
    for universal in ("every class", "every teacher"):
        if sentence.startswith(f"{universal} has no "):
            rest = sentence[len(f"{universal} has no "):]
            return f"no {universal[len('every '):]} has {rest}"
    return sentence


def _render_run(form: Run) -> str:
    subject, used = _scope_subject(form.scope, form.selector)
    lessons = _describe_lessons(form.selector, used)
    clauses = []
    if form.block_size is not None:
        clauses.append(
            f"{lessons} are scheduled in blocks of {form.block_size} consecutive periods"
        )
    if form.max_consecutive is not None:
        n = form.max_consecutive
        if n == 1:
            clauses.append(f"no two {lessons} are back to back")
        else:
            clauses.append(
                f"no more than {n} {lessons} run back to back"
            )
    body = _join(clauses)
    # A run is always within a day - saying so removes the reading where the
    # count carries across days.
    return f"for {subject}, {body} on any day"


def _render_adjacency(form: Adjacency) -> str:
    subject, used = _scope_subject(form.scope, form.first)
    first = _describe_lessons(form.first, used)
    second = _describe_lessons(form.second, used)

    if form.must_follow:
        return f"for {subject}, {second} come in the period straight after {first}"

    if form.min_gap == 1:
        if form.directional:
            return f"for {subject}, {second} never come in the period straight after {first}"
        return f"for {subject}, {first} and {second} are never back to back, in either order"

    gap = form.min_gap
    periods = _plural(gap, "period")
    if form.directional:
        return (
            f"for {subject}, {second} come at least {gap} {periods} after {first}, "
            f"never sooner"
        )
    return f"for {subject}, {first} and {second} are at least {gap} {periods} apart on the same day"


def _render_bucket(form: Bucket) -> str:
    subject, used = _scope_subject(form.scope, form.first)
    first = _describe_lessons(form.first, used)
    second = _describe_lessons(form.second, used)
    unit = "day" if form.dimension == "day" else "period"
    if form.relation == "same":
        if form.dimension == "period":
            return f"for {subject}, {first} and {second} are scheduled at the same time"
        return f"for {subject}, {first} and {second} fall on the same {unit}"
    if form.dimension == "period":
        return f"for {subject}, {first} and {second} are never scheduled at the same time"
    return f"for {subject}, {first} and {second} never fall on the same {unit}"


def _render_conditional(form: Conditional) -> str:
    condition = _render_count(form.when)
    if isinstance(form.then, Count) and form.then.scope == form.when.scope:
        # "...on any day, ... on any day" - the condition already framed it.
        consequence = _render_count(form.then, suppress_time=True)
    else:
        consequence = render_form(form.then)
    return f"wherever {condition}, {consequence}"


def render_form(form: Form) -> str:
    if isinstance(form, Count):
        return _render_count(form)
    if isinstance(form, Run):
        return _render_run(form)
    if isinstance(form, Adjacency):
        return _render_adjacency(form)
    if isinstance(form, Bucket):
        return _render_bucket(form)
    if isinstance(form, Conditional):
        return _render_conditional(form)
    raise TypeError(f"cannot render {type(form).__name__}")


_STRENGTH_PREFIX = {
    "required": "",
    # Said out loud rather than shown as a badge: an admin confirming a rule
    # needs to see that it can be broken, and a preference silently treated as
    # a requirement (or the reverse) is exactly the kind of misreading this
    # sentence exists to catch.
    "strong_preference": "As far as possible, ",
    "preference": "Where it can be arranged, ",
}


def render(rule: Rule) -> str:
    """The sentence shown to the admin for confirmation."""
    body = render_form(rule.form)
    prefix = _STRENGTH_PREFIX.get(rule.strength, "")
    sentence = f"{prefix}{body}" if prefix else body
    sentence = sentence.strip()
    if not sentence:
        return ""
    return sentence[0].upper() + sentence[1:] + "."
