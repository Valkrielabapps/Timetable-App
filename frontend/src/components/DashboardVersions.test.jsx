import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import DashboardTab from './DashboardTab'

const actions = { open: vi.fn(() => Promise.resolve()), rename: vi.fn(() => Promise.resolve()), remove: vi.fn(() => Promise.resolve()) }
let frozen = []
vi.mock('../api', () => ({ api: { downloadTimetableExport: vi.fn() } }))
vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({
    data: [
      { id: 10, status: 'draft', version_number: 1, name: 'Grades 1-5 approved', created_at: '2026-10-26T10:00:00Z' },
      { id: 11, status: 'draft', version_number: 2, is_current: true, created_at: '2026-10-27T10:00:00Z' },
    ],
    isLoading: false,
  }),
  useFrozenStatus: () => ({ data: frozen }),
  useVersionActions: () => actions,
}))

function renderTab(onNavigate = vi.fn()) {
  render(
    <DashboardTab
      user={{ name: 'Allen' }} school={{ id: 1 }} classGroups={[{ id: 5, grade: 'Grade 1', name: 'A' }]}
      teachers={[]} subjects={[]} constraints={[]} periods={[]} allRequirements={[]}
      progress={{ loaded: true, allRequiredDone: true }} onNavigate={onNavigate} onOpenSection={vi.fn()}
    />,
  )
  return onNavigate
}

describe('timetable versions on the Dashboard', () => {
  it('marks the current version and names the others', () => {
    renderTab()
    expect(screen.getByText('Current')).toBeInTheDocument()
    expect(screen.getByText('· Grades 1-5 approved')).toBeInTheDocument()
  })

  it('opening an older version makes it current, then shows it', async () => {
    const nav = renderTab()
    fireEvent.click(screen.getAllByRole('button', { name: 'Open' })[1]) // Version 1 (listed second)
    await waitFor(() => expect(actions.open).toHaveBeenCalledWith(10))
    expect(nav).toHaveBeenCalledWith('timetable')
  })

  it('renames a version', async () => {
    renderTab()
    fireEvent.click(screen.getAllByRole('button', { name: 'Rename' })[0])
    fireEvent.change(screen.getByLabelText('Version name'), { target: { value: 'Final' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(actions.rename).toHaveBeenCalledWith(11, 'Final'))
  })

  it('asks before deleting', async () => {
    renderTab()
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[1])
    expect(actions.remove).not.toHaveBeenCalled()
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' }).at(-1))
    await waitFor(() => expect(actions.remove).toHaveBeenCalledWith(10))
  })

  it('a version sections are frozen from says so instead of deleting', () => {
    frozen = [{ class_group_id: 5, frozen: true, frozen_from_timetable_id: 10 }]
    renderTab()
    expect(screen.getByText(/1 frozen from this version/)).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[1])
    expect(screen.getByText(/Grade 1 - A is frozen from this version/)).toBeInTheDocument()
    frozen = []
  })
})
