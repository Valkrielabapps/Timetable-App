import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TimetableTab from './TimetableTab'

vi.mock('../api', () => ({ api: {} }))

// The timetable comes from React Query inside the component, not from props,
// so the hooks are what have to be stubbed.
const mockTimetable = vi.fn()
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: [{ id: 1, status: 'draft' }] }),
  useTimetable: () => ({ data: mockTimetable() }),
  useGenerateTimetable: () => ({ generate: vi.fn(), isGenerating: false }),
  useApplyEntryUpdates: () => vi.fn(),
  useOptimisticMove: () => vi.fn(),
  useOptimisticSwap: () => vi.fn(),
}))

/**
 * The warning shown when a manual edit breaks a saved rule.
 *
 * Dragging a teacher into a period her rule excludes double-books nobody, so
 * every physical check passes and the move is saved - while the Constraints
 * tab goes on calling that rule enforced. Two properties matter, and they pull
 * against each other: the move is kept, and it is reported.
 *
 * The quiet case is tested as carefully as the loud one. A banner that shows
 * when nothing is wrong is one people learn to scroll past, and then it is
 * worth nothing on the day it matters.
 */

const PERIODS = [
  { id: 1, day_of_week: 0, order: 0, label: null, is_break: false },
  { id: 2, day_of_week: 0, order: 1, label: null, is_break: false },
]

const ENTRY = {
  id: 11, class_group_id: 100, class_group_name: 'A', subject_id: 1,
  subject_name: 'Hindi', teacher_id: 10, teacher_name: 'Mrs. Kamini Chandra',
  assistant_teacher_id: null, assistant_teacher_name: null,
  period_id: 2, period_label: null, day_of_week: 0, order: 1,
  room_id: null, room_name: null, locked: false, lab_batch: null,
}

const VIOLATION = {
  constraint_id: 7,
  description: 'Mrs. Kamini Chandra has no periods in periods 5, 6, 7 or 8.',
  strength: 'required',
  entry_ids: [11],
  detail: '1 period here, but the rule says exactly 0',
}

function renderTab(timetable) {
  mockTimetable.mockReturnValue(timetable)
  render(
    <TimetableTab
      schoolId={1}
      classGroup={{ id: 100, grade: 'Grade 8', name: 'A' }}
      classGroups={[{ id: 100, grade: 'Grade 8', name: 'A' }]}
      teachers={[{ id: 10, name: 'Mrs. Kamini Chandra' }]}
      periods={PERIODS}
      constraints={[]}
      readOnly
    />,
  )
}

const CLEAN = { id: 1, status: 'draft', entries: [ENTRY], violations: [] }

describe('timetable rule violations', () => {
  it('says nothing when the timetable honours every rule', () => {
    renderTab(CLEAN)
    expect(screen.queryByText(/breaks? a rule/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/break rules/i)).not.toBeInTheDocument()
  })

  it('names the broken rule in the words the admin confirmed', () => {
    renderTab({ ...CLEAN, violations: [VIOLATION] })
    // Not a paraphrase: this is what the Constraints tab shows, and a warning
    // naming it differently sends someone looking for a rule they don't have.
    expect(screen.getByText(VIOLATION.description, { exact: false })).toBeInTheDocument()
  })

  it('counts the slots rather than the rules', () => {
    renderTab({ ...CLEAN, violations: [VIOLATION] })
    expect(screen.getByText('1 slot now breaks a rule you set')).toBeInTheDocument()
  })

  it('says what went wrong in numbers', () => {
    renderTab({ ...CLEAN, violations: [VIOLATION] })
    // "This breaks a rule" without "1 period here, the rule says 0" leaves
    // someone hunting for which slot to move.
    expect(screen.getByText(/1 period here/)).toBeInTheDocument()
  })

  it('makes clear the change was kept', () => {
    renderTab({ ...CLEAN, violations: [VIOLATION] })
    // Manual editing exists so a human can override. If the warning reads like
    // a rejection, people delete the rule instead - and then nothing records
    // what they wanted.
    expect(screen.getByText(/The change is kept/)).toBeInTheDocument()
  })

  it('counts one slot once even when it breaks two rules', () => {
    renderTab({
      ...CLEAN,
      violations: [
        VIOLATION,
        { ...VIOLATION, constraint_id: 8, description: 'Hindi is never in the last period.' },
      ],
    })
    expect(screen.getByText('1 slot now breaks a rule you set')).toBeInTheDocument()
    expect(screen.getByText(/Hindi is never in the last period/)).toBeInTheDocument()
  })

  it('counts separate slots separately', () => {
    renderTab({
      ...CLEAN,
      entries: [ENTRY, { ...ENTRY, id: 12, period_id: 1, order: 0 }],
      violations: [{ ...VIOLATION, entry_ids: [11, 12] }],
    })
    expect(screen.getByText('2 slots now break rules you set')).toBeInTheDocument()
  })

  it('survives a timetable from before violations existed', () => {
    // Older responses have no `violations` key at all.
    const { violations, ...withoutField } = CLEAN  // eslint-disable-line no-unused-vars
    renderTab(withoutField)
    expect(screen.queryByText(/breaks? a rule/i)).not.toBeInTheDocument()
  })
})
