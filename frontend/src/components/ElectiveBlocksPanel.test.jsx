import React from 'react'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { optionsOf, pick } from '../test/pick'
import ElectiveBlocksPanel from './ElectiveBlocksPanel'

/**
 * Entering a section's elective blocks.
 *
 * A block is a set of subjects the section studies at the same time, each
 * student taking one. The set is saved as a whole, because every way a block
 * goes wrong is about the set: one option, a subject twice, or a subject that
 * everybody already takes.
 */

const SUBJECTS = [
  { id: 1, name: 'Physics' },
  { id: 2, name: 'Accounts' },
  { id: 3, name: 'Biology' },
  { id: 4, name: 'English' },
  { id: 5, name: 'Chemistry' },
]

const TEACHERS = [
  { id: 10, name: 'Mrs. Rao', qualified_subject_ids: [1], qualified_grades: [] },
  { id: 11, name: 'Mr. Khan', qualified_subject_ids: [2], qualified_grades: [] },
  { id: 12, name: 'Ms. Iyer', qualified_subject_ids: [3], qualified_grades: ['Grade 12'] },
  { id: 13, name: 'Mr. Das', qualified_subject_ids: [1, 5], qualified_grades: [] },
]

const BLOCK = {
  id: 7, school_id: 1, class_group_id: 100, name: 'Block 1', periods_per_week: 6,
  options: [
    { id: 70, subject_id: 1, preferred_teacher_id: 13 },
    { id: 71, subject_id: 2, preferred_teacher_id: null },
  ],
}

let mutations

function renderPanel(props = {}) {
  render(
    <ElectiveBlocksPanel
      schoolId={1}
      classGroupId={100}
      sectionGrade="Grade 11"
      blocks={[]}
      commonSubjectIds={[4]}
      subjects={SUBJECTS}
      teachers={TEACHERS}
      mutations={mutations}
      readOnly={false}
      {...props}
    />,
  )
}

const form = () => screen.getByRole('form', { name: 'Elective block' })
const check = (name) => fireEvent.click(within(form()).getByLabelText(name))

beforeEach(() => {
  mutations = {
    create: vi.fn().mockResolvedValue({}),
    update: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  }
})

describe('adding a block', () => {
  it('saves the name, periods and every chosen option in one request', async () => {
    renderPanel()
    fireEvent.click(screen.getByText('+ Add elective block'))
    fireEvent.change(within(form()).getByLabelText('Periods/week'), { target: { value: '6' } })
    check('Physics')
    check('Accounts')
    pick('Teacher for Physics', 'Mr. Das')
    fireEvent.click(screen.getByText('Save block'))
    await waitFor(() =>
      expect(mutations.create).toHaveBeenCalledWith({
        school_id: 1,
        class_group_id: 100,
        name: 'Block 1',
        periods_per_week: 6,
        section_ids: [100],
        options: [
          { subject_id: 1, preferred_teacher_id: 13, label: null, class_group_ids: null },
          { subject_id: 2, preferred_teacher_id: null, label: null, class_group_ids: null },
        ],
      }),
    )
  })

  it('closes the form once the block is saved', async () => {
    renderPanel()
    fireEvent.click(screen.getByText('+ Add elective block'))
    check('Physics')
    check('Accounts')
    fireEvent.click(screen.getByText('Save block'))
    await waitFor(() => expect(screen.queryByRole('form', { name: 'Elective block' })).toBeNull())
    expect(screen.getByText('+ Add elective block')).toBeInTheDocument()
  })

  it('refuses a block with a single subject without asking the server', () => {
    // One option is not a block - it is an ordinary subject of the section.
    renderPanel()
    fireEvent.click(screen.getByText('+ Add elective block'))
    check('Physics')
    fireEvent.click(screen.getByText('Save block'))
    expect(mutations.create).not.toHaveBeenCalled()
    expect(screen.getByText(/at least two subjects/)).toBeInTheDocument()
  })

  it('refuses a block with no periods', () => {
    renderPanel()
    fireEvent.click(screen.getByText('+ Add elective block'))
    fireEvent.change(within(form()).getByLabelText('Periods/week'), { target: { value: '0' } })
    check('Physics')
    check('Accounts')
    fireEvent.click(screen.getByText('Save block'))
    expect(mutations.create).not.toHaveBeenCalled()
    expect(screen.getByText(/at least 1 period/)).toBeInTheDocument()
  })

  it("does not offer a subject the whole section already takes", () => {
    renderPanel()
    fireEvent.click(screen.getByText('+ Add elective block'))
    expect(within(form()).queryByLabelText('English')).toBeNull()
  })

  it("does not offer a subject already in another of the section's blocks", () => {
    renderPanel({ blocks: [BLOCK] })
    fireEvent.click(screen.getByText('+ Add elective block'))
    expect(within(form()).queryByLabelText('Physics')).toBeNull()
    expect(within(form()).getByLabelText('Chemistry')).toBeInTheDocument()
  })

  it('offers only teachers qualified for the subject and the grade', () => {
    renderPanel()
    fireEvent.click(screen.getByText('+ Add elective block'))
    check('Physics')
    check('Biology')
    // Alphabetical by name, titles ignored: Das before Rao.
    expect(optionsOf('Teacher for Physics')).toEqual(['Any qualified (let solver choose)', 'Mr. Das', 'Mrs. Rao'])
    // Ms. Iyer teaches Biology, but only to Grade 12.
    expect(screen.getByText(/No qualified teacher yet/)).toBeInTheDocument()
  })

  it("shows the server's reason when it refuses", async () => {
    mutations.create.mockRejectedValue(new Error('Physics is already an option in Block 2.'))
    renderPanel()
    fireEvent.click(screen.getByText('+ Add elective block'))
    check('Physics')
    check('Accounts')
    fireEvent.click(screen.getByText('Save block'))
    expect(await screen.findByText('Physics is already an option in Block 2.')).toBeInTheDocument()
    // Still open, with what was entered, so it can be fixed.
    expect(form()).toBeInTheDocument()
  })
})

describe('an existing block', () => {
  it('shows its options and who teaches them', () => {
    renderPanel({ blocks: [BLOCK] })
    expect(screen.getByText('Block 1')).toBeInTheDocument()
    expect(screen.getByText('6 periods/week')).toBeInTheDocument()
    expect(screen.getByText('Physics')).toBeInTheDocument()
    expect(screen.getByText(/Mr\. Das/)).toBeInTheDocument()
    // Accounts has one qualified teacher, who is therefore the one.
    expect(screen.getByText(/Mr\. Khan/)).toBeInTheDocument()
  })

  it('saves edits as the full new set of options', async () => {
    renderPanel({ blocks: [BLOCK] })
    fireEvent.click(screen.getByText('Edit'))
    check('Accounts') // off
    check('Chemistry') // on
    fireEvent.click(screen.getByText('Save block'))
    await waitFor(() =>
      expect(mutations.update).toHaveBeenCalledWith(7, {
        name: 'Block 1',
        periods_per_week: 6,
        section_ids: [100],
        options: [
          { subject_id: 1, preferred_teacher_id: 13, label: null, class_group_ids: null },
          { subject_id: 5, preferred_teacher_id: null, label: null, class_group_ids: null },
        ],
      }),
    )
  })

  it('deletes after confirming', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPanel({ blocks: [BLOCK] })
    fireEvent.click(screen.getByText('Delete'))
    await waitFor(() => expect(mutations.delete).toHaveBeenCalledWith(7))
  })

  it('does not delete when the confirmation is cancelled', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderPanel({ blocks: [BLOCK] })
    fireEvent.click(screen.getByText('Delete'))
    expect(mutations.delete).not.toHaveBeenCalled()
  })

  it('cannot be changed by a viewer', () => {
    renderPanel({ blocks: [BLOCK], readOnly: true })
    expect(screen.queryByText('Edit')).toBeNull()
    expect(screen.queryByText('Delete')).toBeNull()
    expect(screen.queryByText('+ Add elective block')).toBeNull()
  })
})

describe('a block shared with other sections', () => {
  const SECTIONS = [
    { id: 100, grade: 'Grade 11', name: 'A' },
    { id: 101, grade: 'Grade 11', name: 'B' },
    { id: 200, grade: 'Grade 12', name: 'A' },
  ]

  beforeEach(() => {
    mutations = { create: vi.fn(() => Promise.resolve()), update: vi.fn(() => Promise.resolve()), delete: vi.fn() }
  })

  it('pools another section into every class, and can keep one class for one section', async () => {
    renderPanel({ classGroups: SECTIONS })
    fireEvent.click(screen.getByText('+ Add elective block'))
    fireEvent.click(screen.getByText('+ Share with other sections'))
    check('Grade 11 B')
    check('Physics')
    check('Accounts')
    // Accounts only for 11 A's students.
    const accounts = within(form()).getByRole('group', { name: 'Students in Accounts' })
    fireEvent.click(within(accounts).getByText('Grade 11 B'))
    fireEvent.click(screen.getByText('Save block'))
    await waitFor(() =>
      expect(mutations.create).toHaveBeenCalledWith(expect.objectContaining({
        section_ids: [100, 101],
        options: [
          { subject_id: 1, preferred_teacher_id: null, label: null, class_group_ids: null },
          { subject_id: 2, preferred_teacher_id: null, label: null, class_group_ids: [100] },
        ],
      })),
    )
  })

  it('one subject alone is a combined class once sections are shared', async () => {
    renderPanel({ classGroups: SECTIONS })
    fireEvent.click(screen.getByText('+ Add elective block'))
    fireEvent.click(screen.getByText('+ Share with other sections'))
    check('Grade 11 B')
    check('Physics')
    fireEvent.click(screen.getByText('Save block'))
    await waitFor(() => expect(mutations.create).toHaveBeenCalled())
  })

  it('splits a subject into two named groups taught at once', async () => {
    renderPanel({ classGroups: SECTIONS })
    fireEvent.click(screen.getByText('+ Add elective block'))
    check('Physics')
    check('Accounts')
    fireEvent.click(within(form()).getAllByText('Split into another group')[0])
    fireEvent.click(screen.getByText('Save block'))
    await waitFor(() =>
      expect(mutations.create).toHaveBeenCalledWith(expect.objectContaining({
        options: [
          { subject_id: 1, preferred_teacher_id: null, label: 'Group 1', class_group_ids: null },
          { subject_id: 1, preferred_teacher_id: null, label: 'Group 2', class_group_ids: null },
          { subject_id: 2, preferred_teacher_id: null, label: null, class_group_ids: null },
        ],
      })),
    )
  })

  it('refuses to leave a section with no class to go to', async () => {
    renderPanel({ classGroups: SECTIONS })
    fireEvent.click(screen.getByText('+ Add elective block'))
    fireEvent.click(screen.getByText('+ Share with other sections'))
    check('Grade 11 B')
    check('Physics')
    fireEvent.click(within(within(form()).getByRole('group', { name: 'Students in Physics' })).getByText('Grade 11 B'))
    fireEvent.click(screen.getByText('Save block'))
    expect(await screen.findByText(/No subject in this block is for Grade 11 B/)).toBeTruthy()
    expect(mutations.create).not.toHaveBeenCalled()
  })

  it('says which sections share a saved block', () => {
    renderPanel({
      classGroups: SECTIONS,
      blocks: [{ ...BLOCK, section_ids: [100, 101], options: [
        { id: 70, subject_id: 1, preferred_teacher_id: 13, class_group_ids: null },
        { id: 71, subject_id: 2, preferred_teacher_id: null, class_group_ids: [101], label: 'B only' },
      ] }],
    })
    expect(screen.getByText('Shared: Grade 11 A, Grade 11 B')).toBeTruthy()
    expect(screen.getByText('(B only)')).toBeTruthy()
  })
})
