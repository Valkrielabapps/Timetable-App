import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
vi.mock('../api', () => ({ api: {} }))
import SettingsTab from './SettingsTab'

const school = {
  id: 1,
  name: 'Valkyrie Labs School',
  institution_type: 'school',
  profile: { board: 'CBSE', city: 'Thiruvananthapuram', academic_year_start_month: 6 },
}

function renderIt(extra = {}) {
  const props = {
    user: { id: 1, name: 'Allen', email: 'a@a.com' },
    onUserUpdated: vi.fn(),
    school,
    onRenameSchool: vi.fn().mockResolvedValue(),
    onUpdateInstitutionType: vi.fn().mockResolvedValue(),
    onSaveProfile: vi.fn().mockResolvedValue(),
    isAdmin: true,
    members: [],
    invites: [],
    onReloadTeam: vi.fn(),
    ...extra,
  }
  render(<SettingsTab {...props} />)
  return props
}

describe('SettingsTab school profile', () => {
  it('shows saved details and "Not provided" for blanks', () => {
    renderIt()
    expect(screen.getByText('CBSE')).toBeInTheDocument()
    expect(screen.getByText('June')).toBeInTheDocument()
    expect(screen.getAllByText('Not provided').length).toBeGreaterThan(3)
  })

  it('hides Edit for viewers', () => {
    renderIt({ isAdmin: false })
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  })

  it('validates, then saves only filled fields', async () => {
    const props = renderIt()
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByLabelText('PIN / postal code'), { target: { value: '123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(screen.getByText('Indian PIN codes have 6 digits')).toBeInTheDocument()
    expect(props.onSaveProfile).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('PIN / postal code'), { target: { value: '695020' } })
    fireEvent.change(screen.getByLabelText('State'), { target: { value: 'Kerala' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(props.onSaveProfile).toHaveBeenCalled())
    expect(props.onSaveProfile).toHaveBeenCalledWith({
      board: 'CBSE',
      academic_year_start_month: 6,
      city: 'Thiruvananthapuram',
      state: 'Kerala',
      country: 'India',
      postal_code: '695020',
    })
    expect(props.onRenameSchool).not.toHaveBeenCalled()
  })
})
