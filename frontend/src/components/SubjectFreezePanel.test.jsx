import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SubjectFreezePanel from './SubjectFreezePanel'
import { optionsOf, pick } from '../test/pick'

/**
 * Freezing a subject: choosing it, where (whole school, grades, sections),
 * and for a subject in an elective block, just it or the whole block.
 *
 * Maths is taught in 11A, 11B and 12A. Physics is in a block with Accounts
 * in 11A only; 12A has Physics on its own.
 */

const SECTIONS = [
  { id: 100, grade: 'Grade 11', name: 'A' },
  { id: 101, grade: 'Grade 11', name: 'B' },
  { id: 102, grade: 'Grade 12', name: 'A' },
]
let id = 1
const lesson = (cg, subjectId, subject, block = null) => ({
  id: id++, class_group_id: cg, subject_id: subjectId, subject_name: subject, elective_block_id: block,
})
const ENTRIES = [
  lesson(100, 1, 'Maths'), lesson(101, 1, 'Maths'), lesson(102, 1, 'Maths'),
  lesson(100, 2, 'Physics', 7), lesson(100, 3, 'Accounts', 7),
  lesson(102, 2, 'Physics'),
]

const freezeStatus = (extra = {}) => ({
  id: 5, subject_id: 1, subject: 'Maths', scope: 'school', scope_label: 'Whole school', grades: null,
  class_group_ids: [100, 101, 102], section_count: 3, block_mode: 'subject', in_blocks: false,
  frozen_at: '2026-10-28T10:00:00', frozen_from: 'Version 3', frozen_from_timetable_id: 3,
  stale_reasons: [], notes: [], ...extra,
})

let onFreeze, onUnfreeze
function renderPanel({ freezes = [], canFreeze = true } = {}) {
  render(
    <SubjectFreezePanel freezes={freezes} entries={ENTRIES} sections={SECTIONS} canFreeze={canFreeze}
      busy={false} onFreeze={onFreeze} onUnfreeze={onUnfreeze} />,
  )
}

beforeEach(() => {
  onFreeze = vi.fn().mockResolvedValue([])
  onUnfreeze = vi.fn().mockResolvedValue([])
})

describe('freezing a subject', () => {
  it('offers the subjects the timetable has, alphabetically', () => {
    renderPanel()
    expect(optionsOf('Subject to freeze')).toEqual(['Accounts', 'Maths', 'Physics'])
  })

  it('across the whole school', async () => {
    renderPanel()
    pick('Subject to freeze', 'Maths')
    expect(screen.getByLabelText('Whole school (3 sections)')).toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: 'Freeze Maths' }))
    await waitFor(() => expect(onFreeze).toHaveBeenCalledWith({
      subject_id: 1, scope: 'school', grades: null, class_group_ids: null, block_mode: 'subject',
    }))
  })

  it('in some grades', async () => {
    renderPanel()
    pick('Subject to freeze', 'Maths')
    fireEvent.click(screen.getByLabelText('Some grades'))
    const grades = screen.getByRole('group', { name: 'Grades' })
    expect(within(grades).getAllByRole('checkbox').map((c) => c.closest('label').textContent))
      .toEqual(['Grade 11', 'Grade 12'])
    expect(screen.getByRole('button', { name: 'Freeze Maths' })).toBeDisabled()
    fireEvent.click(within(grades).getByLabelText('Grade 11'))
    fireEvent.click(screen.getByRole('button', { name: 'Freeze Maths in 2 sections' }))
    await waitFor(() => expect(onFreeze).toHaveBeenCalledWith({
      subject_id: 1, scope: 'grades', grades: ['Grade 11'], class_group_ids: null, block_mode: 'subject',
    }))
  })

  it('in some sections', async () => {
    renderPanel()
    pick('Subject to freeze', 'Maths')
    fireEvent.click(screen.getByLabelText('Some sections'))
    fireEvent.click(screen.getByLabelText('Grade 12 - A'))
    fireEvent.click(screen.getByRole('button', { name: 'Freeze Maths in 1 section' }))
    await waitFor(() => expect(onFreeze).toHaveBeenCalledWith({
      subject_id: 1, scope: 'sections', grades: null, class_group_ids: [102], block_mode: 'subject',
    }))
  })

  it('in an elective block: just the subject, or the whole block', async () => {
    renderPanel()
    pick('Subject to freeze', 'Physics')
    expect(screen.getByText('Physics is in an elective block with Accounts')).toBeInTheDocument()
    expect(screen.getByLabelText(/Just Physics/)).toBeChecked()
    fireEvent.click(screen.getByLabelText(/The whole block/))
    fireEvent.click(screen.getByRole('button', { name: 'Freeze Physics' }))
    await waitFor(() => expect(onFreeze).toHaveBeenCalledWith(expect.objectContaining({ block_mode: 'block' })))
  })

  it('asks about the block only when the sections chosen have it', () => {
    renderPanel()
    pick('Subject to freeze', 'Physics')
    fireEvent.click(screen.getByLabelText('Some sections'))
    fireEvent.click(screen.getByLabelText('Grade 12 - A'))
    expect(screen.queryByLabelText(/The whole block/)).toBeNull()
    fireEvent.click(screen.getByLabelText('Grade 11 - A'))
    expect(screen.getByLabelText(/The whole block/)).toBeInTheDocument()
  })

  it('a block choice made earlier is dropped when the sections chosen have no block', async () => {
    renderPanel()
    pick('Subject to freeze', 'Physics')
    fireEvent.click(screen.getByLabelText(/The whole block/))
    fireEvent.click(screen.getByLabelText('Some sections'))
    fireEvent.click(screen.getByLabelText('Grade 12 - A'))
    fireEvent.click(screen.getByRole('button', { name: 'Freeze Physics in 1 section' }))
    await waitFor(() => expect(onFreeze).toHaveBeenCalledWith(expect.objectContaining({
      class_group_ids: [102], block_mode: 'subject',
    })))
  })

  it('does not offer sections where the subject is already frozen', () => {
    renderPanel({ freezes: [freezeStatus({ scope: 'sections', class_group_ids: [100], section_count: 1 })] })
    pick('Subject to freeze', 'Maths')
    expect(screen.getByLabelText('Whole school (2 sections)')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Some sections'))
    expect(screen.queryByLabelText('Grade 11 - A')).toBeNull()
  })

  it('says so when the subject is frozen everywhere it is taught', () => {
    renderPanel({ freezes: [freezeStatus()] })
    pick('Subject to freeze', 'Maths')
    expect(screen.getByText('Maths is already frozen everywhere it’s taught.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Freeze Maths/ })).toBeNull()
  })

  it('shows the server’s reason when it refuses', async () => {
    onFreeze = vi.fn().mockRejectedValue(new Error('Maths has no lessons yet for Grade 12 - A in this version.'))
    renderPanel()
    pick('Subject to freeze', 'Maths')
    fireEvent.click(screen.getByRole('button', { name: 'Freeze Maths' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Maths has no lessons yet for Grade 12 - A')
  })
})

describe('frozen subjects', () => {
  it('lists each with where, how many sections and the version', () => {
    renderPanel({ freezes: [freezeStatus()] })
    const item = within(screen.getByRole('list', { name: 'Frozen subjects' })).getByRole('listitem')
    expect(item).toHaveTextContent('❄ Maths · Whole school (3 sections) · from Version 3')
  })

  it('says how a block subject is frozen', () => {
    renderPanel({ freezes: [
      freezeStatus({ id: 1, subject: 'Physics', in_blocks: true, block_mode: 'block' }),
      freezeStatus({ id: 2, subject: 'Chemistry', in_blocks: true, block_mode: 'subject' }),
    ] })
    expect(screen.getByText('With its whole elective block')).toBeInTheDocument()
    expect(screen.getByText('Just Chemistry in its elective block - the other subjects\' teachers can change'))
      .toBeInTheDocument()
  })

  it('shows why one is out of date, and notes', () => {
    renderPanel({ freezes: [freezeStatus({
      stale_reasons: ["Grade 11 - A's Maths went from 2 to 1 periods a week."],
      notes: ['Grade 12 - A now has 1 more period of Maths a week than when it was frozen.'],
    })] })
    expect(screen.getByText(/Out of date - generating will stop/)).toBeInTheDocument()
    expect(screen.getByText("Grade 11 - A's Maths went from 2 to 1 periods a week.")).toBeInTheDocument()
    expect(screen.getByText(/1 more period of Maths/)).toBeInTheDocument()
  })

  it('unfreezes', async () => {
    renderPanel({ freezes: [freezeStatus()] })
    fireEvent.click(screen.getByRole('button', { name: 'Unfreeze' }))
    await waitFor(() => expect(onUnfreeze).toHaveBeenCalledWith(5))
  })

  it('a viewer sees them but cannot change them', () => {
    renderPanel({ freezes: [freezeStatus()], canFreeze: false })
    expect(screen.getByText(/❄ Maths/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Unfreeze' })).toBeNull()
    expect(screen.queryByRole('combobox', { name: 'Subject to freeze' })).toBeNull()
  })
})
