import { inBlock, optionsFor } from './electiveSections'

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
 * `{ choices: [[blockId, subjectId, optionId], ...], label: 'Physics + Chemistry' }`.
 * A section that joins a block made in another counts it too, and only the
 * groups its own students are in are choices.
 *
 * Empty when the section has no blocks - its timetable is the same for
 * everyone. `null` when there are more than MAX_COMBINATIONS.
 */
export function combinationsFor(blocks, classGroupId, subjectName) {
  const mine = blocks
    .filter((b) => inBlock(b, classGroupId) && optionsFor(b, classGroupId).length > 0)
    .sort((a, b) => a.id - b.id)
  if (mine.length === 0) return []

  const labelOf = new Map(mine.flatMap((b) => b.options.map((o) => [o.id, o.label])))
  const perBlock = mine.map((b) =>
    [...optionsFor(b, classGroupId)].sort((x, y) => x.id - y.id).map((o) => [b.id, o.subject_id, o.id]),
  )
  const total = perBlock.reduce((n, options) => n * options.length, 1)
  if (total > MAX_COMBINATIONS) return null

  let picks = [[]]
  for (const options of perBlock) {
    picks = picks.flatMap((picked) => options.map((choice) => [...picked, choice]))
  }
  return picks.map((choices) => ({
    choices,
    label: choices
      .map(([, subjectId, optionId]) =>
        labelOf.get(optionId) ? `${subjectName(subjectId)} (${labelOf.get(optionId)})` : subjectName(subjectId),
      )
      .join(' + '),
  }))
}

/** Whether a student with this combination is in the lesson an entry describes. */
export function keeps(combination, entry) {
  if (entry.elective_block_id == null) return true
  if (entry.elective_option_id != null && combination.choices.every((c) => c[2] != null)) {
    return combination.choices.some(([, , optionId]) => optionId === entry.elective_option_id)
  }
  return combination.choices.some(
    ([blockId, subjectId]) => blockId === entry.elective_block_id && subjectId === entry.subject_id,
  )
}
