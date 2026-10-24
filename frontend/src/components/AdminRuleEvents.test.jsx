import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AdminRuleEvents from './AdminRuleEvents'

const ruleEvents = vi.fn()
const triageRuleEvent = vi.fn(() => Promise.resolve({}))
vi.mock('../api', () => ({ api: { admin: { ruleEvents: (...a) => ruleEvents(...a), triageRuleEvent: (...a) => triageRuleEvent(...a) } } }))

const DATA = {
  counts: { interpreted: 10, confirmed: 8, cancelled: 1 },
  confirmed_share: 0.8,
  events: [{
    id: 5, kind: 'cancelled', text: 'no pe after lunch', school_name: 'Greenfield', created_at: '2026-10-24T10:00:00',
    detail: { shown: 'No Physical Education in period 5.' }, triage: null,
  }],
}

describe('admin rule reading', () => {
  it('shows what the school typed, what it was shown, and files it', async () => {
    ruleEvents.mockResolvedValue(DATA)
    render(<AdminRuleEvents />)
    expect(await screen.findByText(/no pe after lunch/)).toBeInTheDocument()
    expect(screen.getByText('No Physical Education in period 5.')).toBeInTheDocument()
    expect(screen.getByText('80%')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Misread' }))
    await waitFor(() => expect(triageRuleEvent).toHaveBeenCalledWith(5, 'misread'))
    expect(screen.getByRole('button', { name: 'Misread' })).toHaveAttribute('aria-pressed', 'true')
  })
})
