"""
One-off verification script for lab-batch splitting (Subject.lab_batch_count).
Not part of the test suite - run manually: python verify_lab_batches.py

Builds a small in-memory SQLite school: one class group, a normal subject
(Math) and a lab subject split into 3 batches (Programming Lab), 3 teachers
qualified for the lab, one teacher for Math, a handful of periods and rooms.
Asserts:
  - generation succeeds (optimal/feasible)
  - the lab subject produces exactly 3 simultaneous entries per session,
    all at the same period, each with a distinct teacher
  - no teacher is double-booked anywhere in the result
  - batches get distinct rooms when enough lab-type rooms exist
"""
import sys

sys.path.insert(0, ".")

from app.core.database import Base, SessionLocal, engine
from app.models.school import ClassGroup, Period, Room, Subject, SubjectRequirement, Teacher, School
from app.models.user import User
from app.services.solver import generate_school_timetable

Base.metadata.create_all(bind=engine)
db = SessionLocal()

owner = User(email="verify@example.com", hashed_password="x")
db.add(owner)
db.commit()
db.refresh(owner)

school = School(name="Verify College", owner_id=owner.id)
db.add(school)
db.commit()
db.refresh(school)

cg = ClassGroup(school_id=school.id, grade="Semester 3", name="A")
db.add(cg)
db.commit()
db.refresh(cg)

math = Subject(school_id=school.id, name="Math")
lab = Subject(school_id=school.id, name="Programming Lab", required_room_type="lab", lab_batch_count=3)
db.add_all([math, lab])
db.commit()
db.refresh(math)
db.refresh(lab)

math_teacher = Teacher(school_id=school.id, name="Mr. Rao", qualified_subject_ids=[math.id])
lab_teachers = [
    Teacher(school_id=school.id, name=f"Lab Teacher {i+1}", qualified_subject_ids=[lab.id])
    for i in range(3)
]
db.add(math_teacher)
db.add_all(lab_teachers)
db.commit()
for t in [math_teacher] + lab_teachers:
    db.refresh(t)

for day in range(5):
    for order in range(4):
        db.add(Period(school_id=school.id, day_of_week=day, order=order, label=f"P{order+1}"))
db.commit()

lab_rooms = [Room(school_id=school.id, name=f"Lab {i+1}", room_type="lab") for i in range(3)]
db.add_all(lab_rooms)
db.commit()

db.add(SubjectRequirement(class_group_id=cg.id, subject_id=math.id, periods_per_week=4))
db.add(SubjectRequirement(class_group_id=cg.id, subject_id=lab.id, periods_per_week=2))
db.commit()

result = generate_school_timetable(db, school.id)
print("status:", result.status)
print("errors:", result.errors)
assert result.status in ("optimal", "feasible"), f"expected success, got {result.status}: {result.errors}"

lab_assignments = [a for a in result.assignments if a["subject_id"] == lab.id]
print(f"lab assignments: {len(lab_assignments)}")
assert len(lab_assignments) == 2 * 3, f"expected 6 (2 sessions x 3 batches), got {len(lab_assignments)}"

by_period = {}
for a in lab_assignments:
    by_period.setdefault(a["period_id"], []).append(a)

assert len(by_period) == 2, f"expected 2 distinct lab session periods, got {len(by_period)}"
for period_id, batch_group in by_period.items():
    assert len(batch_group) == 3, f"period {period_id} has {len(batch_group)} batches, expected 3"
    teacher_ids = [a["teacher_id"] for a in batch_group]
    assert len(set(teacher_ids)) == 3, f"batches at period {period_id} share a teacher: {teacher_ids}"
    batch_numbers = sorted(a["batch"] for a in batch_group)
    assert batch_numbers == [1, 2, 3], f"expected batch numbers 1,2,3, got {batch_numbers}"
    room_ids = [a.get("room_id") for a in batch_group]
    assert len(set(room_ids)) == 3 and None not in room_ids, f"batches at period {period_id} didn't get 3 distinct rooms: {room_ids}"

# No teacher double-booked anywhere in the full result (lab + math).
seen = set()
for a in result.assignments:
    key = (a["teacher_id"], a["period_id"])
    assert key not in seen, f"teacher {a['teacher_id']} double-booked at period {a['period_id']}"
    seen.add(key)

print("ALL CHECKS PASSED")
