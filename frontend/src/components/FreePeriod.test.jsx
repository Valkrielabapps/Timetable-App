import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PlanPicker from './PlanPicker'
import FreeCountdown from './FreeCountdown'
import LockedScreen from './LockedScreen'

describe('PlanPicker', () => {
  it('shows the four plans by size, and reports trial, buy and contact choices', () => {
    const onChoose = vi.fn()
    render(<PlanPicker onChoose={onChoose} onBack={() => {}} onSignIn={() => {}} />)
    expect(screen.getByText('₹9,999')).toBeInTheDocument()
    expect(screen.getByText('Done for you: ₹26,999 first year')).toBeInTheDocument()
    expect(screen.getByText('From ₹19,999')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Start free trial' })[1])
    fireEvent.click(screen.getAllByRole('button', { name: 'Buy now instead' })[2])
    fireEvent.click(screen.getByRole('button', { name: 'Get in touch' }))
    expect(onChoose.mock.calls).toEqual([['standard'], ['plus', { buy: true }], ['business']])
  })
})

describe('FreeCountdown', () => {
  it('shows the days left during the free period', () => {
    const onUpgrade = vi.fn()
    render(<FreeCountdown entitlements={{ status: 'free', free_days_left: 9 }} onUpgrade={onUpgrade} />)
    expect(screen.getByText('9 days left')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /choose a plan/i }))
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
    expect(screen.getByText('Your 14-day free trial has ended')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /choose a plan/i }))
    expect(onUpgrade).toHaveBeenCalled()
  })

  it('tells viewers to ask an admin', () => {
    render(<LockedScreen entitlements={{ status: 'locked', paid_plan: 'pro' }} isAdmin={false} onUpgrade={() => {}} />)
    expect(screen.getByText('Your Pro plan has ended')).toBeInTheDocument()
    expect(screen.getByText(/ask a school admin/i)).toBeInTheDocument()
  })
})
