"""
Stress test: generate a timetable for a school with 50+ sections, using a
*realistic* teacher assignment structure rather than a fully-symmetric
worst case (every teacher qualified for every subject/section) - real
schools have natural variation (subject teachers are assigned per grade
band, not shared across the whole school), which is much friendlier to
the solver than a deliberately adversarial fully-symmetric instance.

Structure: 10 grades x 5 sections = 50 sections. Each grade has its own
dedicated pool of 2 teachers per subject (8 subjects), so teachers aren't
shared across grades - this mirrors how Indian schools typically staff
larger campuses (a "Grade 6-8 wing" teacher roster, etc).

Not part of the app itself - a one-off diagnostic script, run directly
with `python3 stress_test_50sections.py`.
"""
import os
import time

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/stress_50.db")
if os.path.exists("/tmp/stress_50.db"):
    os.remove("/tmp/stress_50.db")

from app.core.database import Base, engine, SessionLocal  # noqa: E402
import app.models.user  # noqa: E402, F401 - registers User table
from app.models.school import (  # noqa: E402
    School, Period, Subject, Teacher, ClassGroup, SubjectRequirement, Constraint,
)
from app.services.solver import generate_school_timetable  # noqa: E402

Base.metadata.create_all(bind=engine)
db = SessionLocal()

school = School(name="Stress Test School (50 sections)")
db.add(school)
db.commit()
db.refresh(school)

# 5 days x 8 periods/day = 40 slots/week per section
periods = []
for day in range(5):
    for order in range(8):
        p = Period(school_id=school.id, day_of_week=day, order=order, label=f"P{order}")
        db.add(p)
        periods.append(p)
db.commit()

SUBJECT_NAMES = ["Math", "English", "Science", "Social Studies", "Hindi", "Computer", "Art", "PE"]
PERIODS_PER_WEEK = [6, 6, 5, 5, 4, 4, 5, 5]  # sums to 40, matches the week's capacity
assert sum(PERIODS_PER_WEEK) == 40

subjects = {}
for name in SUBJECT_NAMES:
    s = Subject(school_id=school.id, name=name)
    db.add(s)
    subjects[name] = s
db.commit()

NUM_GRADES = int(os.environ.get("NUM_GRADES", "10"))
GRADES = [f"Grade {i}" for i in range(1, NUM_GRADES + 1)]
SECTIONS = ["A", "B", "C", "D", "E"]  # 5 sections each = 50 total

class_groups = []
teacher_count = 0
requirement_count = 0

TEACHERS_PER_SUBJECT_PER_GRADE = int(os.environ.get("TEACHERS_PER_SUBJECT_PER_GRADE", "2"))
# If set, pins each section's requirement to a specific teacher
# (round-robin across the pool) instead of leaving the solver free to pick
# among interchangeable teachers. This is what "assign preferred teacher"
# looks like in the real UI, and it's the practical fix for symmetry-driven
# slowness: the admin (who already knows who's covering which section)
# tells the solver, instead of making it search for an arbitrary
# equally-valid answer among N! interchangeable options.
PIN_PREFERRED_TEACHER = os.environ.get("PIN_PREFERRED_TEACHER") == "1"

grade_teachers_by_grade = {}

for grade in GRADES:
    # dedicated teachers per subject for this grade only (not shared
    # across grades) - realistic staffing, but >1 interchangeable teacher
    # per subject introduces symmetry the solver has to break itself
    # (unless PIN_PREFERRED_TEACHER pins it ahead of time).
    grade_teachers = {}
    for name in SUBJECT_NAMES:
        pool = []
        for i in range(TEACHERS_PER_SUBJECT_PER_GRADE):
            t = Teacher(
                school_id=school.id,
                name=f"{grade} {name} Teacher {i + 1}",
                qualified_subject_ids=[subjects[name].id],
            )
            db.add(t)
            pool.append(t)
            teacher_count += 1
        grade_teachers[name] = pool
    grade_teachers_by_grade[grade] = grade_teachers

    for section in SECTIONS:
        cg = ClassGroup(school_id=school.id, grade=grade, name=section)
        db.add(cg)
        class_groups.append(cg)
db.commit()

for section_index, cg in enumerate(class_groups):
    grade = cg.grade
    for name, ppw in zip(SUBJECT_NAMES, PERIODS_PER_WEEK):
        preferred_teacher_id = None
        if PIN_PREFERRED_TEACHER:
            pool = grade_teachers_by_grade[grade][name]
            preferred_teacher_id = pool[section_index % len(pool)].id
        req = SubjectRequirement(
            class_group_id=cg.id,
            subject_id=subjects[name].id,
            periods_per_week=ppw,
            preferred_teacher_id=preferred_teacher_id,
        )
        db.add(req)
        requirement_count += 1
db.commit()

print(f"Seeded: {len(class_groups)} sections, {teacher_count} teachers, {requirement_count} requirements, {len(periods)} periods")

start = time.time()
result = generate_school_timetable(db, school.id)
elapsed = time.time() - start

print(f"\nSolve finished in {elapsed:.1f}s")
print(f"status = {result.status}")
print(f"assignments = {len(result.assignments)}")
if result.errors:
    print("errors:", result.errors)

db.close()
