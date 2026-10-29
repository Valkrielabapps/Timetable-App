import React from 'react'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TimetableTab from './TimetableTab'
import { pick } from '../test/pick'

const api = vi.hoisted(() => ({ moveSlot: vi.fn(), lockSlot: vi.fn() }))
vi.mock('../api', () => ({ api }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => ({ data: undefined }) }))

const hooks = vi.hoisted(() => ({ frozen: [], setFrozen: null, optimistic: null, generate: null }))
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: [{ id: 1, status: 'draft' }] }),
  useTimetable: () => ({ data: hooks.timetable }),
  useGenerateTimetable: () => ({ generate: hooks.generate, isGenerating: false }),
  useApplyEntryUpdates: () => vi.fn(),
  useOptimisticSlotMove: () => hooks.optimistic,
  useElectiveBlocks: () => ({ data: [] }),
  useFrozenStatus: () => ({ data: hooks.frozen }),
  useSetFrozen: () => ({ setFrozen: hooks.setFrozen, isSaving: false }),
  useSubjectFreezes: () => ({ data: hooks.subjectFreezes ?? [] }),
  useSubjectFreezeActions: () => ({ freeze: hooks.freezeSubject, unfreeze: hooks.unfreezeSubject, isSaving: false }),
}))

/**
 * Freezing sections on the timetable: per section and per grade, shown
 * plainly, and nothing in a frozen section can be dragged or locked.
 */

const PERIODS = [
  { id: 1, day_of_week: 0, order: 0, label: null, kind: 'lesson', is_break: false, number: 1, zero_grades: [] },
  { id: 2, day_of_week: 0, order: 1, label: null, kind: 'lesson', is_break: false, number: 2, zero_grades: [] },
]

const SECTIONS = [
  { id: 100, grade: 'Grade 11', name: 'A' },
  { id: 101, grade: 'Grade 11', name: 'B' },
  { id: 102, grade: 'Grade 12', name: 'A' },
]

const entry = (id, cg, periodId, subject) => ({
  id, class_group_id: cg, class_group_name: 'x', subject_id: 1, subject_name: subject,
  teacher_id: 10, teacher_name: 'Mrs. Rao', assistant_teacher_id: null, assistant_teacher_name: null,
  period_id: periodId, period_label: null, day_of_week: 0, order: periodId - 1, room_id: null,
  room_name: null, locked: false, lab_batch: null, elective_block_id: null, elective_block_name: null,
})

function renderTab({ frozen = [], readOnly = false, subjectFreezes = [], subjectFrozen = [] } = {}) {
  hooks.frozen = frozen
  hooks.subjectFreezes = subjectFreezes
  hooks.timetable = {
    id: 1, status: 'draft', violations: [],
    entries: [entry(1, 100, 1, 'Maths'), entry(2, 101, 1, 'Physics'), entry(3, 102, 1, 'English')]
      .map((e) => ({ ...e, subject_frozen: subjectFrozen.includes(e.id) })),
  }
  render(
    <TimetableTab schoolId={1} classGroup={SECTIONS[0]} classGroups={SECTIONS} teachers={[{ id: 10, name: 'Mrs. Rao' }]}
                  subjects={[]} periods={PERIODS} constraints={[]} readOnly={readOnly} />,
  )
}

const status = (id, extra = {}) => ({ class_group_id: id, frozen: true, frozen_at: '2026-10-24T10:00:00', stale_reason: null, ...extra })
const section = (name) => screen.getByRole('region', { name })

beforeEach(() => {
  vi.clearAllMocks()
  hooks.setFrozen = vi.fn().mockResolvedValue([])
  hooks.optimistic = vi.fn(() => vi.fn())
  hooks.generate = vi.fn().mockResolvedValue(undefined)
  hooks.freezeSubject = vi.fn().mockResolvedValue([])
  hooks.unfreezeSubject = vi.fn().mockResolvedValue([])
})

describe('freezing sections', () => {
  it('freezes one section', async () => {
    renderTab()
    fireEvent.click(within(section('Grade 11 · A')).getByRole('button', { name: 'Freeze' }))
    await waitFor(() => expect(hooks.setFrozen).toHaveBeenCalledWith([100], true))
  })

  it('unfreezes one section', async () => {
    renderTab({ frozen: [status(100)] })
    fireEvent.click(within(section('Grade 11 · A')).getByRole('button', { name: 'Unfreeze' }))
    await waitFor(() => expect(hooks.setFrozen).toHaveBeenCalledWith([100], false))
  })

  it('freezes a whole grade at once', async () => {
    renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Freeze all of Grade 11' }))
    await waitFor(() => expect(hooks.setFrozen).toHaveBeenCalledWith([100, 101], true))
  })

  it('offers to unfreeze a grade once all of it is frozen', async () => {
    renderTab({ frozen: [status(100), status(101)] })
    fireEvent.click(screen.getByRole('button', { name: 'Unfreeze all of Grade 11' }))
    await waitFor(() => expect(hooks.setFrozen).toHaveBeenCalledWith([100, 101], false))
  })

  it('still offers to freeze a grade that is only partly frozen', () => {
    renderTab({ frozen: [status(100)] })
    expect(screen.getByRole('button', { name: 'Freeze all of Grade 11' })).toBeInTheDocument()
  })

  it('marks a frozen section', () => {
    // The server lists every section; the unfrozen ones say frozen: false.
    renderTab({ frozen: [status(100), status(101, { frozen: false, frozen_at: null })] })
    expect(within(section('Grade 11 · A')).getByText('❄ Frozen')).toBeInTheDocument()
    expect(within(section('Grade 11 · B')).queryByText('❄ Frozen')).toBeNull()
  })

  it('says what generating will and will not change, naming whole grades as grades', () => {
    renderTab({ frozen: [status(100), status(101)] })
    expect(screen.getByText(/Frozen: Grade 11 \(2 sections\)/)).toBeInTheDocument()
    expect(screen.getByText(/only changes the other 1\./)).toBeInTheDocument()
  })

  it('names single sections when the grade is not all frozen', () => {
    renderTab({ frozen: [status(102), status(100)] })
    expect(screen.getByText(/Frozen: Grade 11 · A, Grade 12/)).toBeInTheDocument()
  })

  it('says nothing when nothing is frozen', () => {
    renderTab({ frozen: SECTIONS.map((cg) => status(cg.id, { frozen: false, frozen_at: null })) })
    expect(screen.queryByText(/Frozen:/)).toBeNull()
  })

  it('shows why a frozen section is out of date', () => {
    renderTab({ frozen: [status(100, { stale_reason: 'Its plan has changed since it was frozen.' })] })
    expect(within(section('Grade 11 · A')).getByText('Its plan has changed since it was frozen.')).toBeInTheDocument()
  })

  it('cannot drag anything in a frozen section', () => {
    renderTab({ frozen: [status(100)] })
    expect(section('Grade 11 · A').querySelector('[draggable="true"]')).toBeNull()
    expect(section('Grade 11 · B').querySelector('[draggable="true"]')).not.toBeNull()
  })

  it('cannot lock anything in a frozen section', () => {
    renderTab({ frozen: [status(100)] })
    fireEvent.click(within(section('Grade 11 · A')).getByText('Maths'))
    expect(api.lockSlot).not.toHaveBeenCalled()
  })

  it('is not offered to a viewer', () => {
    renderTab({ readOnly: true })
    expect(screen.queryByRole('button', { name: 'Freeze' })).toBeNull()
    expect(screen.queryByRole('button', { name: /Freeze all/ })).toBeNull()
  })

  it("shows the server's reason when freezing is refused", async () => {
    hooks.setFrozen = vi.fn().mockRejectedValue(new Error('Generate a timetable for Grade 12 - A before freezing it.'))
    renderTab()
    fireEvent.click(within(section('Grade 12 · A')).getByRole('button', { name: 'Freeze' }))
    expect(await screen.findByText('Generate a timetable for Grade 12 - A before freezing it.')).toBeInTheDocument()
  })
})

const subjectFreeze = (extra = {}) => ({
  id: 5, subject_id: 1, subject: 'Maths', scope: 'school', scope_label: 'Whole school', grades: null,
  class_group_ids: [100], section_count: 1, block_mode: 'subject', in_blocks: false,
  frozen_at: '2026-10-28T10:00:00', frozen_from: 'Version 3', frozen_from_timetable_id: 1,
  stale_reasons: [], notes: [], ...extra,
})

describe('freezing subjects', () => {
  const freezing = () => screen.getByRole('region', { name: 'Freezing' })

  it('has Sections and Subjects, with how many of each are frozen', () => {
    renderTab({ frozen: [status(100)], subjectFreezes: [subjectFreeze()] })
    expect(within(freezing()).getAllByRole('tab').map((t) => t.textContent)).toEqual(['Sections (1)', 'Subjects (1)'])
    expect(within(freezing()).getByText(/Frozen: Grade 11 · A/)).toBeInTheDocument()
  })

  it('says how to freeze a section when none are', () => {
    renderTab()
    expect(within(freezing()).getByText(/No sections are frozen\. Freeze one with the Freeze button/)).toBeInTheDocument()
  })

  it('freezes a subject from the Subjects tab', async () => {
    renderTab()
    fireEvent.click(within(freezing()).getByRole('tab', { name: 'Subjects' }))
    expect(within(freezing()).getByText('No subjects are frozen.')).toBeInTheDocument()
    pick('Subject to freeze', 'Maths')
    fireEvent.click(screen.getByRole('button', { name: 'Freeze Maths' }))
    await waitFor(() => expect(hooks.freezeSubject).toHaveBeenCalledWith(expect.objectContaining({ subject_id: 1 })))
  })

  it('unfreezes one', async () => {
    renderTab({ subjectFreezes: [subjectFreeze()] })
    fireEvent.click(within(freezing()).getByRole('tab', { name: 'Subjects (1)' }))
    fireEvent.click(within(freezing()).getByRole('button', { name: 'Unfreeze' }))
    await waitFor(() => expect(hooks.unfreezeSubject).toHaveBeenCalledWith(5))
  })

  it("marks a frozen subject's lessons, which can't be dragged or locked", () => {
    renderTab({ subjectFreezes: [subjectFreeze()], subjectFrozen: [1] })
    const a = section('Grade 11 · A')
    expect(within(a).getByText('❄ Frozen')).toBeInTheDocument()
    expect(a.querySelector('[draggable="true"]')).toBeNull()
    fireEvent.click(within(a).getByText('Maths'))
    expect(api.lockSlot).not.toHaveBeenCalled()
    // The rest of the timetable is as usual.
    expect(section('Grade 11 · B').querySelector('[draggable="true"]')).not.toBeNull()
  })

  it('asks before generating, saying which subjects are kept', async () => {
    renderTab({ subjectFreezes: [subjectFreeze()] })
    fireEvent.click(screen.getByRole('button', { name: 'Generate Timetable' }))
    expect(hooks.generate).not.toHaveBeenCalled()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('Keeping these subjects’ lessons where they are')
    expect(dialog).toHaveTextContent('Maths (Whole school, from Version 3)')
    expect(dialog).not.toHaveTextContent('Keeping, exactly as they are')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Generate' }))
    await waitFor(() => expect(hooks.generate).toHaveBeenCalledTimes(1))
  })

  it('warns before generating that an out-of-date subject will stop it', () => {
    renderTab({ subjectFreezes: [subjectFreeze({ stale_reasons: ['Grade 11 - A no longer has Maths.'] })] })
    fireEvent.click(screen.getByRole('button', { name: 'Generate Timetable' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('Maths changed since freezing, so generating will stop.')
  })
})
