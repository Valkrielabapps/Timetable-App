import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import TimetableTab from './TimetableTab'

vi.mock('../api', () => ({
  api: {
    acceptCompromise: vi.fn(() => Promise.resolve()),
    downloadTimetableExport: vi.fn(() => Promise.resolve()),
    downloadStudentTimetables: vi.fn(() => Promise.resolve()),
    suggestMove: vi.fn(),
    moveChain: vi.fn(),
    editTimetableByCommand: vi.fn(),
  },
}))

const m = vi.hoisted(() => ({
  timetable: null, list: [], frozen: [], subjectFreezes: [], blocks: [], rooms: [], lessons: [], check: null,
  entitlements: undefined, forecast: null,
  generate: null, setFrozen: null, blank: null, open: null, edits: null, apply: null,
}))

vi.mock('./SubstitutionsTab', () => ({ default: () => <div data-testid="subs" /> }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => ({ data: m.entitlements }) }))
vi.mock('../hooks/useSchoolData', () => ({
  usePlanChanges: () => ({ data: null }),
  useRefreshAll: () => () => {},
  useSetupCheck: () => ({ data: m.check, isLoading: false }),
  useTimetables: () => ({ data: m.list }),
  useTimetable: (id) => ({ data: id != null ? m.timetable : null }),
  useGenerateTimetable: () => ({ generate: m.generate, isGenerating: false }),
  useApplyEntryUpdates: () => m.apply,
  useElectiveBlocks: () => ({ data: m.blocks }),
  useFrozenStatus: () => ({ data: m.frozen }),
  useRooms: () => ({ data: m.rooms }),
  useSetFrozen: () => ({ setFrozen: m.setFrozen, isSaving: false }),
  useSubjectFreezes: () => ({ data: m.subjectFreezes }),
  useSubjectFreezeActions: () => ({ freeze: vi.fn(), unfreeze: vi.fn(), isSaving: false }),
  useVersionActions: () => ({ open: m.open }),
}))
vi.mock('../hooks/useTimetableEdits', () => ({
  useTimetableEdits: () => m.edits,
  useLessons: () => ({ data: m.lessons }),
  useForecast: () => m.forecast,
  useStartBlank: () => m.blank,
}))

/**
 * The Timetable page: building one teacher at a time in the workspace, reading
 * in plain view, and everything that used to sit around the grid - rules,
 * freezing, exports, versions - in the places it lives now.
 */

const A = { id: 1, grade: 'Grade 9', name: 'A', class_teacher_id: 7 }
const B = { id: 2, grade: 'Grade 9', name: 'B' }
const C = { id: 3, grade: 'Grade 10', name: 'A' }
const sections = [C, B, A] // out of order on purpose
const susan = { id: 7, name: 'Mrs Susan', qualified_subject_ids: [5], qualified_grades: ['Grade 9'], unavailable_period_ids: [] }
const george = { id: 8, name: 'Mr George', qualified_subject_ids: [6], qualified_grades: [], unavailable_period_ids: [] }
const subjects = [{ id: 5, name: 'Physics' }, { id: 6, name: 'Maths' }]
const periods = [
  { id: 11, day_of_week: 0, order: 0, number: 1, kind: 'lesson' },
  { id: 12, day_of_week: 0, order: 1, number: 2, kind: 'lesson' },
  { id: 13, day_of_week: 0, order: 2, kind: 'break', is_break: true, label: 'Recess' },
  { id: 14, day_of_week: 0, order: 3, kind: 'class_teacher', is_break: true },
  { id: 15, day_of_week: 0, order: 4, number: 3, kind: 'lesson', zero_grades: ['Grade 10'] },
]
const entry = (id, section, period, teacher, subject, more = {}) => ({
  id, class_group_id: section, period_id: period, teacher_id: teacher, teacher_name: teacher === 7 ? 'Mrs Susan' : teacher === 8 ? 'Mr George' : null,
  subject_id: subject, subject_name: subject === 5 ? 'Physics' : 'Maths', day_of_week: 0, order: periods.find((p) => p.id === period).order,
  room_id: null, room_name: null, locked: false, subject_frozen: false, elective_block_id: null, ...more,
})
const physicsA = {
  key: 'r1', kind: 'subject', class_group_id: 1, section_ids: [1], subject_id: 5, label: 'Physics', detail: null,
  periods_per_week: 3, teacher_ids: [7], split: false, frozen: null, options: [],
}
const physicsB = { ...physicsA, key: 'r2', class_group_id: 2, section_ids: [2] }

const VIOLATION = { constraint_id: 3, description: 'Mrs Susan: no classes after break', strength: 'required', entry_ids: [101], detail: 'Monday period 3' }

function useTimetable(more = {}) {
  m.timetable = {
    id: 1, status: 'draft', version_number: 2, name: null, created_at: null, entries: [entry(101, 1, 11, 7, 5), entry(102, 2, 11, 8, 6)],
    violations: [], generation_notes: [], frozen_kept: [], ...more,
  }
  m.list = [{ id: 1, status: 'draft', is_current: true, version_number: 2 }, { id: 0, status: 'draft', is_current: false, version_number: 1 }]
}

function renderTab(props = {}) {
  return render(
    <TimetableTab schoolId={1} classGroup={A} classGroups={sections} teachers={[george, susan]} subjects={subjects} periods={periods} constraints={[]} {...props} />,
  )
}

// jsdom has no PointerEvent; React only needs the event's type and fields.
const pointer = (el, type, x = 10, y = 10) => fireEvent(el, new MouseEvent(type, { bubbles: true, button: 0, clientX: x, clientY: y }))
const clickLikeAPointer = (el) => { pointer(el, 'pointerdown'); pointer(el, 'pointerup') }
const teacherBoard = (name) => screen.getByRole('article', { name: `${name}'s timetable` })
const sectionBoard = (name) => screen.getByRole('article', { name: `${name} timetable` })
const huesIn = (board) => [...board.querySelectorAll('td[data-pid]')].map((c) => [Number(c.dataset.pid), c.dataset.hue])
const cell = (board, pid) => board.querySelector(`td[data-pid="${pid}"]`)
const openPlain = () => fireEvent.click(screen.getByRole('button', { name: 'Plain view' }))
const openRules = () => fireEvent.click(screen.getByRole('button', { name: /rules? broken|setup problem/ }))

beforeEach(() => {
  Object.assign(m, {
    timetable: null, list: [], frozen: [], subjectFreezes: [], blocks: [], rooms: [], lessons: [physicsA, physicsB], check: null,
    entitlements: undefined, forecast: null,
    generate: vi.fn(() => Promise.resolve()), setFrozen: vi.fn(() => Promise.resolve()), blank: vi.fn(() => Promise.resolve()),
    open: vi.fn(() => Promise.resolve()), apply: vi.fn(),
    edits: {
      undoCount: 0, revision: 0, place: vi.fn(), move: vi.fn(), remove: vi.fn(), lock: vi.fn(), undo: vi.fn(),
    },
  })
  vi.clearAllMocks()
})

describe('the workspace', () => {
  it('shows one teacher at a time, alphabetically, with their lessons as cards', () => {
    useTimetable()
    renderTab()
    expect(screen.getByRole('combobox', { name: 'Choose teacher' })).toHaveValue('8')
    expect(teacherBoard('Mr George')).toHaveClass('tw-active')
    expect(teacherBoard('Mrs Susan')).not.toHaveClass('tw-active')
    fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))
    expect(teacherBoard('Mrs Susan')).toHaveClass('tw-active')
    expect(screen.getByText('Lessons Mrs Susan is qualified for')).toBeInTheDocument()
    expect(screen.getByText('Physics 9-A')).toBeInTheDocument()
    expect(screen.getByText('Physics, Grade 9, from the Teachers step.', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('2 of 3 left')).toBeInTheDocument()
  })

  it('finds a teacher by search, dropdown and previous', () => {
    useTimetable()
    renderTab()
    fireEvent.change(screen.getByRole('textbox', { name: 'Search teachers' }), { target: { value: 'sus' } })
    fireEvent.click(screen.getByRole('button', { name: /Mrs Susan/ }))
    expect(teacherBoard('Mrs Susan')).toHaveClass('tw-active')
    fireEvent.click(screen.getByRole('button', { name: 'Previous teacher' }))
    expect(teacherBoard('Mr George')).toHaveClass('tw-active')
    fireEvent.change(screen.getByRole('combobox', { name: 'Choose teacher' }), { target: { value: '7' } })
    expect(teacherBoard('Mrs Susan')).toHaveClass('tw-active')
    fireEvent.change(screen.getByRole('textbox', { name: 'Search teachers' }), { target: { value: 'nobody' } })
    expect(screen.getByText('No teacher by that name')).toBeInTheDocument()
  })

  it('works on another teacher when their grid is clicked', () => {
    useTimetable()
    renderTab()
    clickLikeAPointer(within(teacherBoard('Mrs Susan')).getByText('Mon'))
    expect(teacherBoard('Mrs Susan')).toHaveClass('tw-active')
  })

  it('orders class timetables the way the sidebar lists them', () => {
    useTimetable()
    renderTab()
    const headings = [...document.querySelectorAll('.tw-strip h2')].map((h) => h.textContent)
    expect(headings).toEqual(['Grade 9-A', 'Grade 9-B', 'Grade 10-A'])
  })

  it('darkens only the selected teacher’s lessons in the class timetables', () => {
    useTimetable()
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))
    expect(within(sectionBoard('Grade 9-A')).getByText('Physics').closest('.tw-lesson')).toHaveClass('tw-mine')
    expect(within(sectionBoard('Grade 9-B')).getByText('Maths').closest('.tw-lesson')).not.toHaveClass('tw-mine')
  })

  it('marks a lesson breaking a rule', () => {
    useTimetable({ violations: [VIOLATION] })
    renderTab()
    expect(within(sectionBoard('Grade 9-A')).getByText('Physics').closest('.tw-lesson')).toHaveClass('tw-broken')
    expect(screen.getByRole('button', { name: '! 1 rule broken' })).toBeInTheDocument()
  })

  it('needs a desktop', () => {
    useTimetable()
    renderTab()
    expect(screen.getByText('Building a timetable needs a desktop')).toBeInTheDocument()
    expect(document.querySelector('.tw-gate')).toBeTruthy()
    expect(document.querySelector('.tw-desktop .tw-work')).toBeTruthy()
  })
})

describe('placing a lesson', () => {
  const pickUp = (text = 'Physics 9-A') => {
    fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))
    clickLikeAPointer(screen.getByText(text).closest('[data-card]'))
  }

  it('colours the teacher’s week and the class’s the moment a card is picked up', () => {
    useTimetable()
    m.forecast = { cards: { r1: { 12: { status: 'warn', reason: 'Mrs Susan: no classes after break' } } }, slots: {} }
    renderTab()
    pickUp()
    const expected = [[11, 'bad'], [12, 'warn'], [15, 'ok']]
    expect(huesIn(teacherBoard('Mrs Susan'))).toEqual(expected)
    expect(huesIn(sectionBoard('Grade 9-A'))).toEqual(expected)
    expect(huesIn(sectionBoard('Grade 9-B'))).toEqual([[11, undefined], [12, undefined], [15, undefined]])
    expect(sectionBoard('Grade 9-A')).toHaveAttribute('data-target')
    expect(document.querySelector('.tw-ghost')).toHaveTextContent('Physics 9-A')
  })

  it('places on green', () => {
    useTimetable()
    renderTab()
    pickUp()
    clickLikeAPointer(cell(teacherBoard('Mrs Susan'), 15))
    expect(m.edits.place).toHaveBeenCalledTimes(1)
    expect(m.edits.place.mock.calls[0].slice(0, 2)).toEqual([physicsA, 7])
    expect(m.edits.place.mock.calls[0][2].id).toBe(15)
    expect(screen.getByText('Physics 9-A placed')).toBeInTheDocument()
    expect(document.querySelector('.tw-ghost')).toBeNull()
    expect(document.querySelector('td[data-hue]')).toBeNull()
  })

  it('can also drop on the class timetable', () => {
    useTimetable()
    renderTab()
    pickUp()
    clickLikeAPointer(cell(sectionBoard('Grade 9-A'), 15))
    expect(m.edits.place).toHaveBeenCalledTimes(1)
  })

  it('places on amber and says which rule broke', () => {
    useTimetable()
    m.forecast = { cards: { r1: { 12: { status: 'warn', reason: 'Mrs Susan: no classes after break' } } }, slots: {} }
    renderTab()
    pickUp()
    clickLikeAPointer(cell(teacherBoard('Mrs Susan'), 12))
    expect(m.edits.place).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Physics 9-A placed, 1 rule broken')).toBeInTheDocument()
    expect(screen.getByText('Mrs Susan: no classes after break')).toBeInTheDocument()
  })

  it('refuses red and says why, without asking the server', () => {
    useTimetable()
    renderTab()
    pickUp()
    clickLikeAPointer(cell(teacherBoard('Mrs Susan'), 11))
    expect(m.edits.place).not.toHaveBeenCalled()
    expect(screen.getByText('Not placed')).toBeInTheDocument()
    expect(screen.getByText('9-A already has Physics with Mrs Susan here')).toBeInTheDocument()
  })

  it('refuses a grade’s own zero period', () => {
    useTimetable()
    m.lessons = [{ ...physicsA, class_group_id: 3, section_ids: [3], key: 'r9' }]
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))
    clickLikeAPointer(screen.getByText('Physics 10-A').closest('[data-card]'))
    expect(cell(teacherBoard('Mrs Susan'), 15).dataset.hue).toBe('bad')
  })

  it('lets go with Escape or a click elsewhere', () => {
    useTimetable()
    renderTab()
    pickUp()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(document.querySelector('td[data-hue]')).toBeNull()
    expect(document.querySelector('.tw-ghost')).toBeNull()
    clickLikeAPointer(screen.getByText('Physics 9-A').closest('[data-card]'))
    expect(document.querySelector('td[data-hue]')).not.toBeNull()
    clickLikeAPointer(screen.getByText('Lessons Mrs Susan is qualified for'))
    expect(document.querySelector('td[data-hue]')).toBeNull()
    expect(m.edits.place).not.toHaveBeenCalled()
  })

  it('offers undo', () => {
    useTimetable()
    renderTab()
    pickUp()
    clickLikeAPointer(cell(teacherBoard('Mrs Susan'), 15))
    fireEvent.click(within(document.querySelector('.tw-toasts')).getByRole('button', { name: 'Undo' }))
    expect(m.edits.undo).toHaveBeenCalledTimes(1)
  })

  it('greys cards that can’t be placed and says why', () => {
    useTimetable({ entries: [entry(101, 1, 11, 8, 5)] })
    m.lessons = [
      physicsA,
      { ...physicsB, frozen: 'Physics' },
      { ...physicsB, key: 'r3', label: 'Robotics', split: true },
      { ...physicsB, key: 'r4', class_group_id: 3, section_ids: [3], periods_per_week: 0 },
    ]
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))
    expect(screen.getByText('Mr George teaches this.', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('❄ 3 of 3 left, frozen')).toBeInTheDocument()
    expect(screen.getByText('3 of 3 left. Split lab, placed by Generate')).toBeInTheDocument()
    expect(screen.getByText('All placed')).toBeInTheDocument()
    expect(document.querySelectorAll('[data-card]')).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Switch' }))
    expect(teacherBoard('Mr George')).toHaveClass('tw-active')
  })
})

describe('a placed lesson', () => {
  const openDetails = (more) => {
    useTimetable(more)
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))
    clickLikeAPointer(within(teacherBoard('Mrs Susan')).getByText('Physics').closest('.tw-lesson'))
    return document.querySelector('.tw-pop')
  }

  it('shows its details on click, and can be locked or taken off', () => {
    const pop = openDetails()
    expect(pop).toHaveTextContent('Physics 9-A')
    expect(pop).toHaveTextContent('Monday, period 1')
    fireEvent.click(within(pop).getByRole('button', { name: '❄ Lock' }))
    expect(m.edits.lock).toHaveBeenCalledWith(expect.anything(), 1, 11, true)
  })

  it('takes it off', () => {
    const pop = openDetails()
    fireEvent.click(within(pop).getByRole('button', { name: 'Take off' }))
    expect(m.edits.remove).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Physics 9-A taken off the timetable')).toBeInTheDocument()
  })

  it('offers unlock, not take off, when locked', () => {
    const pop = openDetails({ entries: [entry(101, 1, 11, 7, 5, { locked: true })] })
    expect(within(pop).getByRole('button', { name: 'Unlock' })).toBeInTheDocument()
    expect(within(pop).queryByRole('button', { name: 'Take off' })).toBeNull()
  })

  it('offers neither when its subject is frozen', () => {
    const pop = openDetails({ entries: [entry(101, 1, 11, 7, 5, { subject_frozen: true })] })
    expect(pop).toHaveTextContent('Physics is frozen')
    expect(within(pop).queryByRole('button', { name: '❄ Lock' })).toBeNull()
  })

  it('can’t be locked as a split lab', () => {
    useTimetable({ entries: [entry(101, 1, 11, 7, 5, { lab_batch: 1 })] })
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))
    clickLikeAPointer(within(teacherBoard('Mrs Susan')).getByText('Physics B1').closest('.tw-lesson'))
    const pop = document.querySelector('.tw-pop')
    expect(within(pop).queryByRole('button', { name: '❄ Lock' })).toBeNull()
  })

  it('offers to work on the teacher when it is someone else’s', () => {
    useTimetable()
    renderTab()
    clickLikeAPointer(within(sectionBoard('Grade 9-A')).getByText('Physics').closest('.tw-lesson'))
    fireEvent.click(screen.getByRole('button', { name: 'Work on Mrs Susan' }))
    expect(teacherBoard('Mrs Susan')).toHaveClass('tw-active')
  })
})

describe('dragging', () => {
  // jsdom has no layout, so give the cells and panels real places: the teacher's
  // cells at x 0-100 and the class's at x 1000-1100, one row per period.
  const at = (pid) => ({ x: 50, y: pid * 10 + 5 })
  let original
  beforeEach(() => {
    original = Element.prototype.getBoundingClientRect
    Element.prototype.getBoundingClientRect = function rect() {
      const box = (left, top, right, bottom) => ({ left, top, right, bottom, width: right - left, height: bottom - top, x: left, y: top })
      if (this.matches('.tw-teachers, .tw-strip')) return box(0, 0, 5000, 5000)
      if (this.matches('.tw-cards')) return box(2000, 0, 3000, 500)
      if (this.matches('td[data-pid]')) {
        const y = Number(this.dataset.pid) * 10
        const x = this.closest('[data-teacher]') ? 0 : 1000
        return box(x, y, x + 100, y + 10)
      }
      return original.call(this)
    }
  })
  afterEach(() => { Element.prototype.getBoundingClientRect = original })

  const startDrag = (el) => {
    pointer(el, 'pointerdown', 500, 500)
    pointer(el, 'pointermove', 520, 520)
  }
  const dropAt = (x, y) => pointer(window, 'pointerup', x, y)
  const mine = () => within(teacherBoard('Mrs Susan')).getByText('Physics').closest('.tw-lesson')
  const toSusan = () => fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))

  it('places a card on the slot it is dropped on', () => {
    useTimetable()
    renderTab()
    toSusan()
    startDrag(screen.getByText('Physics 9-A').closest('[data-card]'))
    expect(document.querySelector('.tw-ghost')).toHaveTextContent('Physics 9-A')
    dropAt(at(15).x, at(15).y)
    expect(m.edits.place.mock.calls[0][2].id).toBe(15)
    expect(document.querySelector('.tw-ghost')).toBeNull()
  })

  it('does nothing when dropped away from any slot', () => {
    useTimetable()
    renderTab()
    toSusan()
    startDrag(screen.getByText('Physics 9-A').closest('[data-card]'))
    dropAt(4000, 4000)
    expect(m.edits.place).not.toHaveBeenCalled()
    expect(document.querySelector('td[data-hue]')).toBeNull()
  })

  it('moves a placed lesson', () => {
    useTimetable()
    renderTab()
    toSusan()
    startDrag(mine())
    expect(cell(teacherBoard('Mrs Susan'), 11).dataset.hue).toBe('origin')
    dropAt(at(15).x, at(15).y)
    expect(m.edits.move).toHaveBeenCalledTimes(1)
    expect(m.edits.move.mock.calls[0][1]).toBe(11)
    expect(m.edits.move.mock.calls[0][2].id).toBe(15)
    expect(screen.getByText('Physics 9-A moved')).toBeInTheDocument()
  })

  it('leaves it alone when dropped back where it was', () => {
    useTimetable()
    renderTab()
    toSusan()
    startDrag(mine())
    dropAt(at(11).x, at(11).y)
    expect(m.edits.move).not.toHaveBeenCalled()
  })

  it('takes it off when dropped on the cards', () => {
    useTimetable()
    renderTab()
    toSusan()
    startDrag(mine())
    dropAt(2500, 100)
    expect(m.edits.remove).toHaveBeenCalledTimes(1)
    expect(m.edits.move).not.toHaveBeenCalled()
  })

  it('doesn’t take a card off when it is dropped on the cards', () => {
    useTimetable()
    renderTab()
    toSusan()
    startDrag(screen.getByText('Physics 9-A').closest('[data-card]'))
    dropAt(2500, 100)
    expect(m.edits.remove).not.toHaveBeenCalled()
    expect(m.edits.place).not.toHaveBeenCalled()
  })

  it('offers moves that make room when a move is blocked, and makes them all at once', async () => {
    useTimetable({ entries: [entry(101, 1, 11, 7, 5), entry(102, 2, 12, 7, 5), entry(103, 1, 12, 8, 6)] })
    api.suggestMove.mockResolvedValue({
      reason: 'Mr George teaches 9-A then',
      suggestions: [{ steps: [{ class_group_id: 1, from_period_id: 12, to_period_id: 15, text: 'Move 9-A Maths' }], warnings: ['A rule breaks'] }],
    })
    api.moveChain.mockResolvedValue({ entries: [] })
    renderTab()
    toSusan()
    startDrag(within(sectionBoard('Grade 9-A')).getByText('Physics').closest('.tw-lesson'))
    dropAt(at(12).x, at(12).y)
    expect(m.edits.move).not.toHaveBeenCalled()
    expect(screen.getByText('Not moved')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Find a way' }))
    const dialog = await screen.findByRole('dialog', { name: 'Blocked move' })
    expect(api.suggestMove).toHaveBeenCalledWith(1, 1, 11, 12)
    expect(await within(dialog).findByText('Move 9-A Maths')).toBeInTheDocument()
    expect(dialog).toHaveTextContent('Allowed, but: A rule breaks')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Make this move' }))
    await waitFor(() => expect(api.moveChain).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Blocked move' })).toBeNull())
    expect(m.apply).toHaveBeenCalledTimes(1)
  })

  it('says when there is no way round', async () => {
    useTimetable({ entries: [entry(101, 1, 11, 7, 5), entry(103, 1, 12, 8, 6)] })
    api.suggestMove.mockResolvedValue({ reason: 'Busy', suggestions: [] })
    renderTab()
    toSusan()
    startDrag(within(sectionBoard('Grade 9-A')).getByText('Physics').closest('.tw-lesson'))
    dropAt(at(12).x, at(12).y)
    fireEvent.click(screen.getByRole('button', { name: 'Find a way' }))
    expect(await screen.findByText(/No small set of moves makes room/)).toBeInTheDocument()
  })

  it('tells a lesson it can’t move another teacher’s lessons from a class timetable', () => {
    useTimetable()
    renderTab()
    toSusan()
    startDrag(within(sectionBoard('Grade 9-B')).getByText('Maths').closest('.tw-lesson'))
    expect(document.querySelector('.tw-ghost')).toBeNull()
  })

  it('stops when the window loses focus', () => {
    useTimetable()
    renderTab()
    toSusan()
    startDrag(screen.getByText('Physics 9-A').closest('[data-card]'))
    fireEvent.blur(window)
    expect(document.querySelector('.tw-ghost')).toBeNull()
  })

  it('leaves nothing behind when the page goes away', () => {
    useTimetable()
    const { unmount } = renderTab()
    toSusan()
    startDrag(screen.getByText('Physics 9-A').closest('[data-card]'))
    unmount()
    expect(document.querySelector('.tw-ghost')).toBeNull()
    expect(document.body.style.cursor).toBe('')
  })
})

describe('what can’t be dragged', () => {
  it('won’t pick up a locked lesson, and says why', () => {
    useTimetable({ entries: [entry(101, 1, 11, 7, 5, { locked: true })] })
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))
    const lesson = within(teacherBoard('Mrs Susan')).getByText('Physics').closest('.tw-lesson')
    pointer(lesson, 'pointerdown', 10, 10)
    pointer(lesson, 'pointermove', 40, 40)
    expect(document.querySelector('.tw-ghost')).toBeNull()
    expect(screen.getByText("Can't move this lesson")).toBeInTheDocument()
  })

  it('shows the amber and the moving heading while moving', () => {
    useTimetable()
    m.forecast = { cards: {}, slots: { '1:11': { 15: { status: 'warn', reason: 'Breaks “No late Physics”' } } } }
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))
    const lesson = within(teacherBoard('Mrs Susan')).getByText('Physics').closest('.tw-lesson')
    pointer(lesson, 'pointerdown', 10, 10)
    pointer(lesson, 'pointermove', 40, 40)
    expect(huesIn(teacherBoard('Mrs Susan'))).toEqual([[11, 'origin'], [12, 'ok'], [15, 'warn']])
    expect(document.querySelector('.tw-work')).toHaveAttribute('data-moving')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(document.querySelector('.tw-work')).not.toHaveAttribute('data-moving')
  })
})

describe('generating', () => {
  const choose = (name) => {
    fireEvent.click(screen.getByRole('button', { name: /Generate timetable/ }))
    fireEvent.click(screen.getByRole('button', { name }))
  }

  it('fills the gaps, keeping what is placed', async () => {
    useTimetable()
    renderTab()
    choose(/Fill the empty slots/)
    await waitFor(() => expect(m.generate).toHaveBeenCalledWith({ keepPlaced: true }))
  })

  it('regenerates everything', async () => {
    useTimetable()
    renderTab()
    choose(/Regenerate everything/)
    await waitFor(() => expect(m.generate).toHaveBeenCalledWith({ keepPlaced: false }))
  })

  it('starts blank', async () => {
    useTimetable()
    renderTab()
    choose(/Start with a blank timetable/)
    await waitFor(() => expect(m.blank).toHaveBeenCalledTimes(1))
  })

  it('offers both when there is no timetable yet, and can’t fill nothing', async () => {
    renderTab()
    expect(screen.getByText('No timetable yet for this school.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start with a blank timetable' }))
    await waitFor(() => expect(m.blank).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: /Generate timetable ▾/ }))
    expect(screen.getByRole('button', { name: /Fill the empty slots/ })).toBeDisabled()
  })

  it('says what it keeps and builds when sections are frozen', async () => {
    useTimetable()
    m.frozen = [{ class_group_id: 1, frozen: true, frozen_from: 'Version 1' }, { class_group_id: 2, frozen: true }]
    m.subjectFreezes = [{ id: 1, subject: 'Physics', scope_label: 'Whole school', frozen_from: 'Version 1', stale_reasons: ['Changed'] }]
    renderTab()
    choose(/Regenerate everything/)
    const dialog = screen.getByRole('dialog', { name: 'Generate a new version' })
    expect(dialog).toHaveTextContent('Grade 9 (2 sections, frozen from Version 1)')
    expect(dialog).toHaveTextContent('Physics (Whole school, from Version 1)')
    expect(dialog).toHaveTextContent('Grade 10 (1 section)')
    expect(dialog).toHaveTextContent('changed since freezing, so generating will stop')
    expect(m.generate).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Generate' }))
    await waitFor(() => expect(m.generate).toHaveBeenCalledWith({ keepPlaced: false }))
  })

  it('shows progress instead of the grids', () => {
    useTimetable({ status: 'generating', entries: [] })
    renderTab()
    expect(screen.getByText(/Solving the schedule/)).toBeInTheDocument()
    expect(document.querySelector('.tw-work')).toBeNull()
  })

  it('says when the last one failed', () => {
    useTimetable({ status: 'failed', error_message: 'No room', entries: [] })
    renderTab()
    expect(screen.getByRole('button', { name: /Last generation failed/ })).toBeInTheDocument()
  })

  it('switches version', async () => {
    useTimetable()
    renderTab()
    const picker = screen.getByRole('combobox', { name: 'Version' })
    expect(picker).toHaveValue('1')
    expect(within(picker).getByRole('option', { name: 'Version 2 (current)' })).toBeInTheDocument()
    fireEvent.change(picker, { target: { value: '0' } })
    await waitFor(() => expect(m.open).toHaveBeenCalledWith(0))
  })
})

describe('rules', () => {
  it('says nothing is wrong when nothing is', () => {
    useTimetable()
    renderTab()
    expect(screen.getByRole('button', { name: 'No rules broken' })).not.toHaveClass('tw-alert')
    openRules()
    expect(within(screen.getByRole('complementary', { name: 'Rules' })).getAllByText('No rules broken.')).toHaveLength(1)
  })

  it('names each broken rule once, in the words the admin confirmed', () => {
    useTimetable({ violations: [VIOLATION, { ...VIOLATION, detail: 'Tuesday period 3', entry_ids: [102] }] })
    renderTab()
    expect(screen.getByRole('button', { name: '! 1 rule broken' })).toHaveClass('tw-alert')
    openRules()
    const drawer = screen.getByRole('complementary', { name: 'Rules' })
    const issue = within(drawer).getByRole('button', { name: /Mrs Susan: no classes after break/ })
    expect(issue).toHaveTextContent('Monday period 3, and 1 more')
    expect(drawer).toHaveTextContent('It stays on the timetable')
    fireEvent.click(issue)
    expect(screen.queryByRole('complementary', { name: 'Rules' })).toBeNull()
    expect(teacherBoard('Mrs Susan')).toHaveClass('tw-active')
  })

  it('counts rules, not places', () => {
    useTimetable({ violations: [VIOLATION, { ...VIOLATION, constraint_id: 4, description: 'Another' }] })
    renderTab()
    expect(screen.getByRole('button', { name: '! 2 rules broken' })).toBeInTheDocument()
  })

  it('survives a timetable from before violations existed', () => {
    useTimetable({ violations: undefined })
    renderTab()
    expect(screen.getByRole('button', { name: 'No rules broken' })).toBeInTheDocument()
  })

  it('treats an unmet preference calmly', () => {
    useTimetable({ violations: [{ ...VIOLATION, strength: 'preference', description: 'Try to avoid Mondays', detail: 'x' }] })
    renderTab()
    openRules()
    expect(screen.getByRole('button', { name: 'No rules broken' })).toBeInTheDocument()
    expect(screen.getByText('Try to avoid Mondays')).toBeInTheDocument()
    expect(screen.getByText(/Not met in 1 case/)).toBeInTheDocument()
    expect(within(sectionBoard('Grade 9-A')).getByText('Physics').closest('.tw-lesson')).not.toHaveClass('tw-broken')
  })

  it('lists subjects with no teacher, once each', () => {
    useTimetable({ entries: [entry(1, 1, 11, null, 5), entry(2, 1, 12, null, 5)] })
    renderTab()
    expect(within(sectionBoard('Grade 9-A')).getAllByText('No teacher yet')).toHaveLength(2)
    openRules()
    expect(screen.getByText('1 subject has no teacher yet')).toBeInTheDocument()
    expect(screen.getByText(/Physics in Grade 9-A\./)).toBeInTheDocument()
  })

  it('says when saved constraints aren’t applied, and what generating noted', () => {
    useTimetable({ generation_notes: ['A note'], frozen_kept: ['Grade 9 - A'] })
    renderTab({ constraints: [{ id: 1, enforced: false }] })
    openRules()
    expect(screen.getByText(/1 saved constraint isn't applied/)).toBeInTheDocument()
    expect(screen.getByText('A note')).toBeInTheDocument()
    expect(screen.getByText(/Kept as frozen: Grade 9 - A/)).toBeInTheDocument()
  })

  it('opens by itself for a timetable made with compromises, and can be kept', async () => {
    const compromise = { rules: ['Mrs Susan: no classes after break'], reason: ['Not enough periods'], accepted: false }
    useTimetable({ compromise })
    const onOpenConstraints = vi.fn()
    renderTab({ onOpenConstraints })
    const notice = screen.getByRole('region', { name: 'Made with compromises' })
    expect(notice).toHaveTextContent('bends one of them')
    fireEvent.click(within(notice).getByRole('button', { name: /Why couldn/ }))
    expect(notice).toHaveTextContent('Not enough periods')
    fireEvent.click(within(notice).getByRole('button', { name: 'Change the rules' }))
    expect(onOpenConstraints).toHaveBeenCalledTimes(1)
    fireEvent.click(within(notice).getByRole('button', { name: 'Keep this timetable' }))
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Made with compromises' })).toBeNull())
    expect(api.acceptCompromise).toHaveBeenCalledWith(1)
  })

  it('stays out of the way for an ordinary or already kept timetable', () => {
    useTimetable({ compromise: { rules: ['x'], accepted: true } })
    renderTab()
    expect(screen.queryByRole('region', { name: 'Made with compromises' })).toBeNull()
    expect(screen.queryByRole('complementary', { name: 'Rules' })).toBeNull()
  })

  it('stops to ask when setup is certain to stop generation', async () => {
    useTimetable()
    m.check = { ok: false, errors: [{ severity: 'error', kind: 'x', message: 'Grade 9 A is overfull' }], warnings: [] }
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: /Generate timetable/ }))
    fireEvent.click(screen.getByRole('button', { name: /Regenerate everything/ }))
    const ask = screen.getByRole('alertdialog', { name: 'Setup problems' })
    expect(ask).toHaveTextContent('will stop the timetable')
    fireEvent.click(within(ask).getByRole('button', { name: 'See the problems' }))
    expect(screen.getByRole('complementary', { name: 'Rules' })).toHaveTextContent('Grade 9 A is overfull')
    expect(m.generate).not.toHaveBeenCalled()
  })
})

describe('freezing', () => {
  const openFreezing = () => fireEvent.click(screen.getByRole('button', { name: '❄ Freezing' }))

  it('freezes one section', async () => {
    useTimetable()
    renderTab()
    openFreezing()
    fireEvent.click(screen.getByRole('checkbox', { name: /Grade 9-A/ }))
    await waitFor(() => expect(m.setFrozen).toHaveBeenCalledWith([1], true))
  })

  it('freezes a whole grade, and offers to unfreeze it once all of it is frozen', async () => {
    useTimetable()
    renderTab()
    openFreezing()
    fireEvent.click(screen.getByRole('button', { name: 'Freeze all of Grade 9' }))
    await waitFor(() => expect(m.setFrozen).toHaveBeenCalledWith([1, 2], true))
  })

  it('offers to unfreeze a grade once all of it is frozen', () => {
    useTimetable()
    m.frozen = [{ class_group_id: 1, frozen: true }, { class_group_id: 2, frozen: true }]
    renderTab()
    openFreezing()
    expect(screen.getByRole('button', { name: 'Unfreeze all of Grade 9' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Freeze all of Grade 10' })).toBeInTheDocument()
  })

  it('marks a frozen section and why it is out of date', () => {
    useTimetable()
    m.frozen = [{ class_group_id: 1, frozen: true, frozen_from: 'Version 1', stale_reason: 'Its plan changed.' }]
    renderTab()
    expect(within(sectionBoard('Grade 9-A')).getByText('❄ Frozen')).toBeInTheDocument()
    openFreezing()
    const drawer = screen.getByRole('complementary', { name: 'Freezing' })
    expect(drawer).toHaveTextContent('Frozen from Version 1')
    expect(drawer).toHaveTextContent('Its plan changed.')
    expect(drawer).toHaveTextContent('Generating keeps it exactly as it is and only changes the other 2.')
  })

  it('won’t place into or move inside a frozen section', () => {
    useTimetable()
    m.frozen = [{ class_group_id: 1, frozen: true }]
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))
    expect(screen.getByText(/left, frozen/)).toBeInTheDocument()
    const lesson = within(teacherBoard('Mrs Susan')).getByText('Physics').closest('.tw-lesson')
    pointer(lesson, 'pointerdown', 10, 10)
    pointer(lesson, 'pointermove', 40, 40)
    expect(document.querySelector('.tw-ghost')).toBeNull()
    expect(screen.getByText('9-A is frozen')).toBeInTheDocument()
  })

  it('shows the reason when freezing is refused', async () => {
    useTimetable()
    m.setFrozen = vi.fn(() => Promise.reject(new Error('Not allowed')))
    renderTab()
    openFreezing()
    fireEvent.click(screen.getByRole('checkbox', { name: /Grade 9-A/ }))
    expect(await screen.findByText('Not allowed')).toBeInTheDocument()
  })

  it('has Sections and Subjects, with how many of each', () => {
    useTimetable()
    m.frozen = [{ class_group_id: 1, frozen: true }]
    m.subjectFreezes = [{ id: 1, subject: 'Physics', subject_id: 5, scope_label: 'Whole school', class_group_ids: [1], stale_reasons: [], notes: [] }]
    renderTab()
    openFreezing()
    expect(screen.getByRole('tab', { name: 'Sections (1)' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: 'Subjects (1)' }))
    expect(screen.getByRole('complementary', { name: 'Freezing' })).toHaveTextContent('Physics')
  })
})

describe('plain view', () => {
  it('stacks every section with its own lessons, starting at the chosen one', () => {
    useTimetable()
    renderTab()
    openPlain()
    const boxes = [...document.querySelectorAll('.tw-plainbox')]
    expect(boxes.map((b) => b.querySelector('h2').textContent)).toEqual(['Grade 9-A', 'Grade 9-B', 'Grade 10-A'])
    expect(boxes[0]).toHaveTextContent('Physics')
    expect(boxes[0]).not.toHaveTextContent('Maths')
    expect(screen.getByRole('combobox', { name: 'Choose timetable' })).toHaveValue('1')
    expect(screen.getByText('1 of 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next ›' }))
    expect(screen.getByText('2 of 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '‹ Prev' }))
    fireEvent.click(screen.getByRole('button', { name: '‹ Prev' }))
    expect(screen.getByText('3 of 3')).toBeInTheDocument()
  })

  it('also lists teachers and rooms', () => {
    useTimetable({ entries: [entry(101, 1, 11, 7, 5, { room_id: 40, room_name: 'Lab 1' })] })
    m.rooms = [{ id: 40, name: 'Lab 1' }]
    renderTab()
    openPlain()
    fireEvent.click(screen.getByRole('button', { name: 'Teacher' }))
    expect([...document.querySelectorAll('.tw-plainbox h2')].map((h) => h.textContent)).toEqual(['Mr George', 'Mrs Susan'])
    fireEvent.click(screen.getByRole('button', { name: 'Room' }))
    const room = document.querySelector('.tw-plainbox')
    expect(room).toHaveTextContent('Lab 1')
    expect(room).toHaveTextContent('9-A · Mrs Susan')
  })

  it('opens the section picked in the sidebar', () => {
    useTimetable()
    const { rerender } = renderTab()
    expect(document.querySelector('.tw-work')).toBeTruthy()
    rerender(<TimetableTab schoolId={1} classGroup={B} classGroups={sections} teachers={[george, susan]} subjects={subjects} periods={periods} constraints={[]} openSectionSignal={1} />)
    expect(document.querySelector('.tw-work')).toBeNull()
    expect(screen.getByRole('combobox', { name: 'Choose timetable' })).toHaveValue('2')
  })

  it('is all a viewer gets, with nothing to change', () => {
    useTimetable()
    renderTab({ readOnly: true })
    expect(document.querySelector('.tw-work')).toBeNull()
    expect(document.querySelectorAll('.tw-plainbox')).toHaveLength(3)
    for (const name of [/Generate timetable/, 'Workspace', 'Undo', 'Freeze', /✦ Edit|Describe an edit/]) {
      expect(screen.queryByRole('button', { name })).toBeNull()
    }
    expect(screen.getByRole('combobox', { name: 'Version' })).toBeDisabled()
  })

  it('freezes a section from its heading', async () => {
    useTimetable()
    renderTab()
    openPlain()
    fireEvent.click(within(screen.getByRole('article', { name: 'Grade 9-A' })).getByRole('button', { name: 'Freeze' }))
    await waitFor(() => expect(m.setFrozen).toHaveBeenCalledWith([1], true))
  })

  it('prints just the timetable on screen', () => {
    useTimetable()
    window.print = vi.fn(() => {
      expect(document.querySelectorAll('[data-printing]')).toHaveLength(1)
      expect(document.querySelector('[data-printing] h2')).toHaveTextContent('Grade 9-A')
    })
    renderTab()
    openPlain()
    fireEvent.click(screen.getByRole('button', { name: 'Print' }))
    expect(window.print).toHaveBeenCalledTimes(1)
    expect(document.querySelector('[data-printing]')).toBeNull()
  })
})

describe('special periods', () => {
  beforeEach(() => useTimetable())

  it('numbers only the lessons, and shows the break by name', () => {
    renderTab()
    openPlain()
    const rows = [...document.querySelector('.tw-plainbox tbody').children].map((r) => r.children[0].textContent || r.children[1].textContent)
    expect(rows).toEqual(['1', '2', 'Recess', 'Class teacher: Mrs Susan', '3'])
  })

  it('says only "Class teacher" for a section without one', () => {
    renderTab()
    openPlain()
    const boxB = screen.getByRole('article', { name: 'Grade 9-B' })
    expect(within(boxB).getByText('Class teacher')).toBeInTheDocument()
  })

  it('shows a teacher their own class teacher period', () => {
    renderTab()
    openPlain()
    fireEvent.click(screen.getByRole('button', { name: 'Teacher' }))
    expect(screen.getByText('Class teacher: 9-A')).toBeInTheDocument()
  })

  it('marks a grade’s zero period', () => {
    renderTab()
    openPlain()
    expect(within(screen.getByRole('article', { name: 'Grade 10-A' })).getByText('Zero period')).toBeInTheDocument()
    expect(within(screen.getByRole('article', { name: 'Grade 9-A' })).queryByText('Zero period')).toBeNull()
  })
})

describe('elective blocks', () => {
  const block = {
    id: 4, name: 'Block A', class_group_id: 1, section_ids: [1], periods_per_week: 1,
    options: [{ id: 1, subject_id: 5, class_group_ids: null, label: null }, { id: 2, subject_id: 6, class_group_ids: null, label: null }],
  }
  const blockEntries = [
    entry(201, 1, 11, 7, 5, { elective_block_id: 4, elective_block_name: 'Block A', elective_option_id: 1 }),
    entry(202, 1, 11, 8, 6, { elective_block_id: 4, elective_block_name: 'Block A', elective_option_id: 2 }),
  ]

  it('shows as one lesson in the class timetable', () => {
    useTimetable({ entries: blockEntries })
    m.blocks = [block]
    renderTab()
    const board = sectionBoard('Grade 9-A')
    expect(within(board).getByText('Block A')).toBeInTheDocument()
    expect(within(board).getByText('2 teachers')).toBeInTheDocument()
  })

  it('moves as one: every option goes with it', () => {
    useTimetable({ entries: blockEntries })
    m.blocks = [block]
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Next teacher' }))
    const lesson = within(teacherBoard('Mrs Susan')).getByText('Physics').closest('.tw-lesson')
    pointer(lesson, 'pointerdown', 10, 10)
    pointer(lesson, 'pointermove', 40, 40)
    expect(document.querySelector('.tw-ghost')).toHaveTextContent('Block A 9-A')
    fireEvent.keyDown(window, { key: 'Escape' })
  })

  it('lists each student’s combination, and shows only what they attend', () => {
    useTimetable({ entries: [...blockEntries, entry(203, 1, 12, 8, 6)] })
    m.blocks = [block]
    renderTab()
    openPlain()
    const box = screen.getByRole('article', { name: 'Grade 9-A' })
    const picker = within(box).getByRole('combobox', { name: 'Whose timetable to show for Grade 9-A' })
    expect(within(picker).getAllByRole('option').map((o) => o.textContent)).toEqual(['Whole section', '1. Physics', '2. Maths'])
    expect(within(box).getByText('Block A')).toBeInTheDocument()
    fireEvent.change(picker, { target: { value: '0' } })
    expect(within(box).queryByText('Block A')).toBeNull()
    expect(box.querySelectorAll('.tw-lesson')).toHaveLength(2)
    fireEvent.change(picker, { target: { value: '' } })
    expect(within(box).getByText('Block A')).toBeInTheDocument()
  })

  it('isn’t offered for a section without blocks', () => {
    useTimetable()
    renderTab()
    openPlain()
    expect(screen.queryByRole('combobox', { name: /Whose timetable/ })).toBeNull()
  })

  it('downloads student timetables, with the watermark as set', async () => {
    useTimetable({ entries: blockEntries })
    m.blocks = [block]
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: /Export/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /Timetablz watermark/ }))
    openPlain()
    fireEvent.click(within(screen.getByRole('article', { name: 'Grade 9-A' })).getByRole('button', { name: 'Excel' }))
    await waitFor(() => expect(api.downloadStudentTimetables).toHaveBeenCalledWith(1, 'xlsx', 1, 'Grade 9 A', { watermark: false }))
  })
})

describe('exporting', () => {
  const openExport = () => fireEvent.click(screen.getByRole('button', { name: /Export/ }))

  it('downloads the whole school, with the watermark on by default', async () => {
    useTimetable()
    renderTab()
    openExport()
    fireEvent.click(screen.getByRole('button', { name: 'Excel' }))
    await waitFor(() => expect(api.downloadTimetableExport).toHaveBeenCalledWith(1, 'xlsx', { watermark: true }))
  })

  it('can be turned off on a paid plan', async () => {
    useTimetable()
    renderTab()
    openExport()
    fireEvent.click(screen.getByRole('checkbox', { name: /Timetablz watermark/ }))
    fireEvent.click(screen.getByRole('button', { name: 'PDF' }))
    await waitFor(() => expect(api.downloadTimetableExport).toHaveBeenCalledWith(1, 'pdf', { watermark: false }))
  })

  it('opens the upgrade prompt on Free instead', () => {
    useTimetable()
    m.entitlements = { limits: { clean_exports: false } }
    const prompted = vi.fn()
    window.addEventListener('timetablz:plan-limit', prompted)
    renderTab()
    openExport()
    const box = screen.getByRole('checkbox', { name: /Timetablz watermark/ })
    fireEvent.click(box)
    expect(prompted).toHaveBeenCalledTimes(1)
    expect(box).toBeChecked()
    window.removeEventListener('timetablz:plan-limit', prompted)
  })

  it('says why when a download fails', async () => {
    useTimetable()
    api.downloadTimetableExport.mockRejectedValueOnce(new Error('Export failed'))
    renderTab()
    openExport()
    fireEvent.click(screen.getByRole('button', { name: 'PDF' }))
    expect(await screen.findByText('Export failed')).toBeInTheDocument()
  })
})

describe('describing an edit', () => {
  it('applies it and says what happened', async () => {
    useTimetable()
    api.editTimetableByCommand.mockResolvedValue({ description: 'Moved Maths', entries: [] })
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Describe an edit' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Describe an edit' }), { target: { value: 'Move Maths' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
    expect(await screen.findByText('Moved Maths')).toBeInTheDocument()
    expect(api.editTimetableByCommand).toHaveBeenCalledWith(1, 'Move Maths')
    expect(m.apply).toHaveBeenCalledTimes(1)
  })
})

describe('substitutions', () => {
  it('is its own tab, with no timetable controls', () => {
    useTimetable()
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Substitutions' }))
    expect(screen.getByTestId('subs')).toBeInTheDocument()
    expect(document.querySelector('.tw-work')).toBeNull()
    expect(screen.queryByRole('button', { name: /Generate timetable/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Schedule' }))
    expect(document.querySelector('.tw-work')).toBeTruthy()
  })
})
