import { memo } from 'react'
import { teacherLessons } from '../../electiveSections'
import { sectionShort } from './lessonLogic'

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/**
 * One week: periods down, days across. Rendered once per teacher, section and
 * room, so it only re-renders when something in its own week changed - see
 * sameWeek below. Drag colours aren't props: Workspace sets `data-hue` on the
 * cells directly, which is what makes picking a lesson up instant however many
 * grids the school has.
 */
function WeekGrid({ kind, entries, layout, sectionsById, mine = '', broken = '', owner, plain = false }) {
  const { days, rows, at } = layout
  const byPeriod = new Map()
  for (const e of entries) {
    if (!byPeriod.has(e.period_id)) byPeriod.set(e.period_id, [])
    byPeriod.get(e.period_id).push(e)
  }
  const mineIds = new Set(mine.split(',').filter(Boolean).map(Number))
  const brokenIds = new Set(broken.split(',').filter(Boolean).map(Number))

  return (
    <table className="tw-grid">
      <thead>
        <tr>
          <th className="tw-p" aria-label="Period" />
          {days.map((d) => <th key={d}>{DAY_NAMES[d]}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) =>
          row.band ? (
            <tr key={row.order} className="tw-band">
              <td />
              <td colSpan={days.length}>{bandText(row, kind, owner)}</td>
            </tr>
          ) : (
            <tr key={row.order}>
              <td className="tw-p">{row.label}</td>
              {days.map((d) => {
                const period = at(d, row.order)
                if (!period) return <td key={d} className="tw-cell tw-none" />
                const here = byPeriod.get(period.id) ?? []
                const special = here.length === 0 ? cellSpecial(period, kind, owner) : null
                return (
                  <td
                    key={d}
                    className={`tw-cell${special ? ' tw-special' : ''}`}
                    data-pid={period.id}
                    data-empty={here.length === 0 ? '1' : undefined}
                  >
                    {special ?? (here.length > 0 && (
                      <Lesson kind={kind} entries={here} sectionsById={sectionsById} mineIds={mineIds} brokenIds={brokenIds} plain={plain} />
                    ))}
                  </td>
                )
              })}
            </tr>
          ),
        )}
      </tbody>
    </table>
  )
}

function bandText(row, kind, owner) {
  if (row.kind !== 'class_teacher') return row.label
  if (kind === 'section') return owner?.classTeacher ? `Class teacher: ${owner.classTeacher}` : 'Class teacher'
  if (kind === 'teacher' && owner?.ownSections) return `Class teacher: ${owner.ownSections}`
  return 'Class teacher'
}

function cellSpecial(period, kind, owner) {
  if (kind !== 'section') return null
  const grade = owner?.grade
  if (period.zero_all || (grade != null && (period.zero_grades ?? []).includes(grade))) return 'Zero period'
  if (grade != null && (period.off_grades ?? []).includes(grade)) return 'No class'
  return null
}

function Lesson({ kind, entries, sectionsById, mineIds, brokenIds, plain }) {
  const shown = kind === 'teacher' ? teacherLessons(entries) : entries
  const first = shown[0]
  const isBlock = first.elective_block_id != null
  const anyMine = entries.some((e) => mineIds.has(e.id))
  const isBroken = entries.some((e) => brokenIds.has(e.id))
  const frozen = entries.some((e) => e.locked || e.subject_frozen)
  const sectionsText = (e) => (e.class_group_ids ?? [e.class_group_id]).map((id) => sectionShort(sectionsById.get(id))).join(', ')
  const batches = !isBlock && entries.length > 1

  let top = first.subject_name
  let bottom
  if (kind === 'teacher') {
    bottom = sectionsText(first)
    if (first.room_name) bottom += ` · ${first.room_name.replace(/ Lab$/, '')}`
    if (first.lab_batch) top = `${first.subject_name} B${first.lab_batch}`
  } else if (kind === 'section') {
    if (isBlock && entries.length > 1) {
      top = first.elective_block_name ?? 'Elective block'
      bottom = `${entries.length} teachers`
    } else if (batches) {
      top = `${first.subject_name} (${entries.length} batches)`
      bottom = entries.map((e) => e.teacher_name ?? 'No teacher').join(', ')
    } else {
      bottom = first.teacher_name ?? 'No teacher yet'
    }
  } else {
    bottom = `${sectionShort(sectionsById.get(first.class_group_id))} · ${first.teacher_name ?? 'No teacher yet'}`
  }
  if (plain && kind === 'section' && isBlock && entries.length > 1) {
    bottom = entries.map((e) => `${e.subject_name}${e.teacher_name ? ` (${e.teacher_name})` : ''}`).join(', ')
  }
  const title = entries
    .map((e) => [e.subject_name, sectionShort(sectionsById.get(e.class_group_id)), e.teacher_name, e.room_name].filter(Boolean).join(', '))
    .join('\n')

  return (
    <div
      className={`tw-lesson${anyMine ? ' tw-mine' : ''}${isBroken ? ' tw-broken' : ''}`}
      data-section={first.class_group_id}
      data-period={first.period_id}
      title={title}
    >
      <b>{top}</b>
      <span>{bottom}</span>
      {plain && first.assistant_teacher_name && <span>Asst: {first.assistant_teacher_name}</span>}
      {plain && first.room_name && kind !== 'room' && <span>{first.room_name}</span>}
      {isBroken ? <i className="tw-mark tw-mark-warn">!</i> : frozen ? <i className="tw-mark">❄</i> : null}
    </div>
  )
}

/** A week only changes when its own lessons do. */
function sameWeek(a, b) {
  if (a.layout !== b.layout || a.mine !== b.mine || a.broken !== b.broken || a.kind !== b.kind || a.plain !== b.plain) return false
  if (a.sectionsById !== b.sectionsById) return false
  if (a.owner?.classTeacher !== b.owner?.classTeacher || a.owner?.ownSections !== b.owner?.ownSections || a.owner?.grade !== b.owner?.grade) return false
  if (a.entries.length !== b.entries.length) return false
  return a.entries.every((e, i) => e === b.entries[i])
}

export default memo(WeekGrid, sameWeek)
