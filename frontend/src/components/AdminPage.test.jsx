import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('../api', () => ({
  getToken: vi.fn(() => 'token'),
  setToken: vi.fn(),
  api: {
    me: vi.fn(),
    admin: {
      stats: vi.fn(),
      schools: vi.fn(),
      invoices: vi.fn(),
      accounts: vi.fn(),
    },
  },
}))
vi.mock('./AuthPage', () => ({ default: () => <div>Sign-in form</div> }))
import { api, getToken } from '../api'
import AdminPage from './AdminPage'

const STATS = {
  schools: 3, accounts: 4, by_status: { free: 1, active: 1, grace: 0, locked: 1 }, paying: { pro: 1, business: 0 },
  free_ending_within_3_days: 1, open_offers: 0, revenue_total_inr: 4999, revenue_this_month_inr: 4999, invoices: 1,
}

describe('AdminPage', () => {
  beforeEach(() => {
    api.admin.stats.mockResolvedValue(STATS)
    api.admin.schools.mockResolvedValue([])
    api.admin.invoices.mockResolvedValue([])
    api.admin.accounts.mockResolvedValue([{ id: 1, email: 'head@school.in', name: 'Head', google: false, owns: ['Sunrise'], member_of: [] }])
  })

  it('asks for sign-in when signed out', async () => {
    getToken.mockReturnValueOnce(null)
    render(<AdminPage />)
    expect(await screen.findByText('Sign-in form')).toBeInTheDocument()
  })

  it('shows nothing to an ordinary account', async () => {
    api.me.mockResolvedValue({ id: 2, email: 'someone@school.in', is_platform_admin: false })
    render(<AdminPage />)
    expect(await screen.findByText(/isn.t available/)).toBeInTheDocument()
    expect(api.admin.stats).not.toHaveBeenCalled()
  })

  it('shows the dashboard and accounts to the admin', async () => {
    api.me.mockResolvedValue({ id: 1, email: 'valkyrielabapps@gmail.com', is_platform_admin: true })
    render(<AdminPage />)
    expect(await screen.findByText('Revenue to date')).toBeInTheDocument()
    expect((await screen.findAllByText('₹4,999')).length).toBe(2)
    expect(screen.getByText('1 Pro · 0 Business')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Accounts' }))
    expect(await screen.findByText('head@school.in')).toBeInTheDocument()
  })
})
