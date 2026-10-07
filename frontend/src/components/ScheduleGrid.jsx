const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

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
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-slate-200">
      <table className="min-w-full border-collapse text-sm">
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
                Period {order + 1}
              </td>
              {days.map((d) => {
                const entries = entriesAt(d, order)
                const period = periodAt(d, order)
                const blockId = entries.find((e) => e.elective_block_id != null)?.elective_block_id
                const isBlock = blockId != null
                // A split lab: several batches of one subject at once. Moved as
                // a unit like a block, but not lockable - the solver does not
                // honour locks on batched subjects (see solver.py), so offering
                // one would promise something regenerating would not keep.
                const isBatched = !isBlock && entries.length > 1
                const lockable = entries.length > 0 && !isBatched
                // Any rather than every: a lock set on one option through the
                // edit box still pins the whole slot on the server, which
                // refuses to move a slot with anything locked in it.
                const locked = entries.some((e) => e.locked)
                const canDrag = editable && entries.length > 0 && !locked
                // Locked/unlocked as a light background tint on the whole cell
                // rather than an icon on the entry — red for locked, green for
                // unlocked — so the state reads at a glance across the grid.
                const lockTint = lockable
                  ? locked
                    ? 'bg-red-50 hover:bg-red-100'
                    : 'bg-emerald-50 hover:bg-emerald-100'
                  : isBatched
                  ? 'hover:bg-slate-50'
                  : ''
                // An inset ring rather than a border, so the grid's own lines
                // don't shift and the lock tint stays readable underneath —
                // the two say different things and both need to survive.
                const broken = entries.flatMap((e) => violatingEntries.get(e.id) ?? [])
                const violationRing = broken.length ? 'ring-2 ring-inset ring-amber-400' : ''
                const what = isBlock && entries.length > 1 ? 'the whole block' : isBatched ? 'every batch' : 'it'
                const hint = !editable
                  ? locked
                    ? 'Locked in place'
                    : undefined
                  : locked
                  ? 'Locked — click to unlock (movable, may change on regenerate)'
                  : isBatched
                  ? 'Drag to move every batch together. Split labs can’t be locked yet.'
                  : `Drag to move ${what}, or click to lock ${what} in place before regenerating`
                return (
                  <td
                    key={d}
                    title={broken.length ? broken.map((v) => v.description).join('\n') : undefined}
                    className={`border border-slate-200 px-3 py-2 transition-colors ${
                      editable ? 'align-top' : ''
                    } ${lockTint} ${violationRing}`}
                    onDragOver={editable && period ? (e) => e.preventDefault() : undefined}
                    onDrop={editable && period ? () => onDrop(d, order) : undefined}
                  >
                    {!period ? (
                      <span className="text-slate-300">—</span>
                    ) : entries.length === 0 ? (
                      <span className="text-xs text-slate-300">Free</span>
                    ) : (
                      <div
                        draggable={canDrag}
                        onDragStart={canDrag ? () => onDragStart(d, order, entries) : undefined}
                        onDragEnd={onDragEnd}
                        onClick={editable && lockable ? () => onToggleLock(entries) : undefined}
                        title={hint}
                        className={
                          editable ? (canDrag ? 'cursor-move' : lockable ? 'cursor-pointer' : '') : ''
                        }
                      >
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
      <div className="font-medium">
        {entry.subject_name}
        {entry.lab_batch && (
          <span className="ml-1 text-xs font-normal text-slate-400">Batch {entry.lab_batch}</span>
        )}
        {/* A teacher's own timetable shows only their option of a block, so
            the block is named alongside it - otherwise it reads as an
            ordinary lesson that could be moved on its own. */}
        {blockName && <span className="ml-1 text-xs font-normal text-slate-400">{blockName}</span>}
      </div>
      <div className="text-xs text-slate-500">{secondaryLine(entry)}</div>
      {showAssistant && entry.assistant_teacher_name && (
        <div className="text-xs text-slate-400">Asst: {entry.assistant_teacher_name}</div>
      )}
      {entry.room_name && <div className="text-xs text-slate-400">{entry.room_name}</div>}
    </>
  )
}
