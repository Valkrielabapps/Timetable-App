/**
 * The school's week as one structure, and how a day is laid out from it.
 *
 * Mirrors layout() in backend/app/services/timetable_structure.py so the
 * preview shows exactly the periods saving will make. The server is still the
 * one that makes them; this only draws them.
 */

export const DAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
export const DAY_FULL = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export const DEFAULT_STRUCTURE = {
  days: [0, 1, 2, 3, 4],
  periods_per_day: 8,
  short_days: {},
  breaks: [],
  class_teacher_period: { enabled: false, after: 0 },
  zero_period: { enabled: false, scope: 'school', placements: [] },
}

/**
 * Whether the zero period is a numbered slot kept free (true) or a slot of
 * its own between numbers (false). Only a whole-school zero period at the
 * same point every day is its own slot - anywhere else some sections are
 * being taught in it while others aren't.
 */
export function zeroIsNumbered(s) {
  const z = s.zero_period
  if (!z?.enabled) return false
  const wholeSchoolFixed =
    z.scope === 'school' && z.placements.length === 1 && z.placements[0].every_day != null
  return !wholeSchoolFixed
}

/** Ordinary periods on a day - fewer on a shorter day. */
export function periodsOn(s, day) {
  return Number(s.short_days?.[day] ?? s.periods_per_day)
}

/** Numbered slots on a day: its periods, plus the zero period's when it has one. */
export function lessonsOn(s, day) {
  return periodsOn(s, day) + (zeroIsNumbered(s) ? 1 : 0)
}

/**
 * The slots of one day, in order:
 *   { kind: 'class_teacher' | 'break' | 'zero' | 'lesson', number?, label?, zeroFor? }
 * `zeroFor` on a lesson lists who has their zero period there ('Whole school'
 * or grade names) when the zero period is a numbered slot kept free.
 */
export function layoutDay(s, day) {
  const lessons = lessonsOn(s, day)
  const numbered = zeroIsNumbered(s)
  const z = s.zero_period
  const zeroAt = z?.enabled && !numbered ? Number(z.placements[0].every_day) : null
  const ct = s.class_teacher_period
  const out = []
  const ctAfter = (k) => {
    if (ct?.enabled && Number(ct.after) === k) out.push({ kind: 'class_teacher' })
  }
  const zeroFor = (number) => {
    if (!numbered) return []
    return z.placements
      .filter((p) => {
        const at = p.every_day != null ? p.every_day : p.by_day?.[day]
        return at != null && Number(at) === number
      })
      .map((p) => p.grade ?? 'Whole school')
  }

  ctAfter(0)
  for (let k = 1; k <= lessons; k++) {
    if (zeroAt === k) out.push({ kind: 'zero' })
    out.push({ kind: 'lesson', number: k, zeroFor: zeroFor(k) })
    if (k < lessons) {
      ctAfter(k)
      for (const b of s.breaks) {
        if (Number(b.after) === k) out.push({ kind: 'break', label: b.label || 'Break' })
      }
    }
  }
  if (zeroAt === lessons + 1) out.push({ kind: 'zero' })
  return out
}

/** Server shape -> form shape: JSON object keys arrive as strings. */
export function fromServer(structure) {
  if (!structure) return DEFAULT_STRUCTURE
  const numericKeys = (obj) =>
    obj ? Object.fromEntries(Object.entries(obj).map(([k, v]) => [Number(k), Number(v)])) : obj
  return {
    ...structure,
    short_days: numericKeys(structure.short_days) ?? {},
    zero_period: {
      ...structure.zero_period,
      placements: structure.zero_period.placements.map((p) => ({ ...p, by_day: numericKeys(p.by_day) ?? null })),
    },
  }
}
