import React from 'react'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TimetableTab from './TimetableTab'

const api = vi.hoisted(() => ({
  moveSlot: vi.fn(),
  lockSlot: vi.fn(),
  downloadStudentTimetables: vi.fn(),
}))
vi.mock('../api', () => ({ api }))

const hooks = vi.hoisted(() => ({
  timetable: null,
  blocks: [],
  applyEntryUpdates: vi.fn(),
  optimisticSlotMove: vi.fn(),
}))
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: [{ id: 1, status: 'draft' }] }),
  useTimetable: () => ({ data: hooks.timetable }),
  useGenerateTimetable: () => ({ generate: vi.fn(), isGenerating: false }),
  useApplyEntryUpdates: () => hooks.applyEntryUpdates,
  useOptimisticSlotMove: () => hooks.optimisticSlotMove,
  useElectiveBlocks: () => ({ data: hooks.blocks }),
}))

/**
 * Elective blocks on the Timetable tab.
 *
 * A block is several subjects one section studies at once, each student
 * taking one. On screen it is one cell; the drag and lock unit is that cell,
 * because the options always run together. Each section with blocks also
 * offers the timetable each combination of choices actually gets.
 */

const PERIODS = [
  { id: 1, day_of_week: 0, order: 0, label: null, is_break: false },
  { id: 2, day_of_week: 0, order: 1, label: null, is_break: false },
  { id: 3, day_of_week: 0, order: 2, label: null, is_break: false },
  { id: 4, day_of_week: 0, order: 3, label: null, is_break: true },
]

const CLASS_GROUPS = [
  { id: 100, grade: 'Grade 11', name: 'A' },
  { id: 101, grade: 'Grade 9', name: 'A' },
]

const SUBJECTS = [
  { id: 1, name: 'Physics' },
  { id: 2, name: 'Accounts' },
  { id: 3, name: 'English' },
  { id: 4, name: 'Chemistry' },
  { id: 5, name: 'Economics' },
  { id: 6, name: 'Hindi' },
]

const entry = (id, classGroupId, periodId, subjectId, teacher, block = null) => ({
  id, class_group_id: classGroupId, class_group_name: 'x',
  subject_id: subjectId, subject_name: SUBJECTS.find((s) => s.id === subjectId).name,
  teacher_id: id, teacher_name: teacher,
  assistant_teacher_id: null, assistant_teacher_name: null,
  period_id: periodId, period_label: null, day_of_week: 0, order: periodId - 1,
  room_id: null, room_name: null, locked: false, lab_batch: null,
  elective_block_id: block?.id ?? null, elective_block_name: block?.name ?? null,
})

const B1 = { id: 7, name: 'Block 1' }
const B2 = { id: 8, name: 'Block 2' }

// 11A: Block 1 (Physics / Accounts) in period 1, English in period 2,
// Block 2 (Chemistry / Economics) in period 3. 9A: Hindi in period 1.
const TIMETABLE = {
  id: 1,
  status: 'draft',
  entries: [
    entry(11, 100, 1, 1, 'Mrs. Rao', B1),
    entry(12, 100, 1, 2, 'Mr. Khan', B1),
    entry(13, 100, 2, 3, 'Ms. Verma'),
    entry(14, 100, 3, 4, 'Mr. Das', B2),
    entry(15, 100, 3, 5, 'Ms. Nair', B2),
    entry(21, 101, 1, 6, 'Mrs. Joshi'),
  ],
  violations: [],
}

const BLOCKS = [
  { id: 7, school_id: 1, class_group_id: 100, name: 'Block 1', periods_per_week: 1,
    options: [{ id: 70, subject_id: 1, preferred_teacher_id: null },
              { id: 71, subject_id: 2, preferred_teacher_id: null }] },
  { id: 8, school_id: 1, class_group_id: 100, name: 'Block 2', periods_per_week: 1,
    options: [{ id: 80, subject_id: 4, preferred_teacher_id: null },
              { id: 81, subject_id: 5, preferred_teacher_id: null }] },
]

function renderTab({ timetable = TIMETABLE, blocks = BLOCKS, ...props } = {}) {
  hooks.timetable = timetable
  hooks.blocks = blocks
  render(
    <TimetableTab
      schoolId={1}
      classGroup={CLASS_GROUPS[0]}
      classGroups={CLASS_GROUPS}
      teachers={[{ id: 11, name: 'Mrs. Rao' }]}
      subjects={SUBJECTS}
      periods={PERIODS}
      constraints={[]}
      {...props}
    />,
  )
}

const section = (label) => screen.getByText(label).closest('section')
const cellOf = (text, label = 'Grade 11 · A') => within(section(label)).getByText(text).closest('td')
const cellAt = (label, order) =>
  section(label).querySelectorAll('tbody tr')[order].querySelectorAll('td')[1]

function drag(fromCell, toCell) {
  fireEvent.dragStart(fromCell.querySelector('[draggable]'))
  fireEvent.drop(toCell)
}

beforeEach(() => {
  vi.clearAllMocks()
  hooks.optimisticSlotMove.mockReturnValue(vi.fn())
  api.moveSlot.mockResolvedValue({ entries: [], violations: [] })
  api.lockSlot.mockResolvedValue({ entries: [], violations: [] })
  api.downloadStudentTimetables.mockResolvedValue(undefined)
})

describe('moving a block', () => {
  it('drops a block onto a lesson as one slot move', async () => {
    renderTab()
    drag(cellOf('Block 1'), cellOf('English'))
    await waitFor(() => expect(api.moveSlot).toHaveBeenCalledWith(1, 100, 1, 2))
    expect(api.moveSlot).toHaveBeenCalledTimes(1)
  })

  it('moves the cells before the server answers', () => {
    renderTab()
    drag(cellOf('Block 1'), cellOf('English'))
    expect(hooks.optimisticSlotMove).toHaveBeenCalledWith(
      100,
      expect.objectContaining({ id: 1 }),
      expect.objectContaining({ id: 2 }),
    )
  })

  it("patches in the server's answer", async () => {
    const answer = { entries: [{ ...TIMETABLE.entries[0], period_id: 2 }], violations: [] }
    api.moveSlot.mockResolvedValue(answer)
    renderTab()
    drag(cellOf('Block 1'), cellOf('English'))
    await waitFor(() => expect(hooks.applyEntryUpdates).toHaveBeenCalledWith(answer))
  })

  it('puts the cells back and says why when the server refuses', async () => {
    const rollback = vi.fn()
    hooks.optimisticSlotMove.mockReturnValue(rollback)
    api.moveSlot.mockRejectedValue(new Error('Mr. Khan is already teaching 9A in that period.'))
    renderTab()
    drag(cellOf('Block 1'), cellOf('English'))
    expect(await screen.findByText('Mr. Khan is already teaching 9A in that period.')).toBeInTheDocument()
    expect(rollback).toHaveBeenCalled()
  })

  it('does nothing when a slot is dropped back where it was', () => {
    renderTab()
    drag(cellOf('Block 1'), cellOf('Block 1'))
    expect(api.moveSlot).not.toHaveBeenCalled()
    expect(hooks.optimisticSlotMove).not.toHaveBeenCalled()
  })

  it("refuses a drop into another section's grid", () => {
    renderTab()
    drag(cellOf('Block 1'), cellOf('Hindi', 'Grade 9 · A'))
    expect(api.moveSlot).not.toHaveBeenCalled()
    expect(screen.getByText("A slot can only be moved within its own section's timetable.")).toBeInTheDocument()
  })

  it('refuses a drop onto a locked slot without asking the server', () => {
    const locked = {
      ...TIMETABLE,
      entries: TIMETABLE.entries.map((e) => (e.id === 13 ? { ...e, locked: true } : e)),
    }
    renderTab({ timetable: locked })
    drag(cellOf('Block 1'), cellOf('English'))
    expect(api.moveSlot).not.toHaveBeenCalled()
    expect(screen.getByText(/That slot is locked/)).toBeInTheDocument()
  })

  it('refuses a drop onto a break', () => {
    renderTab()
    drag(cellOf('Block 1'), cellAt('Grade 11 · A', 3))
    expect(api.moveSlot).not.toHaveBeenCalled()
    expect(screen.getByText('Nothing can be scheduled in a break.')).toBeInTheDocument()
  })

  it('moves an ordinary lesson into a free cell the same way', async () => {
    const withGap = { ...TIMETABLE, entries: TIMETABLE.entries.filter((e) => e.id !== 14 && e.id !== 15) }
    renderTab({ timetable: withGap })
    drag(cellOf('English'), cellAt('Grade 11 · A', 2))
    await waitFor(() => expect(api.moveSlot).toHaveBeenCalledWith(1, 100, 2, 3))
  })
})

describe('locking a block', () => {
  it('locks every option at once', async () => {
    renderTab()
    fireEvent.click(within(cellOf('Block 1')).getByText('Physics'))
    await waitFor(() => expect(api.lockSlot).toHaveBeenCalledWith(1, 100, 1, true))
  })

  it('unlocks a locked block', async () => {
    const locked = {
      ...TIMETABLE,
      entries: TIMETABLE.entries.map((e) => (e.elective_block_id === 7 ? { ...e, locked: true } : e)),
    }
    renderTab({ timetable: locked })
    fireEvent.click(within(cellOf('Block 1')).getByText('Accounts'))
    await waitFor(() => expect(api.lockSlot).toHaveBeenCalledWith(1, 100, 1, false))
  })

  it('frees the whole block when only part of it was locked', async () => {
    // A lock set on one option through the edit box still pins the slot; a
    // click should free it rather than lock the rest.
    const partly = {
      ...TIMETABLE,
      entries: TIMETABLE.entries.map((e) => (e.id === 12 ? { ...e, locked: true } : e)),
    }
    renderTab({ timetable: partly })
    fireEvent.click(within(cellOf('Block 1')).getByText('Physics'))
    await waitFor(() => expect(api.lockSlot).toHaveBeenCalledWith(1, 100, 1, false))
  })
})

describe("each student's own timetable", () => {
  const picker = () => within(section('Grade 11 · A')).getByRole('combobox')

  it('lists every combination of choices, in the order the export prints them', () => {
    renderTab()
    const labels = within(picker()).getAllByRole('option').map((o) => o.textContent)
    expect(labels).toEqual([
      'Whole section (every option)',
      '1. Physics + Chemistry',
      '2. Physics + Economics',
      '3. Accounts + Chemistry',
      '4. Accounts + Economics',
    ])
  })

  it('shows only the chosen options and the common subjects', () => {
    renderTab()
    fireEvent.change(picker(), { target: { value: '2' } }) // Accounts + Chemistry
    // The table, not the section: the picker's own labels name every subject.
    const grid = section('Grade 11 · A').querySelector('table')
    expect(grid).toHaveTextContent('Accounts')
    expect(grid).toHaveTextContent('Chemistry')
    expect(grid).toHaveTextContent('English')
    expect(grid).not.toHaveTextContent('Physics')
    expect(grid).not.toHaveTextContent('Economics')
  })

  it('does not call a student’s lesson a block', () => {
    renderTab()
    fireEvent.change(picker(), { target: { value: '0' } })
    expect(section('Grade 11 · A')).not.toHaveTextContent('Block 1')
  })

  it("is read-only, since dragging it would move the whole block", () => {
    renderTab()
    fireEvent.change(picker(), { target: { value: '0' } })
    expect(section('Grade 11 · A').querySelector('[draggable="true"]')).toBeNull()
  })

  it('goes back to the whole section', () => {
    renderTab()
    fireEvent.change(picker(), { target: { value: '0' } })
    fireEvent.change(picker(), { target: { value: '' } })
    expect(section('Grade 11 · A').querySelector('table')).toHaveTextContent('Economics')
    expect(section('Grade 11 · A').querySelector('[draggable="true"]')).not.toBeNull()
  })

  it('is not offered for a section without blocks', () => {
    // Its timetable is already the same for every student.
    renderTab()
    expect(within(section('Grade 9 · A')).queryByRole('combobox')).toBeNull()
    expect(within(section('Grade 9 · A')).queryByText('Student timetables:')).toBeNull()
  })

  it('downloads the student timetables for that section', async () => {
    renderTab()
    fireEvent.click(within(section('Grade 11 · A')).getByRole('button', { name: 'PDF' }))
    await waitFor(() =>
      expect(api.downloadStudentTimetables).toHaveBeenCalledWith(1, 'pdf', 100, 'Grade 11 A'),
    )
  })

  it('says so when there are too many combinations to list', () => {
    // Ten two-option blocks: 1024 combinations.
    const many = Array.from({ length: 10 }, (_, i) => ({
      id: 100 + i, school_id: 1, class_group_id: 100, name: `B${i}`, periods_per_week: 1,
      options: [{ id: 1000 + 2 * i, subject_id: 1, preferred_teacher_id: null },
                { id: 1001 + 2 * i, subject_id: 2, preferred_teacher_id: null }],
    }))
    renderTab({ blocks: many })
    expect(within(section('Grade 11 · A')).queryByRole('combobox')).toBeNull()
    expect(section('Grade 11 · A')).toHaveTextContent('more than 512 subject combinations')
  })
})

describe('counting broken slots', () => {
  it('counts a block once even when several of its options break the rule', () => {
    renderTab({
      timetable: {
        ...TIMETABLE,
        violations: [{
          constraint_id: 7, description: 'Nothing in period 1.', strength: 'required',
          entry_ids: [11, 12], detail: 'x',
        }],
      },
    })
    expect(section('Grade 11 · A')).toHaveTextContent('1 slot breaking a rule')
    expect(screen.getByText('1 slot now breaks a rule you set')).toBeInTheDocument()
  })
})
