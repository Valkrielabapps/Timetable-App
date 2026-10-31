import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminOutreach from './AdminOutreach'

const o = {
  overview: vi.fn(),
  schools: vi.fn(),
  draft: vi.fn(),
  approve: vi.fn(),
  findContacts: vi.fn(),
  messages: vi.fn(),
  editSchool: vi.fn(),
  saveSettings: vi.fn(),
  settings: vi.fn(),
  connectGmail: vi.fn(),
  cancel: vi.fn(),
  importWorkbook: vi.fn(),
}
vi.mock('../api', () => ({
  api: { admin: { outreach: new Proxy({}, { get: (_, k) => (...a) => o[k](...a) }) } },
}))

const OVERVIEW = {
  schools: 2, with_email: 1, with_principal: 1, awaiting_approval: 1, queued: 0, sent_this_week: 3,
  by_status: { not_contacted: 2, emailed: 0, replied: 1, bounced: 0, opted_out: 0, demo_booked: 0, trial: 0, paid: 0, not_interested: 0 },
  sent_today: 2, daily_limit: 10, daily_limit_set: 15, sending_enabled: false, in_send_window: true,
  mailbox: 'arpith@gmail.com', mailbox_connected: true, gmail_configured: true, job: { running: false },
}
const SCHOOLS = {
  districts: ['Chennai'],
  schools: [
    { id: 1, name: 'Sunrise Vidyalaya', area: 'Adyar', district: 'Chennai', classes_up_to: 'Class 12', priority: 'High',
      principal_name: 'Dr. Meena Iyer', emails: ['office@sunrise.in'], recipient: 'office@sunrise.in', status: 'not_contacted', sequence: null },
    { id: 2, name: 'Lotus School', district: 'Chennai', priority: 'Medium', emails: [], recipient: null,
      status: 'not_contacted', sequence: { status: 'draft', step: 1 } },
  ],
}

beforeEach(() => {
  Object.values(o).forEach((f) => f.mockReset())
  o.overview.mockResolvedValue(OVERVIEW)
  o.schools.mockResolvedValue(SCHOOLS)
  o.draft.mockResolvedValue({ created: 1, skipped: 0 })
  o.approve.mockResolvedValue({ approved: 3 })
  o.saveSettings.mockResolvedValue({})
  o.messages.mockResolvedValue([])
})

describe('admin outreach', () => {
  it('shows where sending stands and the numbers', async () => {
    render(<AdminOutreach />)
    expect(await screen.findByText('arpith@gmail.com')).toBeInTheDocument()
    expect(screen.getByText(/warming up the mailbox/)).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Sending on' })).not.toBeChecked()
    fireEvent.click(screen.getByRole('switch', { name: 'Sending on' }))
    await waitFor(() => expect(o.saveSettings).toHaveBeenCalledWith({ sending_enabled: true }))
  })

  it('lists schools with who to write to, and drafts for the selected ones', async () => {
    render(<AdminOutreach />)
    expect(await screen.findByText('Sunrise Vidyalaya')).toBeInTheDocument()
    expect(screen.getByText('Dr. Meena Iyer (Principal)')).toBeInTheDocument()
    expect(screen.getByText('None found')).toBeInTheDocument()
    expect(screen.getByText('Drafted')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Select Sunrise Vidyalaya'))
    fireEvent.click(screen.getByRole('button', { name: 'Draft emails' }))
    await waitFor(() => expect(o.draft).toHaveBeenCalledWith([1]))
    expect(await screen.findByText(/Drafted emails for 1 school/)).toBeInTheDocument()
  })

  it('changes a status straight from the list', async () => {
    o.editSchool.mockResolvedValue({ ...SCHOOLS.schools[0], status: 'demo_booked' })
    render(<AdminOutreach />)
    fireEvent.change(await screen.findByLabelText('Status of Sunrise Vidyalaya'), { target: { value: 'demo_booked' } })
    await waitFor(() => expect(o.editSchool).toHaveBeenCalledWith(1, { status: 'demo_booked' }))
  })

  it('reviews a school’s emails and approves them together', async () => {
    o.messages.mockResolvedValue([
      { id: 11, school_id: 1, school_name: 'Sunrise Vidyalaya', step: 1, to_email: 'office@sunrise.in', subject: 'Timetables at Sunrise Vidyalaya', body: 'Dear Dr. Iyer,', status: 'draft' },
      { id: 12, school_id: 1, school_name: 'Sunrise Vidyalaya', step: 2, to_email: 'office@sunrise.in', subject: 'Re: Timetables', body: 'Just bringing this back', status: 'draft' },
    ])
    render(<AdminOutreach />)
    fireEvent.click(await screen.findByRole('button', { name: /Review emails/ }))
    const card = await screen.findByRole('article', { name: 'Emails to Sunrise Vidyalaya' })
    expect(within(card).getByDisplayValue('Dear Dr. Iyer,')).toBeInTheDocument()
    fireEvent.click(within(card).getByRole('button', { name: 'Follow-up 1' }))
    expect(within(card).getByDisplayValue('Just bringing this back')).toBeInTheDocument()
    fireEvent.click(within(card).getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(o.approve).toHaveBeenCalledWith([1]))
  })
})
