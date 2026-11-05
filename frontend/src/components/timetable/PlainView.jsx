import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api'
import { combinationsFor, keeps, MAX_COMBINATIONS } from '../../studentCombinations'
import WeekGrid from './WeekGrid'
import { sectionShort, sectionTitle } from './lessonLogic'

/**
 * Reading the timetable: every section, teacher or room as one large grid, in a
 * list that scrolls. Nothing here changes the timetable except freezing a
 * section. A section with elective blocks can also show what one student's
 * subject combination attends, and export those timetables.
 */
export default function PlainView({
  kind, id, onKind, onId, sections, sectionsById, teachers, rooms, entries, layout, timetableId, watermark,
  electiveBlocks, subjectName, frozenById, canFreeze, freezing, onFreeze, exporting, onExport, onError, printSignal,
}) {
  const listRef = useRef(null)
  const options = useMemo(() => {
    if (kind === 'section') return sections.map((s) => ({ id: s.id, label: sectionTitle(s) }))
    if (kind === 'teacher') return teachers.map((t) => ({ id: t.id, label: t.name }))
    return rooms.map((r) => ({ id: r.id, label: r.name }))
  }, [kind, sections, teachers, rooms])
  const position = options.findIndex((o) => o.id === id)

  const grouped = useMemo(() => {
    const map = new Map(options.map((o) => [o.id, []]))
    for (const e of entries) {
      if (kind === 'section') map.get(e.class_group_id)?.push(e)
      else if (kind === 'room') map.get(e.room_id)?.push(e)
      else {
        map.get(e.teacher_id)?.push(e)
        if (e.assistant_teacher_id !== e.teacher_id) map.get(e.assistant_teacher_id)?.push(e)
      }
    }
    return map
  }, [entries, kind, options])

  const ignoreUntil = useRef(0)
  const scrollTo = (target, behavior) => {
    const box = listRef.current
    const el = box?.querySelector(`[data-plain="${target}"]`)
    if (!el) return
    ignoreUntil.current = Date.now() + (behavior === 'smooth' ? 700 : 100)
    box.scrollTo?.({ top: el.offsetTop - box.offsetTop - 2, behavior })
  }
  // Opening a list, or arriving from the sidebar, lands on the chosen timetable.
  const scrolledFor = useRef(null)
  useEffect(() => {
    const signature = `${kind}:${id}`
    if (scrolledFor.current === signature) return
    scrolledFor.current = signature
    scrollTo(id, 'auto')
  }, [kind, id])

  const timer = useRef(null)
  function onScroll() {
    if (Date.now() < ignoreUntil.current) return
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      const box = listRef.current
      if (!box) return
      const b = box.getBoundingClientRect()
      let best = null
      let gap = Infinity
      for (const el of box.children) {
        if (!el.dataset.plain) continue
        const r = el.getBoundingClientRect()
        const g = Math.abs((r.top + r.bottom) / 2 - (b.top + b.bottom) / 2)
        if (g < gap) { gap = g; best = Number(el.dataset.plain) }
      }
      if (best != null && best !== id) {
        scrolledFor.current = `${kind}:${best}`
        onId(best)
      }
    }, 120)
  }
  useEffect(() => () => clearTimeout(timer.current), [])

  function choose(target) {
    scrolledFor.current = `${kind}:${target}`
    onId(target)
    scrollTo(target, 'smooth')
  }
  const step = (by) => options.length && choose(options[(position + by + options.length) % options.length].id)

  function print() {
    const box = listRef.current?.querySelector(`[data-plain="${id}"]`)
    if (!box) return
    box.dataset.printing = '1'
    window.print()
    delete box.dataset.printing
  }
  const seenPrint = useRef(printSignal)
  useEffect(() => {
    if (seenPrint.current === printSignal) return
    seenPrint.current = printSignal
    print()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [printSignal])

  return (
    <div className="tw-plainwrap">
      <div className="tw-plainhead">
        <div className="tw-seg">
          {[['section', 'Section'], ['teacher', 'Teacher'], ['room', 'Room']].map(([k, label]) => (
            <button key={k} type="button" className={k === kind ? 'tw-on' : ''} onClick={() => onKind(k)}>{label}</button>
          ))}
        </div>
        <select className="tw-btn" aria-label="Choose timetable" value={id ?? ''} onChange={(e) => choose(Number(e.target.value))}>
          {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>
        <button type="button" className="tw-btn" onClick={() => step(-1)}>‹ Prev</button>
        <button type="button" className="tw-btn" onClick={() => step(1)}>Next ›</button>
        <span className="tw-count">{options.length ? `${position + 1} of ${options.length}` : ''}</span>
        <span className="tw-spacer" />
        <button type="button" className="tw-btn" onClick={print}>Print</button>
        <button type="button" className="tw-btn" disabled={!!exporting} onClick={() => onExport('pdf')}>
          {exporting === 'pdf' ? 'Preparing…' : 'PDF'}
        </button>
      </div>
      <div className="tw-plain" ref={listRef} onScroll={onScroll}>
        {options.length === 0 && <p className="tw-count" style={{ textAlign: 'center' }}>Nothing to show here yet.</p>}
        {options.map((o) => (
          kind === 'section' ? (
            <SectionBox
              key={o.id}
              section={sectionsById.get(o.id)}
              label={o.label}
              entries={grouped.get(o.id)}
              layout={layout}
              sectionsById={sectionsById}
              timetableId={timetableId}
              watermark={watermark}
              combinations={combinationsFor(electiveBlocks, o.id, subjectName)}
              frozen={frozenById.get(o.id) ?? null}
              canFreeze={canFreeze}
              freezing={freezing}
              onFreeze={onFreeze}
              onError={onError}
              classTeacher={teachers.find((t) => t.id === sectionsById.get(o.id)?.class_teacher_id)?.name}
            />
          ) : (
            <article key={o.id} className="tw-plainbox" data-plain={o.id}>
              <div className="tw-plaintitle"><h2>{o.label}</h2></div>
              <WeekGrid
                kind={kind}
                plain
                entries={grouped.get(o.id)}
                layout={layout}
                sectionsById={sectionsById}
                owner={kind === 'teacher' ? ownerFor(o.id, sections) : undefined}
              />
            </article>
          )
        ))}
      </div>
    </div>
  )
}

const ownerFor = (teacherId, sections) => ({
  ownSections: sections.filter((s) => s.class_teacher_id === teacherId).map(sectionShort).join(', '),
})

function SectionBox({
  section, label, entries, layout, sectionsById, timetableId, watermark, combinations, frozen, canFreeze, freezing, onFreeze, onError, classTeacher,
}) {
  const [student, setStudent] = useState('')
  const [exporting, setExporting] = useState(null)
  const combination = student === '' || !combinations ? null : combinations[Number(student)] ?? null
  const shown = useMemo(() => (combination ? entries.filter((e) => keeps(combination, e)) : entries), [entries, combination])
  const owner = useMemo(() => ({ classTeacher, grade: section.grade }), [classTeacher, section.grade])

  async function exportStudents(format) {
    if (exporting) return
    setExporting(format)
    try {
      await api.downloadStudentTimetables(
        timetableId, format, section.id, section.grade ? `${section.grade} ${section.name}` : section.name, { watermark },
      )
    } catch (err) {
      onError(err.message)
    } finally {
      setExporting(null)
    }
  }

  return (
    <article className="tw-plainbox" data-plain={section.id} aria-label={label}>
      <div className="tw-plaintitle">
        <h2>{label}</h2>
        {frozen && <span title="Frozen">❄ Frozen</span>}
        <span className="tw-spacer" />
        {combinations === null && (
          <small>This section&rsquo;s blocks allow more than {MAX_COMBINATIONS} subject combinations. Check them for a mistake.</small>
        )}
        {combinations?.length > 0 && (
          <>
            <select className="tw-btn" aria-label={`Whose timetable to show for ${label}`} value={student} onChange={(e) => setStudent(e.target.value)}>
              <option value="">Whole section</option>
              {combinations.map((c, i) => <option key={c.label + i} value={i}>{i + 1}. {c.label}</option>)}
            </select>
            <small>Student timetables:</small>
            <button type="button" className="tw-btn" disabled={!!exporting} onClick={() => exportStudents('xlsx')}>
              {exporting === 'xlsx' ? 'Preparing…' : 'Excel'}
            </button>
            <button type="button" className="tw-btn" disabled={!!exporting} onClick={() => exportStudents('pdf')}>
              {exporting === 'pdf' ? 'Preparing…' : 'PDF'}
            </button>
          </>
        )}
        {canFreeze && (
          <button
            type="button"
            className="tw-btn"
            disabled={freezing}
            onClick={() => onFreeze([section.id], !frozen)}
            title={frozen ? 'Let the next Generate change this section again' : 'Keep this section exactly as it is when generating again'}
          >
            {frozen ? 'Unfreeze' : 'Freeze'}
          </button>
        )}
      </div>
      {frozen?.stale_reason && <p className="tw-warnline" style={{ marginBottom: 8 }}>{frozen.stale_reason}</p>}
      <WeekGrid kind="section" plain entries={shown} layout={layout} sectionsById={sectionsById} owner={owner} />
    </article>
  )
}
