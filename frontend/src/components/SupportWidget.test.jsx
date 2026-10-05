import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ api: { createSupportTicket: vi.fn() } }))
import { api } from '../api'
import SupportWidget from './SupportWidget'

describe('SupportWidget', () => {
  it('opens the menu with the three help options', () => {
    render(<SupportWidget schoolId={3} />)
    fireEvent.click(screen.getByRole('button', { name: 'Open help menu' }))
    expect(screen.getByText('Raise a support ticket')).toBeInTheDocument()
    expect(screen.getByText('Help & FAQ')).toBeInTheDocument()
    expect(screen.getByText('Schedule a call')).toBeInTheDocument()
  })

  it("won't send an empty ticket", () => {
    api.createSupportTicket.mockClear()
    render(<SupportWidget schoolId={3} />)
    fireEvent.click(screen.getByRole('button', { name: 'Open help menu' }))
    fireEvent.click(screen.getByText('Raise a support ticket'))
    fireEvent.click(screen.getByRole('button', { name: 'Send ticket' }))
    expect(screen.getByText('Add a subject and some details first.')).toBeInTheDocument()
    expect(api.createSupportTicket).not.toHaveBeenCalled()
  })

  it('sends the ticket with the current school and shows the confirmation', async () => {
    api.createSupportTicket.mockResolvedValue({ sent: true })
    render(<SupportWidget schoolId={3} />)
    fireEvent.click(screen.getByRole('button', { name: 'Open help menu' }))
    fireEvent.click(screen.getByText('Raise a support ticket'))
    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Stuck' } })
    fireEvent.change(screen.getByLabelText('Details'), { target: { value: 'Generate fails' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send ticket' }))
    await waitFor(() => expect(screen.getByText('Ticket sent')).toBeInTheDocument())
    expect(api.createSupportTicket).toHaveBeenCalledWith({
      category: 'question',
      subject: 'Stuck',
      message: 'Generate fails',
      school_id: 3,
    })
  })

  it('shows the error from the server instead of claiming success', async () => {
    api.createSupportTicket.mockImplementation(() => {
      // Pre-attach a handler: vitest keeps the mock's returned promise in
      // mock.results and reports it as unhandled otherwise, even though
      // the component does catch it.
      const failed = Promise.reject(new Error('Please email support@timetablz.com directly.'))
      failed.catch(() => {})
      return failed
    })
    render(<SupportWidget schoolId={3} />)
    fireEvent.click(screen.getByRole('button', { name: 'Open help menu' }))
    fireEvent.click(screen.getByText('Raise a support ticket'))
    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Stuck' } })
    fireEvent.change(screen.getByLabelText('Details'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send ticket' }))
    await waitFor(() => expect(screen.getByText('Please email support@timetablz.com directly.')).toBeInTheDocument())
    expect(screen.queryByText('Ticket sent')).not.toBeInTheDocument()
  })
})
