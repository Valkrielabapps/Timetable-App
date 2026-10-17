import React from 'react'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TimetableTab from './TimetableTab'

const api = vi.hoisted(() => ({ moveSlot: vi.fn(), lockSlot: vi.fn() }))
vi.mock('../api', () => ({ api }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => ({ data: undefined }) }))

const hooks = vi.hoisted(() => ({ timetable: null }))
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: [{ id: 1, status: 'draft' }] }),
  useTimetable: () => ({ data: hooks.timetable }),
  useGenerateTimetable: () => ({ generate: vi.fn(), isGenerating: false }),
  useApplyEntryUpdates: () => vi.fn(),
  useOptimisticSlotMove: () => vi.fn(() => vi.fn()),
  useElectiveBlocks: () => ({ data: [] }),
}))

/**
 * The class teacher period, zero periods and breaks on the timetable.
 *
 * One day: a class teacher period, period 1, lunch, period 2, period 3.
 * Grade 6 has its zero period in period 3; Grade 7 is taught then.
 */

const P = (id, order, kind, extra = {}) => ({
  id, day_of_week: 0, order, label: null, kind, is_break: kind !== 'lesson', number: null,
  zero_all: false, zero_grades: [], ...extra,
})
const PERIODS = [
  P(1, 0, 'class_teacher'),
  P(2, 1, 'lesson', { number: 1 }),
  P(3, 2, 'break', { label: 'Lunch' }),
  P(4, 3, 'lesson', { number: 2 }),
  P(5, 4, 'lesson', { number: 3, zero_grades: ['Grade 6'] }),
]

const SECTIONS = [
  { id: 100, grade: 'Grade 6', name: 'A', class_teacher_id: 10 },
  { id: 101, grade: 'Grade 7', name: 'A', class_teacher_id: null },
]
const TEACHERS = [{ id: 10, name: 'Mrs. Rao' }, { id: 11, name: 'Mr. Khan' }]

const entry = (id, cg, periodId, subject) => ({
  id, class_group_id: cg, class_group_name: 'x', subject_id: 1, subject_name: subject,
  teacher_id: 11, teacher_name: 'Mr. Khan', assistant_teacher_id: null, assistant_teacher_name: null,
  period_id: periodId, period_label: null, day_of_week: 0, order: 0, room_id: null, room_name: null,
  locked: false, lab_batch: null, elective_block_id: null, elective_block_name: null,
})

function renderTab() {
  hooks.timetable = {
    id: 1, status: 'draft', violations: [],
    entries: [entry(21, 100, 2, 'Maths'), entry(22, 101, 5, 'English')],
  }
  render(
    <TimetableTab schoolId={1} classGroup={SECTIONS[0]} classGroups={SECTIONS} teachers={TEACHERS}
                  subjects={[]} periods={PERIODS} constraints={[]} />,
  )
}

const section = (label) => screen.getByText(label).closest('section')
const rows = (label) => [...section(label).querySelectorAll('tbody tr')]
const cell = (label, row) => rows(label)[row].querySelectorAll('td')[1]

beforeEach(() => vi.clearAllMocks())

describe('special periods on the timetable', () => {
  it('numbers only the lessons', () => {
    renderTab()
    expect(rows('Grade 6 · A').map((r) => r.querySelector('td').textContent)).toEqual([
      'Class teacher', 'Period 1', 'Lunch', 'Period 2', 'Period 3',
    ])
  })

  it("names each section's class teacher in the class teacher period", () => {
    renderTab()
    expect(cell('Grade 6 · A', 0)).toHaveTextContent('Mrs. Rao')
  })

  it('says when a section has no class teacher', () => {
    renderTab()
    expect(cell('Grade 7 · A', 0)).toHaveTextContent('No class teacher set')
  })

  it("marks a grade's zero period, and teaches the other grade in it", () => {
    renderTab()
    expect(cell('Grade 6 · A', 4)).toHaveTextContent('Zero period')
    expect(cell('Grade 7 · A', 4)).toHaveTextContent('English')
  })

  it('shows the break by name', () => {
    renderTab()
    expect(cell('Grade 6 · A', 2)).toHaveTextContent('Lunch')
  })

  it('refuses a drop into the class teacher period without asking the server', () => {
    renderTab()
    fireEvent.dragStart(cell('Grade 6 · A', 1).querySelector('[draggable]'))
    fireEvent.drop(cell('Grade 6 · A', 0))
    expect(api.moveSlot).not.toHaveBeenCalled()
  })

  it("refuses a drop into the section's own zero period", () => {
    renderTab()
    // Drop handlers are only on lesson cells, so the zero cell takes none;
    // the guard in handleDrop covers a drop that reaches it anyway.
    fireEvent.dragStart(cell('Grade 6 · A', 1).querySelector('[draggable]'))
    fireEvent.drop(cell('Grade 6 · A', 4))
    expect(api.moveSlot).not.toHaveBeenCalled()
  })

  it("shows a teacher their own class teacher period", () => {
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'By Teacher' }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '10' } })
    const grid = document.querySelector('table')
    expect(within(grid).getByText('Class teacher · Grade 6 A')).toBeInTheDocument()
  })
})
