import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ConstraintsTab from './ConstraintsTab'
import { api } from '../api'

vi.mock('../api', () => ({
  api: {
    interpretConstraint: vi.fn(),
    confirmConstraint: vi.fn(),
    parseConstraintsBatch: vi.fn(),
    deleteConstraint: vi.fn(),
    reparseConstraint: vi.fn(),
    updateConstraint: vi.fn(),
  },
}))

vi.mock('../hooks/useSchoolData', () => ({
  useTimetables: () => ({ data: [] }),
  useTimetable: () => ({ data: null }),
}))

/**
 * The two-step entry flow: read the rule back, then save what was read.
 *
 * The property under test is that nothing reaches the database without someone
 * agreeing to a sentence. Everything else here is in service of that - the
 * reading has to be shown before the save, the save has to send the rule that
 * was shown, and declining has to leave nothing behind.
 */

const READING = {
  understood: true,
  sentence: 'No class has PE periods on Friday.',
  rule: { form: 'count', scope: ['class_group'], relation: '==', value: 0 },
  unknown_names: [],
}

function setup() {
  const onReload = vi.fn().mockResolvedValue(undefined)
  render(
    <ConstraintsTab schoolId={1} classGroups={[]} constraints={[]} onReload={onReload} />,
  )
  return { onReload }
}

function type(text) {
  fireEvent.change(screen.getByPlaceholderText(/Math can't immediately follow PE/), {
    target: { value: text },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Add' }))
}

describe('ConstraintsTab rule entry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.interpretConstraint.mockResolvedValue(READING)
    api.confirmConstraint.mockResolvedValue({ id: 1 })
  })

  it('reads the rule back before saving anything', async () => {
    setup()
    type('no PE on fridays')

    expect(await screen.findByText(READING.sentence)).toBeInTheDocument()
    // The whole point: interpreting is not saving.
    expect(api.confirmConstraint).not.toHaveBeenCalled()
  })

  it('saves the rule that was shown, not the text that produced it', async () => {
    const { onReload } = setup()
    type('no PE on fridays')
    fireEvent.click(await screen.findByRole('button', { name: /that's right/i }))

    await waitFor(() => expect(api.confirmConstraint).toHaveBeenCalledWith(
      1, READING.rule, 'no PE on fridays',
    ))
    // Re-parsing the text here could return something different from what they
    // read, and then the sentence they agreed to would not be what was stored.
    await waitFor(() => expect(onReload).toHaveBeenCalled())
  })

  it('puts the original text back in the box when the reading is rejected', async () => {
    setup()
    type('no PE on fridays')
    fireEvent.click(await screen.findByRole('button', { name: /reword/i }))

    const input = screen.getByPlaceholderText(/Math can't immediately follow PE/)
    // Not cleared: they are usually changing a word, and retyping the whole
    // rule is enough friction to make accepting a wrong reading the easier
    // option.
    expect(input).toHaveValue('no PE on fridays')
    expect(api.confirmConstraint).not.toHaveBeenCalled()
  })

  it('leaves nothing behind when the reading is cancelled', async () => {
    setup()
    type('no PE on fridays')
    fireEvent.click(await screen.findByRole('button', { name: /cancel/i }))

    expect(screen.getByPlaceholderText(/Math can't immediately follow PE/)).toHaveValue('')
    expect(screen.queryByText(READING.sentence)).not.toBeInTheDocument()
    expect(api.confirmConstraint).not.toHaveBeenCalled()
  })

  it('replaces the input with the reading rather than showing both', async () => {
    setup()
    type('no PE on fridays')
    await screen.findByText(READING.sentence)
    // Two inputs on screen invites typing the next rule before answering for
    // this one, which is how an unanswered reading gets abandoned.
    expect(screen.queryByPlaceholderText(/Math can't immediately follow PE/)).not.toBeInTheDocument()
  })

  it('shows a declined reading with no way to save it', async () => {
    api.interpretConstraint.mockResolvedValue({
      understood: false,
      reason: 'too_vague',
      explanation: '"Balanced" has no measurable meaning here.',
      readings: [],
    })
    setup()
    type('make it balanced')

    expect(await screen.findByText(/measurable meaning/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /that's right/i })).not.toBeInTheDocument()
  })

  it('surfaces an interpretation failure instead of saving blindly', async () => {
    api.interpretConstraint.mockRejectedValue(new Error('Rule interpretation is unavailable'))
    setup()
    type('no PE on fridays')

    expect(await screen.findByText(/unavailable/)).toBeInTheDocument()
    expect(api.confirmConstraint).not.toHaveBeenCalled()
  })

  it('does not interpret an empty rule', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(api.interpretConstraint).not.toHaveBeenCalled()
  })
})
