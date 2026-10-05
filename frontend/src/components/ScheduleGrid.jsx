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
 * several entries: a lab-batch-split subject produces one per batch at the
 * same class group and period, each with its own teacher and room.
 */
export default function ScheduleGrid({
  days,
  orders,
  periodAt,
  entriesAt,
  editable,
  violatingEntries,
  onDragStart,
  onDragEnd,
  onDrop,
  onToggleLock,
  // Section view names the teacher in each cell; teacher view names the
  // section. Passed rather than branched on inside, so this component has no
  // opinion about which view it is serving.
  secondaryLine,
  showAssistant,
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
                // Lab-batch slots (2+ simultaneous entries) aren't
                // drag/lock-editable in this version — see solver.py's note on
                // locked entries not being honored for batched subjects.
                // Editing one batch out of several needs its own interaction
                // that hasn't been designed yet.
                const isBatched = entries.length > 1
                const singleEntry = entries.length === 1 ? entries[0] : null
                // Locked/unlocked as a light background tint on the whole cell
                // rather than an icon on the entry — red for locked, green for
                // unlocked — so the state reads at a glance across the grid.
                const lockTint = singleEntry
                  ? singleEntry.locked
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
                return (
                  <td
                    key={d}
                    title={broken.length ? broken.map((v) => v.description).join('\n') : undefined}
                    className={`border border-slate-200 px-3 py-2 transition-colors ${
                      editable ? 'align-top' : ''
                    } ${lockTint} ${violationRing}`}
                    onDragOver={editable && !isBatched ? (e) => e.preventDefault() : undefined}
                    onDrop={editable && !isBatched ? () => onDrop(d, order) : undefined}
                  >
                    {!period ? (
                      <span className="text-slate-300">—</span>
                    ) : isBatched ? (
                      <div className="flex flex-col gap-1.5">
                        {entries
                          .slice()
                          .sort((a, b) => (a.lab_batch ?? 0) - (b.lab_batch ?? 0))
                          .map((e) => (
                            <div key={e.id} className="border-l-2 border-slate-200 pl-1.5">
                              <div className="font-medium">
                                {e.subject_name}
                                {e.lab_batch && (
                                  <span className="ml-1 text-xs font-normal text-slate-400">
                                    Batch {e.lab_batch}
                                  </span>
                                )}
                              </div>
                              <div className="text-xs text-slate-500">{secondaryLine(e)}</div>
                              {showAssistant && e.assistant_teacher_name && (
                                <div className="text-xs text-slate-400">
                                  Asst: {e.assistant_teacher_name}
                                </div>
                              )}
                              {e.room_name && (
                                <div className="text-xs text-slate-400">{e.room_name}</div>
                              )}
                            </div>
                          ))}
                      </div>
                    ) : singleEntry ? (
                      <div
                        draggable={editable && !singleEntry.locked}
                        onDragStart={editable ? () => onDragStart(singleEntry) : undefined}
                        onDragEnd={onDragEnd}
                        onClick={editable ? () => onToggleLock(singleEntry) : undefined}
                        title={
                          editable
                            ? singleEntry.locked
                              ? 'Locked — click to unlock (movable, may change on regenerate)'
                              : 'Click to lock in place before regenerating'
                            : singleEntry.locked
                            ? 'Locked in place'
                            : undefined
                        }
                        className={
                          editable ? (singleEntry.locked ? 'cursor-pointer' : 'cursor-move') : ''
                        }
                      >
                        <div className="font-medium">{singleEntry.subject_name}</div>
                        <div className="text-xs text-slate-500">{secondaryLine(singleEntry)}</div>
                        {showAssistant && singleEntry.assistant_teacher_name && (
                          <div className="text-xs text-slate-400">
                            Asst: {singleEntry.assistant_teacher_name}
                          </div>
                        )}
                        {singleEntry.room_name && (
                          <div className="text-xs text-slate-400">{singleEntry.room_name}</div>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-slate-300">Free</span>
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
