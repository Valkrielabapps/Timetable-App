"""
A general representation for scheduling rules.

Why this exists
---------------
Until now a parsed rule had to be one of nine named types, and anything else
became `scheduling_rule` - saved, shown, never applied. Measured against
docs/research/constraint-catalogue.tsv, 187 rules written the way school staff
actually write them, that covered about one rule in seven.

The nine types were not too few because nobody got round to adding a tenth.
They were too few because a type is written per *rule*, and a principal's
vocabulary is open-ended. The catalogue makes the alternative visible: sort
those rules by the shape of the arithmetic rather than by subject matter and
they collapse into five.

    count       for each <scope>, the number of lessons matching <selector>
                must be <relation> N
    run         for each <scope>, lessons matching <selector> may not run more
                than N periods back to back (or must run in blocks of N)
    adjacency   for each <scope>, lessons matching <first> and <second> must be
                at least <min_gap> periods apart
    bucket      for each <scope>, lessons matching <first> and <second> must
                fall on the same / a different <dimension>
    conditional any of the above, enforced only where another count holds

"Placement" is deliberately absent. A rule that forbids something is a count of
zero and a rule that requires something is a count of at least one, so folding
them in costs nothing and removes a form the model would otherwise have to
choose between - one fewer way to be wrong.

What a form does NOT decide
---------------------------
The five forms say what arithmetic to apply. Two orthogonal things say where:

  SELECTOR  which lessons the rule is about - by subject, teacher, class group,
            day, or position in the day. Fields are ANDed; values within a
            field are ORed. An empty selector means every lesson.

  SCOPE     the grouping the arithmetic applies over, independently per group.
            scope=["teacher", "day"] with count <= 6 is "no teacher teaches
            more than 6 periods in a day" - one constraint per teacher per day.
            scope=[] is a single constraint across the whole school.

That split is what lets five forms cover a hundred rules. "No teacher more than
6 periods a day", "Priya at most 28 a week", "at most 3 heavy subjects in a
day" and "the computer lab at most 35 periods a week" are all one form; they
differ only in scope and selector.

Names, not ids
--------------
Unlike the nine legacy types, an IR rule stores teacher/subject/class-group
*names*, resolved to rows when the solver runs. Three reasons: the echo-back
has to render a rule as English before it is ever saved, so names must survive
that far regardless; a stored rule stays readable in the database, which is the
point of the provenance work; and a rule naming a teacher who has since been
deleted should say so rather than quietly matching nothing.

This module is pure data. It builds no CP-SAT model and touches no database, so
validation and rendering are testable without either.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# Dimensions a rule can group by. "period" means one group per slot in the week
# (for rules like "at least one English teacher is free in every period");
# "day" means one group per weekday.
SCOPE_DIMENSIONS = ("teacher", "class_group", "subject", "day", "period")

RELATIONS = ("<=", ">=", "==")

# What a bucket form can compare two sets of lessons on.
BUCKET_DIMENSIONS = ("day", "period")

STRENGTHS = ("required", "strong_preference", "preference")

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_SELECTOR_FIELDS = ("subjects", "not_subjects", "teachers", "class_groups", "days", "period_orders")


class IRError(ValueError):
    """A rule that cannot be represented, with a reason meant for a person.

    Raised rather than returned because every caller either shows this text to
    an admin or fails the parse - no path carries on with an invalid rule, and
    an exception keeps that guarantee rather than relying on each caller to
    check a flag.
    """


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Selector:
    """Which lessons a rule is about.

    Every field is a filter and they are ANDed: subjects=["PE"], days=[4] means
    "PE lessons on Friday", not "PE lessons or Friday lessons". Values inside
    one field are ORed, so days=[0, 2, 4] is Monday, Wednesday or Friday.

    All-None means every lesson in the school, which is what rules about
    teacher load ("no teacher more than 6 a day") need - they care about the
    count, not about which subject it was.
    """

    subjects: tuple[str, ...] | None = None
    # Negation gets its own field rather than a general not-expression:
    # "theory periods" means "not PE, Art, Music or Library" and recurs through
    # the catalogue, while a nested boolean language would be far more than
    # those rules need and far more than a model reliably emits.
    not_subjects: tuple[str, ...] | None = None
    teachers: tuple[str, ...] | None = None
    class_groups: tuple[str, ...] | None = None
    days: tuple[int, ...] | None = None
    period_orders: tuple[int, ...] | None = None

    def is_empty(self) -> bool:
        return all(getattr(self, f) is None for f in _SELECTOR_FIELDS)

    def names(self) -> dict[str, tuple[str, ...]]:
        """Every name this selector expects to exist, by kind, so a caller can
        check them against the school before the rule is saved."""
        return {
            "subject": (self.subjects or ()) + (self.not_subjects or ()),
            "teacher": self.teachers or (),
            "class_group": self.class_groups or (),
        }


def _as_str_tuple(value, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise IRError(f"{field_name} must be a list of names, got {type(value).__name__}")
    out = tuple(str(v).strip() for v in value if str(v).strip())
    return out or None


def _as_int_tuple(value, field_name: str, low: int, high: int) -> tuple[int, ...] | None:
    if value is None:
        return None
    if isinstance(value, (int, str)):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise IRError(f"{field_name} must be a list of numbers, got {type(value).__name__}")
    out = []
    for item in value:
        if isinstance(item, bool):
            raise IRError(f"{field_name} must contain numbers, not true/false")
        try:
            n = int(item)
        except (TypeError, ValueError):
            raise IRError(f"{field_name} must contain numbers, got {item!r}") from None
        if not low <= n <= high:
            raise IRError(f"{field_name} value {n} is outside the allowed range {low}-{high}")
        out.append(n)
    return tuple(dict.fromkeys(out)) or None


def selector_from_dict(data: dict | None) -> Selector:
    if data is None:
        return Selector()
    if not isinstance(data, dict):
        raise IRError(f"selector must be an object, got {type(data).__name__}")
    unknown = set(data) - set(_SELECTOR_FIELDS)
    if unknown:
        raise IRError(f"selector has unknown field(s): {', '.join(sorted(unknown))}")
    sel = Selector(
        subjects=_as_str_tuple(data.get("subjects"), "selector.subjects"),
        not_subjects=_as_str_tuple(data.get("not_subjects"), "selector.not_subjects"),
        teachers=_as_str_tuple(data.get("teachers"), "selector.teachers"),
        class_groups=_as_str_tuple(data.get("class_groups"), "selector.class_groups"),
        days=_as_int_tuple(data.get("days"), "selector.days", 0, 6),
        # Period numbering is per school; 30 is a ceiling no real school reaches,
        # here to catch a model answering with minutes or a clock time.
        period_orders=_as_int_tuple(data.get("period_orders"), "selector.period_orders", 0, 30),
    )
    if sel.subjects and sel.not_subjects and set(sel.subjects) & set(sel.not_subjects):
        both = sorted(set(sel.subjects) & set(sel.not_subjects))
        raise IRError(f"selector both includes and excludes: {', '.join(both)}")
    return sel


def selector_to_dict(sel: Selector) -> dict:
    out: dict = {}
    for name in _SELECTOR_FIELDS:
        value = getattr(sel, name)
        if value is not None:
            out[name] = list(value)
    return out


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Count:
    """For each group in `scope`, the number of matching lessons `relation` `value`.

    The workhorse. A ban is value=0, a requirement is relation=">=" value=1, and
    a cap is relation="<=".

    `distinct` changes what is counted: with distinct="subject" the count is of
    how many *different* subjects appear, not how many lessons - which is what
    "at most 6 different subjects a day" and "no teacher more than 6 sections"
    are asking for.
    """

    scope: tuple[str, ...]
    selector: Selector
    relation: str
    value: int
    distinct: str | None = None


@dataclass(frozen=True)
class Run:
    """For each group in `scope`, how many matching lessons may sit back to back.

    max_consecutive caps a run ("not more than 2 Maths in a row", "no double
    English" is max 1). block_size requires one ("practicals need two periods
    together"). At least one must be set.

    Runs are counted within a day and broken by breaks, so a lesson before lunch
    and one after are not adjacent - the solver already splits days this way for
    the legacy max_consecutive type.
    """

    scope: tuple[str, ...]
    selector: Selector
    max_consecutive: int | None = None
    block_size: int | None = None


@dataclass(frozen=True)
class Adjacency:
    """For each group in `scope`, how close `first` and `second` may be.

    min_gap is the number of periods that must separate them, so min_gap=1
    forbids them being back to back and min_gap=0 forbids nothing.

    `directional` is the distinction the legacy types got wrong often enough to
    need its own field: "Maths can't come right after PE" forbids one order,
    while "Maths and PE shouldn't be next to each other" forbids both. With
    directional=True only second-after-first is forbidden.
    """

    scope: tuple[str, ...]
    first: Selector
    second: Selector
    min_gap: int = 1
    directional: bool = False
    # For "Physics practical must come right after Physics theory" - the
    # inverse of a forbidden adjacency, where the two must be adjacent and in
    # this order. min_gap is ignored when this is set.
    must_follow: bool = False


@dataclass(frozen=True)
class Bucket:
    """For each group in `scope`, whether `first` and `second` share a `dimension`.

    dimension="day" with relation="different" is "keep Physics and Chemistry on
    different days". dimension="period" with relation="same" is how parallel
    scheduling is expressed: two sets of lessons that must happen at the same
    time, which is what electives, combined sections and staff meetings need.
    """

    scope: tuple[str, ...]
    first: Selector
    second: Selector
    dimension: str
    relation: str  # "same" | "different"


@dataclass(frozen=True)
class Conditional:
    """`then` is enforced only in the groups where `when` holds.

    Both are evaluated per group in the shared `scope`, which is what makes "if
    a teacher has 7 periods one day, the next day is at most 5" and "on days
    Priya teaches Grade 12, she teaches at most 5 periods" expressible without
    a rule language of their own.
    """

    scope: tuple[str, ...]
    when: Count
    then: Count | Run | Adjacency | Bucket


Form = Count | Run | Adjacency | Bucket | Conditional


@dataclass(frozen=True)
class Rule:
    """One scheduling rule: a form, how firmly it is meant, and what it says.

    `description` is the English the admin confirmed, kept alongside the form so
    the UI never has to re-render a rule to show it - and so a rule stays
    readable even if the renderer changes later.
    """

    form: Form
    strength: str = "required"
    description: str = ""


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------


def _scope_from(value, allow_empty: bool = True) -> tuple[str, ...]:
    if value is None:
        value = []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise IRError(f"scope must be a list, got {type(value).__name__}")
    out = []
    for item in value:
        name = str(item).strip().lower()
        if name not in SCOPE_DIMENSIONS:
            raise IRError(
                f"scope cannot group by {item!r}; allowed: {', '.join(SCOPE_DIMENSIONS)}"
            )
        if name not in out:
            out.append(name)
    if not out and not allow_empty:
        raise IRError("scope cannot be empty for this form")
    return tuple(out)


def _int_from(value, field_name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or value is None:
        raise IRError(f"{field_name} must be a number")
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise IRError(f"{field_name} must be a number, got {value!r}") from None
    if not low <= n <= high:
        raise IRError(f"{field_name} must be between {low} and {high}, got {n}")
    return n


def _count_from_dict(data: dict) -> Count:
    relation = str(data.get("relation", "")).strip()
    if relation not in RELATIONS:
        raise IRError(f"relation must be one of {', '.join(RELATIONS)}, got {relation!r}")
    distinct = data.get("distinct")
    if distinct is not None:
        distinct = str(distinct).strip().lower()
        # Counting distinct teachers or class groups is what "at most 2
        # different teachers for 8A Maths" and "no teacher more than 6
        # sections" need; distinct days would be a spread rule, which is a
        # bucket, so it is not offered here.
        if distinct not in ("subject", "teacher", "class_group"):
            raise IRError(
                f"distinct must be subject, teacher or class_group, got {distinct!r}"
            )
    return Count(
        scope=_scope_from(data.get("scope")),
        selector=selector_from_dict(data.get("selector")),
        relation=relation,
        value=_int_from(data.get("value"), "value", 0, 500),
        distinct=distinct,
    )


def _run_from_dict(data: dict) -> Run:
    max_consecutive = data.get("max_consecutive")
    block_size = data.get("block_size")
    if max_consecutive is None and block_size is None:
        raise IRError("a run rule needs max_consecutive or block_size")
    run = Run(
        scope=_scope_from(data.get("scope")),
        selector=selector_from_dict(data.get("selector")),
        max_consecutive=None if max_consecutive is None else _int_from(max_consecutive, "max_consecutive", 1, 30),
        block_size=None if block_size is None else _int_from(block_size, "block_size", 2, 30),
    )
    if run.max_consecutive is not None and run.block_size is not None and run.block_size > run.max_consecutive:
        raise IRError(
            f"a block of {run.block_size} cannot fit under a maximum run of {run.max_consecutive}"
        )
    if run.selector.is_empty():
        # Without a selector this caps every lesson of every kind back to back,
        # which is never what a run rule means and is usually the model having
        # dropped the subject.
        raise IRError("a run rule needs a selector saying which lessons form the run")
    return run


def _adjacency_from_dict(data: dict) -> Adjacency:
    must_follow = bool(data.get("must_follow", False))
    adj = Adjacency(
        scope=_scope_from(data.get("scope")),
        first=selector_from_dict(data.get("first")),
        second=selector_from_dict(data.get("second")),
        min_gap=1 if must_follow else _int_from(data.get("min_gap", 1), "min_gap", 1, 30),
        directional=bool(data.get("directional", False)),
        must_follow=must_follow,
    )
    if adj.first.is_empty() or adj.second.is_empty():
        raise IRError("an adjacency rule needs both sides to say which lessons they mean")
    return adj


def _bucket_from_dict(data: dict) -> Bucket:
    dimension = str(data.get("dimension", "")).strip().lower()
    if dimension not in BUCKET_DIMENSIONS:
        raise IRError(f"dimension must be day or period, got {dimension!r}")
    relation = str(data.get("relation", "")).strip().lower()
    if relation not in ("same", "different"):
        raise IRError(f"a bucket relation must be same or different, got {relation!r}")
    bucket = Bucket(
        scope=_scope_from(data.get("scope")),
        first=selector_from_dict(data.get("first")),
        second=selector_from_dict(data.get("second")),
        dimension=dimension,
        relation=relation,
    )
    if bucket.first.is_empty() or bucket.second.is_empty():
        raise IRError("a bucket rule needs both sides to say which lessons they mean")
    return bucket


def _conditional_from_dict(data: dict) -> Conditional:
    when = data.get("when")
    then = data.get("then")
    if not isinstance(when, dict) or not isinstance(then, dict):
        raise IRError("a conditional rule needs both when and then")
    when_form = _count_from_dict(when)
    then_form = form_from_dict(then)
    if isinstance(then_form, Conditional):
        # Nested conditionals are representable but nothing in the catalogue
        # needs one, and they make the echo-back unreadable - which is the one
        # thing standing between a misreading and a wrong timetable.
        raise IRError("a conditional rule cannot contain another conditional")
    return Conditional(scope=_scope_from(data.get("scope")), when=when_form, then=then_form)


_FORM_PARSERS = {
    "count": _count_from_dict,
    "run": _run_from_dict,
    "adjacency": _adjacency_from_dict,
    "bucket": _bucket_from_dict,
    "conditional": _conditional_from_dict,
}


def form_from_dict(data: dict) -> Form:
    if not isinstance(data, dict):
        raise IRError(f"a rule must be an object, got {type(data).__name__}")
    name = str(data.get("form", "")).strip().lower()
    parser = _FORM_PARSERS.get(name)
    if parser is None:
        raise IRError(
            f"unknown form {name!r}; allowed: {', '.join(sorted(_FORM_PARSERS))}"
        )
    return parser(data)


def rule_from_dict(data: dict) -> Rule:
    """Validate one IR document. Raises IRError with a readable reason."""
    if not isinstance(data, dict):
        raise IRError(f"a rule must be an object, got {type(data).__name__}")
    strength = data.get("strength") or "required"
    strength = str(strength).strip().lower()
    if strength not in STRENGTHS:
        raise IRError(f"strength must be one of {', '.join(STRENGTHS)}, got {strength!r}")
    return Rule(
        form=form_from_dict(data),
        strength=strength,
        description=str(data.get("description") or "").strip(),
    )


def _form_to_dict(form: Form) -> dict:
    if isinstance(form, Count):
        out = {
            "form": "count",
            "scope": list(form.scope),
            "selector": selector_to_dict(form.selector),
            "relation": form.relation,
            "value": form.value,
        }
        if form.distinct:
            out["distinct"] = form.distinct
        return out
    if isinstance(form, Run):
        out = {"form": "run", "scope": list(form.scope), "selector": selector_to_dict(form.selector)}
        if form.max_consecutive is not None:
            out["max_consecutive"] = form.max_consecutive
        if form.block_size is not None:
            out["block_size"] = form.block_size
        return out
    if isinstance(form, Adjacency):
        return {
            "form": "adjacency",
            "scope": list(form.scope),
            "first": selector_to_dict(form.first),
            "second": selector_to_dict(form.second),
            "min_gap": form.min_gap,
            "directional": form.directional,
            "must_follow": form.must_follow,
        }
    if isinstance(form, Bucket):
        return {
            "form": "bucket",
            "scope": list(form.scope),
            "first": selector_to_dict(form.first),
            "second": selector_to_dict(form.second),
            "dimension": form.dimension,
            "relation": form.relation,
        }
    if isinstance(form, Conditional):
        return {
            "form": "conditional",
            "scope": list(form.scope),
            "when": _form_to_dict(form.when),
            "then": _form_to_dict(form.then),
        }
    raise IRError(f"cannot serialise {type(form).__name__}")


def rule_to_dict(rule: Rule) -> dict:
    """The stored shape, which is what lands in Constraint.parameters."""
    out = _form_to_dict(rule.form)
    out["strength"] = rule.strength
    if rule.description:
        out["description"] = rule.description
    return out


def referenced_names(rule: Rule) -> dict[str, set[str]]:
    """Every teacher/subject/class-group name the rule expects to exist.

    The caller checks these against the school so a rule naming someone who
    isn't on staff is caught while the admin is still looking at it, rather
    than matching nothing at solve time.
    """
    found: dict[str, set[str]] = {"subject": set(), "teacher": set(), "class_group": set()}

    def visit(form: Form) -> None:
        selectors: tuple[Selector, ...]
        if isinstance(form, (Count, Run)):
            selectors = (form.selector,)
        elif isinstance(form, (Adjacency, Bucket)):
            selectors = (form.first, form.second)
        elif isinstance(form, Conditional):
            visit(form.when)
            visit(form.then)
            return
        else:
            return
        for sel in selectors:
            for kind, names in sel.names().items():
                found[kind].update(names)

    visit(rule.form)
    return found
