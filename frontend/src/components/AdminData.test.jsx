import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  getToken: vi.fn(() => 'token'),
  setToken: vi.fn(),
  api: {
    me: vi.fn(),
    admin: {
      stats: vi.fn(), schools: vi.fn(), invoices: vi.fn(), accounts: vi.fn(), account: vi.fn(),
      deleteAccount: vi.fn(), schoolData: vi.fn(), deleteSchool: vi.fn(), downloadSchoolData: vi.fn(),
    },
  },
}))
import { api } from '../api'
import AdminPage from './AdminPage'
import { DeleteBox, SchoolData } from './AdminData'

const DATA = {
  counts: { sections: 1, subjects: 1, teachers: 1, rooms: 0, rules: 1, timetables: 1, people: 1 },
  people: [{ email: 'head@school.in', name: 'Head', role: 'owner' }],
  class_groups: [{ id: 5, grade: 'Grade 6', name: 'A', student_count: 40, class_teacher_id: 9 }],
  subjects: [{ id: 3, name: 'Maths' }],
  teachers: [{ id: 9, name: 'Anil', email: 'anil@school.in', qualified_subject_ids: [3], qualified_grades: [] }],
  requirements: [{ class_group_id: 5, subject_id: 3, periods_per_week: 6, preferred_teacher_id: 9 }],
  constraints: [{ description: 'No Maths in the last period', is_hard: true }],
  rooms: [], timetables: [{ id: 2, lessons: 30 }],
}

describe('admin: a school’s data and deleting', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows what the school entered, by section', async () => {
    api.admin.schoolData.mockResolvedValue(DATA)
    render(<SchoolData school={{ id: 1, name: 'Sunrise' }} />)
    expect(await screen.findByText(/1 sections · 1 subjects · 1 teachers/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Teachers/ }))
    expect(screen.getByText('anil@school.in')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Weekly plan/ }))
    expect(screen.getAllByText('Grade 6 A').length).toBeGreaterThan(0)
  })

  it('only deletes once the exact name is typed', async () => {
    const onDelete = vi.fn().mockResolvedValue()
    render(<DeleteBox what="this school" confirmText="Sunrise School" note="Gone." onDelete={onDelete} onCancel={() => {}} />)
    const go = screen.getByRole('button', { name: 'Delete this school' })
    expect(go).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Type Sunrise School to confirm'), { target: { value: 'sunrise' } })
    expect(go).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Type Sunrise School to confirm'), { target: { value: 'sunrise school' } })
    fireEvent.click(go)
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith('sunrise school'))
  })

  it('deletes an account, with its schools only when ticked', async () => {
    api.me.mockResolvedValue({ email: 'boss@timetablz.com', is_platform_admin: true })
    api.admin.stats.mockResolvedValue({ by_status: {}, paying: {} })
    api.admin.schools.mockResolvedValue([])
    api.admin.invoices.mockResolvedValue([])
    api.admin.accounts.mockResolvedValue([{ id: 7, email: 'head@school.in', name: 'Head', google: false, owns: ['Sunrise'], member_of: [] }])
    api.admin.account.mockResolvedValue({
      id: 7, email: 'head@school.in', email_verified: true, google: false, platform_admin: false,
      owns: [{ id: 1, name: 'Sunrise' }], member_of: [],
      terms: [{ version: '2026-11-08', accepted_at: '2026-11-08T10:00:00Z', ip_address: '203.0.113.7' }],
    })
    api.admin.deleteAccount.mockResolvedValue({})
    render(<AdminPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Accounts' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Details' }))
    expect(await screen.findByText(/Version 2026-11-08 on .* from 203.0.113.7/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete account…' }))
    const box = screen.getByRole('form', { name: 'Delete this account' })
    fireEvent.change(within(box).getByLabelText('Type head@school.in to confirm'), { target: { value: 'head@school.in' } })
    fireEvent.click(within(box).getByRole('checkbox'))
    fireEvent.click(within(box).getByRole('button', { name: 'Delete this account' }))
    await waitFor(() => expect(api.admin.deleteAccount).toHaveBeenCalledWith(7, 'head@school.in', true))
  })
})
