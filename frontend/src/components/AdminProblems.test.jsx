import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminProblems from './AdminProblems'
import SendToSupport from './SendToSupport'

const api = vi.hoisted(() => ({
  admin: { problems: vi.fn(), updateProblem: vi.fn(), downloadProblemSnapshot: vi.fn() },
  sendToSupport: vi.fn(),
}))
vi.mock('../api', () => ({ api }))

const DATA = {
  counts: { generation_failed: 2, setup_error: 3 },
  common: [{ kind: 'setup_error', label: 'teacher_overloaded', schools: 3 }],
  problems: [
    { id: 9, kind: 'support_request', summary: "Maths won't fit", school_name: 'Sunrise', status: 'open',
      has_snapshot: true, school_id: 4,
      detail: { message: "Maths won't fit", email: 'head@sunrise.in', context: { where: 'the setup check' } } },
    { id: 8, kind: 'move_blocked', summary: 'Verma teaches Grade 11 B then', school_name: 'Lotus', status: 'open',
      has_snapshot: false, school_id: 5,
      detail: { lesson: "Grade 11 A's English", from: 'Mon P2', to: 'Mon P3', fixes_found: 0 } },
  ],
}

beforeEach(() => {
  Object.values(api.admin).forEach((f) => f.mockReset())
  api.sendToSupport.mockReset()
  api.admin.problems.mockResolvedValue(DATA)
  api.admin.updateProblem.mockResolvedValue({})
})

describe('admin problems', () => {
  it('shows the counts, the most common, and each problem with what happened', async () => {
    render(<AdminProblems />)
    expect(await screen.findByText('Teacher alone over their limit')).toBeInTheDocument()
    expect(screen.getByText('3 schools')).toBeInTheDocument()
    const move = screen.getByRole('article', { name: 'Problem 8' })
    expect(move).toHaveTextContent("Grade 11 A's English, Mon P2 → Mon P3")
    expect(within(move).queryByRole('button', { name: 'Download setup' })).not.toBeInTheDocument()
  })

  it('downloads the setup and marks a problem', async () => {
    render(<AdminProblems />)
    const req = await screen.findByRole('article', { name: 'Problem 9' })
    fireEvent.click(within(req).getByRole('button', { name: 'Download setup' }))
    expect(api.admin.downloadProblemSnapshot).toHaveBeenCalledWith(DATA.problems[0])
    fireEvent.click(within(req).getByRole('button', { name: "School's own setup" }))
    await waitFor(() => expect(api.admin.updateProblem).toHaveBeenCalledWith(9, { status: 'school_setup' }))
  })

  it('filters by kind from the boxes', async () => {
    render(<AdminProblems />)
    await screen.findByRole('article', { name: 'Problem 9' })
    fireEvent.click(screen.getByRole('button', { name: /Generation failed/ }))
    await waitFor(() => expect(api.admin.problems).toHaveBeenLastCalledWith({ kind: 'generation_failed', status: 'open', q: '' }))
  })
})

describe('send to support', () => {
  it('sends the note with what the school was looking at', async () => {
    api.sendToSupport.mockResolvedValue({ id: 1 })
    render(<SendToSupport schoolId={4} context={{ where: 'the setup check' }} />)
    fireEvent.click(screen.getByRole('button', { name: /Send this to Timetablz support/ }))
    fireEvent.change(screen.getByLabelText('Message to support'), { target: { value: 'Help please' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send to support' }))
    expect(await screen.findByText(/has your setup/)).toBeInTheDocument()
    expect(api.sendToSupport).toHaveBeenCalledWith(4, 'Help please', { where: 'the setup check' })
  })
})
