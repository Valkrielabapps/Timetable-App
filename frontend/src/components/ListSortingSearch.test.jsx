import React from 'react'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeachersSection from './TeachersSection'
import SubjectsSection from './SubjectsSection'

vi.mock('../api', () => ({ api: { bulkImportTemplateUrl: () => '#' } }))

const hooks = vi.hoisted(() => ({ timetable: null }))
vi.mock('../hooks/useSchoolData', () => ({
  useElectiveBlocks: () => ({ data: [] }),
  useTimetables: () => ({ data: hooks.timetable ? [{ id: 1, status: 'draft' }] : [] }),
  useTimetable: () => ({ data: hooks.timetable }),
}))

/**
 * Searching and sorting the Teachers and Subjects lists.
 *
 * Both are alphabetical by default - a teacher by name, never by title - and
 * can be sorted by what they're doing. A teacher's periods are the real ones
 * once a timetable exists: what the generator gave them, not only what was
 * pinned on section plans, which is how one teacher was shown "10 periods"
 * while teaching 33.
 */

const SUBJECTS = [{ id: 1, name: 'Hindi' }, { id: 2, name: 'Maths' }, { id: 3, name: 'Art' }, { id: 4, name: 'Cursive' }]

const teacher = (id, name, subjects, grades = [], extra = {}) => ({
  id, name, qualified_subject_ids: subjects, qualified_grades: grades, unavailable_period_ids: [],
  max_periods_per_week: null, is_assistant_eligible: false, ...extra,
})
const TEACHERS = [
  teacher(1, 'Mrs. Zareena', [2, 3], ['Grade 3']),
  teacher(2, 'Vinita', [1, 4], ['Grade 3', 'Grade 4', 'Grade 5']),
  teacher(3, 'Mr. Anil', [2]),
  teacher(4, 'Ms. Shallu', [2, 1, 3], ['Grade 10']),
]
const SECTIONS = [{ id: 100, grade: 'Grade 4', name: 'A' }, { id: 101, grade: 'Grade 4', name: 'B' }]
// Vinita is pinned to two Hindi classes - 10 periods on the plans.
const REQUIREMENTS = [
  { id: 1, class_group_id: 100, subject_id: 1, periods_per_week: 5, preferred_teacher_id: 2 },
  { id: 2, class_group_id: 101, subject_id: 1, periods_per_week: 5, preferred_teacher_id: 2 },
  { id: 3, class_group_id: 100, subject_id: 2, periods_per_week: 6, preferred_teacher_id: null },
]

// The generated timetable: Vinita actually has 4 periods, Anil 2, Shallu 1.
const entry = (id, teacherId, periodId) => ({ id, teacher_id: teacherId, assistant_teacher_id: null, period_id: periodId })
const TIMETABLE = {
  id: 1, status: 'draft',
  entries: [entry(1, 2, 1), entry(2, 2, 2), entry(3, 2, 3), entry(4, 2, 4), entry(5, 3, 1), entry(6, 3, 2), entry(7, 4, 5)],
}

const names = () => [...document.querySelectorAll('span.font-medium')].map((el) => el.textContent)

function renderTeachers() {
  render(
    <TeachersSection
      schoolId={1}
      teachers={TEACHERS}
      subjects={SUBJECTS}
      classGroups={SECTIONS}
      allRequirements={REQUIREMENTS}
      onTeachersChanged={{ create: vi.fn(), update: vi.fn().mockResolvedValue({}), delete: vi.fn(), reload: vi.fn() }}
      readOnly={false}
    />,
  )
}

beforeEach(() => {
  hooks.timetable = null
  window.localStorage.clear()
})

describe('the Teachers list', () => {
  it('is alphabetical by first name, titles ignored', () => {
    renderTeachers()
    expect(names()).toEqual(['Mr. Anil', 'Ms. Shallu', 'Vinita', 'Mrs. Zareena'])
  })

  it('finds a teacher by name', () => {
    renderTeachers()
    fireEvent.change(screen.getByLabelText('Search teachers'), { target: { value: 'vin' } })
    expect(names()).toEqual(['Vinita'])
  })

  it('finds teachers by subject', () => {
    renderTeachers()
    fireEvent.change(screen.getByLabelText('Search teachers'), { target: { value: 'hindi' } })
    expect(names()).toEqual(['Ms. Shallu', 'Vinita'])
  })

  it('finds teachers by grade', () => {
    renderTeachers()
    fireEvent.change(screen.getByLabelText('Search teachers'), { target: { value: 'grade 5' } })
    expect(names()).toEqual(['Vinita'])
  })

  it('says when nobody matches', () => {
    renderTeachers()
    fireEvent.change(screen.getByLabelText('Search teachers'), { target: { value: 'zzz' } })
    expect(screen.getByText('No teachers match "zzz".')).toBeInTheDocument()
  })

  it('sorts Z to A', () => {
    renderTeachers()
    fireEvent.change(screen.getByLabelText('Sort teachers'), { target: { value: 'name-desc' } })
    expect(names()).toEqual(['Mrs. Zareena', 'Vinita', 'Ms. Shallu', 'Mr. Anil'])
  })

  it('sorts by the periods in the timetable, most first', () => {
    hooks.timetable = TIMETABLE
    renderTeachers()
    fireEvent.change(screen.getByLabelText('Sort teachers'), { target: { value: 'load-desc' } })
    expect(names()).toEqual(['Vinita', 'Mr. Anil', 'Ms. Shallu', 'Mrs. Zareena'])
  })

  it('sorts by periods, fewest first', () => {
    hooks.timetable = TIMETABLE
    renderTeachers()
    fireEvent.change(screen.getByLabelText('Sort teachers'), { target: { value: 'load-asc' } })
    expect(names()).toEqual(['Mrs. Zareena', 'Ms. Shallu', 'Mr. Anil', 'Vinita'])
  })

  it('sorts by how many subjects they teach', () => {
    renderTeachers()
    fireEvent.change(screen.getByLabelText('Sort teachers'), { target: { value: 'subjects' } })
    expect(names()).toEqual(['Ms. Shallu', 'Vinita', 'Mrs. Zareena', 'Mr. Anil'])
  })

  it('sorts by grades taught, lowest first, and "all grades" last', () => {
    renderTeachers()
    fireEvent.change(screen.getByLabelText('Sort teachers'), { target: { value: 'grades' } })
    // Grade 3 (Vinita and Zareena, by name), then Grade 10, then no restriction.
    expect(names()).toEqual(['Vinita', 'Mrs. Zareena', 'Ms. Shallu', 'Mr. Anil'])
  })

  it('remembers the sort on this device', () => {
    renderTeachers()
    fireEvent.change(screen.getByLabelText('Sort teachers'), { target: { value: 'name-desc' } })
    expect(window.localStorage.getItem('timetablz.teachers.sort')).toBe('name-desc')
  })

  it('shows the real load once a timetable exists, with what is pinned beside it', () => {
    hooks.timetable = TIMETABLE
    renderTeachers()
    const vinita = screen.getByText('Vinita').closest('.group')
    expect(within(vinita).getByText('4 periods/week')).toBeInTheDocument()
    expect(within(vinita).getByText('in the timetable · 10 pinned on plans')).toBeInTheDocument()
  })

  it('shows what is pinned until there is a timetable, and says so', () => {
    renderTeachers()
    const vinita = screen.getByText('Vinita').closest('.group')
    expect(within(vinita).getByText('10 periods/week')).toBeInTheDocument()
    expect(within(vinita).getByText('pinned on plans (generate for the real load)')).toBeInTheDocument()
  })

  it('counts assisting as being busy, once per period', () => {
    hooks.timetable = {
      id: 1, status: 'draft',
      entries: [
        { id: 1, teacher_id: 3, assistant_teacher_id: 2, period_id: 9 }, // assisting
        entry(2, 2, 8), // teaching
        { id: 3, teacher_id: 4, assistant_teacher_id: 2, period_id: 8 }, // same period again
      ],
    }
    renderTeachers()
    expect(within(screen.getByText('Vinita').closest('.group')).getByText('2 periods/week')).toBeInTheDocument()
  })

  it("lists a teacher's subjects alphabetically", () => {
    renderTeachers()
    const shallu = screen.getByText('Ms. Shallu').closest('.group')
    const chips = [...shallu.querySelectorAll('span.rounded-full.bg-neutral-900')].map((c) => c.firstChild.textContent)
    expect(chips).toEqual(['Art', 'Hindi', 'Maths'])
  })

  it('adds a subject by typing it and pressing Enter', () => {
    const update = vi.fn().mockResolvedValue({})
    render(
      <TeachersSection schoolId={1} teachers={[TEACHERS[2]]} subjects={SUBJECTS} classGroups={SECTIONS}
                       allRequirements={[]} onTeachersChanged={{ update, reload: vi.fn() }} readOnly={false} />,
    )
    fireEvent.click(screen.getAllByText('+ Add')[0])
    const search = screen.getByLabelText('Add a subject to Mr. Anil')
    fireEvent.change(search, { target: { value: 'cur' } })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(update).toHaveBeenCalledWith(3, { qualified_subject_ids: [2, 4] })
  })
})

describe('the Subjects list', () => {
  const rows = () => [...document.querySelectorAll('tbody input[id^="subject-name-"]')].map((i) => i.value)

  function renderSubjects(props = {}) {
    return render(
      <SubjectsSection
        schoolId={1}
        subjects={SUBJECTS}
        onSubjectsChanged={{ create: vi.fn(), update: vi.fn(), delete: vi.fn(), reload: vi.fn() }}
        allRequirements={REQUIREMENTS}
        teachers={TEACHERS}
        readOnly={false}
        {...props}
      />,
    )
  }

  it('is alphabetical', () => {
    renderSubjects()
    expect(rows()).toEqual(['Art', 'Cursive', 'Hindi', 'Maths'])
  })

  it('finds a subject', async () => {
    renderSubjects()
    fireEvent.change(screen.getByLabelText('Search subjects'), { target: { value: 'ma' } })
    // Rows fade out rather than vanish, so wait for them to go.
    await waitFor(() => expect(rows()).toEqual(['Maths']))
  })

  it('sorts by periods a week across the school', () => {
    renderSubjects()
    fireEvent.change(screen.getByLabelText('Sort subjects'), { target: { value: 'periods' } })
    expect(rows()).toEqual(['Hindi', 'Maths', 'Art', 'Cursive'])
  })

  it('sorts by sections taking it', () => {
    renderSubjects()
    fireEvent.change(screen.getByLabelText('Sort subjects'), { target: { value: 'sections' } })
    expect(rows()).toEqual(['Hindi', 'Maths', 'Art', 'Cursive'])
  })

  it('sorts by qualified teachers, either way', () => {
    renderSubjects()
    fireEvent.change(screen.getByLabelText('Sort subjects'), { target: { value: 'teachers' } })
    expect(rows()).toEqual(['Maths', 'Art', 'Hindi', 'Cursive'])
    fireEvent.change(screen.getByLabelText('Sort subjects'), { target: { value: 'teachers-asc' } })
    expect(rows()).toEqual(['Cursive', 'Art', 'Hindi', 'Maths'])
  })

  it('shows the figures it sorts by', () => {
    renderSubjects()
    expect(screen.getByText('2 sections · 10 periods/week · 2 teachers')).toBeInTheDocument()
  })

  it("counts an elective block's periods for each of its subjects", () => {
    renderSubjects({
      electiveBlocks: [{ id: 7, class_group_id: 101, periods_per_week: 4,
                         options: [{ id: 70, subject_id: 3 }, { id: 71, subject_id: 4 }] }],
    })
    // Art: 4 periods in one section, from the block.
    expect(screen.getAllByText('1 section · 4 periods/week · 2 teachers')).toHaveLength(1)
  })

  it('keeps a subject added on this visit at the bottom while it is named', () => {
    const { rerender } = renderSubjects()
    const added = [...SUBJECTS, { id: 9, name: 'New subject' }]
    rerender(
      <SubjectsSection schoolId={1} subjects={added}
                       onSubjectsChanged={{ create: vi.fn(), update: vi.fn(), delete: vi.fn(), reload: vi.fn() }}
                       allRequirements={REQUIREMENTS} teachers={TEACHERS} readOnly={false} />,
    )
    expect(rows()).toEqual(['Art', 'Cursive', 'Hindi', 'Maths', 'New subject'])
  })
})
