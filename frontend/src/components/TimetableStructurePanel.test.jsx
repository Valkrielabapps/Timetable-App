import React from 'react'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TimetableStructurePanel from './TimetableStructurePanel'

const api = vi.hoisted(() => ({ getTimetableStructure: vi.fn(), saveTimetableStructure: vi.fn() }))
vi.mock('../api', () => ({ api }))

/**
 * Setting the week up once: working days, periods per day, breaks, and the
 * class teacher and zero periods - instead of adding every period by hand.
 */

const SAVED = {
  days: [0, 1, 2, 3, 4],
  periods_per_day: 8,
  short_days: {},
  breaks: [{ after: 4, label: 'Lunch' }],
  class_teacher_period: { enabled: false, after: 0 },
  zero_period: { enabled: false, scope: 'school', placements: [] },
}

const REPORT = {
  changed: true, periods_added: 5, periods_removed: 0, timetable_entries_removed: 0,
  unavailability_removed: [], rules_out_of_range: [], sections_without_class_teacher: [],
  timetable_outdated: false,
}

let onSaved

async function renderPanel({ structure = SAVED, irregular = false, readOnly = false, grades = ['Grade 6', 'Grade 7'] } = {}) {
  api.getTimetableStructure.mockResolvedValue({ structure, irregular })
  render(<TimetableStructurePanel schoolId={1} grades={grades} onSaved={onSaved} readOnly={readOnly} />)
  await screen.findByText('Working days')
}

const preview = () => screen.getByLabelText('Preview of the day')
const save = () => fireEvent.click(screen.getByRole('button', { name: /Save changes|Create periods/ }))
const sent = () => api.saveTimetableStructure.mock.calls.at(-1)[1]

beforeEach(() => {
  vi.clearAllMocks()
  onSaved = vi.fn()
  api.saveTimetableStructure.mockImplementation(async (_id, structure) => ({ structure, report: REPORT }))
})

describe('the structure editor', () => {
  it('shows the saved structure and a preview of the day', async () => {
    await renderPanel()
    expect(screen.getByLabelText('Periods per day')).toHaveValue(8)
    expect(within(preview()).getByText('Lunch')).toBeInTheDocument()
    expect(within(preview()).getByText('Mon, Tue, Wed, Thu, Fri')).toBeInTheDocument()
  })

  it('sets the number of periods once for every day', async () => {
    await renderPanel()
    fireEvent.change(screen.getByLabelText('Periods per day'), { target: { value: '6' } })
    save()
    await waitFor(() => expect(sent().periods_per_day).toBe(6))
    expect(sent().days).toEqual([0, 1, 2, 3, 4])
  })

  it('adds a working day', async () => {
    await renderPanel()
    fireEvent.click(screen.getByRole('button', { name: 'Sat' }))
    save()
    await waitFor(() => expect(sent().days).toEqual([0, 1, 2, 3, 4, 5]))
  })

  it('gives one day fewer periods', async () => {
    await renderPanel({ structure: { ...SAVED, days: [0, 1, 2, 3, 4, 5] } })
    fireEvent.change(screen.getByLabelText('Add a shorter day'), { target: { value: '5' } })
    fireEvent.change(screen.getByLabelText('Periods on Saturday'), { target: { value: '3' } })
    save()
    await waitFor(() => expect(sent().short_days).toEqual({ 5: 3 }))
  })

  it('adds and names a break', async () => {
    await renderPanel({ structure: { ...SAVED, breaks: [] } })
    fireEvent.click(screen.getByText('+ Add a break'))
    fireEvent.change(screen.getByLabelText('Break 1 comes after'), { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText('Break 1 name'), { target: { value: 'Recess' } })
    save()
    await waitFor(() => expect(sent().breaks).toEqual([{ after: 3, label: 'Recess' }]))
  })

  it('turns on a class teacher period at the start of the day', async () => {
    await renderPanel()
    fireEvent.click(screen.getByRole('switch', { name: 'Class teacher period' }))
    expect(within(preview()).getByText('Class teacher')).toBeInTheDocument()
    save()
    await waitFor(() => expect(sent().class_teacher_period).toEqual({ enabled: true, after: 0 }))
  })

  it('can put the class teacher period after a given period', async () => {
    await renderPanel()
    fireEvent.click(screen.getByRole('switch', { name: 'Class teacher period' }))
    fireEvent.change(screen.getByLabelText('When the class teacher period is'), { target: { value: '2' } })
    save()
    await waitFor(() => expect(sent().class_teacher_period).toEqual({ enabled: true, after: 2 }))
  })
})

describe('the zero period', () => {
  async function zeroOn() {
    await renderPanel()
    fireEvent.click(screen.getByRole('switch', { name: 'Zero period' }))
  }

  it('starts as the whole school, first thing every day', async () => {
    await zeroOn()
    save()
    await waitFor(() =>
      expect(sent().zero_period).toEqual({
        enabled: true, scope: 'school', placements: [{ grade: null, every_day: 1, by_day: null }],
      }),
    )
  })

  it('reads as a slot between periods when it is the same for everyone', async () => {
    await zeroOn()
    const select = screen.getByLabelText('Zero period for the whole school')
    expect(within(select).getByText('Before period 1')).toBeInTheDocument()
    expect(within(select).getByText('After period 8')).toBeInTheDocument()
    fireEvent.change(select, { target: { value: '9' } })
    expect(within(preview()).getAllByText(/\S/).at(-1)).toHaveTextContent('Zero')
  })

  it('can be at a different point each day', async () => {
    await zeroOn()
    fireEvent.click(screen.getByLabelText('Different each day for the whole school'))
    fireEvent.change(screen.getByLabelText('Zero period for the whole school on Tuesday'), { target: { value: '7' } })
    save()
    await waitFor(() =>
      expect(sent().zero_period.placements[0]).toEqual({
        grade: null, every_day: null, by_day: { 0: 1, 1: 7, 2: 1, 3: 1, 4: 1 },
      }),
    )
  })

  it('can differ by grade', async () => {
    await zeroOn()
    fireEvent.click(screen.getByLabelText('Different by grade'))
    fireEvent.change(screen.getByLabelText('Zero period for Grade 7'), { target: { value: '9' } })
    save()
    await waitFor(() =>
      expect(sent().zero_period).toEqual({
        enabled: true,
        scope: 'grade',
        placements: [
          { grade: 'Grade 6', every_day: 1, by_day: null },
          { grade: 'Grade 7', every_day: 9, by_day: null },
        ],
      }),
    )
  })

  it('numbers its periods once it differs by grade, since others are taught in it', async () => {
    await zeroOn()
    fireEvent.click(screen.getByLabelText('Different by grade'))
    expect(within(screen.getByLabelText('Zero period for Grade 6')).getByText('Period 9')).toBeInTheDocument()
    expect(within(preview()).getByText('9')).toBeInTheDocument()
  })

  it('can leave a grade without one', async () => {
    await zeroOn()
    fireEvent.click(screen.getByLabelText('Different by grade'))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Grade 6' }))
    save()
    await waitFor(() => expect(sent().zero_period.placements.map((p) => p.grade)).toEqual(['Grade 7']))
  })

  it('cannot differ by grade in a school with no grades yet', async () => {
    await renderPanel({ grades: [] })
    fireEvent.click(screen.getByRole('switch', { name: 'Zero period' }))
    expect(screen.getByLabelText('Different by grade')).toBeDisabled()
  })
})

describe('saving', () => {
  it('refreshes the periods afterwards', async () => {
    await renderPanel()
    save()
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
  })

  it('says what else changed', async () => {
    api.saveTimetableStructure.mockResolvedValue({
      structure: SAVED,
      report: {
        ...REPORT,
        timetable_outdated: true,
        unavailability_removed: ['Mrs. Rao: 1 unavailable period no longer exists'],
        sections_without_class_teacher: ['Grade 6 - B'],
      },
    })
    await renderPanel()
    save()
    expect(await screen.findByText(/generate it again/)).toBeInTheDocument()
    expect(screen.getByText(/Mrs. Rao: 1 unavailable period no longer exists/)).toBeInTheDocument()
    expect(screen.getByText(/No class teacher yet for Grade 6 - B/)).toBeInTheDocument()
  })

  it("shows the server's reason when it refuses", async () => {
    api.saveTimetableStructure.mockRejectedValue(new Error('There are two breaks after period 3.'))
    await renderPanel()
    save()
    expect(await screen.findByText('There are two breaks after period 3.')).toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('creates periods for a school that has none yet', async () => {
    await renderPanel({ structure: null })
    expect(screen.getByRole('button', { name: 'Create periods' })).toBeInTheDocument()
  })

  it('warns that saving will even out days that differ', async () => {
    await renderPanel({ irregular: true })
    expect(screen.getByText(/don't follow one pattern/)).toBeInTheDocument()
  })

  it('cannot be changed by a viewer', async () => {
    await renderPanel({ readOnly: true })
    expect(screen.getByLabelText('Periods per day')).toBeDisabled()
    expect(screen.queryByRole('button', { name: /Save changes/ })).toBeNull()
  })
})
