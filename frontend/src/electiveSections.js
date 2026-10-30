/**
 * Which sections an elective block, and each of its groups, covers.
 *
 * A block can span several sections (`section_ids`), and each option is a
 * teaching group drawn from some of them (`class_group_ids`, null = all).
 * Mirrors backend/app/services/elective_sections.py. Older payloads without
 * `section_ids` are a block for its own section alone.
 */
export const blockSectionIds = (block) => block.section_ids ?? [block.class_group_id]

export const inBlock = (block, classGroupId) => blockSectionIds(block).includes(classGroupId)

export const groupSectionIds = (block, option) => {
  const all = blockSectionIds(block)
  if (!option.class_group_ids || option.class_group_ids.length === 0) return all
  return all.filter((id) => option.class_group_ids.includes(id))
}

/** The groups of a block whose students include this section's. */
export const optionsFor = (block, classGroupId) =>
  block.options.filter((o) => groupSectionIds(block, o).includes(classGroupId))

/** A block's name for one section, with the others sharing it. */
export const sharedWithText = (names) => (names?.length ? `with ${names.join(', ')}` : '')

/**
 * A teacher's view of entries: a block group taught to several sections is
 * one entry per section, but one lesson for its teacher. Copies are merged
 * into the first, which gains `class_group_ids` (every section in it) and
 * `copy_ids` (every entry id). Other entries pass through unchanged.
 */
export function teacherLessons(entries) {
  const seen = new Map()
  const out = []
  for (const e of entries) {
    if (e.elective_option_id == null || e.teacher_id == null) {
      out.push(e)
      continue
    }
    const key = `${e.period_id}:${e.elective_option_id}:${e.teacher_id}`
    const first = seen.get(key)
    if (first) {
      first.class_group_ids.push(e.class_group_id)
      first.copy_ids.push(e.id)
      continue
    }
    const merged = { ...e, class_group_ids: [e.class_group_id], copy_ids: [e.id] }
    seen.set(key, merged)
    out.push(merged)
  }
  return out
}
