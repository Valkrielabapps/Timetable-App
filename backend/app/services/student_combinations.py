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
    # The group chosen in each block, in block order - what tells "Maths
    # group 1" from "Maths group 2" when a subject is split.
    option_ids: tuple[int, ...] = ()

    def keeps(self, entry) -> bool:
        """Whether this student is in the lesson an entry describes."""
        if entry.elective_block_id is None:
            return True
        option_id = getattr(entry, "elective_option_id", None)
        if option_id is not None and self.option_ids:
            return option_id in self.option_ids
        return (entry.elective_block_id, entry.subject_id) in self.choices


def combinations_for(db: Session, class_group_id: int) -> list[Combination]:
    """Every way of choosing one option from each of a section's blocks.

    Empty when the section has no blocks: its timetable is already the only
    one, and there is nothing to choose between.
    """
    from app.services.elective_sections import blocks_for_sections, options_for_section

    per_block_options = [
        (b, sorted(options_for_section(b, class_group_id), key=lambda o: o.id))
        for b in blocks_for_sections(db, [class_group_id])
    ]
    per_block_options = [(b, opts) for b, opts in per_block_options if opts]
    if not per_block_options:
        return []

    total = 1
    for _b, opts in per_block_options:
        total *= len(opts)
    if total > MAX_COMBINATIONS:
        raise TooManyCombinations(
            f"This section's blocks allow {total} different combinations, which is more than "
            f"can sensibly be printed ({MAX_COMBINATIONS}). Check the blocks for a mistake."
        )

    subject_ids = {o.subject_id for _b, opts in per_block_options for o in opts}
    names = {
        s.id: s.name for s in db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
    }

    def name(o) -> str:
        base = names.get(o.subject_id, "?")
        return f"{base} ({o.label})" if o.label else base

    return [
        Combination(
            choices=tuple((o.block_id, o.subject_id) for o in picked),
            label=" + ".join(name(o) for o in picked),
            option_ids=tuple(o.id for o in picked),
        )
        for picked in product(*(opts for _b, opts in per_block_options))
    ]
