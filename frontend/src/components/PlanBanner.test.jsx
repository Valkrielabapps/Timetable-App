import React from 'react'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PlanBanner from './PlanBanner'
import UpgradePrompt from './UpgradePrompt'

describe('PlanBanner', () => {
  it('says nothing for a free school or an active plan', () => {
    const { container } = render(<PlanBanner entitlements={{ status: 'free', paid_plan: null }} isAdmin onRenew={() => {}} />)
    expect(container).toBeEmptyDOMElement()
    render(<PlanBanner entitlements={{ status: 'active', paid_plan: 'pro' }} isAdmin onRenew={() => {}} />)
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('asks admins to renew during the grace period', () => {
    const onRenew = vi.fn()
    render(<PlanBanner entitlements={{ status: 'grace', paid_plan: 'pro', plan_valid_until: '2026-10-01T00:00:00', grace_ends_at: '2026-10-16T00:00:00' }} isAdmin onRenew={onRenew} />)
    expect(screen.getByText(/renew by/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /renew pro/i }))
    expect(onRenew).toHaveBeenCalled()
  })
})

describe('UpgradePrompt', () => {
  it('opens on a plan-limit event and sends the admin to plans', () => {
    const onSeePlans = vi.fn()
    render(
      <QueryClientProvider client={new QueryClient()}>
        <UpgradePrompt isAdmin onSeePlans={onSeePlans} />
      </QueryClientProvider>
    )
    act(() => {
      window.dispatchEvent(new CustomEvent('timetablz:plan-limit', { detail: { message: 'The Free plan includes up to 5 sections.' } }))
    })
    expect(screen.getByText('The Free plan includes up to 5 sections.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /see plans/i }))
    expect(onSeePlans).toHaveBeenCalled()
  })
})
