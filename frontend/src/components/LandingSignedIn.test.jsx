import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import LandingPage from './LandingPage'

// The landing page's animations ask for matchMedia / IntersectionObserver,
// which jsdom doesn't provide.
window.matchMedia ||= () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} })
window.IntersectionObserver ||= class { observe() {} unobserve() {} disconnect() {} }

describe('LandingPage for a signed-in visitor', () => {
  it('replaces Sign in / Get started with a way into the app', () => {
    const enter = vi.fn()
    render(<LandingPage signedIn onGetStarted={enter} onSignIn={enter} />)
    expect(screen.queryByRole('button', { name: 'Sign in' })).toBeNull()
    // In the top bar and again in the closing band above the footer.
    const openApp = screen.getAllByRole('button', { name: 'Open app' })
    expect(openApp).toHaveLength(2)
    openApp.forEach((b) => fireEvent.click(b))
    fireEvent.click(screen.getByRole('button', { name: 'Go to your dashboard' }))
    expect(enter).toHaveBeenCalledTimes(3)
  })

  it('keeps Sign in and Get started for visitors', () => {
    render(<LandingPage onGetStarted={() => {}} onSignIn={() => {}} />)
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Get started free' }).length).toBeGreaterThan(0)
  })

  it('ends with a closing call to action above the footer', () => {
    render(<LandingPage onGetStarted={() => {}} onSignIn={() => {}} />)
    expect(screen.getByRole('heading', { name: /make the hardest timetable feel effortless/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Book a demo' })).toHaveAttribute('href', '?page=contact')
  })
})
