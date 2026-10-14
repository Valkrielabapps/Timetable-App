import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  api: {
    admin: {
      schools: vi.fn(),
      invoices: vi.fn(),
      createOffer: vi.fn(),
      markPaid: vi.fn(),
      extendFree: vi.fn(),
      cancelOffer: vi.fn(),
      downgrade: vi.fn(),
    },
    downloadInvoice: vi.fn(),
  },
}))
import { api } from '../api'
import AdminTab from './AdminTab'

const SCHOOL = {
  id: 3, name: 'Sunrise School', owner_email: 'head@sunrise.in', plan: 'free', plan_name: 'Free', paid_plan: null,
  status: 'free', free_days_left: 9, plan_valid_until: null, sections: 4, members: 1,
  limits: { max_sections: 5, max_members: 1 }, open_offer: null,
}

describe('AdminTab', () => {
  it('lists schools and sends a custom offer', async () => {
    api.admin.schools.mockResolvedValue([SCHOOL])
    api.admin.invoices.mockResolvedValue([])
    api.admin.createOffer.mockResolvedValue({ id: 1 })
    render(<AdminTab />)
    expect(await screen.findByText('Sunrise School')).toBeInTheDocument()
    expect(screen.getByText('Free · 9 days left')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Manage' }))
    fireEvent.change(screen.getByLabelText('Price (₹)'), { target: { value: '18000' } })
    fireEvent.change(screen.getByLabelText('Max sections'), { target: { value: '150' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send offer' }))
    await waitFor(() =>
      expect(api.admin.createOffer).toHaveBeenCalledWith(3, expect.objectContaining({ price_inr: 18000, max_sections: 150, max_members: null, period_days: 365 }))
    )
    expect(await screen.findByText(/offer sent/i)).toBeInTheDocument()
  })

  it('records a bank transfer', async () => {
    api.admin.schools.mockResolvedValue([SCHOOL])
    api.admin.invoices.mockResolvedValue([])
    api.admin.markPaid.mockResolvedValue({})
    render(<AdminTab />)
    fireEvent.click(await screen.findByRole('button', { name: 'Manage' }))
    fireEvent.change(screen.getByLabelText('Reference (UTR / cheque no.)'), { target: { value: 'UTR9' } })
    fireEvent.click(screen.getByRole('button', { name: 'Mark as paid' }))
    await waitFor(() => expect(api.admin.markPaid).toHaveBeenCalledWith(3, { kind: 'pro', amount_inr: 4999, reference: 'UTR9' }))
  })
})
