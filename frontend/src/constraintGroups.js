/**
 * Organising saved rules the way an admin looks for them.
 *
 * Rules used to be listed in the order they were typed, each headed by its
 * internal type - which, for every rule entered since the general form went
 * in, was "ir". At fifty rules that is a wall nobody can find anything in.
 *
 * Grouped instead by who the rule is about, using `about` from the server
 * (backend/app/services/constraint_about.py), which reads the stored rule - the
 * same fields the solver uses - rather than its wording:
 *
 *   Teachers          one group per teacher named, plus "Every teacher"
 *   Sections & grades one per section or grade named, plus "Every section"
 *   Subjects          one per subject named, plus "Every subject"
 *   Whole school      everything else
 *
 * A rule goes in the most specific category it names - teacher, then section,
 * then subject - because that is the one someone would look under: "Mrs. Rao
 * never teaches 11A in period 1" is a fact about Mrs. Rao's week first. Within
 * that category it appears under every name it mentions, so a rule about two
 * teachers is found under either.
 *
 * Anything that needs fixing is pulled out of the groups into its own list at
 * the top, rather than left as a note on a card somewhere in the middle.
 */

export const CATEGORIES = [
  { key: 'teachers', label: 'Teachers', every: 'teacher', everyLabel: 'Every teacher', field: 'teachers' },
  { key: 'sections', label: 'Sections & grades', every: 'class_group', everyLabel: 'Every section', field: 'class_groups' },
  { key: 'subjects', label: 'Subjects', every: 'subject', everyLabel: 'Every subject', field: 'subjects' },
  { key: 'school', label: 'Whole school' },
]

/** Where a rule is filed: [{ category, group }], group null for Whole school. */
export function placesFor(constraint) {
  const about = constraint.about ?? {}
  const named = CATEGORIES.slice(0, 3)
  for (const cat of named) {
    const names = about[cat.field] ?? []
    if (names.length) return names.map((name) => ({ category: cat.key, group: name }))
  }
  for (const cat of named) {
    if ((about.every ?? []).includes(cat.every)) return [{ category: cat.key, group: cat.everyLabel }]
  }
  return [{ category: 'school', group: null }]
}

/**
 * Why a rule needs looking at, in words. Empty when it is fine.
 *
 * `violatedIds` is the set of rule ids the current timetable breaks - normally
 * empty, filled by hand moves that pass every physical check but break a rule.
 */
export function problemsWith(constraint, violatedIds = new Set()) {
  const reasons = []
  if (!constraint.enforced) reasons.push('Not applied when generating')
  if (constraint.conflicts?.length) reasons.push('Contradicts another rule')
  if (violatedIds.has(constraint.id)) reasons.push('Broken by the current timetable')
  return reasons
}

/** The names that can be filtered by, from the rules that actually mention them. */
export function filterOptions(constraints) {
  const collect = (field) =>
    [...new Set(constraints.flatMap((c) => c.about?.[field] ?? []))].sort(byName)
  return { teachers: collect('teachers'), subjects: collect('subjects'), sections: collect('class_groups') }
}

export const NO_FILTERS = { text: '', teacher: '', subject: '', section: '', strength: 'all' }

export function filtersActive(filters) {
  return (
    filters.text.trim() !== '' ||
    filters.teacher !== '' ||
    filters.subject !== '' ||
    filters.section !== '' ||
    filters.strength !== 'all'
  )
}

/** Whether a rule passes the search box and filters. */
export function matches(constraint, filters) {
  const about = constraint.about ?? {}
  if (filters.teacher && !(about.teachers ?? []).includes(filters.teacher)) return false
  if (filters.subject && !(about.subjects ?? []).includes(filters.subject)) return false
  if (filters.section && !(about.class_groups ?? []).includes(filters.section)) return false
  if (filters.strength === 'rules' && constraint.is_hard === false) return false
  if (filters.strength === 'preferences' && constraint.is_hard !== false) return false
  const text = filters.text.trim().toLowerCase()
  if (text) {
    const haystack = [
      constraint.description,
      constraint.source_text,
      ...(about.teachers ?? []),
      ...(about.subjects ?? []),
      ...(about.class_groups ?? []),
    ]
      .filter(Boolean)
      .join('\n')
      .toLowerCase()
    if (!haystack.includes(text)) return false
  }
  return true
}

/**
 * Everything the list shows, after filtering:
 *
 *   attention   [{ constraint, reasons }] - rules with something to fix
 *   categories  [{ key, label, count, groups: [{ name, items }] }], empty
 *               categories left out; Whole school has one group, name null
 *   shown       how many rules passed the filters
 */
export function organise(constraints, { violatedIds = new Set(), filters = NO_FILTERS } = {}) {
  const visible = constraints.filter((c) => matches(c, filters)).sort((a, b) => a.id - b.id)
  const attention = []
  const byCategory = new Map(CATEGORIES.map((cat) => [cat.key, new Map()]))

  for (const c of visible) {
    const reasons = problemsWith(c, violatedIds)
    if (reasons.length) {
      attention.push({ constraint: c, reasons })
      continue
    }
    for (const { category, group } of placesFor(c)) {
      const groups = byCategory.get(category)
      if (!groups.has(group)) groups.set(group, [])
      groups.get(group).push(c)
    }
  }

  const categories = CATEGORIES.map((cat) => {
    const groups = [...byCategory.get(cat.key).entries()]
      .map(([name, items]) => ({ name, items }))
      // "Every teacher" first - it applies to everyone listed after it.
      .sort((a, b) =>
        a.name === cat.everyLabel ? -1 : b.name === cat.everyLabel ? 1 : byName(a.name ?? '', b.name ?? ''),
      )
    const count = new Set(groups.flatMap((g) => g.items.map((c) => c.id))).size
    return { key: cat.key, label: cat.label, count, groups }
  }).filter((cat) => cat.count > 0)

  return { attention, categories, shown: visible.length }
}

function byName(a, b) {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })
}
