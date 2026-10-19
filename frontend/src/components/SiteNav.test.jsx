import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const token = vi.hoisted(() => ({ current: null }))
vi.mock('../api', () => ({ getToken: () => token.current }))

import SiteNav from './SiteNav'
import PricingPage from './PricingPage'

describe('SiteNav', () => {
  it('links every public page and marks the current one', () => {
    render(<SiteNav current="pricing" />)
    for (const label of ['Why Timetablz', 'Plans and Pricing', 'Customers', 'About', 'Support']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
    }
    expect(screen.getByRole('link', { name: 'Plans and Pricing' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Timetablz' })).toBeInTheDocument()
  })

  it('offers sign in when signed out, and the app when signed in', () => {
    token.current = null
    const { unmount } = render(<SiteNav />)
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Get started free' })).toBeInTheDocument()
    unmount()
    token.current = 'abc'
    render(<SiteNav />)
    expect(screen.queryByRole('button', { name: 'Sign in' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Open app' })).toBeInTheDocument()
    token.current = null
  })

  it('is on the pricing page, with no "Back to home"', () => {
    // The page's scroll-in animations need a browser API jsdom lacks.
    globalThis.IntersectionObserver ??= class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    render(<PricingPage onBack={() => {}} onGetStarted={() => {}} />)
    expect(screen.getByRole('navigation', { name: 'Site' })).toBeInTheDocument()
    expect(screen.queryByText(/back to home/i)).toBeNull()
  })
})
