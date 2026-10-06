"""
A student's own timetable, for each combination of elective choices.

No extra solving. The section's timetable already contains every combination
at once - that is the whole point of blocks: Physics and Chemistry are in
different blocks precisely so one student can take both. So a student's
timetable is a filter over the section's: the subjects everyone takes, plus,
from each block, only the option they chose.

The combinations are every way of picking one option from each block. The
school decided which subjects share a block, which is what decides which
combinations exist, so all of them are produced; a combination nobody takes
costs a page, while a missing one is a student with no timetable.

Order is fixed - blocks by id, options by id - and the frontend enumerates in
the same order, so "combination 3" means the same thing on screen and on paper.
"""
from dataclasses import dataclass
from itertools import product

from sqlalchemy.orm import Session

from app.models.school import ElectiveBlock, Subject

# Four blocks of five options is 625 pages. Past this the request is almost
# certainly a data-entry mistake rather than a school's real structure, and
# producing it would just look like the export had hung.
MAX_COMBINATIONS = 512


class TooManyCombinations(ValueError):
    pass


@dataclass(frozen=True)
class Combination:
    # (block_id, subject_id) for each block, in block order.
    choices: tuple[tuple[int, int], ...]
    # "Physics + Chemistry + Maths", for a title or a sheet name.
    label: str

    def keeps(self, entry) -> bool:
        """Whether this student is in the lesson an entry describes."""
        if entry.elective_block_id is None:
            return True
        return (entry.elective_block_id, entry.subject_id) in self.choices


def combinations_for(db: Session, class_group_id: int) -> list[Combination]:
    """Every way of choosing one option from each of a section's blocks.

    Empty when the section has no blocks: its timetable is already the only
    one, and there is nothing to choose between.
    """
    blocks = (
        db.query(ElectiveBlock)
        .filter(ElectiveBlock.class_group_id == class_group_id)
        .order_by(ElectiveBlock.id)
        .all()
    )
    blocks = [b for b in blocks if b.options]
    if not blocks:
        return []

    total = 1
    for b in blocks:
        total *= len(b.options)
    if total > MAX_COMBINATIONS:
        raise TooManyCombinations(
            f"This section's blocks allow {total} different combinations, which is more than "
            f"can sensibly be printed ({MAX_COMBINATIONS}). Check the blocks for a mistake."
        )

    subject_ids = {o.subject_id for b in blocks for o in b.options}
    names = {
        s.id: s.name for s in db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
    }
    per_block = [
        [(b.id, o.subject_id) for o in sorted(b.options, key=lambda o: o.id)] for b in blocks
    ]
    return [
        Combination(
            choices=tuple(picked),
            label=" + ".join(names.get(subject_id, "?") for _, subject_id in picked),
        )
        for picked in product(*per_block)
    ]
