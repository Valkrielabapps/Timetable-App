import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PlanPicker from './PlanPicker'
import FreeCountdown from './FreeCountdown'
import LockedScreen from './LockedScreen'

describe('PlanPicker', () => {
  it('offers Free, Pro and Business and reports the choice', () => {
    const onChoose = vi.fn()
    render(<PlanPicker onChoose={onChoose} onBack={() => {}} onSignIn={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Start free' }))
    fireEvent.click(screen.getByRole('button', { name: 'Choose Pro' }))
    fireEvent.click(screen.getByRole('button', { name: 'Contact us' }))
    expect(onChoose.mock.calls.map((c) => c[0])).toEqual(['free', 'pro', 'business'])
    expect(screen.getByText('for 14 days')).toBeInTheDocument()
  })
})

describe('FreeCountdown', () => {
  it('shows the days left during the free period', () => {
    const onUpgrade = vi.fn()
    render(<FreeCountdown entitlements={{ status: 'free', free_days_left: 9 }} onUpgrade={onUpgrade} />)
    expect(screen.getByText('9 days left')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /upgrade to pro/i }))
    expect(onUpgrade).toHaveBeenCalled()
  })

  it('says "1 day" on the last day and nothing once paid', () => {
    const { rerender, container } = render(<FreeCountdown entitlements={{ status: 'free', free_days_left: 1 }} onUpgrade={() => {}} />)
    expect(screen.getByText('1 day left')).toBeInTheDocument()
    rerender(<FreeCountdown entitlements={{ status: 'active', free_days_left: null }} onUpgrade={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('LockedScreen', () => {
  it('explains the free period has ended and offers the upgrade to admins', () => {
    const onUpgrade = vi.fn()
    render(<LockedScreen entitlements={{ status: 'locked', paid_plan: null, pro_price_inr: 4999 }} isAdmin onUpgrade={onUpgrade} />)
    expect(screen.getByText('Your 14-day free period has ended')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /upgrade to pro/i }))
    expect(onUpgrade).toHaveBeenCalled()
  })

  it('tells viewers to ask an admin', () => {
    render(<LockedScreen entitlements={{ status: 'locked', paid_plan: 'pro' }} isAdmin={false} onUpgrade={() => {}} />)
    expect(screen.getByText('Your Pro plan has ended')).toBeInTheDocument()
    expect(screen.getByText(/ask a school admin/i)).toBeInTheDocument()
  })
})
