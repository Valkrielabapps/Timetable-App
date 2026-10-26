import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SubstitutionsTab from './SubstitutionsTab'
import { optionsOf, pick } from '../test/pick'

const api = vi.hoisted(() => ({
  listPeriods: vi.fn(),
  listTimetables: vi.fn(),
  listSubstitutionLogs: vi.fn(),
  getTimetable: vi.fn(),
  getGradeCategories: vi.fn(),
  saveSubstitutionLog: vi.fn(),
  getSubstitutionSummary: vi.fn(),
  downloadSubstitutionSummaryPdf: vi.fn(),
}))
vi.mock('../api', () => ({ api }))

/**
 * Arranging cover by date and by part of the school.
 *
 * Monday has two periods. Mrs. Rao teaches Grade 3 A (primary) Maths in
 * both; Mr. Khan teaches Grade 7 A (middle) Science in period 1. Ms. Iyer
 * (primary) and Mr. Bose (middle) both teach Maths, only on Tuesday, so
 * both are free on Monday. Dr. Sen teaches nothing.
 */

const MONDAY = '2026-10-26'
const PERIODS = [
  { id: 1, day_of_week: 0, order: 0, number: 1, label: null, is_break: false },
  { id: 2, day_of_week: 0, order: 1, number: 2, label: null, is_break: false },
  { id: 3, day_of_week: 1, order: 0, number: 1, label: null, is_break: false },
]
const TEACHERS = [
  { id: 10, name: 'Mrs. Rao', qualified_subject_ids: [1] },
  { id: 11, name: 'Mr. Khan', qualified_subject_ids: [2] },
  { id: 12, name: 'Ms. Iyer', qualified_subject_ids: [1] },
  { id: 13, name: 'Mr. Bose', qualified_subject_ids: [1] },
  { id: 14, name: 'Dr. Sen', qualified_subject_ids: [] },
]
const CLASSES = [
  { id: 100, grade: 'Grade 3', name: 'A' },
  { id: 200, grade: 'Grade 7', name: 'A' },
]
let nextId = 1
const lesson = (classId, subjectId, subject, teacherId, periodId) => ({
  id: nextId++, class_group_id: classId, subject_id: subjectId, subject_name: subject, teacher_id: teacherId,
  period_id: periodId, elective_block_id: null,
})
const TIMETABLE = {
  status: 'draft',
  entries: [
    lesson(100, 1, 'Maths', 10, 1),
    lesson(100, 1, 'Maths', 10, 2),
    lesson(200, 2, 'Science', 11, 1),
    lesson(100, 1, 'Maths', 12, 3),
    lesson(200, 1, 'Maths', 13, 3),
  ],
}

function renderTab({ logs = [], readOnly = false } = {}) {
  api.listPeriods.mockResolvedValue(PERIODS)
  api.listTimetables.mockResolvedValue([{ id: 3, status: 'draft' }])
  api.listSubstitutionLogs.mockResolvedValue(logs)
  api.getTimetable.mockResolvedValue({ ...TIMETABLE, id: 3 })
  api.getGradeCategories.mockResolvedValue([
    { grade: 'Grade 3', category: 'primary', default: 'primary' },
    { grade: 'Grade 7', category: 'middle', default: 'middle' },
  ])
  render(<SubstitutionsTab schoolId={1} teachers={TEACHERS} classGroups={CLASSES} readOnly={readOnly} />)
}

async function choose(part, date = MONDAY) {
  fireEvent.change(await screen.findByLabelText('Date'), { target: { value: date } })
  fireEvent.click(screen.getByRole('radio', { name: part }))
}

const absentList = () =>
  screen.queryAllByRole('checkbox')
    .filter((c) => !c.getAttribute('aria-label'))
    .map((c) => c.closest('label').textContent)
const pickers = () => screen.queryAllByRole('combobox', { name: /^Substitute for/ })
const shown = () => pickers().map((p) => p.textContent.replace('▾', '').trim())

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
})

describe('choosing the day and the part of the school', () => {
  it('shows the date with its weekday', async () => {
    renderTab()
    await choose('Primary')
    expect(screen.getByText('Monday, 26 October 2026')).toBeInTheDocument()
  })

  it('asks for the part of the school before listing anyone', async () => {
    renderTab()
    fireEvent.change(await screen.findByLabelText('Date'), { target: { value: MONDAY } })
    expect(absentList()).toEqual([])
    expect(screen.getByText('Choose which part of the school to arrange cover for.')).toBeInTheDocument()
  })

  it('lists only the teachers with lessons in that part that day', async () => {
    renderTab()
    await choose('Primary')
    expect(absentList()).toEqual(['Mrs. Rao'])
    fireEvent.click(screen.getByRole('radio', { name: 'Middle' }))
    expect(absentList()).toEqual(['Mr. Khan'])
    fireEvent.click(screen.getByRole('radio', { name: 'Whole school' }))
    expect(absentList()).toEqual(['Mr. Khan', 'Mrs. Rao'])
    // On Tuesday it's the Tuesday teachers.
    fireEvent.change(screen.getByLabelText('Date'), { target: { value: '2026-10-27' } })
    expect(absentList()).toEqual(['Mr. Bose', 'Ms. Iyer'])
  })

  it('remembers the part chosen last time', async () => {
    renderTab()
    await choose('Middle')
    expect(window.localStorage.getItem('substitutions-category-1')).toBe('middle')
  })
})

describe('who is away, and when', () => {
  it('a whole day off needs cover for every lesson', async () => {
    renderTab()
    await choose('Primary')
    fireEvent.click(screen.getByLabelText('Mrs. Rao'))
    expect(screen.getByText(/Period 1 • Maths • Absent: Mrs\. Rao/)).toBeInTheDocument()
    expect(screen.getByText(/Period 2 • Maths • Absent: Mrs\. Rao/)).toBeInTheDocument()
  })

  it('away for some periods needs cover for only the periods ticked', async () => {
    renderTab()
    await choose('Primary')
    fireEvent.click(screen.getByLabelText('Mrs. Rao'))
    fireEvent.click(screen.getByLabelText('Some periods'))
    expect(screen.getByText('No lessons need cover for the periods chosen.')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Mrs. Rao away Period 2'))
    expect(screen.queryByText(/Period 1 • Maths/)).not.toBeInTheDocument()
    expect(screen.getByText(/Period 2 • Maths • Absent: Mrs\. Rao/)).toBeInTheDocument()
  })

  it('a teacher away for some periods can still cover in the others', async () => {
    renderTab()
    await choose('Whole school')
    fireEvent.click(screen.getByLabelText('Mr. Khan'))
    fireEvent.click(screen.getByLabelText('Some periods'))
    fireEvent.click(screen.getByLabelText('Mr. Khan away Period 1'))
    fireEvent.click(screen.getByLabelText('Mrs. Rao'))
    // Two "Some periods" now; Mrs. Rao's is the second.
    fireEvent.click(screen.getAllByLabelText('Some periods')[1])
    fireEvent.click(screen.getByLabelText('Mrs. Rao away Period 2'))
    const [khanLesson, raoLesson] = pickers()
    expect(khanLesson).toHaveAccessibleName('Substitute for Science, Period 1, Grade 7 A')
    expect(optionsOf(raoLesson.getAttribute('aria-label'))).toContain('Mr. Khan')
  })
})

describe('suggested substitutes', () => {
  it('from the same part of the school first, then the rest', async () => {
    renderTab()
    await choose('Primary')
    fireEvent.click(screen.getByLabelText('Mrs. Rao'))
    fireEvent.click(screen.getByLabelText('Some periods'))
    fireEvent.click(screen.getByLabelText('Mrs. Rao away Period 1'))
    // Mr. Khan teaches at period 1; Mrs. Rao is the one away.
    expect(optionsOf('Substitute for Maths, Period 1, Grade 3 A').filter((o) => o !== 'Not covered')).toEqual([
      'Ms. Iyer', 'Mr. Bose', 'Dr. Sen',
    ])
    expect(screen.getByText('Suggested: qualified, free, in Primary')).toBeInTheDocument()
    expect(screen.getByText('Free in other parts of the school')).toBeInTheDocument()
  })

  it('fills in the same-part suggestion to start with', async () => {
    renderTab()
    await choose('Primary')
    fireEvent.click(screen.getByLabelText('Mrs. Rao'))
    await waitFor(() => expect(shown()).toEqual(['Ms. Iyer', 'Ms. Iyer']))
  })

  it('leaves out anyone already covering at that period in another part', async () => {
    renderTab({
      logs: [{
        id: 5, date: MONDAY, category: 'middle', day_of_week: 0, created_at: `${MONDAY}T08:00:00`,
        absences: [{ teacher_id: 11, period_ids: null }],
        changes: [{ period_id: 1, class_group_id: 200, absent_teacher_id: 11, substituting_teacher_id: 12 }],
      }],
    })
    await choose('Primary')
    fireEvent.click(screen.getByLabelText('Mrs. Rao'))
    await waitFor(() => expect(pickers()[1]).toHaveTextContent('Ms. Iyer'))
    // Ms. Iyer is with Grade 7 at period 1; nobody else in primary is free.
    expect(pickers()[0]).toHaveTextContent('Not covered')
    expect(optionsOf(pickers()[0].getAttribute('aria-label'))).not.toContain('Ms. Iyer')
  })
})

describe('saved cover elsewhere and choices made', () => {
  it('leaves out anyone saved as away in another part', async () => {
    renderTab({
      logs: [{
        id: 5, date: MONDAY, category: 'middle', day_of_week: 0, created_at: `${MONDAY}T08:00:00`,
        absences: [{ teacher_id: 13, period_ids: null }], changes: [],
      }],
    })
    await choose('Primary')
    fireEvent.click(screen.getByLabelText('Mrs. Rao'))
    const options = optionsOf(pickers()[0].getAttribute('aria-label'))
    expect(options).toContain('Dr. Sen')
    expect(options).not.toContain('Mr. Bose')
  })

  it('a lesson chosen to be left uncovered stays so', async () => {
    renderTab()
    await choose('Whole school')
    fireEvent.click(screen.getByLabelText('Mrs. Rao'))
    await waitFor(() => expect(shown()).toEqual(['Ms. Iyer', 'Ms. Iyer']))
    pick(pickers()[0].getAttribute('aria-label'), 'Not covered')
    // Another absence brings in another lesson; the choice above is kept.
    fireEvent.click(screen.getByLabelText('Mr. Khan'))
    await waitFor(() => expect(pickers()).toHaveLength(3))
    expect(shown()[0]).toBe('Not covered')
  })
})

describe('saving', () => {
  const SUMMARY = {
    date: MONDAY, weekday: 'Monday', category: 'primary', category_label: 'Primary',
    on_leave: [{ teacher_id: 10, teacher: 'Mrs. Rao', periods: null }],
    rows: [
      { period: 'Period 1', class_group: 'Grade 3 - A', subject: 'Maths', category: 'primary',
        category_label: 'Primary', absent_teacher: 'Mrs. Rao', substitute: 'Ms. Iyer' },
      { period: 'Period 2', class_group: 'Grade 3 - A', subject: 'Maths', category: 'primary',
        category_label: 'Primary', absent_teacher: 'Mrs. Rao', substitute: null },
    ],
    uncovered: 1,
  }

  it('saves the date, the part, who is away and every lesson - uncovered ones too', async () => {
    api.saveSubstitutionLog.mockResolvedValue({
      id: 9, date: MONDAY, category: 'primary', day_of_week: 0, created_at: `${MONDAY}T09:00:00`,
      absences: [{ teacher_id: 10, period_ids: null }], changes: [],
    })
    api.getSubstitutionSummary.mockResolvedValue(SUMMARY)
    renderTab()
    await choose('Primary')
    fireEvent.click(screen.getByLabelText('Mrs. Rao'))
    await waitFor(() => expect(pickers()[1]).toHaveTextContent('Ms. Iyer'))
    pick(pickers()[1].getAttribute('aria-label'), 'Not covered')
    expect(screen.getByText('1 lesson without a substitute will be saved as not covered.')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Save & View Summary'))

    await screen.findByRole('region', { name: 'Substitution summary' })
    expect(api.saveSubstitutionLog).toHaveBeenCalledWith(1, {
      date: MONDAY,
      category: 'primary',
      absences: [{ teacher_id: 10, period_ids: null }],
      changes: [
        { period_id: 1, absent_teacher_id: 10, substituting_teacher_id: 12, class_group_id: 100, subject_id: 1 },
        { period_id: 2, absent_teacher_id: 10, substituting_teacher_id: null, class_group_id: 100, subject_id: 1 },
      ],
    })
    expect(api.getSubstitutionSummary).toHaveBeenCalledWith(1, MONDAY, 'primary')
    const summary = screen.getByRole('region', { name: 'Substitution summary' })
    expect(within(summary).getByText('Monday, 26 October 2026')).toBeInTheDocument()
    expect(within(summary).getByText('Mrs. Rao (whole day)')).toBeInTheDocument()
    expect(within(summary).getAllByText('Not covered')).toHaveLength(1)
    expect(within(summary).getByText('1 period still needs cover.')).toBeInTheDocument()
  })

  it('saves partial leave as the periods ticked, and the whole school as no part', async () => {
    api.saveSubstitutionLog.mockResolvedValue({
      id: 9, date: MONDAY, category: null, day_of_week: 0, created_at: `${MONDAY}T09:00:00`, absences: [], changes: [],
    })
    api.getSubstitutionSummary.mockResolvedValue({ ...SUMMARY, category: null, category_label: 'Whole school' })
    renderTab()
    await choose('Whole school')
    fireEvent.click(screen.getByLabelText('Mrs. Rao'))
    fireEvent.click(screen.getByLabelText('Some periods'))
    fireEvent.click(screen.getByLabelText('Mrs. Rao away Period 2'))
    fireEvent.click(screen.getByText('Save & View Summary'))
    await waitFor(() => expect(api.saveSubstitutionLog).toHaveBeenCalled())
    const body = api.saveSubstitutionLog.mock.calls[0][1]
    expect(body.category).toBeNull()
    expect(body.absences).toEqual([{ teacher_id: 10, period_ids: [2] }])
    expect(body.changes.map((c) => c.period_id)).toEqual([2])
    await waitFor(() => expect(api.getSubstitutionSummary).toHaveBeenCalledWith(1, MONDAY, null))
  })

  it('picks up what was saved for the same date and part', async () => {
    renderTab({
      logs: [{
        id: 5, date: MONDAY, category: 'primary', day_of_week: 0, created_at: `${MONDAY}T08:00:00`,
        absences: [{ teacher_id: 10, period_ids: [2] }],
        changes: [{ period_id: 2, class_group_id: 100, absent_teacher_id: 10, substituting_teacher_id: 13 }],
      }],
    })
    await choose('Primary')
    expect(screen.getByLabelText('Mrs. Rao')).toBeChecked()
    expect(screen.getByLabelText('Mrs. Rao away Period 1')).not.toBeChecked()
    expect(screen.getByLabelText('Mrs. Rao away Period 2')).toBeChecked()
    expect(shown()).toEqual(['Mr. Bose'])
    expect(screen.getByText('Saved earlier for this date — saving again replaces it.')).toBeInTheDocument()
    // Another part of the school starts empty.
    fireEvent.click(screen.getByRole('radio', { name: 'Middle' }))
    expect(screen.getByLabelText('Mr. Khan')).not.toBeChecked()
  })

  it('a viewer can look but not save', async () => {
    renderTab({ readOnly: true })
    await choose('Primary')
    expect(screen.getByLabelText('Mrs. Rao')).toBeDisabled()
    expect(screen.queryByText('Save & View Summary')).not.toBeInTheDocument()
  })
})

describe('history', () => {
  it('one row per date, newest first, opening each part saved', async () => {
    api.getSubstitutionSummary.mockResolvedValue({
      date: MONDAY, weekday: 'Monday', category: null, category_label: 'Whole school',
      on_leave: [], rows: [], uncovered: 0,
    })
    const log = (id, date, category, subs) => ({
      id, date, category, day_of_week: 0, created_at: `${date}T08:00:00`, absences: [],
      changes: subs.map((s) => ({ period_id: 1, class_group_id: 100, absent_teacher_id: 10, substituting_teacher_id: s })),
    })
    renderTab({
      logs: [
        log(1, '2026-10-19', null, [12]),
        log(2, MONDAY, 'middle', [12, null]),
        log(3, MONDAY, 'primary', [13]),
        // From before dates were kept: the day it was saved.
        { ...log(4, null, null, [12]), created_at: '2026-10-12T08:00:00' },
      ],
    })
    fireEvent.click(await screen.findByText('History'))
    const rows = screen.getAllByRole('listitem')
    expect(rows.map((r) => within(r).getByText(/2026$/).textContent)).toEqual([
      'Monday, 26 October 2026', 'Monday, 19 October 2026', 'Monday, 12 October 2026',
    ])
    expect(rows[0]).toHaveTextContent('3 lessons needed cover · 1 not covered')
    expect(within(rows[0]).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Whole school', 'Primary', 'Middle',
    ])
    expect(within(rows[1]).getAllByRole('button').map((b) => b.textContent)).toEqual(['Whole school'])
    fireEvent.click(within(rows[0]).getByText('Whole school'))
    await waitFor(() => expect(api.getSubstitutionSummary).toHaveBeenCalledWith(1, MONDAY, null))
    expect(await screen.findByRole('region', { name: 'Substitution summary' })).toBeInTheDocument()
  })
})
