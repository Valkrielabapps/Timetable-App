"""
Timetable solver service.

Wraps Google OR-Tools' CP-SAT solver. Kept separate from the API routers so
it can be unit tested and evolved independently (e.g. swapping in new
constraint types) without touching HTTP handling code.

`solve_example()` is the original small worked example, kept as a fast
sanity check that the OR-Tools install works (see /api/solver/test).
`generate_school_timetable()` is the real thing: it reads a school's
teachers, class groups, subject requirements, and periods from the
database and builds/solves a CP-SAT model from that real data.
"""
import contextvars
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from itertools import combinations

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.constraint_ir import IRError, rule_from_dict
from app.services.constraint_ir_compiler import Atom, SchoolIndex, compile_rules
from app.models.school import (
    ClassGroup,
    Constraint,
    ElectiveBlock,
    Period,
    Room,
    School,
    Subject,
    SubjectRequirement,
    Teacher,
    Timetable,
    ZeroPeriod,
)


@dataclass
class SolveResult:
    status: str  # "optimal", "feasible", "infeasible", "unknown"
    assignments: list[dict]  # list of {class_group, subject, teacher, period}


@dataclass
class TimetableSolveResult:
    """Result of solving a real school's timetable from database data."""

    status: str  # "optimal", "feasible", "infeasible", "no_periods", "no_requirements"
    # each entry: {class_group_id, subject_id, teacher_id, period_id}
    assignments: list[dict] = field(default_factory=list)
    # human-readable reasons the solve couldn't proceed (populated on failure
    # paths that happen before the solver even runs, e.g. missing data)
    errors: list[str] = field(default_factory=list)
    # (class_group_id, subject_id, teacher_id, period_id) tuples that were
    # locked on the previous timetable and successfully honored in this
    # solve — the router uses this to mark the corresponding new
    # TimetableEntry rows locked=True again, so a lock "sticks" across
    # regenerations instead of needing to be re-applied by hand each time.
    locked_keys: set[tuple[int, int, int, int]] = field(default_factory=set)
    # Rules that did not make it into the model, with a reason - a rule naming
    # a teacher who has since left, or one stored in a shape that no longer
    # validates. Distinct from `errors`: the timetable was still produced, so
    # this is not a failure, but a rule silently doing nothing while the UI
    # reports it as enforced is the failure mode the IR exists to end.
    warnings: list[str] = field(default_factory=list)


logger = logging.getLogger(__name__)


def _usable_cpus() -> int:
    """CPUs this process may actually use.

    os.cpu_count() reports the host machine. Inside a container (Railway) that
    can be 32+ cores while the service is allowed one or two, and the solver
    then starts 8 parallel searches that fight over those - each slower than
    one search alone would be. The cgroup's CPU quota is the real number.
    """
    try:
        quota, period = open("/sys/fs/cgroup/cpu.max").read().split()[:2]  # cgroup v2
        if quota != "max":
            return max(1, int(int(quota) / int(period)))
    except (OSError, ValueError):
        pass
    try:
        quota = int(open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read())  # cgroup v1
        period = int(open("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read())
        if quota > 0:
            return max(1, quota // period)
    except (OSError, ValueError):
        pass
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def _search_workers() -> int:
    # At least 2 even on one CPU: CP-SAT's portfolio pairs a feasibility
    # search with a complete one, and one alone loses that.
    return min(8, max(2, _usable_cpus()))


# Rules to leave out of a solve, and a time limit to use instead of the
# configured one - set only by find_blocking_rules, which re-solves a failed
# school with rules switched off to find which ones are to blame. Context
# variables rather than parameters so generate_school_timetable's signature
# (and every caller of it) stays as it is.
_SKIP_RULES: contextvars.ContextVar = contextvars.ContextVar("skip_rules", default=frozenset())
_TIME_LIMIT: contextvars.ContextVar = contextvars.ContextVar("time_limit", default=None)
# Parts of the school's setup to relax for a diagnostic re-solve:
#   "one_teacher"  - let a section's subject be split between teachers
#   "max_periods"  - ignore teachers' max periods/week
_RELAX: contextvars.ContextVar = contextvars.ContextVar("relax", default=frozenset())


def _constraint_query(db: Session):
    query = db.query(Constraint)
    skip = _SKIP_RULES.get()
    return query.filter(Constraint.id.notin_(skip)) if skip else query


# Quick passes (no presolve) tried, each from a new random start, before
# falling back to one full pass. A quick pass that has found no timetable at
# all within FAST_PASS_SECONDS is cut short and restarted.
FAST_PASSES = 2
FAST_PASS_SECONDS = 12
# With preference rules the solver is minimising a penalty, and it would
# otherwise keep searching for a better answer until the time limit even
# when it stopped finding one long ago. This long without an improvement
# counts as settled.
SETTLE_SECONDS = 4.0
# Once a valid timetable exists, how long to spend improving it against the
# preference rules. Preferences are worth some seconds, not the whole minute
# someone is watching a spinner for.
IMPROVE_SECONDS = 20


class _SettleWatch(cp_model.CpSolverSolutionCallback):
    """Remembers when the last better timetable turned up."""

    def __init__(self):
        super().__init__()
        self.last_improvement = None

    def on_solution_callback(self):
        self.last_improvement = time.monotonic()


def _new_solver(time_limit: float, fast: bool, seed: int, light_presolve: bool = False) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    # Every core up to a cap - CP-SAT's parallel search scales well.
    solver.parameters.num_search_workers = _search_workers()
    solver.parameters.max_time_in_seconds = max(1.0, time_limit)
    # A fresh seed per generation plus randomized branching, so every
    # placement the rules allow is reachable rather than the same first
    # answer every run (which looked exactly like a deleted rule still being
    # applied). SOLVER_RANDOM_SEED pins it for debugging and tests.
    solver.parameters.random_seed = seed
    solver.parameters.randomize_search = True
    if fast:
        # Measured on the 30- and 50-section stress schools: the default
        # presolve (mostly symmetry detection over interchangeable teachers)
        # took 15 of 16 seconds and 30 of 34, and the search itself under a
        # second. Skipping it finds the same timetable in 2-5 seconds.
        solver.parameters.cp_model_presolve = False
        solver.parameters.symmetry_level = 0
    elif light_presolve:
        # Presolve on, symmetry detection off: keeps what presolve is good at
        # (simplifying away the slack a preference rule adds) without the
        # symmetry step that took most of the time on the stress schools.
        solver.parameters.symmetry_level = 0
    return solver


def _run(solver: cp_model.CpSolver, model: cp_model.CpModel, has_objective: bool,
         first_answer_within: float | None):
    """Solve, stopping early in two cases:

    - no timetable at all within `first_answer_within` seconds (an unlucky
      quick pass - the caller restarts it from a new random start),
    - without preference rules, as soon as the first timetable is found, and
    - with preference rules, SETTLE_SECONDS after the last improvement.
      While better timetables keep turning up it keeps going, up to the
      solver's own time limit, so a school with many preferences loses none
      of the quality it had; it just stops when the answer stops changing.
    """
    watch = _SettleWatch()
    done = threading.Event()
    started = time.monotonic()

    def watch_and_stop():
        while not done.wait(0.25):
            last = watch.last_improvement
            now = time.monotonic()
            if last is None:
                if first_answer_within is not None and now - started >= first_answer_within:
                    solver.StopSearch()
                    return
            elif not has_objective or now - last >= SETTLE_SECONDS:
                # Nothing to optimise: the first timetable is the answer.
                # CP-SAT should stop there by itself, but measured on a
                # 14-section school one worker found it at 1.5s while another
                # ran on to the 60s limit.
                solver.StopSearch()
                return

    watcher = threading.Thread(target=watch_and_stop, daemon=True)
    watcher.start()
    try:
        return solver.Solve(model, watch)
    finally:
        done.set()
        watcher.join()


def _solve_timetable_model(model: cp_model.CpModel, has_objective: bool):
    """Solve quickly where possible, thoroughly where needed.

    Without preference rules this is _find_timetable: quick passes, then the
    full pass.

    With them, a valid timetable is found FIRST, ignoring the preferences, and
    only then improved. Searching for the best timetable from the start made a
    school whose hard rules solve in two seconds fail outright once two "try
    to" rules were added - the optimiser never reached a first answer inside
    the time limit. Preferences can now only make the answer better, never
    turn a solvable school into "couldn't build a timetable".
    """
    override = _TIME_LIMIT.get()
    limit = float(override if override is not None else settings.solver_time_limit_seconds)
    pinned = settings.solver_random_seed
    rng = random.Random(pinned) if pinned is not None else random.SystemRandom()
    started = time.monotonic()

    def remaining():
        return limit - (time.monotonic() - started)

    if not has_objective:
        return _find_timetable(model, rng, remaining)

    objective = cp_model.cp_model_pb2.CpObjectiveProto()
    objective.CopyFrom(model.Proto().objective)
    model.ClearObjective()
    try:
        # Preference rules add slack variables that only presolve simplifies
        # away, so the no-presolve quick passes stall on them (12s each with
        # nothing found, where a presolved pass finished in 10).
        first = _new_solver(remaining(), fast=False, seed=rng.randrange(2**31 - 1), light_presolve=True)
        status = _run(first, model, False, first_answer_within=None)
    finally:
        model.Proto().objective.CopyFrom(objective)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE) or remaining() < 2:
        return first, status

    # Improve from the timetable just found rather than from nothing.
    model.ClearHints()
    values = first.ResponseProto().solution
    proto = model.Proto()
    proto.solution_hint.vars.extend(range(len(values)))
    proto.solution_hint.values.extend(values)
    better = _new_solver(min(IMPROVE_SECONDS, remaining()), fast=False, seed=rng.randrange(2**31 - 1))
    better_status = _run(better, model, True, first_answer_within=None)
    model.ClearHints()
    if better_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return better, better_status
    # Ran out of time before re-finding even the hinted answer: keep the
    # valid one. FEASIBLE, not OPTIMAL - the preferences weren't weighed.
    return first, cp_model.FEASIBLE


def _find_timetable(model, rng, remaining):
    """Quick passes skip presolve and almost always settle a school in seconds -
    with a timetable, or with proof there isn't one. How long one takes depends
    heavily on its random starting point (3s or 25s for the same school), so an
    unlucky pass is cut short and restarted from a new one rather than waited
    out. Only if FAST_PASSES quick passes all end undecided does the full pass
    run, with whatever time is left. The model must have no objective."""
    solver, status = None, cp_model.UNKNOWN
    for _ in range(FAST_PASSES):
        if solver is not None and remaining() < 2:
            return solver, status
        solver = _new_solver(remaining(), fast=True, seed=rng.randrange(2**31 - 1))
        status = _run(solver, model, False, first_answer_within=FAST_PASS_SECONDS)
        if status != cp_model.UNKNOWN:
            return solver, status

    if remaining() < 2:
        return solver, status
    solver = _new_solver(remaining(), fast=False, seed=rng.randrange(2**31 - 1))
    return solver, _run(solver, model, False, first_answer_within=None)


def _at_most(model, penalties, expr, bound: int, constraint, name: str) -> None:
    """Add `expr <= bound`, hard or soft depending on the Constraint row.

    A hard rule is a plain Add. A soft one is relaxed by a slack variable -
    the timetable may exceed the bound, but every unit over it costs the
    constraint's weight, so the solver trades violations off against each
    other rather than refusing to produce anything.

    Relaxing rather than dropping matters: a preference the solver cannot
    fully honour should still pull the answer as close as it can get, which
    is the difference between "PE ran four in a row instead of three" and
    "the preference was ignored entirely".
    """
    if constraint.is_hard:
        model.Add(expr <= bound)
        return
    weight = constraint.weight if isinstance(constraint.weight, int) and constraint.weight > 0 else 1
    slack = model.NewIntVar(0, 1000, name)
    model.Add(expr <= bound + slack)
    penalties.append(weight * slack)


@dataclass(frozen=True)
class _OptionReq:
    """One option of an elective block, shaped like a SubjectRequirement.

    The placement rules and the legacy constraint types are all written per
    requirement, reading exactly these attributes. Wrapping each option this
    way lets them apply to a subject in a block as they would to an ordinary
    one, rather than each needing a block-aware copy that would drift.

    `id` is the option's id negated, so it can share dicts keyed by
    requirement id without colliding - requirement ids are always positive.
    `periods_per_week` is the block's: every option runs whenever it does.
    """

    id: int
    class_group_id: int
    subject_id: int
    periods_per_week: int
    preferred_teacher_id: int | None
    block_id: int
    option_id: int
    assistant_teacher_id: int | None = None


def _can_staff_all(free: dict[int, list[int]]) -> bool:
    """Whether every option can be given its own teacher at once.

    A bipartite matching of options to free teachers, by augmenting paths.
    A per-option check is not enough: Physics and Chemistry may each have a
    free qualified teacher, and it may be the same person. Blocks have a
    handful of options, so the simple algorithm is plenty.
    """
    teacher_of: dict[int, int] = {}

    def assign(option_id: int, seen: set[int]) -> bool:
        for teacher_id in free[option_id]:
            if teacher_id in seen:
                continue
            seen.add(teacher_id)
            holder = teacher_of.get(teacher_id)
            if holder is None or assign(holder, seen):
                teacher_of[teacher_id] = option_id
                return True
        return False

    return all(assign(option_id, set()) for option_id in free)


def _explain_unstaffable_block(
    block_label: str,
    needed: int,
    possible: int,
    opts: list,
    candidates: dict[int, list[int]],
    teachers_by_id: dict,
    subjects_by_id: dict,
) -> str:
    """Say why a block cannot meet as often as it needs to.

    The useful answer names people. "No timetable possible" leaves an admin
    checking every teacher by hand; "Physics and Chemistry can only be taught
    by Mrs. Rao" tells them exactly what to change. So this looks first for a
    group of options that, between them, have fewer qualified teachers than
    options - which no timetable can fix - and only falls back to availability
    when there is no such group.
    """
    name = lambda o: subjects_by_id[o.subject_id].name if o.subject_id in subjects_by_id else "a subject"  # noqa: E731
    # Smallest group of options whose qualified teachers are too few to cover
    # them all at once (Hall's condition failing). Blocks are small, so trying
    # every subset is cheap and finds the clearest explanation.
    for size in range(2, len(opts) + 1):
        for group in combinations(opts, size):
            pool = set().union(*(candidates[o.id] for o in group))
            if len(pool) < size:
                subjects = ", ".join(name(o) for o in group[:-1]) + f" and {name(group[-1])}"
                people = ", ".join(sorted(teachers_by_id[t].name for t in pool))
                return (
                    f"{block_label} can never meet: {subjects} run at the same time, but the only "
                    f"teacher{'s' if len(pool) != 1 else ''} qualified for them "
                    f"{'are' if len(pool) != 1 else 'is'} {people}, who can't teach "
                    f"{size} classes at once. Qualify another teacher for one of these subjects."
                )
    if possible == 0:
        return (
            f"{block_label} can never meet: there is no period where all of its subjects can be "
            f"given a teacher at the same time. Check the marked-unavailable periods of the "
            f"teachers for {', '.join(name(o) for o in opts)}, and any placement rules on them."
        )
    return (
        f"{block_label} needs {needed} periods a week, but its subjects can only all be given a "
        f"teacher at the same time in {possible}. Check the marked-unavailable periods of the "
        f"teachers for {', '.join(name(o) for o in opts)}, and any placement rules on them, or "
        f"reduce the block's periods a week."
    )


def _block_atoms(block_occ, option_x, option_reqs, periods_by_id) -> list[Atom]:
    """Rule-engine atoms for elective blocks.

    Each option gets a class-side atom carrying its subject, all sharing the
    block's one variable - so "no Physics in the last period" sees Physics in
    a block, while "at most 6 periods a day" counts the block once, because the
    compiler counts a shared variable once. Each teacher choice is a
    teacher-side atom, exactly like a lab batch's.
    """
    by_option = {o.option_id: o for o in option_reqs}
    options_of_block: dict[int, list] = {}
    for o in option_reqs:
        options_of_block.setdefault(o.block_id, []).append(o)

    atoms: list[Atom] = []
    for (block_id, period_id), occ in block_occ.items():
        period = periods_by_id[period_id]
        for o in options_of_block.get(block_id, []):
            atoms.append(Atom(
                var=occ, requirement_id=o.id, class_group_id=o.class_group_id,
                subject_id=o.subject_id, teacher_id=None, period_id=period_id,
                day_of_week=period.day_of_week, order=period.order,
                occupies_class=True, occupies_teacher=False,
            ))
    for (block_id, period_id, option_id), choice in option_x.items():
        o = by_option[option_id]
        period = periods_by_id[period_id]
        for teacher_id, var in choice:
            atoms.append(Atom(
                var=var, requirement_id=o.id, class_group_id=o.class_group_id,
                subject_id=o.subject_id, teacher_id=teacher_id, period_id=period_id,
                day_of_week=period.day_of_week, order=period.order,
                occupies_class=False, occupies_teacher=True,
            ))
    return atoms


def _class_group_labels(class_groups: list[ClassGroup]) -> dict[str, list[int]]:
    """Label -> the class groups it names, for resolving an IR rule's names.

    A label is either a whole grade ("Grade 8", every section in it) or one
    section ("Grade 8 - A"), which is the same two-level naming the constraint
    router already shows the parser - so a rule can say either and mean it.
    """
    labels: dict[str, list[int]] = {}
    for grade in sorted({cg.grade for cg in class_groups if cg.grade}):
        labels[grade] = [cg.id for cg in class_groups if cg.grade == grade]
    for cg in class_groups:
        labels[_class_group_label(cg)] = [cg.id]
    return labels


def _ir_atoms(x, batch_x, batch_occ, requirements_by_id, periods_by_id, no_teacher=None) -> list[Atom]:
    """Flatten the model's decision variables into what a selector can filter.

    The IR compiler needs one list of variables tagged with the class group,
    subject, teacher and slot each stands for. Everything here already exists
    in the model; this only labels it.

    Lab batches are the one case where a variable is not simply "a lesson":
    one class session runs as several simultaneous batches, so the session
    occupies the class's slot once while two or three teachers are busy.
    `occupies_class` / `occupies_teacher` keep those two counts from
    contaminating each other - without them, "this class has at most 6 periods
    a day" would count a split lab three times, and "this teacher has at most
    6" would miss the batch they taught.
    """
    atoms: list[Atom] = []

    for (req_id, teacher_id, period_id), var in x.items():
        req = requirements_by_id.get(req_id)
        period = periods_by_id.get(period_id)
        if req is None or period is None:
            continue
        atoms.append(Atom(
            var=var, requirement_id=req_id, class_group_id=req.class_group_id,
            subject_id=req.subject_id, teacher_id=teacher_id, period_id=period_id,
            day_of_week=period.day_of_week, order=period.order,
        ))

    for (req_id, period_id), var in batch_occ.items():
        req = requirements_by_id.get(req_id)
        period = periods_by_id.get(period_id)
        if req is None or period is None:
            continue
        atoms.append(Atom(
            var=var, requirement_id=req_id, class_group_id=req.class_group_id,
            subject_id=req.subject_id, teacher_id=None, period_id=period_id,
            day_of_week=period.day_of_week, order=period.order,
            occupies_class=True, occupies_teacher=False,
        ))

    for (req_id, period_id, _batch), teacher_vars in batch_x.items():
        req = requirements_by_id.get(req_id)
        period = periods_by_id.get(period_id)
        if req is None or period is None:
            continue
        for teacher_id, var in teacher_vars:
            atoms.append(Atom(
                var=var, requirement_id=req_id, class_group_id=req.class_group_id,
                subject_id=req.subject_id, teacher_id=teacher_id, period_id=period_id,
                day_of_week=period.day_of_week, order=period.order,
                # The class's slot is reserved once by the session's `occ`
                # variable, which is counted below - not once per batch here.
                occupies_class=False, occupies_teacher=True,
            ))

    # Lessons with no teacher yet fill the class's slot and nobody's time.
    for (req_id, period_id), var in (no_teacher or {}).items():
        req = requirements_by_id.get(req_id)
        period = periods_by_id.get(period_id)
        if req is None or period is None:
            continue
        atoms.append(Atom(
            var=var, requirement_id=req_id, class_group_id=req.class_group_id,
            subject_id=req.subject_id, teacher_id=None, period_id=period_id,
            day_of_week=period.day_of_week, order=period.order,
            occupies_class=True, occupies_teacher=False,
        ))

    return atoms


def _runs_by_day(all_periods: list[Period]) -> list[list[Period]]:
    """Each day's teaching periods, split into consecutive runs at breaks.

    "No more than 3 periods back to back" should not be tripped by periods
    either side of lunch - they aren't back to back, there is a break in
    between. Filtering breaks out of the list would make periods 3 and 5
    look adjacent and do exactly that, so the split happens here and the
    max-consecutive constraints below iterate runs rather than whole days.

    A day with no breaks yields exactly one run, which is the previous
    behaviour.
    """
    by_day: dict[int, list[Period]] = {}
    for p in all_periods:
        by_day.setdefault(p.day_of_week, []).append(p)

    runs: list[list[Period]] = []
    for day_periods in by_day.values():
        current: list[Period] = []
        for period in sorted(day_periods, key=lambda p: p.order):
            if period.is_break:
                if current:
                    runs.append(current)
                    current = []
            else:
                current.append(period)
        if current:
            runs.append(current)
    return runs


def _class_group_label(cg: ClassGroup) -> str:
    return f"{cg.grade} - {cg.name}" if cg.grade else cg.name


def _candidate_teacher_ids(
    req: SubjectRequirement,
    teachers: list[Teacher],
    teachers_by_id: dict[int, Teacher],
    class_groups_by_id: dict[int, ClassGroup],
) -> list[int]:
    """Which teachers could even be assigned to this requirement, ignoring
    period-level availability — qualification, grade restriction, and an
    explicit preferred-teacher pin (which bypasses both). Factored out so
    the main solve and _diagnose_constraint_conflicts's separate model
    below can't silently drift apart on what "qualified" means."""
    req_class_group = class_groups_by_id.get(req.class_group_id)
    req_grade = req_class_group.grade if req_class_group else None
    if req.preferred_teacher_id:
        return [req.preferred_teacher_id] if req.preferred_teacher_id in teachers_by_id else []
    # A shortlist ("Priya or Joseph") is an explicit choice like the pin
    # above: the solver picks one of them, whatever else is qualified.
    shortlist = getattr(req, "allowed_teacher_ids", None) or []
    if len(shortlist) >= 2:
        return [t for t in dict.fromkeys(shortlist) if t in teachers_by_id]
    return [
        t.id for t in teachers
        if req.subject_id in (t.qualified_subject_ids or [])
        and (not (t.qualified_grades or []) or not req_grade or req_grade in t.qualified_grades)
    ]


def _is_batched(req: SubjectRequirement, subjects_by_id: dict[int, "Subject"]) -> bool:
    subject = subjects_by_id.get(req.subject_id)
    n = subject.lab_batch_count if subject else None
    return isinstance(n, int) and n >= 2


def generate_school_timetable(db: Session, school_id: int) -> TimetableSolveResult:
    """
    Build a CP-SAT model from a school's real data and solve it.

    Model shape, mirroring the worked example in solve_example() but with
    real entities:
      - One boolean variable per (class_group, subject, teacher, period)
        combination that's even possible (teacher must be qualified for the
        subject and not marked unavailable for that period).
      - Each SubjectRequirement's periods_per_week is met exactly
        (sum of its variables across all teacher/period options == N).
      - A class group can have at most one subject/teacher in any one
        period (no double-booking a class).
      - A teacher can teach at most one class/subject in any one period
        (no double-booking a teacher).
      - If a teacher has max_periods_per_week set, their total assigned
        periods across everything must not exceed it.
      - "no_subject_period" Constraint rows (parameters={subject_id,
        position: "first"|"last", class_group_ids?}) ban that subject from
        the first/last period of every day. Scoped to specific class
        groups if class_group_ids is set, otherwise school-wide.
      - "require_subject_period" Constraint rows restrict that subject to
        ONLY the first/last period of every day (same scoping rules). If
        both types apply to the same requirement (contradictory input),
        the ban wins.
      - "no_subject_day" / "require_subject_day" Constraint rows
        (parameters={subject_id, day_of_week, class_group_ids?}) are the
        same idea as the two above but for a whole day of the week instead
        of a single first/last period — resolved into the same
        req_restricted_periods / req_required_periods sets, just matching
        every period on that day rather than one position.
      - "max_consecutive_periods" Constraint rows cap how many periods can
        run back-to-back on the same day, either for one subject
        (parameters={subject_id, max_consecutive, class_group_ids?},
        scoped like the placement types) or for one teacher's whole
        schedule regardless of subject/class (parameters={teacher_id,
        max_consecutive} — never scoped to class groups, since it's about
        that teacher's day, not one class's).
      - "min_gap_between_subjects" Constraint rows (parameters={
        first_subject_id, second_subject_id, min_gap, class_group_ids?})
        forbid the two named subjects from landing within min_gap periods
        of each other on the same day, for the scoped class groups (or
        school-wide). Symmetric — order doesn't matter, unlike
        subject_sequence below.
      - "subject_sequence" Constraint rows (parameters={first_subject_id,
        second_subject_id, class_group_ids?}) forbid second_subject from
        being scheduled in the period immediately after first_subject, for
        the same class group (e.g. "Math can't immediately follow PE").
        Cross-subject, so this (and min_gap_between_subjects) are the two
        constraint types that link two different SubjectRequirement rows'
        period-occupancy together.
      - Subject.lab_batch_count (2+) splits a requirement's sessions into
        that many simultaneous batches — e.g. a 60-student "Programming
        Lab" splitting into 3 batches of ~20 at the same period, each with
        its own teacher and (best-effort) room. See the lab_batch_count
        branch inside the main requirement-building loop below for the
        modeling approach. Known limitation: locked entries aren't honored
        for batched subjects (they're re-solved fresh every regeneration)
        — see the comment where locks are read, further down.
      - Room assignment is a second, separate CP-SAT solve
        (`_assign_rooms`) run after the main schedule is fixed — see its
        docstring for why it's kept separate rather than folded into the
        main model. Best-effort: entries that can't get a matching room
        (by Subject.required_room_type and Room.capacity vs. ClassGroup.
        student_count) just keep room_id=None rather than blocking
        generation.
      - SubjectRequirement.assistant_teacher_id reserves that teacher's
        time wherever this requirement lands: their own candidate/occ
        variables for a period are also fed into the assistant's
        teacher_period_vars and teacher_total_vars entries, so the
        existing "no teacher double-booked" and "respect max periods/week"
        constraints below cover the assistant for free, and a period where
        the assistant is marked unavailable is excluded from this
        requirement's eligible periods, same as it already is for the
        primary teacher. Previously this field was purely a label copied
        onto the generated entry (see TimetableEntry.assistant_teacher_id)
        with no effect on the solve at all, which meant an assistant could
        be silently double-booked between their own primary-teaching load
        and whatever they were assisting on. Not applied to lab-batch
        requirements (Subject.lab_batch_count >= 2) — a batch's "does a
        session happen" variable (`occ`) isn't the same variable as any
        one teacher's own assignment, so reserving the assistant's time
        against `occ` directly would double-count whenever the assistant
        also happens to be picked as one of the batch's own teachers.
        Assigning an assistant to a batched subject is allowed but not yet
        conflict-checked, consistent with lab batching's other known
        limitations (see the lock-honoring note below).

    Constraint plumbing: teacher availability (unavailable_period_ids) and
    workload caps (max_periods_per_week) are read directly off the Teacher
    row rather than the generic Constraint table, because
    app/routers/constraints.py already writes them there when it parses a
    matching constraint — the Constraint row itself is kept too, purely as
    a human-readable record for the UI. Everything else (placement,
    consecutive-period limits, subject sequencing) has no single row to
    live on, so those are read directly from the Constraint table here.

    Deliberately not yet handled (documented limitation, not a bug):
      - The catch-all "scheduling_rule" constraint type — recorded and
        shown in the UI, but not applied. Free-text rules that don't match
        any of the specific types above land here.
    """
    all_periods = db.query(Period).filter(Period.school_id == school_id).all()
    if not all_periods:
        return TimetableSolveResult(
            status="no_periods",
            errors=["This school has no periods defined yet. Add periods before generating a timetable."],
        )

    # Breaks (lunch, assembly) occupy a slot in the day but are never taught
    # in, so every variable and constraint below is built over teaching
    # periods only. They still matter structurally, which is why the full
    # list is kept: _runs_by_day uses it to split a day at its breaks, so a
    # teacher scheduled either side of lunch isn't counted as having taught
    # back-to-back.
    periods = [p for p in all_periods if not p.is_break]
    if not periods:
        return TimetableSolveResult(
            status="no_periods",
            errors=[
                "Every period in this school is marked as a break, so there is nothing to timetable. "
                "Unmark at least one period to generate."
            ],
        )

    # Group periods by day so "first period" / "last period" constraints
    # can be resolved to concrete period ids regardless of how many
    # periods a day has or what their labels are.
    periods_by_day: dict[int, list[Period]] = {}
    for p in periods:
        periods_by_day.setdefault(p.day_of_week, []).append(p)
    first_period_ids = {min(day_periods, key=lambda p: p.order).id for day_periods in periods_by_day.values()}
    last_period_ids = {max(day_periods, key=lambda p: p.order).id for day_periods in periods_by_day.values()}
    sorted_periods_by_day = {day: sorted(day_periods, key=lambda p: p.order) for day, day_periods in periods_by_day.items()}
    # Teaching runs, split at breaks. Used by the constraints that care
    # about adjacency (max-consecutive, subject-sequence) rather than about
    # distance, which reads period.order and so already counts breaks.
    teaching_runs = _runs_by_day(all_periods)

    class_groups = db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()
    requirements: list[SubjectRequirement] = []
    for cg in class_groups:
        requirements.extend(cg.requirements)

    # Elective blocks (see ElectiveBlock): subjects a section studies at the
    # same time, each student taking one. Each option is wrapped to look like
    # a requirement, so the placement rules and the legacy constraint types
    # below - which are all written per requirement - apply to a subject in a
    # block exactly as they would to an ordinary one, without each of them
    # needing a block-aware copy. What makes a block a block is handled in its
    # own section further down: one shared "does the block meet here"
    # variable per period, which every option's teacher choice is tied to.
    all_blocks: list[ElectiveBlock] = [b for cg in class_groups for b in cg.elective_blocks]
    blocks = [b for b in all_blocks if b.options]
    option_reqs: list[_OptionReq] = [
        _OptionReq(
            id=-o.id, class_group_id=b.class_group_id, subject_id=o.subject_id,
            periods_per_week=b.periods_per_week, preferred_teacher_id=o.preferred_teacher_id,
            block_id=b.id, option_id=o.id,
        )
        for b in blocks for o in b.options
    ]

    if not requirements and not blocks:
        return TimetableSolveResult(
            status="no_requirements",
            errors=["No class group has any subject requirements yet. Add at least one before generating."],
        )

    teachers = db.query(Teacher).filter(Teacher.school_id == school_id).all()
    teachers_by_id = {t.id: t for t in teachers}

    def _applies_to(constraint_params: dict, req: SubjectRequirement) -> bool:
        if constraint_params.get("subject_id") != req.subject_id:
            return False
        class_group_ids = constraint_params.get("class_group_ids")
        return not class_group_ids or req.class_group_id in class_group_ids

    # Every period id that falls on a given day, for resolving
    # "no_subject_day" / "require_subject_day" the same way first/last
    # period ids are resolved above.
    period_ids_by_day: dict[int, set[int]] = {
        day: {p.id for p in day_periods} for day, day_periods in periods_by_day.items()
    }

    # Per-requirement period restrictions from "no_subject_period" /
    # "require_subject_period" (position-based) and "no_subject_day" /
    # "require_subject_day" (whole-day) Constraint rows, resolved once up
    # front rather than re-querying per requirement.
    placement_constraints = (
        _constraint_query(db)
        .filter(
            Constraint.school_id == school_id,
            Constraint.type.in_(
                ["no_subject_period", "require_subject_period", "no_subject_day", "require_subject_day"]
            ),
        )
        .all()
    )
    # Zero periods that differ by grade or by day are reservations on ordinary
    # lesson slots - other grades are taught in them. (A whole-school zero
    # period at a fixed point is a non-lesson slot and never reaches here.)
    zero_by_grade: dict[str | None, set[int]] = {}
    for z in db.query(ZeroPeriod).filter(ZeroPeriod.school_id == school_id).all():
        zero_by_grade.setdefault(z.grade, set()).add(z.period_id)
    # Grades with a shorter day (Grades 1 and 2 home after period 6) are kept
    # out of the slots after their last period the same way.
    from app.services.timetable_structure import grade_off_period_ids
    school_row = db.get(School, school_id)
    off_by_grade = grade_off_period_ids(periods, school_row.grade_day_limits if school_row else None)
    zero_period_ids_by_class_group: dict[int, set[int]] = {
        cg.id: zero_by_grade.get(None, set()) | zero_by_grade.get(cg.grade, set()) | off_by_grade.get(cg.grade, set())
        for cg in class_groups
    }

    req_restricted_periods: dict[int, set[int]] = {}
    req_required_periods: dict[int, set[int] | None] = {}
    # Soft placement preferences, as period_id -> accumulated penalty weight.
    # Hard restrictions are enforced by never creating the variable at all,
    # which leaves nothing to penalise - so a preference has to take the
    # opposite route: build the variable, then make choosing it cost
    # something. Weights accumulate when several preferences discourage the
    # same slot, so two mild objections outweigh one strong one.
    req_discouraged_periods: dict[int, dict[int, int]] = {}
    # Options included: "no Physics in the last period" must keep the block
    # holding Physics out of the last period, since every option of a block
    # runs whenever the block does.
    for req in [*requirements, *option_reqs]:
        restricted: set[int] = set()
        required: set[int] | None = None
        discouraged: dict[int, int] = {}
        for c in placement_constraints:
            p = c.parameters or {}
            if not _applies_to(p, req):
                continue
            if c.type in ("no_subject_period", "require_subject_period"):
                position = p.get("position")
                if position not in ("first", "last"):
                    continue
                matched = first_period_ids if position == "first" else last_period_ids
            else:  # no_subject_day / require_subject_day
                day_of_week = p.get("day_of_week")
                if not isinstance(day_of_week, int):
                    continue
                matched = period_ids_by_day.get(day_of_week, set())
            bans = c.type in ("no_subject_period", "no_subject_day")
            if c.is_hard:
                if bans:
                    restricted |= matched
                else:
                    required = matched if required is None else (required & matched)
                continue

            # Soft. "Avoid these periods" discourages the matched set;
            # "prefer these periods" discourages everything else, which is
            # the same statement from the other side.
            weight = c.weight if isinstance(c.weight, int) and c.weight > 0 else 1
            target = matched if bans else {p.id for p in periods} - matched
            for period_id in target:
                discouraged[period_id] = discouraged.get(period_id, 0) + weight

        # A zero period kept free for this section's grade (or the whole
        # school) is a slot it has no lessons in, whatever the subject.
        restricted |= zero_period_ids_by_class_group.get(req.class_group_id, set())

        if required is not None:
            required -= restricted  # a ban always wins over a same-subject requirement
        req_restricted_periods[req.id] = restricted
        req_required_periods[req.id] = required
        # A hard ban already removes the variable, so paying a penalty for it
        # too would be double-counting something that cannot happen.
        req_discouraged_periods[req.id] = {
            pid: w for pid, w in discouraged.items() if pid not in restricted
        }

    errors = []
    # Rules that could not be applied — see TimetableSolveResult.warnings.
    warnings: list[str] = []
    model = cp_model.CpModel()

    # x[(requirement_id, teacher_id, period_id)] = this requirement's
    # subject is taught by this teacher in this period, for this class group.
    x: dict[tuple[int, int, int], cp_model.IntVar] = {}
    requirement_vars: dict[int, list] = {r.id: [] for r in requirements}
    class_group_period_vars: dict[tuple[int, int], list] = {}
    teacher_period_vars: dict[tuple[int, int], list] = {}
    teacher_total_vars: dict[int, list] = {t.id: [] for t in teachers}
    # req_period_vars[req.id][period.id] = list of candidate vars for that
    # requirement at that period (0 or 1 will end up true, thanks to
    # class_group_period_vars' AddAtMostOne below) — used by the
    # max_consecutive_periods constraint further down to know whether a
    # requirement "occupies" a given period without needing a separate
    # aggregate variable.
    req_period_vars: dict[int, dict[int, list]] = {r.id: {} for r in [*requirements, *option_reqs]}
    # Which teacher(s) could even be assigned to each requirement, before
    # any period-level filtering — kept around for _diagnose_infeasibility
    # below (specifically: spotting a sole qualified/preferred teacher
    # who's overloaded across their requirements).
    candidate_ids_by_req: dict[int, list[int]] = {}

    subjects_by_id = {s.id: s for s in db.query(Subject).filter(Subject.school_id == school_id).all()}
    class_groups_by_id = {c.id: c for c in class_groups}
    requirements_by_id = {r.id: r for r in requirements}
    periods_by_id = {p.id: p for p in periods}

    # batch_x[(req_id, period_id, batch_index)] = list of (teacher_id, var)
    # — the lab-batch-splitting counterpart to `x` above. See the
    # lab_batch_count branch below for why this needs its own structure
    # instead of reusing `x` directly (each batch needs its own teacher
    # choice, all tied to the same "does a session happen here" variable).
    batch_x: dict[tuple[int, int, int], list[tuple[int, cp_model.IntVar]]] = {}
    # batch_occ[(req_id, period_id)] = "does a session happen here" — the
    # variable that reserves the class group's slot for a split lab. Kept
    # separately from batch_x because for IR rules it is the class's lesson,
    # while batch_x's per-teacher vars are the teachers' assignments.
    batch_occ: dict[tuple[int, int], cp_model.IntVar] = {}
    # no_teacher[(req_id, period_id)] = a lesson of a subject nobody can teach
    # yet. The lesson still takes its place in the section's week - so adding
    # the teacher later doesn't reshuffle everything - but books no teacher.
    no_teacher: dict[tuple[int, int], cp_model.IntVar] = {}
    unstaffed_labels: list[str] = []

    def _batch_count(req: SubjectRequirement) -> int:
        subject = subjects_by_id.get(req.subject_id)
        n = subject.lab_batch_count if subject else None
        return n if isinstance(n, int) and n >= 2 else 1

    for req in requirements:
        # Qualification/grade/preferred-teacher-pin logic lives in
        # _candidate_teacher_ids so this and _diagnose_constraint_conflicts'
        # separate model below can't drift apart on what "qualified" means.
        candidate_ids = _candidate_teacher_ids(req, teachers, teachers_by_id, class_groups_by_id)
        candidate_ids_by_req[req.id] = candidate_ids

        if not candidate_ids:
            subject = subjects_by_id.get(req.subject_id)
            cg = class_groups_by_id.get(req.class_group_id)
            subject_name = subject.name if subject else f"subject_id={req.subject_id}"
            cg_label = _class_group_label(cg) if cg else f"class_group_id={req.class_group_id}"
            # No teacher yet: place the lessons without one rather than fail
            # the whole school. The admin is told, and the grid says so.
            unstaffed_labels.append(f"{subject_name} in {cg_label}")
            restricted = req_restricted_periods.get(req.id, set())
            required = req_required_periods.get(req.id)
            for period in periods:
                if period.id in restricted or (required is not None and period.id not in required):
                    continue
                var = model.NewBoolVar(f"nt_r{req.id}_p{period.id}")
                no_teacher[(req.id, period.id)] = var
                requirement_vars[req.id].append(var)
                class_group_period_vars.setdefault((req.class_group_id, period.id), []).append(var)
                req_period_vars[req.id].setdefault(period.id, []).append(var)
            continue

        restricted_periods_for_req = req_restricted_periods.get(req.id, set())
        required_periods_for_req = req_required_periods.get(req.id)  # None = no restriction
        batch_count = _batch_count(req)

        if batch_count == 1:
            # See the docstring's assistant_teacher_id bullet above: an
            # assistant assigned to co-teach this requirement has their
            # time reserved wherever it lands, by feeding the same
            # candidate variable into their own teacher_period_vars /
            # teacher_total_vars entries below.
            assistant_id = req.assistant_teacher_id
            assistant = teachers_by_id.get(assistant_id) if assistant_id else None
            assistant_unavailable = set(assistant.unavailable_period_ids or []) if assistant else set()
            for teacher_id in candidate_ids:
                teacher = teachers_by_id[teacher_id]
                unavailable = set(teacher.unavailable_period_ids or [])
                for period in periods:
                    if period.id in unavailable:
                        continue
                    if assistant and period.id in assistant_unavailable:
                        continue
                    if period.id in restricted_periods_for_req:
                        continue
                    if required_periods_for_req is not None and period.id not in required_periods_for_req:
                        continue
                    var = model.NewBoolVar(f"x_r{req.id}_t{teacher_id}_p{period.id}")
                    x[(req.id, teacher_id, period.id)] = var
                    requirement_vars[req.id].append(var)
                    class_group_period_vars.setdefault((req.class_group_id, period.id), []).append(var)
                    teacher_period_vars.setdefault((teacher_id, period.id), []).append(var)
                    teacher_total_vars[teacher_id].append(var)
                    req_period_vars[req.id].setdefault(period.id, []).append(var)
                    # Reserve the assistant's time too, unless they're
                    # already the primary teacher for this candidate (that
                    # would add the same var to the same list twice, which
                    # would silently double-count it in the AddAtMostOne /
                    # workload-cap constraints below).
                    if assistant and assistant_id != teacher_id:
                        teacher_period_vars.setdefault((assistant_id, period.id), []).append(var)
                        teacher_total_vars[assistant_id].append(var)
            continue

        # Lab-batch splitting (Subject.lab_batch_count >= 2): this
        # requirement's periods are sessions where the whole class group
        # splits into `batch_count` simultaneous batches, each with its
        # own teacher (and, in the room-assignment pass below, its own
        # room). Modeled with one "occ" var per eligible period (does a
        # session happen here at all — this is what reserves the class
        # group's slot and counts toward periods_per_week, exactly like a
        # normal requirement's per-period vars would) plus, per batch, a
        # teacher-choice var per candidate that's forced to sum to
        # exactly `occ` — i.e. "if a session happens here, batch b has
        # exactly one teacher; if not, zero". Feeding those teacher-choice
        # vars into the same teacher_period_vars/teacher_total_vars
        # structures the non-batched path uses means teacher
        # double-booking (and therefore batch-to-batch distinctness within
        # one period) and workload caps are enforced for free, with no
        # extra constraints needed here.
        if len(candidate_ids) < batch_count:
            subject = subjects_by_id.get(req.subject_id)
            cg = class_groups_by_id.get(req.class_group_id)
            errors.append(
                f"{subject.name if subject else 'This subject'} for "
                f"{_class_group_label(cg) if cg else 'a section'} splits into {batch_count} lab "
                f"batches, but only {len(candidate_ids)} qualified teacher(s) are available — add "
                f"more qualified teachers (need at least {batch_count}) to staff every batch at once."
            )
            continue

        for period in periods:
            if period.id in restricted_periods_for_req:
                continue
            if required_periods_for_req is not None and period.id not in required_periods_for_req:
                continue
            free_teacher_ids = [
                t_id for t_id in candidate_ids
                if period.id not in set(teachers_by_id[t_id].unavailable_period_ids or [])
            ]
            if len(free_teacher_ids) < batch_count:
                continue  # not enough free teachers to staff every batch at this period

            occ = model.NewBoolVar(f"occ_r{req.id}_p{period.id}")
            batch_occ[(req.id, period.id)] = occ
            requirement_vars[req.id].append(occ)
            class_group_period_vars.setdefault((req.class_group_id, period.id), []).append(occ)
            req_period_vars[req.id].setdefault(period.id, []).append(occ)

            for batch in range(batch_count):
                batch_vars = []
                for teacher_id in free_teacher_ids:
                    var = model.NewBoolVar(f"x_r{req.id}_b{batch}_t{teacher_id}_p{period.id}")
                    batch_vars.append((teacher_id, var))
                    teacher_period_vars.setdefault((teacher_id, period.id), []).append(var)
                    teacher_total_vars[teacher_id].append(var)
                batch_x[(req.id, period.id, batch)] = batch_vars
                # Exactly one teacher for this batch iff a session occurs
                # here — ties every batch's period choice to `occ`, so all
                # batches always land on the same period as each other.
                model.Add(sum(v for _, v in batch_vars) == occ)

    # Honor locked entries from the previous generation: an admin can lock
    # a slot in TimetableTab.jsx (PATCH /api/timetables/entries/{id}) to
    # pin it in place, then regenerate to re-solve everything else around
    # it. Only the most recent "draft" timetable's locks are read — older
    # ones are history, not the current schedule. Read before the blocks are
    # built, because a locked block slot changes which variables a block gets.
    previous_timetable = (
        db.query(Timetable)
        .filter(Timetable.school_id == school_id, Timetable.status == "draft")
        .order_by(Timetable.id.desc())
        .first()
    )
    locked_keys: set[tuple[int, int, int, int]] = set()
    locked_rooms: dict[tuple[int, int, int, int], int | None] = {}

    # ------------------------------------------------------------------
    # Elective blocks
    # ------------------------------------------------------------------
    # One "does the block meet here" variable per period (block_occ), and per
    # option a teacher choice that sums to exactly that variable - so when the
    # block meets, every option has exactly one teacher at that moment, and
    # when it doesn't, none do. It is the lab-batch structure above with the
    # parallel strands being different subjects rather than batches of one.
    #
    # block_occ reserves the section's slot ONCE. Each option's teacher
    # variables reserve the teachers. Counting them the other way round would
    # either fill the section three times over for a three-option block, or
    # leave the teachers free to be booked elsewhere at the same moment.
    #
    # option_x[(block_id, period_id, option_id)] = [(teacher_id, var), ...]
    option_x: dict[tuple[int, int, int], list[tuple[int, cp_model.IntVar]]] = {}
    block_occ: dict[tuple[int, int], cp_model.IntVar] = {}
    teacherless_options_by_block: dict[int, list[_OptionReq]] = {}
    options_by_block: dict[int, list[_OptionReq]] = {b.id: [] for b in blocks}
    for o in option_reqs:
        options_by_block[o.block_id].append(o)

    for b in all_blocks:
        if not b.options:
            cg = class_groups_by_id.get(b.class_group_id)
            warnings.append(
                f"{b.name} for {_class_group_label(cg) if cg else 'a section'} has no subjects "
                f"in it, so it was left out of the timetable."
            )

    # Locked block slots from the previous draft, as (block_id, period_id) ->
    # {option_id: (teacher_id, room_id)}. A lock is a deliberate admin
    # override, so - exactly as for an ordinary locked entry - the slot is
    # kept even if a placement rule or a teacher's availability has changed
    # since it was locked.
    locked_block_slots: dict[tuple[int, int], dict[int, tuple[int, int | None]]] = {}
    if previous_timetable:
        option_by_block_subject = {(o.block_id, o.subject_id): o for o in option_reqs}
        for le in previous_timetable.entries:
            if not le.locked or le.elective_block_id is None:
                continue
            option = option_by_block_subject.get((le.elective_block_id, le.subject_id))
            if option is None or le.period_id not in periods_by_id or le.teacher_id not in teachers_by_id:
                continue  # the block, the option, the period or the teacher is gone
            locked_block_slots.setdefault((le.elective_block_id, le.period_id), {})[option.option_id] = (
                le.teacher_id, le.room_id,
            )

    for block in blocks:
        opts = options_by_block[block.id]
        cg = class_groups_by_id.get(block.class_group_id)
        block_label = f"{block.name} for {_class_group_label(cg) if cg else 'a section'}"

        candidates: dict[int, list[int]] = {}
        for o in opts:
            candidates[o.id] = _candidate_teacher_ids(o, teachers, teachers_by_id, class_groups_by_id)
            candidate_ids_by_req[o.id] = candidates[o.id]
            if not candidates[o.id]:
                subject = subjects_by_id.get(o.subject_id)
                unstaffed_labels.append(f"{subject.name if subject else 'a subject'} in {block_label}")
        # Options nobody can teach yet run with the block, without a teacher;
        # only the others need staffing at the same moment.
        teacherless_opts = [o for o in opts if not candidates[o.id]]
        staffed_opts = [o for o in opts if candidates[o.id]]
        if teacherless_opts:
            teacherless_options_by_block[block.id] = teacherless_opts

        # A period is usable only if EVERY option may be there - they all run
        # whenever the block does - and every option can be given its own
        # teacher at that moment. The second check is a matching, not a
        # per-option one: two options whose only qualified teacher is the same
        # person each have "a" teacher, but never both at once.
        staffable: list[Period] = []
        free_by_period: dict[int, dict[int, list[int]]] = {}
        for period in periods:
            locked_here = locked_block_slots.get((block.id, period.id), {})
            if not locked_here and not all(
                period.id not in req_restricted_periods.get(o.id, set())
                and (req_required_periods.get(o.id) is None or period.id in req_required_periods[o.id])
                for o in opts
            ):
                continue
            free: dict[int, list[int]] = {}
            for o in staffed_opts:
                f = [
                    t for t in candidates[o.id]
                    if period.id not in set(teachers_by_id[t].unavailable_period_ids or [])
                ]
                locked_teacher = locked_here.get(o.option_id, (None, None))[0]
                if locked_teacher is not None and locked_teacher not in f:
                    f.append(locked_teacher)
                free[o.id] = f
            if all(free.values()) and _can_staff_all(free):
                staffable.append(period)
                free_by_period[period.id] = free

        if len(staffable) < block.periods_per_week:
            errors.append(_explain_unstaffable_block(
                block_label, block.periods_per_week, len(staffable), staffed_opts, candidates,
                teachers_by_id, subjects_by_id,
            ))
            continue

        block_vars = []
        for period in staffable:
            occ = model.NewBoolVar(f"occ_b{block.id}_p{period.id}")
            block_occ[(block.id, period.id)] = occ
            block_vars.append(occ)
            class_group_period_vars.setdefault((block.class_group_id, period.id), []).append(occ)
            for o in opts:
                # The option is present wherever the block is, which is what
                # lets the legacy per-requirement rules read it.
                req_period_vars[o.id].setdefault(period.id, []).append(occ)
                if not candidates[o.id]:
                    continue  # no teacher yet: present, but books nobody
                choice = []
                for teacher_id in free_by_period[period.id][o.id]:
                    var = model.NewBoolVar(f"x_b{block.id}_o{o.option_id}_t{teacher_id}_p{period.id}")
                    choice.append((teacher_id, var))
                    teacher_period_vars.setdefault((teacher_id, period.id), []).append(var)
                    teacher_total_vars.setdefault(teacher_id, []).append(var)
                option_x[(block.id, period.id, o.option_id)] = choice
                model.Add(sum(v for _, v in choice) == occ)
        model.Add(sum(block_vars) == block.periods_per_week)

        for (locked_block_id, period_id), by_option in locked_block_slots.items():
            if locked_block_id != block.id:
                continue
            occ = block_occ.get((block.id, period_id))
            if occ is None:
                warnings.append(
                    f"A locked {block_label} slot could not be kept, because its subjects can no "
                    f"longer all be given a teacher at that time. It was scheduled again freshly."
                )
                continue
            # Implied by pinning any of the slot's teachers below, since each
            # option's teacher choice sums to occ - stated anyway so the slot is
            # kept on its own terms rather than only as a side effect of which
            # teacher variables happened to be found.
            model.Add(occ == 1)
            option_subject = {o.option_id: o.subject_id for o in opts}
            for option_id, (teacher_id, room_id) in by_option.items():
                choice = option_x.get((block.id, period_id, option_id), [])
                var = next((v for t, v in choice if t == teacher_id), None)
                if var is None:
                    continue
                model.Add(var == 1)
                key = (block.class_group_id, option_subject[option_id], teacher_id, period_id)
                locked_keys.add(key)
                locked_rooms[key] = room_id

    if unstaffed_labels:
        shown = ", ".join(unstaffed_labels[:6])
        more = f" and {len(unstaffed_labels) - 6} more" if len(unstaffed_labels) > 6 else ""
        warnings.append(
            f"No teacher yet for {shown}{more}. Their lessons are in the timetable marked "
            f"\"No teacher yet\" - add a qualified teacher and generate again to fill them in."
        )

    if errors:
        return TimetableSolveResult(status="infeasible", errors=errors)

    # Ordinary requirements only: a locked block entry was handled above, and
    # matching one here by its subject would treat a block option as a
    # standalone requirement it is not.
    req_by_class_subject = {(r.class_group_id, r.subject_id): r for r in requirements}
    if previous_timetable:
        for le in previous_timetable.entries:
            if not le.locked or le.elective_block_id is not None:
                continue
            req = req_by_class_subject.get((le.class_group_id, le.subject_id))
            if not req:
                continue  # the requirement this was locked against no longer exists
            if _batch_count(req) > 1:
                # Known limitation: locking isn't supported for lab-batch
                # subjects yet — honoring a lock here would need to pin
                # one specific batch's teacher without disturbing the
                # others' occ-tied structure above, which the current
                # single-key (req, teacher, period) lock format can't
                # express. Batched sessions just get freshly re-solved
                # every regeneration instead of silently mis-locking.
                continue
            if le.teacher_id is None:
                # A lesson locked before it had a teacher.
                var = no_teacher.get((req.id, le.period_id))
                if var is not None:
                    model.Add(var == 1)
                    result_key = (le.class_group_id, le.subject_id, None, le.period_id)
                    locked_keys.add(result_key)
                    locked_rooms[result_key] = le.room_id
                continue
            if le.teacher_id not in teachers_by_id:
                continue  # the teacher was removed
            key = (req.id, le.teacher_id, le.period_id)
            if key not in x:
                # Filtered out of the normal candidate list (e.g. the
                # teacher's availability or a placement constraint changed
                # since this was locked). An explicit lock is a deliberate
                # admin override, so honor it anyway rather than silently
                # dropping it — it participates in every other constraint
                # below exactly like a normal candidate variable would.
                var = model.NewBoolVar(f"locked_r{req.id}_t{le.teacher_id}_p{le.period_id}")
                x[key] = var
                requirement_vars[req.id].append(var)
                class_group_period_vars.setdefault((req.class_group_id, le.period_id), []).append(var)
                teacher_period_vars.setdefault((le.teacher_id, le.period_id), []).append(var)
                teacher_total_vars.setdefault(le.teacher_id, []).append(var)
                req_period_vars[req.id].setdefault(le.period_id, []).append(var)
            model.Add(x[key] == 1)
            result_key = (le.class_group_id, le.subject_id, le.teacher_id, le.period_id)
            locked_keys.add(result_key)
            locked_rooms[result_key] = le.room_id

    # ------------------------------------------------------------------
    # One teacher per subject per section, all week
    # ------------------------------------------------------------------
    # Without this the teacher is chosen lesson by lesson, so a section's
    # English could be Mrs. Rao on Monday and Mr. Iyer on Tuesday - valid by
    # every other rule, and not how any school works. Each strand that needs
    # a teacher (a requirement; each batch of a split lab; each option of an
    # elective block) gets one "this is the teacher" choice, and every lesson
    # of that strand may only use the chosen teacher.
    #
    # A strand whose locked lessons already name two different teachers (a
    # timetable from before this rule, then locked) can't satisfy it, and a
    # lock is a deliberate override - so that strand is left free and the
    # admin is told, rather than the whole generation failing.
    locked_teachers_by_req: dict[int, set[int]] = {}
    if previous_timetable:
        req_by_cg_subject = {(r.class_group_id, r.subject_id): r for r in requirements}
        for le in previous_timetable.entries:
            if le.locked and le.elective_block_id is None and le.lab_batch is None:
                r = req_by_cg_subject.get((le.class_group_id, le.subject_id))
                if r is not None and le.teacher_id is not None:
                    locked_teachers_by_req.setdefault(r.id, set()).add(le.teacher_id)

    def _one_teacher(name: str, by_teacher: dict[int, list]) -> None:
        if len(by_teacher) <= 1:
            return  # one possible teacher: already consistent
        chosen = {t: model.NewBoolVar(f"{name}_t{t}") for t in by_teacher}
        model.AddExactlyOne(chosen.values())
        for t, lesson_vars in by_teacher.items():
            for v in lesson_vars:
                model.AddImplication(v, chosen[t])

    strands: dict[tuple, dict[int, list]] = {}
    for (req_id, teacher_id, _period_id), var in x.items():
        strands.setdefault(("r", req_id), {}).setdefault(teacher_id, []).append(var)
    for (req_id, _period_id, batch), choice in batch_x.items():
        for teacher_id, var in choice:
            strands.setdefault(("b", req_id, batch), {}).setdefault(teacher_id, []).append(var)
    for (block_id, _period_id, option_id), choice in option_x.items():
        for teacher_id, var in choice:
            strands.setdefault(("o", block_id, option_id), {}).setdefault(teacher_id, []).append(var)

    for key, by_teacher in ({} if "one_teacher" in _RELAX.get() else strands).items():
        if key[0] == "r" and len(locked_teachers_by_req.get(key[1], ())) > 1:
            req = requirements_by_id.get(key[1])
            subject = subjects_by_id.get(req.subject_id) if req else None
            cg = class_groups_by_id.get(req.class_group_id) if req else None
            warnings.append(
                f"{subject.name if subject else 'A subject'} in {_class_group_label(cg) if cg else 'a section'} "
                f"has locked lessons with different teachers, so it may still be split between them. "
                f"Unlock them and generate again to give it a single teacher."
            )
            continue
        _one_teacher("one_" + "_".join(str(k) for k in key), by_teacher)

    # Weighted cost of every soft constraint this timetable violates,
    # minimised at the end. Empty when a school has only hard rules, in
    # which case no objective is added at all and the solver behaves exactly
    # as it did before soft constraints existed - it stops at the first
    # feasible answer instead of proving one optimal.
    penalties: list = []

    # Soft placement preferences: the variable exists (unlike a hard ban),
    # so scheduling into a discouraged period is allowed but costs its
    # weight.
    for req in requirements:
        for period_id, weight in req_discouraged_periods.get(req.id, {}).items():
            for var in req_period_vars[req.id].get(period_id, []):
                penalties.append(weight * var)
    # An option discouraging a period discourages its whole block there, since
    # the option cannot be there without the block.
    for o in option_reqs:
        for period_id, weight in req_discouraged_periods.get(o.id, {}).items():
            occ = block_occ.get((o.block_id, period_id))
            if occ is not None:
                penalties.append(weight * occ)

    # Each requirement must be met exactly (periods_per_week times).
    for req in requirements:
        model.Add(sum(requirement_vars[req.id]) == req.periods_per_week)

    # No class group double-booked in a period.
    for _, group_vars in class_group_period_vars.items():
        model.AddAtMostOne(group_vars)

    # No teacher double-booked in a period.
    for _, group_vars in teacher_period_vars.items():
        model.AddAtMostOne(group_vars)

    # Respect each teacher's max periods/week, if set.
    for teacher in teachers:
        if teacher.max_periods_per_week is not None and teacher_total_vars[teacher.id] and "max_periods" not in _RELAX.get():
            model.Add(sum(teacher_total_vars[teacher.id]) <= teacher.max_periods_per_week)

    # "max_consecutive_periods" Constraint rows: cap how many periods in a
    # row (same day, adjacent order) a subject can run for the scoped
    # requirements. Implemented as a sliding window over each day's
    # periods — no new variables needed, since a requirement's presence at
    # a period is just the sum of its candidate vars there (0 or 1,
    # guaranteed by the AddAtMostOne on class_group_period_vars above).
    consecutive_constraints = (
        _constraint_query(db)
        .filter(
            Constraint.school_id == school_id,
            Constraint.type == "max_consecutive_periods",
        )
        .all()
    )
    for c in consecutive_constraints:
        p = c.parameters or {}
        max_consecutive = p.get("max_consecutive")
        if not isinstance(max_consecutive, int) or max_consecutive < 1:
            continue

        teacher_id = p.get("teacher_id")
        if teacher_id is not None:
            # Teacher variant: caps how many periods in a row that teacher
            # is scheduled at all, any subject/class — uses
            # teacher_period_vars (already AddAtMostOne'd to 0-or-1 per
            # period) instead of one requirement's per-period vars.
            for day_periods in teaching_runs:
                if len(day_periods) <= max_consecutive:
                    continue
                for start in range(len(day_periods) - max_consecutive):
                    window = day_periods[start:start + max_consecutive + 1]
                    window_vars = [
                        v for wp in window for v in teacher_period_vars.get((teacher_id, wp.id), [])
                    ]
                    if window_vars:
                        _at_most(
                            model, penalties, sum(window_vars), max_consecutive, c,
                            f"over_consec_t{teacher_id}_c{c.id}_s{start}",
                        )
            continue

        for req in [*requirements, *option_reqs]:
            if not _applies_to(p, req):
                continue
            per_period_vars = req_period_vars.get(req.id, {})
            for day_periods in teaching_runs:
                if len(day_periods) <= max_consecutive:
                    continue  # can't possibly exceed the cap in this run
                for start in range(len(day_periods) - max_consecutive):
                    window = day_periods[start:start + max_consecutive + 1]
                    window_vars = [v for wp in window for v in per_period_vars.get(wp.id, [])]
                    if window_vars:
                        _at_most(
                            model, penalties, sum(window_vars), max_consecutive, c,
                            f"over_consec_r{req.id}_c{c.id}_s{start}",
                        )

    # "max_subject_periods_per_day" Constraint rows: cap how many times one
    # subject can land in a single day for a class group. "Both PE periods
    # can't be on the same day" is max_per_day=1 - a spread-across-the-week
    # rule, which none of the other types express: max_consecutive caps
    # back-to-back runs, and min_gap is about two *different* subjects.
    per_day_constraints = (
        _constraint_query(db)
        .filter(
            Constraint.school_id == school_id,
            Constraint.type == "max_subject_periods_per_day",
        )
        .all()
    )
    for c in per_day_constraints:
        p = c.parameters or {}
        max_per_day = p.get("max_per_day")
        if not isinstance(max_per_day, int) or max_per_day < 1:
            continue
        for req in [*requirements, *option_reqs]:
            if not _applies_to(p, req):
                continue
            per_period_vars = req_period_vars.get(req.id, {})
            for day_periods in sorted_periods_by_day.values():
                day_vars = [v for dp in day_periods for v in per_period_vars.get(dp.id, [])]
                # Nothing to cap if the day can't even hold more than the limit.
                if len(day_vars) <= max_per_day:
                    continue
                _at_most(
                    model, penalties, sum(day_vars), max_per_day, c,
                    f"per_day_r{req.id}_c{c.id}_d{day_periods[0].day_of_week}",
                )

    # "subject_sequence" Constraint rows: forbid second_subject_id from
    # being scheduled in the period immediately after first_subject_id, on
    # the same day, for the same class group. Requirements are unique per
    # (class_group, subject) (see SubjectRequirement's unique constraint),
    # so each side of the rule maps to at most one requirement per class
    # group — no aggregation needed beyond the per-period var lists already
    # built above.
    sequence_constraints = (
        _constraint_query(db)
        .filter(
            Constraint.school_id == school_id,
            Constraint.type == "subject_sequence",
        )
        .all()
    )
    # Ordinary requirements and block options, by (section, subject).
    subject_owner = {
        **req_by_class_subject,
        **{(o.class_group_id, o.subject_id): o for o in option_reqs},
    }

    def _same_block(a, b) -> bool:
        return isinstance(a, _OptionReq) and isinstance(b, _OptionReq) and a.block_id == b.block_id

    if sequence_constraints:
        for c in sequence_constraints:
            p = c.parameters or {}
            first_subject_id = p.get("first_subject_id")
            second_subject_id = p.get("second_subject_id")
            if not first_subject_id or not second_subject_id:
                continue
            class_group_ids = p.get("class_group_ids") or [cg.id for cg in class_groups]
            for cg_id in class_group_ids:
                req1 = subject_owner.get((cg_id, first_subject_id))
                req2 = subject_owner.get((cg_id, second_subject_id))
                if not req1 or not req2 or _same_block(req1, req2):
                    continue  # this class group doesn't have both subjects; nothing to constrain
                for day_periods in teaching_runs:
                    for i in range(len(day_periods) - 1):
                        period, next_period = day_periods[i], day_periods[i + 1]
                        first_vars = req_period_vars.get(req1.id, {}).get(period.id, [])
                        second_vars = req_period_vars.get(req2.id, {}).get(next_period.id, [])
                        if first_vars and second_vars:
                            _at_most(
                                model, penalties, sum(first_vars) + sum(second_vars), 1, c,
                                f"seq_c{c.id}_cg{cg_id}_p{period.id}",
                            )

    # "min_gap_between_subjects" Constraint rows: forbid first_subject_id
    # and second_subject_id from landing within min_gap periods of each
    # other on the same day, for the scoped class groups. Unlike
    # subject_sequence, this is symmetric (order doesn't matter) and
    # covers every period pair within the gap, not just the immediately
    # adjacent one — implemented as a direct "at most one of these two
    # periods" constraint for every same-day period pair whose order
    # distance is less than min_gap (this naturally also covers the
    # same-period case, distance 0, though that's already impossible via
    # the class-group double-booking constraint above).
    gap_constraints = (
        _constraint_query(db)
        .filter(
            Constraint.school_id == school_id,
            Constraint.type == "min_gap_between_subjects",
        )
        .all()
    )
    for c in gap_constraints:
        p = c.parameters or {}
        first_subject_id = p.get("first_subject_id")
        second_subject_id = p.get("second_subject_id")
        min_gap = p.get("min_gap")
        if not first_subject_id or not second_subject_id or not isinstance(min_gap, int) or min_gap < 1:
            continue
        class_group_ids = p.get("class_group_ids") or [cg.id for cg in class_groups]
        for cg_id in class_group_ids:
            req1 = subject_owner.get((cg_id, first_subject_id))
            req2 = subject_owner.get((cg_id, second_subject_id))
            if not req1 or not req2 or _same_block(req1, req2):
                continue  # this class group doesn't have both subjects; nothing to constrain
            for day_periods in sorted_periods_by_day.values():
                for p1 in day_periods:
                    p1_vars = req_period_vars.get(req1.id, {}).get(p1.id, [])
                    if not p1_vars:
                        continue
                    for p2 in day_periods:
                        # min_gap counts the periods that must SEPARATE the two
                        # subjects, so min_gap=1 means at least one period in
                        # between - orders 1 and 3, a difference of 2. Testing
                        # `>= min_gap` made min_gap=1 forbid only a difference
                        # of 0, which one class group can never have anyway
                        # (AddAtMostOne per class/period above) - so the most
                        # natural phrasing of this rule, "X can't immediately
                        # follow Y", silently did nothing while the UI reported
                        # it as enforced.
                        if abs(p1.order - p2.order) > min_gap:
                            continue
                        p2_vars = req_period_vars.get(req2.id, {}).get(p2.id, [])
                        if p2_vars:
                            _at_most(
                                model, penalties, sum(p1_vars) + sum(p2_vars), 1, c,
                                f"gap_c{c.id}_cg{cg_id}_p{p1.id}_{p2.id}",
                            )

    # ------------------------------------------------------------------
    # Generic IR rules (Constraint.type == "ir")
    # ------------------------------------------------------------------
    # Everything above is one block of code per named constraint type, which
    # is why there were only ever nine of them: a tenth rule shape meant a
    # tenth block here. An IR rule is a selector and a scope over the same
    # variables, so the shapes are data and this is one call regardless of
    # how many there are. See app/services/constraint_ir.py.
    #
    # The two kinds coexist deliberately. Migrating the nine legacy types
    # into IR at the same time as introducing it would put every rule that
    # currently works at risk of the new path's bugs, for no gain the day it
    # ships; they can be retired once the IR has run against real schools.
    ir_constraints = (
        _constraint_query(db)
        .filter(Constraint.school_id == school_id, Constraint.type == "ir")
        .all()
    )
    if ir_constraints:
        atoms = _ir_atoms(x, batch_x, batch_occ, requirements_by_id, periods_by_id, no_teacher)
        atoms.extend(_block_atoms(block_occ, option_x, option_reqs, periods_by_id))
        index = SchoolIndex(
            subject_ids={s.name: s.id for s in subjects_by_id.values()},
            teacher_ids={t.name: t.id for t in teachers},
            class_group_ids=_class_group_labels(class_groups),
            # Lesson slots only: "period 5" is the fifth lesson of the day.
            # Breaks, the class teacher period and a school-wide zero period
            # sit between numbers, so adding one never shifts a saved rule -
            # see app/services/timetable_structure.py.
            orders_by_day={
                day: sorted(p.order for p in day_periods)
                for day, day_periods in periods_by_day.items()
            },
            # Teaching periods only, and per day, so "the last period" on a
            # half-day Saturday is that day's last rather than the week's - and
            # never lands on lunch.
            first_order_by_day={
                day: min(p.order for p in day_periods)
                for day, day_periods in periods_by_day.items()
            },
            last_order_by_day={
                day: max(p.order for p in day_periods)
                for day, day_periods in periods_by_day.items()
            },
        )
        rules = []
        for c in ir_constraints:
            try:
                rules.append((f"c{c.id}", rule_from_dict(c.parameters or {})))
            except IRError as exc:
                # A stored rule that no longer validates is a bug in whatever
                # wrote it, not something the admin can act on mid-solve - but
                # it must not pass silently either, or it joins the population
                # of rules that claim to be enforced and do nothing.
                warnings.append(
                    f"{c.description or 'A rule'} was not applied because it is "
                    f"not a valid rule: {exc}."
                )
        warnings.extend(compile_rules(model, penalties, atoms, rules, index))

    # Only added when something soft exists. A school with only hard rules
    # gets the previous behaviour exactly - the solver returns the first
    # feasible timetable rather than searching for the best one, which is
    # both faster and the reason "optimal" keeps meaning what it used to.
    if penalties:
        model.Minimize(sum(penalties))

    # Cheap and decisive: if whole sections can't be shared out between the
    # teachers at all, no timetable exists - say so in a second rather than
    # after the full search budget.
    staffing = [] if _RELAX.get() else _diagnose_teacher_assignment(
        requirements, option_reqs, candidate_ids_by_req, teachers_by_id, periods,
        subjects_by_id, class_groups_by_id, _batch_count,
    )
    if staffing:
        return TimetableSolveResult(
            status="infeasible", assignments=[], locked_keys=locked_keys,
            errors=errors + staffing, warnings=warnings,
        )

    solver, status = _solve_timetable_model(model, bool(penalties))

    status_name = {
        cp_model.OPTIMAL: "optimal",
        cp_model.FEASIBLE: "feasible",
        cp_model.INFEASIBLE: "infeasible",
    }.get(status, "unknown")

    assignments = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        req_by_id = {r.id: r for r in requirements}
        for (req_id, teacher_id, period_id), var in x.items():
            if solver.Value(var):
                req = req_by_id[req_id]
                assignments.append(
                    {
                        "class_group_id": req.class_group_id,
                        "subject_id": req.subject_id,
                        "teacher_id": teacher_id,
                        "period_id": period_id,
                    }
                )
        # Lab-batch assignments live in batch_x, not x (see the
        # lab_batch_count branch above) — pulled in separately here, each
        # tagged with its 1-indexed batch number so the frontend can show
        # "Batch 1 - Room 3" / "Batch 2 - Room 5" for the same class,
        # subject, and period instead of two indistinguishable rows.
        for (req_id, period_id, batch), teacher_options in batch_x.items():
            for teacher_id, var in teacher_options:
                if solver.Value(var):
                    req = req_by_id[req_id]
                    assignments.append(
                        {
                            "class_group_id": req.class_group_id,
                            "subject_id": req.subject_id,
                            "teacher_id": teacher_id,
                            "period_id": period_id,
                            "batch": batch + 1,
                        }
                    )
                    break
        # Block options, one entry each, tagged with their block so the grid can
        # show them as one slot and dragging can move them together.
        option_by_id = {o.option_id: o for o in option_reqs}
        for (block_id, period_id, option_id), choice in option_x.items():
            for teacher_id, var in choice:
                if solver.Value(var):
                    o = option_by_id[option_id]
                    assignments.append(
                        {
                            "class_group_id": o.class_group_id,
                            "subject_id": o.subject_id,
                            "teacher_id": teacher_id,
                            "period_id": period_id,
                            "elective_block_id": block_id,
                        }
                    )
                    break
        for (req_id, period_id), var in no_teacher.items():
            if solver.Value(var):
                req = req_by_id[req_id]
                assignments.append({
                    "class_group_id": req.class_group_id, "subject_id": req.subject_id,
                    "teacher_id": None, "period_id": period_id,
                })
        for (block_id, period_id), occ in block_occ.items():
            if teacherless_options_by_block.get(block_id) and solver.Value(occ):
                for o in teacherless_options_by_block[block_id]:
                    assignments.append({
                        "class_group_id": o.class_group_id, "subject_id": o.subject_id,
                        "teacher_id": None, "period_id": period_id, "elective_block_id": block_id,
                    })
        _assign_rooms(db, school_id, assignments, locked_rooms=locked_rooms)

    if status_name in ("infeasible", "unknown"):
        errors = errors + _diagnose_infeasibility(
            requirements, teachers_by_id, periods,
            req_restricted_periods, req_required_periods, candidate_ids_by_req,
            subjects_by_id, class_groups_by_id,
            blocks=blocks, option_reqs=option_reqs,
            unavailable_by_cg=zero_period_ids_by_class_group,
        )
        # Whole sections have to be shared out between teachers now that a
        # section keeps one teacher per subject - the commonest new cause,
        # and invisible to the period-counting checks above.
        if not errors:
            errors = errors + _diagnose_teacher_assignment(
                requirements, option_reqs, candidate_ids_by_req, teachers_by_id, periods,
                subjects_by_id, class_groups_by_id, _batch_count,
            )
        # Only reachable for a *proven* infeasibility (not "unknown", a
        # timeout) — SufficientAssumptionsForInfeasibility() needs CP-SAT to
        # have actually established there's no solution, not just failed to
        # find one in time. Only attempted when the cheap checks above found
        # nothing, since they're strictly cheaper and more specific when
        # they do apply.
        if not errors and status_name == "infeasible":
            errors = errors + _diagnose_constraint_conflicts(
                db, school_id, requirements, teachers, teachers_by_id, periods,
                periods_by_day, teaching_runs, first_period_ids, last_period_ids,
                period_ids_by_day, class_groups_by_id, subjects_by_id, class_groups,
            )

    return TimetableSolveResult(
        status=status_name, assignments=assignments, locked_keys=locked_keys,
        errors=errors, warnings=warnings,
    )


def _diagnose_teacher_assignment(
    requirements, option_reqs, candidate_ids_by_req, teachers_by_id, periods,
    subjects_by_id, class_groups_by_id, batch_count,
) -> list[str]:
    """Can every section be given ONE teacher per subject at all?

    Ignores when lessons happen and asks only who teaches what: each strand
    (a section's subject, each batch of a split lab, each option of a block)
    takes one of its qualified teachers, and no teacher may end up with more
    periods than their weekly limit (or than the lesson periods they are
    available for). If that alone is impossible, no timetable exists, and the
    reason can be said in terms an admin can act on.

    The whole school is tried first; when that fails, each subject on its own,
    so the message can name the subject (or, if every subject fits alone but
    not together, the teachers who teach several of them).
    """
    lesson_ids = [p.id for p in periods if not p.is_break]

    def capacity(t) -> int:
        free = sum(1 for pid in lesson_ids if pid not in set(t.unavailable_period_ids or []))
        return min(t.max_periods_per_week, free) if t.max_periods_per_week else free

    strands = []  # (subject_id, class_group_id, periods, candidates, group) - group: strands that run at once
    for r in requirements:
        cands = candidate_ids_by_req.get(r.id) or []
        if not cands or not r.periods_per_week:
            continue
        for b in range(batch_count(r)):
            strands.append((r.subject_id, r.class_group_id, r.periods_per_week, cands, ("r", r.id)))
    for o in option_reqs:
        cands = candidate_ids_by_req.get(o.id) or []
        if cands and o.periods_per_week:
            strands.append((o.subject_id, o.class_group_id, o.periods_per_week, cands, ("b", o.block_id)))
    if not strands:
        return []

    def fits(selected) -> bool:
        m = cp_model.CpModel()
        y = {}
        for i, (_, _, _, cands, _) in enumerate(selected):
            for t in cands:
                y[(i, t)] = m.NewBoolVar("")
            m.AddExactlyOne(y[(i, t)] for t in cands)
        by_group: dict = {}
        for i, (_, _, _, cands, group) in enumerate(selected):
            for t in cands:
                by_group.setdefault((group, t), []).append(y[(i, t)])
        for vs in by_group.values():
            if len(vs) > 1:
                m.AddAtMostOne(vs)  # strands that run at once need different teachers
        load: dict = {}
        for (i, t), v in y.items():
            load.setdefault(t, []).append(selected[i][2] * v)
        for t, terms in load.items():
            m.Add(sum(terms) <= capacity(teachers_by_id[t]))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5
        solver.parameters.num_search_workers = _search_workers()
        return solver.Solve(m) != cp_model.INFEASIBLE

    if fits(strands):
        return []

    def label(cg_id):
        cg = class_groups_by_id.get(cg_id)
        return _class_group_label(cg) if cg else "a section"

    messages = []
    subject_ids = sorted({st[0] for st in strands}, key=lambda sid: subjects_by_id[sid].name if sid in subjects_by_id else "")
    for sid in subject_ids:
        mine = [st for st in strands if st[0] == sid]
        if fits(mine):
            continue
        name = subjects_by_id[sid].name if sid in subjects_by_id else "A subject"
        need = sum(st[2] for st in mine)
        teacher_ids = sorted({t for st in mine for t in st[3]}, key=lambda t: teachers_by_id[t].name)
        sections = ", ".join(f"{label(st[1])} ({st[2]})" for st in mine)
        staff = ", ".join(f"{teachers_by_id[t].name} (up to {capacity(teachers_by_id[t])})" for t in teacher_ids)
        messages.append(
            f"{name} can't be shared out: each section keeps one {name} teacher all week, and the "
            f"sections need {need} periods in total - {sections} - but the qualified teachers, "
            f"{staff}, can't take whole sections without someone going over their limit. "
            f"Raise a teacher's max periods/week, qualify another teacher for {name} "
            f"(or for more grades), or reduce {name}'s periods/week."
        )
    if messages:
        return messages

    # Every subject fits alone; they clash through teachers who teach several.
    shared = {}
    for st in strands:
        for t in st[3]:
            shared.setdefault(t, set()).add(st[0])
    busy = [t for t, subs in shared.items() if len(subs) > 1]
    names = ", ".join(
        f"{teachers_by_id[t].name} ({' and '.join(sorted(subjects_by_id[x].name for x in shared[t] if x in subjects_by_id))})"
        for t in sorted(busy, key=lambda t: teachers_by_id[t].name)[:6]
    )
    return [
        "Each subject can be staffed on its own, but not all at once: teachers who teach more than one "
        f"subject don't have enough periods for every section they'd need to take whole - {names}. "
        "Raise their max periods/week or add another teacher for one of those subjects."
    ]


def _diagnose_infeasibility(
    requirements: list[SubjectRequirement],
    teachers_by_id: dict[int, Teacher],
    periods: list[Period],
    req_restricted_periods: dict[int, set[int]],
    req_required_periods: dict[int, set[int] | None],
    candidate_ids_by_req: dict[int, list[int]],
    subjects_by_id: dict[int, Subject],
    class_groups_by_id: dict[int, ClassGroup],
    blocks: list | None = None,
    option_reqs: list | None = None,
    unavailable_by_cg: dict[int, set[int]] | None = None,
) -> list[str]:
    """
    Best-effort explanation for why the solve came back infeasible (or
    timed out inconclusively) instead of just surfacing CP-SAT's raw
    status. This is deliberately NOT a general infeasibility explainer —
    that's a genuinely hard problem (formally, finding a minimal
    unsatisfiable subset of constraints) that would need something like
    CP-SAT's assumption-based conflict analysis to do properly for
    arbitrary constraint interactions. Instead, this checks for the
    handful of causes that are both common in practice and cheap to
    detect directly from the data, without needing to interrogate the
    solver at all:

      1. A class group's total periods/week demand (summed across all its
         subjects) exceeds how many periods the school even has defined.
      2. A "subject must be in the first/last period" placement constraint
         leaves fewer eligible periods than the subject's periods/week —
         e.g. "6 periods/week, but restricted to only the first period of
         a 5-day week" is impossible regardless of anything else.
      3. A teacher who is the *only* qualified (or explicitly preferred)
         teacher for one or more requirements is asked for more total
         periods/week than their max_periods_per_week cap or their actual
         available periods allow.

    Each hit becomes one specific, actionable sentence. Returns an empty
    list if none of these apply — a genuinely opaque infeasibility (e.g.
    an interaction between several constraints, none of which alone is
    the problem) isn't diagnosed, and the caller falls back to a generic
    message rather than pretending to know the cause.
    """
    messages: list[str] = []

    # 1. Total demand vs. total periods available, per class group.
    total_periods = len(periods)
    demand_by_cg: dict[int, int] = {}
    for req in requirements:
        demand_by_cg[req.class_group_id] = demand_by_cg.get(req.class_group_id, 0) + req.periods_per_week
    # A block occupies its section once, however many options it has.
    for block in blocks or []:
        demand_by_cg[block.class_group_id] = demand_by_cg.get(block.class_group_id, 0) + block.periods_per_week
    lesson_ids = {p.id for p in periods}
    for cg_id, demand in demand_by_cg.items():
        # A grade with a shorter day, or a zero period of its own, has fewer
        # periods to fill than the school's whole week.
        kept_free = (unavailable_by_cg or {}).get(cg_id, set()) & lesson_ids
        available = total_periods - len(kept_free)
        if demand > available:
            cg = class_groups_by_id.get(cg_id)
            label = _class_group_label(cg) if cg else f"class_group_id={cg_id}"
            if kept_free:
                messages.append(
                    f"{label} needs {demand} periods/week in total across all its subjects, but it "
                    f"only has {available} periods in its week (its grade's shorter day or zero "
                    f"periods take up the rest). Reduce periods/week for one or more of its subjects, "
                    f"or give its grade a longer day in Setup."
                )
            else:
                messages.append(
                    f"{label} needs {demand} periods/week in total across all its subjects, but "
                    f"the school only has {total_periods} periods defined. Add more periods, or "
                    f"reduce periods/week for one or more subjects in this section."
                )

    # 2. A placement restriction leaves too few eligible periods for a
    # requirement's periods/week, regardless of teacher availability.
    for req in requirements:
        required = req_required_periods.get(req.id)
        if required is not None and len(required) < req.periods_per_week:
            subject = subjects_by_id.get(req.subject_id)
            cg = class_groups_by_id.get(req.class_group_id)
            subject_name = subject.name if subject else f"subject_id={req.subject_id}"
            cg_label = _class_group_label(cg) if cg else f"class_group_id={req.class_group_id}"
            messages.append(
                f"{subject_name} for {cg_label} needs {req.periods_per_week} periods/week, but "
                f"a subject-placement constraint restricts it to only {len(required)} eligible "
                f"period(s) — loosen that constraint or reduce periods/week."
            )

    # 3. A sole qualified/preferred teacher is asked for more than they
    # can give, either by their own cap or by how many periods they're
    # actually available for.
    load_by_teacher: dict[int, int] = {}
    # Options count separately here: each one is a real class a teacher has to
    # take, at the same moment as the block's other options.
    for req in [*requirements, *(option_reqs or [])]:
        candidates = candidate_ids_by_req.get(req.id, [])
        if len(candidates) == 1:
            load_by_teacher[candidates[0]] = load_by_teacher.get(candidates[0], 0) + req.periods_per_week
    for teacher_id, load in load_by_teacher.items():
        teacher = teachers_by_id.get(teacher_id)
        if not teacher:
            continue
        available = len(periods) - len(set(teacher.unavailable_period_ids or []))
        cap = teacher.max_periods_per_week
        effective_cap = min(cap, available) if cap is not None else available
        if load > effective_cap:
            if cap is not None and cap <= available:
                reason = f"capped at {cap} periods/week"
            else:
                reason = f"only available for {available} period(s)/week (given their marked-unavailable periods)"
            messages.append(
                f"{teacher.name} is the only qualified or preferred teacher for requirements "
                f"totaling {load} periods/week, but is {reason} — raise their cap, free up more "
                f"of their availability, or add another teacher qualified for the same subject(s)."
            )

    return messages


def _diagnose_constraint_conflicts(
    db: Session,
    school_id: int,
    requirements: list[SubjectRequirement],
    teachers: list[Teacher],
    teachers_by_id: dict[int, Teacher],
    periods: list[Period],
    periods_by_day: dict[int, list[Period]],
    # Teaching runs split at breaks - the diagnosis has to model adjacency
    # the same way the real solve does, or it reports conflicts that the
    # generator never actually hit.
    teaching_runs: list[list[Period]],
    first_period_ids: set[int],
    last_period_ids: set[int],
    period_ids_by_day: dict[int, set[int]],
    class_groups_by_id: dict[int, ClassGroup],
    subjects_by_id: dict[int, Subject],
    class_groups: list[ClassGroup],
) -> list[str]:
    """
    Follow-up to _diagnose_infeasibility, for the one class of cause that
    function can't see: two or more admin-authored Constraint rows
    (placement/day restrictions, consecutive-period caps, subject
    sequencing, subject spacing) that are each individually fine but can't
    all hold at once together — e.g. two different subjects both required
    into the same class group's first period, each fine alone, impossible
    together. docs/ARCHITECTURE.md names exactly this as the thing the
    cheap single-cause checks deliberately don't cover.

    Approach: rebuild a second, smaller CP-SAT model where every
    conflict-capable Constraint row is guarded by its own boolean
    "assumption" literal (CpModel.AddAssumptions) instead of being
    unconditionally true. Solving with every assumption asked-true is
    exactly equivalent to the real model's behavior when everything's
    satisfiable — so if this comes back infeasible, CP-SAT's
    SufficientAssumptionsForInfeasibility() returns a genuinely sufficient
    (not necessarily the single smallest possible, but always a real,
    checkable) subset of those literals that can't all hold together,
    which is mapped back to the actual Constraint rows for the message.

    If this second model turns out satisfiable, or the solve times out
    inconclusively, this returns an empty list rather than guessing — the
    original infeasibility must then be caused by something this pass
    doesn't model (kept deliberately narrower than the main solve; see the
    lab-batch exclusion below), and the caller falls back to its generic
    "couldn't automatically identify the cause" message, same as it
    already does when _diagnose_infeasibility finds nothing.

    Kept as an entirely separate model from the main solve in
    generate_school_timetable — not a modification of it — specifically so
    this only runs, and can only ever affect anything, on the failure path.
    The main solve's happy-path behavior and performance (already
    stress-tested to 200 sections) is completely unchanged by this
    function's existence.

    Deliberately excludes lab-batch requirements (Subject.lab_batch_count
    >= 2): a batch's "does a session happen" occupancy variable isn't a
    per-teacher assignment the way every other variable in this pass is, so
    reserving assistant time or reasoning about it the same way would need
    the same batch-specific modeling the main solve uses. If the only real
    conflict involves a batched subject, this pass simply won't find it and
    returns an empty list rather than fabricating a wrong answer.
    """
    conflict_types = (
        "no_subject_period", "require_subject_period",
        "no_subject_day", "require_subject_day",
        "max_consecutive_periods", "subject_sequence", "min_gap_between_subjects",
    )
    rule_constraints = (
        db.query(Constraint)
        .filter(
            Constraint.school_id == school_id,
            Constraint.type.in_(conflict_types),
            Constraint.is_hard.is_(True),
        )
        .all()
    )
    if not rule_constraints:
        return []  # nothing optional to blame; the cause is elsewhere

    def _applies_to(constraint_params: dict, req: SubjectRequirement) -> bool:
        if constraint_params.get("subject_id") != req.subject_id:
            return False
        class_group_ids = constraint_params.get("class_group_ids")
        return not class_group_ids or req.class_group_id in class_group_ids

    non_batched = [r for r in requirements if not _is_batched(r, subjects_by_id)]
    if not non_batched:
        return []

    model = cp_model.CpModel()
    x: dict[tuple[int, int, int], cp_model.IntVar] = {}
    requirement_vars: dict[int, list] = {r.id: [] for r in non_batched}
    class_group_period_vars: dict[tuple[int, int], list] = {}
    teacher_period_vars: dict[tuple[int, int], list] = {}
    teacher_total_vars: dict[int, list] = {t.id: [] for t in teachers}
    req_period_vars: dict[int, dict[int, list]] = {r.id: {} for r in non_batched}

    for req in non_batched:
        candidate_ids = _candidate_teacher_ids(req, teachers, teachers_by_id, class_groups_by_id)
        if not candidate_ids:
            # A missing-qualified-teacher cause — _diagnose_infeasibility
            # (or the main solve's own upfront check) already reports this
            # specifically; this pass has nothing useful to add.
            return []

        assistant_id = req.assistant_teacher_id
        assistant = teachers_by_id.get(assistant_id) if assistant_id else None
        assistant_unavailable = set(assistant.unavailable_period_ids or []) if assistant else set()

        for teacher_id in candidate_ids:
            teacher = teachers_by_id[teacher_id]
            unavailable = set(teacher.unavailable_period_ids or [])
            for period in periods:
                if period.id in unavailable:
                    continue
                if assistant and period.id in assistant_unavailable:
                    continue
                var = model.NewBoolVar(f"cx_r{req.id}_t{teacher_id}_p{period.id}")
                x[(req.id, teacher_id, period.id)] = var
                requirement_vars[req.id].append(var)
                class_group_period_vars.setdefault((req.class_group_id, period.id), []).append(var)
                teacher_period_vars.setdefault((teacher_id, period.id), []).append(var)
                teacher_total_vars[teacher_id].append(var)
                req_period_vars[req.id].setdefault(period.id, []).append(var)
                if assistant and assistant_id != teacher_id:
                    teacher_period_vars.setdefault((assistant_id, period.id), []).append(var)
                    teacher_total_vars[assistant_id].append(var)

    for req in non_batched:
        if requirement_vars[req.id]:
            model.Add(sum(requirement_vars[req.id]) == req.periods_per_week)
    for group_vars in class_group_period_vars.values():
        model.AddAtMostOne(group_vars)
    for group_vars in teacher_period_vars.values():
        model.AddAtMostOne(group_vars)
    for teacher in teachers:
        if teacher.max_periods_per_week is not None and teacher_total_vars[teacher.id]:
            model.Add(sum(teacher_total_vars[teacher.id]) <= teacher.max_periods_per_week)

    req_by_class_subject = {(r.class_group_id, r.subject_id): r for r in non_batched}
    sorted_periods_by_day = {day: sorted(dp, key=lambda p: p.order) for day, dp in periods_by_day.items()}

    assumptions: list[cp_model.IntVar] = []
    # Keyed by the assumption BoolVar's model-internal index (var.Index()),
    # not its position in the `assumptions` list — that's what
    # SufficientAssumptionsForInfeasibility() actually returns below, and
    # the two aren't the same number once other variables exist in the
    # model (verified directly against the ortools API before relying on
    # it here).
    assumption_constraints: dict[int, Constraint] = {}

    for c in rule_constraints:
        p = c.parameters or {}
        contributed = False

        if c.type in ("no_subject_period", "require_subject_period", "no_subject_day", "require_subject_day"):
            is_ban = c.type in ("no_subject_period", "no_subject_day")
            assume = model.NewBoolVar(f"assume_c{c.id}")
            for req in non_batched:
                if not _applies_to(p, req):
                    continue
                if c.type in ("no_subject_period", "require_subject_period"):
                    position = p.get("position")
                    if position not in ("first", "last"):
                        continue
                    matched = first_period_ids if position == "first" else last_period_ids
                else:
                    day_of_week = p.get("day_of_week")
                    if not isinstance(day_of_week, int):
                        continue
                    matched = period_ids_by_day.get(day_of_week, set())
                per_period = req_period_vars.get(req.id, {})
                zero_period_ids = matched if is_ban else (set(per_period.keys()) - matched)
                for period_id in zero_period_ids:
                    for var in per_period.get(period_id, []):
                        model.Add(var == 0).OnlyEnforceIf(assume)
                        contributed = True
        elif c.type == "max_consecutive_periods":
            assume = model.NewBoolVar(f"assume_c{c.id}")
            max_consecutive = p.get("max_consecutive")
            if isinstance(max_consecutive, int) and max_consecutive >= 1:
                teacher_id = p.get("teacher_id")
                if teacher_id is not None:
                    for day_periods in teaching_runs:
                        if len(day_periods) <= max_consecutive:
                            continue
                        for start in range(len(day_periods) - max_consecutive):
                            window = day_periods[start:start + max_consecutive + 1]
                            window_vars = [v for wp in window for v in teacher_period_vars.get((teacher_id, wp.id), [])]
                            if window_vars:
                                model.Add(sum(window_vars) <= max_consecutive).OnlyEnforceIf(assume)
                                contributed = True
                else:
                    for req in non_batched:
                        if not _applies_to(p, req):
                            continue
                        per_period_vars = req_period_vars.get(req.id, {})
                        for day_periods in teaching_runs:
                            if len(day_periods) <= max_consecutive:
                                continue
                            for start in range(len(day_periods) - max_consecutive):
                                window = day_periods[start:start + max_consecutive + 1]
                                window_vars = [v for wp in window for v in per_period_vars.get(wp.id, [])]
                                if window_vars:
                                    model.Add(sum(window_vars) <= max_consecutive).OnlyEnforceIf(assume)
                                    contributed = True
        elif c.type == "subject_sequence":
            assume = model.NewBoolVar(f"assume_c{c.id}")
            first_subject_id = p.get("first_subject_id")
            second_subject_id = p.get("second_subject_id")
            if first_subject_id and second_subject_id:
                class_group_ids = p.get("class_group_ids") or [cg.id for cg in class_groups]
                for cg_id in class_group_ids:
                    req1 = req_by_class_subject.get((cg_id, first_subject_id))
                    req2 = req_by_class_subject.get((cg_id, second_subject_id))
                    if not req1 or not req2:
                        continue
                    for day_periods in teaching_runs:
                        for i in range(len(day_periods) - 1):
                            period, next_period = day_periods[i], day_periods[i + 1]
                            first_vars = req_period_vars.get(req1.id, {}).get(period.id, [])
                            second_vars = req_period_vars.get(req2.id, {}).get(next_period.id, [])
                            if first_vars and second_vars:
                                model.Add(sum(first_vars) + sum(second_vars) <= 1).OnlyEnforceIf(assume)
                                contributed = True
        elif c.type == "min_gap_between_subjects":
            assume = model.NewBoolVar(f"assume_c{c.id}")
            first_subject_id = p.get("first_subject_id")
            second_subject_id = p.get("second_subject_id")
            min_gap = p.get("min_gap")
            if first_subject_id and second_subject_id and isinstance(min_gap, int) and min_gap >= 1:
                class_group_ids = p.get("class_group_ids") or [cg.id for cg in class_groups]
                for cg_id in class_group_ids:
                    req1 = req_by_class_subject.get((cg_id, first_subject_id))
                    req2 = req_by_class_subject.get((cg_id, second_subject_id))
                    if not req1 or not req2:
                        continue
                    for day_periods in sorted_periods_by_day.values():
                        for p1 in day_periods:
                            p1_vars = req_period_vars.get(req1.id, {}).get(p1.id, [])
                            if not p1_vars:
                                continue
                            for p2 in day_periods:
                                # Same off-by-one fix as the main model - these
                                # two must agree, or the diagnosis describes a
                                # constraint the solve did not actually apply.
                                if abs(p1.order - p2.order) > min_gap:
                                    continue
                                p2_vars = req_period_vars.get(req2.id, {}).get(p2.id, [])
                                if p2_vars:
                                    model.Add(sum(p1_vars) + sum(p2_vars) <= 1).OnlyEnforceIf(assume)
                                    contributed = True
        else:
            continue

        if contributed:
            assumptions.append(assume)
            assumption_constraints[assume.Index()] = c

    if len(assumptions) < 2:
        # Can't have a *multi*-constraint conflict with fewer than two
        # candidates — either nothing here applies to this school's actual
        # requirements, or there's only one, which would already have to be
        # a structural issue the cheap checks above should have caught.
        return []

    model.AddAssumptions(assumptions)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = _search_workers()
    # A diagnostic pass on an already-failed generation — doesn't need
    # anywhere near the main solve's time budget.
    solver.parameters.max_time_in_seconds = min(15, settings.solver_time_limit_seconds)
    status = solver.Solve(model)

    if status != cp_model.INFEASIBLE:
        # Either genuinely satisfiable once the admin rules are only
        # *tried* rather than unconditionally forced (meaning they aren't
        # actually the cause), or the solve timed out inconclusively —
        # either way, this pass can't honestly name a cause, so it stays
        # silent rather than guessing.
        return []

    conflicting_indices = solver.SufficientAssumptionsForInfeasibility()
    conflicting = [assumption_constraints[i] for i in conflicting_indices if i in assumption_constraints]
    if len(conflicting) < 2:
        # A single constraint "conflicting" with nothing else would really
        # be a structural issue the cheap checks above should have already
        # caught — not the multi-constraint interaction this pass exists
        # for. Stay silent rather than blaming one rule for something it
        # isn't solely responsible for.
        return []

    descriptions = ", ".join(f"\"{c.description}\"" for c in conflicting)
    return [
        f"These {len(conflicting)} constraints can't all be satisfied together: {descriptions} — "
        f"loosen or remove at least one of them and regenerate."
    ]


def _assign_rooms(
    db: Session,
    school_id: int,
    assignments: list[dict],
    locked_rooms: dict[tuple[int, int, int, int], int | None] | None = None,
) -> None:
    """
    Best-effort second pass: assigns a Room to as many scheduled entries as
    possible, without touching the (subject, teacher, period) choices the
    main solve already made. Mutates each dict in `assignments` in place,
    adding a "room_id" key (int or None).

    Kept as its own separate, much smaller CP-SAT model rather than folded
    into the main model above, for two reasons:
      1. Once the period/teacher for every entry is fixed, room-matching
         reduces to a much simpler problem (which room, if any, for an
         already-fixed class/period) — solving it separately keeps rooms
         from making the expensive part of the search (the main model)
         any slower as more rooms are added to a school.
      2. It's genuinely optional/best-effort: a school might have fewer
         rooms than simultaneous classes, and that should mean some
         entries just don't get a room, not that generation fails
         entirely. So this maximizes the number of entries assigned a
         room rather than requiring all of them to get one.
    """
    locked_rooms = locked_rooms or {}
    rooms = db.query(Room).filter(Room.school_id == school_id).all()

    # Locked entries keep whatever room they already had (or stay
    # room-less if they didn't have one) — they're not up for
    # re-matching. Their (period, room) pair is still reserved so an
    # unlocked entry can't get matched into it below.
    locked_period_rooms: set[tuple[int, int]] = set()
    for a in assignments:
        key = (a["class_group_id"], a["subject_id"], a["teacher_id"], a["period_id"])
        if key in locked_rooms:
            a["room_id"] = locked_rooms[key]
            if locked_rooms[key] is not None:
                locked_period_rooms.add((a["period_id"], locked_rooms[key]))
        else:
            a["room_id"] = None
    if not rooms:
        return  # nothing to assign against; every unlocked entry stays room_id=None

    subjects_by_id = {s.id: s for s in db.query(Subject).filter(Subject.school_id == school_id).all()}
    class_groups_by_id = {c.id: c for c in db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()}

    # Rooms in one period never affect another, so this is one small
    # matching per period - entries on one side, rooms they may use on the
    # other - and a maximum matching is exactly "as many entries as possible
    # get a room". Solved directly (augmenting paths) rather than as one
    # school-wide CP-SAT model, which took its full 15-second limit on a
    # school with labs and gave nothing a matching doesn't.
    eligible_by_period: dict[int, list[tuple[int, list[int]]]] = {}
    for idx, a in enumerate(assignments):
        key = (a["class_group_id"], a["subject_id"], a["teacher_id"], a["period_id"])
        if key in locked_rooms:
            continue  # already fixed above; not part of this pass

        subject = subjects_by_id.get(a["subject_id"])
        class_group = class_groups_by_id.get(a["class_group_id"])
        required_type = subject.required_room_type if subject else None
        student_count = class_group.student_count if class_group else None

        eligible = [
            r.id for r in rooms
            if (not required_type or r.room_type == required_type)
            and (not student_count or not r.capacity or r.capacity >= student_count)
            and (a["period_id"], r.id) not in locked_period_rooms
        ]
        if eligible:
            eligible_by_period.setdefault(a["period_id"], []).append((idx, eligible))

    for entries in eligible_by_period.values():
        # Most constrained first: fewer augmenting detours, same optimum.
        entries.sort(key=lambda e: len(e[1]))
        room_holder: dict[int, int] = {}  # room_id -> assignment index

        def place(idx: int, options: list[int], seen: set[int]) -> bool:
            for room_id in options:
                if room_id in seen:
                    continue
                seen.add(room_id)
                holder = room_holder.get(room_id)
                if holder is None or place(holder, options_of[holder], seen):
                    room_holder[room_id] = idx
                    return True
            return False

        options_of = {idx: options for idx, options in entries}
        for idx, options in entries:
            place(idx, options, set())
        for room_id, idx in room_holder.items():
            assignments[idx]["room_id"] = room_id


def solve_example() -> SolveResult:
    """
    A tiny worked example used to prove the OR-Tools integration works
    end-to-end: 1 class group, 2 subjects, 2 teachers, 2 periods.
    Each subject needs exactly 1 period; a teacher can't teach two things
    at once.
    """
    model = cp_model.CpModel()

    class_groups = ["Grade8-A"]
    subjects = ["Math", "English"]
    teachers = {"Math": "Mr. Rao", "English": "Ms. Iyer"}
    periods = ["Mon-P1", "Mon-P2"]

    # One bool var per (class_group, subject, period): is this subject
    # taught to this class group in this period?
    x = {}
    for c in class_groups:
        for s in subjects:
            for p in periods:
                x[(c, s, p)] = model.NewBoolVar(f"x_{c}_{s}_{p}")

    # Each subject must be scheduled in exactly one period.
    for c in class_groups:
        for s in subjects:
            model.AddExactlyOne(x[(c, s, p)] for p in periods)

    # A class group can only have one subject per period.
    for c in class_groups:
        for p in periods:
            model.AddAtMostOne(x[(c, s, p)] for s in subjects)

    # A teacher can't teach two subjects at the same period (trivially true
    # here since each teacher only teaches one subject, but the pattern
    # generalizes once teachers can teach multiple subjects/classes).
    for p in periods:
        for teacher in set(teachers.values()):
            subjects_for_teacher = [s for s, t in teachers.items() if t == teacher]
            model.AddAtMostOne(
                x[(c, s, p)] for c in class_groups for s in subjects_for_teacher
            )

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    status_name = {
        cp_model.OPTIMAL: "optimal",
        cp_model.FEASIBLE: "feasible",
        cp_model.INFEASIBLE: "infeasible",
    }.get(status, "unknown")

    assignments = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for c in class_groups:
            for s in subjects:
                for p in periods:
                    if solver.Value(x[(c, s, p)]):
                        assignments.append(
                            {
                                "class_group": c,
                                "subject": s,
                                "teacher": teachers[s],
                                "period": p,
                            }
                        )

    return SolveResult(status=status_name, assignments=assignments)


# Rule types the solver reads from Constraint rows. Workload and availability
# rules are applied by editing the Teacher, so switching their row off would
# not switch the rule off - they are left out of the search.
_SEARCHABLE_TYPES = (
    "ir", "no_subject_period", "require_subject_period", "no_subject_day", "require_subject_day",
    "max_consecutive_periods", "max_subject_periods_per_day", "min_gap_between_subjects", "subject_sequence",
)


def find_blocking_rules(db: Session, school_id: int, budget_seconds: float = 180, per_try_seconds: float = 15) -> list[str]:
    """Which of the school's rules stop a timetable from existing.

    The step the failure message used to ask the admin to do by hand - switch
    rules off one at a time and regenerate - done here instead, in the
    background job, so the message can name the rule.

      1. Every rule off. Still no timetable: the rules aren't the cause, and
         the message says so (it is then teachers, periods or the plan).
      2. Each rule off on its own. Any rule whose removal is enough is named.
      3. If no single rule is enough, a deletion filter finds a smallest set
         that can't all hold together: drop each rule in turn, keep it dropped
         if the school is still impossible without it. What is left are rules
         that, between them, are the conflict.

    Only a solve that FINDS a timetable counts as "possible". A try that runs
    out of time counts as impossible, which can make step 3 keep a rule it
    didn't need, but never names a rule as the fix when it isn't. Preferences
    are left out: a soft rule can't make a school impossible. Returns [] if
    the search runs out of time before it can say anything.
    """
    rows = [
        c for c in db.query(Constraint)
        .filter(Constraint.school_id == school_id, Constraint.type.in_(_SEARCHABLE_TYPES))
        .order_by(Constraint.id)
        .all()
        if c.is_hard is not False
    ]
    started = time.monotonic()
    all_ids = {c.id for c in rows}
    # Preferences stay off throughout: they can't make a school impossible,
    # and with them on every try optimises instead of just finding a
    # timetable - which ran a try that should take seconds past its limit.
    soft_ids = {
        c.id for c in db.query(Constraint).filter(Constraint.school_id == school_id).all()
        if c.is_hard is False
    }

    def attempt(skip: set[int], relax: frozenset = frozenset()):
        left = budget_seconds - (time.monotonic() - started)
        if left < 3:
            return None
        t1 = _SKIP_RULES.set(frozenset(skip | soft_ids))
        t2 = _TIME_LIMIT.set(min(per_try_seconds, left))
        t3 = _RELAX.set(relax)
        try:
            return generate_school_timetable(db, school_id)
        finally:
            _SKIP_RULES.reset(t1)
            _TIME_LIMIT.reset(t2)
            _RELAX.reset(t3)

    def possible(skip: set[int]) -> bool | None:
        t = time.monotonic()
        result = attempt(skip)
        ok = None if result is None else result.status in ("optimal", "feasible")
        logger.info(
            "find_blocking_rules school=%s off=%d/%d -> %s in %.1fs",
            school_id, len(skip & all_ids), len(all_ids), "out of time" if ok is None else ok, time.monotonic() - t,
        )
        return ok

    def quote(c: Constraint) -> str:
        return f"“{(c.description or c.source_text or 'a rule').strip().rstrip('.')}”"

    everything_off = possible(all_ids) if rows else False
    if everything_off is None:
        return []
    if not everything_off:
        return _diagnose_setup(db, school_id, attempt, all_ids, bool(rows))

    singles = []
    checked = 0
    for c in rows:
        ok = possible({c.id})
        if ok is None:
            break
        checked += 1
        if ok:
            singles.append(c)
    if singles:
        if len(singles) == 1:
            return [f"The rule {quote(singles[0])} makes the timetable impossible. Remove or loosen it and generate again."]
        return [
            f"Removing any one of these rules makes a timetable possible: {', '.join(quote(c) for c in singles)}. "
            "They can't all be met together - loosen one of them."
        ]

    if checked < len(rows):
        # Ran out of time partway through the single-rule checks.
        return [
            "The timetable works with all your rules switched off, so one or more of them is the cause. "
            f"There wasn't time to test every rule (checked {checked} of {len(rows)}), and none of those "
            "was the cause on its own. Remove a few of the rules below, generate, and add them back one at a time:",
            *[quote(c) for c in rows[checked:]],
        ]

    needed = list(rows)
    finished = True
    for c in rows:
        trial = [r for r in needed if r.id != c.id]
        ok = possible(all_ids - {r.id for r in trial})
        if ok is None:
            finished = False
            break
        if not ok:
            needed = trial  # still impossible without it: not part of the conflict
    if finished and needed:
        return [
            f"These rules can't all be met at the same time: {', '.join(quote(c) for c in needed)}. "
            "Loosen any one of them and generate again."
        ]
    # Out of time while narrowing down: say what is known so far rather than
    # nothing - `needed` still contains the conflict, it just may not be the
    # smallest set.
    return [
        "The timetable works with all your rules switched off, and no single rule is the cause - it's a "
        f"combination. It is among these {len(needed)} rules; loosening one of them should fix it:",
        *[quote(c) for c in needed],
    ]


def _diagnose_setup(db, school_id, attempt, all_ids, had_rules) -> list[str]:
    """No timetable even without any rules: find which part of the setup is
    the problem by relaxing one part at a time and seeing what it took."""
    lead = (
        "This isn't caused by your rules: even with all of them switched off there is still no timetable. "
        if had_rules else "This isn't caused by any rule - the school's setup can't be timetabled as it is. "
    )
    teachers = {t.id: t for t in db.query(Teacher).filter(Teacher.school_id == school_id).all()}
    subjects = {x.id: x.name for x in db.query(Subject).filter(Subject.school_id == school_id).all()}
    groups = {c.id: c for c in db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()}

    def label(cg_id):
        cg = groups.get(cg_id)
        return _class_group_label(cg) if cg else "a section"

    split = attempt(all_ids, frozenset({"one_teacher"}))
    if split is not None and split.status in ("optimal", "feasible"):
        by_strand: dict = {}
        for a in split.assignments:
            key = (a["class_group_id"], a["subject_id"], a.get("batch"))
            by_strand.setdefault(key, {}).setdefault(a["teacher_id"], 0)
            by_strand[key][a["teacher_id"]] += 1
        lines = []
        for (cg_id, sub_id, _batch), teachers_used in sorted(by_strand.items(), key=lambda kv: (label(kv[0][0]), subjects.get(kv[0][1], ""))):
            if len(teachers_used) < 2:
                continue
            who = " and ".join(f"{teachers[t].name} ({n})" for t, n in teachers_used.items() if t in teachers)
            lines.append(f"{subjects.get(sub_id, 'A subject')} in {label(cg_id)} - split between {who}")
        if lines:
            shown = lines[:8]
            more = f" (and {len(lines) - 8} more)" if len(lines) > 8 else ""
            return [
                lead + "It only works if some sections share a subject between two teachers, and each "
                "section has to keep one teacher per subject. Give the teachers below more room "
                "(a higher max periods/week, or fewer other sections), or qualify another teacher, "
                "so each of these can have a single teacher" + more + ":",
                *shown,
            ]

    uncapped = attempt(all_ids, frozenset({"max_periods"}))
    if uncapped is not None and uncapped.status in ("optimal", "feasible"):
        load: dict = {}
        for a in uncapped.assignments:
            load[a["teacher_id"]] = load.get(a["teacher_id"], 0) + 1
        over = [
            f"{t.name}: needs {load[t.id]}, limit {t.max_periods_per_week}"
            for t in sorted(teachers.values(), key=lambda t: t.name)
            if t.max_periods_per_week and load.get(t.id, 0) > t.max_periods_per_week
        ]
        return [
            lead + "It works only if some teachers go over their max periods/week. "
            "Raise these limits, or move some of their sections to another qualified teacher:",
            *(over or ["(the limits are tight across several teachers rather than one)"]),
        ]

    return [
        lead + "Even with sections allowed to share a teacher and no weekly limits, it can't be done - so "
        "it's down to when teachers are available, or the plan itself. Check each teacher's unavailable "
        "periods, elective blocks (every option needs its own teacher at the same time), lab batches "
        "(one teacher per batch at once), and that no section has more periods/week than the week has."
    ]

