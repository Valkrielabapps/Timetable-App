import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConstraintInterpretation from './ConstraintInterpretation'

/**
 * These assert on the properties the confirmation step depends on to be worth
 * anything, rather than on styling.
 *
 * A rule used to be matched against nine fixed types, so a misreading showed
 * itself by visibly doing nothing. Rules now go through a general
 * representation where almost any sentence yields a valid rule, so a
 * misreading schedules the wrong thing faithfully instead. Against real rules,
 * about a third of the ones that parsed cleanly meant something other than
 * what was typed - and nearly all of those were obvious to read. This panel is
 * what turns "obvious to read" into "caught", so: the sentence has to be
 * shown, nothing may save without an explicit yes, and refusing has to be as
 * easy as accepting.
 */

const UNDERSTOOD = {
  understood: true,
  sentence: 'Mrs. Rao has no Grade 10 - C periods in the last period of the day.',
  rule: { form: 'count', scope: [], relation: '==', value: 0 },
  unknown_names: [],
}

describe('ConstraintInterpretation', () => {
  it('shows both what was typed and what was understood', () => {
    render(
      <ConstraintInterpretation
        typed="rao mam shd not get 10C in last period"
        interpretation={UNDERSTOOD}
        saving={false}
        onConfirm={vi.fn()}
        onReword={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    // Both, because the check is a comparison - the reading alone gives
    // nothing to compare it against.
    expect(screen.getByText('rao mam shd not get 10C in last period')).toBeInTheDocument()
    expect(screen.getByText(UNDERSTOOD.sentence)).toBeInTheDocument()
  })

  it('saves nothing until the reading is explicitly accepted', () => {
    const onConfirm = vi.fn()
    render(
      <ConstraintInterpretation
        typed="x" interpretation={UNDERSTOOD} saving={false}
        onConfirm={onConfirm} onReword={vi.fn()} onCancel={vi.fn()}
      />,
    )
    expect(onConfirm).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /that's right/i }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('offers rejecting as plainly as accepting', () => {
    const onReword = vi.fn()
    render(
      <ConstraintInterpretation
        typed="x" interpretation={UNDERSTOOD} saving={false}
        onConfirm={vi.fn()} onReword={onReword} onCancel={vi.fn()}
      />,
    )
    // A "no" buried behind a link or a second click makes accepting a wrong
    // reading the path of least resistance, which defeats the whole step.
    fireEvent.click(screen.getByRole('button', { name: /reword/i }))
    expect(onReword).toHaveBeenCalledTimes(1)
  })

  it('blocks saving a rule that names someone the school does not have', () => {
    render(
      <ConstraintInterpretation
        typed="Verma is off on Mondays"
        interpretation={{ ...UNDERSTOOD, unknown_names: ['Mr. Verma'] }}
        saving={false} onConfirm={vi.fn()} onReword={vi.fn()} onCancel={vi.fn()}
      />,
    )
    // Caught here, while they are still looking at what they typed - rather
    // than as a warning on a timetable that has already been generated.
    expect(screen.getByRole('button', { name: /that's right/i })).toBeDisabled()
    expect(screen.getByText(/Mr\. Verma/)).toBeInTheDocument()
  })

  it('leaves rewording available even when saving is blocked', () => {
    const onReword = vi.fn()
    render(
      <ConstraintInterpretation
        typed="x" interpretation={{ ...UNDERSTOOD, unknown_names: ['Mr. Verma'] }}
        saving={false} onConfirm={vi.fn()} onReword={onReword} onCancel={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /reword/i }))
    expect(onReword).toHaveBeenCalledTimes(1)
  })

  it('disables the buttons while a save is in flight', () => {
    render(
      <ConstraintInterpretation
        typed="x" interpretation={UNDERSTOOD} saving
        onConfirm={vi.fn()} onReword={vi.fn()} onCancel={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /reword/i })).toBeDisabled()
  })
})

describe('ConstraintInterpretation, when the parser declined', () => {
  const DECLINED = {
    understood: false,
    reason: 'too_vague',
    explanation: '"Balanced" does not have a measurable meaning here.',
    question: 'What would make it balanced - even daily loads, or fewer gaps?',
    readings: [],
  }

  it('shows the explanation and the question it asked', () => {
    render(
      <ConstraintInterpretation
        typed="make the timetable balanced" interpretation={DECLINED}
        saving={false} onConfirm={vi.fn()} onReword={vi.fn()} onCancel={vi.fn()}
      />,
    )
    expect(screen.getByText(/measurable meaning/)).toBeInTheDocument()
    expect(screen.getByText(/even daily loads/)).toBeInTheDocument()
  })

  it('offers no way to save, because there is nothing to save', () => {
    render(
      <ConstraintInterpretation
        typed="x" interpretation={DECLINED} saving={false}
        onConfirm={vi.fn()} onReword={vi.fn()} onCancel={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /that's right/i })).not.toBeInTheDocument()
  })

  it('lists the alternative readings when the rule was ambiguous', () => {
    render(
      <ConstraintInterpretation
        typed="only 12th can use the physics lab in the afternoon"
        interpretation={{
          understood: false, reason: 'ambiguous',
          explanation: 'Two readings block opposite groups.',
          question: 'Which did you mean?',
          readings: [
            'Afternoons are reserved for Grade 12',
            'Grade 12 may only use the lab in afternoons',
          ],
        }}
        saving={false} onConfirm={vi.fn()} onReword={vi.fn()} onCancel={vi.fn()}
      />,
    )
    expect(screen.getByText('Afternoons are reserved for Grade 12')).toBeInTheDocument()
    expect(screen.getByText('Grade 12 may only use the lab in afternoons')).toBeInTheDocument()
  })

  it('says a rule it cannot handle is the app\'s limitation, not the admin\'s mistake', () => {
    render(
      <ConstraintInterpretation
        typed="chem lab needs a gap between practicals"
        interpretation={{
          understood: false, reason: 'not_supported',
          explanation: 'Rules about rooms cannot be handled yet.',
          readings: [],
        }}
        saving={false} onConfirm={vi.fn()} onReword={vi.fn()} onCancel={vi.fn()}
      />,
    )
    expect(screen.getByText(/We can't handle this kind of rule yet/)).toBeInTheDocument()
  })
})
