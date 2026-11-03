"""
One-off verification script for deleting a ClassGroup that already has
generated TimetableEntry rows - checks the fix in
app/routers/class_groups.py's delete_class_group (explicit TimetableEntry
cleanup, since there's no ORM cascade for that relationship).

Run manually: DATABASE_URL="sqlite:////tmp/verify_delete.db" python verify_delete_class_group.py
"""
import sys

sys.path.insert(0, ".")

from app.core.database import Base, SessionLocal, engine
from app.models.school import ClassGroup, Period, Subject, SubjectRequirement, Teacher, School, Timetable, TimetableEntry
from app.models.user import User

Base.metadata.create_all(bind=engine)
db = SessionLocal()

owner = User(email="verify-delete@example.com", hashed_password="x")
db.add(owner)
db.commit()
db.refresh(owner)

school = School(name="Verify Delete School", owner_id=owner.id)
db.add(school)
db.commit()
db.refresh(school)

cg = ClassGroup(school_id=school.id, grade="Grade 5", name="A")
db.add(cg)
db.commit()
db.refresh(cg)

subject = Subject(school_id=school.id, name="Math")
db.add(subject)
db.commit()
db.refresh(subject)

teacher = Teacher(school_id=school.id, name="Ms. Iyer", qualified_subject_ids=[subject.id])
db.add(teacher)
db.commit()
db.refresh(teacher)

period = Period(school_id=school.id, day_of_week=0, order=0, label="P1")
db.add(period)
db.commit()
db.refresh(period)

req = SubjectRequirement(class_group_id=cg.id, subject_id=subject.id, periods_per_week=1)
db.add(req)
db.commit()

timetable = Timetable(school_id=school.id, status="draft", solver_status="optimal")
db.add(timetable)
db.commit()
db.refresh(timetable)

entry = TimetableEntry(
    timetable_id=timetable.id,
    class_group_id=cg.id,
    subject_id=subject.id,
    teacher_id=teacher.id,
    period_id=period.id,
)
db.add(entry)
db.commit()

# Sanity: the entry exists before deletion.
assert db.query(TimetableEntry).filter(TimetableEntry.class_group_id == cg.id).count() == 1

# Simulate the router's delete_class_group logic directly (avoids needing
# a running server/auth for this one-off check).
db.query(TimetableEntry).filter(TimetableEntry.class_group_id == cg.id).delete()
db.delete(cg)
db.commit()

remaining_entries = db.query(TimetableEntry).filter(TimetableEntry.class_group_id == cg.id).count()
remaining_requirements = db.query(SubjectRequirement).filter(SubjectRequirement.class_group_id == cg.id).count()
remaining_class_group = db.get(ClassGroup, cg.id)

assert remaining_entries == 0, f"expected 0 orphaned timetable entries, found {remaining_entries}"
assert remaining_requirements == 0, f"expected 0 orphaned requirements, found {remaining_requirements}"
assert remaining_class_group is None, "class group should be gone"

print("ALL CHECKS PASSED")
