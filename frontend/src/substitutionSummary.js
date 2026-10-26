/**
 * The parts of a school that substitutions are arranged by, and the ways a
 * day's summary leaves the screen: printed, or copied as text for WhatsApp.
 * The PDF is made by the server (app/services/substitution_summary.py).
 *
 * Which grade is in which part comes from the server too
 * (api.getGradeCategories) - the defaults and each school's changes live
 * there, in app/services/school_categories.py.
 */

export const CATEGORIES = [
  { key: 'pre_primary', label: 'Pre-primary' },
  { key: 'primary', label: 'Primary' },
  { key: 'middle', label: 'Middle' },
  { key: 'high', label: 'High school' },
]
export const WHOLE_SCHOOL = 'whole'

export function categoryLabel(key) {
  if (key === WHOLE_SCHOOL) return 'Whole school'
  return CATEGORIES.find((c) => c.key === key)?.label ?? 'Other'
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
  'October', 'November', 'December']
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

/** "2026-10-27" -> a local Date, without the UTC shift `new Date(iso)` gives. */
export function parseDate(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

/** The app's day numbering: 0 = Monday ... 6 = Sunday. */
export function weekdayOf(iso) {
  return (parseDate(iso).getDay() + 6) % 7
}

/** "Monday, 27 October 2026" */
export function formatDate(iso) {
  const d = parseDate(iso)
  return `${WEEKDAYS[weekdayOf(iso)]}, ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

export function todayIso() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** "Mrs. Rao (whole day)" / "Mr. Khan (Period 2, Period 6)" */
export function leaveText(person) {
  return `${person.teacher} (${person.periods == null ? 'whole day' : person.periods.join(', ')})`
}

/**
 * The summary's rows in the groups they're shown in: one group for a part
 * of the school, or, for the whole school, a group per part in the usual
 * order, with grades in no part last.
 */
export function groupRows(summary) {
  if (summary.category != null) {
    return summary.rows.length > 0 ? [{ label: summary.category_label, rows: summary.rows }] : []
  }
  return [...CATEGORIES.map((c) => c.key), null]
    .map((key) => ({ label: categoryLabel(key), rows: summary.rows.filter((r) => (r.category ?? null) === key) }))
    .filter((g) => g.rows.length > 0)
}

/** The summary as a WhatsApp message (*bold* is WhatsApp's own markup). */
export function summaryText(summary) {
  const lines = [`*Substitutions — ${formatDate(summary.date)}*`, summary.category_label]
  if (summary.on_leave.length > 0) {
    lines.push('', `*On leave:* ${summary.on_leave.map(leaveText).join(', ')}`)
  }
  if (summary.rows.length === 0) {
    lines.push('', 'No lessons need cover.')
  }
  for (const group of groupRows(summary)) {
    lines.push('')
    if (summary.category == null) lines.push(`*${group.label}*`)
    for (const r of group.rows) {
      const lesson = [r.period, r.class_group, r.subject].filter(Boolean).join(' · ')
      lines.push(`${lesson}: ${r.absent_teacher} → ${r.substitute ?? '*NOT COVERED*'}`)
    }
  }
  if (summary.uncovered > 0) {
    const n = summary.uncovered
    lines.push('', `⚠️ ${n} period${n === 1 ? '' : 's'} still need${n === 1 ? 's' : ''} cover.`)
  }
  return lines.join('\n')
}

const escapeHtml = (text) =>
  String(text ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

/** A plain page with just the summary, for the browser's print dialog. */
export function summaryHtml(summary, schoolName) {
  const groups = groupRows(summary)
    .map((g) => `
      ${summary.category == null ? `<h2>${escapeHtml(g.label)}</h2>` : ''}
      <table>
        <thead><tr><th>Period</th><th>Class</th><th>Subject</th><th>On leave</th><th>Replaced by</th></tr></thead>
        <tbody>${g.rows.map((r) => `<tr>
          <td>${escapeHtml(r.period)}</td><td>${escapeHtml(r.class_group)}</td><td>${escapeHtml(r.subject)}</td>
          <td>${escapeHtml(r.absent_teacher)}</td>
          <td>${r.substitute ? escapeHtml(r.substitute) : '<strong class="uncovered">Not covered</strong>'}</td>
        </tr>`).join('')}</tbody>
      </table>`)
    .join('')
  const n = summary.uncovered
  return `<!doctype html><html><head><meta charset="utf-8">
<title>Substitutions ${escapeHtml(summary.date)}</title>
<style>
  body { font-family: system-ui, sans-serif; color: #0f172a; margin: 24px; }
  h1 { font-size: 20px; margin: 0; } h2 { font-size: 15px; margin: 18px 0 6px; }
  .sub { color: #475569; margin: 2px 0 14px; } p { font-size: 14px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { border: 1px solid #cbd5e1; padding: 5px 8px; text-align: left; vertical-align: top; }
  th { background: #1e293b; color: white; } .uncovered { color: #b91c1c; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
</style></head><body>
<h1>Substitutions — ${escapeHtml(formatDate(summary.date))}</h1>
<div class="sub">${escapeHtml([schoolName, summary.category_label].filter(Boolean).join(' · '))}</div>
${summary.on_leave.length ? `<p><strong>On leave:</strong> ${escapeHtml(summary.on_leave.map(leaveText).join(', '))}</p>` : ''}
${summary.rows.length ? groups : '<p>No lessons need cover.</p>'}
${n ? `<p class="uncovered"><strong>${n} period${n === 1 ? '' : 's'} still need${n === 1 ? 's' : ''} cover.</strong></p>` : ''}
</body></html>`
}

export function printSummary(summary, schoolName) {
  const win = window.open('', '_blank')
  if (!win) return false
  win.document.write(summaryHtml(summary, schoolName))
  win.document.close()
  win.focus()
  win.print()
  return true
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Older browsers, or no permission: the hidden-textarea way.
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    let ok = false
    try {
      ok = document.execCommand('copy')
    } catch {
      ok = false
    }
    area.remove()
    return ok
  }
}
