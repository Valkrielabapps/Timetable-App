import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const checkout = vi.fn()
vi.mock('@cashfreepayments/cashfree-js', () => ({ load: vi.fn(async () => ({ checkout })) }))
vi.mock('../api', () => ({
  api: { createPaymentOrder: vi.fn(), getPaymentOrder: vi.fn() },
  getToken: vi.fn(() => 'token'),
}))

vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: [] }) }))

const entitlements = { current: null }
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => ({ data: entitlements.current, isLoading: false }) }))

const FREE = {
  plan: 'free', paid_plan: null, status: 'free', plan_valid_until: null, grace_ends_at: null,
  limits: { max_sections: 5, max_members: 1, ai_actions_per_month: 10, clean_exports: false },
  usage: { sections: 5, members: 1, ai_actions_this_month: 3 },
  pro_price_inr: 4999,
}

import { api } from '../api'
import BillingSection from './BillingSection'
import PaymentStatusPage from './PaymentStatusPage'

const school = { id: 7, plan: null, plan_valid_until: null, profile: { phone: '98765 43210' } }

describe('BillingSection', () => {
  beforeEach(() => {
    entitlements.current = FREE
    checkout.mockReset()
    api.createPaymentOrder.mockReset()
  })

  it('creates an order with only school, plan and phone, then opens checkout with the session id', async () => {
    api.createPaymentOrder.mockResolvedValue({ order_id: 'tz_7_abc', payment_session_id: 'session_1' })
    checkout.mockResolvedValue({})
    render(<BillingSection school={school} isAdmin />)
    fireEvent.click(screen.getByRole('button', { name: /pay now/i }))
    await waitFor(() => expect(checkout).toHaveBeenCalled())
    expect(api.createPaymentOrder).toHaveBeenCalledWith({ school_id: 7, phone: '9876543210', plan: 'pro' })
    expect(checkout).toHaveBeenCalledWith({ paymentSessionId: 'session_1', redirectTarget: '_self' })
  })

  it('rejects a bad phone number before calling the server', () => {
    render(<BillingSection school={{ ...school, profile: {} }} isAdmin />)
    fireEvent.change(screen.getByPlaceholderText('98765 43210'), { target: { value: '123' } })
    fireEvent.click(screen.getByRole('button', { name: /pay now/i }))
    expect(screen.getByText(/valid 10-digit mobile number/i)).toBeInTheDocument()
    expect(api.createPaymentOrder).not.toHaveBeenCalled()
  })

  it('shows the server error if the order cannot be created', async () => {
    api.createPaymentOrder.mockRejectedValue(new Error("Online payments aren't set up yet."))
    render(<BillingSection school={school} isAdmin />)
    fireEvent.click(screen.getByRole('button', { name: /pay now/i }))
    expect(await screen.findByText(/aren't set up yet/i)).toBeInTheDocument()
  })

  it('hides the pay button from viewers', () => {
    render(<BillingSection school={school} isAdmin={false} />)
    expect(screen.queryByRole('button', { name: /pay now/i })).not.toBeInTheDocument()
  })

  it('shows Pro when the plan is active', () => {
    entitlements.current = { ...FREE, plan: 'pro', paid_plan: 'pro', status: 'active', plan_valid_until: '2099-01-01T00:00:00',
      limits: { ...FREE.limits, max_sections: 60, ai_actions_per_month: null } }
    render(<BillingSection school={school} isAdmin />)
    expect(screen.getByText('Pro')).toBeInTheDocument()
    expect(screen.getByText(/renew pro/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /renew now/i })).toBeInTheDocument()
  })

  it('shows usage against the plan limits', () => {
    render(<BillingSection school={school} isAdmin />)
    expect(screen.getByText('Sections')).toBeInTheDocument()
    expect(screen.getByText('5 / 5')).toBeInTheDocument()
    expect(screen.getByText('3 / 10')).toBeInTheDocument()
  })

  it('explains the grace period', () => {
    entitlements.current = { ...FREE, plan: 'pro', paid_plan: 'pro', status: 'grace',
      plan_valid_until: '2026-10-01T00:00:00', grace_ends_at: '2026-10-16T00:00:00' }
    render(<BillingSection school={school} isAdmin />)
    expect(screen.getByText(/features stay on until/i)).toBeInTheDocument()
  })

  it('pays a custom offer with the offer id', async () => {
    entitlements.current = { ...FREE, offer: { id: 42, name: 'Sunrise Business', price_inr: 18000, period_days: 365, max_sections: 150, max_members: 15 } }
    api.createPaymentOrder.mockResolvedValue({ order_id: 'tz_7_x', payment_session_id: 's' })
    checkout.mockResolvedValue({})
    render(<BillingSection school={school} isAdmin />)
    expect(screen.getByText('Your custom plan')).toBeInTheDocument()
    expect(screen.getByText(/up to 150 sections/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /pay now · ₹18,000/i }))
    await waitFor(() => expect(api.createPaymentOrder).toHaveBeenCalledWith({ school_id: 7, phone: '9876543210', plan: 'pro', offer_id: 42 }))
  })

  it('does not offer checkout to a Business school', () => {
    entitlements.current = { ...FREE, plan: 'business', paid_plan: 'business', status: 'active' }
    render(<BillingSection school={school} isAdmin />)
    expect(screen.queryByRole('button', { name: /pay now/i })).not.toBeInTheDocument()
    expect(screen.getByText(/business plan/i)).toBeInTheDocument()
  })
})

describe('PaymentStatusPage', () => {
  it('shows success only when the backend says PAID', async () => {
    api.getPaymentOrder.mockResolvedValue({ order_id: 'tz', status: 'PAID', amount: 4999, plan: 'pro', plan_valid_until: '2027-10-12T00:00:00' })
    render(<PaymentStatusPage orderId="tz" onDone={() => {}} />)
    expect(await screen.findByText('Payment successful')).toBeInTheDocument()
    expect(api.getPaymentOrder).toHaveBeenCalledWith('tz')
  })

  it('shows the failure state', async () => {
    api.getPaymentOrder.mockResolvedValue({ order_id: 'tz', status: 'FAILED', amount: 4999, plan: 'pro' })
    render(<PaymentStatusPage orderId="tz" onDone={() => {}} />)
    expect(await screen.findByText('Payment not completed')).toBeInTheDocument()
  })

  it('shows pending while the bank confirms', async () => {
    api.getPaymentOrder.mockResolvedValue({ order_id: 'tz', status: 'PENDING', amount: 4999, plan: 'pro' })
    render(<PaymentStatusPage orderId="tz" onDone={() => {}} />)
    expect(await screen.findByText('Payment processing')).toBeInTheDocument()
  })
})
