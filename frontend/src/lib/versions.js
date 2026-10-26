/**
 * Which timetable version to show, from the school's list of versions.
 *
 * The school works from its *current* version (backend
 * app/services/versions.py): the one it chose, or the newest successful one.
 * A generation still running is shown instead, so its progress is visible, and
 * a generation that failed after the current version is reported alongside it
 * rather than replacing it - a failed attempt shouldn't hide the timetable the
 * school is working from.
 */
export function pickVersions(list = []) {
  if (!list.length) return { current: null, newest: null, shownId: null, failure: null }
  const newest = list.reduce((a, b) => (b.id > a.id ? b : a))
  const current =
    list.find((t) => t.is_current) ??
    [...list].filter((t) => t.status === 'draft' || t.status === 'published').sort((a, b) => b.id - a.id)[0] ??
    null
  if (newest.status === 'generating') return { current, newest, shownId: newest.id, failure: null }
  const failure = newest.status === 'failed' && (!current || newest.id > current.id) ? newest : null
  return { current, newest, shownId: current?.id ?? newest.id, failure }
}

/** "Version 3" or "Version 3 · Grades 1-5 approved". */
export function versionLabel(t) {
  if (!t) return ''
  const base = `Version ${t.version_number ?? t.id}`
  return t.name ? `${base} · ${t.name}` : base
}
