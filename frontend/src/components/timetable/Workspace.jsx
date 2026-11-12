import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import WeekGrid from './WeekGrid'
import {
  buildIndex, cantMoveReason, cardState, judgeCard, judgeSlot, lessonsForTeacher, qualificationText, sectionShort,
  sectionTitle, slotEntries, teachersOfLesson,
} from './lessonLogic'

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const MOVE_BEFORE_DRAG = 5
// A cell's data-state while a lesson is held over it (read by the automated demo).
const HELD_STATE = { ok: 'free', warn: 'rule', bad: 'taken' }
const restingState = (cell) => (cell.dataset.empty ? 'empty' : 'filled')
const smooth = () => (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth')

/**
 * Building the timetable: one teacher's week in the middle of the left column,
 * the class timetables to the right, and below them the lessons this teacher
 * can take, as cards to drag onto a slot.
 *
 * A drag never goes through React. Picking a lesson up sets `data-hue` on the
 * cells of the grids involved, and moving the pointer only moves the chip and
 * rewrites the reason line. Nothing re-renders until the drop, so it stays
 * instant however many grids the school has. The drop itself updates the
 * timetable straight away and the server is told afterwards (useTimetableEdits).
 */
export default function Workspace({
  teachers, teacherId, onSelectTeacher, sections, sectionsById, subjects, lessons, entries, layout, periodsById,
  forecast, frozenSections, brokenIds, edits, toast, onFindAWay, flashEntryId,
}) {
  const rootRef = useRef(null)
  const listRef = useRef(null)
  const stripRef = useRef(null)
  const [search, setSearch] = useState('')
  const [pop, setPop] = useState(null)

  const teachersById = useMemo(() => new Map(teachers.map((t) => [t.id, t])), [teachers])
  const sectionOrder = useMemo(() => new Map(sections.map((s, i) => [s.id, i])), [sections])
  const index = useMemo(() => buildIndex(entries), [entries])

  // What a drag reads: always the latest, without the pointer handlers being
  // rebuilt or a re-render being needed to see it.
  const live = useRef({})
  live.current = {
    teacherId, entries, index, forecast, frozen: frozenSections, sections: sectionsById, teachers: teachersById,
    lessons, periodsById, edits, toast, onFindAWay, sectionOrder,
  }

  const byTeacher = useMemo(() => {
    const map = new Map(teachers.map((t) => [t.id, []]))
    for (const e of entries) {
      map.get(e.teacher_id)?.push(e)
      if (e.assistant_teacher_id !== e.teacher_id) map.get(e.assistant_teacher_id)?.push(e)
    }
    return map
  }, [entries, teachers])
  const bySection = useMemo(() => {
    const map = new Map(sections.map((s) => [s.id, []]))
    for (const e of entries) map.get(e.class_group_id)?.push(e)
    return map
  }, [entries, sections])
  const brokenFor = (list) => list.filter((e) => brokenIds.has(e.id)).map((e) => e.id).join(',')

  const cards = useMemo(() => lessonsForTeacher(lessons, teacherId, sectionOrder), [lessons, teacherId, sectionOrder])
  const teacher = teachersById.get(teacherId)
  const position = teachers.findIndex((t) => t.id === teacherId)

  /* ---------- Scrolling and choosing a teacher ---------- */
  const ignoreScrollUntil = useRef(0)
  const centreOn = useCallback((id, behavior) => {
    const box = listRef.current
    const el = box?.querySelector(`[data-teacher="${id}"]`)
    if (!el) return
    ignoreScrollUntil.current = Date.now() + (behavior === 'smooth' ? 700 : 150)
    box.scrollTo?.({ top: el.offsetTop - box.offsetTop - (box.clientHeight - el.offsetHeight) / 2, behavior })
  }, [])
  const showFirstSection = useCallback((id, behavior) => {
    const order = live.current.sectionOrder
    const first = lessonsForTeacher(live.current.lessons, id, order)[0]
    const sectionId = first ? first.section_ids.map((s) => [order.get(s), s]).sort((a, b) => a[0] - b[0])[0][1] : null
    const el = sectionId == null ? stripRef.current?.firstElementChild : stripRef.current?.querySelector(`[data-section-board="${sectionId}"]`)
    if (el) stripRef.current.scrollTo?.({ left: el.offsetLeft, behavior })
  }, [])

  const choose = useCallback((id, { scrollList = true } = {}) => {
    setPop(null)
    setSearch('')
    onSelectTeacher(id)
    if (scrollList) centreOn(id, smooth())
    showFirstSection(id, smooth())
  }, [centreOn, onSelectTeacher, showFirstSection])

  // The grid sits in the middle of its column: room above the first teacher
  // and below the last, so every teacher can be centred.
  const padFor = useCallback(() => {
    const box = listRef.current
    const el = box?.querySelector(`[data-teacher="${live.current.teacherId}"]`)
    if (box && el) box.style.setProperty('--tw-pad', `${Math.max(0, (box.clientHeight - el.offsetHeight) / 2 - 12)}px`)
  }, [])
  const centredOnce = useRef(false)
  useLayoutEffect(() => {
    padFor()
    if (!centredOnce.current && teacherId != null) {
      centredOnce.current = true
      centreOn(teacherId, 'auto')
      showFirstSection(teacherId, 'auto')
    }
  }, [padFor, centreOn, showFirstSection, teacherId])
  useEffect(() => {
    window.addEventListener('resize', padFor)
    return () => window.removeEventListener('resize', padFor)
  }, [padFor])

  const scrollTimer = useRef(null)
  function onListScroll() {
    if (Date.now() < ignoreScrollUntil.current || drag.current) return
    clearTimeout(scrollTimer.current)
    scrollTimer.current = setTimeout(() => {
      const box = listRef.current
      if (!box || drag.current) return
      const b = box.getBoundingClientRect()
      let best = null
      let gap = Infinity
      for (const el of box.querySelectorAll('[data-teacher]')) {
        const r = el.getBoundingClientRect()
        const g = Math.abs((r.top + r.bottom) / 2 - (b.top + b.bottom) / 2)
        if (g < gap) { gap = g; best = Number(el.dataset.teacher) }
      }
      if (best != null && best !== live.current.teacherId) choose(best, { scrollList: false })
    }, 150)
  }
  useEffect(() => () => clearTimeout(scrollTimer.current), [])

  /* ---------- The drag ---------- */
  const drag = useRef(null)
  const press = useRef(null)

  const context = () => live.current
  const judge = (d, period) => (d.lesson
    ? judgeCard(d.lesson, d.teacherIds, period, context())
    : judgeSlot(d.slot, d.fromPeriodId, period, context()))

  function targetGrids(d) {
    const root = rootRef.current
    if (!root) return []
    const grids = [root.querySelector(`[data-teacher="${live.current.teacherId}"]`)]
    for (const sid of d.sectionIds) grids.push(root.querySelector(`[data-section-board="${sid}"]`))
    return grids.filter(Boolean)
  }

  function hueGrids(d) {
    d.verdicts = new Map()
    for (const grid of targetGrids(d)) {
      for (const cell of grid.querySelectorAll('td[data-pid]')) {
        const pid = Number(cell.dataset.pid)
        let v = d.verdicts.get(pid)
        if (!v) {
          const period = live.current.periodsById.get(pid)
          v = period ? judge(d, period) : { kind: 'bad', text: 'Nothing can be scheduled there' }
          d.verdicts.set(pid, v)
        }
        cell.dataset.hue = v.kind
        cell.dataset.state = HELD_STATE[v.kind] ?? restingState(cell)
      }
    }
  }

  function clearHues() {
    const root = rootRef.current
    if (!root) return
    for (const cell of root.querySelectorAll('td[data-hue]')) {
      delete cell.dataset.hue
      delete cell.dataset.hot
      cell.dataset.state = restingState(cell)
    }
    for (const el of root.querySelectorAll('[data-target]')) delete el.dataset.target
    for (const el of root.querySelectorAll('[data-picked]')) delete el.dataset.picked
    delete root.dataset.dragging
    delete root.dataset.moving
    const reason = root.querySelector('.tw-reason')
    if (reason) reason.textContent = ''
  }

  // Where the droppable cells are, measured once rather than on every move:
  // asking the browser what's under the pointer makes it recheck the page, which
  // is what a slow laptop feels as lag. Measured again only after a scroll.
  function measure(d) {
    const root = rootRef.current
    const clips = (el) => el?.getBoundingClientRect()
    const listClip = clips(listRef.current)
    const stripClip = clips(stripRef.current)
    d.cells = []
    for (const grid of targetGrids(d)) {
      const clip = grid.dataset.teacher ? listClip : stripClip
      for (const cell of grid.querySelectorAll('td[data-pid]')) {
        const r = cell.getBoundingClientRect()
        const left = Math.max(r.left, clip.left)
        const right = Math.min(r.right, clip.right)
        const top = Math.max(r.top, clip.top)
        const bottom = Math.min(r.bottom, clip.bottom)
        if (left < right && top < bottom) d.cells.push({ cell, left, right, top, bottom })
      }
    }
    d.trash = root.querySelector('[data-trash]')?.getBoundingClientRect() ?? null
    d.cover = document.querySelector('.tw-drawer')?.getBoundingClientRect() ?? null
    d.stale = false
  }

  function cellAt(d, x, y) {
    if (d.cover && x >= d.cover.left) return null
    for (const c of d.cells) {
      if (x >= c.left && x < c.right && y >= c.top && y < c.bottom) return c.cell
    }
    return null
  }
  const inTrash = (d, x, y) => !!d.trash && !d.cover && x >= d.trash.left && x < d.trash.right && y >= d.trash.top && y < d.trash.bottom

  function showHover(d) {
    const { x, y } = d
    if (d.stale) measure(d)
    const ghost = d.ghost
    // Its size is measured once: reading it on every move would make the
    // browser lay the whole page out again each time.
    ghost.style.transform = `translate3d(${x - d.ghostW / 2}px, ${y - d.ghostH / 2}px, 0)`
    const cell = cellAt(d, x, y)
    if (d.hot !== cell) {
      if (d.hot) delete d.hot.dataset.hot
      if (cell) cell.dataset.hot = '1'
      d.hot = cell
    }
    let kind = ''
    let text = 'Drop on a highlighted slot'
    if (cell) {
      const v = d.verdicts.get(Number(cell.dataset.pid))
      if (v) { kind = v.kind === 'origin' ? '' : v.kind; text = v.text }
    } else if (d.slot && inTrash(d, x, y)) {
      text = 'Take off the timetable'
    }
    if (d.kind !== kind) { ghost.dataset.kind = kind; d.kind = kind }
    if (d.text !== text) {
      const reason = rootRef.current?.querySelector('.tw-reason')
      if (reason) { reason.textContent = text; reason.dataset.kind = kind }
      d.text = text
    }
  }

  function begin(pick, x, y, sticky, cardEl) {
    setPop(null)
    const ghost = document.createElement('div')
    ghost.className = 'tw-ghost'
    ghost.textContent = pick.title
    document.body.appendChild(ghost)
    document.body.style.cursor = 'grabbing'
    const d = {
      ...pick, x, y, sticky, ghost, ghostW: ghost.offsetWidth, ghostH: ghost.offsetHeight,
      verdicts: new Map(), hot: null, kind: null, text: null,
    }
    drag.current = d
    const root = rootRef.current
    // Bring what's being aimed at into view, without animating the page away
    // from under the pointer. Everything is measured before anything changes,
    // so the browser only has to work the page out once.
    const strip = stripRef.current
    const board = strip?.querySelector(`[data-section-board="${d.sectionIds[0]}"]`)
    if (board) {
      const a = board.getBoundingClientRect()
      const b = strip.getBoundingClientRect()
      if (a.left < b.left || a.right > b.right) strip.scrollLeft = board.offsetLeft
    }
    const list = listRef.current
    const mine = list?.querySelector(`[data-teacher="${live.current.teacherId}"]`)
    if (mine) {
      const a = mine.getBoundingClientRect()
      const b = list.getBoundingClientRect()
      if (a.top < b.top || a.bottom > b.bottom) centreOn(live.current.teacherId, 'auto')
    }
    measure(d)
    root.dataset.dragging = '1'
    if (d.slot) root.dataset.moving = '1'
    if (cardEl) cardEl.dataset.picked = '1'
    for (const grid of targetGrids(d)) grid.setAttribute('data-target', '1')
    hueGrids(d)
    showHover(d)
  }

  const finish = useCallback(() => {
    const d = drag.current
    if (!d) return
    if (d.frame) cancelAnimationFrame(d.frame)
    d.ghost.remove()
    document.body.style.cursor = ''
    drag.current = null
    clearHues()
  }, [])

  function pickCard(key, x, y, sticky, el) {
    const lesson = live.current.lessons.find((l) => l.key === key)
    if (!lesson) return
    const teacherIds = teachersOfLesson(lesson, live.current.teacherId, live.current.entries)
    begin({
      lesson, teacherIds, sectionIds: lesson.section_ids,
      title: `${lesson.label} ${sectionShort(live.current.sections.get(lesson.class_group_id))}`,
    }, x, y, sticky, el)
  }

  function dropOn(cell) {
    const d = drag.current
    const pid = Number(cell.dataset.pid)
    const period = live.current.periodsById.get(pid)
    const v = d.verdicts.get(pid) ?? (period ? judge(d, period) : { kind: 'bad', text: 'Nothing can be scheduled there' })
    const { edits: run, toast: say, onFindAWay: findWay } = live.current
    const title = d.ghost.textContent
    const when = `${DAY_NAMES[period?.day_of_week] ?? ''}, period ${period?.number ?? ''}`
    const lesson = d.lesson
    const slot = d.slot
    const from = d.fromPeriodId
    if (v.kind === 'origin') return finish()
    if (v.kind === 'bad') {
      finish()
      const action = slot ? { label: 'Find a way', run: () => findWay(slot.sections[0], from, pid, v.text) } : null
      return say('bad', slot ? 'Not moved' : 'Not placed', v.text, action)
    }
    const undo = { label: 'Undo', run: () => run.undo() }
    if (lesson) run.place(lesson, live.current.teacherId, period, d.teacherIds)
    else run.move(slot, from, period)
    finish()
    if (v.kind === 'warn') {
      say('warn', `${title} ${lesson ? 'placed' : 'moved'}, ${v.breaks.length} rule${v.breaks.length > 1 ? 's' : ''} broken`, v.breaks.join('; '), undo)
    } else {
      say('ok', `${title} ${lesson ? 'placed' : 'moved'}`, when, undo)
    }
  }

  function takeOff(slot, fromPeriodId) {
    const { edits: run, toast: say, periodsById: periods, sections: byId } = live.current
    const first = slot.entries[0]
    const name = first.elective_block_name ?? first.subject_name
    finish()
    setPop(null)
    run.remove(slot, periods.get(fromPeriodId))
    say('ok', `${name} ${sectionShort(byId.get(first.class_group_id))} taken off the timetable`, 'Its card is back in the list.', { label: 'Undo', run: () => run.undo() })
  }

  useEffect(() => {
    function onMove(e) {
      const d = drag.current
      if (d) {
        d.x = e.clientX
        d.y = e.clientY
        if (!d.frame) {
          d.frame = requestAnimationFrame(() => {
            d.frame = null
            if (drag.current === d) showHover(d)
          })
        }
        return
      }
      const p = press.current
      if (!p || Math.hypot(e.clientX - p.x, e.clientY - p.y) < MOVE_BEFORE_DRAG) return
      if (p.card) {
        p.dragged = true
        pickCard(p.card.dataset.card, e.clientX, e.clientY, false, p.card)
      } else if (p.lesson && !p.moved) {
        p.moved = true
        const sectionId = Number(p.lesson.dataset.section)
        const periodId = Number(p.lesson.dataset.period)
        const ctx = live.current
        const slot = slotEntries(ctx.index, sectionId, periodId)
        const inActiveGrid = !p.board?.dataset.teacher || Number(p.board.dataset.teacher) === ctx.teacherId
        if (!inActiveGrid || !slot.entries.some((x) => x.teacher_id === ctx.teacherId)) return
        const refused = cantMoveReason(slot, ctx)
        if (refused) {
          press.current = null
          ctx.toast('bad', "Can't move this lesson", refused)
          return
        }
        p.dragged = true
        const first = slot.entries[0]
        begin({
          slot, fromPeriodId: periodId, sectionIds: slot.sections,
          title: `${first.elective_block_name ?? first.subject_name} ${sectionShort(ctx.sections.get(sectionId))}`,
        }, e.clientX, e.clientY, false)
      }
    }
    function onUp(e) {
      const p = press.current
      press.current = null
      const d = drag.current
      if (d && p?.dragged) {
        if (d.stale) measure(d)
        const cell = cellAt(d, e.clientX, e.clientY)
        if (cell) return dropOn(cell)
        if (d.slot && inTrash(d, e.clientX, e.clientY)) return takeOff(d.slot, d.fromPeriodId)
        return finish()
      }
      if (!p) return
      if (d) { // A card was clicked, and now a slot is.
        if (p.cell?.dataset.hue) return dropOn(p.cell)
        return finish()
      }
      if (p.card) return pickCard(p.card.dataset.card, e.clientX, e.clientY, true, p.card)
      const other = p.board?.dataset.teacher && Number(p.board.dataset.teacher) !== live.current.teacherId
      if (other) return choose(Number(p.board.dataset.teacher))
      if (p.lesson) {
        setPop({ section: Number(p.lesson.dataset.section), period: Number(p.lesson.dataset.period), x: e.clientX, y: e.clientY })
      } else setPop(null)
    }
    function onCancel() {
      press.current = null
      finish()
    }
    function onKey(e) {
      if (e.key === 'Escape') {
        finish()
        setPop(null)
        setSearch('')
      }
    }
    function onScrollDuring(e) {
      const d = drag.current
      if (d && e.target !== document) {
        d.stale = true
        if (!d.frame) {
          d.frame = requestAnimationFrame(() => {
            d.frame = null
            if (drag.current === d) showHover(d)
          })
        }
      }
    }
    window.addEventListener('scroll', onScrollDuring, true)
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onCancel)
    window.addEventListener('blur', onCancel)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('scroll', onScrollDuring, true)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onCancel)
      window.removeEventListener('blur', onCancel)
      window.removeEventListener('keydown', onKey)
      finish()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The rule forecast can land mid-drag: add its amber to the cells.
  useEffect(() => {
    const d = drag.current
    if (d) {
      hueGrids(d)
      showHover(d)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forecast])

  function onPointerDown(e) {
    if (e.button !== 0) return
    const t = e.target
    if (t.closest('button, select, input, a, label')) return
    const card = t.closest('[data-card]')
    const lesson = t.closest('.tw-lesson[data-section]')
    press.current = {
      x: e.clientX, y: e.clientY, card, lesson,
      cell: t.closest('td[data-pid]'),
      board: t.closest('[data-teacher], [data-section-board]'),
    }
    if (card || lesson) e.preventDefault()
  }
  function onCardKey(e) {
    if (e.key !== 'Enter' && e.key !== ' ') return
    const key = e.target.dataset?.card
    if (!key) return
    e.preventDefault()
    const r = e.target.getBoundingClientRect()
    pickCard(key, r.left + r.width / 2, r.top, true, e.target)
  }

  // Jump to a lesson from the Rules drawer.
  useEffect(() => {
    if (!flashEntryId) return
    const e = entries.find((x) => x.id === flashEntryId.id)
    if (!e) return
    const stripBoard = stripRef.current?.querySelector(`[data-section-board="${e.class_group_id}"]`)
    if (stripBoard) stripRef.current.scrollTo?.({ left: stripBoard.offsetLeft, behavior: smooth() })
    centreOn(live.current.teacherId, smooth())
    const nodes = rootRef.current?.querySelectorAll(`.tw-lesson[data-section="${e.class_group_id}"][data-period="${e.period_id}"]`) ?? []
    nodes.forEach((n) => n.classList.add('tw-flash'))
    const timer = setTimeout(() => nodes.forEach((n) => n.classList.remove('tw-flash')), 2400)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flashEntryId])

  const query = search.trim().toLowerCase()
  const hits = query
    ? teachers.filter((t) => t.name.toLowerCase().includes(query) || qualificationText(t, subjects).toLowerCase().includes(query)).slice(0, 7)
    : []
  const go = (step) => teachers.length && choose(teachers[(position + step + teachers.length) % teachers.length].id)

  return (
    <div className="tw-work" ref={rootRef} onPointerDown={onPointerDown} onKeyDown={onCardKey}>
      <div className="tw-col">
        <div className="tw-picker">
          <div className="tw-search">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search teachers"
              autoComplete="off"
              aria-label="Search teachers"
            />
            {query && (
              <div className="tw-results">
                {hits.length > 0 ? hits.map((t) => (
                  <button key={t.id} type="button" onClick={() => choose(t.id)}>
                    {t.name} <small>{qualificationText(t, subjects)}</small>
                  </button>
                )) : <p>No teacher by that name</p>}
              </div>
            )}
          </div>
          <select className="tw-btn" data-testid="teacher-select" aria-label="Choose teacher" value={teacherId ?? ''} onChange={(e) => choose(Number(e.target.value))}>
            {teachers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <button type="button" className="tw-btn" aria-label="Previous teacher" onClick={() => go(-1)}>‹ Prev</button>
          <button type="button" className="tw-btn" aria-label="Next teacher" onClick={() => go(1)}>Next ›</button>
          <span className="tw-count">{position + 1} of {teachers.length}</span>
        </div>
        <div className="tw-teachers" ref={listRef} onScroll={onListScroll}>
          {teachers.map((t) => {
            const list = byTeacher.get(t.id) ?? []
            return (
              <TeacherBoard
                key={t.id}
                teacher={t}
                active={t.id === teacherId}
                entries={list}
                layout={layout}
                sectionsById={sectionsById}
                broken={brokenFor(list)}
                subjects={subjects}
                ownSections={sections.filter((s) => s.class_teacher_id === t.id).map(sectionShort).join(', ')}
              />
            )
          })}
        </div>
      </div>

      <div className="tw-col">
        <div className="tw-legend">
          <span className="tw-key"><i className="tw-k-ok" />Free</span>
          <span className="tw-key"><i className="tw-k-warn" />Breaks a rule, can still drop</span>
          <span className="tw-key"><i className="tw-k-bad" />Already taken</span>
          <span className="tw-reason" role="status" />
        </div>
        <div className="tw-strip" ref={stripRef}>
          {sections.map((s) => {
            const list = bySection.get(s.id) ?? []
            return (
              <SectionBoard
                key={s.id}
                section={s}
                frozen={frozenSections.has(s.id)}
                note={teacher && lessons.some((l) => l.section_ids.includes(s.id) && l.teacher_ids.includes(teacherId)) ? `${teacher.name} qualifies` : ''}
                entries={list}
                layout={layout}
                sectionsById={sectionsById}
                mine={list.filter((e) => e.teacher_id === teacherId).map((e) => e.id).join(',')}
                broken={brokenFor(list)}
                classTeacher={teachersById.get(s.class_teacher_id)?.name}
              />
            )
          })}
        </div>
        <div className="tw-cards" data-trash="1">
          <h2 className="tw-cards-title">{teacher ? `Lessons ${teacher.name} is qualified for` : 'Lessons'}</h2>
          <h2 className="tw-cards-drop">Drop here to take this lesson off the timetable</h2>
          <p className="tw-cards-sub">
            {teacher ? `${qualificationText(teacher, subjects)}, from the Teachers step. ` : ''}
            Drag a card onto a slot, or click a card and then click a slot.
          </p>
          <div className="tw-cardlist">
            {cards.map((lesson) => (
              <LessonCard
                key={lesson.key}
                lesson={lesson}
                state={cardState(lesson, teacherId, entries, frozenSections)}
                section={sectionsById.get(lesson.class_group_id)}
                takenByName={(id) => teachersById.get(id)?.name}
                onSwitch={choose}
              />
            ))}
          </div>
          {teacher && cards.length === 0 && (
            <p className="tw-cards-sub" style={{ marginTop: 6 }}>No lesson in this school&rsquo;s plan matches what {teacher.name} is set up to teach.</p>
          )}
        </div>
      </div>

      {pop && (
        <LessonPop
          pop={pop}
          index={index}
          ctx={live.current}
          teacherId={teacherId}
          brokenIds={brokenIds}
          periodsById={periodsById}
          onWorkOn={(id) => choose(id)}
          onClose={() => setPop(null)}
          onTakeOff={takeOff}
          edits={edits}
          toast={toast}
        />
      )}
    </div>
  )
}

const TeacherBoard = memo(function TeacherBoard({ teacher, active, entries, layout, sectionsById, broken, subjects, ownSections }) {
  const owner = useMemo(() => ({ ownSections }), [ownSections])
  // Roughly its real height, so skipping off-screen grids doesn't shift scrolling.
  const rows = layout.rows.reduce((h, r) => h + (r.band ? 14 : 42), 0)
  return (
    <article
      className={`tw-board${active ? ' tw-active' : ''}`}
      data-teacher={teacher.id}
      style={{ containIntrinsicSize: `auto ${rows + 62}px` }}
      aria-label={`${teacher.name}'s timetable`}
    >
      <header>
        <h2>{teacher.name}</h2>
        <small>{entries.length} periods a week · {qualificationText(teacher, subjects)}</small>
      </header>
      <WeekGrid kind="teacher" entries={entries} layout={layout} sectionsById={sectionsById} mine={active ? entries.map((e) => e.id).join(',') : ''} broken={broken} owner={owner} />
    </article>
  )
}, (a, b) => (
  a.active === b.active && a.layout === b.layout && a.broken === b.broken && a.teacher === b.teacher
  && a.sectionsById === b.sectionsById && a.subjects === b.subjects && a.ownSections === b.ownSections
  && a.entries.length === b.entries.length && a.entries.every((e, i) => e === b.entries[i])
))

const SectionBoard = memo(function SectionBoard({ section, frozen, note, entries, layout, sectionsById, mine, broken, classTeacher }) {
  const owner = useMemo(() => ({ classTeacher, grade: section.grade }), [classTeacher, section.grade])
  const rows = layout.rows.reduce((h, r) => h + (r.band ? 14 : 32), 0)
  return (
    <article
      className="tw-board"
      data-section-board={section.id}
      style={{ containIntrinsicSize: `392px ${rows + 62}px` }}
      aria-label={`${sectionTitle(section)} timetable`}
    >
      <header>
        <h2>{sectionTitle(section)}</h2>
        {frozen && <span title="Frozen">❄ Frozen</span>}
        <small>{note}</small>
      </header>
      <WeekGrid kind="section" entries={entries} layout={layout} sectionsById={sectionsById} mine={mine} broken={broken} owner={owner} />
    </article>
  )
}, (a, b) => (
  a.frozen === b.frozen && a.note === b.note && a.mine === b.mine && a.broken === b.broken && a.layout === b.layout
  && a.section === b.section && a.sectionsById === b.sectionsById && a.classTeacher === b.classTeacher
  && a.entries.length === b.entries.length && a.entries.every((e, i) => e === b.entries[i])
))

function LessonCard({ lesson, state, section, takenByName, onSwitch }) {
  const { placed, left, takenBy, frozen, off } = state
  let line = `${left} of ${lesson.periods_per_week} left`
  if (left <= 0) line = 'All placed'
  if (frozen) line = `❄ ${Math.max(left, 0)} of ${lesson.periods_per_week} left, frozen`
  if (lesson.split) line = `${Math.max(left, 0)} of ${lesson.periods_per_week} left. Split lab, placed by Generate`
  return (
    <div
      className={`tw-card${off ? ' tw-off' : ''}`}
      data-testid="lesson-card"
      {...(off ? {} : { 'data-card': lesson.key, role: 'button', tabIndex: 0 })}
      title={lesson.detail ?? lesson.label}
    >
      <b>{lesson.label} {sectionShort(section)}</b>
      <span className="tw-card-left">{line}</span>
      {takenBy != null && (
        <div className="tw-card-left">
          {takenByName(takenBy)} teaches this.{' '}
          <button type="button" className="tw-link" onClick={() => onSwitch(takenBy)}>Switch</button>
        </div>
      )}
      <div className="tw-pips" aria-hidden="true">
        {Array.from({ length: lesson.periods_per_week }, (_, i) => <i key={i} className={i < placed ? 'tw-done' : undefined} />)}
      </div>
    </div>
  )
}

function LessonPop({ pop, index, ctx, teacherId, brokenIds, periodsById, onWorkOn, onClose, onTakeOff, edits, toast }) {
  const slot = slotEntries(index, pop.section, pop.period)
  const shown = index.at(pop.section, pop.period)
  const first = shown[0]
  if (!first) return null
  const period = periodsById.get(pop.period)
  const section = ctx.sections.get(pop.section)
  const isMine = shown.some((e) => e.teacher_id === teacherId)
  const locked = slot.entries.some((e) => e.locked)
  const blocked = slot.sections.some((s) => ctx.frozen.has(s)) ? `${sectionShort(section)} is frozen` : slot.entries.find((e) => e.subject_frozen)?.subject_name
  const isSplit = slot.entries.some((e) => e.lab_batch != null)
  const anyBroken = shown.some((e) => brokenIds.has(e.id))
  const other = first.teacher_id != null && !isMine ? first.teacher_id : null
  return (
    <div className="tw-pop" style={{ left: Math.min(pop.x + 8, window.innerWidth - 262), top: Math.min(pop.y + 8, window.innerHeight - 240) }}>
      <h3>{first.elective_block_name ?? first.subject_name} {sectionShort(section)}</h3>
      <p>
        {DAY_NAMES[period?.day_of_week]}, period {period?.number ?? ''}
        {shown.map((e) => (
          <span key={e.id} style={{ display: 'block' }}>
            {first.elective_block_id != null || shown.length > 1 ? `${e.subject_name}: ` : ''}{e.teacher_name ?? 'No teacher yet'}
            {e.assistant_teacher_name ? `, with ${e.assistant_teacher_name} assisting` : ''}{e.room_name ? `, ${e.room_name}` : ''}
          </span>
        ))}
      </p>
      {anyBroken && <div className="tw-warnline">This lesson breaks a rule. See the Rules button above.</div>}
      <div className="tw-row">
        {other != null && <button type="button" className="tw-btn" onClick={() => onWorkOn(other)}>Work on {ctx.teachers.get(other)?.name}</button>}
        {blocked ? (
          <p>{blocked === first.subject_name ? `${blocked} is frozen` : blocked}</p>
        ) : (
          <>
            {!isSplit && (
              <button
                type="button"
                className="tw-btn"
                onClick={() => {
                  onClose()
                  edits.lock(slot, pop.section, pop.period, !locked)
                  toast('ok', locked ? 'Lesson unlocked' : 'Lesson locked', locked ? '' : 'It stays here when you generate.', { label: 'Undo', run: () => edits.undo() })
                }}
              >
                {locked ? 'Unlock' : '❄ Lock'}
              </button>
            )}
            {!locked && <button type="button" className="tw-btn" onClick={() => onTakeOff(slot, pop.period)}>Take off</button>}
          </>
        )}
      </div>
    </div>
  )
}
