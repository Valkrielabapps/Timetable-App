"""Which elective blocks and options a section takes part in.

A block belongs to the section it was made in, but can span others too (see
ElectiveBlock.section_ids), and each option is a group drawn from some or all
of those sections (ElectiveOption.group_section_ids). Everything that asks
"what does this section study in its blocks" goes through here, so a section
that only joins a block made elsewhere is never forgotten.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.school import ElectiveBlock, ElectiveBlockSection


def blocks_for_sections(db: Session, section_ids) -> list[ElectiveBlock]:
    """Every block any of these sections is in, made there or joined."""
    ids = list(set(section_ids))
    if not ids:
        return []
    joined = db.query(ElectiveBlockSection.block_id).filter(ElectiveBlockSection.class_group_id.in_(ids))
    return (
        db.query(ElectiveBlock)
        .filter(or_(ElectiveBlock.class_group_id.in_(ids), ElectiveBlock.id.in_(joined)))
        .order_by(ElectiveBlock.id)
        .all()
    )


def option_subjects_by_section(db: Session, section_ids) -> dict[int, dict[int, str]]:
    """section id -> {subject id: block name} for the block options its
    students are in."""
    wanted = set(section_ids)
    out: dict[int, dict[int, str]] = {s: {} for s in wanted}
    for block in blocks_for_sections(db, wanted):
        for option in block.options:
            for s in option.group_section_ids:
                if s in wanted:
                    out[s].setdefault(option.subject_id, block.name)
    return out


def options_for_section(block: ElectiveBlock, section_id: int) -> list:
    """The groups of a block whose students include this section's."""
    return [o for o in block.options if section_id in o.group_section_ids]
