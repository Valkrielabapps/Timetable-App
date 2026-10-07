import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TimetableTab from './TimetableTab'

vi.mock('../api', () => ({ api: {} }))

const mockTimetable = vi.fn()
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: [{ id: 1, status: 'draft' }] }),
  useTimetable: () => ({ data: mockTimetable() }),
  useGenerateTimetable: () => ({ generate: vi.fn(), isGenerating: false }),
  useApplyEntryUpdates: () => vi.fn(),
  useOptimisticSlotMove: () => vi.fn(),
  useElectiveBlocks: () => ({ data: [] }),
}))

/**
 * Every section's timetable on one scrollable page.
 *
 * The by-section view used to show one section at a time, swapped by the
 * sidebar. A timetable is read as a whole - checking one section against
 * another is most of what the job is - so the sidebar now scrolls rather than
 * replaces.
 */

const PERIODS = [
  { id: 1, day_of_week: 0, order: 0, label: null, is_break: false },
  { id: 2, day_of_week: 0, order: 1, label: null, is_break: false },
]

const CLASS_GROUPS = [
  { id: 100, grade: 'Grade 8', name: 'A' },
  { id: 101, grade: 'Grade 8', name: 'B' },
  { id: 102, grade: 'Grade 9', name: 'A' },
]

const entry = (id, classGroupId, periodId, subject) => ({
  id, class_group_id: classGroupId, class_group_name: 'x',
  subject_id: 1, subject_name: subject, teacher_id: 10, teacher_name: 'Mrs. Rao',
  assistant_teacher_id: null, assistant_teacher_name: null,
  period_id: periodId, period_label: null,
  day_of_week: 0, order: periodId - 1,
  room_id: null, room_name: null, locked: false, lab_batch: null,
})

const TIMETABLE = {
  id: 1,
  status: 'draft',
  entries: [
    entry(11, 100, 1, 'Hindi'),
    entry(12, 101, 1, 'Maths'),
    entry(13, 102, 2, 'Science'),
  ],
  violations: [],
}

function renderTab(timetable = TIMETABLE, props = {}) {
  mockTimetable.mockReturnValue(timetable)
  render(
    <TimetableTab
      schoolId={1}
      classGroup={CLASS_GROUPS[0]}
      classGroups={CLASS_GROUPS}
      teachers={[{ id: 10, name: 'Mrs. Rao' }]}
      periods={PERIODS}
      constraints={[]}
      {...props}
    />,
  )
}

describe('all sections on one page', () => {
  it('shows every section, not just the selected one', () => {
    renderTab()
    expect(screen.getByText('Grade 8 · A')).toBeInTheDocument()
    expect(screen.getByText('Grade 8 · B')).toBeInTheDocument()
    expect(screen.getByText('Grade 9 · A')).toBeInTheDocument()
  })

  it('puts each section its own lessons and nobody else\'s', () => {
    renderTab()
    const sectionOf = (label) => screen.getByText(label).closest('section')
    expect(sectionOf('Grade 8 · A')).toHaveTextContent('Hindi')
    expect(sectionOf('Grade 8 · A')).not.toHaveTextContent('Maths')
    expect(sectionOf('Grade 8 · B')).toHaveTextContent('Maths')
    expect(sectionOf('Grade 9 · A')).toHaveTextContent('Science')
  })

  it('gives each section an anchor the sidebar can scroll to', () => {
    // Derived from the id rather than passed around, so selecting a section
    // needs no extra wiring between the sidebar and this view.
    renderTab()
    for (const cg of CLASS_GROUPS) {
      expect(document.getElementById(`timetable-section-${cg.id}`)).not.toBeNull()
    }
  })

  it('orders sections the way the sidebar lists them', () => {
    // Scrolling and clicking have to agree about what comes next.
    renderTab()
    const headings = [...document.querySelectorAll('section h4')].map((h) => h.textContent)
    expect(headings).toEqual(['Grade 8 · A', 'Grade 8 · B', 'Grade 9 · A'])
  })

  it('marks which section a broken rule is in', () => {
    // The band above says what broke; with every section stacked it does not
    // say where to scroll.
    renderTab({
      ...TIMETABLE,
      violations: [{
        constraint_id: 7, description: 'No class has Hindi in period 1.',
        strength: 'required', entry_ids: [11], detail: '1 period here, the rule says 0',
      }],
    })
    const sectionA = screen.getByText('Grade 8 · A').closest('section')
    expect(sectionA).toHaveTextContent('1 slot breaking a rule')
    expect(screen.getByText('Grade 8 · B').closest('section'))
      .not.toHaveTextContent('breaking a rule')
  })

  it('counts several broken slots in one section together', () => {
    renderTab({
      ...TIMETABLE,
      entries: [...TIMETABLE.entries, entry(14, 100, 2, 'Hindi')],
      violations: [{
        constraint_id: 7, description: 'x', strength: 'required',
        entry_ids: [11, 14], detail: 'y',
      }],
    })
    expect(screen.getByText('Grade 8 · A').closest('section'))
      .toHaveTextContent('2 slots breaking a rule')
  })

  it('is read-only when the viewer cannot edit', () => {
    renderTab(TIMETABLE, { readOnly: true })
    const draggable = document.querySelector('[draggable="true"]')
    expect(draggable).toBeNull()
  })
})
