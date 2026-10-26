"""
Core database models.

Kept generic (not tied to one curriculum/board) per docs/ARCHITECTURE.md:
schools define their own periods, subjects, and constraints rather than the
schema assuming a fixed structure.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, JSON, UniqueConstraint, false, func
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # "school" or "college" — chosen once at creation (see routers/schools.py
    # and frontend App.jsx's create-school modal). Purely a UI hint for
    # smart defaults (terminology, which optional fields to show) — nothing
    # in the solver or access-control logic branches on this, so an
    # existing row with this left null is treated as "school" everywhere
    # that reads it, not an error state.
    institution_type = Column(String, nullable=True)
    # Explicit display order for the sidebar's grade groups, as a list of
    # grade label strings (e.g. ["Nursery", "LKG", "UKG", "Grade 1", ...]).
    # Empty by default — the sidebar falls back to a natural (numeric-
    # aware) sort until an admin explicitly reorders grades (see
    # PUT /api/schools/{id}/grade-order), since most schools' grade names
    # sort correctly on their own and shouldn't require manual setup.
    # Grades not present in this list (e.g. a brand-new one added after
    # the last reorder) are shown after every listed grade.
    grade_order = Column(JSON, default=list)
    # Grades whose school day is shorter than everyone else's - Grades 1 and 2
    # going home after period 6, say. A list of
    #   {"grades": ["Grade 1", "Grade 2"], "periods_per_day": 6,
    #    "by_day": {"5": 3}}
    # where by_day overrides the count for a weekday (0 = Monday; 0 periods =
    # no school that day). Lesson periods after a grade's last one are kept
    # empty for its sections, exactly like a zero period. Null = none.
    grade_day_limits = Column(JSON, nullable=True)
    # The timetable version the school works from: what the Timetable tab
    # shows and edits, what exports and substitutions read, and where the next
    # generation takes its locked slots from. Set to each new successful
    # version, and to any older one the admin opens. Not a foreign key, so
    # deleting a version never cascades into the school row; a value pointing
    # at a version that no longer exists is treated as unset.
    current_timetable_id = Column(Integer, nullable=True)
    # Descriptive details shown and edited in Settings > School profile:
    # board, affiliation/UDISE code, principal, contact details, address,
    # academic year start, etc. One JSON column rather than a dozen
    # columns because none of it is queried, filtered or used by the
    # solver - it's display data for the profile page and, later, export
    # headers. The allowed keys and their limits live in
    # app/schemas/school.py (SchoolProfile), which is what actually
    # validates what goes in here. Null for schools created before this.
    profile = Column(JSON, nullable=True)
    # Paid plan. Null plan = Free. Set only by app/routers/payments.py, and
    # only after Cashfree has confirmed the payment server-side; a renewal
    # extends plan_valid_until from whichever is later, now or the current
    # expiry, so paying early never loses days.
    plan = Column(String(20), nullable=True)
    plan_valid_until = Column(DateTime, nullable=True)
    # Limits from a custom offer (PlanOffer) the school has paid for, e.g.
    # {"max_sections": 150, "max_members": 15}; a missing or null key means
    # unlimited. Applied on top of the Business plan by app/services/plans.py.
    custom_limits = Column(JSON, nullable=True)
    custom_plan_name = Column(String(80), nullable=True)
    # AI actions used this calendar month ("2026-10"), for plans with a
    # monthly allowance (app/services/plans.py: use_ai). Resets lazily when
    # the month changes rather than with a scheduled job.
    # End of the 14 free days a school gets on creation (app/services/plans.py:
    # FREE_DAYS). After it, an unpaid school is locked until it upgrades.
    free_trial_ends_at = Column(DateTime, nullable=True)
    ai_usage_month = Column(String(7), nullable=True)
    ai_usage_count = Column(Integer, nullable=True)

    owner = relationship("User", back_populates="schools")
    teachers = relationship("Teacher", back_populates="school", cascade="all, delete-orphan")
    class_groups = relationship("ClassGroup", back_populates="school", cascade="all, delete-orphan")
    subjects = relationship("Subject", back_populates="school", cascade="all, delete-orphan")
    rooms = relationship("Room", back_populates="school", cascade="all, delete-orphan")
    periods = relationship("Period", back_populates="school", cascade="all, delete-orphan")
    constraints = relationship("Constraint", back_populates="school", cascade="all, delete-orphan")


class Period(Base):
    """A schedulable time slot, e.g. 'Monday, slot 3 (9:00-9:45)'.

    Schools define their own list of periods instead of the app assuming a
    fixed daily structure, so different school types (half-day, shift-based,
    etc.) are supported without schema changes.
    """
    __tablename__ = "periods"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0 = Monday ... 6 = Sunday
    order = Column(Integer, nullable=False)  # position within the day
    label = Column(String, nullable=True)  # e.g. "Period 3", "9:00-9:45", "Lunch"
    # What the slot is for. Only "lesson" slots are timetabled and numbered;
    # the others sit in the day's order without a number, so "period 1" is
    # always the first lesson whatever comes before it:
    #
    #   lesson         an ordinary period
    #   break          lunch, recess - nothing happens
    #   class_teacher  each section with its own class teacher (attendance);
    #                  shown, never solved, not counted towards workload
    #   zero           a free slot for activities, the same for the whole
    #                  school. A zero period that differs by grade or by day is
    #                  not a kind of slot but a ZeroPeriod reservation on a
    #                  lesson slot - see below.
    #
    # Non-lesson slots are kept as rows rather than gaps in `order` so a
    # teacher's back-to-back run is correctly interrupted by them (see
    # app/services/solver.py, which splits each day into runs at them).
    kind = Column(String, nullable=False, default="lesson", server_default="lesson")

    school = relationship("School", back_populates="periods")
    zero_reservations = relationship(
        "ZeroPeriod", back_populates="period", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (UniqueConstraint("school_id", "day_of_week", "order"),)

    KINDS = ("lesson", "break", "class_teacher", "zero")

    @property
    def is_break(self) -> bool:
        """Whether nothing is ever timetabled here - any kind but a lesson.

        Kept under its old name because that is the question every caller asks
        (the solver, the exports, the edit checks); before kinds existed a
        break was the only slot without lessons.
        """
        return self.kind not in (None, "lesson")

    @is_break.setter
    def is_break(self, value: bool) -> None:
        # Lets older callers (and tests) keep saying is_break=True. Turning it
        # off only undoes a break - it never turns a class teacher period into
        # a lesson behind someone's back.
        if value:
            if self.kind in (None, "lesson"):
                self.kind = "break"
        elif self.kind == "break":
            self.kind = "lesson"


class ZeroPeriod(Base):
    """A lesson slot kept free for one grade (or, grade=None, everyone).

    The form a zero period takes when it differs by grade or by day: the slot
    is an ordinary numbered period that other grades are taught in, and this
    row keeps lessons for the named grade out of it. A school-wide zero period
    at the same point every day is a Period of kind "zero" instead.
    """
    __tablename__ = "zero_periods"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    period_id = Column(Integer, ForeignKey("periods.id", ondelete="CASCADE"), nullable=False, index=True)
    # ClassGroup.grade label; None = every section in the school.
    grade = Column(String, nullable=True)

    period = relationship("Period", back_populates="zero_reservations")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    # If set, the solver will only assign this subject to a Room whose
    # room_type matches exactly (e.g. "lab" for Chemistry). Null means any
    # room is fine — most subjects don't need a specific room type.
    required_room_type = Column(String, nullable=True)
    # Optional, informational only — colleges track credits per course;
    # schools generally don't set this at all. Not read by the solver.
    credits = Column(Integer, nullable=True)
    # If set to 2+, every period the solver schedules for this subject is
    # split into this many simultaneous batches instead of one class
    # session — e.g. a 60-student "Programming Lab" section splitting into
    # 3 batches of ~20 in 3 different lab rooms, at the same time, each
    # needing its own qualified teacher. Null/1 means no split (the
    # default, and what every subject used before this field existed).
    # See app/services/solver.py's batch-splitting block for how this is
    # enforced — each batch is its own teacher+room assignment tied to the
    # same day/period as its sibling batches.
    lab_batch_count = Column(Integer, nullable=True)

    school = relationship("School", back_populates="subjects")


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    capacity = Column(Integer, nullable=True)
    room_type = Column(String, nullable=True)  # e.g. "lab", "regular", "auditorium"

    school = relationship("School", back_populates="rooms")


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    # subject_ids this teacher is qualified to teach
    qualified_subject_ids = Column(JSON, default=list)
    # Which grades (ClassGroup.grade label, e.g. "Grade 9") this teacher
    # teaches. Empty list = no restriction (teaches every grade) — this is
    # the default and matches every teacher's behavior before this field
    # existed, so a school that never touches this setting sees no change.
    # Only meaningful in combination with qualified_subject_ids: the
    # solver requires *both* to match before assigning a teacher to a
    # class group's subject requirement (see app/services/solver.py).
    qualified_grades = Column(JSON, default=list)
    # period_ids this teacher is NOT available (hard constraint shortcut)
    unavailable_period_ids = Column(JSON, default=list)
    max_periods_per_week = Column(Integer, nullable=True)
    # Whether this teacher can be picked as an *assistant* teacher on a
    # section's plan (see SubjectRequirement.assistant_teacher_id below) —
    # a separate flag from qualified_subject_ids, since being someone's
    # assistant for a class isn't the same as being qualified to teach
    # that subject solo. Defaults false so no existing teacher becomes
    # assistant-eligible just because this column was added.
    is_assistant_eligible = Column(Boolean, nullable=False, default=False, server_default="false")

    school = relationship("School", back_populates="teachers")


class ClassGroup(Base):
    """A group of students that moves through the timetable together
    (a 'section', e.g. Section A of Grade 8).

    `grade` + `name` together form the Grade > Section hierarchy shown in
    the UI (e.g. grade="Grade 8", name="A"). `grade` is a free-text label
    rather than its own table for the same reason periods/subjects are
    generic — schools name grades differently (Grade 8, Class VIII, Year 9).
    """
    __tablename__ = "class_groups"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    grade = Column(String, nullable=True)
    name = Column(String, nullable=False)
    student_count = Column(Integer, nullable=True)
    # Takes the section in the class teacher period (attendance and the like).
    # Cleared, not cascaded, when the teacher is deleted.
    class_teacher_id = Column(
        Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # A frozen section keeps its timetable exactly as it is through every later
    # generation: its lessons are copied forward as fixed facts and the solver
    # schedules everyone else around them. See generate_school_timetable.
    frozen = Column(Boolean, nullable=False, default=False, server_default=false())
    frozen_at = Column(DateTime, nullable=True)
    # What the section's plan and timetable looked like when it was frozen, so
    # a later change - a subject's periods, a block, a lesson lost to a
    # structure change - can be pointed out instead of silently ignored.
    frozen_signature = Column(String, nullable=True)
    frozen_lessons = Column(Integer, nullable=True)
    # The version the section was frozen in. Its lessons are copied from this
    # version into every later generation, however many come after - so
    # approving Grades 1-5 in Version 3 keeps Version 3's Grades 1-5.
    frozen_from_timetable_id = Column(Integer, nullable=True)

    school = relationship("School", back_populates="class_groups")
    requirements = relationship(
        "SubjectRequirement", back_populates="class_group", cascade="all, delete-orphan"
    )
    elective_blocks = relationship(
        "ElectiveBlock", back_populates="class_group", cascade="all, delete-orphan"
    )


class SubjectRequirement(Base):
    """How many periods per week a given class group needs of a given subject.

    Unique on (class_group_id, subject_id): a class group should only have
    one requirement per subject. This is enforced at the DB level as a
    backstop — the API layer also upserts on this pair (see
    app/routers/class_groups.py) rather than relying on the DB constraint
    alone, since a raw IntegrityError isn't a friendly API error.
    """
    __tablename__ = "subject_requirements"

    id = Column(Integer, primary_key=True)
    class_group_id = Column(Integer, ForeignKey("class_groups.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    periods_per_week = Column(Integer, nullable=False)
    preferred_teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    # A shortlist the solver picks ONE teacher from for this section's
    # subject, when the admin wants "Priya or Joseph, not anyone qualified".
    # Only used with two or more teachers and no preferred_teacher_id: one
    # teacher is a fixed choice and stays in preferred_teacher_id, so
    # everything that reads that field keeps working. Null = any qualified.
    allowed_teacher_ids = Column(JSON, nullable=True)
    # Optional second teacher for this section's subject — picked from
    # teachers flagged Teacher.is_assistant_eligible, independent of
    # qualified_subject_ids (an assistant doesn't need to be independently
    # qualified to teach the subject solo). Purely informational: the
    # solver doesn't currently schedule around this, it's just recorded
    # and shown alongside the main teacher.
    assistant_teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)

    __table_args__ = (UniqueConstraint("class_group_id", "subject_id"),)

    class_group = relationship("ClassGroup", back_populates="requirements")


class ElectiveBlock(Base):
    """A set of subjects one section studies at the same time, each student
    taking exactly one of them.

    The usual shape for Grades 11 and 12: a section has common subjects that
    everyone takes (English, as normal SubjectRequirements) and then blocks
    like "Physics / Accounts / History", where the class splits up for those
    periods and each student goes to the one they chose. Which subjects share
    a block is decided by the school before timetabling starts - it is what
    determines which subject combinations a student can take at all.

    Scheduled as one slot with several simultaneous lessons: when the block
    meets, the section is occupied once and every option needs its own
    teacher at that moment. Every option therefore gets the block's
    periods_per_week - they run together, so they cannot differ.

    Scoped to one section. Blocks that span a whole grade (students leaving
    their section to join a subject) are deliberately not modelled: they
    would need a timetable entry owned by several sections at once.
    """
    __tablename__ = "elective_blocks"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    class_group_id = Column(Integer, ForeignKey("class_groups.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    periods_per_week = Column(Integer, nullable=False)

    class_group = relationship("ClassGroup", back_populates="elective_blocks")
    options = relationship(
        "ElectiveOption", back_populates="block", cascade="all, delete-orphan",
        order_by="ElectiveOption.id",
    )


class ElectiveOption(Base):
    """One subject a student can choose within an ElectiveBlock.

    Unique per (block, subject). A subject also may not appear in two blocks
    of the same section, or as both a block option and a normal requirement
    for it - the API refuses both, because either would schedule the subject
    twice and silently inflate the section's real periods per week.
    """
    __tablename__ = "elective_options"

    id = Column(Integer, primary_key=True)
    block_id = Column(Integer, ForeignKey("elective_blocks.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    # Same meaning as SubjectRequirement.preferred_teacher_id: pins this
    # option to one teacher instead of letting the solver pick among the
    # qualified ones.
    preferred_teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)

    __table_args__ = (UniqueConstraint("block_id", "subject_id"),)

    block = relationship("ElectiveBlock", back_populates="options")


class Constraint(Base):
    """A generic scheduling rule.

    Stored as (type, parameters) rather than one column per rule so new
    constraint types can ship without a schema migration each time. `type`
    is a string key the solver service knows how to interpret (e.g.
    'teacher_unavailable', 'no_subject_last_period', 'max_consecutive_periods').
    `is_hard` = must be satisfied; soft constraints are scored/optimized instead.
    """
    __tablename__ = "constraints"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    type = Column(String, nullable=False)
    parameters = Column(JSON, default=dict)
    is_hard = Column(Boolean, default=True)
    weight = Column(Integer, default=1)  # relevant for soft constraints only
    description = Column(Text, nullable=True)  # human-readable, shown in the UI

    # What the admin actually typed, before any parsing. `description` is the
    # parser's *summary*, which is the wrong end of the problem when the
    # question is "which phrasings do we fail to understand" - that needs the
    # input, not our interpretation of it.
    source_text = Column(Text, nullable=True)
    # "llm" or "regex" (or null for rows predating this). Without it a
    # scheduling_rule row is uninterpretable: one produced by the regex
    # fallback says nothing about what Claude can or can't handle.
    parsed_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())

    school = relationship("School", back_populates="constraints")


class RuleReadEvent(Base):
    """One moment worth learning from in turning a sentence into a rule.

    Written alongside the normal flow and never read by it: what the admin
    typed, what the parser made of it, and what happened next (confirmed,
    cancelled, reworded, deleted soon after, handed back unread). The Timetablz
    admin page lists these so misreadings can be found and fixed - see
    app/services/rule_events.py. Logging failing never affects the rule itself.
    """
    __tablename__ = "rule_read_events"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # interpreted | unclear | invalid | confirmed | cancelled | reworded |
    # batch_unread | not_applied | quick_delete
    kind = Column(String(32), nullable=False, index=True)
    text = Column(Text, nullable=False)
    # Whatever explains it: the parser's sentence or rule, its reason and
    # question, the description that was deleted.
    detail = Column(JSON, nullable=True)
    constraint_id = Column(Integer, nullable=True)
    # Set from the admin page once looked at, with the bucket it was put in:
    # misread | checker | unsupported | ambiguous | fine.
    triage = Column(String(16), nullable=True)


class Timetable(Base):
    """A generated schedule (one solver run's output).

    Generation runs as a background job (see app/routers/timetables.py)
    rather than blocking the HTTP request that kicked it off — a solve can
    legitimately take up to a minute for a large school, which is too long
    to hold a request open. `status` tracks the job lifecycle:
    "generating" -> "draft" (succeeded) or "failed". `solver_status` and
    `error_message` record what CP-SAT actually reported, for display.
    """
    __tablename__ = "timetables"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    status = Column(String, default="generating")  # generating, draft, failed, published, archived
    solver_status = Column(String, nullable=True)  # optimal, feasible, infeasible, unknown, no_periods, ...
    # When generation started - the moment the solver read the school's rules.
    # A rule saved after this wasn't part of the solve, so it isn't "broken" by
    # this timetable, just not applied yet. Null on timetables from before the
    # column existed, for which every rule is checked as before.
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    error_message = Column(Text, nullable=True)
    # Plain-language rewrite of error_message, generated once at failure
    # time by app/services/infeasibility_explainer.py (see its docstring).
    # Null whenever that service couldn't run (no ANTHROPIC_API_KEY, etc.)
    # or wasn't applicable (e.g. the generic timeout/unattributed-failure
    # messages, which are already plain English) — the frontend falls
    # back to showing just the raw error_message list in that case, so a
    # null here is never a broken state, just a less-polished one.
    error_explanation = Column(Text, nullable=True)
    # Version 1, 2, 3... per school, fixed at creation so numbers don't shift
    # when older versions are deleted. `name` is the admin's own label.
    version_number = Column(Integer, nullable=True)
    name = Column(String(80), nullable=True)
    # What a successful generation wants the admin to know: a frozen section
    # that couldn't be kept, a rule that couldn't be applied, a subject with no
    # teacher yet. These used to be logged and thrown away, so a freeze that
    # silently didn't hold looked exactly like one that did.
    generation_notes = Column(JSON, nullable=True)

    entries = relationship("TimetableEntry", back_populates="timetable", cascade="all, delete-orphan")


class TimetableEntry(Base):
    """One (class group, subject, teacher, room, period) assignment."""
    __tablename__ = "timetable_entries"

    id = Column(Integer, primary_key=True)
    timetable_id = Column(Integer, ForeignKey("timetables.id"), nullable=False)
    class_group_id = Column(Integer, ForeignKey("class_groups.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    # None = a subject with no qualified teacher yet, placed anyway.
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)
    period_id = Column(Integer, ForeignKey("periods.id"), nullable=False)
    locked = Column(Boolean, default=False)  # admin locked this slot before regenerating
    # Copied from SubjectRequirement.assistant_teacher_id at generation
    # time (see _run_generation_job in app/routers/timetables.py) — not
    # something the solver chooses or optimizes around, just carried over
    # so the generated grid can show who's assisting on this slot without
    # a separate lookup back to the plan.
    assistant_teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    # 1-indexed batch number when this entry came from a Subject.lab_batch_count
    # split (see app/services/solver.py) — null for every normal, unsplit
    # entry. Lets the frontend show "Batch 1"/"Batch 2" for what would
    # otherwise be two indistinguishable rows at the same class/subject/period.
    lab_batch = Column(Integer, nullable=True)
    # Set when this entry is one option of an elective block - several entries
    # then share one section and period, one per option. Lets the grid show
    # them as one block, lets dragging move them together, and is what a
    # student's own timetable is filtered by. SET NULL rather than cascade on
    # the block's deletion: a generated timetable is a record and keeps its
    # rows, it just stops knowing they were a block.
    elective_block_id = Column(
        Integer, ForeignKey("elective_blocks.id", ondelete="SET NULL"), nullable=True
    )

    timetable = relationship("Timetable", back_populates="entries")

    # Every read of a timetable filters by timetable_id, and edits look up one
    # section's period (a slot) or everything in one period (conflict checks).
    # Without these each of those scans every entry of every timetable ever
    # generated, by every school - about a thousand more rows per Generate.
    __table_args__ = (
        Index("ix_timetable_entries_timetable_class_period", "timetable_id", "class_group_id", "period_id"),
        Index("ix_timetable_entries_timetable_period", "timetable_id", "period_id"),
    )


class SchoolMembership(Base):
    """
    A second admin/viewer login for a school, on top of School.owner_id.

    The owner (School.owner_id) is always an implicit "admin" member, even
    with no row here — this table only needs to exist for *additional*
    users, so a freshly created school with a single owner works exactly
    as before with zero rows in this table (see
    app/core/access.get_membership_role for where that implicit-owner
    check lives, right alongside the explicit-row lookup). Rows here are
    normally created by accepting an invite (see SchoolInvite below), not
    directly.

    Roles are deliberately just two tiers for now: "admin" (everything the
    owner can do, including inviting/removing other members) and "viewer"
    (read-only — every mutating endpoint rejects a viewer with 403, see
    app/core/access.require_school_access). See docs/ARCHITECTURE.md for
    why finer-grained permissions were left out of this first pass.
    """
    __tablename__ = "school_memberships"
    __table_args__ = (UniqueConstraint("school_id", "user_id", name="uq_membership_school_user"),)

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String, nullable=False, default="viewer")  # "admin" | "viewer"

    school = relationship("School")
    user = relationship("User")


class SchoolInvite(Base):
    """
    A pending invitation for someone (identified by email, not yet
    necessarily a User row) to join a school with a given role. Created by
    an existing admin (POST /api/schools/{id}/invites), consumed by
    POST /api/invites/{token}/accept — which creates the User row too if
    the invited email hasn't signed up yet, so an admin can invite a
    colleague who's never used the app before. `token` is the only thing
    the invite link needs to carry; it's long and random specifically so
    it's safe to put in a URL and email (see app/routers/invites.py for
    how it's generated).
    """
    __tablename__ = "school_invites"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    email = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False, default="viewer")  # "admin" | "viewer"
    token = Column(String, nullable=False, unique=True, index=True)
    invited_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String, nullable=False, default="pending")  # "pending" | "accepted" | "revoked"

    school = relationship("School")


class SubstitutionLog(Base):
    """
    A day's worth of manual teacher-substitution records — e.g. "Ms. Iyer
    is out Wednesday, Mr. Rao is covering her Period 3 Grade 8A Math
    class." This is deliberately a simple audit log, not something the
    solver reads or reasons about: substitutions are same-day, one-off
    fixes an admin makes by hand when a teacher is unexpectedly absent,
    not a scheduling constraint to solve around. See
    app/routers/substitutions.py.

    `changes` stores a list of individual swaps as JSON (each with
    period_id, absent_teacher_id, substituting_teacher_id, class_group_id,
    and an optional subject_id) rather than one row per swap, so a whole
    day's substitutions are created and read as a single record — see
    app/schemas/substitutions.py's SubstitutionChange for the shape of
    each entry.
    """
    __tablename__ = "substitution_logs"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0 = Monday ... 6 = Sunday
    changes = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    school = relationship("School")
