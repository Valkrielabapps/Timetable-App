"""
Compile IR rules into CP-SAT constraints.

The solver's decision variables are booleans meaning "this class's lesson in
this subject is taught by this teacher in this period". Every form in the IR is
arithmetic over subsets of those booleans, so this module needs exactly two
things from the solver: a flat list of those variables tagged with what they
mean (`Atom`), and the model to add constraints to.

That is the whole reason the IR is worth having. The nine legacy types each got
their own query, their own loop and their own block inside a 1,400-line
function - so a tenth rule shape meant a tenth block. Here a rule shape is a
selector and a scope, and both are data.

Nothing in here knows about the database. The solver resolves names to ids once
(`SchoolIndex`) and hands over atoms; a rule naming a teacher who no longer
exists is reported by name rather than quietly matching nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from .constraint_ir import (
    Adjacency,
    Bucket,
    Conditional,
    Count,
    Form,
    Rule,
    Run,
    Selector,
)

# How firmly a rule is meant, as the penalty weight a violation costs. Only
# compared against each other, so the gap matters more than the numbers.
_SOFT_WEIGHT = {"strong_preference": 5, "preference": 1}


@dataclass(frozen=True)
class Atom:
    """One decision variable, tagged with everything a selector can filter on.

    `occupies_class` and `occupies_teacher` exist because lab-batch
    requirements split one class session across several simultaneous teachers:
    the session occupies the class's slot once, but two or three teachers are
    busy. Counting a class's periods must not multiply by the batch count, and
    counting a teacher's load must not miss the batch they taught - so the two
    questions read different subsets. For ordinary requirements both are true
    and the distinction never comes up.
    """

    var: cp_model.IntVar
    requirement_id: int
    class_group_id: int
    subject_id: int
    teacher_id: int | None
    period_id: int
    day_of_week: int
    order: int
    occupies_class: bool = True
    occupies_teacher: bool = True


@dataclass
class SchoolIndex:
    """Name-to-id lookups for one school, plus what a class-group label means.

    A label can name a whole grade ("Grade 8", every section) or one section
    ("Grade 8 - A"), which is the same two-level naming the constraint router
    already exposes to the parser - so a rule can say either and mean it.
    """

    subject_ids: dict[str, int]
    teacher_ids: dict[str, int]
    class_group_ids: dict[str, list[int]]

    def unknown(self, kind: str, name: str) -> bool:
        table = {"subject": self.subject_ids, "teacher": self.teacher_ids,
                 "class_group": self.class_group_ids}[kind]
        return name not in table


class UnknownName(Exception):
    """A rule names something this school doesn't have.

    Carried as an exception rather than a skipped rule so the caller reports it
    - a rule that silently matches nothing looks identical to one that is being
    honoured, which is the failure mode the whole IR effort exists to remove.
    """

    def __init__(self, kind: str, name: str):
        self.kind = kind
        self.name = name
        super().__init__(f"no {kind.replace('_', ' ')} called {name!r} in this school")


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _resolve(sel: Selector, index: SchoolIndex) -> dict:
    """Turn a selector's names into id sets, failing loudly on any it can't."""
    out: dict = {}
    if sel.subjects is not None:
        ids = set()
        for name in sel.subjects:
            if index.unknown("subject", name):
                raise UnknownName("subject", name)
            ids.add(index.subject_ids[name])
        out["subjects"] = ids
    if sel.not_subjects is not None:
        ids = set()
        for name in sel.not_subjects:
            if index.unknown("subject", name):
                raise UnknownName("subject", name)
            ids.add(index.subject_ids[name])
        out["not_subjects"] = ids
    if sel.teachers is not None:
        ids = set()
        for name in sel.teachers:
            if index.unknown("teacher", name):
                raise UnknownName("teacher", name)
            ids.add(index.teacher_ids[name])
        out["teachers"] = ids
    if sel.class_groups is not None:
        ids = set()
        for name in sel.class_groups:
            if index.unknown("class_group", name):
                raise UnknownName("class_group", name)
            ids.update(index.class_group_ids[name])
        out["class_groups"] = ids
    if sel.days is not None:
        out["days"] = set(sel.days)
    if sel.period_orders is not None:
        out["period_orders"] = set(sel.period_orders)
    return out


def _matches(atom: Atom, resolved: dict, ignore_time: bool = False) -> bool:
    """Whether one atom passes a resolved selector. Fields AND, values OR.

    `ignore_time` drops the day/period filters, which is how group membership
    is decided - see _count for why that distinction decides whether an
    unsatisfiable rule is reported or silently skipped.
    """
    if "subjects" in resolved and atom.subject_id not in resolved["subjects"]:
        return False
    if "not_subjects" in resolved and atom.subject_id in resolved["not_subjects"]:
        return False
    if "teachers" in resolved and atom.teacher_id not in resolved["teachers"]:
        return False
    if "class_groups" in resolved and atom.class_group_id not in resolved["class_groups"]:
        return False
    if not ignore_time:
        if "days" in resolved and atom.day_of_week not in resolved["days"]:
            return False
        if "period_orders" in resolved and atom.order not in resolved["period_orders"]:
            return False
    return True


def _side(scope: tuple[str, ...], sel: Selector) -> str:
    """Whether this rule counts class slots or teacher assignments.

    A rule that groups by teacher, or names teachers, is about somebody's load;
    anything else is about a class's day. Only lab-batch requirements make the
    two differ, and getting it wrong there would either multiply a class's
    period count by the batch size or lose a teacher's batch periods entirely.
    """
    return "teacher" if ("teacher" in scope or sel.teachers is not None) else "class"


def _pool(atoms: list[Atom], side: str) -> list[Atom]:
    if side == "teacher":
        return [a for a in atoms if a.occupies_teacher]
    return [a for a in atoms if a.occupies_class]


_SCOPE_KEY = {
    "teacher": lambda a: a.teacher_id,
    "class_group": lambda a: a.class_group_id,
    "subject": lambda a: a.subject_id,
    "day": lambda a: a.day_of_week,
    "period": lambda a: a.period_id,
}


def _group(atoms: list[Atom], scope: tuple[str, ...]) -> dict[tuple, list[Atom]]:
    """Partition atoms by the scope's grouping key. Empty scope = one group."""
    groups: dict[tuple, list[Atom]] = {}
    for atom in atoms:
        key = tuple(_SCOPE_KEY[dim](atom) for dim in scope)
        groups.setdefault(key, []).append(atom)
    return groups


# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------


def _relate(model, penalties, expr, relation: str, value: int, weight: int | None, name: str) -> None:
    """Apply a relation, hard or relaxed by a penalised slack variable.

    A soft rule is relaxed rather than dropped so a preference the solver can't
    fully honour still pulls the answer as close as it can - the difference
    between "PE ran four in a row instead of three" and "the preference was
    ignored".
    """
    if weight is None:
        if relation == "<=":
            model.Add(expr <= value)
        elif relation == ">=":
            model.Add(expr >= value)
        else:
            model.Add(expr == value)
        return

    if relation in ("<=", "=="):
        over = model.NewIntVar(0, 10_000, f"{name}_over")
        model.Add(expr <= value + over)
        penalties.append(weight * over)
    if relation in (">=", "=="):
        under = model.NewIntVar(0, 10_000, f"{name}_under")
        model.Add(expr >= value - under)
        penalties.append(weight * under)


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


def _count(model, penalties, atoms, form: Count, index, weight, tag: str) -> None:
    resolved = _resolve(form.selector, index)
    pool = _pool(atoms, _side(form.scope, form.selector))

    # Group membership ignores the selector's time filters, and the sum does
    # not. The difference decides what happens to a rule like "Grade 10 must
    # have Maths in period 1" for a class that has no Maths at all: its group
    # holds no matching atoms even ignoring time, so the rule does not apply to
    # it. A class that *does* have Maths but cannot place it in period 1 keeps
    # its group, the sum is empty, and the rule is correctly infeasible rather
    # than quietly skipped. Skipping there would be the old failure - a rule
    # that reports itself as enforced and does nothing.
    members = [a for a in pool if _matches(a, resolved, ignore_time=True)]
    if not members:
        return

    for key, group in _group(members, form.scope).items():
        selected = [a.var for a in group if _matches(a, resolved)]
        name = f"ir_{tag}_{'_'.join(str(k) for k in key)}"

        if form.distinct:
            keyer = {"subject": lambda a: a.subject_id,
                     "teacher": lambda a: a.teacher_id,
                     "class_group": lambda a: a.class_group_id}[form.distinct]
            by_kind: dict = {}
            for atom in group:
                if _matches(atom, resolved):
                    by_kind.setdefault(keyer(atom), []).append(atom.var)
            indicators = []
            for kind, vars_ in by_kind.items():
                used = model.NewBoolVar(f"{name}_has{kind}")
                # used == 1 exactly when at least one of those lessons happens.
                model.AddMaxEquality(used, vars_)
                indicators.append(used)
            if not indicators and form.relation in ("<=",):
                continue
            _relate(model, penalties, sum(indicators) if indicators else 0,
                    form.relation, form.value, weight, name)
            continue

        if not selected and form.relation == "<=":
            continue  # nothing to cap
        _relate(model, penalties, sum(selected) if selected else 0,
                form.relation, form.value, weight, name)


def _runs_within(group: list[Atom]) -> list[list[Atom]]:
    """Split one group's atoms into consecutive stretches within a day.

    Adjacency is by position in the day, and a break ends a stretch - a lesson
    before lunch and one after are not back to back. Breaks never produce
    atoms, so a gap in `order` is exactly where a run ends, whether that gap is
    lunch or a free period.
    """
    by_day: dict[int, dict[int, list[Atom]]] = {}
    for atom in group:
        by_day.setdefault(atom.day_of_week, {}).setdefault(atom.order, []).append(atom)
    runs = []
    for _, by_order in sorted(by_day.items()):
        current: list[list[Atom]] = []
        previous = None
        for order in sorted(by_order):
            if previous is not None and order != previous + 1:
                if current:
                    runs.append(current)
                current = []
            current.append(by_order[order])
            previous = order
        if current:
            runs.append(current)
    # Each run is a list of slots, and each slot the atoms at that position -
    # several when more than one teacher could take the lesson.
    return runs


def _run(model, penalties, atoms, form: Run, index, weight, tag: str) -> None:
    resolved = _resolve(form.selector, index)
    pool = _pool(atoms, _side(form.scope, form.selector))
    members = [a for a in pool if _matches(a, resolved, ignore_time=True)]
    if not members:
        return

    for key, group in _group(members, form.scope).items():
        name = f"ir_{tag}_{'_'.join(str(k) for k in key)}"
        runs = _runs_within([a for a in group if _matches(a, resolved)])

        if form.max_consecutive is not None:
            n = form.max_consecutive
            for run_index, run in enumerate(runs):
                # Every window of n+1 consecutive periods may hold at most n of
                # these lessons, which is what "no more than n in a row" means
                # and needs no extra variables.
                for start in range(0, max(0, len(run) - n)):
                    window = run[start:start + n + 1]
                    vars_ = [a.var for slot in window for a in slot]
                    _relate(model, penalties, sum(vars_), "<=", n, weight,
                            f"{name}_r{run_index}_w{start}")

        if form.block_size is not None:
            # A block rule says a lesson may not sit alone: wherever one is
            # scheduled, its neighbour within the run must be too. Expressed as
            # "an isolated lesson is forbidden" rather than by building block
            # variables, which keeps it linear and leaves the solver free to
            # choose where the block goes.
            for run_index, run in enumerate(runs):
                for i, slot in enumerate(run):
                    neighbours = []
                    if i > 0:
                        neighbours += [a.var for a in run[i - 1]]
                    if i + 1 < len(run):
                        neighbours += [a.var for a in run[i + 1]]
                    here = [a.var for a in slot]
                    if not neighbours:
                        # A run of one: nowhere to pair with, so nothing of
                        # this subject may go here at all.
                        _relate(model, penalties, sum(here), "<=", 0, weight,
                                f"{name}_r{run_index}_alone{i}")
                        continue
                    for j, var in enumerate(here):
                        if weight is None:
                            model.Add(sum(neighbours) >= 1).OnlyEnforceIf(var)
                        else:
                            lonely = model.NewBoolVar(f"{name}_r{run_index}_lone{i}_{j}")
                            # Either a neighbour is scheduled, or this one is
                            # isolated and pays for it.
                            model.Add(sum(neighbours) + lonely >= var)
                            penalties.append(weight * lonely)


def _adjacency(model, penalties, atoms, form: Adjacency, index, weight, tag: str) -> None:
    first = _resolve(form.first, index)
    second = _resolve(form.second, index)
    pool = _pool(atoms, _side(form.scope, form.first))

    for key, group in _group(pool, form.scope).items():
        name = f"ir_{tag}_{'_'.join(str(k) for k in key)}"
        firsts = [a for a in group if _matches(a, first)]
        seconds = [a for a in group if _matches(a, second)]
        if not firsts or not seconds:
            continue

        if form.must_follow:
            # Wherever a `first` happens, a `second` must be in the next period.
            by_slot: dict[tuple[int, int], list[Atom]] = {}
            for atom in seconds:
                by_slot.setdefault((atom.day_of_week, atom.order), []).append(atom)
            for atom in firsts:
                following = by_slot.get((atom.day_of_week, atom.order + 1), [])
                if not following:
                    _relate(model, penalties, atom.var, "<=", 0, weight,
                            f"{name}_nofollow_{atom.period_id}")
                    continue
                if weight is None:
                    model.Add(sum(a.var for a in following) >= 1).OnlyEnforceIf(atom.var)
                else:
                    miss = model.NewBoolVar(f"{name}_miss_{atom.period_id}")
                    model.Add(sum(a.var for a in following) + miss >= atom.var)
                    penalties.append(weight * miss)
            continue

        for a in firsts:
            for b in seconds:
                if a.day_of_week != b.day_of_week:
                    continue
                if a.var is b.var:
                    continue
                distance = b.order - a.order
                if form.directional:
                    # Only second-after-first is forbidden. "Maths can't come
                    # right after PE" says nothing about PE after Maths, and
                    # forbidding both is a different, stricter rule.
                    if not 0 < distance <= form.min_gap:
                        continue
                elif abs(distance) > form.min_gap:
                    continue
                _relate(model, penalties, a.var + b.var, "<=", 1, weight,
                        f"{name}_{a.period_id}_{b.period_id}_{a.requirement_id}_{b.requirement_id}")


def _bucket(model, penalties, atoms, form: Bucket, index, weight, tag: str) -> None:
    first = _resolve(form.first, index)
    second = _resolve(form.second, index)
    pool = _pool(atoms, _side(form.scope, form.first))

    for key, group in _group(pool, form.scope).items():
        name = f"ir_{tag}_{'_'.join(str(k) for k in key)}"
        firsts = [a for a in group if _matches(a, first)]
        seconds = [a for a in group if _matches(a, second)]
        if not firsts or not seconds:
            continue
        keyer = (lambda a: a.day_of_week) if form.dimension == "day" else (lambda a: a.period_id)

        if form.relation == "different":
            # Pairwise: two lessons that would share the bucket can't both run.
            for a in firsts:
                for b in seconds:
                    if keyer(a) != keyer(b) or a.var is b.var:
                        continue
                    _relate(model, penalties, a.var + b.var, "<=", 1, weight,
                            f"{name}_{a.period_id}_{b.period_id}_{a.requirement_id}_{b.requirement_id}")
            continue

        # "same": for each bucket, the two sides must agree on whether they are
        # in it. Indicator per side per bucket, then force them equal - which
        # is what makes parallel scheduling (electives, combined sections)
        # expressible rather than needing a form of its own.
        buckets = {keyer(a) for a in firsts} | {keyer(a) for a in seconds}
        for bucket in buckets:
            a_vars = [a.var for a in firsts if keyer(a) == bucket]
            b_vars = [a.var for a in seconds if keyer(a) == bucket]
            a_used = model.NewBoolVar(f"{name}_a{bucket}")
            b_used = model.NewBoolVar(f"{name}_b{bucket}")
            if a_vars:
                model.AddMaxEquality(a_used, a_vars)
            else:
                model.Add(a_used == 0)
            if b_vars:
                model.AddMaxEquality(b_used, b_vars)
            else:
                model.Add(b_used == 0)
            if weight is None:
                model.Add(a_used == b_used)
            else:
                differ = model.NewBoolVar(f"{name}_differ{bucket}")
                model.Add(a_used - b_used <= differ)
                model.Add(b_used - a_used <= differ)
                penalties.append(weight * differ)


def _conditional(model, penalties, atoms, form: Conditional, index, weight, tag: str) -> None:
    """Enforce `then` only in the groups where `when` holds.

    `when` becomes an indicator per group, and `then` is added under
    OnlyEnforceIf - which is what lets "on days Priya teaches Grade 12 she
    teaches at most 5 periods" be one rule rather than a rule language of its
    own.
    """
    when_resolved = _resolve(form.when.selector, index)
    when_pool = _pool(atoms, _side(form.when.scope, form.when.selector))

    for key, group in _group(when_pool, form.scope).items():
        name = f"ir_{tag}_{'_'.join(str(k) for k in key)}"
        trigger_vars = [a.var for a in group if _matches(a, when_resolved)]
        if not trigger_vars:
            continue

        holds = model.NewBoolVar(f"{name}_when")
        total = sum(trigger_vars)
        if form.when.relation == ">=":
            # holds <=> total >= value
            model.Add(total >= form.when.value).OnlyEnforceIf(holds)
            model.Add(total <= form.when.value - 1).OnlyEnforceIf(holds.Not())
        elif form.when.relation == "<=":
            model.Add(total <= form.when.value).OnlyEnforceIf(holds)
            model.Add(total >= form.when.value + 1).OnlyEnforceIf(holds.Not())
        else:
            model.Add(total == form.when.value).OnlyEnforceIf(holds)
            # == is the awkward one: "not equal" needs both directions, so the
            # negative side is left unconstrained. That makes `holds` an
            # over-approximation - it may be 0 when the count happens to match,
            # so the consequence is sometimes skipped rather than wrongly
            # applied. Erring towards under-enforcing is the safe direction:
            # the rule shows up as unmet rather than silently distorting a
            # timetable nobody asked to change.
            pass

        # The consequence shares the condition's groups, so it is applied over
        # this group's atoms only, gated on `holds`.
        then = form.then
        if isinstance(then, Count):
            then_resolved = _resolve(then.selector, index)
            then_pool = _pool(atoms, _side(then.scope, then.selector))
            then_group = [a for a in _group(then_pool, form.scope).get(key, [])
                          if _matches(a, then_resolved)]
            if not then_group:
                continue
            expr = sum(a.var for a in then_group)
            if weight is None:
                if then.relation == "<=":
                    model.Add(expr <= then.value).OnlyEnforceIf(holds)
                elif then.relation == ">=":
                    model.Add(expr >= then.value).OnlyEnforceIf(holds)
                else:
                    model.Add(expr == then.value).OnlyEnforceIf(holds)
            else:
                slack = model.NewIntVar(0, 10_000, f"{name}_slack")
                if then.relation in ("<=", "=="):
                    model.Add(expr <= then.value + slack).OnlyEnforceIf(holds)
                if then.relation in (">=", "=="):
                    model.Add(expr >= then.value - slack).OnlyEnforceIf(holds)
                penalties.append(weight * slack)


_COMPILERS = {
    Count: _count,
    Run: _run,
    Adjacency: _adjacency,
    Bucket: _bucket,
    Conditional: _conditional,
}


def compile_rule(model, penalties: list, atoms: list[Atom], rule: Rule,
                 index: SchoolIndex, tag: str) -> None:
    """Add one IR rule to the model. Raises UnknownName if it names a stranger."""
    weight = None if rule.strength == "required" else _SOFT_WEIGHT.get(rule.strength, 1)
    compiler = _COMPILERS.get(type(rule.form))
    if compiler is None:
        raise TypeError(f"no compiler for {type(rule.form).__name__}")
    compiler(model, penalties, atoms, rule.form, index, weight, tag)


def compile_rules(model, penalties: list, atoms: list[Atom],
                  rules: list[tuple[str, Rule]], index: SchoolIndex) -> list[str]:
    """Add every rule it can, and return a message for each it could not.

    Carries on past a bad rule rather than failing the whole solve: one rule
    naming a teacher who left should not stop a school generating a timetable.
    The messages are surfaced, not swallowed - a rule that did nothing has to
    say so.
    """
    problems: list[str] = []
    for tag, rule in rules:
        try:
            compile_rule(model, penalties, atoms, rule, index, tag)
        except UnknownName as exc:
            problems.append(f"{rule.description or 'A rule'} was not applied: {exc}.")
        except (TypeError, KeyError) as exc:  # pragma: no cover - defensive
            problems.append(f"{rule.description or 'A rule'} could not be applied: {exc}.")
    return problems
