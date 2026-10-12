import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const checkout = vi.fn()
vi.mock('@cashfreepayments/cashfree-js', () => ({ load: vi.fn(async () => ({ checkout })) }))
vi.mock('../api', () => ({
  api: { createPaymentOrder: vi.fn(), getPaymentOrder: vi.fn() },
  getToken: vi.fn(() => 'token'),
}))

import { api } from '../api'
import BillingSection from './BillingSection'
import PaymentStatusPage from './PaymentStatusPage'

const school = { id: 7, plan: null, plan_valid_until: null, profile: { phone: '98765 43210' } }

describe('BillingSection', () => {
  beforeEach(() => {
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
    render(<BillingSection school={{ ...school, plan: 'pro', plan_valid_until: '2099-01-01T00:00:00' }} isAdmin />)
    expect(screen.getByText('Pro')).toBeInTheDocument()
    expect(screen.getByText(/renew pro/i)).toBeInTheDocument()
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
