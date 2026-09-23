"""
Core database models.

Kept generic (not tied to one curriculum/board) per docs/ARCHITECTURE.md:
schools define their own periods, subjects, and constraints rather than the
schema assuming a fixed structure.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
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
    # A slot in the day that exists in the ordering but is never taught in -
    # lunch, assembly, games. Kept as a Period rather than a gap in `order`
    # so "the period after lunch" resolves to something, and so a teacher's
    # back-to-back run is correctly interrupted by it (see
    # app/services/solver.py, which splits each day into runs at breaks
    # rather than treating periods 3 and 5 as adjacent).
    is_break = Column(Boolean, nullable=False, default=False, server_default="false")

    school = relationship("School", back_populates="periods")

    __table_args__ = (UniqueConstraint("school_id", "day_of_week", "order"),)


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
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
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    name = Column(String, nullable=False)
    capacity = Column(Integer, nullable=True)
    room_type = Column(String, nullable=True)  # e.g. "lab", "regular", "auditorium"

    school = relationship("School", back_populates="rooms")


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
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
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    grade = Column(String, nullable=True)
    name = Column(String, nullable=False)
    student_count = Column(Integer, nullable=True)

    school = relationship("School", back_populates="class_groups")
    requirements = relationship(
        "SubjectRequirement", back_populates="class_group", cascade="all, delete-orphan"
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
    # Optional second teacher for this section's subject — picked from
    # teachers flagged Teacher.is_assistant_eligible, independent of
    # qualified_subject_ids (an assistant doesn't need to be independently
    # qualified to teach the subject solo). Purely informational: the
    # solver doesn't currently schedule around this, it's just recorded
    # and shown alongside the main teacher.
    assistant_teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)

    __table_args__ = (UniqueConstraint("class_group_id", "subject_id"),)

    class_group = relationship("ClassGroup", back_populates="requirements")


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
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    type = Column(String, nullable=False)
    parameters = Column(JSON, default=dict)
    is_hard = Column(Boolean, default=True)
    weight = Column(Integer, default=1)  # relevant for soft constraints only
    description = Column(Text, nullable=True)  # human-readable, shown in the UI

    school = relationship("School", back_populates="constraints")


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
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    status = Column(String, default="generating")  # generating, draft, failed, published, archived
    solver_status = Column(String, nullable=True)  # optimal, feasible, infeasible, unknown, no_periods, ...
    error_message = Column(Text, nullable=True)
    # Plain-language rewrite of error_message, generated once at failure
    # time by app/services/infeasibility_explainer.py (see its docstring).
    # Null whenever that service couldn't run (no ANTHROPIC_API_KEY, etc.)
    # or wasn't applicable (e.g. the generic timeout/unattributed-failure
    # messages, which are already plain English) — the frontend falls
    # back to showing just the raw error_message list in that case, so a
    # null here is never a broken state, just a less-polished one.
    error_explanation = Column(Text, nullable=True)

    entries = relationship("TimetableEntry", back_populates="timetable", cascade="all, delete-orphan")


class TimetableEntry(Base):
    """One (class group, subject, teacher, room, period) assignment."""
    __tablename__ = "timetable_entries"

    id = Column(Integer, primary_key=True)
    timetable_id = Column(Integer, ForeignKey("timetables.id"), nullable=False)
    class_group_id = Column(Integer, ForeignKey("class_groups.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
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

    timetable = relationship("Timetable", back_populates="entries")


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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
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
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
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
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0 = Monday ... 6 = Sunday
    changes = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    school = relationship("School")
