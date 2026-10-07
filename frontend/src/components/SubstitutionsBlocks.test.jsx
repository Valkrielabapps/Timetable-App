import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SubstitutionsTab from './SubstitutionsTab'

const api = vi.hoisted(() => ({
  listPeriods: vi.fn(),
  listTimetables: vi.fn(),
  listSubstitutionLogs: vi.fn(),
  getTimetable: vi.fn(),
}))
vi.mock('../api', () => ({ api }))

/**
 * Covering an absent teacher's block lesson.
 *
 * In a block the section is split: while Mrs. Rao's Physics group needs
 * cover, the Accounts group is with Mr. Khan. The card has to say which
 * lesson it is, or "Grade 11 A, period 1" reads as the whole class.
 */

const PERIODS = [{ id: 1, day_of_week: 0, order: 0, label: null, is_break: false }]

const entry = (id, subjectId, subject, teacherId, block = null) => ({
  id, class_group_id: 100, subject_id: subjectId, subject_name: subject,
  teacher_id: teacherId, teacher_name: 'x', period_id: 1, day_of_week: 0, order: 0,
  locked: false, lab_batch: null,
  elective_block_id: block ? 7 : null, elective_block_name: block,
})

function renderTab({ timetables, timetable }) {
  api.listPeriods.mockResolvedValue(PERIODS)
  api.listTimetables.mockResolvedValue(timetables)
  api.listSubstitutionLogs.mockResolvedValue([])
  api.getTimetable.mockImplementation(async (id) => ({ ...timetable, id }))
  render(
    <SubstitutionsTab
      schoolId={1}
      teachers={[
        { id: 10, name: 'Mrs. Rao', qualified_subject_ids: [1] },
        { id: 11, name: 'Mr. Khan', qualified_subject_ids: [2] },
      ]}
      classGroups={[{ id: 100, grade: 'Grade 11', name: 'A' }]}
    />,
  )
}

const BLOCK_TIMETABLE = {
  status: 'draft',
  entries: [entry(1, 1, 'Physics', 10, 'Block 1'), entry(2, 2, 'Accounts', 11, 'Block 1')],
}

describe('substitutions with elective blocks', () => {
  it('names the lesson and says only that group needs cover', async () => {
    renderTab({ timetables: [{ id: 3, status: 'draft' }], timetable: BLOCK_TIMETABLE })
    fireEvent.click(await screen.findByLabelText('Mrs. Rao'))
    expect(await screen.findByText(/Period 1 • Physics • Absent: Mrs\. Rao/)).toBeInTheDocument()
    expect(screen.getByText('Block 1 — only the Physics group')).toBeInTheDocument()
  })

  it('works from the newest timetable, the one the Timetable tab shows', async () => {
    renderTab({
      timetables: [{ id: 3, status: 'draft' }, { id: 9, status: 'draft' }, { id: 5, status: 'failed' }],
      timetable: BLOCK_TIMETABLE,
    })
    await screen.findByLabelText('Mrs. Rao')
    expect(api.getTimetable).toHaveBeenCalledWith(9)
  })
})
