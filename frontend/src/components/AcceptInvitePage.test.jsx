import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import AcceptInvitePage from './AcceptInvitePage'
import { api } from '../api'

// AcceptInvitePage calls the real `api` module on mount (api.previewInvite)
// and on submit (api.acceptInvite) - mocked here rather than hitting a real
// backend, which is the pattern any future test on a component that talks
// to api.js should follow.
vi.mock('../api', () => ({
  api: { previewInvite: vi.fn(), acceptInvite: vi.fn() },
  setToken: vi.fn(),
}))

describe('AcceptInvitePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a loading spinner before the invite preview resolves', () => {
    // Never resolves during this test - asserts on the state before that.
    api.previewInvite.mockReturnValue(new Promise(() => {}))
    const { container } = render(<AcceptInvitePage token="abc" onAccepted={vi.fn()} />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('shows an error card when the invite is invalid or expired', async () => {
    api.previewInvite.mockRejectedValue(new Error('This invite link is invalid, expired, or has already been used.'))
    render(<AcceptInvitePage token="bad-token" onAccepted={vi.fn()} />)

    expect(await screen.findByText(/invalid, expired, or has already been used/)).toBeInTheDocument()
  })

  it('renders the join form once the preview resolves, and submits it', async () => {
    api.previewInvite.mockResolvedValue({
      email: 'new@school.edu',
      role: 'viewer',
      school_name: 'Valkyrie Labs',
      status: 'pending',
    })
    api.acceptInvite.mockResolvedValue({
      access_token: 'tok123',
      user: { id: 1, email: 'new@school.edu', name: null },
    })
    const onAccepted = vi.fn()

    render(<AcceptInvitePage token="good-token" onAccepted={onAccepted} />)

    expect(await screen.findByText('Join Valkyrie Labs')).toBeInTheDocument()
    expect(screen.getByText(/invited as a viewer/)).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Set a new password, or enter your existing one'), {
      target: { value: 'password123' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Accept invite' }))

    await waitFor(() => {
      expect(api.acceptInvite).toHaveBeenCalledWith('good-token', { name: null, password: 'password123' })
      expect(onAccepted).toHaveBeenCalledWith({ id: 1, email: 'new@school.edu', name: null })
    })
  })
})
