import { useState } from 'react'

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

// While dragging: where the slot can go. Replaces the lock tint for the
// length of the drag, since "can it go here" is the question then.
const DROP_TONE = {
  ok: 'bg-emerald-100 ring-2 ring-inset ring-emerald-400',
  warn: 'bg-amber-100 ring-2 ring-inset ring-amber-400',
  blocked: 'bg-red-100 ring-2 ring-inset ring-red-400',
}

const SPECIAL_TONE = {
  muted: 'bg-slate-50 text-slate-400',
  class_teacher: 'bg-violet-50 text-violet-800',
  zero: 'bg-emerald-50 text-emerald-800',
  warn: 'bg-amber-50 text-amber-800',
}

/**
 * One week's grid: periods down, days across.
 *
 * Pulled out of TimetableTab so it can be rendered once per section and
 * stacked, which is what the by-section view now does. It was inline there
 * while only one section was ever on screen; repeating it meant either
 * duplicating a hundred and fifty lines of cell rendering or extracting it,
 * and two copies of the drag, lock and violation handling would not have
 * stayed identical for long.
 *
 * Takes a slot lookup rather than a flat entry list because a slot can hold
 * several entries: a lab-batch-split subject produces one per batch, and an
 * elective block one per option, all at the same class group and period.
 *
 * The cell is the unit of editing, not the entry. Dragging a cell moves
 * everything in it, and clicking it locks everything in it - see move-slot and
 * lock-slot in backend/app/routers/timetables.py. A block's options always run
 * together, so moving or locking one of them alone is not a thing that can
 * mean anything.
 */
export default function ScheduleGrid({
  days,
  orders,
  periodAt,
  entriesAt,
  editable,
  violatingEntries,
  // (day, order, entries) - the caller remembers where the drag began.
  onDragStart,
  onDragEnd,
  onDrop,
  // (entries) - every entry in the clicked cell.
  onToggleLock,
  // Section view names the teacher in each cell; teacher view names the
  // section. Passed rather than branched on inside, so this component has no
  // opinion about which view it is serving.
  secondaryLine,
  showAssistant,
  // A student's own timetable shows the one option they attend; calling that
  // cell "Block 1" would read as if they still had a choice to make.
  showBlockName = true,
  // "Period 3" for a lesson row, the slot's own name for a break or the class
  // teacher period. Rows are slots in the day, and only lessons are numbered.
  rowLabel = (order) => `Period ${order + 1}`,
  // (day, order) -> { text, tone } for a slot that isn't an ordinary lesson
  // here - a break, the class teacher period, a zero period - or null. Such a
  // slot shows its text and takes no drops.
  specialCell = () => null,
  // The whole section is frozen: nothing in it moves or unlocks until it is
  // unfrozen, so its slots show neither red nor green.
  sectionFrozen = false,
  // While a slot is dragged: Map(periodId -> { status: ok|warn|blocked,
  // reason }) for every period it could be dropped in (see move-targets in
  // backend/app/routers/timetables.py), or null. Colours each cell green,
  // amber or red, and the cell under the pointer says why.
  dropTargets = null,
  dragFromPeriodId = null,
}) {
  // The cell being dragged over - a title tooltip doesn't show mid-drag, so
  // the reason is written into the cell itself.
  const [over, setOver] = useState(null)
  return (
    <div className="overflow-x-auto rounded-md border border-slate-200">
      <table className="min-w-full border-collapse text-[15px] leading-snug">
        <thead>
          <tr className="bg-slate-50">
            <th className="border border-slate-200 px-3 py-2 text-left font-medium">Period</th>
            {days.map((d) => (
              <th key={d} className="border border-slate-200 px-3 py-2 text-left font-medium">
                {DAY_NAMES[d]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order}>
              <td className="border border-slate-200 px-3 py-2 font-medium text-slate-500">
                {rowLabel(order)}
              </td>
              {days.map((d) => {
                const entries = entriesAt(d, order)
                const period = periodAt(d, order)
                const special = period ? specialCell(d, order) : null
                if (special) {
                  return (
                    <td
                      key={d}
                      className={`border border-slate-200 px-3 py-2 text-sm ${SPECIAL_TONE[special.tone] ?? SPECIAL_TONE.muted}`}
                    >
                      {special.text}
                    </td>
                  )
                }
                const blockId = entries.find((e) => e.elective_block_id != null)?.elective_block_id
                const isBlock = blockId != null
                // A split lab: several batches of one subject at once. Moved as
                // a unit like a block, but not lockable - the solver does not
                // honour locks on batched subjects (see solver.py), so offering
                // one would promise something regenerating would not keep.
                const isBatched = !isBlock && entries.length > 1
                // Kept in place by a frozen subject: not dragged, not locked.
                const subjectFrozen = entries.find((e) => e.subject_frozen)
                const lockable = entries.length > 0 && !isBatched && !subjectFrozen
                // Any rather than every: a lock set on one option through the
                // edit box still pins the whole slot on the server, which
                // refuses to move a slot with anything locked in it.
                const locked = entries.some((e) => e.locked)
                const canDrag = editable && entries.length > 0 && !locked && !subjectFrozen
                // Locked/unlocked as a light background tint on the whole cell
                // rather than an icon on the entry — red for locked, green for
                // unlocked — so the state reads at a glance across the grid.
                const lockTint = sectionFrozen
                  ? 'bg-slate-50'
                  : lockable
                  ? locked
                    ? 'bg-red-50 hover:bg-red-100'
                    : 'bg-emerald-50 hover:bg-emerald-100'
                  : subjectFrozen
                  ? 'bg-sky-50'
                  : isBatched
                  ? 'hover:bg-slate-50'
                  : ''
                // An inset ring rather than a border, so the grid's own lines
                // don't shift and the lock tint stays readable underneath —
                // the two say different things and both need to survive.
                const target = dropTargets && period ? dropTargets.get(period.id) : null
                const dragTint = target ? DROP_TONE[target.status] ?? '' : ''
                const isDragOrigin = dropTargets && period && period.id === dragFromPeriodId
                const broken = entries.flatMap((e) => violatingEntries.get(e.id) ?? [])
                const violationRing = broken.length ? 'ring-2 ring-inset ring-amber-400' : ''
                const what = isBlock && entries.length > 1 ? 'the whole block' : isBatched ? 'every batch' : 'it'
                const hint = sectionFrozen
                  ? 'This section is frozen, so nothing here moves or unlocks. Unfreeze it to change it.'
                  : subjectFrozen
                  ? `${subjectFrozen.subject_name} is frozen, so this stays where it is`
                  : !editable
                  ? locked
                    ? 'Locked in place'
                    : undefined
                  : locked
                  ? 'Locked. Click to unlock (movable, may change on regenerate)'
                  : isBatched
                  ? 'Drag to move every batch together. Split labs can’t be locked yet.'
                  : `Drag to move ${what}, or click to lock ${what} in place before regenerating`
                return (
                  <td
                    key={d}
                    data-drop={target?.status}
                    title={
                      target?.reason ?? (broken.length ? broken.map((v) => v.description).join('\n') : undefined)
                    }
                    className={`relative border border-slate-200 px-3 py-2 transition-colors ${
                      editable ? 'align-top' : ''
                    } ${editable && lockable ? 'cursor-pointer' : ''} ${
                      dragTint || `${lockTint} ${violationRing}`
                    } ${isDragOrigin ? 'opacity-50' : ''}`}
                    // The whole coloured cell toggles the lock, not just the
                    // words in it - clicking the empty part of a red cell used
                    // to do nothing at all.
                    onClick={editable && lockable ? () => onToggleLock(entries) : undefined}
                    onDragOver={editable && period ? (e) => e.preventDefault() : undefined}
                    onDragEnter={editable && period ? () => setOver(period.id) : undefined}
                    onDrop={
                      editable && period
                        ? () => {
                            setOver(null)
                            onDrop(d, order)
                          }
                        : undefined
                    }
                  >
                    {target?.reason && over === period.id && (
                      <div
                        role="status"
                        className={`pointer-events-none absolute inset-x-0 bottom-0 z-10 px-1.5 py-1 text-[11px] font-medium leading-tight ${
                          target.status === 'blocked' ? 'bg-red-600 text-white' : 'bg-amber-500 text-white'
                        }`}
                      >
                        {target.reason}
                      </div>
                    )}
                    {!period ? (
                      <span className="text-slate-300">-</span>
                    ) : entries.length === 0 ? (
                      <span className="text-sm text-slate-300">Free</span>
                    ) : (
                      <div
                        draggable={canDrag}
                        onDragStart={canDrag ? () => onDragStart(d, order, entries) : undefined}
                        onDragEnd={onDragEnd}
                        title={hint}
                        className={
                          editable ? (canDrag ? 'cursor-move' : lockable ? 'cursor-pointer' : '') : ''
                        }
                      >
                        {subjectFrozen && (
                          <div className="text-[11px] font-medium text-sky-700">❄ Frozen</div>
                        )}
                        {entries.length === 1 ? (
                          <Lesson
                            entry={entries[0]}
                            secondaryLine={secondaryLine}
                            showAssistant={showAssistant}
                            blockName={showBlockName ? entries[0].elective_block_name : null}
                          />
                        ) : (
                          <div className="flex flex-col gap-1.5">
                            {isBlock && showBlockName && (
                              <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
                                {entries[0].elective_block_name ?? 'Elective block'}
                              </div>
                            )}
                            {sortedForCell(entries, isBlock).map((e) => (
                              <div key={e.id} className="border-l-2 border-slate-200 pl-1.5">
                                <Lesson entry={e} secondaryLine={secondaryLine} showAssistant={showAssistant} />
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Fixed order so a cell's contents don't reshuffle between renders: batches by
// number, a block's options by subject.
function sortedForCell(entries, isBlock) {
  return entries
    .slice()
    .sort((a, b) =>
      isBlock
        ? (a.subject_name ?? '').localeCompare(b.subject_name ?? '')
        : (a.lab_batch ?? 0) - (b.lab_batch ?? 0),
    )
}

function Lesson({ entry, secondaryLine, showAssistant, blockName = null }) {
  return (
    <>
      <div className="break-words text-base font-medium">
        {entry.subject_name}
        {entry.elective_option_label && (
          <span className="ml-1 text-xs font-normal text-slate-400">{entry.elective_option_label}</span>
        )}
        {entry.lab_batch && (
          <span className="ml-1 text-xs font-normal text-slate-400">Batch {entry.lab_batch}</span>
        )}
        {/* A teacher's own timetable shows only their option of a block, so
            the block is named alongside it - otherwise it reads as an
            ordinary lesson that could be moved on its own. */}
        {blockName && <span className="ml-1 text-xs font-normal text-slate-400">{blockName}</span>}
      </div>
      <div className="break-words text-sm text-slate-600">{secondaryLine(entry)}</div>
      {/* A class pooled from several sections, seen from one of them. */}
      {entry.shared_with_names?.length > 0 && !entry.class_group_ids && (
        <div className="text-[13px] text-violet-700">with {entry.shared_with_names.join(', ')}</div>
      )}
      {showAssistant && entry.assistant_teacher_name && (
        <div className="text-[13px] text-slate-500">Asst: {entry.assistant_teacher_name}</div>
      )}
      {entry.room_name && <div className="text-[13px] text-slate-500">{entry.room_name}</div>}
    </>
  )
}
