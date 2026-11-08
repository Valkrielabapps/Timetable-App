import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AcceptTermsPage from './AcceptTermsPage'

const api = vi.hoisted(() => ({ acceptTerms: vi.fn() }))
vi.mock('../api', () => ({ api }))

const USER = { email: 'priya@school.in', needs_terms: true, terms_version: '2026-11-08', has_accepted_before: false }

describe('accepting the terms after signing in', () => {
  it('shows the terms and only continues once the box is ticked', async () => {
    const onAccepted = vi.fn()
    api.acceptTerms.mockResolvedValue({ ...USER, needs_terms: false })
    render(<AcceptTermsPage user={USER} onAccepted={onAccepted} onSignOut={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Before you continue' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Limitation of liability/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', '/privacy')
    const go = screen.getByRole('button', { name: 'I agree, continue' })
    expect(go).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(go)
    await waitFor(() => expect(onAccepted).toHaveBeenCalledWith({ ...USER, needs_terms: false }))
    expect(api.acceptTerms).toHaveBeenCalledWith('2026-11-08')
  })

  it('says the terms changed for someone who accepted before, and can sign out instead', () => {
    const onSignOut = vi.fn()
    render(<AcceptTermsPage user={{ ...USER, has_accepted_before: true }} onAccepted={() => {}} onSignOut={onSignOut} />)
    expect(screen.getByRole('heading', { name: 'We’ve updated our terms' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(onSignOut).toHaveBeenCalled()
  })

  it('shows why it could not be saved', async () => {
    api.acceptTerms.mockRejectedValue(new Error('The terms have been updated. Reload the page to see the new version.'))
    render(<AcceptTermsPage user={USER} onAccepted={() => {}} onSignOut={() => {}} />)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'I agree, continue' }))
    expect(await screen.findByText(/Reload the page/)).toBeInTheDocument()
  })
})
