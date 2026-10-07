/**
 * A student's own timetable, for each combination of elective choices.
 *
 * Mirrors backend/app/services/student_combinations.py, which builds the same
 * list for the export. No extra solving either side: a section's timetable
 * already holds every combination at once, so a student's is a filter over it
 * - the subjects everyone takes, plus only the chosen option from each block.
 *
 * Same order as the backend - blocks by id, options by id - so "combination 3"
 * on screen is sheet 3 of the export.
 */

// Past this the blocks are almost certainly a data-entry mistake; a picker
// with hundreds of entries helps nobody. Same cap as the export.
export const MAX_COMBINATIONS = 512

/**
 * Every way of choosing one option from each of a section's blocks, as
 * `{ choices: [[blockId, subjectId], ...], label: 'Physics + Chemistry' }`.
 *
 * Empty when the section has no blocks - its timetable is the same for
 * everyone. `null` when there are more than MAX_COMBINATIONS.
 */
export function combinationsFor(blocks, classGroupId, subjectName) {
  const mine = blocks
    .filter((b) => b.class_group_id === classGroupId && b.options.length > 0)
    .sort((a, b) => a.id - b.id)
  if (mine.length === 0) return []

  const perBlock = mine.map((b) =>
    [...b.options].sort((x, y) => x.id - y.id).map((o) => [b.id, o.subject_id]),
  )
  const total = perBlock.reduce((n, options) => n * options.length, 1)
  if (total > MAX_COMBINATIONS) return null

  let picks = [[]]
  for (const options of perBlock) {
    picks = picks.flatMap((picked) => options.map((choice) => [...picked, choice]))
  }
  return picks.map((choices) => ({
    choices,
    label: choices.map(([, subjectId]) => subjectName(subjectId)).join(' + '),
  }))
}

/** Whether a student with this combination is in the lesson an entry describes. */
export function keeps(combination, entry) {
  if (entry.elective_block_id == null) return true
  return combination.choices.some(
    ([blockId, subjectId]) => blockId === entry.elective_block_id && subjectId === entry.subject_id,
  )
}
