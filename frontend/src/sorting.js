/**
 * Sorting and searching people and things by name.
 *
 * Everything listing teachers or subjects is alphabetical by default, and a
 * teacher sorts by their name, never their title: "Mrs. Rao" goes under R,
 * next to "Rahul", not in a block with every other "Mrs." at M. Titles
 * arrive however a school typed them - "Mrs.", "mrs", "Dr", "Prof." - so all
 * of them are ignored, wherever they came from.
 *
 * Numbers sort as numbers, so "Grade 2" comes before "Grade 10".
 */

// A title at the start of a name, with or without its full stop. More than
// one ("Prof. Dr. Iyer") is stripped in turn.
const TITLE = /^\s*(mr|mrs|ms|miss|mx|dr|prof|professor)\.?(\s+|$)/i

export function withoutTitle(name) {
  const original = (name ?? '').trim()
  let rest = original
  for (;;) {
    const next = rest.replace(TITLE, '')
    if (next === rest) break
    rest = next
  }
  // A name that is nothing but a title is still a name.
  return rest.trim() || original
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

/** Compare two names alphabetically, ignoring titles, capitals and accents. */
export function compareNames(a, b) {
  return collator.compare(withoutTitle(a), withoutTitle(b)) || collator.compare(a ?? '', b ?? '')
}

/** A comparator for objects, by whatever `getName` reads off them. */
export const byName = (getName = (x) => x.name) => (a, b) => compareNames(getName(a), getName(b))

/** A sorted copy, alphabetical by name. */
export const sortByName = (list, getName = (x) => x.name) => [...list].sort(byName(getName))

/** Sections by grade, then name - "Grade 2 · A" before "Grade 10 · A". */
export function sortSections(sections) {
  return [...sections].sort(
    (a, b) => compareNames(a.grade ?? '', b.grade ?? '') || compareNames(a.name ?? '', b.name ?? ''),
  )
}

/** Whether every word typed appears somewhere in the text. */
export function matchesSearch(text, query) {
  const words = (query ?? '').trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length === 0) return true
  const haystack = (text ?? '').toLowerCase()
  return words.every((w) => haystack.includes(w))
}

/**
 * What a search box should offer for what was typed, best first: names
 * that start with it ("vi" -> "Vinita"), then names with a word starting
 * with it ("rao" -> "Mrs. Rao"), then anything containing it. Alphabetical
 * within each, so the order never feels random.
 */
export function rankMatches(items, query, getName = (x) => x.name) {
  const q = (query ?? '').trim().toLowerCase()
  if (!q) return sortByName(items, getName)
  const scored = []
  for (const item of items) {
    const name = getName(item) ?? ''
    const bare = withoutTitle(name).toLowerCase()
    const full = name.toLowerCase()
    let score = null
    if (bare.startsWith(q)) score = 0
    else if (full.split(/[\s.\-–]+/).some((word) => word.startsWith(q))) score = 1
    else if (matchesSearch(full, q)) score = 2
    if (score !== null) scored.push({ item, score, name })
  }
  scored.sort((a, b) => a.score - b.score || compareNames(a.name, b.name))
  return scored.map((s) => s.item)
}

/**
 * Remembered per device: how a list was last sorted. Wrapped because storage
 * can be unavailable (private windows, blocked site data) and a sort choice
 * is never worth an error.
 */
export function loadChoice(key, fallback) {
  try {
    return window.localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

export function saveChoice(key, value) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Not remembered this time; nothing else depends on it.
  }
}
