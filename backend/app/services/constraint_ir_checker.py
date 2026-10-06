"""
Check a finished timetable against the rules it was supposed to honour.

The compiler turns a rule into CP-SAT constraints before a timetable exists.
This answers the same question afterwards, about a timetable that already does:
which rules does this arrangement break, and in which slots.

Two things need it.

A manual edit can break a rule without breaking anything physical. Dragging a
teacher into a period her availability rule excludes double-books nobody, so
the slot-conflict check passes and the move is saved - while the Constraints
tab goes on reporting that rule as enforced. The timetable and the UI disagree
and nothing says so.

And a freshly generated timetable should break no rules at all. When it does,
the compiler and this disagree, and one of them is wrong. That has already
happened three times: a min_gap that was a no-op, an availability rule that
blocked a whole day, and period numbers that were off by one. Each produced a
timetable contradicting its own constraints, and nothing noticed because
nothing was looking.

Cheap, because the entries are fixed. No variables, no solver - a rule is a
selector, a scope and a relation, and against concrete placements that is
filtering and counting.

Deliberately shares the selector and scope resolution with the compiler rather
than reimplementing it. An independent implementation would catch more, but two
definitions of "which lessons does this rule mean" drifting apart would be
worse than either bug this is meant to find: rules would be enforced one way
and reported another, with no way to tell which was right.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .constraint_ir import (
    Adjacency,
    Balance,
    Bucket,
    Conditional,
    Count,
    Form,
    Rule,
    Run,
    Span,
)
from .constraint_ir_compiler import (
    _SCOPE_KEY,
    SchoolIndex,
    UnknownName,
    _group,
    _matches,
    _resolve,
    _side,
)


@dataclass(frozen=True)
class Placement:
    """One scheduled slot. The concrete counterpart of the compiler's Atom.

    Field names match Atom's on purpose: the selector and scope helpers are
    shared, and they read these attributes.
    """

    entry_id: int
    class_group_id: int
    subject_id: int
    teacher_id: int | None
    period_id: int
    day_of_week: int
    order: int
    occupies_class: bool = True
    occupies_teacher: bool = True


@dataclass
class Violation:
    """One rule this timetable breaks, and where.

    `entry_ids` is what the UI marks. `detail` says what went wrong in numbers,
    because "this breaks a rule" without "she has 7 periods and the rule allows
    6" leaves someone hunting for which slot to move.
    """

    constraint_id: int | None
    description: str
    strength: str
    entry_ids: list[int] = field(default_factory=list)
    detail: str = ""


def _slots(placements, side: str) -> int:
    """How many periods these placements occupy, counted the way the solver does.

    One period of a section is one slot, however many entries share it: an
    elective block puts one entry per option into the same section and
    period, and a split lab one per batch. The solver reserves that slot with
    a single variable, so counting entries here would report "7 periods
    today" where the solver saw 5 - a violation nobody can find, on a
    timetable that honours the rule.

    A teacher, on the other hand, really is busy once per entry.
    """
    if side == "teacher":
        return len({(p.teacher_id, p.period_id) for p in placements})
    return len({(p.class_group_id, p.period_id) for p in placements})


def _simultaneous(a, b) -> bool:
    """Strands of one slot - a block's options, a lab's batches - rather than
    separate lessons. They happen at the same moment by construction, so a
    rule about two lessons being too close, or sharing a day, is not about
    them. Mirrors the compiler, which skips the same pairs."""
    return a.class_group_id == b.class_group_id and a.period_id == b.period_id


def _count_in(group: list[Placement], resolved: dict, form: Count,
              side: str = "class") -> tuple[int, list[Placement]]:
    matching = [p for p in group if _matches(p, resolved)]
    if not form.distinct:
        return _slots(matching, side), matching
    keyer = _SCOPE_KEY[form.distinct]
    return len({keyer(p) for p in matching}), matching


def _holds(actual: int, relation: str, value: int) -> bool:
    if relation == "<=":
        return actual <= value
    if relation == ">=":
        return actual >= value
    return actual == value


def _unit(form: Count, n: int = 2) -> str:
    """The thing being counted, singular when there is one of it.

    "1 periods here" is the kind of wrongness that makes a warning look
    automated and therefore ignorable, which defeats a message whose only job
    is to be read."""
    plural = {"subject": "subjects", "teacher": "teachers", "class_group": "classes",
              "day": "days", "period_order": "period numbers"}.get(form.distinct, "periods")
    if n != 1:
        return plural
    return {"subjects": "subject", "teachers": "teacher", "classes": "class",
            "days": "day", "period numbers": "period number", "periods": "period"}[plural]


def _check_count(placements, form: Count, index) -> list[tuple[list[int], str]]:
    resolved = _resolve(form.selector, index)
    side = _side(form.scope, form.selector)
    pool = [p for p in placements
            if (p.occupies_teacher if side == "teacher" else p.occupies_class)]
    members = [p for p in pool if _matches(p, resolved, ignore_time=True)]
    if not members:
        return []

    if form.exists_over:
        outer = tuple(d for d in form.scope if d not in form.exists_over)
        inner = tuple(d for d in form.scope if d in form.exists_over)
        found = []
        for _key, outer_group in _group(members, outer).items():
            satisfied, everything = False, []
            for _inner_key, inner_group in _group(outer_group, inner).items():
                actual, matching = _count_in(inner_group, resolved, form, side)
                everything.extend(matching)
                if _holds(actual, form.relation, form.value):
                    satisfied = True
                    break
            if not satisfied:
                found.append((
                    [p.entry_id for p in everything],
                    f"no {' or '.join(form.exists_over)} satisfies "
                    f"{form.relation} {form.value} {_unit(form, form.value)}",
                ))
        return found

    found = []
    for _key, group in _group(members, form.scope).items():
        actual, matching = _count_in(group, resolved, form, side)
        if not _holds(actual, form.relation, form.value):
            found.append((
                [p.entry_id for p in matching],
                f"{actual} {_unit(form, actual)} here, but the rule says "
                f"{'at most' if form.relation == '<=' else 'at least' if form.relation == '>=' else 'exactly'} "
                f"{form.value}",
            ))
    return found


def _runs(group: list[Placement]) -> list[list[list[Placement]]]:
    by_day: dict[int, dict[int, list[Placement]]] = {}
    for p in group:
        by_day.setdefault(p.day_of_week, {}).setdefault(p.order, []).append(p)
    runs = []
    for _day, by_order in sorted(by_day.items()):
        current, previous = [], None
        for order in sorted(by_order):
            if previous is not None and order != previous + 1:
                if current:
                    runs.append(current)
                current = []
            current.append(by_order[order])
            previous = order
        if current:
            runs.append(current)
    return runs


def _check_run(placements, form: Run, index) -> list[tuple[list[int], str]]:
    resolved = _resolve(form.selector, index)
    members = [p for p in placements if _matches(p, resolved)]
    if not members:
        return []
    found = []
    for _key, group in _group(members, form.scope).items():
        for run in _runs(group):
            flat = [p for slot in run for p in slot]
            if form.max_consecutive is not None and len(run) > form.max_consecutive:
                found.append(([p.entry_id for p in flat],
                              f"{len(run)} in a row, but the rule allows "
                              f"{form.max_consecutive}"))
            if form.block_size is not None and len(run) < form.block_size:
                found.append(([p.entry_id for p in flat],
                              f"a stretch of {len(run)}, but the rule needs blocks "
                              f"of {form.block_size}"))
    return found


def _check_adjacency(placements, form: Adjacency, index) -> list[tuple[list[int], str]]:
    first_sel = _resolve(form.first, index)
    second_sel = _resolve(form.second, index)
    found = []
    for _key, group in _group(placements, form.scope).items():
        firsts = [p for p in group if _matches(p, first_sel)]
        seconds = [p for p in group if _matches(p, second_sel)]

        if form.must_follow:
            for a in firsts:
                if not any(b.day_of_week == a.day_of_week and b.order == a.order + 1
                           for b in seconds):
                    found.append(([a.entry_id], "nothing follows it in the next period"))
            continue

        if form.must_precede:
            for a in firsts:
                for b in seconds:
                    if a.day_of_week == b.day_of_week and b.order < a.order:
                        found.append(([a.entry_id, b.entry_id], "they are the wrong way round"))
            continue

        for a in firsts:
            for b in seconds:
                if a.day_of_week != b.day_of_week or a.entry_id == b.entry_id or _simultaneous(a, b):
                    continue
                distance = b.order - a.order
                too_close = (0 < distance <= form.min_gap) if form.directional \
                    else abs(distance) <= form.min_gap
                if too_close:
                    found.append(([a.entry_id, b.entry_id],
                                  f"{abs(distance)} period(s) apart, but the rule needs "
                                  f"more than {form.min_gap}"))
    return found


def _check_bucket(placements, form: Bucket, index) -> list[tuple[list[int], str]]:
    first_sel = _resolve(form.first, index)
    second_sel = _resolve(form.second, index)
    keyer = (lambda p: p.day_of_week) if form.dimension == "day" else (lambda p: p.period_id)
    word = "day" if form.dimension == "day" else "period"
    found = []
    for _key, group in _group(placements, form.scope).items():
        firsts = [p for p in group if _matches(p, first_sel)]
        seconds = [p for p in group if _matches(p, second_sel)]
        if not firsts or not seconds:
            continue
        if form.relation == "different":
            for a in firsts:
                for b in seconds:
                    if a.entry_id != b.entry_id and keyer(a) == keyer(b) and not _simultaneous(a, b):
                        found.append(([a.entry_id, b.entry_id], f"both on the same {word}"))
        else:
            a_buckets = {keyer(p) for p in firsts}
            b_buckets = {keyer(p) for p in seconds}
            if a_buckets != b_buckets:
                stranded = [p for p in firsts + seconds
                            if keyer(p) not in (a_buckets & b_buckets)]
                found.append(([p.entry_id for p in stranded],
                              f"they do not share the same {word}"))
    return found


def _check_span(placements, form: Span, index) -> list[tuple[list[int], str]]:
    resolved = _resolve(form.selector, index)
    members = [p for p in placements if _matches(p, resolved)]
    found = []
    for _key, group in _group(members, form.scope).items():
        if not group:
            continue
        orders = sorted({p.order for p in group})
        span = orders[-1] - orders[0] + 1
        ids = [p.entry_id for p in group]
        if form.max_span is not None and span > form.max_span:
            found.append((ids, f"stretches over {span} periods, but the rule allows "
                               f"{form.max_span}"))
        if form.max_idle is not None and span - len(orders) > form.max_idle:
            found.append((ids, f"{span - len(orders)} free period(s) in the middle, but "
                               f"the rule allows {form.max_idle}"))
    return found


def _check_balance(placements, form: Balance, index) -> list[tuple[list[int], str]]:
    resolved = _resolve(form.selector, index)
    members = [p for p in placements if _matches(p, resolved)]
    if not members:
        return []
    all_buckets = {tuple(_SCOPE_KEY[d](p) for d in form.across) for p in members}
    if len(all_buckets) < 2:
        return []
    found = []
    side = _side(form.scope, form.selector)
    for _key, group in _group(members, form.scope).items():
        by_bucket: dict = {b: [] for b in all_buckets}
        for p in group:
            by_bucket[tuple(_SCOPE_KEY[d](p) for d in form.across)].append(p)
        counts = {b: _slots(ps, side) for b, ps in by_bucket.items()}
        spread = max(counts.values()) - min(counts.values())
        if spread > form.max_spread:
            found.append(([p.entry_id for p in group],
                          f"the fullest and emptiest differ by {spread}, but the rule "
                          f"allows {form.max_spread}"))
    return found


def _check_conditional(placements, form: Conditional, index) -> list[tuple[list[int], str]]:
    when_resolved = _resolve(form.when.selector, index)
    members = [p for p in placements if _matches(p, when_resolved, ignore_time=True)]
    found = []
    for key, group in _group(members, form.scope).items():
        actual, _ = _count_in(group, when_resolved, form.when,
                              _side(form.when.scope, form.when.selector))
        if not _holds(actual, form.when.relation, form.when.value):
            continue  # the condition doesn't hold here, so the rule says nothing
        # Only this group's placements are subject to the consequence.
        in_group = [p for p in placements
                    if tuple(_SCOPE_KEY[d](p) for d in form.scope) == key]
        found.extend(_check_form(in_group, form.then, index))
    return found


_CHECKERS = {
    Count: _check_count,
    Run: _check_run,
    Adjacency: _check_adjacency,
    Bucket: _check_bucket,
    Span: _check_span,
    Balance: _check_balance,
    Conditional: _check_conditional,
}


def _check_form(placements, form: Form, index) -> list[tuple[list[int], str]]:
    checker = _CHECKERS.get(type(form))
    if checker is None:  # pragma: no cover - every form has one
        raise TypeError(f"no checker for {type(form).__name__}")
    return checker(placements, form, index)


def check_rule(placements: list[Placement], rule: Rule, index: SchoolIndex,
               constraint_id: int | None = None) -> list[Violation]:
    """Every way this timetable breaks one rule. Empty means it honours it."""
    seen: set[tuple] = set()
    out: list[Violation] = []
    for ids, detail in _check_form(placements, rule.form, index):
        key = (tuple(sorted(set(ids))), detail)
        if key in seen:
            continue
        seen.add(key)
        out.append(Violation(constraint_id=constraint_id, description=rule.description,
                             strength=rule.strength, entry_ids=list(key[0]), detail=detail))
    return out


def check_rules(placements: list[Placement], rules: list[tuple[int | None, Rule]],
                index: SchoolIndex) -> list[Violation]:
    """Check every rule, carrying on past ones that can't be checked.

    A rule naming a teacher who has since left cannot be evaluated, and that is
    not the timetable's fault - it is skipped rather than reported as broken,
    because a violation nobody can act on trains people to ignore the warnings
    that matter.
    """
    violations: list[Violation] = []
    for constraint_id, rule in rules:
        try:
            violations.extend(check_rule(placements, rule, index, constraint_id))
        except UnknownName:
            continue
    return violations
