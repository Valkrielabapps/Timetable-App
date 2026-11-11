import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PLANS, detectCurrency, invoiceMailto, planPrice } from './plans'
import PricingPage from '../components/PricingPage'

function inZone(tz) {
  const real = Intl.DateTimeFormat
  vi.spyOn(Intl, 'DateTimeFormat').mockImplementation((...a) => {
    const f = new real(...a)
    return { ...f, resolvedOptions: () => ({ ...f.resolvedOptions(), timeZone: tz }), format: f.format.bind(f) }
  })
}

globalThis.IntersectionObserver ??= class { observe() {} unobserve() {} disconnect() {} }

beforeEach(() => window.localStorage.clear())

afterEach(() => {
  vi.restoreAllMocks()
  window.localStorage.clear()
})

describe('currency by country', () => {
  it('is rupees in India and dollars elsewhere', () => {
    inZone('Asia/Kolkata')
    expect(detectCurrency()).toBe('INR')
    vi.restoreAllMocks()
    inZone('Asia/Dubai')
    expect(detectCurrency()).toBe('USD')
  })

  it('remembers a choice made on the switch', () => {
    inZone('Asia/Kolkata')
    window.localStorage.setItem('timetablz.currency', 'USD')
    expect(detectCurrency()).toBe('USD')
  })

  it('prices each plan in both', () => {
    expect(planPrice(PLANS[0], 'INR')).toBe('₹9,999')
    expect(planPrice(PLANS[0], 'USD')).toBe('$149')
    expect(planPrice(PLANS[1], 'USD', 'done_for_you')).toBe('$399')
    expect(planPrice(PLANS[2], 'USD')).toBe('$299')
  })

  it('builds an invoice email', () => {
    const m = invoiceMailto('Standard', 'software', '$229', 40)
    expect(m.startsWith('mailto:support@timetablz.com?subject=')).toBe(true)
    expect(decodeURIComponent(m)).toContain('Number of sections: 40')
  })

  it('shows dollar prices on the pricing page outside India', () => {
    inZone('Europe/London')
    render(<PricingPage onBack={() => {}} onGetStarted={() => {}} />)
    expect(screen.getByText('$149')).toBeInTheDocument()
    expect(screen.queryByText('₹9,999')).not.toBeInTheDocument()
    expect(screen.getByText(/outside India, in US dollars/)).toBeInTheDocument()
  })
})
