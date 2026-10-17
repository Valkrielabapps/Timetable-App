import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import GenerationFailedDialog from './GenerationFailedDialog'

const MESSAGE = [
  'Math for Grade 10 - B needs 8 periods/week, but only 5 periods are allowed.',
  'Math for Grade 10 - A needs 8 periods/week, but only 5 periods are allowed.',
].join('\n')

describe('GenerationFailedDialog', () => {
  it('lists every reason as its own numbered item, with the summary above', () => {
    render(<GenerationFailedDialog open explanation="Math doesn't fit." message={MESSAGE} onClose={() => {}} />)
    expect(screen.getByRole('dialog', { name: /couldn.t build a conflict-free timetable/i })).toBeInTheDocument()
    expect(screen.getByText("Math doesn't fit.")).toBeInTheDocument()
    expect(screen.getByText('Reasons (2)')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText(/Grade 10 - A needs 8/)).toBeInTheDocument()
  })

  it('closes with the button and with Escape', () => {
    const onClose = vi.fn()
    render(<GenerationFailedDialog open message="One reason" onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Got it' }))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('can send the admin to the Constraints tab', () => {
    const onClose = vi.fn()
    const onOpenConstraints = vi.fn()
    render(<GenerationFailedDialog open message="x" onClose={onClose} onOpenConstraints={onOpenConstraints} />)
    fireEvent.click(screen.getByRole('button', { name: 'Review constraints' }))
    expect(onOpenConstraints).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('renders nothing when closed', () => {
    render(<GenerationFailedDialog open={false} message="x" onClose={() => {}} />)
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
